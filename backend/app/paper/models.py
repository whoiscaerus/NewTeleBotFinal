"""
Paper Trading Database Models

Provides virtual portfolio, positions, and trade history for sandbox mode.
"""

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Index, Numeric, String
from sqlalchemy.orm import relationship

from backend.app.core.db import Base


class TradeSide(Enum):
    """Trade direction"""

    BUY = "buy"
    SELL = "sell"


class PaperAccount(Base):
    """
    Virtual trading account for sandbox mode.

    Each user has one paper account with virtual balance.
    """

    __tablename__ = "paper_accounts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, unique=True)
    balance = Column(Numeric(15, 2), nullable=False, default=10000.00)  # Virtual cash
    equity = Column(
        Numeric(15, 2), nullable=False, default=10000.00
    )  # Balance + unrealized PnL
    enabled = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    user = relationship("User", back_populates="paper_account")
    positions = relationship(
        "PaperPosition", back_populates="account", cascade="all, delete-orphan"
    )
    trades = relationship(
        "PaperTrade", back_populates="account", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("ix_paper_accounts_user_id", "user_id"),
        {"extend_existing": True},
    )

    def __repr__(self):
        return f"<PaperAccount {self.id}: user={self.user_id} balance={self.balance} enabled={self.enabled}>"


class PaperPosition(Base):
    """
    Open position in paper trading account.

    Tracks unrealized PnL and position details.
    """

    __tablename__ = "paper_positions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    account_id = Column(
        String(36), ForeignKey("paper_accounts.id"), nullable=False, index=True
    )
    symbol = Column(String(20), nullable=False)
    side = Column(SQLEnum(TradeSide), nullable=False)
    volume = Column(Numeric(10, 2), nullable=False)
    entry_price = Column(Numeric(15, 5), nullable=False)
    current_price = Column(Numeric(15, 5), nullable=False)
    unrealized_pnl = Column(Numeric(15, 2), nullable=False, default=0.00)
    opened_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    account = relationship("PaperAccount", back_populates="positions")

    # Indexes
    __table_args__ = (
        Index("ix_paper_positions_account_symbol", "account_id", "symbol"),
        {"extend_existing": True},
    )

    def __repr__(self):
        return f"<PaperPosition {self.id}: {self.symbol} {self.side.value} {self.volume} @ {self.entry_price}>"


class PaperTrade(Base):
    """
    Closed trade in paper trading account.

    Records entry/exit prices, realized PnL, and slippage.
    """

    __tablename__ = "paper_trades"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    account_id = Column(
        String(36), ForeignKey("paper_accounts.id"), nullable=False, index=True
    )
    symbol = Column(String(20), nullable=False)
    side = Column(SQLEnum(TradeSide), nullable=False)
    volume = Column(Numeric(10, 2), nullable=False)
    entry_price = Column(Numeric(15, 5), nullable=False)
    exit_price = Column(
        Numeric(15, 5), nullable=True
    )  # NULL for entry-only (position still open)
    realized_pnl = Column(
        Numeric(15, 2), nullable=True
    )  # NULL until exit (calculated on close)
    slippage = Column(Numeric(15, 5), nullable=False, default=0.00)
    filled_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)  # NULL for open positions

    # Relationships
    account = relationship("PaperAccount", back_populates="trades")

    # Indexes
    __table_args__ = (
        Index("ix_paper_trades_account_filled", "account_id", "filled_at"),
        Index("ix_paper_trades_symbol", "symbol"),
        {"extend_existing": True},
    )

    def __repr__(self):
        status = "closed" if self.closed_at else "open"
        return f"<PaperTrade {self.id}: {self.symbol} {self.side.value} {self.volume} {status}>"
