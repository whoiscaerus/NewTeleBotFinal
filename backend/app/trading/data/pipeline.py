"""
Data pipeline orchestration for scheduled market data pulling.

This module provides the DataPipeline class which orchestrates periodic pulling
of market data from MT5 with:
- Scheduled execution (e.g., every 5 minutes)
- Error handling and retry logic
- Data caching for efficiency
- Graceful startup/shutdown
- Health monitoring

Architecture:
    The pipeline runs a background task that periodically calls MT5DataPuller
    to refresh market data. Multiple pull cycles can run concurrently for
    different symbols/timeframes.

Example:
    >>> from backend.app.trading.data.pipeline import DataPipeline
    >>> from backend.app.trading.mt5 import MT5SessionManager
    >>> from backend.app.trading.data.mt5_puller import MT5DataPuller
    >>>
    >>> session_manager = MT5SessionManager()
    >>> puller = MT5DataPuller(session_manager)
    >>> pipeline = DataPipeline(puller)
    >>>
    >>> # Start pulling data every 5 minutes
    >>> await pipeline.start()
    >>>
    >>> # ... later, gracefully stop
    >>> await pipeline.stop()
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from backend.app.trading.data.mt5_puller import MT5DataPuller

# Configure logger
logger = logging.getLogger(__name__)


@dataclass
class PullConfig:
    """Configuration for a data pull task.

    Attributes:
        symbols: List of symbols to pull data for
        timeframe: Candle timeframe (e.g., 'M5', 'H1')
        interval_seconds: Time between pulls in seconds
        enabled: Whether this pull is enabled
        max_retries: Maximum retry attempts on failure
    """

    symbols: list[str] = field(default_factory=list)
    timeframe: str = "M5"
    interval_seconds: int = 300  # 5 minutes default
    enabled: bool = True
    max_retries: int = 3


@dataclass
class PipelineStatus:
    """Current status of the data pipeline.

    Attributes:
        running: Whether pipeline is actively pulling data
        uptime_seconds: Seconds since pipeline started
        total_pulls: Total pull operations executed
        successful_pulls: Successful pull count
        failed_pulls: Failed pull count
        last_pull_time: Timestamp of last pull attempt
        next_pull_time: Estimated time of next pull
        active_symbols: Symbols currently being pulled
        error_message: Latest error message (if any)
    """

    running: bool = False
    uptime_seconds: int = 0
    total_pulls: int = 0
    successful_pulls: int = 0
    failed_pulls: int = 0
    last_pull_time: Optional[datetime] = None
    next_pull_time: Optional[datetime] = None
    active_symbols: list[str] = field(default_factory=list)
    error_message: Optional[str] = None


class DataPipeline:
    """Orchestrates scheduled market data pulling.

    Manages periodic pulling of OHLC and price data from MT5 with coordinated
    error handling and status tracking.

    The pipeline:
    1. Accepts multiple pull configurations
    2. Executes pulls on schedule
    3. Retries on failures (exponential backoff)
    4. Tracks success/failure metrics
    5. Provides health status

    Attributes:
        puller: MT5DataPuller instance for data operations
        pull_configs: Configuration for each pull task
        status: Current pipeline status

    Example:
        >>> pipeline = DataPipeline(puller)
        >>> pipeline.add_pull_config(
        ...     symbols=["EURUSD", "GBPUSD"],
        ...     timeframe="M5",
        ...     interval_seconds=300
        ... )
        >>> await pipeline.start()
        >>> status = pipeline.get_status()
        >>> print(f"Pipeline running: {status.running}")
        >>> await pipeline.stop()
    """

    # Timing constants
    MIN_PULL_INTERVAL = 60  # 1 minute minimum
    MAX_PULL_INTERVAL = 3600  # 1 hour maximum

    def __init__(self, puller: MT5DataPuller):
        """Initialize data pipeline.

        Args:
            puller: MT5DataPuller instance for data operations

        Raises:
            ValueError: If puller is None
        """
        if puller is None:
            raise ValueError("puller cannot be None")

        self.puller = puller
        self.pull_configs: dict[str, PullConfig] = {}
        self.status = PipelineStatus()

        # Background tasks
        self._pull_tasks: dict[str, asyncio.Task] = {}
        self._shutdown_event = asyncio.Event()
        self._start_time: Optional[datetime] = None

        logger.info("DataPipeline initialized", extra={"service": "pipeline"})

    def add_pull_config(
        self,
        name: str,
        symbols: list[str],
        timeframe: str = "M5",
        interval_seconds: int = 300,
        enabled: bool = True,
    ) -> None:
        """Add a data pull configuration.

        Configurations are named for easy management and status tracking.

        Args:
            name: Unique name for this pull configuration
            symbols: List of symbols to pull
            timeframe: Candle timeframe (default 'M5')
            interval_seconds: Pull interval in seconds (default 300)
            enabled: Whether to enable this pull (default True)

        Raises:
            ValueError: If name already exists or values invalid

        Example:
            >>> pipeline.add_pull_config(
            ...     name="forex_5min",
            ...     symbols=["EURUSD", "GBPUSD"],
            ...     interval_seconds=300
            ... )
        """
        # Validate inputs
        if name in self.pull_configs:
            raise ValueError(f"Pull config '{name}' already exists")
        if not symbols:
            raise ValueError("symbols list cannot be empty")
        if interval_seconds < self.MIN_PULL_INTERVAL:
            raise ValueError(f"interval_seconds must be >= {self.MIN_PULL_INTERVAL}")
        if interval_seconds > self.MAX_PULL_INTERVAL:
            raise ValueError(f"interval_seconds must be <= {self.MAX_PULL_INTERVAL}")

        config = PullConfig(
            symbols=symbols,
            timeframe=timeframe,
            interval_seconds=interval_seconds,
            enabled=enabled,
        )

        self.pull_configs[name] = config

        logger.info(
            f"Added pull config: {name}",
            extra={
                "config_name": name,
                "symbol_count": len(symbols),
                "interval_seconds": interval_seconds,
                "enabled": enabled,
            },
        )

    async def start(self) -> None:
        """Start the data pipeline.

        Launches background tasks for each enabled pull configuration.
        Already running pipeline start is no-op.

        Raises:
            ValueError: If no pull configurations defined

        Example:
            >>> await pipeline.start()
            >>> print("Pipeline started")
        """
        if not self.pull_configs:
            raise ValueError(
                "No pull configurations defined. Call add_pull_config first."
            )

        if self.status.running:
            logger.warning("Pipeline already running, ignoring start request")
            return

        logger.info(
            f"Starting DataPipeline with {len(self.pull_configs)} configs",
            extra={"config_count": len(self.pull_configs)},
        )

        self.status.running = True
        self._start_time = datetime.utcnow()
        self._shutdown_event.clear()

        # Start background task for each enabled config
        for config_name, config in self.pull_configs.items():
            if config.enabled:
                task = asyncio.create_task(self._pull_loop(config_name, config))
                self._pull_tasks[config_name] = task
                logger.debug(f"Started pull task: {config_name}")

        logger.info(
            f"Pipeline started with {len(self._pull_tasks)} active tasks",
            extra={"task_count": len(self._pull_tasks)},
        )

    async def stop(self) -> None:
        """Stop the data pipeline gracefully.

        Cancels all background pull tasks and waits for shutdown.
        Already stopped pipeline stop is no-op.

        Example:
            >>> await pipeline.stop()
            >>> print("Pipeline stopped")
        """
        if not self.status.running:
            logger.warning("Pipeline not running, ignoring stop request")
            return

        logger.info("Stopping DataPipeline")

        self.status.running = False
        self._shutdown_event.set()

        # Cancel all pull tasks
        for task_name, task in self._pull_tasks.items():
            logger.debug(f"Cancelling pull task: {task_name}")
            task.cancel()

        # Wait for all tasks to complete
        results = await asyncio.gather(
            *self._pull_tasks.values(), return_exceptions=True
        )

        # Check for exceptions
        for task_name, result in zip(self._pull_tasks.keys(), results):
            if isinstance(result, asyncio.CancelledError):
                logger.debug(f"Pull task {task_name} cancelled")
            elif isinstance(result, Exception):
                logger.error(f"Pull task {task_name} error: {result}")

        self._pull_tasks.clear()

        logger.info(
            "Pipeline stopped",
            extra={
                "total_pulls": self.status.total_pulls,
                "successful": self.status.successful_pulls,
                "failed": self.status.failed_pulls,
            },
        )

    async def _pull_loop(self, config_name: str, config: PullConfig) -> None:
        """Background task for periodic data pulling.

        Runs indefinitely, pulling data at specified intervals.

        Args:
            config_name: Configuration name
            config: PullConfig with pull parameters
        """
        logger.info(
            f"Pull loop started: {config_name}", extra={"config_name": config_name}
        )

        try:
            while not self._shutdown_event.is_set():
                try:
                    # Execute pull cycle
                    await self._pull_cycle(config_name, config)

                    # Wait for next interval
                    self.status.next_pull_time = datetime.utcnow() + timedelta(
                        seconds=config.interval_seconds
                    )

                    # Sleep until next pull (with cancellation support)
                    await asyncio.sleep(config.interval_seconds)

                except asyncio.CancelledError:
                    logger.debug(f"Pull loop {config_name} cancelled")
                    raise

                except Exception as e:
                    logger.error(
                        f"Error in pull loop {config_name}: {e}",
                        exc_info=True,
                        extra={"config_name": config_name},
                    )
                    self.status.error_message = str(e)

                    # Backoff before retry
                    await asyncio.sleep(min(config.interval_seconds, 30))

        except asyncio.CancelledError:
            pass

        finally:
            logger.info(
                f"Pull loop ended: {config_name}", extra={"config_name": config_name}
            )

    async def _pull_cycle(self, config_name: str, config: PullConfig) -> None:
        """Execute a single pull cycle for all symbols in config.

        Args:
            config_name: Configuration name
            config: PullConfig with symbols
        """
        self.status.total_pulls += 1
        self.status.last_pull_time = datetime.utcnow()
        self.status.active_symbols = config.symbols

        logger.info(
            f"Starting pull cycle: {config_name}",
            extra={
                "config_name": config_name,
                "symbol_count": len(config.symbols),
                "cycle_number": self.status.total_pulls,
            },
        )

        try:
            # Pull OHLC data for each symbol
            for symbol in config.symbols:
                try:
                    candles = await self.puller.get_ohlc_data(
                        symbol=symbol,
                        timeframe=config.timeframe,
                        count=100,
                        validate=True,
                    )

                    logger.debug(
                        f"Pulled {len(candles)} candles for {symbol}",
                        extra={"symbol": symbol, "candle_count": len(candles)},
                    )

                except Exception as e:
                    logger.warning(
                        f"Failed to pull {symbol}: {e}",
                        extra={"symbol": symbol, "error": str(e)},
                    )
                    continue

            # Pull current prices
            prices = await self.puller.get_all_symbols_data(config.symbols)

            logger.info(
                f"Pull cycle complete: {config_name}",
                extra={
                    "config_name": config_name,
                    "symbol_count": len(config.symbols),
                    "price_count": len(prices),
                },
            )

            self.status.successful_pulls += 1
            self.status.error_message = None

        except Exception as e:
            logger.error(
                f"Pull cycle failed: {config_name}",
                exc_info=True,
                extra={"config_name": config_name, "error": str(e)},
            )
            self.status.failed_pulls += 1
            self.status.error_message = str(e)
            raise

    def get_status(self) -> PipelineStatus:
        """Get current pipeline status.

        Returns:
            PipelineStatus object with current metrics

        Example:
            >>> status = pipeline.get_status()
            >>> print(f"Total pulls: {status.total_pulls}")
            >>> print(f"Success rate: {100 * status.successful_pulls / status.total_pulls:.1f}%")
        """
        # Update uptime
        if self._start_time:
            uptime = datetime.utcnow() - self._start_time
            self.status.uptime_seconds = int(uptime.total_seconds())

        return self.status

    async def health_check(self) -> bool:
        """Verify pipeline is operational.

        Returns:
            True if running and healthy, False otherwise

        Example:
            >>> if await pipeline.health_check():
            ...     print("Pipeline is healthy")
        """
        try:
            # Check if running
            if not self.status.running:
                logger.warning("Pipeline not running")
                return False

            # Check if all tasks alive
            for name, task in self._pull_tasks.items():
                if task.done():
                    logger.warning(f"Pull task {name} not running")
                    return False

            # Check puller health
            puller_healthy = await self.puller.health_check()
            if not puller_healthy:
                logger.warning("Puller health check failed")
                return False

            logger.info("Pipeline health check: PASS")
            return True

        except Exception as e:
            logger.error(f"Health check error: {e}", exc_info=True)
            return False

    def get_summary(self) -> dict[str, Any]:
        """Get text summary of pipeline state.

        Returns:
            Dictionary with summary information

        Example:
            >>> summary = pipeline.get_summary()
            >>> print(summary["status"])
        """
        status = self.get_status()
        total = status.total_pulls or 1

        return {
            "running": status.running,
            "total_pulls": status.total_pulls,
            "successful_pulls": status.successful_pulls,
            "failed_pulls": status.failed_pulls,
            "success_rate_percent": 100 * status.successful_pulls / total,
            "uptime_minutes": status.uptime_seconds // 60,
            "active_symbols": len(status.active_symbols),
            "configurations": len(self.pull_configs),
            "enabled_configurations": sum(
                1 for c in self.pull_configs.values() if c.enabled
            ),
        }
