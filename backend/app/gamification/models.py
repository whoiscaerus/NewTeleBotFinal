"""Gamification models for PR-088.

Database models for badges, earned badges, trader levels, and leaderboard opt-in.

Business Rules:
- Badges awarded based on specific achievements (10 trades, 90-day streak)
- Trader levels determined by XP (trades approved + PnL stability)
- Leaderboard participation is opt-in only (privacy-safe)
- Leaderboard ranks by risk-adjusted return %
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.app.core.db import Base


class Badge(Base):
    """Badge definition model.

    Represents a type of badge that can be earned by users.
    Examples: "10 Approved Trades", "90-Day Profit Streak", "First Trade"

    Business Rules:
    - Each badge has unique identifier and name
    - Badge criteria defined in description
    - Badges are immutable once created
    """

    __tablename__ = "badges"

    id = Column(String(36), primary_key=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=False)
    icon = Column(String(50), nullable=False)  # Emoji or icon identifier
    category = Column(
        String(50), nullable=False, index=True
    )  # "milestone", "streak", "performance"
    xp_reward = Column(Integer, nullable=False, default=100)  # XP granted on earn
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    earned_badges = relationship(
        "EarnedBadge", back_populates="badge", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Badge {self.name}>"


class EarnedBadge(Base):
    """Record of a user earning a badge.

    Tracks when and why a badge was awarded to a specific user.

    Business Rules:
    - User can only earn each badge once (unique constraint)
    - XP awarded at time of earning
    - Immutable after creation (no updates)
    """

    __tablename__ = "earned_badges"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    badge_id = Column(String(36), ForeignKey("badges.id"), nullable=False, index=True)
    earned_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    context = Column(
        Text, nullable=True
    )  # JSON context: {"trades_count": 10, "streak_days": 90}

    # Relationships
    badge = relationship("Badge", back_populates="earned_badges")
    user = relationship("User", back_populates="earned_badges")

    # Constraints
    __table_args__ = (
        UniqueConstraint("user_id", "badge_id", name="uq_user_badge"),
        Index("ix_earned_badges_user_earned_at", "user_id", "earned_at"),
    )

    def __repr__(self):
        return f"<EarnedBadge user={self.user_id} badge={self.badge_id}>"


class Level(Base):
    """Trader level/tier system.

    Defines XP thresholds for different trader levels.
    Example: Bronze (0-1000 XP), Silver (1001-5000 XP), Gold (5001-15000 XP)

    Business Rules:
    - Levels ordered by min_xp ascending
    - No XP gaps (next level starts where previous ends + 1)
    - Level names unique
    """

    __tablename__ = "levels"

    id = Column(String(36), primary_key=True)
    name = Column(String(50), nullable=False, unique=True, index=True)
    min_xp = Column(Integer, nullable=False, unique=True, index=True)
    max_xp = Column(Integer, nullable=True)  # NULL for highest level (no upper bound)
    icon = Column(String(50), nullable=False)  # Badge/trophy icon
    color = Column(String(20), nullable=False)  # UI color: "bronze", "silver", "gold"
    perks = Column(Text, nullable=True)  # JSON: ["feature_1", "discount_5pct"]
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"<Level {self.name} ({self.min_xp}-{self.max_xp} XP)>"


class LeaderboardOptIn(Base):
    """User opt-in for leaderboard participation.

    Privacy-safe leaderboard: users must explicitly opt-in.

    Business Rules:
    - Opt-in is per-user
    - User can opt-out at any time
    - Only opted-in users appear on leaderboard
    - Display name optional (defaults to "Trader {id[:8]}")
    """

    __tablename__ = "leaderboard_optins"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, unique=True)
    opted_in = Column(Boolean, nullable=False, default=True, index=True)
    display_name = Column(
        String(50), nullable=True
    )  # Optional public name (fallback: "Trader XXXX")
    opted_in_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    opted_out_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="leaderboard_optin")

    # Indexes
    __table_args__ = (Index("ix_leaderboard_opted_in", "opted_in"),)

    def __repr__(self):
        status = "opted-in" if self.opted_in else "opted-out"
        return f"<LeaderboardOptIn user={self.user_id} {status}>"
