"""Gamification service for PR-088.

Business logic for badges, XP tracking, level progression, and leaderboards.

XP Calculation:
- Base XP: 10 XP per approved trade
- PnL Stability Bonus: Up to 50 XP for consistent wins (risk-adjusted)
- Badge XP: Earned from achieving milestones

Level System:
- Bronze: 0-1000 XP
- Silver: 1001-5000 XP
- Gold: 5001-15000 XP
- Platinum: 15001-50000 XP
- Diamond: 50001+ XP

Badge Triggers:
- "First Trade": Approve 1 trade
- "Getting Started": Approve 10 trades
- "Trader": Approve 50 trades
- "Veteran": Approve 200 trades
- "90-Day Profit Streak": 90 consecutive profitable days
- "Risk Master": Maintain <10% drawdown for 30 days

Leaderboard Ranking:
- Primary: Risk-adjusted return % (Sharpe-like)
- Tiebreaker: Total XP
- Privacy: Opt-in only
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Optional
from uuid import uuid4

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.analytics.equity import EquityEngine
from backend.app.approvals.models import Approval, ApprovalDecision
from backend.app.gamification.models import Badge, EarnedBadge, LeaderboardOptIn, Level
from backend.app.observability import get_metrics

logger = logging.getLogger(__name__)
metrics = get_metrics()


class GamificationService:
    """Service for gamification operations.

    Handles XP accrual, badge awarding, level calculation, and leaderboard.
    """

    # XP Constants
    XP_PER_TRADE = 10
    XP_MAX_STABILITY_BONUS = 50

    # Badge Definitions (will be seeded in DB)
    BADGE_DEFINITIONS = {
        "first_trade": {
            "name": "First Trade",
            "description": "Approved your first trade signal",
            "icon": "🎯",
            "category": "milestone",
            "xp_reward": 50,
        },
        "getting_started": {
            "name": "Getting Started",
            "description": "Approved 10 trade signals",
            "icon": "🚀",
            "category": "milestone",
            "xp_reward": 100,
        },
        "trader": {
            "name": "Trader",
            "description": "Approved 50 trade signals",
            "icon": "💼",
            "category": "milestone",
            "xp_reward": 250,
        },
        "veteran": {
            "name": "Veteran",
            "description": "Approved 200 trade signals",
            "icon": "🏆",
            "category": "milestone",
            "xp_reward": 500,
        },
        "profit_streak_90d": {
            "name": "90-Day Profit Streak",
            "description": "Maintained positive returns for 90 consecutive days",
            "icon": "🔥",
            "category": "streak",
            "xp_reward": 1000,
        },
        "risk_master": {
            "name": "Risk Master",
            "description": "Maintained drawdown below 10% for 30 days",
            "icon": "🛡️",
            "category": "performance",
            "xp_reward": 750,
        },
    }

    # Level Definitions (will be seeded in DB)
    LEVEL_DEFINITIONS = [
        {
            "name": "Bronze",
            "min_xp": 0,
            "max_xp": 1000,
            "icon": "🥉",
            "color": "#CD7F32",
            "perks": '["basic_alerts"]',
        },
        {
            "name": "Silver",
            "min_xp": 1001,
            "max_xp": 5000,
            "icon": "🥈",
            "color": "#C0C0C0",
            "perks": '["basic_alerts", "advanced_charts"]',
        },
        {
            "name": "Gold",
            "min_xp": 5001,
            "max_xp": 15000,
            "icon": "🥇",
            "color": "#FFD700",
            "perks": '["basic_alerts", "advanced_charts", "priority_support"]',
        },
        {
            "name": "Platinum",
            "min_xp": 15001,
            "max_xp": 50000,
            "icon": "💎",
            "color": "#E5E4E2",
            "perks": '["basic_alerts", "advanced_charts", "priority_support", "custom_indicators"]',
        },
        {
            "name": "Diamond",
            "min_xp": 50001,
            "max_xp": None,
            "icon": "💠",
            "color": "#B9F2FF",
            "perks": '["basic_alerts", "advanced_charts", "priority_support", "custom_indicators", "api_access"]',
        },
    ]

    def __init__(self, db: AsyncSession):
        """Initialize service with database session."""
        self.db = db

    async def calculate_user_xp(self, user_id: str) -> int:
        """Calculate total XP for a user.

        XP Sources:
        1. Approved trades: 10 XP each
        2. PnL stability bonus: Up to 50 XP based on risk-adjusted performance
        3. Earned badges: XP reward from each badge

        Args:
            user_id: User ID

        Returns:
            Total XP
        """
        # Count approved trades
        stmt = select(func.count(Approval.id)).where(
            and_(
                Approval.user_id == user_id,
                Approval.decision == ApprovalDecision.APPROVED.value,
            )
        )
        result = await self.db.execute(stmt)
        approved_count = result.scalar() or 0

        # Base XP from trades
        base_xp = approved_count * self.XP_PER_TRADE

        # PnL stability bonus (risk-adjusted)
        stability_bonus = await self._calculate_stability_bonus(user_id)

        # Badge XP
        stmt = (
            select(func.sum(Badge.xp_reward))
            .join(EarnedBadge, EarnedBadge.badge_id == Badge.id)
            .where(EarnedBadge.user_id == user_id)
        )
        result = await self.db.execute(stmt)
        badge_xp = result.scalar() or 0

        total_xp = base_xp + stability_bonus + badge_xp

        logger.info(
            f"Calculated XP for user {user_id}: base={base_xp}, stability={stability_bonus}, badges={badge_xp}, total={total_xp}"
        )

        return total_xp

    async def _calculate_stability_bonus(self, user_id: str) -> int:
        """Calculate PnL stability bonus (risk-adjusted performance).

        Stability Bonus Logic:
        - Calculate Sharpe ratio from last 90 days of equity
        - Sharpe >= 2.0: 50 XP
        - Sharpe >= 1.5: 35 XP
        - Sharpe >= 1.0: 20 XP
        - Sharpe < 1.0: 0 XP

        Args:
            user_id: User ID

        Returns:
            Stability bonus XP (0-50)
        """
        try:
            equity_engine = EquityEngine(self.db)

            # Get last 90 days of data
            end_date = datetime.now(UTC)
            start_date = end_date - timedelta(days=90)

            # Calculate equity series
            equity_series = await equity_engine.compute_equity_series(
                user_id=user_id,
                start_date=start_date,
                end_date=end_date,
            )

            if not equity_series or len(equity_series) < 30:
                # Not enough data
                return 0

            # Calculate daily returns
            returns = []
            for i in range(1, len(equity_series)):
                prev_equity = equity_series[i - 1].final_equity
                curr_equity = equity_series[i].final_equity
                if prev_equity > 0:
                    daily_return = (curr_equity - prev_equity) / prev_equity
                    returns.append(daily_return)

            if not returns:
                return 0

            # Calculate Sharpe ratio (simplified: returns/std, assuming rf=0)
            import statistics

            mean_return = statistics.mean(returns)
            std_return = statistics.stdev(returns) if len(returns) > 1 else 0.0

            if std_return == 0:
                sharpe = 0.0
            else:
                sharpe = (mean_return / std_return) * (252**0.5)  # Annualized

            # Award bonus based on Sharpe
            if sharpe >= 2.0:
                bonus = 50
            elif sharpe >= 1.5:
                bonus = 35
            elif sharpe >= 1.0:
                bonus = 20
            else:
                bonus = 0

            logger.info(
                f"Stability bonus for user {user_id}: sharpe={sharpe:.2f}, bonus={bonus} XP"
            )

            return bonus

        except Exception as e:
            logger.warning(
                f"Failed to calculate stability bonus for user {user_id}: {e}"
            )
            return 0

    async def get_user_level(self, user_id: str) -> Optional[Level]:
        """Get current level for a user based on XP.

        Args:
            user_id: User ID

        Returns:
            Current Level or None if no levels defined
        """
        total_xp = await self.calculate_user_xp(user_id)

        # Find matching level
        stmt = (
            select(Level)
            .where(Level.min_xp <= total_xp)
            .where((Level.max_xp >= total_xp) | (Level.max_xp.is_(None)))
            .order_by(Level.min_xp.desc())
        )

        result = await self.db.execute(stmt)
        level = result.scalar_one_or_none()

        return level

    async def check_and_award_badges(self, user_id: str) -> list[EarnedBadge]:
        """Check if user earned any new badges and award them.

        Badge Triggers:
        - first_trade: 1 approved trade
        - getting_started: 10 approved trades
        - trader: 50 approved trades
        - veteran: 200 approved trades
        - profit_streak_90d: 90 consecutive profitable days
        - risk_master: <10% drawdown for 30 days

        Args:
            user_id: User ID

        Returns:
            List of newly earned badges
        """
        newly_earned = []

        # Get current approved trade count
        stmt = select(func.count(Approval.id)).where(
            and_(
                Approval.user_id == user_id,
                Approval.decision == ApprovalDecision.APPROVED.value,
            )
        )
        result = await self.db.execute(stmt)
        approved_count = result.scalar() or 0

        # Check milestone badges
        milestone_checks = [
            ("first_trade", 1),
            ("getting_started", 10),
            ("trader", 50),
            ("veteran", 200),
        ]

        for badge_key, threshold in milestone_checks:
            if approved_count >= threshold:
                earned = await self._award_badge(user_id, badge_key)
                if earned:
                    newly_earned.append(earned)

        # Check streak/performance badges
        if approved_count >= 10:  # Only check if user has some activity
            # 90-day profit streak
            if await self._check_profit_streak(user_id, days=90):
                earned = await self._award_badge(user_id, "profit_streak_90d")
                if earned:
                    newly_earned.append(earned)

            # Risk master (low drawdown)
            if await self._check_low_drawdown(user_id, days=30, max_dd=0.10):
                earned = await self._award_badge(user_id, "risk_master")
                if earned:
                    newly_earned.append(earned)

        return newly_earned

    async def _award_badge(self, user_id: str, badge_key: str) -> Optional[EarnedBadge]:
        """Award a badge to a user if not already earned.

        Args:
            user_id: User ID
            badge_key: Badge identifier key

        Returns:
            EarnedBadge if newly awarded, None if already had it
        """
        # Find badge by name
        badge_def = self.BADGE_DEFINITIONS.get(badge_key)
        if not badge_def:
            logger.warning(f"Badge definition not found: {badge_key}")
            return None

        stmt = select(Badge).where(Badge.name == badge_def["name"])
        result = await self.db.execute(stmt)
        badge = result.scalar_one_or_none()

        if not badge:
            logger.warning(f"Badge not found in DB: {badge_def['name']}")
            return None

        # Check if already earned
        stmt = select(EarnedBadge).where(
            and_(
                EarnedBadge.user_id == user_id,
                EarnedBadge.badge_id == badge.id,
            )
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            return None  # Already earned

        # Award badge
        earned_badge = EarnedBadge(
            id=str(uuid4()),
            user_id=user_id,
            badge_id=badge.id,
            earned_at=datetime.now(UTC),
        )

        self.db.add(earned_badge)
        await self.db.commit()
        await self.db.refresh(earned_badge)

        # Increment telemetry
        metrics.badges_awarded_total.labels(name=badge.name).inc()

        logger.info(f"Awarded badge '{badge.name}' to user {user_id}")

        return earned_badge

    async def _check_profit_streak(self, user_id: str, days: int) -> bool:
        """Check if user has consecutive profitable days.

        Args:
            user_id: User ID
            days: Number of consecutive days required

        Returns:
            True if streak achieved
        """
        try:
            equity_engine = EquityEngine(self.db)

            end_date = datetime.now(UTC)
            start_date = end_date - timedelta(days=days + 10)  # Extra buffer

            equity_series = await equity_engine.compute_equity_series(
                user_id=user_id,
                start_date=start_date,
                end_date=end_date,
            )

            if not equity_series or len(equity_series) < days:
                return False

            # Check last N days all profitable
            consecutive_profit = 0
            for i in range(len(equity_series) - 1, 0, -1):
                prev_equity = equity_series[i - 1].final_equity
                curr_equity = equity_series[i].final_equity

                if curr_equity > prev_equity:
                    consecutive_profit += 1
                else:
                    break

                if consecutive_profit >= days:
                    return True

            return False

        except Exception as e:
            logger.warning(f"Failed to check profit streak for user {user_id}: {e}")
            return False

    async def _check_low_drawdown(self, user_id: str, days: int, max_dd: float) -> bool:
        """Check if user maintained low drawdown over period.

        Args:
            user_id: User ID
            days: Number of days to check
            max_dd: Maximum allowed drawdown (e.g., 0.10 for 10%)

        Returns:
            True if drawdown stayed below threshold
        """
        try:
            equity_engine = EquityEngine(self.db)

            end_date = datetime.now(UTC)
            start_date = end_date - timedelta(days=days)

            equity_series = await equity_engine.compute_equity_series(
                user_id=user_id,
                start_date=start_date,
                end_date=end_date,
            )

            if not equity_series or len(equity_series) < days:
                return False

            # Calculate max drawdown over period
            peak = 0.0
            max_drawdown = 0.0

            for point in equity_series:
                equity = point.final_equity
                if equity > peak:
                    peak = equity

                if peak > 0:
                    drawdown = (peak - equity) / peak
                    max_drawdown = max(max_drawdown, drawdown)

            return max_drawdown <= max_dd

        except Exception as e:
            logger.warning(
                f"Failed to check drawdown for user {user_id}: {e}", exc_info=True
            )
            return False

    async def opt_in_leaderboard(
        self, user_id: str, display_name: Optional[str] = None
    ) -> LeaderboardOptIn:
        """Opt user into leaderboard with optional display name.

        Args:
            user_id: User ID
            display_name: Optional public display name (default: "Trader XXXX")

        Returns:
            LeaderboardOptIn record
        """
        # Check if already exists
        stmt = select(LeaderboardOptIn).where(LeaderboardOptIn.user_id == user_id)
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Update opt-in status
            existing.opted_in = True
            existing.opted_in_at = datetime.now(UTC)
            existing.opted_out_at = None
            if display_name:
                existing.display_name = display_name

            await self.db.commit()
            await self.db.refresh(existing)

            metrics.leaderboard_optin_total.inc()
            logger.info(f"User {user_id} re-opted into leaderboard")

            return existing

        # Create new opt-in
        optin = LeaderboardOptIn(
            id=str(uuid4()),
            user_id=user_id,
            opted_in=True,
            display_name=display_name,
            opted_in_at=datetime.now(UTC),
        )

        self.db.add(optin)
        await self.db.commit()
        await self.db.refresh(optin)

        metrics.leaderboard_optin_total.inc()
        logger.info(f"User {user_id} opted into leaderboard")

        return optin

    async def opt_out_leaderboard(self, user_id: str) -> LeaderboardOptIn:
        """Opt user out of leaderboard.

        Args:
            user_id: User ID

        Returns:
            Updated LeaderboardOptIn record
        """
        stmt = select(LeaderboardOptIn).where(LeaderboardOptIn.user_id == user_id)
        result = await self.db.execute(stmt)
        optin = result.scalar_one_or_none()

        if not optin:
            # Create opt-out record
            optin = LeaderboardOptIn(
                id=str(uuid4()),
                user_id=user_id,
                opted_in=False,
                opted_out_at=datetime.now(UTC),
            )
            self.db.add(optin)
        else:
            optin.opted_in = False
            optin.opted_out_at = datetime.now(UTC)

        await self.db.commit()
        await self.db.refresh(optin)

        logger.info(f"User {user_id} opted out of leaderboard")

        return optin

    async def get_leaderboard(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """Get leaderboard rankings (opt-in users only).

        Ranking Logic:
        1. Calculate risk-adjusted return % (Sharpe ratio)
        2. Tiebreaker: Total XP
        3. Only include users who opted in

        Args:
            limit: Max number of entries
            offset: Pagination offset

        Returns:
            List of leaderboard entries with rank, display_name, xp, sharpe, return_pct
        """
        # Get opted-in users
        stmt = select(LeaderboardOptIn.user_id).where(LeaderboardOptIn.opted_in == True)
        result = await self.db.execute(stmt)
        opted_in_user_ids = [row[0] for row in result.fetchall()]

        if not opted_in_user_ids:
            return []

        # Calculate metrics for each user
        user_metrics = []

        for user_id in opted_in_user_ids:
            try:
                # Get XP
                xp = await self.calculate_user_xp(user_id)

                # Get risk-adjusted return (Sharpe)
                sharpe = await self._calculate_sharpe(user_id)

                # Get total return %
                return_pct = await self._calculate_return_pct(user_id)

                # Get display name
                stmt = select(LeaderboardOptIn).where(
                    LeaderboardOptIn.user_id == user_id
                )
                result = await self.db.execute(stmt)
                optin = result.scalar_one()
                display_name = optin.display_name or f"Trader {user_id[:8]}"

                user_metrics.append(
                    {
                        "user_id": user_id,
                        "display_name": display_name,
                        "xp": xp,
                        "sharpe": sharpe,
                        "return_pct": return_pct,
                    }
                )

            except Exception as e:
                logger.warning(f"Failed to calculate metrics for user {user_id}: {e}")
                continue

        # Sort by Sharpe (desc), then XP (desc)
        sorted_metrics = sorted(
            user_metrics,
            key=lambda x: (x["sharpe"], x["xp"]),
            reverse=True,
        )

        # Add rank and paginate
        leaderboard = []
        for rank, metrics in enumerate(
            sorted_metrics[offset : offset + limit], start=offset + 1
        ):
            leaderboard.append(
                {
                    "rank": rank,
                    "display_name": metrics["display_name"],
                    "xp": metrics["xp"],
                    "sharpe": metrics["sharpe"],
                    "return_pct": metrics["return_pct"],
                }
            )

        return leaderboard

    async def _calculate_sharpe(self, user_id: str) -> float:
        """Calculate Sharpe ratio for user (last 90 days).

        Args:
            user_id: User ID

        Returns:
            Sharpe ratio (annualized)
        """
        try:
            equity_engine = EquityEngine(self.db)

            end_date = datetime.now(UTC)
            start_date = end_date - timedelta(days=90)

            equity_series = await equity_engine.compute_equity_series(
                user_id=user_id,
                start_date=start_date,
                end_date=end_date,
            )

            if not equity_series or len(equity_series) < 2:
                return 0.0

            # Calculate daily returns
            returns = []
            for i in range(1, len(equity_series)):
                prev_equity = equity_series[i - 1].final_equity
                curr_equity = equity_series[i].final_equity
                if prev_equity > 0:
                    daily_return = (curr_equity - prev_equity) / prev_equity
                    returns.append(daily_return)

            if not returns:
                return 0.0

            # Calculate Sharpe
            import statistics

            mean_return = statistics.mean(returns)
            std_return = statistics.stdev(returns) if len(returns) > 1 else 0.0

            if std_return == 0:
                return 0.0

            sharpe = (mean_return / std_return) * (252**0.5)  # Annualized

            return round(sharpe, 2)

        except Exception as e:
            logger.warning(f"Failed to calculate Sharpe for user {user_id}: {e}")
            return 0.0

    async def _calculate_return_pct(self, user_id: str) -> float:
        """Calculate total return % for user (all-time).

        Args:
            user_id: User ID

        Returns:
            Return percentage
        """
        try:
            equity_engine = EquityEngine(self.db)

            # Get all equity data
            equity_series = await equity_engine.compute_equity_series(
                user_id=user_id,
                start_date=None,  # All-time
                end_date=None,
            )

            if not equity_series or len(equity_series) < 2:
                return 0.0

            initial_equity = equity_series[0].final_equity
            final_equity = equity_series[-1].final_equity

            if initial_equity == 0:
                return 0.0

            return_pct = ((final_equity - initial_equity) / initial_equity) * 100

            return round(return_pct, 2)

        except Exception as e:
            logger.warning(f"Failed to calculate return % for user {user_id}: {e}")
            return 0.0


async def seed_badges_and_levels(db: AsyncSession) -> None:
    """Seed initial badges and levels into database.

    Called during app startup or migration.

    Args:
        db: Database session
    """
    # Seed badges
    for badge_key, badge_def in GamificationService.BADGE_DEFINITIONS.items():
        stmt = select(Badge).where(Badge.name == badge_def["name"])
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if not existing:
            badge = Badge(
                id=str(uuid4()),
                name=badge_def["name"],
                description=badge_def["description"],
                icon=badge_def["icon"],
                category=badge_def["category"],
                xp_reward=badge_def["xp_reward"],
            )
            db.add(badge)
            logger.info(f"Seeded badge: {badge.name}")

    # Seed levels
    for level_def in GamificationService.LEVEL_DEFINITIONS:
        stmt = select(Level).where(Level.name == level_def["name"])
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if not existing:
            level = Level(
                id=str(uuid4()),
                name=level_def["name"],
                min_xp=level_def["min_xp"],
                max_xp=level_def["max_xp"],
                icon=level_def["icon"],
                color=level_def["color"],
                perks=level_def["perks"],
            )
            db.add(level)
            logger.info(f"Seeded level: {level.name}")

    await db.commit()
    logger.info("Badge and level seeding complete")
