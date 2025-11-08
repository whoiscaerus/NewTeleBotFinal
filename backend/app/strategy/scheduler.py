"""Strategy scheduler for orchestrating multi-strategy execution.

Coordinates execution of multiple strategies on new candle detection and fans out
signals to the Signals API (PR-021).

Flow:
    1. Detect new 15-min candle boundary
    2. Run all enabled strategies
    3. Collect SignalCandidate outputs
    4. POST to Signals API for each candidate
    5. Track telemetry and errors

Example:
    >>> from backend.app.strategy.scheduler import StrategyScheduler
    >>> from backend.app.strategy.registry import get_registry
    >>>
    >>> scheduler = StrategyScheduler(registry=get_registry())
    >>> await scheduler.run_strategies(df, "GOLD", datetime.utcnow())
"""

import logging
from datetime import datetime

import pandas as pd
from httpx import AsyncClient

from backend.app.observability.metrics import get_metrics
from backend.app.strategy.fib_rsi.schema import SignalCandidate
from backend.app.strategy.registry import StrategyRegistry

logger = logging.getLogger(__name__)


class StrategyScheduler:
    """Orchestrates execution of multiple trading strategies.

    Runs all enabled strategies on new candle data and posts signals to API.

    Attributes:
        registry: StrategyRegistry instance
        signals_api_base: Base URL for signals API
        http_client: HTTP client for API calls
    """

    def __init__(
        self,
        registry: StrategyRegistry,
        signals_api_base: str | None = None,
        http_client: AsyncClient | None = None,
    ):
        """Initialize strategy scheduler.

        Args:
            registry: StrategyRegistry with enabled strategies
            signals_api_base: Signals API base URL (e.g., "http://localhost:8000/api/v1")
            http_client: Optional HTTP client for API calls

        Example:
            >>> from backend.app.strategy.registry import get_registry
            >>> scheduler = StrategyScheduler(registry=get_registry())
        """
        self.registry = registry
        self.signals_api_base = signals_api_base or "http://localhost:8000/api/v1"
        self.http_client = http_client

        # Track metrics
        self.metrics = get_metrics()

        logger.info(
            "StrategyScheduler initialized",
            extra={
                "signals_api_base": self.signals_api_base,
                "enabled_strategies": registry.get_enabled_strategies(),
            },
        )

    async def run_strategies(
        self,
        df: pd.DataFrame,
        instrument: str,
        timestamp: datetime,
        post_to_api: bool = True,
    ) -> dict[str, list[SignalCandidate]]:
        """Run all enabled strategies on new candle data.

        Args:
            df: OHLC dataframe with columns [open, high, low, close, volume]
            instrument: Trading instrument (e.g., "GOLD", "EURUSD")
            timestamp: Candle timestamp (UTC)
            post_to_api: If True, POST signals to API (default: True)

        Returns:
            Dict mapping strategy names to list of generated signals

        Example:
            >>> df = pd.DataFrame({
            ...     'open': [1950.0],
            ...     'high': [1955.0],
            ...     'low': [1945.0],
            ...     'close': [1952.0],
            ...     'volume': [1000]
            ... })
            >>> signals = await scheduler.run_strategies(df, "GOLD", datetime.utcnow())
            >>> print(signals)  # {"fib_rsi": [SignalCandidate(...)]
        """
        enabled_strategies = self.registry.get_enabled_strategies()

        if not enabled_strategies:
            logger.warning(
                "No enabled strategies to run",
                extra={"instrument": instrument, "timestamp": timestamp},
            )
            return {}

        logger.info(
            f"Running {len(enabled_strategies)} strategies",
            extra={
                "strategies": enabled_strategies,
                "instrument": instrument,
                "timestamp": timestamp,
            },
        )

        results: dict[str, list[SignalCandidate]] = {}

        for strategy_name in enabled_strategies:
            try:
                # Get strategy instance
                strategy = self.registry.get_strategy(strategy_name)

                # Track metrics
                self.metrics.strategy_runs_total.labels(name=strategy_name).inc()

                # Run strategy
                start_time = datetime.utcnow()

                signal = await strategy.generate_signal(df, instrument, timestamp)

                elapsed = (datetime.utcnow() - start_time).total_seconds()

                # Collect results
                if signal is None:
                    logger.debug(
                        f"Strategy {strategy_name} returned no signal",
                        extra={"strategy": strategy_name, "instrument": instrument},
                    )
                    results[strategy_name] = []
                    continue

                # Handle single signal or list of signals
                signals = [signal] if not isinstance(signal, list) else signal

                results[strategy_name] = signals

                logger.info(
                    f"Strategy {strategy_name} generated {len(signals)} signal(s)",
                    extra={
                        "strategy": strategy_name,
                        "signal_count": len(signals),
                        "instrument": instrument,
                        "elapsed_seconds": elapsed,
                    },
                )

                # Track emit metrics
                self.metrics.strategy_emit_total.labels(name=strategy_name).inc(
                    len(signals)
                )

                # POST signals to API
                if post_to_api and signals:
                    await self._post_signals_to_api(signals, strategy_name)

            except Exception as e:
                logger.error(
                    f"Strategy {strategy_name} failed",
                    exc_info=True,
                    extra={
                        "strategy": strategy_name,
                        "instrument": instrument,
                        "error": str(e),
                    },
                )
                results[strategy_name] = []
                # Continue with other strategies instead of failing completely

        return results

    async def _post_signals_to_api(
        self, signals: list[SignalCandidate], strategy_name: str
    ) -> None:
        """POST signals to Signals API.

        Args:
            signals: List of signal candidates to post
            strategy_name: Name of strategy that generated signals

        Example:
            >>> signal = SignalCandidate(
            ...     instrument="GOLD",
            ...     side="buy",
            ...     entry_price=1950.0,
            ...     stop_loss=1935.0,
            ...     take_profit=1980.0,
            ...     confidence=0.85,
            ...     timestamp=datetime.utcnow(),
            ...     reason="rsi_oversold"
            ... )
            >>> await scheduler._post_signals_to_api([signal], "fib_rsi")
        """
        if not self.http_client:
            logger.warning(
                "No HTTP client configured, skipping signal POST",
                extra={"strategy": strategy_name, "signal_count": len(signals)},
            )
            return

        for signal in signals:
            try:
                # Convert SignalCandidate to API format
                payload = {
                    "instrument": signal.instrument,
                    "side": signal.side,
                    "price": signal.entry_price,
                    "payload": {
                        **signal.payload,
                        "confidence": signal.confidence,
                        "reason": signal.reason,
                        "strategy": strategy_name,
                        "timestamp": signal.timestamp.isoformat(),
                    },
                    "owner_only": {
                        "stop_loss": signal.stop_loss,
                        "take_profit": signal.take_profit,
                        "strategy": strategy_name,
                    },
                }

                response = await self.http_client.post(
                    f"{self.signals_api_base}/signals",
                    json=payload,
                    timeout=10.0,
                )

                response.raise_for_status()

                logger.info(
                    f"Posted signal to API: {signal.instrument} {signal.side}",
                    extra={
                        "strategy": strategy_name,
                        "instrument": signal.instrument,
                        "side": signal.side,
                        "entry_price": signal.entry_price,
                        "confidence": signal.confidence,
                    },
                )

            except Exception as e:
                logger.error(
                    "Failed to POST signal to API",
                    exc_info=True,
                    extra={
                        "strategy": strategy_name,
                        "instrument": signal.instrument,
                        "error": str(e),
                    },
                )
                # Continue with other signals instead of failing completely

    async def run_on_new_candle(
        self,
        df: pd.DataFrame,
        instrument: str,
        timestamp: datetime,
        timeframe: str = "15m",
        window_seconds: int = 60,
    ) -> dict[str, list[SignalCandidate]] | None:
        """Run strategies only if this is a new candle.

        Checks if timestamp is at a candle boundary (e.g., :00, :15, :30, :45 for 15m).
        Allows a window for timing drift.

        Args:
            df: OHLC dataframe
            instrument: Trading instrument
            timestamp: Current timestamp
            timeframe: Timeframe string (e.g., "15m", "1h")
            window_seconds: Grace period for candle boundary detection

        Returns:
            Dict of signals if new candle detected, None otherwise

        Example:
            >>> # At 10:15:05 UTC (new 15m candle + 5 second drift)
            >>> signals = await scheduler.run_on_new_candle(
            ...     df, "GOLD", datetime(2025, 1, 1, 10, 15, 5)
            ... )
            >>> # signals will be generated
            >>>
            >>> # At 10:17:30 UTC (mid-candle)
            >>> signals = await scheduler.run_on_new_candle(
            ...     df, "GOLD", datetime(2025, 1, 1, 10, 17, 30)
            ... )
            >>> # signals will be None (not a new candle)
        """
        # Check if timestamp is at candle boundary
        is_new_candle = self._is_new_candle(timestamp, timeframe, window_seconds)

        if not is_new_candle:
            logger.debug(
                f"Not a new {timeframe} candle, skipping strategy execution",
                extra={
                    "instrument": instrument,
                    "timestamp": timestamp,
                    "timeframe": timeframe,
                },
            )
            return None

        logger.info(
            f"New {timeframe} candle detected, running strategies",
            extra={
                "instrument": instrument,
                "timestamp": timestamp,
                "timeframe": timeframe,
            },
        )

        return await self.run_strategies(df, instrument, timestamp)

    def _is_new_candle(
        self, timestamp: datetime, timeframe: str, window_seconds: int
    ) -> bool:
        """Check if timestamp is at a new candle boundary.

        Args:
            timestamp: Timestamp to check
            timeframe: Timeframe string (e.g., "15m", "1h")
            window_seconds: Grace period for timing drift

        Returns:
            True if within window of candle boundary, False otherwise

        Example:
            >>> scheduler = StrategyScheduler(registry)
            >>> # At 10:15:05 (5 seconds after 15m boundary)
            >>> scheduler._is_new_candle(datetime(2025, 1, 1, 10, 15, 5), "15m", 60)
            True
            >>> # At 10:17:30 (mid-candle)
            >>> scheduler._is_new_candle(datetime(2025, 1, 1, 10, 17, 30), "15m", 60)
            False
        """
        # Parse timeframe
        if timeframe.endswith("m"):
            interval_minutes = int(timeframe[:-1])
        elif timeframe.endswith("h"):
            interval_minutes = int(timeframe[:-1]) * 60
        else:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        # Calculate seconds since epoch
        total_seconds = int(timestamp.timestamp())

        # Calculate interval in seconds
        interval_seconds = interval_minutes * 60

        # Calculate seconds within current candle
        seconds_in_candle = total_seconds % interval_seconds

        # Check if within window of boundary (0 or interval_seconds)
        is_boundary = seconds_in_candle <= window_seconds

        return is_boundary
