"""Backtesting framework for strategy validation.

Provides reproducible offline backtests that run strategies with the same code paths
used in live trading. Ensures strategy parity between backtesting and production.

Architecture:
    1. Data adapters: Load historical data from CSV/Parquet
    2. Runner: Execute strategies deterministically with historical data
    3. Report: Generate performance metrics matching live analytics (PR-052/053)
    4. Metrics: Track backtesting operations via Prometheus

Key Features:
    - Strategy parity: Same code paths as live trading
    - Deterministic: Reproducible results from same data
    - Metrics parity: Identical metrics to live analytics
    - Multiple data sources: CSV, Parquet, database
    - Export formats: HTML, CSV, JSON

Example:
    >>> from backend.app.backtest.runner import BacktestRunner
    >>> from backend.app.backtest.adapters import CSVAdapter
    >>>
    >>> adapter = CSVAdapter("data/GOLD_15M.csv")
    >>> runner = BacktestRunner(strategy="fib_rsi", data_source=adapter)
    >>> report = await runner.run(start="2024-01-01", end="2024-12-31")
    >>> report.to_html("results.html")
"""

__version__ = "1.0.0"
