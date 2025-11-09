"""Strategy versioning models for safe A/B testing and gradual rollout.

Supports:
- Multiple concurrent versions of same strategy (v1.0, v2.0, vNext)
- Shadow mode: Run vNext alongside vCurrent without affecting users
- Canary rollout: Gradually expose new version to % of copy-trading users
- Decision comparison: Compare shadow vs active outcomes

Example versioning workflow:
    1. Deploy vNext in shadow mode (logs only, no execution)
    2. Compare shadow decisions vs vCurrent outcomes for 7 days
    3. If vNext shows improvement, start canary at 5%
    4. Monitor metrics, gradually increase to 10% → 25% → 50% → 100%
    5. Promote vNext to active, retire vCurrent

Example shadow mode:
    >>> # vCurrent (active) executes trades
    >>> active_engine = StrategyEngine(params_v1, calendar)
    >>> signal = await active_engine.generate_signal(df, "GOLD", timestamp)
    >>> await publisher.publish(signal)  # Published to users
    >>>
    >>> # vNext (shadow) only logs decisions
    >>> shadow_engine = StrategyEngine(params_v2, calendar)
    >>> shadow_signal = await shadow_engine.generate_signal(df, "GOLD", timestamp)
    >>> await log_shadow_decision(shadow_signal)  # Logged, NOT published
    >>>
    >>> # Compare outcomes after 7 days
    >>> comparison = await compare_shadow_vs_active("GOLD", days=7)
    >>> print(f"vNext win rate: {comparison['shadow_win_rate']:.2%}")
    >>> print(f"vCurrent win rate: {comparison['active_win_rate']:.2%}")
"""

import enum
from datetime import datetime

from sqlalchemy import Column, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import Float, Index, String
from sqlalchemy.dialects.postgresql import JSONB

from backend.app.core.db import Base


class VersionStatus(str, enum.Enum):
    """Status of a strategy version in the deployment lifecycle."""

    ACTIVE = "active"  # Currently serving production traffic
    SHADOW = "shadow"  # Running in log-only mode (no execution)
    CANARY = "canary"  # Serving traffic to % of users (gradual rollout)
    RETIRED = "retired"  # No longer in use


class StrategyVersion(Base):
    """Tracks versions of a trading strategy for A/B testing and safe rollout.

    Each strategy (fib_rsi, ppo_gold, etc.) can have multiple concurrent versions:
    - Exactly ONE active version (serves production traffic)
    - Zero or more shadow versions (log-only, for comparison)
    - Zero or one canary version (serving % of users)
    - Any number of retired versions (historical record)

    The version string follows semantic versioning (v1.0.0, v2.1.3, etc.) but
    "vNext" is used for experimental versions before formal versioning.

    Configuration JSONB contains strategy-specific parameters:
    - For fib_rsi: RSI periods, fib levels, profit targets, risk params
    - For ppo_gold: PPO periods, signal thresholds, volatility filters

    Example:
        >>> # Register new shadow version
        >>> version = StrategyVersion(
        ...     strategy_name="fib_rsi",
        ...     version="v2.0.0",
        ...     status=VersionStatus.SHADOW,
        ...     config={
        ...         "rsi_period": 14,
        ...         "rsi_overbought": 70,
        ...         "rsi_oversold": 30,
        ...         "fib_lookback_bars": 55,
        ...         "profit_target_pct": 1.5,
        ...         "stop_loss_pct": 0.75
        ...     }
        ... )
        >>> session.add(version)
        >>> await session.commit()
        >>>
        >>> # After 7 days of shadow comparison, promote to canary
        >>> version.status = VersionStatus.CANARY
        >>> await session.commit()
        >>>
        >>> # Create canary config (5% rollout)
        >>> canary = CanaryConfig(
        ...     strategy_name="fib_rsi",
        ...     version="v2.0.0",
        ...     rollout_percent=5.0
        ... )
        >>> session.add(canary)
        >>> await session.commit()
    """

    __tablename__ = "strategy_versions"

    id = Column(String(36), primary_key=True)
    strategy_name = Column(
        String(100), nullable=False, index=True
    )  # fib_rsi, ppo_gold, etc.
    version = Column(String(50), nullable=False, index=True)  # v1.0.0, v2.0.0, vNext
    status: VersionStatus = Column(  # type: ignore[assignment]
        SQLEnum(VersionStatus, name="version_status_enum"),
        nullable=False,
        index=True,
        default=VersionStatus.SHADOW,
    )

    # Strategy-specific configuration (JSONB for flexibility)
    config = Column(JSONB, nullable=False)

    # Lifecycle timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    activated_at = Column(DateTime, nullable=True)  # When promoted to active status
    retired_at = Column(DateTime, nullable=True)  # When moved to retired status

    # Composite indexes for common queries
    __table_args__ = (
        # Get active version for a strategy
        Index("ix_strategy_versions_name_status", "strategy_name", "status"),
        # List all versions for a strategy (deployment history)
        Index("ix_strategy_versions_name_created", "strategy_name", "created_at"),
        # Ensure unique active version per strategy (enforced in code + DB)
        Index(
            "ix_strategy_versions_unique_active",
            "strategy_name",
            "status",
            unique=True,
            postgresql_where=(
                Column("status") == VersionStatus.ACTIVE
            ),  # Partial unique index
        ),
    )

    def __repr__(self) -> str:
        """String representation of strategy version."""
        return f"<StrategyVersion {self.strategy_name} {self.version} ({self.status.value})>"


class CanaryConfig(Base):
    """Configuration for gradual rollout of a new strategy version.

    Controls what % of copy-trading users receive signals from the canary version.
    Rollout percentage can be adjusted in real-time by strategy owner.

    Typical rollout progression:
    - Day 1-3: 5% (early adopters, closely monitored)
    - Day 4-7: 10% (expand if metrics healthy)
    - Day 8-14: 25% (broader exposure)
    - Day 15-21: 50% (majority testing)
    - Day 22+: 100% (full rollout, retire old version)

    User assignment to canary is deterministic based on user_id hash,
    ensuring consistent experience (user doesn't flip between versions).

    Example:
        >>> # Start canary at 5%
        >>> canary = CanaryConfig(
        ...     strategy_name="ppo_gold",
        ...     version="v1.5.0",
        ...     rollout_percent=5.0
        ... )
        >>> session.add(canary)
        >>> await session.commit()
        >>>
        >>> # After 3 days, increase to 10%
        >>> canary.rollout_percent = 10.0
        >>> canary.updated_at = datetime.utcnow()
        >>> await session.commit()
        >>>
        >>> # Check if user in canary
        >>> user_hash = hash(user.id) % 100
        >>> in_canary = user_hash < canary.rollout_percent
    """

    __tablename__ = "canary_configs"

    id = Column(String(36), primary_key=True)
    strategy_name = Column(String(100), nullable=False, index=True)  # fib_rsi, ppo_gold
    version = Column(String(50), nullable=False, index=True)  # v2.0.0, v1.5.0
    rollout_percent = Column(Float, nullable=False)  # 0.0 to 100.0 (5.0 = 5% of users)

    # Lifecycle timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Track rollout progression for analytics
    started_at = Column(
        DateTime, nullable=False, default=datetime.utcnow
    )  # When canary first started

    # Composite indexes
    __table_args__ = (
        # Get active canary config for a strategy
        Index("ix_canary_configs_name_version", "strategy_name", "version"),
        # Ensure only one active canary per strategy
        Index(
            "ix_canary_configs_unique_strategy", "strategy_name", unique=True
        ),  # One canary at a time
    )

    def __repr__(self) -> str:
        """String representation of canary config."""
        return f"<CanaryConfig {self.strategy_name} {self.version} @ {self.rollout_percent:.1f}%>"


class ShadowDecisionLog(Base):
    """Logs decisions from shadow versions for comparison with active version.

    Shadow mode runs vNext strategy logic but does NOT:
    - Publish signals to users
    - Execute trades
    - Send notifications
    - Affect production state

    Purpose: Validate new strategy before exposing to users.

    Logs include ALL input features so we can:
    - Replay decisions to debug divergence
    - Compare feature importance between versions
    - Identify regime changes where versions differ

    Example comparison query:
        >>> # Get shadow vs active decisions for GOLD over 7 days
        >>> shadow_logs = (
        ...     session.query(ShadowDecisionLog)
        ...     .filter(
        ...         ShadowDecisionLog.version == "v2.0.0",
        ...         ShadowDecisionLog.symbol == "GOLD",
        ...         ShadowDecisionLog.timestamp >= start_date
        ...     )
        ...     .all()
        ... )
        >>>
        >>> active_logs = (
        ...     session.query(DecisionLog)
        ...     .filter(
        ...         DecisionLog.strategy == "fib_rsi",
        ...         DecisionLog.symbol == "GOLD",
        ...         DecisionLog.timestamp >= start_date
        ...     )
        ...     .all()
        ... )
        >>>
        >>> # Compare outcomes
        >>> shadow_buys = sum(1 for log in shadow_logs if log.decision == "buy")
        >>> active_buys = sum(1 for log in active_logs if log.outcome == "ENTERED")
        >>> print(f"Shadow: {shadow_buys} signals, Active: {active_buys} signals")
    """

    __tablename__ = "shadow_decision_logs"

    id = Column(String(36), primary_key=True)
    version = Column(String(50), nullable=False, index=True)  # vNext, v2.0.0
    strategy_name = Column(String(100), nullable=False, index=True)  # fib_rsi, ppo_gold
    symbol = Column(String(20), nullable=False, index=True)  # GOLD, XAUUSD
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    # Decision outcome (buy, sell, hold)
    decision = Column(String(20), nullable=False, index=True)  # buy, sell, hold

    # ALL input features used for decision (JSONB for flexibility)
    features = Column(JSONB, nullable=False)

    # Confidence score (0.0 to 1.0) if strategy provides it
    confidence = Column(Float, nullable=True)

    # Additional metadata (e.g., comparison with active version)
    metadata = Column(JSONB, nullable=True)

    # Composite indexes for analytics queries
    __table_args__ = (
        # Compare shadow vs active over time window
        Index(
            "ix_shadow_logs_version_symbol_timestamp",
            "version",
            "symbol",
            "timestamp",
        ),
        # Aggregate decisions by strategy version
        Index(
            "ix_shadow_logs_strategy_version_timestamp",
            "strategy_name",
            "version",
            "timestamp",
        ),
        # Filter by decision type
        Index("ix_shadow_logs_decision_timestamp", "decision", "timestamp"),
    )

    def __repr__(self) -> str:
        """String representation of shadow decision log."""
        return f"<ShadowDecisionLog {self.strategy_name} {self.version} {self.symbol} {self.decision} @ {self.timestamp}>"
