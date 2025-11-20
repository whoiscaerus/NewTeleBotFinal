"""Strategy metadata models for research and promotion pipeline.

Tracks strategy status, validation results, and promotion history.
Supports walk-forward validation and paper→live promotion workflow.

Status Flow:
    development → backtest → paper → live

Each transition requires passing validation thresholds.
"""

import enum
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Enum, Float, Integer, String

from backend.app.core.db import Base


class StrategyStatus(enum.Enum):
    """Strategy deployment status.

    Workflow:
        1. development: Initial implementation, not validated
        2. backtest: Passed walk-forward validation, ready for paper trading
        3. paper: Paper trading in progress, collecting live data
        4. live: Approved for live trading with real capital
        5. retired: No longer active, archived

    Example:
        >>> strategy = StrategyMetadata(name="fib_rsi", status=StrategyStatus.development)
        >>> # After walk-forward validation passes...
        >>> strategy.status = StrategyStatus.backtest
        >>> # After paper trading succeeds...
        >>> strategy.status = StrategyStatus.live
    """

    development = "development"
    backtest = "backtest"
    paper = "paper"
    live = "live"
    retired = "retired"


class StrategyMetadata(Base):
    """Strategy metadata and status tracking.

    Stores current deployment status, validation results, and promotion history.
    Used by promotion pipeline to gate strategy deployment.

    Attributes:
        name: Strategy identifier (e.g., "fib_rsi", "ppo_gold")
        version: Version string (semantic versioning)
        status: Current deployment status
        created_at: Initial registration timestamp
        updated_at: Last status change timestamp
        backtest_sharpe: Sharpe ratio from walk-forward validation
        backtest_max_dd: Max drawdown % from validation
        backtest_win_rate: Win rate % from validation
        backtest_total_trades: Trade count from validation
        paper_start_date: Paper trading start date
        paper_end_date: Paper trading end date (if completed)
        paper_pnl: Paper trading total PnL
        paper_trade_count: Paper trades executed
        live_start_date: Live trading start date
        promotion_history: JSON array of promotion attempts
    """

    __tablename__ = "strategy_metadata"

    name = Column(String(50), primary_key=True)
    version = Column(String(20), nullable=False, default="1.0.0")
    status: Column[StrategyStatus] = Column(
        Enum(StrategyStatus),
        nullable=False,
        default=StrategyStatus.development,
        index=True,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Backtest validation results (walk-forward)
    backtest_sharpe = Column(Float, nullable=True)
    backtest_max_dd = Column(Float, nullable=True)  # Percentage
    backtest_win_rate = Column(Float, nullable=True)  # Percentage
    backtest_total_trades = Column(Integer, nullable=True)

    # Paper trading results
    paper_start_date = Column(DateTime, nullable=True)
    paper_end_date = Column(DateTime, nullable=True)
    paper_pnl = Column(Float, nullable=True)
    paper_trade_count = Column(Integer, nullable=True)

    # Live trading
    live_start_date = Column(DateTime, nullable=True)

    # Promotion history (audit trail)
    promotion_history = Column(JSON, nullable=False, default=list)

    def __repr__(self) -> str:
        return (
            f"<StrategyMetadata {self.name} v{self.version} status={self.status.value}>"
        )


class WalkForwardResult(Base):
    """Walk-forward validation detailed results.

    Stores per-fold metrics from K-fold time-series cross-validation.
    Used for detailed analysis and reporting.

    Attributes:
        id: Unique identifier
        strategy_name: Strategy being validated
        strategy_version: Version validated
        run_date: Validation execution date
        n_folds: Number of folds (K)
        fold_results: JSON array of per-fold metrics
        overall_sharpe: Average Sharpe across folds
        overall_max_dd: Worst drawdown across folds
        overall_win_rate: Average win rate across folds
        overall_total_trades: Total trades across all folds
        passed: Whether validation passed thresholds
    """

    __tablename__ = "walkforward_results"

    id = Column(String(36), primary_key=True)
    strategy_name = Column(String(50), nullable=False, index=True)
    strategy_version = Column(String(20), nullable=False)
    run_date = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Configuration
    n_folds = Column(Integer, nullable=False)

    # Per-fold results (JSON)
    fold_results = Column(JSON, nullable=False)

    # Aggregated metrics
    overall_sharpe = Column(Float, nullable=False)
    overall_max_dd = Column(Float, nullable=False)
    overall_win_rate = Column(Float, nullable=False)
    overall_total_trades = Column(Integer, nullable=False)

    # Validation outcome
    passed = Column(Integer, nullable=False, default=0)  # Boolean as int

    def __repr__(self) -> str:
        return f"<WalkForwardResult {self.strategy_name} v{self.strategy_version} {self.n_folds} folds passed={bool(self.passed)}>"


class ResearchPaperTrade(Base):
    """Paper trading ledger for research/walk-forward validation.

    Records simulated trades for paper trading mode during strategy validation.
    Separate from live trades and from user paper trading (PaperTrade in paper.models).

    NOTE: This is for research/strategy validation. User paper trading uses
    PaperTrade from backend.app.paper.models with different schema.

    Attributes:
        id: Unique trade identifier
        strategy_name: Strategy that generated signal
        symbol: Instrument traded
        side: 0=buy, 1=sell
        entry_price: Simulated entry price
        entry_time: Entry timestamp
        exit_price: Simulated exit price
        exit_time: Exit timestamp
        size: Position size (lots)
        pnl: Realized PnL (paper)
        slippage_applied: Slippage added (pips)
        fill_reason: "market", "limit", "stop"
        signal_id: Reference to original signal
    """

    __tablename__ = "research_paper_trades"

    id = Column(String(36), primary_key=True)
    strategy_name = Column(String(50), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(Integer, nullable=False)  # 0=buy, 1=sell
    entry_price = Column(Float, nullable=False)
    entry_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    exit_price = Column(Float, nullable=True)
    exit_time = Column(DateTime, nullable=True)
    size = Column(Float, nullable=False)
    pnl = Column(Float, nullable=True)
    slippage_applied = Column(Float, nullable=False, default=0.0)
    fill_reason = Column(String(20), nullable=False, default="market")
    signal_id = Column(String(36), nullable=True)

    def __repr__(self) -> str:
        return f"<ResearchPaperTrade {self.id} {self.symbol} {self.side} @ {self.entry_price}>"
