"""Payment models."""

from datetime import datetime

from sqlalchemy import Column, DateTime, String

from backend.app.core.db import Base


class PaymentRecord(Base):
    """Payment record model."""

    __tablename__ = "payment_records"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False)
    stripe_payment_intent = Column(String)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)


class EntitlementRecord(Base):
    """Entitlement record model."""

    __tablename__ = "entitlement_records"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False)
    feature = Column(String, nullable=False)
    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)

    @property
    def is_active(self) -> bool:
        """Check if entitlement is active."""
        return bool(self.status == "active")
