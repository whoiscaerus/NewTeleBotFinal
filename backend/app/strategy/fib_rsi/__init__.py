"""
Fib-RSI Trading Strategy Module.

Public API for the Fib-RSI strategy implementation.

Exports:
    StrategyParams: Configuration parameters
    StrategyEngine: Main strategy engine
    SignalCandidate: Signal data structure
    ExecutionPlan: Execution plan data structure
    RSICalculator: RSI indicator
    ROCCalculator: ROC indicator
    ATRCalculator: ATR indicator
    FibonacciAnalyzer: Fibonacci level analyzer

Example:
    >>> from backend.app.strategy.fib_rsi import StrategyEngine, StrategyParams
    >>> params = StrategyParams()
    >>> params.validate()
    >>> engine = StrategyEngine(params, calendar)
"""

from backend.app.strategy.fib_rsi.engine import StrategyEngine
from backend.app.strategy.fib_rsi.indicators import (
    ATRCalculator,
    FibonacciAnalyzer,
    ROCCalculator,
    RSICalculator,
)
from backend.app.strategy.fib_rsi.params import StrategyParams
from backend.app.strategy.fib_rsi.schema import ExecutionPlan, SignalCandidate

__all__ = [
    "StrategyParams",
    "StrategyEngine",
    "SignalCandidate",
    "ExecutionPlan",
    "RSICalculator",
    "ROCCalculator",
    "ATRCalculator",
    "FibonacciAnalyzer",
]
