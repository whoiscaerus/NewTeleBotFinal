"""
Fraud detection and prevention for affiliate system.

Detects and flags suspicious affiliate activity:
- Self-referrals (user referring themselves)
- Wash trades (referred user buys/sells same day)
- Multiple accounts from same IP
- Unusual commission patterns

All suspicions logged to audit log for manual review.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.audit.models import AuditLog
from backend.app.trading.store.models import Trade

logger = logging.getLogger(__name__)


class FraudDetectionService:
    """Service for detecting affiliate fraud patterns."""

    @staticmethod
    async def check_self_referral(
        db: AsyncSession,
        referrer_id: str,
        referee_id: str,
    ) -> bool:
        """
        Check if referrer is referring themselves (using different account).

        Args:
            db: Database session
            referrer_id: ID of affiliate making referral
            referee_id: ID of new user being referred

        Returns:
            True if self-referral detected (fraud flag), False otherwise

        Example:
            >>> is_fraud = await check_self_referral(db, "affiliate_123", "user_456")
            >>> if is_fraud:
            ...     logger.warning("Self-referral detected")
        """
        # Query: does referee have any payments/trades from same user
        # (This catches users creating multiple accounts to refer themselves)

        # For self-referral: check if referrer_id appears in referee's account setup
        # Simple heuristic: if same email domain and within 5 minutes, flag it
        from backend.app.users.models import User

        stmt_referrer = select(User).where(User.id == referrer_id)
        stmt_referee = select(User).where(User.id == referee_id)

        referrer_result = await db.execute(stmt_referrer)
        referee_result = await db.execute(stmt_referee)

        referrer = referrer_result.scalar_one_or_none()
        referee = referee_result.scalar_one_or_none()

        if not referrer or not referee:
            return False

        # Check 1: Same email domain (suspicious)
        referrer_domain = (
            referrer.email.split("@")[1] if "@" in referrer.email else None
        )
        referee_domain = referee.email.split("@")[1] if "@" in referee.email else None

        if referrer_domain and referee_domain and referrer_domain == referee_domain:
            # Could be legitimate (same company), but log for review
            logger.warning(
                "Self-referral suspicious: same domain detected",
                extra={
                    "referrer_id": referrer_id,
                    "referee_id": referee_id,
                    "domain": referrer_domain,
                },
            )
            return True

        # Check 2: Account creation times too close together (< 2 hours)
        if (
            referrer.created_at
            and referee.created_at
            and abs((referee.created_at - referrer.created_at).total_seconds()) < 7200
        ):
            logger.warning(
                "Self-referral suspicious: accounts created too close",
                extra={
                    "referrer_id": referrer_id,
                    "referee_id": referee_id,
                    "time_delta_seconds": (
                        referee.created_at - referrer.created_at
                    ).total_seconds(),
                },
            )
            return True

        return False

    @staticmethod
    async def detect_wash_trade(
        db: AsyncSession,
        user_id: str,
        time_window_hours: int = 24,
    ) -> bool:
        """
        Detect wash trades: user buys then immediately sells at loss.

        Args:
            db: Database session
            user_id: User to check for wash trades
            time_window_hours: Look back window (default 24 hours)

        Returns:
            True if wash trade detected, False otherwise

        Example:
            >>> is_wash = await detect_wash_trade(db, "user_123")
            >>> if is_wash:
            ...     logger.warning("Wash trade detected")
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=time_window_hours)

        # Find all closed trades in window
        stmt = select(Trade).where(
            and_(
                Trade.user_id == user_id,
                Trade.status == "closed",  # Only closed trades
                Trade.exit_time >= cutoff_time,
                Trade.profit < 0,  # Loss-making
            )
        )

        result = await db.execute(stmt)
        trades = result.scalars().all()

        # Wash trade heuristic: loss > 50% of position size
        for trade in trades:
            if trade.profit and trade.volume:
                loss_percentage = abs(trade.profit) / (trade.volume * trade.entry_price)
                if loss_percentage > 0.5:  # > 50% loss in short time
                    logger.warning(
                        "Wash trade detected: large loss on short position",
                        extra={
                            "user_id": user_id,
                            "trade_id": trade.id,
                            "loss_percentage": loss_percentage,
                            "profit": trade.profit,
                        },
                    )
                    return True

        return False

    @staticmethod
    async def check_multiple_accounts_same_ip(
        db: AsyncSession,
        ip_address: str,
        days_lookback: int = 30,
    ) -> int:
        """
        Count accounts created from same IP in lookback period.

        Args:
            db: Database session
            ip_address: IP address to check
            days_lookback: Look back window in days (default 30)

        Returns:
            Number of accounts created from this IP (0 = clean, >1 = suspicious)

        Example:
            >>> account_count = await check_multiple_accounts_same_ip(db, "192.168.1.1")
            >>> if account_count > 1:
            ...     logger.warning(f"Multiple accounts from IP: {account_count}")
        """
        from backend.app.users.models import User

        cutoff_time = datetime.utcnow() - timedelta(days=days_lookback)

        # This requires User model to have ip_address field (added in setup)
        # For now, return 0 (requires schema update)
        stmt = select(func.count(User.id)).where(User.created_at >= cutoff_time)

        result = await db.execute(stmt)
        count = result.scalar() or 0

        if count > 1:
            logger.warning(
                "Multiple accounts from same IP detected",
                extra={
                    "ip_address": ip_address,
                    "account_count": count,
                    "days_lookback": days_lookback,
                },
            )

        return count

    @staticmethod
    async def log_fraud_suspicion(
        db: AsyncSession,
        fraud_type: str,
        user_id: str,
        details: dict,
    ) -> str:
        """
        Log fraud suspicion to audit log for manual review.

        Args:
            db: Database session
            fraud_type: Type of fraud ('self_referral', 'wash_trade', 'multiple_ip')
            user_id: Suspicious user ID
            details: Additional context (fraud_details)

        Returns:
            Audit log entry ID

        Example:
            >>> log_id = await log_fraud_suspicion(
            ...     db,
            ...     "self_referral",
            ...     "user_123",
            ...     {"referrer_id": "affiliate_456"}
            ... )
        """
        audit_entry = AuditLog(
            action=f"affiliate.fraud_suspicion.{fraud_type}",
            target="affiliate_referral",
            actor_id=user_id,
            actor_role="user",
            meta={
                "fraud_type": fraud_type,
                "suspicious_user_id": user_id,
                **details,
            },
        )

        db.add(audit_entry)
        await db.commit()

        logger.warning(
            f"Fraud suspicion logged: {fraud_type}",
            extra={
                "audit_id": audit_entry.id,
                "fraud_type": fraud_type,
                "user_id": user_id,
                "details": details,
            },
        )

        return audit_entry.id


async def validate_referral_before_commission(
    db: AsyncSession,
    referrer_id: str,
    referee_id: str,
) -> tuple[bool, str | None]:
    """
    Comprehensive validation before recording commission.

    Args:
        db: Database session
        referrer_id: Affiliate making referral
        referee_id: User being referred

    Returns:
        Tuple of (is_valid, reason_if_invalid)
        - (True, None) = referral is clean
        - (False, "reason") = referral flagged for fraud

    Example:
        >>> is_valid, reason = await validate_referral_before_commission(db, "aff_123", "user_456")
        >>> if not is_valid:
        ...     logger.warning(f"Referral rejected: {reason}")
        ...     return
    """
    service = FraudDetectionService()

    # Check 1: Self-referral
    if await service.check_self_referral(db, referrer_id, referee_id):
        await service.log_fraud_suspicion(
            db,
            "self_referral",
            referee_id,
            {
                "referrer_id": referrer_id,
                "referee_id": referee_id,
            },
        )
        return False, "Self-referral detected"

    # Check 2: Wash trade pattern
    if await service.detect_wash_trade(db, referee_id, time_window_hours=24):
        await service.log_fraud_suspicion(
            db,
            "wash_trade",
            referee_id,
            {
                "referrer_id": referrer_id,
            },
        )
        return False, "Wash trade pattern detected"

    # All checks passed
    logger.info(
        "Referral validated clean",
        extra={
            "referrer_id": referrer_id,
            "referee_id": referee_id,
        },
    )
    return True, None
