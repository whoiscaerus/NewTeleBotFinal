"""Client and Device models for PR-023a Device Registry."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Column, DateTime, Index, String
from sqlalchemy.orm import relationship

# Import Device from canonical location to avoid duplicate table registration
from backend.app.clients.devices.models import Device  # noqa: F401
from backend.app.core.db import Base

if TYPE_CHECKING:
    pass


class Client(Base):
    """Client/User model for device registry."""

    __tablename__ = "clients"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email = Column(String(255), nullable=False, unique=True)
    telegram_id = Column(String(50), nullable=True, unique=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    devices = relationship(
        "Device",
        back_populates="client",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_clients_email", "email"),
        Index("ix_clients_telegram_id", "telegram_id"),
    )
