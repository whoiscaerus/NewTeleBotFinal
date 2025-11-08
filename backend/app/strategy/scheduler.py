"""Strategy scheduler for orchestrating multi-strategy execution.

Coordinates execution of multiple strategies on new candle detection and fans out
signals to the Signals API (PR-021). Integrates with PR-072 for precise candle
boundary detection and unified signal publishing.

Flow:
    1. Detect new 15-min candle boundary (PR-072 CandleDetector)
    2. Prevent duplicate processing within same candle (PR-072)
    3. Run all enabled strategies
    4. Collect SignalCandidate outputs
    5. Publish to Signals API + optional Telegram (PR-072 SignalPublisher)
    6. Track telemetry and errors (PR-060)

Integration:
    - PR-071: Strategy Engine orchestration
    - PR-072: CandleDetector for boundary detection + SignalPublisher for routing
    - PR-021: Signals API endpoint
    - PR-060: Telemetry metrics

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
from backend.app.strategy.candles import CandleDetector
from backend.app.strategy.fib_rsi.schema import SignalCandidate
from backend.app.strategy.publisher import SignalPublisher
from backend.app.strategy.registry import StrategyRegistry

logger = logging.getLogger(__name__)


class StrategyScheduler:
    """Orchestrates execution of multiple trading strategies.

    Runs all enabled strategies on new candle data and posts signals to API.
    Uses PR-072 CandleDetector for precise boundary detection and SignalPublisher
    for unified routing to Signals API + Telegram.

    Attributes:
        registry: StrategyRegistry instance
        candle_detector: CandleDetector for boundary detection (PR-072)
        signal_publisher: SignalPublisher for API/Telegram routing (PR-072)
        signals_api_base: Base URL for signals API (deprecated, use signal_publisher)
        http_client: HTTP client for API calls (deprecated, use signal_publisher)
    """

    def __init__(
        self,
        registry: StrategyRegistry,
        signals_api_base: str | None = None,
        http_client: AsyncClient | None = None,
        candle_detector: CandleDetector | None = None,
        signal_publisher: SignalPublisher | None = None,
    ):
        """Initialize strategy scheduler.

        Args:
            registry: StrategyRegistry with enabled strategies
            signals_api_base: Signals API base URL (deprecated, use signal_publisher)
            http_client: Optional HTTP client for API calls (deprecated)
            candle_detector: CandleDetector instance (default: auto-create from env)
            signal_publisher: SignalPublisher instance (default: auto-create from env)

        Example:
            >>> from backend.app.strategy.registry import get_registry
            >>> scheduler = StrategyScheduler(registry=get_registry())
        """
        self.registry = registry
        self.signals_api_base = signals_api_base or "http://localhost:8000/api/v1"
        self.http_client = http_client

        # PR-072 Integration: Use CandleDetector and SignalPublisher
        self.candle_detector = candle_detector or CandleDetector()
        self.signal_publisher = signal_publisher or SignalPublisher(
            signals_api_base=signals_api_base
        )

        # Track metrics
        self.metrics = get_metrics()

        logger.info(
            "StrategyScheduler initialized with PR-072 integration",
            extra={
                "signals_api_base": self.signals_api_base,
                "enabled_strategies": registry.get_enabled_strategies(),
                "candle_window_seconds": self.candle_detector.window_seconds,
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

                # POST signals to API (PR-072 integration)
                if post_to_api and signals:
                    await self._publish_signals(
                        signals, strategy_name, instrument, timestamp
                    )

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

    async def _publish_signals(
        self,
        signals: list[SignalCandidate],
        strategy_name: str,
        instrument: str,
        timestamp: datetime,
    ) -> None:
        """Publish signals via SignalPublisher (PR-072).

        Uses SignalPublisher for unified routing to Signals API (PR-021) and
        optional Telegram admin notifications with duplicate prevention.

        Args:
            signals: List of signal candidates to publish
            strategy_name: Name of strategy that generated signals
            instrument: Trading instrument
            timestamp: Candle timestamp for duplicate prevention

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
            >>> await scheduler._publish_signals([signal], "fib_rsi", "GOLD", datetime.utcnow())
        """
        # Get candle start for duplicate prevention
        candle_start = self.candle_detector.get_candle_start(timestamp, "15m")

        for signal in signals:
            try:
                # Convert SignalCandidate to SignalPublisher format
                signal_data = {
                    "instrument": signal.instrument,
                    "side": signal.side,
                    "entry_price": signal.entry_price,
                    "stop_loss": signal.stop_loss,
                    "take_profit": signal.take_profit,
                    "strategy": strategy_name,
                    "timestamp": signal.timestamp,
                    "confidence": signal.confidence,
                    "reason": signal.reason,
                    "payload": signal.payload,
                }

                # Publish via SignalPublisher (PR-072)
                result = await self.signal_publisher.publish(
                    signal_data=signal_data,
                    candle_start=candle_start,
                    notify_telegram=False,  # Disable Telegram for now, can be enabled later
                )

                if result.get("api_success"):
                    logger.info(
                        f"Published signal: {signal.instrument} {signal.side}",
                        extra={
                            "strategy": strategy_name,
                            "instrument": signal.instrument,
                            "side": signal.side,
                            "entry_price": signal.entry_price,
                            "signal_id": result.get("signal_id"),
                            "telegram_notified": result.get("telegram_success", False),
                        },
                    )
                else:
                    logger.warning(
                        f"Failed to publish signal: {signal.instrument} {signal.side}",
                        extra={
                            "strategy": strategy_name,
                            "error": result.get("error"),
                        },
                    )

            except Exception as e:
                logger.error(
                    "Failed to publish signal",
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
        """Run strategies only if this is a new candle (PR-072 integration).

        Uses CandleDetector for precise boundary detection and duplicate prevention.
        Checks if timestamp is at a candle boundary (e.g., :00, :15, :30, :45 for 15m).

        Args:
            df: OHLC dataframe
            instrument: Trading instrument
            timestamp: Current timestamp
            timeframe: Timeframe string (e.g., "15m", "1h")
            window_seconds: Grace period (deprecated, uses CandleDetector.window_seconds)

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
        # PR-072: Use CandleDetector for boundary detection and duplicate prevention
        if not self.candle_detector.should_process_candle(
            instrument, timeframe, timestamp
        ):
            logger.debug(
                f"Not a new {timeframe} candle or already processed, skipping",
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
        """Check if timestamp is at a new candle boundary (deprecated).

        **Deprecated**: Use CandleDetector.is_new_candle() directly for new code.
        This method is kept for backward compatibility.

        Args:
            timestamp: Timestamp to check
            timeframe: Timeframe string (e.g., "15m", "1h")
            window_seconds: Grace period (ignored, uses CandleDetector.window_seconds)

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
        # PR-072: Delegate to CandleDetector
        result: bool = self.candle_detector.is_new_candle(timestamp, timeframe)
        return result
