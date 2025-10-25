"""
Fib-RSI strategy engine for signal generation.

This module implements the main strategy engine that orchestrates all components:
- Technical indicator calculation
- Signal detection (buy/sell criteria)
- Entry/SL/TP calculation
- Market hours validation
- Telemetry and logging

The engine is stateless and designed to work with streaming OHLC data.

Example:
    >>> from backend.app.strategy.fib_rsi.engine import StrategyEngine
    >>> from backend.app.strategy.fib_rsi.params import StrategyParams
    >>> from backend.app.trading.time import MarketCalendar
    >>> import pandas as pd
    >>> from datetime import datetime
    >>>
    >>> params = StrategyParams()
    >>> params.validate()
    >>> calendar = MarketCalendar()
    >>>
    >>> engine = StrategyEngine(params, calendar)
    >>>
    >>> df = pd.DataFrame({
    ...     'open': [1.0850, 1.0855, 1.0860],
    ...     'high': [1.0875, 1.0880, 1.0885],
    ...     'low': [1.0840, 1.0845, 1.0850],
    ...     'close': [1.0865, 1.0870, 1.0875],
    ...     'volume': [1000000, 1100000, 1200000]
    ... })
    >>>
    >>> signal = await engine.generate_signal(df, "EURUSD", datetime.utcnow())
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from backend.app.strategy.fib_rsi.indicators import (
    ATRCalculator,
    FibonacciAnalyzer,
    ROCCalculator,
    RSICalculator,
)
from backend.app.strategy.fib_rsi.params import StrategyParams
from backend.app.strategy.fib_rsi.pattern_detector import RSIPatternDetector
from backend.app.strategy.fib_rsi.schema import SignalCandidate
from backend.app.trading.time import MarketCalendar

# Configure logger
logger = logging.getLogger(__name__)


class StrategyEngine:
    """Fib-RSI trading strategy engine using RSI crossing patterns.

    Orchestrates signal generation from OHLC data using RSI crossing state machine:
    - Detects SHORT patterns: RSI crosses above 70, waits for ≤ 40
    - Detects LONG patterns: RSI crosses below 40, waits for ≥ 70
    - Integrates market hours validation and risk management
    - Uses Fibonacci retracement for entry/SL/TP calculation

    Attributes:
        params: Strategy parameters (RSI, ROC, Fib, risk settings)
        market_calendar: Market hours validator
        pattern_detector: RSI pattern detector (state machine)
        logger: Structured logger instance
        _last_signal_times: Track signal generation for rate limiting
    """

    def __init__(
        self,
        params: StrategyParams,
        market_calendar: MarketCalendar,
        logger: logging.Logger | None = None,
    ):
        """Initialize strategy engine.

        Args:
            params: StrategyParams instance with all configuration
            market_calendar: MarketCalendar instance for market hours checking
            logger: Optional logger instance (creates one if not provided)

        Raises:
            ValueError: If params fails validation

        Example:
            >>> params = StrategyParams()
            >>> params.validate()
            >>> calendar = MarketCalendar()
            >>> engine = StrategyEngine(params, calendar)
        """
        params.validate()

        self.params = params
        self.market_calendar = market_calendar
        self.logger = logger or logging.getLogger(__name__)
        self._last_signal_times: dict[str, list[datetime]] = {}

        # Initialize pattern detector with RSI thresholds and completion window
        self.pattern_detector = RSIPatternDetector(
            rsi_high_threshold=params.rsi_overbought,
            rsi_low_threshold=params.rsi_oversold,
            completion_window_hours=100,
        )

    async def generate_signal(
        self,
        df: pd.DataFrame,
        instrument: str,
        current_time: datetime,
    ) -> SignalCandidate | None:
        """Generate trading signal from OHLC data.

        This is the main method that orchestrates the entire signal generation process:
        1. Validate input data
        2. Check market hours
        3. Calculate technical indicators
        4. Detect buy/sell signals
        5. Calculate entry/SL/TP
        6. Create SignalCandidate

        Args:
            df: DataFrame with columns ['open', 'high', 'low', 'close', 'volume']
            instrument: Trading symbol (e.g., "EURUSD", "GOLD")
            current_time: Current time for market hours validation (UTC)

        Returns:
            SignalCandidate if signal generated, None otherwise

        Raises:
            ValueError: If DataFrame invalid or instrument invalid

        Example:
            >>> import pandas as pd
            >>> df = pd.DataFrame({
            ...     'open': [1.0850, 1.0855, 1.0860],
            ...     'high': [1.0875, 1.0880, 1.0885],
            ...     'low': [1.0840, 1.0845, 1.0850],
            ...     'close': [1.0865, 1.0870, 1.0875],
            ...     'volume': [1000000, 1100000, 1200000]
            ... })
            >>> signal = await engine.generate_signal(df, "EURUSD", now)
            >>> if signal:
            ...     print(f"Generated {signal.side} signal at {signal.entry_price}")
        """
        start_time = time.time()

        try:
            # Step 1: Validate inputs
            self._validate_dataframe(df)
            if not instrument or len(instrument) < 2:
                raise ValueError(f"Invalid instrument: {instrument}")

            # Step 2: Check market hours
            if self.params.check_market_hours:
                is_open = await self._check_market_hours(instrument, current_time)
                if not is_open:
                    self.logger.debug(
                        "Market closed",
                        extra={
                            "instrument": instrument,
                            "time": current_time.isoformat(),
                        },
                    )
                    return None

            # Step 3: Check rate limiting
            if self._is_rate_limited(instrument):
                self.logger.debug(
                    "Rate limit exceeded for instrument",
                    extra={"instrument": instrument},
                )
                return None

            # Step 4: Calculate indicators
            indicators = await self._calculate_indicators(df)
            self.logger.debug(
                "Indicators calculated",
                extra={
                    "instrument": instrument,
                    "rsi": indicators.get("rsi", 0),
                    "roc": indicators.get("roc", 0),
                },
            )

            # Step 5: Detect setup using RSI pattern detector
            setup = await self._detect_setup(df, indicators)

            if not setup:
                return None

            # Step 6: Calculate prices using setup data (price extremes, not current)
            entry_price, stop_loss, take_profit = await self._calculate_entry_prices(
                setup,
                indicators,
            )

            # Step 7: Build signal
            signal = SignalCandidate(
                instrument=instrument,
                side=setup["side"],
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                confidence=setup.get("confidence", 0.80),
                timestamp=current_time,
                reason=setup.get("reason", "fib_rsi_pattern"),
                payload={
                    **indicators,
                    "pattern_type": setup["pattern_type"],
                    "price_high": setup.get("price_high"),
                    "price_low": setup.get("price_low"),
                },
            )

            signal.validate_price_relationships()

            self._record_signal_time(instrument)
            elapsed = time.time() - start_time
            self.logger.info(
                f"Signal generated: {signal.side} {instrument} ({setup['pattern_type']})",
                extra={
                    "instrument": instrument,
                    "side": signal.side,
                    "pattern": setup["pattern_type"],
                    "entry": entry_price,
                    "sl": stop_loss,
                    "tp": take_profit,
                    "price_high": setup.get("price_high"),
                    "price_low": setup.get("price_low"),
                    "elapsed_ms": int(elapsed * 1000),
                },
            )

            return signal

        except ValueError as e:
            self.logger.error(
                f"Validation error: {e}",
                extra={"instrument": instrument, "error": str(e)},
            )
            raise

        except Exception as e:
            elapsed = time.time() - start_time
            self.logger.error(
                f"Error generating signal: {e}",
                extra={
                    "instrument": instrument,
                    "error": str(e),
                    "elapsed_ms": int(elapsed * 1000),
                },
                exc_info=True,
            )
            raise

    async def _check_market_hours(
        self,
        instrument: str,
        timestamp: datetime,
    ) -> bool:
        """Check if market is open for instrument.

        Args:
            instrument: Trading symbol
            timestamp: Time to check (UTC)

        Returns:
            bool: True if market is open

        Example:
            >>> is_open = await engine._check_market_hours("EURUSD", now)
        """
        try:
            return self.market_calendar.is_market_open(instrument, timestamp)
        except Exception as e:
            self.logger.warning(
                f"Market hours check failed: {e}",
                extra={"instrument": instrument, "error": str(e)},
            )
            return True  # Fail open - generate signal if unsure

    async def _calculate_indicators(
        self,
        df: pd.DataFrame,
    ) -> dict[str, Any]:
        """Calculate all technical indicators.

        Args:
            df: OHLCV DataFrame

        Returns:
            dict: Indicators including RSI, ROC, ATR, Fib levels, etc.

        Raises:
            ValueError: If calculation fails
        """
        try:
            closes = df["close"].tolist()
            highs = df["high"].tolist()
            lows = df["low"].tolist()

            # RSI
            rsi_values = RSICalculator.calculate(closes, self.params.rsi_period)
            current_rsi = rsi_values[-1]

            # ROC
            roc_values = ROCCalculator.calculate(closes, self.params.roc_period)
            current_roc = roc_values[-1]

            # ATR
            atr_values = ATRCalculator.calculate(highs, lows, closes, period=14)
            current_atr = atr_values[-1]

            # Fibonacci levels
            swing_high, _ = FibonacciAnalyzer.find_swing_high(
                [{"high": h, "low": low} for h, low in zip(highs, lows, strict=False)],
                window=self.params.swing_lookback_bars,
            )
            swing_low, _ = FibonacciAnalyzer.find_swing_low(
                [{"high": h, "low": low} for h, low in zip(highs, lows, strict=False)],
                window=self.params.swing_lookback_bars,
            )

            fib_levels = FibonacciAnalyzer.calculate_levels(swing_high, swing_low)

            return {
                "rsi": current_rsi,
                "rsi_period": self.params.rsi_period,
                "roc": current_roc,
                "roc_period": self.params.roc_period,
                "atr": current_atr,
                "swing_high": swing_high,
                "swing_low": swing_low,
                "fib_levels": fib_levels,
                "current_price": closes[-1],
                "volume": df["volume"].iloc[-1],
            }

        except Exception as e:
            raise ValueError(f"Indicator calculation failed: {e}") from e

    async def _detect_setup(
        self,
        df: pd.DataFrame,
        indicators: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Detect RSI pattern setup.

        Detects SHORT patterns (RSI > 70 then ≤ 40) and LONG patterns
        (RSI < 40 then ≥ 70) using RSI crossing detection.

        Args:
            df: OHLCV DataFrame with at least 2 rows for crossing detection
            indicators: Calculated indicators

        Returns:
            dict with setup details if pattern detected:
                - side: "buy" or "sell"
                - pattern_type: "short_pattern" or "long_pattern"
                - price_high: highest price during pattern
                - price_low: lowest price during pattern
                - confidence: pattern confidence score
                - reason: pattern detection reason
            None if no pattern detected

        Example:
            >>> setup = await engine._detect_setup(df, indicators)
            >>> if setup and setup['side'] == 'sell':
            ...     print(f"SHORT pattern detected at {setup['price_high']}")
        """
        try:
            setup = self.pattern_detector.detect_setup(df, indicators)

            if not setup:
                self.logger.debug("No RSI pattern setup detected")
                return None

            self.logger.debug(
                f"RSI pattern setup detected: {setup['pattern_type']}",
                extra={
                    "pattern": setup["pattern_type"],
                    "side": setup["side"],
                    "price_high": setup.get("price_high"),
                    "price_low": setup.get("price_low"),
                },
            )

            return setup

        except Exception as e:
            self.logger.error(
                f"Pattern detection failed: {e}",
                extra={"error": str(e)},
                exc_info=True,
            )
            return None

    async def _calculate_entry_prices(
        self,
        setup: dict[str, Any],
        indicators: dict[str, Any],
    ) -> tuple:
        """Calculate entry, stop loss, and take profit using Fibonacci levels.

        For SELL (SHORT pattern):
            Entry = price_low + (price_high - price_low) × 0.74
            SL = price_high + (price_high - price_low) × 0.27
            TP = Entry - (Entry - SL) × R:R ratio

        For BUY (LONG pattern):
            Entry = price_high - (price_high - price_low) × 0.74
            SL = price_low - (price_high - price_low) × 0.27
            TP = Entry + (SL - Entry) × R:R ratio

        Args:
            setup: Setup data from pattern detector
            indicators: Calculated indicators

        Returns:
            tuple: (entry_price, stop_loss, take_profit)

        Raises:
            ValueError: If price calculation invalid
        """
        try:
            price_high = setup["price_high"]
            price_low = setup["price_low"]
            side = setup["side"]
            range_size = price_high - price_low

            # Validate price range
            if range_size <= 0:
                raise ValueError(
                    f"Invalid price range: high={price_high}, low={price_low}"
                )

            if side == "sell":
                # SHORT pattern: Use Fibonacci 0.74 and 0.27 multipliers
                entry_price = price_low + (range_size * 0.74)
                stop_loss = price_high + (range_size * 0.27)
                # Risk = entry - sl
                risk = entry_price - stop_loss
                take_profit = entry_price - (risk * self.params.rr_ratio)

            else:  # buy
                # LONG pattern: Use Fibonacci 0.74 and 0.27 multipliers
                entry_price = price_high - (range_size * 0.74)
                stop_loss = price_low - (range_size * 0.27)
                # Risk = sl - entry
                risk = stop_loss - entry_price
                take_profit = entry_price + (risk * self.params.rr_ratio)

            # Validate price relationships
            if side == "sell":
                if not (stop_loss > entry_price > take_profit):
                    raise ValueError(
                        f"Invalid price relationship for SELL: "
                        f"SL={stop_loss} > Entry={entry_price} > TP={take_profit}"
                    )
            else:
                if not (take_profit > entry_price > stop_loss):
                    raise ValueError(
                        f"Invalid price relationship for BUY: "
                        f"TP={take_profit} > Entry={entry_price} > SL={stop_loss}"
                    )

            self.logger.debug(
                "Entry prices calculated",
                extra={
                    "side": side,
                    "entry": entry_price,
                    "sl": stop_loss,
                    "tp": take_profit,
                    "risk": abs(entry_price - stop_loss),
                },
            )

            return entry_price, stop_loss, take_profit

        except Exception as e:
            self.logger.error(
                f"Entry price calculation failed: {e}",
                extra={"error": str(e), "setup": setup},
                exc_info=True,
            )
            raise ValueError(f"Entry price calculation failed: {e}") from e

    def _is_rate_limited(self, instrument: str) -> bool:
        """Check if instrument is rate limited.

        Args:
            instrument: Trading symbol

        Returns:
            bool: True if rate limit exceeded
        """
        if instrument not in self._last_signal_times:
            self._last_signal_times[instrument] = []

        now = datetime.utcnow()
        one_hour_ago = now - timedelta(hours=1)

        # Remove signals older than 1 hour
        self._last_signal_times[instrument] = [
            t for t in self._last_signal_times[instrument] if t > one_hour_ago
        ]

        return (
            len(self._last_signal_times[instrument]) >= self.params.max_signals_per_hour
        )

    def _record_signal_time(self, instrument: str) -> None:
        """Record signal generation time for rate limiting.

        Args:
            instrument: Trading symbol
        """
        if instrument not in self._last_signal_times:
            self._last_signal_times[instrument] = []

        self._last_signal_times[instrument].append(datetime.utcnow())

    @staticmethod
    def _validate_dataframe(df: pd.DataFrame) -> None:
        """Validate DataFrame has required columns and data.

        Args:
            df: DataFrame to validate

        Raises:
            ValueError: If validation fails
        """
        required_columns = {"open", "high", "low", "close", "volume"}
        if not required_columns.issubset(df.columns):
            raise ValueError(
                f"DataFrame missing required columns. "
                f"Need {required_columns}, have {set(df.columns)}"
            )

        if len(df) < 30:
            raise ValueError(f"Need at least 30 candles, got {len(df)}")

        # Check for NaN values
        if df[list(required_columns)].isna().any().any():
            raise ValueError("DataFrame contains NaN values")

        # Check for positive values
        for col in required_columns:
            if (df[col] <= 0).any():
                raise ValueError(f"Column {col} contains non-positive values")
