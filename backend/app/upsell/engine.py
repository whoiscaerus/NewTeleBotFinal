"""
Upsell scoring engine.

Generates personalized recommendations using behavioral & performance signals.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.analytics.models import DailyRollups
from backend.app.approvals.models import Approval
from backend.app.subscriptions.models import Subscription
from backend.app.upsell.models import (
    Experiment,
    Exposure,
    Recommendation,
    RecommendationType,
    Variant,
)

logger = logging.getLogger(__name__)


class UpsellEngine:
    """
    AI-powered upsell recommendation engine.

    Scores users based on:
    - Usage: approvals, alerts created
    - Performance: PnL stability, drawdown control
    - Intent: billing page visits, feature exploration
    - Cohort: comparison to similar users
    """

    def __init__(
        self,
        db: AsyncSession,
        score_threshold: float = 0.6,
        lookback_days: int = 30,
    ):
        """
        Initialize upsell engine.

        Args:
            db: Database session
            score_threshold: Minimum score to generate recommendation (0.0-1.0)
            lookback_days: Days of history to analyze
        """
        self.db = db
        self.score_threshold = score_threshold
        self.lookback_days = lookback_days

    async def score_user(self, user_id: str) -> list[Recommendation]:
        """
        Generate personalized recommendations for a user.

        Args:
            user_id: User ID to score

        Returns:
            List of recommendations sorted by score (highest first)

        Example:
            >>> engine = UpsellEngine(db)
            >>> recs = await engine.score_user("user-123")
            >>> assert all(r.score >= 0.6 for r in recs)
        """
        logger.info(f"Scoring user {user_id} for upsell recommendations")

        # Calculate component scores
        usage_score = await self._calculate_usage_score(user_id)
        performance_score = await self._calculate_performance_score(user_id)
        intent_score = await self._calculate_intent_score(user_id)
        cohort_score = await self._calculate_cohort_score(user_id)

        logger.info(
            f"User {user_id} scores: usage={usage_score:.2f}, "
            f"performance={performance_score:.2f}, intent={intent_score:.2f}, "
            f"cohort={cohort_score:.2f}"
        )

        # Get user's current subscription
        subscription = await self._get_user_subscription(user_id)

        # Generate recommendations for each type
        recommendations = []

        # Plan upgrade recommendation
        if subscription and subscription.tier != "premium":
            plan_score = self._weighted_score(
                usage=usage_score,
                performance=performance_score,
                intent=intent_score,
                cohort=cohort_score,
                weights={
                    "usage": 0.3,
                    "performance": 0.3,
                    "intent": 0.25,
                    "cohort": 0.15,
                },
            )
            if plan_score >= self.score_threshold:
                rec = await self._create_recommendation(
                    user_id=user_id,
                    rec_type=RecommendationType.PLAN_UPGRADE,
                    score=plan_score,
                    usage_score=usage_score,
                    performance_score=performance_score,
                    intent_score=intent_score,
                    cohort_score=cohort_score,
                )
                recommendations.append(rec)

        # Copy-trading upsell (+30% typical revenue lift)
        if performance_score > 0.7 and usage_score > 0.6:
            copy_score = self._weighted_score(
                usage=usage_score,
                performance=performance_score,
                intent=intent_score,
                cohort=cohort_score,
                weights={
                    "usage": 0.2,
                    "performance": 0.5,
                    "intent": 0.2,
                    "cohort": 0.1,
                },
            )
            if copy_score >= self.score_threshold:
                rec = await self._create_recommendation(
                    user_id=user_id,
                    rec_type=RecommendationType.COPY_TRADING,
                    score=copy_score,
                    usage_score=usage_score,
                    performance_score=performance_score,
                    intent_score=intent_score,
                    cohort_score=cohort_score,
                )
                recommendations.append(rec)

        # Analytics pro add-on
        if usage_score > 0.7:
            analytics_score = self._weighted_score(
                usage=usage_score,
                performance=performance_score,
                intent=intent_score,
                cohort=cohort_score,
                weights={
                    "usage": 0.5,
                    "performance": 0.2,
                    "intent": 0.2,
                    "cohort": 0.1,
                },
            )
            if analytics_score >= self.score_threshold:
                rec = await self._create_recommendation(
                    user_id=user_id,
                    rec_type=RecommendationType.ANALYTICS_PRO,
                    score=analytics_score,
                    usage_score=usage_score,
                    performance_score=performance_score,
                    intent_score=intent_score,
                    cohort_score=cohort_score,
                )
                recommendations.append(rec)

        # Device slots (if high usage)
        if usage_score > 0.8:
            device_score = self._weighted_score(
                usage=usage_score,
                performance=performance_score,
                intent=intent_score,
                cohort=cohort_score,
                weights={
                    "usage": 0.6,
                    "performance": 0.1,
                    "intent": 0.2,
                    "cohort": 0.1,
                },
            )
            if device_score >= self.score_threshold:
                rec = await self._create_recommendation(
                    user_id=user_id,
                    rec_type=RecommendationType.DEVICE_SLOTS,
                    score=device_score,
                    usage_score=usage_score,
                    performance_score=performance_score,
                    intent_score=intent_score,
                    cohort_score=cohort_score,
                )
                recommendations.append(rec)

        # Sort by score descending
        recommendations.sort(key=lambda r: r.score, reverse=True)

        logger.info(
            f"Generated {len(recommendations)} recommendations for user {user_id}"
        )
        return recommendations

    async def _calculate_usage_score(self, user_id: str) -> float:
        """
        Calculate usage score (0.0-1.0) based on approvals.

        High usage = more likely to benefit from premium features.
        """
        cutoff = datetime.utcnow() - timedelta(days=self.lookback_days)

        # Count approvals
        approvals_query = select(func.count(Approval.id)).where(
            and_(Approval.user_id == user_id, Approval.created_at >= cutoff)
        )
        approvals_result = await self.db.execute(approvals_query)
        approval_count = approvals_result.scalar() or 0

        # Scoring: 20+ approvals = 1.0
        approval_score = min(approval_count / 20.0, 1.0)

        return approval_score

    async def _calculate_performance_score(self, user_id: str) -> float:
        """
        Calculate performance score (0.0-1.0) based on PnL stability.

        Positive PnL + low drawdown = high score.
        Uses DailyRollups to compute aggregate performance.
        """
        cutoff = datetime.utcnow() - timedelta(days=self.lookback_days)

        # Get recent daily rollups and aggregate
        rollups_query = select(DailyRollups).where(
            and_(
                DailyRollups.user_id == user_id,
                DailyRollups.created_at >= cutoff,
            )
        )
        rollups_result = await self.db.execute(rollups_query)
        rollups = list(rollups_result.scalars().all())

        if not rollups:
            return 0.0

        # Calculate aggregate metrics
        total_pnl = sum(float(r.net_pnl or 0) for r in rollups)
        total_trades = sum(r.total_trades or 0 for r in rollups)
        winning_trades = sum(r.winning_trades or 0 for r in rollups)

        if total_trades == 0:
            return 0.0

        # Estimate return based on PnL (assume $10k account)
        estimated_return = total_pnl / 10000.0 if total_pnl > 0 else 0.0
        return_score = min(estimated_return / 0.10, 1.0)  # 10%+ return = 1.0

        # Calculate win rate as performance indicator
        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0
        win_rate_bonus = max((win_rate - 0.5) * 0.5, 0.0)  # Bonus for >50% win rate

        return min(return_score + win_rate_bonus, 1.0)

    async def _calculate_intent_score(self, user_id: str) -> float:
        """
        Calculate intent score (0.0-1.0) based on billing page visits.

        High intent = visited billing, explored features recently.
        """
        # TODO: Integrate with audit logs (PR-008) to track page visits
        # For now, return moderate score
        return 0.5

    async def _calculate_cohort_score(self, user_id: str) -> float:
        """
        Calculate cohort score (0.0-1.0) based on comparison to similar users.

        How does this user compare to others in their cohort?
        """
        # TODO: Implement cohort analysis (PR-056 revenue cohorts)
        # For now, return moderate score
        return 0.5

    def _weighted_score(
        self,
        usage: float,
        performance: float,
        intent: float,
        cohort: float,
        weights: dict[str, float],
    ) -> float:
        """
        Calculate weighted score from components.

        Args:
            usage: Usage score (0.0-1.0)
            performance: Performance score (0.0-1.0)
            intent: Intent score (0.0-1.0)
            cohort: Cohort score (0.0-1.0)
            weights: Weight dict (must sum to 1.0)

        Returns:
            Weighted score (0.0-1.0)
        """
        return (
            usage * weights.get("usage", 0.0)
            + performance * weights.get("performance", 0.0)
            + intent * weights.get("intent", 0.0)
            + cohort * weights.get("cohort", 0.0)
        )

    async def _create_recommendation(
        self,
        user_id: str,
        rec_type: RecommendationType,
        score: float,
        usage_score: float,
        performance_score: float,
        intent_score: float,
        cohort_score: float,
    ) -> Recommendation:
        """
        Create a recommendation with variant assignment.

        Args:
            user_id: User ID
            rec_type: Type of recommendation
            score: Overall score
            usage_score: Usage component
            performance_score: Performance component
            intent_score: Intent component
            cohort_score: Cohort component

        Returns:
            Recommendation instance (not yet persisted)
        """
        # Get active experiment for this recommendation type
        variant = await self._assign_variant(user_id, rec_type)

        # Generate copy based on type and variant
        headline, copy = self._generate_copy(rec_type, variant)
        discount = variant.discount_percent if variant else None

        rec = Recommendation(
            user_id=user_id,
            recommendation_type=rec_type.value,
            score=score,
            variant_id=variant.id if variant else None,
            usage_score=usage_score,
            performance_score=performance_score,
            intent_score=intent_score,
            cohort_score=cohort_score,
            headline=headline,
            copy=copy,
            discount_percent=discount,
            expires_at=datetime.utcnow() + timedelta(days=7),  # 7-day urgency window
        )

        return rec

    async def _assign_variant(
        self, user_id: str, rec_type: RecommendationType
    ) -> Optional[Variant]:
        """
        Assign user to A/B test variant for this recommendation type.

        Returns:
            Variant or None if no active experiment
        """
        # Find active experiment for this type
        exp_query = (
            select(Experiment)
            .where(
                and_(
                    Experiment.recommendation_type == rec_type.value,
                    Experiment.status == "active",
                )
            )
            .limit(1)
        )
        exp_result = await self.db.execute(exp_query)
        experiment = exp_result.scalar_one_or_none()

        if not experiment:
            return None

        # Check if user already exposed to this experiment
        exposure_query = select(Exposure).where(
            and_(Exposure.user_id == user_id, Exposure.experiment_id == experiment.id)
        )
        exposure_result = await self.db.execute(exposure_query)
        existing_exposure = exposure_result.scalar_one_or_none()

        if existing_exposure:
            # Return same variant
            variant_query = select(Variant).where(
                Variant.id == existing_exposure.variant_id
            )
            variant_result = await self.db.execute(variant_query)
            return variant_result.scalar_one_or_none()

        # Assign to variant based on traffic split
        variants_query = select(Variant).where(Variant.experiment_id == experiment.id)
        variants_result = await self.db.execute(variants_query)
        variants = list(variants_result.scalars().all())

        if not variants:
            return None

        # Simple deterministic assignment: hash user_id
        user_hash = hash(user_id + experiment.id)
        if (user_hash % 100) < experiment.traffic_split_percent:
            # Assign to variant (non-control)
            variant = next((v for v in variants if not v.is_control), variants[0])
        else:
            # Assign to control
            variant = next((v for v in variants if v.is_control), variants[0])

        return variant

    def _generate_copy(
        self, rec_type: RecommendationType, variant: Optional[Variant]
    ) -> tuple[str, str]:
        """
        Generate headline and copy for recommendation.

        Args:
            rec_type: Recommendation type
            variant: Assigned variant (or None)

        Returns:
            (headline, copy) tuple
        """
        if variant:
            return (variant.headline, variant.copy)

        # Default copy by type
        copy_map = {
            RecommendationType.PLAN_UPGRADE: (
                "Upgrade to Premium for Advanced Features",
                "Unlock auto-execution, advanced analytics, and priority support. "
                "Join thousands of traders maximizing their profits.",
            ),
            RecommendationType.COPY_TRADING: (
                "Start Copy Trading Today",
                "Follow top performers and automate your trading. "
                "Our copy traders see 30% higher returns on average.",
            ),
            RecommendationType.ANALYTICS_PRO: (
                "Get Analytics Pro for Deeper Insights",
                "Advanced performance metrics, custom reports, and risk analysis tools. "
                "Make data-driven trading decisions.",
            ),
            RecommendationType.DEVICE_SLOTS: (
                "Expand Your Trading Setup",
                "Add more device slots to trade from anywhere. "
                "Perfect for multi-device traders who need flexibility.",
            ),
        }

        return copy_map.get(
            rec_type,
            (
                "Upgrade Your Account",
                "Unlock premium features and take your trading to the next level.",
            ),
        )

    async def _get_user_subscription(self, user_id: str) -> Optional[Subscription]:
        """Get user's current subscription."""
        query = (
            select(Subscription)
            .where(
                and_(Subscription.user_id == user_id, Subscription.status == "active")
            )
            .order_by(desc(Subscription.created_at))
            .limit(1)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
