"""Client and Device models for PR-023a Device Registry."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import relationship

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
        "Device", back_populates="client", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_clients_email", "email"),
        Index("ix_clients_telegram_id", "telegram_id"),
    )


class Device(Base):
    """Device (MT5 EA instance) model."""

    __tablename__ = "devices"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False)
    name = Column(String(100), nullable=False)
    secret_hash = Column(String(255), nullable=False)  # argon2id hash of secret
    revoked = Column(Boolean, default=False)
    last_seen = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    client = relationship("Client", back_populates="devices")
    executions = relationship(
        "Execution",
        back_populates="device",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_devices_client_id", "client_id"),
        Index("ix_devices_client_name", "client_id", "name"),
    )
