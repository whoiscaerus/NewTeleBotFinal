"""
RSI Pattern Detection for Fib-RSI Strategy.

This module implements the RSI crossing pattern detection that matches DemoNoStochRSI:
- SHORT pattern: RSI crosses above 70, waits for RSI to fall below 40
- LONG pattern: RSI crosses below 40, waits for RSI to rise above 70

Each pattern can take up to 100 hours to complete and generates a setup
when the pattern is finished (RSI completes the journey).

Example:
    >>> detector = RSIPatternDetector(
    ...     rsi_high_threshold=70,
    ...     rsi_low_threshold=40,
    ...     completion_window_hours=100
    ... )
    >>> setup = detector.detect_setup(df, current_rsi)
    >>> if setup:
    ...     print(f"Found {setup['type']} setup: entry={setup['entry']}, SL={setup['stop_loss']}")
"""

import logging
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)


class RSIPatternDetector:
    """Detects RSI crossing patterns for Fib-RSI strategy.

    Tracks RSI threshold crossings and waits for pattern completion:
    - SHORT: RSI > 70 → waiting for RSI <= 40
    - LONG: RSI < 40 → waiting for RSI >= 70

    Attributes:
        rsi_high_threshold: RSI value for overbought (default 70)
        rsi_low_threshold: RSI value for oversold (default 40)
        completion_window_hours: Max hours to wait for pattern (default 100)
    """

    def __init__(
        self,
        rsi_high_threshold: float = 70.0,
        rsi_low_threshold: float = 40.0,
        completion_window_hours: int = 100,
    ):
        """Initialize pattern detector.

        Args:
            rsi_high_threshold: RSI overbought level (default 70)
            rsi_low_threshold: RSI oversold level (default 40)
            completion_window_hours: Max hours for pattern completion (default 100)
        """
        self.rsi_high_threshold = rsi_high_threshold
        self.rsi_low_threshold = rsi_low_threshold
        self.completion_window_hours = completion_window_hours

    def detect_short_setup(
        self,
        df: pd.DataFrame,
    ) -> Optional[dict[str, Any]]:
        """Detect completed SHORT setup (RSI > 70 then RSI <= 40).

        SHORT Pattern:
        1. Find where RSI crosses ABOVE 70
        2. Find highest price while RSI > 70
        3. Look forward (up to 100 hours) for RSI to fall <= 40
        4. Find lowest price when RSI <= 40
        5. Calculate Fibonacci levels

        Args:
            df: OHLCV DataFrame with RSI column (must have datetime index)

        Returns:
            dict: Setup with entry, SL, TP, prices, or None if no complete setup

        Raises:
            ValueError: If DataFrame invalid or missing RSI column
        """
        if df.empty or "rsi" not in df.columns:
            raise ValueError("DataFrame must have 'rsi' column and be non-empty")

        if len(df) < 2:
            return None

        window = df.copy()
        now = window.index[-1]

        # Find RSI crossings above 70
        for i in range(1, len(window)):
            prev_rsi = window["rsi"].iloc[i - 1]
            curr_rsi = window["rsi"].iloc[i]

            # SHORT pattern trigger: RSI crosses above 70
            if prev_rsi <= self.rsi_high_threshold < curr_rsi:
                rsi_high_start_time = window.index[i]
                rsi_high_start = curr_rsi

                logger.debug(
                    f"SHORT: RSI crossed above {self.rsi_high_threshold} at {rsi_high_start_time}, RSI={rsi_high_start:.2f}"
                )

                # Find highest price while RSI > 70
                rsi_high_period = window.loc[window.index[i] :][
                    window["rsi"] > self.rsi_high_threshold
                ]
                if rsi_high_period.empty:
                    logger.debug("SHORT: No period found where RSI > 70")
                    continue

                price_high = rsi_high_period["high"].max()
                price_high_time = rsi_high_period["high"].idxmax()

                logger.debug(
                    f"SHORT: Highest price {price_high:.5f} at {price_high_time}"
                )

                # Look for RSI to fall below 40 within completion window
                rsi_low_end_idx = None
                rsi_low_end_time = None

                for j in range(i + 1, len(window)):
                    elapsed_hours = (
                        window.index[j] - rsi_high_start_time
                    ).total_seconds() / 3600
                    if elapsed_hours > self.completion_window_hours:
                        break

                    if window["rsi"].iloc[j] <= self.rsi_low_threshold:
                        rsi_low_end_idx = j
                        rsi_low_end_time = window.index[j]
                        break

                if rsi_low_end_idx is None:
                    logger.debug(
                        f"SHORT: No RSI <= {self.rsi_low_threshold} within {self.completion_window_hours} hours"
                    )
                    continue

                # Find lowest price when RSI <= 40
                rsi_low_period = window.loc[window.index[rsi_low_end_idx] :][
                    window["rsi"] <= self.rsi_low_threshold
                ]
                if rsi_low_period.empty:
                    rsi_low_period = window.iloc[rsi_low_end_idx : rsi_low_end_idx + 1]

                price_low = rsi_low_period["low"].min()
                if pd.isna(price_low):
                    logger.debug("SHORT: No valid low price found")
                    continue

                price_low_time = rsi_low_period["low"].idxmin()
                rsi_low_end = window["rsi"].iloc[rsi_low_end_idx]

                logger.debug(
                    f"SHORT: Lowest price {price_low:.5f} at {price_low_time}, RSI={rsi_low_end:.2f}"
                )

                # Validate time and age
                time_diff_hours = (
                    price_low_time - price_high_time
                ).total_seconds() / 3600
                age_hours = (now - price_low_time).total_seconds() / 3600

                if time_diff_hours > self.completion_window_hours:
                    logger.debug(
                        f"SHORT: Time window exceeded {time_diff_hours:.1f}h > {self.completion_window_hours}h"
                    )
                    continue

                if price_high <= price_low:
                    logger.debug(
                        f"SHORT: Invalid Fib range: high={price_high} <= low={price_low}"
                    )
                    continue

                # Calculate Fibonacci levels
                fib_range = price_high - price_low
                entry_price = price_low + fib_range * 0.74
                stop_loss = price_high + fib_range * 0.27

                logger.debug(
                    f"SHORT: Fib calculation: range={fib_range:.5f}, entry={entry_price:.5f}, SL={stop_loss:.5f}"
                )

                return {
                    "type": "short",
                    "entry": entry_price,
                    "stop_loss": stop_loss,
                    "price_high": price_high,
                    "price_low": price_low,
                    "rsi_high_value": rsi_high_start,
                    "rsi_low_value": rsi_low_end,
                    "rsi_high_time": rsi_high_start_time,
                    "rsi_low_time": rsi_low_end_time,
                    "price_high_time": price_high_time,
                    "price_low_time": price_low_time,
                    "completion_time": price_low_time,
                    "setup_age_hours": age_hours,
                }

        return None

    def detect_long_setup(
        self,
        df: pd.DataFrame,
    ) -> Optional[dict[str, Any]]:
        """Detect completed LONG setup (RSI < 40 then RSI >= 70).

        LONG Pattern:
        1. Find where RSI crosses BELOW 40
        2. Find lowest price while RSI < 40
        3. Look forward (up to 100 hours) for RSI to rise >= 70
        4. Find highest price when RSI >= 70
        5. Calculate Fibonacci levels

        Args:
            df: OHLCV DataFrame with RSI column (must have datetime index)

        Returns:
            dict: Setup with entry, SL, TP, prices, or None if no complete setup

        Raises:
            ValueError: If DataFrame invalid or missing RSI column
        """
        if df.empty or "rsi" not in df.columns:
            raise ValueError("DataFrame must have 'rsi' column and be non-empty")

        if len(df) < 2:
            return None

        window = df.copy()
        now = window.index[-1]

        # Find RSI crossings below 40
        for i in range(1, len(window)):
            prev_rsi = window["rsi"].iloc[i - 1]
            curr_rsi = window["rsi"].iloc[i]

            # LONG pattern trigger: RSI crosses below 40
            if prev_rsi >= self.rsi_low_threshold > curr_rsi:
                rsi_low_start_time = window.index[i]
                rsi_low_start = curr_rsi

                logger.debug(
                    f"LONG: RSI crossed below {self.rsi_low_threshold} at {rsi_low_start_time}, RSI={rsi_low_start:.2f}"
                )

                # Find lowest price while RSI < 40
                rsi_low_period = window.loc[window.index[i] :][
                    window["rsi"] < self.rsi_low_threshold
                ]
                if rsi_low_period.empty:
                    logger.debug("LONG: No period found where RSI < 40")
                    continue

                price_low = rsi_low_period["low"].min()
                if pd.isna(price_low):
                    logger.debug("LONG: No valid low price found")
                    continue

                price_low_time = rsi_low_period["low"].idxmin()

                logger.debug(f"LONG: Lowest price {price_low:.5f} at {price_low_time}")

                # Look for RSI to rise above 70 within completion window
                rsi_high_end_idx = None
                rsi_high_end_time = None

                for j in range(i + 1, len(window)):
                    elapsed_hours = (
                        window.index[j] - rsi_low_start_time
                    ).total_seconds() / 3600
                    if elapsed_hours > self.completion_window_hours:
                        break

                    if window["rsi"].iloc[j] >= self.rsi_high_threshold:
                        rsi_high_end_idx = j
                        rsi_high_end_time = window.index[j]
                        break

                if rsi_high_end_idx is None:
                    logger.debug(
                        f"LONG: No RSI >= {self.rsi_high_threshold} within {self.completion_window_hours} hours"
                    )
                    continue

                # Find highest price when RSI >= 70
                rsi_high_period = window.loc[window.index[rsi_high_end_idx] :][
                    window["rsi"] >= self.rsi_high_threshold
                ]
                if rsi_high_period.empty:
                    rsi_high_period = window.iloc[
                        rsi_high_end_idx : rsi_high_end_idx + 1
                    ]

                price_high = rsi_high_period["high"].max()
                if pd.isna(price_high):
                    logger.debug("LONG: No valid high price found")
                    continue

                price_high_time = rsi_high_period["high"].idxmax()
                rsi_high_end = window["rsi"].iloc[rsi_high_end_idx]

                logger.debug(
                    f"LONG: Highest price {price_high:.5f} at {price_high_time}, RSI={rsi_high_end:.2f}"
                )

                # Validate time and age
                time_diff_hours = (
                    price_high_time - price_low_time
                ).total_seconds() / 3600
                age_hours = (now - price_high_time).total_seconds() / 3600

                if time_diff_hours > self.completion_window_hours:
                    logger.debug(
                        f"LONG: Time window exceeded {time_diff_hours:.1f}h > {self.completion_window_hours}h"
                    )
                    continue

                if price_high <= price_low:
                    logger.debug(
                        f"LONG: Invalid Fib range: high={price_high} <= low={price_low}"
                    )
                    continue

                # Calculate Fibonacci levels
                fib_range = price_high - price_low
                entry_price = price_high - fib_range * 0.74
                stop_loss = price_low - fib_range * 0.27

                logger.debug(
                    f"LONG: Fib calculation: range={fib_range:.5f}, entry={entry_price:.5f}, SL={stop_loss:.5f}"
                )

                return {
                    "type": "long",
                    "entry": entry_price,
                    "stop_loss": stop_loss,
                    "price_high": price_high,
                    "price_low": price_low,
                    "rsi_high_value": rsi_high_end,
                    "rsi_low_value": rsi_low_start,
                    "rsi_high_time": rsi_high_end_time,
                    "rsi_low_time": rsi_low_start_time,
                    "price_high_time": price_high_time,
                    "price_low_time": price_low_time,
                    "completion_time": price_high_time,
                    "setup_age_hours": age_hours,
                }

        return None

    def detect_setup(self, df: pd.DataFrame) -> Optional[dict[str, Any]]:
        """Detect any completed setup (SHORT or LONG).

        Checks for both SHORT and LONG patterns, preferring the most recent.

        Args:
            df: OHLCV DataFrame with RSI column

        Returns:
            dict: Most recent completed setup, or None if no setup

        Raises:
            ValueError: If DataFrame invalid
        """
        # Try SHORT first
        short_setup = self.detect_short_setup(df)
        if short_setup:
            return short_setup

        # Try LONG second
        long_setup = self.detect_long_setup(df)
        if long_setup:
            return long_setup

        return None
