"""
Public API for trading data pipeline module.

This module exports the main classes and functions for working with market data:
- MT5DataPuller: Pulls OHLC and price data from MT5
- DataPipeline: Orchestrates scheduled data pulling
- Models: SymbolPrice, OHLCCandle, DataPullLog
- Configuration: PullConfig, PipelineStatus

Example:
    >>> from backend.app.trading.data import (
    ...     MT5DataPuller,
    ...     DataPipeline,
    ...     SymbolPrice,
    ...     OHLCCandle,
    ...     PullConfig,
    ... )
    >>>
    >>> # Create pipeline
    >>> puller = MT5DataPuller(session_manager)
    >>> pipeline = DataPipeline(puller)
    >>> pipeline.add_pull_config(
    ...     name="forex_5m",
    ...     symbols=["EURUSD", "GBPUSD"],
    ...     interval_seconds=300
    ... )
    >>> await pipeline.start()
"""

from backend.app.trading.data.models import DataPullLog, OHLCCandle, SymbolPrice
from backend.app.trading.data.mt5_puller import DataValidationError, MT5DataPuller
from backend.app.trading.data.pipeline import DataPipeline, PipelineStatus, PullConfig

__all__ = [
    # Models
    "SymbolPrice",
    "OHLCCandle",
    "DataPullLog",
    # Puller
    "MT5DataPuller",
    "DataValidationError",
    # Pipeline
    "DataPipeline",
    "PullConfig",
    "PipelineStatus",
]
