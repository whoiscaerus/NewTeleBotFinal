"""Candle detection and timing utilities for signal generation.

Provides precise 15-min (or other timeframe) candle boundary detection with
drift tolerance to handle timing variations in real-world systems.

Key Features:
    - New candle detection with configurable window
    - Duplicate signal prevention within same candle
    - Multi-timeframe support (15m, 1h, 4h, 1d)
    - Timezone-aware handling

Example:
    >>> from backend.app.strategy.candles import CandleDetector
    >>> detector = CandleDetector(window_seconds=60)
    >>>
    >>> # Check if timestamp is at new candle boundary
    >>> is_new = detector.is_new_candle(datetime.utcnow(), "15m")
    >>>
    >>> # Prevent duplicates within same candle
    >>> if detector.should_process_candle("GOLD", "15m", datetime.utcnow()):
    ...     # Process signal
    ...     pass
"""

import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)


class CandleDetector:
    """Detects new candle boundaries and prevents duplicate processing.

    Attributes:
        window_seconds: Grace period for boundary detection (drift tolerance)
        _processed_candles: Cache of (instrument, timeframe, candle_timestamp)
    """

    def __init__(self, window_seconds: int | None = None):
        """Initialize candle detector.

        Args:
            window_seconds: Grace period in seconds (default: from CANDLE_CHECK_WINDOW env)

        Example:
            >>> detector = CandleDetector(window_seconds=60)
        """
        self.window_seconds = window_seconds or int(
            os.getenv("CANDLE_CHECK_WINDOW", "60")
        )

        # Track processed candles to prevent duplicates: (instrument, tf, candle_ts) -> timestamp
        self._processed_candles: dict[tuple[str, str, datetime], datetime] = {}

        logger.info(
            "CandleDetector initialized",
            extra={"window_seconds": self.window_seconds},
        )

    def is_new_candle(
        self,
        timestamp: datetime,
        timeframe: str,
    ) -> bool:
        """Check if timestamp is at a new candle boundary.

        Uses modulo arithmetic to determine if timestamp falls within the
        configured window of a candle boundary (e.g., 00:00, 00:15, 00:30, 00:45
        for 15-min candles).

        Args:
            timestamp: Timestamp to check (UTC)
            timeframe: Timeframe string (e.g., "15m", "1h", "4h", "1d")

        Returns:
            True if timestamp is within window of a candle boundary

        Raises:
            ValueError: If timeframe format is unsupported

        Example:
            >>> detector = CandleDetector(window_seconds=60)
            >>>
            >>> # At 10:15:05 (5 seconds after 15m boundary)
            >>> detector.is_new_candle(datetime(2025, 1, 1, 10, 15, 5), "15m")
            True
            >>>
            >>> # At 10:17:30 (mid-candle, 2.5 min after boundary)
            >>> detector.is_new_candle(datetime(2025, 1, 1, 10, 17, 30), "15m")
            False
            >>>
            >>> # At 10:00:55 (55 seconds after boundary, within 60s window)
            >>> detector.is_new_candle(datetime(2025, 1, 1, 10, 0, 55), "15m")
            True
        """
        # Parse timeframe to get interval in minutes
        interval_minutes = self._parse_timeframe(timeframe)

        # Convert to seconds since epoch
        total_seconds = int(timestamp.timestamp())

        # Calculate interval in seconds
        interval_seconds = interval_minutes * 60

        # Calculate seconds within current candle
        seconds_in_candle = total_seconds % interval_seconds

        # Check if within window of boundary
        is_boundary = seconds_in_candle <= self.window_seconds

        if is_boundary:
            logger.debug(
                f"New candle detected at {timestamp.isoformat()}",
                extra={
                    "timeframe": timeframe,
                    "seconds_in_candle": seconds_in_candle,
                    "window_seconds": self.window_seconds,
                },
            )

        return is_boundary

    def should_process_candle(
        self,
        instrument: str,
        timeframe: str,
        timestamp: datetime,
    ) -> bool:
        """Check if candle should be processed (new boundary + not duplicate).

        Combines new candle detection with duplicate prevention to ensure
        each candle is processed exactly once.

        Args:
            instrument: Trading instrument (e.g., "GOLD", "EURUSD")
            timeframe: Timeframe string (e.g., "15m", "1h")
            timestamp: Current timestamp (UTC)

        Returns:
            True if this is a new candle that hasn't been processed yet

        Example:
            >>> detector = CandleDetector(window_seconds=60)
            >>>
            >>> # First call at boundary
            >>> detector.should_process_candle("GOLD", "15m", datetime(2025, 1, 1, 10, 15, 5))
            True
            >>>
            >>> # Second call at same candle (10 seconds later)
            >>> detector.should_process_candle("GOLD", "15m", datetime(2025, 1, 1, 10, 15, 15))
            False  # Duplicate prevented
            >>>
            >>> # Different instrument, same candle
            >>> detector.should_process_candle("EURUSD", "15m", datetime(2025, 1, 1, 10, 15, 5))
            True  # Different instrument, can process
        """
        # Check if at new candle boundary
        if not self.is_new_candle(timestamp, timeframe):
            return False

        # Get candle start timestamp
        candle_start = self.get_candle_start(timestamp, timeframe)

        # Check if we've already processed this candle
        cache_key = (instrument, timeframe, candle_start)

        if cache_key in self._processed_candles:
            logger.debug(
                "Duplicate candle detected, skipping",
                extra={
                    "instrument": instrument,
                    "timeframe": timeframe,
                    "candle_start": candle_start.isoformat(),
                    "previous_process_time": self._processed_candles[
                        cache_key
                    ].isoformat(),
                },
            )
            return False

        # Mark as processed
        self._processed_candles[cache_key] = timestamp

        # Clean up old entries (keep only last 100 candles)
        if len(self._processed_candles) > 1000:
            self._cleanup_old_candles()

        logger.info(
            "New candle ready for processing",
            extra={
                "instrument": instrument,
                "timeframe": timeframe,
                "candle_start": candle_start.isoformat(),
                "timestamp": timestamp.isoformat(),
            },
        )

        return True

    def get_candle_start(
        self,
        timestamp: datetime,
        timeframe: str,
    ) -> datetime:
        """Get the start timestamp of the candle containing the given timestamp.

        Args:
            timestamp: Any timestamp within the candle
            timeframe: Timeframe string (e.g., "15m", "1h")

        Returns:
            Start timestamp of the candle (floor)

        Example:
            >>> detector = CandleDetector()
            >>>
            >>> # 10:17:35 falls in the 10:15-10:30 candle
            >>> start = detector.get_candle_start(datetime(2025, 1, 1, 10, 17, 35), "15m")
            >>> print(start)  # 2025-01-01 10:15:00
        """
        interval_minutes = self._parse_timeframe(timeframe)
        interval_seconds = interval_minutes * 60

        # Floor to interval
        total_seconds = int(timestamp.timestamp())
        candle_seconds = (total_seconds // interval_seconds) * interval_seconds

        return datetime.utcfromtimestamp(candle_seconds)

    def clear_cache(self) -> None:
        """Clear processed candles cache.

        Useful for testing or manual resets.

        Example:
            >>> detector = CandleDetector()
            >>> detector.should_process_candle("GOLD", "15m", datetime.utcnow())
            >>> detector.clear_cache()  # Reset
        """
        self._processed_candles.clear()
        logger.info("Candle cache cleared")

    def _parse_timeframe(self, timeframe: str) -> int:
        """Parse timeframe string to interval in minutes.

        Args:
            timeframe: Timeframe string (e.g., "15m", "1h", "4h", "1d")

        Returns:
            Interval in minutes

        Raises:
            ValueError: If timeframe format is invalid

        Example:
            >>> detector = CandleDetector()
            >>> detector._parse_timeframe("15m")
            15
            >>> detector._parse_timeframe("1h")
            60
            >>> detector._parse_timeframe("4h")
            240
            >>> detector._parse_timeframe("1d")
            1440
        """
        if timeframe.endswith("m"):
            return int(timeframe[:-1])
        elif timeframe.endswith("h"):
            return int(timeframe[:-1]) * 60
        elif timeframe.endswith("d"):
            return int(timeframe[:-1]) * 1440
        else:
            raise ValueError(
                f"Unsupported timeframe format: {timeframe}. "
                f"Expected format: <number><unit> where unit is m, h, or d"
            )

    def _cleanup_old_candles(self) -> None:
        """Remove oldest candles from cache to prevent memory bloat.

        Keeps only the 500 most recent candles.
        """
        if len(self._processed_candles) <= 500:
            return

        # Sort by process time and keep 500 most recent
        sorted_items = sorted(
            self._processed_candles.items(),
            key=lambda x: x[1],  # Sort by timestamp
            reverse=True,
        )

        # Keep only 500 most recent
        self._processed_candles = dict(sorted_items[:500])

        logger.debug(
            "Cleaned up old candles from cache",
            extra={"remaining": len(self._processed_candles)},
        )


# Singleton instance for convenience
_detector: CandleDetector | None = None


def get_candle_detector() -> CandleDetector:
    """Get global candle detector instance.

    Returns:
        Singleton CandleDetector instance

    Example:
        >>> from backend.app.strategy.candles import get_candle_detector
        >>> detector = get_candle_detector()
        >>> is_new = detector.is_new_candle(datetime.utcnow(), "15m")
    """
    global _detector
    if _detector is None:
        _detector = CandleDetector()
    return _detector
