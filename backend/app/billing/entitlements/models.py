"""Entitlement types and user entitlements database models."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String

from backend.app.core.db import Base


class EntitlementType(Base):
    """Type of entitlement (feature/capability).

    Maps to user permissions in the system.
    Examples:
        - premium_signals: Access to premium trading signals
        - copy_trading: Ability to copy other traders
        - advanced_analytics: Access to advanced analytics dashboard
        - vip_support: Priority support access
    """

    __tablename__ = "entitlement_types"

    id = Column(String(36), primary_key=True)
    name = Column(String(50), nullable=False, unique=True)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<EntitlementType {self.name}>"


class UserEntitlement(Base):
    """User's entitlement (feature access).

    Represents a feature/capability granted to a user.
    Can be time-limited (expires_at) or permanent.
    """

    __tablename__ = "user_entitlements"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False, index=True)  # Foreign key to users.id
    entitlement_type_id = Column(
        String(36), ForeignKey("entitlement_types.id"), nullable=False
    )
    granted_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)  # None = permanent
    is_active = Column(Integer, nullable=False, default=1)  # 0=revoked, 1=active
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_user_entitlements_user", "user_id"),
        Index("ix_user_entitlements_active", "user_id", "is_active"),
        Index("ix_user_entitlements_expiry", "expires_at"),
    )

    def __repr__(self) -> str:
        return f"<UserEntitlement user={self.user_id} entitlement={self.entitlement_type_id}>"

    @property
    def is_expired(self):
        """Check if entitlement has expired.

        Returns:
            True if expired, False otherwise
        """
        if self.expires_at is not None and self.expires_at < datetime.utcnow():
            return True
        return False

    @property
    def is_valid(self):
        """Check if entitlement is currently valid.

        Returns:
            True if active and not expired, False otherwise
        """
        return bool(self.is_active == 1 and not self.is_expired)
