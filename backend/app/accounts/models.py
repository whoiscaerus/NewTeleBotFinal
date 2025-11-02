"""
Account Linking Models for PR-043

SQLAlchemy models for linking Telegram users to MT5 trading accounts.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.app.core.db import Base


class AccountLink(Base):
    """
    Links a Telegram user to their MT5 trading account.

    Supports multiple accounts per user with primary account designation.
    """

    __tablename__ = "account_links"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    mt5_account_id = Column(
        String(255), nullable=False
    )  # Account number (e.g., 12345678)
    mt5_login = Column(String(255), nullable=False)  # Login for connection
    broker_name = Column(String(100), default="MetaTrader5", nullable=False)
    is_primary = Column(Boolean, default=False, nullable=False)
    verified_at = Column(DateTime, nullable=True)  # When account was verified
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    user = relationship("User", back_populates="account_links")
    account_info = relationship(
        "AccountInfo", back_populates="account_link", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        UniqueConstraint("user_id", "mt5_account_id", name="unique_user_account"),
        Index("ix_account_links_verified", "verified_at"),
    )

    def __repr__(self):
        return f"<AccountLink {self.id}: user={self.user_id} account={self.mt5_account_id}>"


class AccountInfo(Base):
    """
    Cached account information for performance.

    Updated on each position/balance fetch. 30-second TTL via service layer.
    """

    __tablename__ = "account_info"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    account_link_id = Column(
        String(36), ForeignKey("account_links.id"), nullable=False, index=True
    )
    balance = Column(Numeric(20, 2), nullable=True)
    equity = Column(Numeric(20, 2), nullable=True)
    free_margin = Column(Numeric(20, 2), nullable=True)
    margin_used = Column(Numeric(20, 2), nullable=True)
    margin_level = Column(Numeric(10, 2), nullable=True)
    drawdown_percent = Column(Numeric(6, 2), nullable=True)
    open_positions_count = Column(Integer, default=0, nullable=False)
    last_updated = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    account_link = relationship("AccountLink", back_populates="account_info")

    def __repr__(self):
        return f"<AccountInfo {self.id}: equity={self.equity} drawdown={self.drawdown_percent}%>"
