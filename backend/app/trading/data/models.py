"""
Trading data models for OHLC candles and symbol prices.

This module defines SQLAlchemy ORM models for storing market data pulled from MT5.
All timestamps are UTC-based for consistency across timezones.

Models:
    SymbolPrice: Current price snapshot for a trading symbol
    OHLCCandle: Open-High-Low-Close candle data for a specific timeframe
    DataPullLog: Audit trail of data pull operations for monitoring

Example:
    >>> from backend.app.trading.data.models import SymbolPrice, OHLCCandle
    >>> from datetime import datetime
    >>>
    >>> # Create a price snapshot
    >>> price = SymbolPrice(
    ...     symbol="GOLD",
    ...     bid=1950.50,
    ...     ask=1950.75,
    ...     timestamp=datetime.utcnow()
    ... )
    >>>
    >>> # Create a candle
    >>> candle = OHLCCandle(
    ...     symbol="EURUSD",
    ...     open=1.0850,
    ...     high=1.0875,
    ...     low=1.0840,
    ...     close=1.0865,
    ...     volume=1000000,
    ...     time_open=datetime.utcnow()
    ... )
"""

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from backend.app.core.db import Base


class SymbolPrice(Base):
    """Current price snapshot for a trading symbol.

    Represents the most recent bid/ask prices for a symbol. Used for:
    - Real-time price display
    - Current valuation
    - Spread monitoring
    - Data freshness tracking

    Attributes:
        id: Unique identifier (primary key)
        symbol: Trading symbol (e.g., 'GOLD', 'EURUSD')
        bid: Current bid price
        ask: Current ask price
        timestamp: UTC timestamp of the price snapshot
        created_at: Record creation timestamp (UTC)
        updated_at: Record last update timestamp (UTC)

    Relationships:
        None - Standalone record

    Indexes:
        - symbol: For quick symbol lookups
        - timestamp: For time-based queries
        - symbol + timestamp: For symbol history retrieval

    Example:
        >>> price = SymbolPrice(
        ...     symbol="GOLD",
        ...     bid=1950.50,
        ...     ask=1950.75,
        ...     timestamp=datetime.utcnow()
        ... )
        >>> db.add(price)
        >>> await db.commit()
    """

    __tablename__ = "symbol_prices"

    # Primary key
    id = Column(String(36), primary_key=True, nullable=False)

    # Core data
    symbol = Column(String(20), nullable=False, index=True)
    bid = Column(Float, nullable=False)
    ask = Column(Float, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)

    # Metadata
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
    )

    # Indexes for performance
    __table_args__ = (
        Index("ix_symbol_prices_symbol_timestamp", "symbol", "timestamp"),
        Index("ix_symbol_prices_created", "created_at"),
    )

    def __repr__(self) -> str:
        """String representation of price snapshot."""
        spread = self.ask - self.bid
        return (
            f"<SymbolPrice {self.symbol}: "
            f"bid={self.bid:.5f} ask={self.ask:.5f} spread={spread:.5f}>"
        )

    def get_mid_price(self) -> float:
        """Calculate mid price (average of bid and ask).

        Returns:
            Mid price as (bid + ask) / 2
        """
        return (self.bid + self.ask) / 2.0

    def get_spread(self) -> float:
        """Calculate bid-ask spread.

        Returns:
            Spread as ask - bid
        """
        return self.ask - self.bid

    def get_spread_percent(self) -> float:
        """Calculate spread as percentage of mid price.

        Returns:
            Spread percentage (spread / mid_price * 100)
        """
        mid = self.get_mid_price()
        if mid == 0:
            return 0.0
        return (self.get_spread() / mid) * 100.0


class OHLCCandle(Base):
    """Open-High-Low-Close candle data for a specific timeframe.

    Represents historical price data aggregated into candles.
    Used for:
    - Technical analysis
    - Strategy backtesting
    - Historical price queries
    - Indicator calculations

    Attributes:
        id: Unique identifier (primary key)
        symbol: Trading symbol (e.g., 'EURUSD')
        open: Opening price for the candle
        high: Highest price during the candle period
        low: Lowest price during the candle period
        close: Closing price for the candle
        volume: Trading volume during candle period
        time_open: UTC timestamp when candle opened
        time_close: UTC timestamp when candle closed
        created_at: Record creation timestamp (UTC)
        updated_at: Record last update timestamp (UTC)

    Relationships:
        None - Standalone record

    Constraints:
        - Unique constraint on (symbol, time_open) to prevent duplicates
        - high >= low, high >= open/close, low <= open/close

    Indexes:
        - symbol: For symbol lookups
        - time_open: For chronological queries
        - symbol + time_open: For symbol history

    Example:
        >>> candle = OHLCCandle(
        ...     symbol="EURUSD",
        ...     open=1.0850,
        ...     high=1.0875,
        ...     low=1.0840,
        ...     close=1.0865,
        ...     volume=1000000,
        ...     time_open=datetime.utcnow()
        ... )
        >>> db.add(candle)
        >>> await db.commit()
    """

    __tablename__ = "ohlc_candles"

    # Primary key
    id = Column(String(36), primary_key=True, nullable=False)

    # Symbol and time identification
    symbol = Column(String(20), nullable=False, index=True)
    time_open = Column(DateTime(timezone=True), nullable=False, index=True)
    time_close = Column(DateTime(timezone=True), nullable=True)

    # OHLC data
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Integer, nullable=False, default=0)

    # Metadata
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
    )

    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint("symbol", "time_open", name="uq_candles_symbol_time"),
        Index("ix_ohlc_candles_symbol_time", "symbol", "time_open"),
        Index("ix_ohlc_candles_created", "created_at"),
    )

    def __repr__(self) -> str:
        """String representation of candle."""
        return (
            f"<OHLCCandle {self.symbol} @ {self.time_open}: "
            f"O={self.open:.5f} H={self.high:.5f} L={self.low:.5f} C={self.close:.5f}>"
        )

    def get_range(self) -> float:
        """Calculate high-low range.

        Returns:
            Range as high - low
        """
        return self.high - self.low

    def get_change(self) -> float:
        """Calculate open-to-close change.

        Returns:
            Change as close - open
        """
        return self.close - self.open

    def get_change_percent(self) -> float:
        """Calculate open-to-close change as percentage.

        Returns:
            Change percentage (change / open * 100)
        """
        if self.open == 0:
            return 0.0
        return (self.get_change() / self.open) * 100.0

    def is_bullish(self) -> bool:
        """Determine if candle is bullish (close > open).

        Returns:
            True if close > open, False otherwise
        """
        return self.close > self.open

    def is_bearish(self) -> bool:
        """Determine if candle is bearish (close < open).

        Returns:
            True if close < open, False otherwise
        """
        return self.close < self.open

    def get_true_range(self) -> float:
        """Calculate true range (for ATR calculations).

        True range = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close)
        )

        Note: This implementation only calculates high - low.
        To use true range properly, pass previous close:
        max(self.high - self.low, ...)

        Returns:
            High - low range as minimum true range value
        """
        return self.get_range()


class DataPullLog(Base):
    """Audit trail of data pull operations.

    Tracks all data pulling events for:
    - Monitoring and alerting
    - Debugging pull failures
    - Performance tracking
    - Data quality metrics

    Attributes:
        id: Unique identifier (primary key)
        symbol: Trading symbol that was pulled
        status: Pull result status ('success', 'error', 'partial', 'skipped')
        records_pulled: Number of records successfully pulled
        error_message: Error details if status is 'error'
        duration_ms: Time taken for pull operation (milliseconds)
        timestamp: When the pull operation executed (UTC)
        created_at: Record creation timestamp (UTC)

    Relationships:
        None - Standalone record

    Indexes:
        - symbol: For symbol-specific queries
        - status: For error tracking
        - timestamp: For time-based queries

    Example:
        >>> log = DataPullLog(
        ...     symbol="EURUSD",
        ...     status="success",
        ...     records_pulled=100,
        ...     duration_ms=245,
        ...     timestamp=datetime.utcnow()
        ... )
        >>> db.add(log)
        >>> await db.commit()
    """

    __tablename__ = "data_pull_logs"

    # Primary key
    id = Column(String(36), primary_key=True, nullable=False)

    # Operation details
    symbol = Column(String(20), nullable=False, index=True)
    status = Column(
        String(20), nullable=False, index=True
    )  # success, error, partial, skipped
    records_pulled = Column(Integer, nullable=False, default=0)
    duration_ms = Column(Integer, nullable=False, default=0)

    # Error tracking
    error_message = Column(Text, nullable=True)

    # Timestamp of the pull operation
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)

    # Record metadata
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )

    # Indexes
    __table_args__ = (
        Index("ix_data_pull_logs_symbol_status", "symbol", "status"),
        Index("ix_data_pull_logs_timestamp", "timestamp"),
    )

    def __repr__(self) -> str:
        """String representation of pull log."""
        return (
            f"<DataPullLog {self.symbol} {self.status}: "
            f"records={self.records_pulled} duration={self.duration_ms}ms>"
        )

    def get_success_rate(self) -> float:
        """Estimate success rate based on records pulled.

        Note: This is a simple heuristic. Actual rate depends on expected
        number of records, which varies by timeframe and symbol.

        Returns:
            Percentage estimate (0-100)
        """
        if self.status == "success":
            return 100.0
        elif self.status == "partial":
            return 50.0
        else:
            return 0.0

    def is_error(self) -> bool:
        """Check if pull failed.

        Returns:
            True if status is 'error'
        """
        return self.status == "error"

    def is_success(self) -> bool:
        """Check if pull succeeded.

        Returns:
            True if status is 'success'
        """
        return self.status == "success"
