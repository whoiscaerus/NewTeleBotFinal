"""
Technical indicators for Fib-RSI strategy.

This module implements core technical indicators used by the strategy:
- RSI (Relative Strength Index)
- ROC (Rate of Change)
- ATR (Average True Range)
- Fibonacci support/resistance levels

All calculations follow standard technical analysis formulas and are
designed for fast computation on streaming data.

Example:
    >>> from backend.app.strategy.fib_rsi.indicators import RSICalculator
    >>> prices = [1.0850, 1.0855, 1.0860, 1.0865, 1.0870]
    >>> rsi_values = RSICalculator.calculate(prices, period=14)
    >>> print(rsi_values[-1])  # Latest RSI value
"""

import statistics


class RSICalculator:
    """Relative Strength Index calculator.

    RSI measures momentum and oscillates between 0 and 100.
    > 70 = overbought (sell signal)
    < 30 = oversold (buy signal)
    """

    @staticmethod
    def calculate(prices: list[float], period: int = 14) -> list[float]:
        """Calculate RSI values.

        Args:
            prices: List of close prices
            period: RSI period (default: 14)

        Returns:
            list: RSI values (same length as prices)

        Raises:
            ValueError: If prices < 2 or period < 2

        Example:
            >>> prices = [1.0, 1.1, 1.05, 1.15, 1.2, 1.1]
            >>> rsi = RSICalculator.calculate(prices, period=2)
            >>> len(rsi)
            6
        """
        if len(prices) < 2:
            raise ValueError(f"Need at least 2 prices, got {len(prices)}")
        if period < 2:
            raise ValueError(f"Period must be >= 2, got {period}")

        rsi_values = []
        deltas = [prices[i + 1] - prices[i] for i in range(len(prices) - 1)]

        # First period has no RSI (set to 50.0)
        for i in range(period):
            rsi_values.append(50.0)

        if len(deltas) < period:
            return rsi_values

        # Calculate average gain/loss for first period
        gains = [max(d, 0) for d in deltas[:period]]
        losses = [abs(min(d, 0)) for d in deltas[:period]]

        avg_gain = statistics.mean(gains) if gains else 0
        avg_loss = statistics.mean(losses) if losses else 0

        # Calculate RSI for first valid period
        if avg_loss == 0:
            rsi = 100.0 if avg_gain > 0 else 50.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

        rsi_values.append(rsi)

        # Calculate remaining RSI values using smoothed averages
        for i in range(period + 1, len(deltas) + 1):
            delta = deltas[i - 1]
            gain = max(delta, 0)
            loss = abs(min(delta, 0))

            avg_gain = (avg_gain * (period - 1) + gain) / period
            avg_loss = (avg_loss * (period - 1) + loss) / period

            if avg_loss == 0:
                rsi = 100.0 if avg_gain > 0 else 50.0
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))

            rsi_values.append(rsi)

        return rsi_values

    @staticmethod
    def is_oversold(rsi: float, threshold: float = 30.0) -> bool:
        """Check if RSI indicates oversold condition.

        Args:
            rsi: RSI value (0-100)
            threshold: Oversold threshold (default: 30)

        Returns:
            bool: True if RSI < threshold

        Example:
            >>> RSICalculator.is_oversold(25.0)
            True
            >>> RSICalculator.is_oversold(35.0)
            False
        """
        return rsi < threshold

    @staticmethod
    def is_overbought(rsi: float, threshold: float = 70.0) -> bool:
        """Check if RSI indicates overbought condition.

        Args:
            rsi: RSI value (0-100)
            threshold: Overbought threshold (default: 70)

        Returns:
            bool: True if RSI > threshold

        Example:
            >>> RSICalculator.is_overbought(75.0)
            True
            >>> RSICalculator.is_overbought(65.0)
            False
        """
        return rsi > threshold


class ROCCalculator:
    """Rate of Change indicator calculator.

    ROC measures momentum and can be positive (bullish) or negative (bearish).
    Positive ROC = uptrend, Negative ROC = downtrend.
    """

    @staticmethod
    def calculate(prices: list[float], period: int = 14) -> list[float]:
        """Calculate ROC values.

        Args:
            prices: List of close prices
            period: ROC period (default: 14)

        Returns:
            list: ROC values as percentage change (same length as prices)

        Raises:
            ValueError: If prices < 2 or period < 1

        Example:
            >>> prices = [1.0, 1.05, 1.1, 1.08, 1.12]
            >>> roc = ROCCalculator.calculate(prices, period=2)
            >>> len(roc)
            5
        """
        if len(prices) < 2:
            raise ValueError(f"Need at least 2 prices, got {len(prices)}")
        if period < 1:
            raise ValueError(f"Period must be >= 1, got {period}")

        roc_values = []

        for i in range(len(prices)):
            if i < period:
                roc_values.append(0.0)
            else:
                prev_price = prices[i - period]
                if prev_price == 0:
                    roc_values.append(0.0)
                else:
                    roc = ((prices[i] - prev_price) / prev_price) * 100
                    roc_values.append(roc)

        return roc_values

    @staticmethod
    def is_positive_roc(roc: float, threshold: float = 0.0) -> bool:
        """Check if ROC is positive (bullish).

        Args:
            roc: ROC value (percentage)
            threshold: Positive threshold (default: 0.0)

        Returns:
            bool: True if ROC > threshold

        Example:
            >>> ROCCalculator.is_positive_roc(1.5)
            True
            >>> ROCCalculator.is_positive_roc(-0.5)
            False
        """
        return roc > threshold

    @staticmethod
    def is_negative_roc(roc: float, threshold: float = 0.0) -> bool:
        """Check if ROC is negative (bearish).

        Args:
            roc: ROC value (percentage)
            threshold: Negative threshold (default: 0.0)

        Returns:
            bool: True if ROC < threshold

        Example:
            >>> ROCCalculator.is_negative_roc(-1.5)
            True
            >>> ROCCalculator.is_negative_roc(0.5)
            False
        """
        return roc < threshold


class ATRCalculator:
    """Average True Range calculator for volatility measurement.

    ATR measures volatility and is used for position sizing and SL placement.
    Higher ATR = higher volatility = wider stops needed.
    """

    @staticmethod
    def calculate(
        highs: list[float],
        lows: list[float],
        closes: list[float],
        period: int = 14,
    ) -> list[float]:
        """Calculate ATR values.

        Args:
            highs: List of high prices
            lows: List of low prices
            closes: List of close prices
            period: ATR period (default: 14)

        Returns:
            list: ATR values (same length as input lists)

        Raises:
            ValueError: If lists have different lengths or < 2 elements

        Example:
            >>> highs = [1.1, 1.15, 1.12, 1.18]
            >>> lows = [1.05, 1.08, 1.07, 1.1]
            >>> closes = [1.08, 1.12, 1.1, 1.15]
            >>> atr = ATRCalculator.calculate(highs, lows, closes, period=2)
            >>> len(atr)
            4
        """
        if len(highs) != len(lows) or len(lows) != len(closes):
            raise ValueError("highs, lows, and closes must have same length")
        if len(highs) < 2:
            raise ValueError(f"Need at least 2 candles, got {len(highs)}")
        if period < 1:
            raise ValueError(f"Period must be >= 1, got {period}")

        # Calculate True Range for each candle
        true_ranges = []
        for i in range(len(highs)):
            if i == 0:
                tr = highs[i] - lows[i]
            else:
                tr1 = highs[i] - lows[i]
                tr2 = abs(highs[i] - closes[i - 1])
                tr3 = abs(lows[i] - closes[i - 1])
                tr = max(tr1, tr2, tr3)

            true_ranges.append(tr)

        # Calculate ATR
        atr_values = []
        for i in range(len(true_ranges)):
            if i < period - 1:
                atr_values.append(0.0)
            elif i == period - 1:
                atr = statistics.mean(true_ranges[: i + 1])
                atr_values.append(atr)
            else:
                prev_atr = atr_values[i - 1]
                current_tr = true_ranges[i]
                atr = (prev_atr * (period - 1) + current_tr) / period
                atr_values.append(atr)

        return atr_values

    @staticmethod
    def get_volatility_level(atr: float, atr_high: float = 100.0) -> str:
        """Classify volatility based on ATR value.

        Args:
            atr: ATR value
            atr_high: Threshold for high volatility (default: 100)

        Returns:
            str: Volatility level ("low", "medium", or "high")

        Example:
            >>> ATRCalculator.get_volatility_level(50.0)
            "medium"
        """
        if atr < atr_high / 3:
            return "low"
        elif atr < (2 * atr_high / 3):
            return "medium"
        else:
            return "high"


class FibonacciAnalyzer:
    """Fibonacci support/resistance level analyzer.

    Uses recent swing highs and lows to calculate Fibonacci retracement levels.
    These levels often act as support/resistance in trending markets.
    """

    @staticmethod
    def find_swing_high(
        candles: list[dict[str, float]],
        window: int = 20,
    ) -> tuple[float, int]:
        """Find recent swing high within lookback window.

        Args:
            candles: List of dicts with 'high' key
            window: Lookback window in candles (default: 20)

        Returns:
            tuple: (swing_high_price, candle_index) where index is distance from now

        Raises:
            ValueError: If candles empty or window < 2

        Example:
            >>> candles = [{"high": 1.1}, {"high": 1.15}, {"high": 1.12}]
            >>> high, idx = FibonacciAnalyzer.find_swing_high(candles, window=3)
            >>> high
            1.15
        """
        if len(candles) == 0:
            raise ValueError("candles list is empty")
        if window < 2:
            raise ValueError(f"window must be >= 2, got {window}")

        lookback = min(window, len(candles))
        recent = candles[-lookback:]

        max_high = 0
        max_idx = 0
        for i, candle in enumerate(recent):
            if candle.get("high", 0) > max_high:
                max_high = candle["high"]
                max_idx = len(candles) - lookback + i

        return max_high, len(candles) - 1 - max_idx

    @staticmethod
    def find_swing_low(
        candles: list[dict[str, float]],
        window: int = 20,
    ) -> tuple[float, int]:
        """Find recent swing low within lookback window.

        Args:
            candles: List of dicts with 'low' key
            window: Lookback window in candles (default: 20)

        Returns:
            tuple: (swing_low_price, candle_index) where index is distance from now

        Raises:
            ValueError: If candles empty or window < 2

        Example:
            >>> candles = [{"low": 1.05}, {"low": 1.02}, {"low": 1.03}]
            >>> low, idx = FibonacciAnalyzer.find_swing_low(candles, window=3)
            >>> low
            1.02
        """
        if len(candles) == 0:
            raise ValueError("candles list is empty")
        if window < 2:
            raise ValueError(f"window must be >= 2, got {window}")

        lookback = min(window, len(candles))
        recent = candles[-lookback:]

        min_low = float("inf")
        min_idx = 0
        for i, candle in enumerate(recent):
            if candle.get("low", float("inf")) < min_low:
                min_low = candle["low"]
                min_idx = len(candles) - lookback + i

        return min_low, len(candles) - 1 - min_idx

    @staticmethod
    def calculate_levels(
        swing_high: float,
        swing_low: float,
        fib_ratios: list[float] = None,
    ) -> dict[str, float]:
        """Calculate Fibonacci retracement levels.

        Args:
            swing_high: Recent swing high price
            swing_low: Recent swing low price
            fib_ratios: List of Fib ratios (default: [0.236, 0.382, 0.5, 0.618, 0.786, 1.0])

        Returns:
            dict: Level name -> price mapping

        Raises:
            ValueError: If swing_high <= swing_low or ratios invalid

        Example:
            >>> levels = FibonacciAnalyzer.calculate_levels(1.2, 1.0)
            >>> levels["0.618"]
            1.1236
        """
        if swing_high <= swing_low:
            raise ValueError(
                f"swing_high ({swing_high}) must be > swing_low ({swing_low})"
            )

        if fib_ratios is None:
            fib_ratios = [0.236, 0.382, 0.5, 0.618, 0.786, 1.0]

        for ratio in fib_ratios:
            if not (0 <= ratio <= 1):
                raise ValueError(f"Fib ratio must be 0-1, got {ratio}")

        range_size = swing_high - swing_low
        levels = {}

        for ratio in fib_ratios:
            level = swing_high - (range_size * ratio)
            levels[str(ratio)] = round(level, 5)

        return levels

    @staticmethod
    def find_nearest_level(
        price: float,
        levels: dict[str, float],
        tolerance_pips: float = 50,
    ) -> str:
        """Find nearest Fibonacci level to current price.

        Args:
            price: Current price
            levels: Dict of levels (from calculate_levels)
            tolerance_pips: Max distance to be considered "near" level (default: 50)

        Returns:
            str: Nearest level key, or empty string if none within tolerance

        Example:
            >>> levels = {"0.618": 1.1236, "0.5": 1.1, "0.382": 1.0764}
            >>> nearest = FibonacciAnalyzer.find_nearest_level(1.1235, levels, 50)
            >>> nearest
            "0.618"
        """
        min_distance = float("inf")
        nearest_level = ""

        for level_key, level_price in levels.items():
            distance_pips = abs(price - level_price) * 10000
            if distance_pips < min_distance and distance_pips <= tolerance_pips:
                min_distance = distance_pips
                nearest_level = level_key

        return nearest_level

    @staticmethod
    def is_price_near_level(
        price: float,
        level: float,
        tolerance_pips: float = 50,
    ) -> bool:
        """Check if price is near a specific Fibonacci level.

        Args:
            price: Current price
            level: Fib level price
            tolerance_pips: Max distance tolerance (default: 50)

        Returns:
            bool: True if price within tolerance of level

        Example:
            >>> FibonacciAnalyzer.is_price_near_level(1.1235, 1.1236, 50)
            True
        """
        distance_pips = abs(price - level) * 10000
        return distance_pips <= tolerance_pips
