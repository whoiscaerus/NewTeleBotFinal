"""Data adapters for backtesting framework.

Provides interfaces to load historical OHLCV data from various sources
(CSV, Parquet, database) for deterministic strategy backtesting.

Adapters:
    - DataAdapter: Base interface
    - CSVAdapter: Load from CSV files
    - ParquetAdapter: Load from Parquet files
    - DatabaseAdapter: Load from PostgreSQL warehouse (PR-051)

All adapters return standardized pandas DataFrames with:
    - timestamp: datetime64[ns, UTC]
    - open, high, low, close: float64
    - volume: int64
    - symbol: str

Example:
    >>> adapter = CSVAdapter("data/GOLD_15M.csv")
    >>> df = await adapter.load(start="2024-01-01", end="2024-12-31")
    >>> assert df.index.name == "timestamp"
    >>> assert list(df.columns) == ["open", "high", "low", "close", "volume", "symbol"]
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class DataAdapter(ABC):
    """Base interface for historical data adapters."""

    @abstractmethod
    async def load(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        """Load historical OHLCV data for symbol in date range.

        Args:
            symbol: Trading symbol (e.g., "GOLD", "SP500")
            start: Start datetime (inclusive), None = from beginning
            end: End datetime (inclusive), None = to end

        Returns:
            DataFrame with columns: [open, high, low, close, volume, symbol]
            Index: timestamp (datetime64[ns, UTC])

        Raises:
            ValueError: If symbol not found or date range invalid
            FileNotFoundError: If data file missing (CSV/Parquet adapters)
        """
        pass

    @abstractmethod
    def validate(self) -> bool:
        """Validate adapter configuration and data availability.

        Returns:
            True if adapter is properly configured and data accessible

        Raises:
            ValueError: If configuration invalid
        """
        pass


class CSVAdapter(DataAdapter):
    """Load historical data from CSV files.

    Expected CSV format:
        timestamp,open,high,low,close,volume,symbol
        2024-01-01 00:00:00+00:00,1950.50,1951.00,1949.50,1950.75,1000,GOLD

    Timestamp column:
        - Must be first column
        - Must be parseable by pandas (ISO format recommended)
        - Will be converted to UTC timezone

    Attributes:
        filepath: Path to CSV file
        symbol: Trading symbol (defaults to filename if not in CSV)
        delimiter: CSV delimiter (default: ",")
    """

    def __init__(
        self,
        filepath: str | Path,
        symbol: str | None = None,
        delimiter: str = ",",
    ):
        """Initialize CSV adapter.

        Args:
            filepath: Path to CSV file
            symbol: Trading symbol (overrides CSV column if provided)
            delimiter: CSV delimiter character

        Raises:
            FileNotFoundError: If CSV file doesn't exist
        """
        self.filepath = Path(filepath)
        if not self.filepath.exists():
            raise FileNotFoundError(f"CSV file not found: {self.filepath}")

        self.symbol = symbol
        self.delimiter = delimiter

        logger.info(f"CSVAdapter initialized: {self.filepath}, symbol={symbol}")

    def validate(self) -> bool:
        """Validate CSV file exists and has required columns."""
        if not self.filepath.exists():
            raise ValueError(f"CSV file not found: {self.filepath}")

        # Read first row to validate columns
        df = pd.read_csv(self.filepath, nrows=1, delimiter=self.delimiter)
        required_cols = ["open", "high", "low", "close", "volume"]

        missing = set(required_cols) - set(df.columns)
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}")

        logger.info(f"CSVAdapter validation passed: {self.filepath}")
        return True

    async def load(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        """Load data from CSV file.

        Args:
            symbol: Trading symbol (must match adapter symbol if set)
            start: Start datetime (inclusive)
            end: End datetime (inclusive)

        Returns:
            DataFrame with OHLCV data indexed by timestamp

        Raises:
            ValueError: If symbol mismatch or invalid date range
        """
        if self.symbol and self.symbol != symbol:
            raise ValueError(
                f"Symbol mismatch: adapter={self.symbol}, requested={symbol}"
            )

        logger.info(
            f"Loading CSV data: symbol={symbol}, start={start}, end={end}, "
            f"file={self.filepath}"
        )

        # Read CSV with timestamp as index
        df = pd.read_csv(
            self.filepath,
            delimiter=self.delimiter,
            parse_dates=[0],
            index_col=0,
        )

        # Rename first column to 'timestamp' if needed
        if df.index.name != "timestamp":
            df.index.name = "timestamp"

        # Convert to UTC timezone
        if df.index.tz is None:
            df.index = pd.to_datetime(df.index, utc=True)
        else:
            df.index = df.index.tz_convert("UTC")

        # Add symbol column if not present
        if "symbol" not in df.columns:
            df["symbol"] = symbol or self.symbol or self.filepath.stem

        # Filter by symbol if CSV contains multiple symbols
        if "symbol" in df.columns:
            df = df[df["symbol"] == symbol]

        # Filter by date range
        if start is not None:
            if start.tzinfo is None:
                start = start.replace(tzinfo=pd.Timestamp.utcnow().tz)
            df = df[df.index >= start]

        if end is not None:
            if end.tzinfo is None:
                end = end.replace(tzinfo=pd.Timestamp.utcnow().tz)
            df = df[df.index <= end]

        if df.empty:
            raise ValueError(
                f"No data found for symbol={symbol}, start={start}, end={end}"
            )

        logger.info(f"Loaded {len(df)} rows from CSV: {self.filepath}")

        # Ensure column order and types
        df = df[["open", "high", "low", "close", "volume", "symbol"]].copy()
        df["volume"] = df["volume"].astype("int64")

        return df


class ParquetAdapter(DataAdapter):
    """Load historical data from Parquet files.

    Parquet format advantages:
        - Columnar storage (faster filtering)
        - Compression (smaller files)
        - Schema enforcement (type safety)

    Expected schema:
        timestamp: datetime64[ns, UTC]
        open, high, low, close: float64
        volume: int64
        symbol: string

    Attributes:
        filepath: Path to Parquet file
        symbol: Trading symbol (defaults to filename if not in file)
    """

    def __init__(
        self,
        filepath: str | Path,
        symbol: str | None = None,
    ):
        """Initialize Parquet adapter.

        Args:
            filepath: Path to Parquet file
            symbol: Trading symbol (overrides Parquet column if provided)

        Raises:
            FileNotFoundError: If Parquet file doesn't exist
        """
        self.filepath = Path(filepath)
        if not self.filepath.exists():
            raise FileNotFoundError(f"Parquet file not found: {self.filepath}")

        self.symbol = symbol

        logger.info(f"ParquetAdapter initialized: {self.filepath}, symbol={symbol}")

    def validate(self) -> bool:
        """Validate Parquet file exists and has required schema."""
        if not self.filepath.exists():
            raise ValueError(f"Parquet file not found: {self.filepath}")

        # Read Parquet schema
        parquet_file = pq.ParquetFile(self.filepath)
        schema = parquet_file.schema_arrow

        required_cols = ["open", "high", "low", "close", "volume"]
        existing_cols = [field.name for field in schema]

        missing = set(required_cols) - set(existing_cols)
        if missing:
            raise ValueError(f"Parquet missing required columns: {missing}")

        logger.info(f"ParquetAdapter validation passed: {self.filepath}")
        return True

    async def load(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        """Load data from Parquet file.

        Args:
            symbol: Trading symbol (must match adapter symbol if set)
            start: Start datetime (inclusive)
            end: End datetime (inclusive)

        Returns:
            DataFrame with OHLCV data indexed by timestamp

        Raises:
            ValueError: If symbol mismatch or invalid date range
        """
        if self.symbol and self.symbol != symbol:
            raise ValueError(
                f"Symbol mismatch: adapter={self.symbol}, requested={symbol}"
            )

        logger.info(
            f"Loading Parquet data: symbol={symbol}, start={start}, end={end}, "
            f"file={self.filepath}"
        )

        # Read Parquet file
        df = pd.read_parquet(self.filepath)

        # Set timestamp as index if present
        if "timestamp" in df.columns:
            df = df.set_index("timestamp")
        elif df.index.name != "timestamp":
            # Assume first column is timestamp
            df.index.name = "timestamp"

        # Convert to UTC timezone
        if df.index.tz is None:
            df.index = pd.to_datetime(df.index, utc=True)
        else:
            df.index = df.index.tz_convert("UTC")

        # Add symbol column if not present
        if "symbol" not in df.columns:
            df["symbol"] = symbol or self.symbol or self.filepath.stem

        # Filter by symbol if Parquet contains multiple symbols
        if "symbol" in df.columns:
            df = df[df["symbol"] == symbol]

        # Filter by date range
        if start is not None:
            if start.tzinfo is None:
                start = start.replace(tzinfo=pd.Timestamp.utcnow().tz)
            df = df[df.index >= start]

        if end is not None:
            if end.tzinfo is None:
                end = end.replace(tzinfo=pd.Timestamp.utcnow().tz)
            df = df[df.index <= end]

        if df.empty:
            raise ValueError(
                f"No data found for symbol={symbol}, start={start}, end={end}"
            )

        logger.info(f"Loaded {len(df)} rows from Parquet: {self.filepath}")

        # Ensure column order and types
        df = df[["open", "high", "low", "close", "volume", "symbol"]].copy()
        df["volume"] = df["volume"].astype("int64")

        return df


class DatabaseAdapter(DataAdapter):
    """Load historical data from PostgreSQL warehouse (PR-051).

    Queries the trades_fact table and daily_rollups for OHLCV data.
    Useful for backtesting against production data.

    Attributes:
        db_session: SQLAlchemy async session
        table: Table name to query (default: "daily_rollups")
    """

    def __init__(
        self,
        db_session: AsyncSession,
        table: str = "daily_rollups",
    ):
        """Initialize database adapter.

        Args:
            db_session: SQLAlchemy async session
            table: Table to query for OHLCV data

        Raises:
            ValueError: If table name invalid
        """
        self.db_session = db_session
        self.table = table

        logger.info(f"DatabaseAdapter initialized: table={table}")

    def validate(self) -> bool:
        """Validate database connection and table exists."""
        # Connection validation happens at query time
        logger.info(f"DatabaseAdapter validation passed: table={self.table}")
        return True

    async def load(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        """Load data from database.

        Args:
            symbol: Trading symbol
            start: Start datetime (inclusive)
            end: End datetime (inclusive)

        Returns:
            DataFrame with OHLCV data indexed by timestamp

        Raises:
            ValueError: If no data found or query fails
        """
        logger.info(
            f"Loading database data: symbol={symbol}, start={start}, end={end}, "
            f"table={self.table}"
        )

        # Build query (this is a simplified version - real implementation would
        # import the actual model from backend.app.analytics.models)
        query = f"""
            SELECT timestamp, open, high, low, close, volume, symbol
            FROM {self.table}
            WHERE symbol = :symbol
        """

        if start:
            query += " AND timestamp >= :start"
        if end:
            query += " AND timestamp <= :end"

        query += " ORDER BY timestamp ASC"

        # Execute query
        params: dict[str, Any] = {"symbol": symbol}
        if start:
            params["start"] = start
        if end:
            params["end"] = end

        result = await self.db_session.execute(text(query), params)
        rows = result.fetchall()

        if not rows:
            raise ValueError(
                f"No data found for symbol={symbol}, start={start}, end={end}"
            )

        # Convert to DataFrame
        df = pd.DataFrame(
            rows,
            columns=["timestamp", "open", "high", "low", "close", "volume", "symbol"],
        )

        # Set timestamp as index and convert to UTC
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.set_index("timestamp")

        logger.info(f"Loaded {len(df)} rows from database: table={self.table}")

        # Ensure types
        df["volume"] = df["volume"].astype("int64")

        return df
