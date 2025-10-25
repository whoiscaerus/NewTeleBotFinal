"""
Fib-RSI strategy parameters and configuration.

This module defines all configurable parameters for the Fib-RSI trading strategy
including technical indicator settings, risk management parameters, and market
hours validation options.

Parameters:
    RSI period, overbought/oversold thresholds
    ROC period and momentum threshold
    Fibonacci levels for support/resistance
    Risk per trade, reward:risk ratio, minimum stop distance
    Market hours validation toggle

Example:
    >>> from backend.app.strategy.fib_rsi.params import StrategyParams
    >>>
    >>> params = StrategyParams()
    >>> params.validate()
    >>>
    >>> rsi_config = params.get_rsi_config()
    >>> print(rsi_config["period"])  # 14
    >>>
    >>> risk_config = params.get_risk_config()
    >>> print(risk_config["rr_ratio"])  # 2.0
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StrategyParams:
    """Fib-RSI strategy parameters with validation.

    Uses RSI crossing state machine:
    - SHORT pattern: RSI crosses above 70, waits for RSI ≤ 40
    - LONG pattern: RSI crosses below 40, waits for RSI ≥ 70

    Attributes:
        rsi_period: Period for RSI calculation (default: 14)
        rsi_overbought: RSI threshold for SHORT trigger (default: 70.0)
        rsi_oversold: RSI threshold for LONG trigger (default: 40.0)
        roc_period: Period for Price/RSI ROC calculation (default: 24)
        roc_threshold: ROC threshold for momentum confirmation (default: 0.5)
        fib_levels: Fibonacci retracement levels (default: [0.236, 0.382, 0.5, 0.618, 0.786, 1.0])
        risk_per_trade: Percentage of account risk per trade (default: 0.02 = 2%)
        rr_ratio: Reward:Risk ratio (default: 2.0)
        min_stop_distance_points: Minimum SL distance from entry in points (default: 10)
        check_market_hours: Whether to validate market hours (default: True)
        signal_timeout_seconds: Max age for signal generation (default: 300)
        max_signals_per_hour: Rate limit for signals (default: 5)
    """

    # RSI Indicator parameters
    rsi_period: int = 14
    rsi_overbought: float = 70.0  # SHORT pattern trigger: RSI crosses above 70
    rsi_oversold: float = 40.0  # LONG pattern trigger: RSI crosses below 40

    # ROC Indicator parameters
    roc_period: int = 24  # Price ROC and RSI ROC period
    roc_threshold: float = 0.5

    # Fibonacci parameters
    fib_levels: list[float] = field(
        default_factory=lambda: [0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
    )
    fib_proximity_pips: int = 50  # How close price must be to Fib level

    # Risk management
    risk_per_trade: float = 0.02  # 2% of account
    rr_ratio: float = 3.25  # Reward:Risk ratio (matches DemoNoStochRSI)
    min_stop_distance_points: int = 10  # Minimum SL distance

    # Market hours validation
    check_market_hours: bool = True

    # Signal generation
    signal_timeout_seconds: int = 300
    max_signals_per_hour: int = 5

    # ATR multiplier for SL placement
    atr_multiplier_stop: float = 1.5
    atr_multiplier_tp: float = 1.0

    # Swing detection parameters
    swing_lookback_bars: int = 20
    min_bars_for_analysis: int = 30

    def validate(self) -> bool:
        """Validate all parameters are within acceptable ranges.

        Returns:
            True if validation passes

        Raises:
            ValueError: If any parameter is invalid
            TypeError: If parameter type is incorrect

        Example:
            >>> params = StrategyParams(rsi_period=20)
            >>> result = params.validate()  # Returns True
            >>> assert result is True
            >>>
            >>> params = StrategyParams(rsi_period=-5)
            >>> params.validate()  # Raises ValueError
        """
        errors: list[str] = []

        # RSI validation
        if not isinstance(self.rsi_period, int) or self.rsi_period < 2:
            errors.append("rsi_period must be int >= 2")
        if not (0 < self.rsi_overbought < 100):
            errors.append("rsi_overbought must be between 0 and 100")
        if not (0 < self.rsi_oversold < 100):
            errors.append("rsi_oversold must be between 0 and 100")
        if self.rsi_overbought <= self.rsi_oversold:
            errors.append("rsi_overbought must be > rsi_oversold")

        # ROC validation
        roc_period_valid = isinstance(self.roc_period, int) and self.roc_period >= 2
        if not roc_period_valid:
            errors.append("roc_period must be int >= 2")

        roc_threshold_valid = isinstance(self.roc_threshold, int | float)
        if not roc_threshold_valid:
            errors.append("roc_threshold must be numeric")

        # Fibonacci validation - check type first
        fib_is_valid_list: bool = (
            isinstance(self.fib_levels, list) and len(self.fib_levels) > 0
        )
        if not fib_is_valid_list:
            errors.append("fib_levels must be non-empty list")

        if fib_is_valid_list:
            for level in self.fib_levels:
                if not (0 <= level <= 1):
                    errors.append(f"fib_levels must be between 0 and 1, got {level}")

        # Risk management validation
        if not (0 < self.risk_per_trade < 1):
            errors.append("risk_per_trade must be between 0 and 1 (e.g., 0.02 for 2%)")
        if not (0.5 <= self.rr_ratio <= 10):
            errors.append("rr_ratio must be between 0.5 and 10")
        if (
            not isinstance(self.min_stop_distance_points, int)
            or self.min_stop_distance_points < 1
        ):
            errors.append("min_stop_distance_points must be int >= 1")

        # Market hours validation
        check_market_hours_valid = isinstance(self.check_market_hours, bool)
        if not check_market_hours_valid:
            errors.append("check_market_hours must be boolean")

        # Timeout validation
        if (
            not isinstance(self.signal_timeout_seconds, int)
            or self.signal_timeout_seconds < 1
        ):
            errors.append("signal_timeout_seconds must be int >= 1")

        # Rate limit validation
        if (
            not isinstance(self.max_signals_per_hour, int)
            or self.max_signals_per_hour < 1
        ):
            errors.append("max_signals_per_hour must be int >= 1")

        # ATR multiplier validation
        if (
            not isinstance(self.atr_multiplier_stop, int | float)
            or self.atr_multiplier_stop < 0.1
        ):
            errors.append("atr_multiplier_stop must be numeric >= 0.1")

        # Swing lookback validation
        if (
            not isinstance(self.swing_lookback_bars, int)
            or self.swing_lookback_bars < 2
        ):
            errors.append("swing_lookback_bars must be int >= 2")
        if (
            not isinstance(self.min_bars_for_analysis, int)
            or self.min_bars_for_analysis < 10
        ):
            errors.append("min_bars_for_analysis must be int >= 10")
        if self.min_bars_for_analysis <= self.swing_lookback_bars:
            errors.append("min_bars_for_analysis must be > swing_lookback_bars")

        if errors:
            raise ValueError(f"Parameter validation failed: {'; '.join(errors)}")

        return True

    def get_rsi_config(self) -> dict[str, Any]:
        """Get RSI-specific configuration.

        Returns:
            dict: RSI configuration with period, overbought, oversold thresholds

        Example:
            >>> params = StrategyParams()
            >>> config = params.get_rsi_config()
            >>> config["overbought"]
            70.0
        """
        return {
            "period": self.rsi_period,
            "overbought": self.rsi_overbought,
            "oversold": self.rsi_oversold,
        }

    def get_roc_config(self) -> dict[str, Any]:
        """Get ROC-specific configuration.

        Returns:
            dict: ROC configuration with period and threshold

        Example:
            >>> params = StrategyParams()
            >>> config = params.get_roc_config()
            >>> config["period"]
            14
        """
        return {
            "period": self.roc_period,
            "threshold": self.roc_threshold,
        }

    def get_fib_config(self) -> dict[str, Any]:
        """Get Fibonacci-specific configuration.

        Returns:
            dict: Fibonacci configuration with levels and proximity threshold

        Example:
            >>> params = StrategyParams()
            >>> config = params.get_fib_config()
            >>> len(config["levels"])
            6
        """
        return {
            "levels": self.fib_levels,
            "proximity_pips": self.fib_proximity_pips,
        }

    def get_risk_config(self) -> dict[str, Any]:
        """Get risk management configuration.

        Returns:
            dict: Risk config with risk_per_trade, rr_ratio, min_stop_distance

        Example:
            >>> params = StrategyParams()
            >>> config = params.get_risk_config()
            >>> config["rr_ratio"]
            2.0
        """
        return {
            "risk_per_trade": self.risk_per_trade,
            "rr_ratio": self.rr_ratio,
            "min_stop_distance_points": self.min_stop_distance_points,
            "atr_multiplier_stop": self.atr_multiplier_stop,
            "atr_multiplier_tp": self.atr_multiplier_tp,
        }

    def get_market_hours_config(self) -> dict[str, Any]:
        """Get market hours configuration.

        Returns:
            dict: Market hours validation setting

        Example:
            >>> params = StrategyParams()
            >>> config = params.get_market_hours_config()
            >>> config["enabled"]
            True
        """
        return {
            "enabled": self.check_market_hours,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert all parameters to dictionary.

        Returns:
            dict: All parameters as key-value pairs

        Example:
            >>> params = StrategyParams(rr_ratio=3.0)
            >>> d = params.to_dict()
            >>> d["rr_ratio"]
            3.0
        """
        return {
            "rsi_period": self.rsi_period,
            "rsi_overbought": self.rsi_overbought,
            "rsi_oversold": self.rsi_oversold,
            "roc_period": self.roc_period,
            "roc_threshold": self.roc_threshold,
            "fib_levels": self.fib_levels,
            "fib_proximity_pips": self.fib_proximity_pips,
            "risk_per_trade": self.risk_per_trade,
            "rr_ratio": self.rr_ratio,
            "min_stop_distance_points": self.min_stop_distance_points,
            "check_market_hours": self.check_market_hours,
            "signal_timeout_seconds": self.signal_timeout_seconds,
            "max_signals_per_hour": self.max_signals_per_hour,
            "atr_multiplier_stop": self.atr_multiplier_stop,
            "atr_multiplier_tp": self.atr_multiplier_tp,
            "swing_lookback_bars": self.swing_lookback_bars,
            "min_bars_for_analysis": self.min_bars_for_analysis,
        }

    def __repr__(self) -> str:
        """Return string representation.

        Example:
            >>> params = StrategyParams()
            >>> print(params)
            StrategyParams(rsi_period=14, rr_ratio=2.0, risk_per_trade=0.02)
        """
        return (
            f"StrategyParams(rsi_period={self.rsi_period}, "
            f"rr_ratio={self.rr_ratio}, "
            f"risk_per_trade={self.risk_per_trade})"
        )
