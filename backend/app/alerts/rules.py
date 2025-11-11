"""
PR-065: Price Alerts UX Enhancements - Smart Rules & Cooldowns

Smart rule conditions beyond simple price triggers:
- cross_above/cross_below: Detects when price crosses a level (requires previous state)
- percent_change: Triggers when % change over window exceeds threshold
- rsi_threshold: Triggers when RSI indicator crosses threshold
- daily_high_touch/daily_low_touch: Triggers when price touches daily extremes
- Cooldown mechanism to prevent alert spam
- Per-rule mute/unmute capability
- Multi-channel delivery (Telegram, push, email)
"""

import logging
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, validator
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import relationship

from backend.app.core.db import Base
from backend.app.core.errors import ValidationError

logger = logging.getLogger(__name__)


class RuleType(str, Enum):
    """Alert rule types."""

    CROSS_ABOVE = "cross_above"
    CROSS_BELOW = "cross_below"
    PERCENT_CHANGE = "percent_change"
    RSI_THRESHOLD = "rsi_threshold"
    DAILY_HIGH_TOUCH = "daily_high_touch"
    DAILY_LOW_TOUCH = "daily_low_touch"
    # Legacy from PR-044
    SIMPLE_ABOVE = "above"
    SIMPLE_BELOW = "below"


class NotificationChannel(str, Enum):
    """Notification delivery channels."""

    TELEGRAM = "telegram"
    PUSH = "push"
    EMAIL = "email"


# ============================================================================
# DATABASE MODELS
# ============================================================================


class SmartAlertRule(Base):
    """Smart alert rule with advanced conditions and cooldown.

    Extends basic price alerts with:
    - Complex rule conditions (cross, %, RSI, extremes)
    - Configurable cooldown period
    - Mute/unmute capability
    - Multi-channel preferences
    - Previous state tracking for cross detection
    """

    __tablename__ = "smart_alert_rules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    symbol = Column(String(50), nullable=False, index=True)
    rule_type = Column(String(50), nullable=False)  # RuleType enum value
    threshold_value = Column(Float, nullable=False)

    # Optional parameters based on rule type
    window_minutes = Column(
        Integer
    )  # For percent_change: lookback window (e.g., 60 for 1hr)
    rsi_period = Column(Integer)  # For RSI: period (default 14)

    # Cooldown and mute
    cooldown_minutes = Column(
        Integer, nullable=False, default=60
    )  # Min time between triggers
    is_muted = Column(Boolean, nullable=False, default=False)

    # Multi-channel preferences
    channels = Column(JSON, nullable=False)  # List of NotificationChannel values

    # State tracking
    last_triggered_at = Column(DateTime)
    previous_price = Column(Float)  # For cross detection
    last_evaluation_at = Column(DateTime)

    # Metadata
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    notifications = relationship(
        "RuleNotification", back_populates="rule", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_smart_rules_user_symbol", "user_id", "symbol"),
        Index("ix_smart_rules_active", "is_active", "is_muted"),
        Index("ix_smart_rules_evaluation", "is_active", "last_evaluation_at"),
    )

    def __repr__(self):
        return f"<SmartAlertRule {self.id}: {self.symbol} {self.rule_type} threshold={self.threshold_value}>"


class RuleNotification(Base):
    """Notification sent for a smart rule trigger."""

    __tablename__ = "rule_notifications"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    rule_id = Column(
        String(36), ForeignKey("smart_alert_rules.id"), nullable=False, index=True
    )
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    channel = Column(String(50), nullable=False)  # NotificationChannel value
    message = Column(String(1000), nullable=False)
    sent_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    delivered = Column(Boolean, default=False)
    error_message = Column(String(500))

    # Relationships
    rule = relationship("SmartAlertRule", back_populates="notifications")

    __table_args__ = (
        Index("ix_rule_notifications_rule", "rule_id", "sent_at"),
        Index("ix_rule_notifications_user", "user_id", "sent_at"),
    )

    def __repr__(self):
        return (
            f"<RuleNotification {self.id}: rule={self.rule_id} channel={self.channel}>"
        )


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================


class SmartRuleCreate(BaseModel):
    """Request to create a smart alert rule."""

    symbol: str = Field(..., min_length=2, max_length=50)
    rule_type: RuleType
    threshold_value: float = Field(..., gt=0)
    window_minutes: Optional[int] = Field(None, gt=0, le=1440)  # Max 24 hours
    rsi_period: Optional[int] = Field(None, gt=1, le=200)
    cooldown_minutes: int = Field(60, ge=5, le=10080)  # 5 min to 1 week
    channels: list[NotificationChannel] = Field(
        default_factory=lambda: [NotificationChannel.TELEGRAM]
    )

    @validator("symbol")
    def validate_symbol(cls, v):
        """Validate symbol is supported."""
        # Use same validation as PR-044
        from backend.app.alerts.service import VALID_SYMBOLS

        if v.upper() not in VALID_SYMBOLS:
            raise ValueError(f"Symbol {v} not supported")
        return v.upper()

    @validator("window_minutes")
    def validate_window_for_percent_change(cls, v, values):
        """Validate window_minutes required for percent_change rule."""
        if values.get("rule_type") == RuleType.PERCENT_CHANGE and v is None:
            raise ValueError("window_minutes required for percent_change rule")
        return v

    @validator("rsi_period")
    def validate_rsi_period(cls, v, values):
        """Set default RSI period if not provided."""
        if values.get("rule_type") == RuleType.RSI_THRESHOLD:
            return v or 14  # Default RSI period
        return v


class SmartRuleUpdate(BaseModel):
    """Request to update a smart alert rule."""

    threshold_value: Optional[float] = Field(None, gt=0)
    cooldown_minutes: Optional[int] = Field(None, ge=5, le=10080)
    is_muted: Optional[bool] = None
    channels: Optional[list[NotificationChannel]] = None


class SmartRuleOut(BaseModel):
    """Response with smart rule details."""

    rule_id: str
    symbol: str
    rule_type: str
    threshold_value: float
    window_minutes: Optional[int]
    rsi_period: Optional[int]
    cooldown_minutes: int
    is_muted: bool
    channels: list[str]
    is_active: bool
    last_triggered_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# BUSINESS LOGIC: RULE EVALUATION
# ============================================================================


class SmartRuleEvaluator:
    """Evaluates smart alert rules against market data."""

    @staticmethod
    async def evaluate_cross_above(
        rule: SmartAlertRule, current_price: float
    ) -> tuple[bool, Optional[str]]:
        """Evaluate cross-above condition.

        Triggers when price crosses above threshold from below.
        Requires previous_price to be set.

        Args:
            rule: Smart rule to evaluate
            current_price: Current market price

        Returns:
            (triggered, reason): True if condition met, with explanation
        """
        if rule.previous_price is None:
            # First evaluation - store price for next time
            return False, "Initializing - no previous price"

        if rule.previous_price <= rule.threshold_value < current_price:
            return (
                True,
                f"Price crossed above {rule.threshold_value} (was {rule.previous_price:.2f}, now {current_price:.2f})",
            )

        return False, None

    @staticmethod
    async def evaluate_cross_below(
        rule: SmartAlertRule, current_price: float
    ) -> tuple[bool, Optional[str]]:
        """Evaluate cross-below condition.

        Triggers when price crosses below threshold from above.

        Args:
            rule: Smart rule to evaluate
            current_price: Current market price

        Returns:
            (triggered, reason): True if condition met, with explanation
        """
        if rule.previous_price is None:
            return False, "Initializing - no previous price"

        if rule.previous_price >= rule.threshold_value > current_price:
            return (
                True,
                f"Price crossed below {rule.threshold_value} (was {rule.previous_price:.2f}, now {current_price:.2f})",
            )

        return False, None

    @staticmethod
    async def evaluate_percent_change(
        rule: SmartAlertRule,
        current_price: float,
        historical_prices: list[tuple[datetime, float]],
    ) -> tuple[bool, Optional[str]]:
        """Evaluate percent change condition.

        Triggers when % change over window exceeds threshold.

        Args:
            rule: Smart rule to evaluate
            current_price: Current market price
            historical_prices: List of (timestamp, price) tuples

        Returns:
            (triggered, reason): True if condition met, with explanation
        """
        if not historical_prices or rule.window_minutes is None:
            return False, "Insufficient historical data"

        # Find price at start of window
        cutoff_time = datetime.now(UTC) - timedelta(minutes=rule.window_minutes)
        window_start_price = None

        for timestamp, price in historical_prices:
            if timestamp >= cutoff_time:
                window_start_price = price
                break

        if window_start_price is None:
            return False, f"No price data from {rule.window_minutes} minutes ago"

        # Calculate percent change
        percent_change = (
            (current_price - window_start_price) / window_start_price
        ) * 100

        if abs(percent_change) >= rule.threshold_value:
            direction = "increase" if percent_change > 0 else "decrease"
            return (
                True,
                f"{abs(percent_change):.2f}% {direction} over {rule.window_minutes} minutes (threshold: {rule.threshold_value}%)",
            )

        return False, None

    @staticmethod
    async def evaluate_rsi_threshold(
        rule: SmartAlertRule, current_rsi: float
    ) -> tuple[bool, Optional[str]]:
        """Evaluate RSI threshold condition.

        Triggers when RSI crosses threshold (overbought/oversold).

        Args:
            rule: Smart rule to evaluate
            current_rsi: Current RSI value (0-100)

        Returns:
            (triggered, reason): True if condition met, with explanation
        """
        if current_rsi is None:
            return False, "RSI data not available"

        # Overbought condition (RSI > threshold, e.g., 70)
        if rule.threshold_value >= 50:
            if current_rsi >= rule.threshold_value:
                return (
                    True,
                    f"RSI overbought: {current_rsi:.1f} >= {rule.threshold_value}",
                )
        # Oversold condition (RSI < threshold, e.g., 30)
        else:
            if current_rsi <= rule.threshold_value:
                return (
                    True,
                    f"RSI oversold: {current_rsi:.1f} <= {rule.threshold_value}",
                )

        return False, None

    @staticmethod
    async def evaluate_daily_high_touch(
        rule: SmartAlertRule, current_price: float, daily_high: float
    ) -> tuple[bool, Optional[str]]:
        """Evaluate daily high touch condition.

        Triggers when price touches or exceeds daily high.

        Args:
            rule: Smart rule to evaluate
            current_price: Current market price
            daily_high: Daily high price

        Returns:
            (triggered, reason): True if condition met, with explanation
        """
        if daily_high is None:
            return False, "Daily high data not available"

        # Threshold is % of daily high (e.g., 99.5% means within 0.5%)
        touch_level = daily_high * (rule.threshold_value / 100)

        if current_price >= touch_level:
            return (
                True,
                f"Price touched daily high: {current_price:.2f} (high: {daily_high:.2f}, threshold: {rule.threshold_value}%)",
            )

        return False, None

    @staticmethod
    async def evaluate_daily_low_touch(
        rule: SmartAlertRule, current_price: float, daily_low: float
    ) -> tuple[bool, Optional[str]]:
        """Evaluate daily low touch condition.

        Triggers when price touches or falls below daily low.

        Args:
            rule: Smart rule to evaluate
            current_price: Current market price
            daily_low: Daily low price

        Returns:
            (triggered, reason): True if condition met, with explanation
        """
        if daily_low is None:
            return False, "Daily low data not available"

        # Threshold is % of daily low (e.g., 100.5% means within 0.5%)
        touch_level = daily_low * (rule.threshold_value / 100)

        if current_price <= touch_level:
            return (
                True,
                f"Price touched daily low: {current_price:.2f} (low: {daily_low:.2f}, threshold: {rule.threshold_value}%)",
            )

        return False, None


# ============================================================================
# SERVICE: SMART RULE MANAGEMENT
# ============================================================================


class SmartRuleService:
    """Service for managing smart alert rules."""

    def __init__(self):
        """Initialize smart rule service."""
        self.evaluator = SmartRuleEvaluator()

    async def create_rule(
        self,
        db: AsyncSession,
        user_id: str,
        symbol: str,
        rule_type: RuleType,
        threshold_value: float,
        window_minutes: Optional[int] = None,
        rsi_period: Optional[int] = None,
        cooldown_minutes: int = 60,
        channels: Optional[list[NotificationChannel]] = None,
    ) -> dict[str, Any]:
        """Create a new smart alert rule.

        Args:
            db: Database session
            user_id: User ID
            symbol: Trading symbol
            rule_type: Type of rule condition
            threshold_value: Threshold value for trigger
            window_minutes: Lookback window for percent_change
            rsi_period: RSI period (default 14)
            cooldown_minutes: Minimum time between triggers
            channels: Notification channels (default: Telegram only)

        Returns:
            dict: Created rule details

        Raises:
            ValidationError: If validation fails
        """
        # Validate rule-specific parameters
        if rule_type == RuleType.PERCENT_CHANGE and window_minutes is None:
            raise ValidationError("window_minutes required for percent_change rule")

        if rule_type == RuleType.RSI_THRESHOLD:
            rsi_period = rsi_period or 14

        # Default channels
        if channels is None:
            channels = [NotificationChannel.TELEGRAM]

        # Create rule
        rule = SmartAlertRule(
            id=str(uuid4()),
            user_id=user_id,
            symbol=symbol,
            rule_type=rule_type.value,
            threshold_value=threshold_value,
            window_minutes=window_minutes,
            rsi_period=rsi_period,
            cooldown_minutes=cooldown_minutes,
            channels=[c.value for c in channels],
            is_muted=False,
            is_active=True,
            created_at=datetime.utcnow(),
        )

        db.add(rule)
        await db.commit()
        await db.refresh(rule)

        logger.info(
            f"Created smart rule {rule.id} for user {user_id}",
            extra={
                "rule_id": rule.id,
                "user_id": user_id,
                "symbol": symbol,
                "rule_type": rule_type.value,
            },
        )

        return {
            "rule_id": rule.id,
            "symbol": rule.symbol,
            "rule_type": rule.rule_type,
            "threshold_value": rule.threshold_value,
            "window_minutes": rule.window_minutes,
            "rsi_period": rule.rsi_period,
            "cooldown_minutes": rule.cooldown_minutes,
            "is_muted": rule.is_muted,
            "channels": rule.channels,
            "is_active": rule.is_active,
            "created_at": rule.created_at,
        }

    async def update_rule(
        self, db: AsyncSession, rule_id: str, user_id: str, updates: SmartRuleUpdate
    ) -> dict[str, Any]:
        """Update an existing smart rule.

        Args:
            db: Database session
            rule_id: Rule ID to update
            user_id: User ID (for authorization)
            updates: Update request

        Returns:
            dict: Updated rule details

        Raises:
            ValidationError: If rule not found or not owned by user
        """
        # Fetch rule
        result = await db.execute(
            select(SmartAlertRule).where(
                SmartAlertRule.id == rule_id, SmartAlertRule.user_id == user_id
            )
        )
        rule = result.scalar_one_or_none()

        if not rule:
            raise ValidationError(f"Rule {rule_id} not found")

        # Apply updates
        if updates.threshold_value is not None:
            rule.threshold_value = updates.threshold_value
        if updates.cooldown_minutes is not None:
            rule.cooldown_minutes = updates.cooldown_minutes
        if updates.is_muted is not None:
            rule.is_muted = updates.is_muted
        if updates.channels is not None:
            rule.channels = [c.value for c in updates.channels]

        rule.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(rule)

        logger.info(
            f"Updated smart rule {rule_id}",
            extra={"rule_id": rule_id, "user_id": user_id, "is_muted": rule.is_muted},
        )

        return {
            "rule_id": rule.id,
            "symbol": rule.symbol,
            "rule_type": rule.rule_type,
            "threshold_value": rule.threshold_value,
            "cooldown_minutes": rule.cooldown_minutes,
            "is_muted": rule.is_muted,
            "channels": rule.channels,
            "is_active": rule.is_active,
        }

    async def mute_rule(
        self, db: AsyncSession, rule_id: str, user_id: str
    ) -> dict[str, Any]:
        """Mute a smart rule (stop notifications).

        Args:
            db: Database session
            rule_id: Rule ID to mute
            user_id: User ID (for authorization)

        Returns:
            dict: Updated rule status
        """
        result = await db.execute(
            select(SmartAlertRule).where(
                SmartAlertRule.id == rule_id, SmartAlertRule.user_id == user_id
            )
        )
        rule = result.scalar_one_or_none()

        if not rule:
            raise ValidationError(f"Rule {rule_id} not found")

        rule.is_muted = True
        rule.updated_at = datetime.utcnow()

        await db.commit()

        logger.info(
            f"Muted rule {rule_id}", extra={"rule_id": rule_id, "user_id": user_id}
        )

        return {"rule_id": rule.id, "is_muted": True}

    async def unmute_rule(
        self, db: AsyncSession, rule_id: str, user_id: str
    ) -> dict[str, Any]:
        """Unmute a smart rule (resume notifications).

        Args:
            db: Database session
            rule_id: Rule ID to unmute
            user_id: User ID (for authorization)

        Returns:
            dict: Updated rule status
        """
        result = await db.execute(
            select(SmartAlertRule).where(
                SmartAlertRule.id == rule_id, SmartAlertRule.user_id == user_id
            )
        )
        rule = result.scalar_one_or_none()

        if not rule:
            raise ValidationError(f"Rule {rule_id} not found")

        rule.is_muted = False
        rule.updated_at = datetime.utcnow()

        await db.commit()

        logger.info(
            f"Unmuted rule {rule_id}", extra={"rule_id": rule_id, "user_id": user_id}
        )

        return {"rule_id": rule.id, "is_muted": False}

    async def check_cooldown(
        self, rule: SmartAlertRule
    ) -> tuple[bool, Optional[datetime]]:
        """Check if rule is in cooldown period.

        Args:
            rule: Smart alert rule

        Returns:
            (can_trigger, available_at): True if can trigger, with next available time
        """
        if rule.last_triggered_at is None:
            return True, None

        cooldown_expires = rule.last_triggered_at + timedelta(
            minutes=rule.cooldown_minutes
        )
        now = datetime.utcnow()

        if now >= cooldown_expires:
            return True, None

        return False, cooldown_expires

    async def evaluate_rule(
        self,
        db: AsyncSession,
        rule: SmartAlertRule,
        market_data: dict[str, Any],
    ) -> tuple[bool, Optional[str]]:
        """Evaluate a smart rule against market data.

        Args:
            db: Database session
            rule: Smart rule to evaluate
            market_data: Dict with current_price, historical_prices, rsi, daily_high, daily_low

        Returns:
            (triggered, reason): True if rule triggered, with explanation
        """
        # Check if rule is active and not muted
        if not rule.is_active or rule.is_muted:
            return False, "Rule inactive or muted"

        # Check cooldown
        can_trigger, available_at = await self.check_cooldown(rule)
        if not can_trigger:
            return False, f"In cooldown until {available_at}"

        # Evaluate based on rule type
        rule_type = RuleType(rule.rule_type)
        current_price = market_data.get("current_price")

        if current_price is None:
            return False, "No current price data"

        triggered = False
        reason = None

        if rule_type == RuleType.CROSS_ABOVE:
            triggered, reason = await self.evaluator.evaluate_cross_above(
                rule, current_price
            )
        elif rule_type == RuleType.CROSS_BELOW:
            triggered, reason = await self.evaluator.evaluate_cross_below(
                rule, current_price
            )
        elif rule_type == RuleType.PERCENT_CHANGE:
            triggered, reason = await self.evaluator.evaluate_percent_change(
                rule, current_price, market_data.get("historical_prices", [])
            )
        elif rule_type == RuleType.RSI_THRESHOLD:
            triggered, reason = await self.evaluator.evaluate_rsi_threshold(
                rule, market_data.get("rsi")
            )
        elif rule_type == RuleType.DAILY_HIGH_TOUCH:
            triggered, reason = await self.evaluator.evaluate_daily_high_touch(
                rule, current_price, market_data.get("daily_high")
            )
        elif rule_type == RuleType.DAILY_LOW_TOUCH:
            triggered, reason = await self.evaluator.evaluate_daily_low_touch(
                rule, current_price, market_data.get("daily_low")
            )

        # Update state
        rule.previous_price = current_price
        rule.last_evaluation_at = datetime.utcnow()

        if triggered:
            rule.last_triggered_at = datetime.utcnow()

        await db.commit()

        return triggered, reason
