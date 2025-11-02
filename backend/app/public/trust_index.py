"""Public Trust Index - Trader verification and accuracy metrics for public display."""

import logging
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Float, Index, Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import Base

logger = logging.getLogger(__name__)


# ============================================================================
# Database Model
# ============================================================================


class PublicTrustIndexRecord(Base):
    """Public trust index record for a user.

    This stores precomputed verification metrics that are safe to display publicly.
    Includes accuracy metrics, return/risk ratios, and verified trade statistics.

    Attributes:
        id: Unique identifier
        user_id: User this index belongs to
        accuracy_metric: Win rate or prediction accuracy (0-1)
        average_rr: Average risk/reward ratio (positive float)
        verified_trades_pct: Percentage of trades verified by system (0-100)
        trust_band: Category: "unverified", "verified", "expert", "elite"
        calculated_at: When this record was calculated
        valid_until: When this record expires (TTL)
    """

    __tablename__ = "public_trust_index"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False, unique=True, index=True)
    accuracy_metric = Column(Float, nullable=False)  # 0.0-1.0 (win rate)
    average_rr = Column(Float, nullable=False)  # Risk/reward ratio
    verified_trades_pct = Column(Integer, nullable=False)  # 0-100%
    trust_band = Column(String(20), nullable=False)  # unverified|verified|expert|elite
    calculated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    valid_until = Column(DateTime, nullable=False)
    notes = Column(String(500), nullable=True)

    __table_args__ = (
        Index("ix_public_trust_user", "user_id"),
        Index("ix_public_trust_band", "trust_band"),
        Index("ix_public_trust_calculated", "calculated_at"),
    )

    def __repr__(self):
        return f"<PublicTrustIndex {self.user_id}: {self.trust_band} ({self.accuracy_metric:.1%})>"


# ============================================================================
# Pydantic Schemas
# ============================================================================


class PublicTrustIndexSchema(BaseModel):
    """Public trust index schema for API responses.

    Safe to display publicly - contains only aggregated metrics,
    no sensitive user information.
    """

    user_id: str = Field(..., description="User identifier")
    accuracy_metric: float = Field(
        ..., ge=0.0, le=1.0, description="Win rate / prediction accuracy (0-1)"
    )
    average_rr: float = Field(..., gt=0.0, description="Average risk/reward ratio")
    verified_trades_pct: int = Field(
        ..., ge=0, le=100, description="Percentage of trades verified (0-100)"
    )
    trust_band: str = Field(
        ...,
        pattern="^(unverified|verified|expert|elite)$",
        description="Trust category",
    )
    calculated_at: str = Field(..., description="Calculation timestamp (ISO format)")
    valid_until: str = Field(..., description="Expiration timestamp (ISO format)")

    class Config:
        from_attributes = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "user_id": self.user_id,
            "accuracy_metric": round(self.accuracy_metric, 4),
            "average_rr": round(self.average_rr, 2),
            "verified_trades_pct": self.verified_trades_pct,
            "trust_band": self.trust_band,
            "calculated_at": self.calculated_at,
            "valid_until": self.valid_until,
        }


# ============================================================================
# Calculation Functions
# ============================================================================


def calculate_trust_band(
    accuracy_metric: float, average_rr: float, verified_trades_pct: int
) -> str:
    """
    Calculate trust band from metrics.

    Trust bands are primarily driven by accuracy (win rate), with R/R and verified trades as supporting metrics:
    - unverified: < 50% accuracy
    - verified: ≥ 50% accuracy (primary tier)
    - expert: ≥ 60% accuracy (primary tier)
    - elite: ≥ 75% accuracy (primary tier)

    Args:
        accuracy_metric: Win rate (0.0-1.0)
        average_rr: Risk/reward ratio (0+)
        verified_trades_pct: Verified trades percentage (0-100)

    Returns:
        Trust band: "unverified", "verified", "expert", or "elite"

    Example:
        >>> band = calculate_trust_band(0.65, 1.8, 65)
        >>> band
        "expert"
    """
    # Primary tier determined by accuracy metric
    if accuracy_metric >= 0.75:
        return "elite"
    elif accuracy_metric >= 0.60:
        return "expert"
    elif accuracy_metric >= 0.50:
        return "verified"
    else:
        return "unverified"


async def calculate_trust_index(
    user_id: str, db: AsyncSession
) -> Optional[PublicTrustIndexSchema]:
    """
    Calculate public trust index for a user.

    This calculates:
    1. Accuracy metric: Win rate from verified trades
    2. Average R/R: Average risk/reward ratio
    3. Verified trades %: Percentage of trades verified
    4. Trust band: Category based on above metrics

    Args:
        user_id: User to calculate index for
        db: Async database session

    Returns:
        PublicTrustIndexSchema or None if user not found

    Raises:
        Exception: On database error

    Example:
        >>> index = await calculate_trust_index("user123", db)
        >>> if index:
        ...     print(f"Accuracy: {index.accuracy_metric:.1%}")
    """
    try:
        # First, check if user exists

        from backend.app.auth.models import User
        from backend.app.trading.store.models import Trade

        user_stmt = select(User).where(User.id == user_id)
        user_result = await db.execute(user_stmt)
        user = user_result.scalars().first()

        if not user:
            raise ValueError(f"User {user_id} not found")

        # Fetch closed trades for user
        stmt = select(Trade).where(
            (Trade.user_id == user_id) & (Trade.status == "CLOSED")
        )
        result = await db.execute(stmt)
        trades = result.scalars().all()

        if not trades or len(trades) == 0:
            # No trades yet - return unverified defaults
            accuracy_metric = 0.0
            average_rr = 1.0  # Neutral default (not 0, which is invalid)
            verified_trades_pct = 0
        else:
            # Calculate accuracy (win rate)
            winning_trades = sum(1 for t in trades if t.profit and t.profit > 0)
            accuracy_metric = winning_trades / len(trades) if trades else 0.0

            # Calculate average risk/reward ratio
            rr_values = [
                t.risk_reward_ratio
                for t in trades
                if t.risk_reward_ratio is not None and t.risk_reward_ratio > 0
            ]
            average_rr = sum(rr_values) / len(rr_values) if rr_values else 1.0

            # Calculate percentage of verified trades (those with signal_id)
            verified_trades = sum(1 for t in trades if t.signal_id is not None)
            verified_trades_pct = (
                int(verified_trades / len(trades) * 100) if trades else 0
            )

        # Calculate trust band
        trust_band = calculate_trust_band(
            accuracy_metric, average_rr, verified_trades_pct
        )

        logger.info(
            f"Calculated trust index for {user_id} from {len(trades) if trades else 0} trades",
            extra={
                "user_id": user_id,
                "trade_count": len(trades) if trades else 0,
                "accuracy": accuracy_metric,
                "rr": average_rr,
                "verified": verified_trades_pct,
                "band": trust_band,
            },
        )

        # Check for existing record
        stmt = select(PublicTrustIndexRecord).where(
            PublicTrustIndexRecord.user_id == user_id
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            return PublicTrustIndexSchema(
                user_id=user_id,
                accuracy_metric=existing.accuracy_metric,
                average_rr=existing.average_rr,
                verified_trades_pct=existing.verified_trades_pct,
                trust_band=existing.trust_band,
                calculated_at=existing.calculated_at.isoformat(),
                valid_until=existing.valid_until.isoformat(),
            )

        # Create new record
        record = PublicTrustIndexRecord(
            id=str(__import__("uuid").uuid4()),
            user_id=user_id,
            accuracy_metric=accuracy_metric,
            average_rr=average_rr,
            verified_trades_pct=verified_trades_pct,
            trust_band=trust_band,
            calculated_at=datetime.utcnow(),
            valid_until=datetime.utcnow() + __import__("datetime").timedelta(hours=24),
            notes="Initial calculation",
        )

        db.add(record)
        await db.commit()
        await db.refresh(record)

        return PublicTrustIndexSchema(
            user_id=user_id,
            accuracy_metric=record.accuracy_metric,
            average_rr=record.average_rr,
            verified_trades_pct=record.verified_trades_pct,
            trust_band=record.trust_band,
            calculated_at=record.calculated_at.isoformat(),
            valid_until=record.valid_until.isoformat(),
        )

    except Exception as e:
        logger.error(f"Error calculating trust index for {user_id}: {e}", exc_info=True)
        raise
