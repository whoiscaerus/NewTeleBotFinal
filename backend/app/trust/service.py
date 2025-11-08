"""Trust scoring service with calculations and telemetry integration."""

import logging
from datetime import datetime
from typing import Any, Optional

from prometheus_client import Counter, Histogram
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.trust.graph import (
    _build_graph_from_endorsements,
    _calculate_percentiles,
    calculate_trust_scores,
)
from backend.app.trust.models import (
    Endorsement,
    TrustCalculationLog,
    User,
    UserTrustScore,
)

logger = logging.getLogger(__name__)

# Telemetry metrics
trust_scores_calculated_total = Counter(
    "trust_scores_calculated_total",
    "Total trust scores calculated",
    labelnames=["tier"],
)

trust_score_calculation_duration_seconds = Histogram(
    "trust_score_calculation_duration_seconds",
    "Time taken to calculate trust scores",
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0),
)

users_processed = Histogram(
    "trust_calculation_users_processed",
    "Number of users processed in calculation",
    buckets=(1, 5, 10, 25, 50, 100, 500, 1000),
)


class TrustScoringService:
    """Service for calculating and managing trust scores."""

    @staticmethod
    async def calculate_all_trust_scores(db: AsyncSession) -> dict[str, Any]:
        """
        Calculate trust scores for all users in the system.

        This is the main orchestration function for trust score calculation.
        It:
        1. Fetches all endorsements
        2. Builds the endorsement graph
        3. Fetches user performance data
        4. Calculates trust scores for all users
        5. Stores results in database
        6. Updates telemetry

        Args:
            db: Async database session

        Returns:
            {
                "total_users_processed": int,
                "users_scored": int,
                "calculation_duration_seconds": float,
                "scores_by_tier": {"bronze": count, "silver": count, "gold": count},
                "timestamp": ISO datetime string
            }

        Raises:
            Exception: On database error

        Example:
            >>> result = await TrustScoringService.calculate_all_trust_scores(db)
            >>> print(result["users_scored"])
            5432
        """
        import time

        start_time = time.time()

        try:
            # Fetch all endorsements
            stmt = select(Endorsement).where(Endorsement.revoked_at.is_(None))
            result = await db.execute(stmt)
            endorsements = result.scalars().all()

            logger.info(
                f"Processing {len(endorsements)} endorsements for trust calculation"
            )

            # Build graph
            graph = _build_graph_from_endorsements(endorsements)

            # Fetch all users with their creation dates
            stmt = select(User).where(User.is_active.is_(True))
            result = await db.execute(stmt)
            users = result.scalars().all()

            created_map = {user.id: user.created_at for user in users}
            users_processed.observe(len(users))

            # Fetch performance data for all users (from performance metrics table)
            # This assumes performance_data is available in the database
            perf_data = await _get_performance_data(db, list(created_map.keys()))

            # Calculate trust scores (deterministic algorithm)
            scores = calculate_trust_scores(graph, perf_data, created_map)

            # Calculate percentiles
            score_values = {uid: data["score"] for uid, data in scores.items()}
            percentiles = _calculate_percentiles(score_values)

            # Store in database
            tier_counts = {"bronze": 0, "silver": 0, "gold": 0}
            stored_count = 0

            for user_id, score_data in scores.items():
                tier = score_data["tier"]
                tier_counts[tier] = tier_counts.get(tier, 0) + 1

                # Get previous score for audit log
                stmt = select(UserTrustScore).where(UserTrustScore.user_id == user_id)
                result = await db.execute(stmt)
                previous_record = result.scalar_one_or_none()
                previous_score = previous_record.score if previous_record else None

                # Create or update trust score
                trust_score = UserTrustScore(
                    id=str(__import__("uuid").uuid4()),
                    user_id=user_id,
                    score=score_data["score"],
                    performance_component=score_data["performance"],
                    tenure_component=score_data["tenure"],
                    endorsement_component=score_data["endorsements"],
                    tier=tier,
                    percentile=percentiles.get(user_id, 0),
                    calculated_at=datetime.utcnow(),
                    valid_until=datetime.utcnow()
                    + __import__("datetime").timedelta(hours=24),
                )

                # Update if exists (upsert pattern)
                if previous_record:
                    # Delete old record
                    await db.delete(previous_record)

                db.add(trust_score)
                stored_count += 1

                # Log calculation
                audit_log = TrustCalculationLog(
                    id=str(__import__("uuid").uuid4()),
                    user_id=user_id,
                    previous_score=previous_score,
                    new_score=score_data["score"],
                    input_graph_nodes=graph.number_of_nodes(),
                    input_graph_edges=graph.number_of_edges(),
                    algorithm_version="1.0",
                    calculated_at=datetime.utcnow(),
                    notes=f"Batch recalculation - tier {tier}",
                )
                db.add(audit_log)

                # Increment telemetry counter
                trust_scores_calculated_total.labels(tier=tier).inc()

            # Commit all changes
            await db.commit()

            duration = time.time() - start_time
            trust_score_calculation_duration_seconds.observe(duration)

            logger.info(
                f"Trust score calculation complete: {stored_count} scores, "
                f"{duration:.2f}s, Bronze:{tier_counts['bronze']} Silver:{tier_counts['silver']} Gold:{tier_counts['gold']}"
            )

            return {
                "total_users_processed": len(users),
                "users_scored": stored_count,
                "calculation_duration_seconds": duration,
                "scores_by_tier": tier_counts,
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error calculating trust scores: {e}", exc_info=True)
            raise

    @staticmethod
    async def calculate_single_user_score(
        user_id: str, db: AsyncSession
    ) -> Optional[dict]:
        """
        Calculate trust score for a single user.

        This is useful for on-demand score updates when a user's performance changes
        or when they receive a new endorsement.

        Args:
            user_id: User ID to score
            db: Async database session

        Returns:
            {
                "user_id": str,
                "score": float,
                "tier": str,
                "percentile": int,
                "components": {...}
            } or None if user not found

        Example:
            >>> score = await TrustScoringService.calculate_single_user_score("user123", db)
            >>> if score:
            ...     print(f"User score: {score['score']}")
        """
        try:
            # Fetch user
            stmt = select(User).where(User.id == user_id)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                logger.warning(f"User not found: {user_id}")
                return None

            # Fetch endorsements for this user
            stmt = select(Endorsement).where(Endorsement.revoked_at.is_(None))
            result = await db.execute(stmt)
            endorsements = result.scalars().all()

            # Build graph
            graph = _build_graph_from_endorsements(endorsements)

            # Fetch all users for context
            stmt = select(User).where(User.is_active.is_(True))
            result = await db.execute(stmt)
            all_users = result.scalars().all()

            created_map = {u.id: u.created_at for u in all_users}

            # Fetch performance data
            perf_data = await _get_performance_data(db, [user_id])

            # Calculate scores for all users
            scores = calculate_trust_scores(graph, perf_data, created_map)

            if user_id not in scores:
                logger.warning(f"Could not calculate score for user: {user_id}")
                return None

            score_data = scores[user_id]

            # Calculate percentiles
            score_values = {uid: data["score"] for uid, data in scores.items()}
            percentiles = _calculate_percentiles(score_values)

            result_score = {
                "user_id": user_id,
                "score": score_data["score"],
                "tier": score_data["tier"],
                "percentile": percentiles.get(user_id, 0),
                "components": {
                    "performance": score_data["performance"],
                    "tenure": score_data["tenure"],
                    "endorsements": score_data["endorsements"],
                },
            }

            return result_score

        except Exception as e:
            logger.error(
                f"Error calculating score for user {user_id}: {e}", exc_info=True
            )
            raise


async def _get_performance_data(
    db: AsyncSession, user_ids: list
) -> dict[str, dict[str, float]]:
    """
    Fetch performance data for users.

    This would typically fetch from a performance_metrics table or
    calculation service. For now, returns placeholder data.

    Args:
        db: Database session
        user_ids: List of user IDs

    Returns:
        {user_id: {win_rate, sharpe_ratio, profit_factor}}

    Example:
        >>> perf = await _get_performance_data(db, ["user1", "user2"])
        >>> perf["user1"]["win_rate"]
        0.65
    """
    # TODO: Fetch from performance_metrics table once it's available
    # For now, return reasonable defaults
    perf_data = {}

    for user_id in user_ids:
        perf_data[user_id] = {
            "win_rate": 0.55,  # Default 55% win rate
            "sharpe_ratio": 1.0,  # Default Sharpe 1.0
            "profit_factor": 1.5,  # Default profit factor 1.5x
        }

    return perf_data


def _calculate_percentiles(scores: dict[str, float]) -> dict[str, int]:
    """
    Calculate percentile rank for each user score.

    Args:
        scores: {user_id: score_value}

    Returns:
        {user_id: percentile (0-100)}

    Example:
        >>> percentiles = _calculate_percentiles({"u1": 90, "u2": 70, "u3": 80})
        >>> percentiles["u1"]
        100
    """
    if not scores:
        return {}

    sorted_scores = sorted(scores.values(), reverse=True)
    percentiles = {}

    for user_id, score in scores.items():
        # Count how many users scored lower
        lower_count = sum(1 for s in sorted_scores if s < score)
        percentile = int((lower_count / len(sorted_scores)) * 100)
        percentiles[user_id] = min(100, max(0, percentile))

    return percentiles
