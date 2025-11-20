"""Strategy promotion pipeline with validation gating.

Promotes strategies through deployment stages:
    development → backtest → paper → live

Each promotion requires passing validation thresholds.

Example:
    >>> engine = PromotionEngine(
    ...     min_sharpe=1.0,
    ...     max_drawdown=15.0,
    ...     min_win_rate=55.0,
    ...     min_trades=30,
    ... )
    >>> # After walk-forward validation...
    >>> success = await engine.promote_to_backtest(
    ...     strategy_name="fib_rsi",
    ...     validation_result=wf_result,
    ...     db_session=session,
    ... )
    >>> assert strategy.status == StrategyStatus.backtest
"""

import logging
from datetime import datetime

from prometheus_client import Counter
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.research.models import StrategyMetadata, StrategyStatus
from backend.app.research.walkforward import WalkForwardValidationResult

logger = logging.getLogger(__name__)

# Telemetry
promotion_attempt_total = Counter(
    "promotion_attempt_total",
    "Total strategy promotion attempts",
    ["strategy", "from_status", "to_status", "result"],
)


class PromotionEngine:
    """Strategy promotion pipeline with validation gating.

    Enforces thresholds for each promotion stage:
    - development → backtest: Pass walk-forward validation
    - backtest → paper: Manual approval
    - paper → live: Pass paper trading thresholds

    Example:
        >>> engine = PromotionEngine(
        ...     min_sharpe=1.0,
        ...     max_drawdown=15.0,
        ...     min_win_rate=55.0,
        ...     min_trades=30,
        ... )
        >>> success = await engine.promote_to_backtest(
        ...     strategy_name="fib_rsi",
        ...     validation_result=wf_result,
        ...     db_session=session,
        ... )
    """

    def __init__(
        self,
        min_sharpe: float = 1.0,
        max_drawdown: float = 15.0,
        min_win_rate: float = 55.0,
        min_trades: int = 30,
        min_paper_days: int = 30,
        min_paper_trades: int = 20,
    ):
        """Initialize promotion engine with thresholds.

        Args:
            min_sharpe: Minimum Sharpe ratio for backtest promotion
            max_drawdown: Maximum drawdown % for backtest promotion
            min_win_rate: Minimum win rate % for backtest promotion
            min_trades: Minimum trade count for backtest promotion
            min_paper_days: Minimum paper trading days for live promotion
            min_paper_trades: Minimum paper trades for live promotion
        """
        self.min_sharpe = min_sharpe
        self.max_drawdown = max_drawdown
        self.min_win_rate = min_win_rate
        self.min_trades = min_trades
        self.min_paper_days = min_paper_days
        self.min_paper_trades = min_paper_trades

        logger.info(
            f"PromotionEngine initialized: Sharpe≥{min_sharpe}, "
            f"DD≤{max_drawdown}%, WR≥{min_win_rate}%, Trades≥{min_trades}"
        )

    async def promote_to_backtest(
        self,
        strategy_name: str,
        validation_result: WalkForwardValidationResult,
        db_session: AsyncSession,
    ) -> bool:
        """Promote strategy from development to backtest status.

        Requires passing walk-forward validation thresholds.

        Args:
            strategy_name: Strategy to promote
            validation_result: Walk-forward validation results
            db_session: Database session

        Returns:
            True if promoted, False if rejected

        Raises:
            ValueError: If strategy not found or already promoted
        """
        logger.info(f"Attempting backtest promotion: {strategy_name}")

        # Load strategy metadata
        strategy = await self._get_strategy(strategy_name, db_session)

        if strategy.status != StrategyStatus.development:
            raise ValueError(
                f"Strategy {strategy_name} is {strategy.status.value}, "
                "expected development"
            )

        # Check thresholds
        passed = self._check_backtest_thresholds(validation_result)

        if passed:
            # Promote to backtest
            strategy.status = StrategyStatus.backtest
            strategy.backtest_sharpe = validation_result.overall_sharpe
            strategy.backtest_max_dd = validation_result.overall_max_dd
            strategy.backtest_win_rate = validation_result.overall_win_rate
            strategy.backtest_total_trades = validation_result.overall_total_trades
            strategy.updated_at = datetime.utcnow()

            # Record promotion attempt
            promotion_record = {
                "timestamp": datetime.utcnow().isoformat(),
                "from_status": "development",
                "to_status": "backtest",
                "result": "approved",
                "metrics": {
                    "sharpe": validation_result.overall_sharpe,
                    "max_dd": validation_result.overall_max_dd,
                    "win_rate": validation_result.overall_win_rate,
                    "total_trades": validation_result.overall_total_trades,
                },
                "run_id": validation_result.run_id,
            }
            strategy.promotion_history.append(promotion_record)

            await db_session.commit()

            logger.info(f"Strategy {strategy_name} promoted to backtest")

            promotion_attempt_total.labels(
                strategy=strategy_name,
                from_status="development",
                to_status="backtest",
                result="approved",
            ).inc()

            return True
        else:
            # Rejected
            rejection_record = {
                "timestamp": datetime.utcnow().isoformat(),
                "from_status": "development",
                "to_status": "backtest",
                "result": "rejected",
                "reason": self._get_rejection_reason(validation_result),
                "metrics": {
                    "sharpe": validation_result.overall_sharpe,
                    "max_dd": validation_result.overall_max_dd,
                    "win_rate": validation_result.overall_win_rate,
                    "total_trades": validation_result.overall_total_trades,
                },
                "run_id": validation_result.run_id,
            }
            strategy.promotion_history.append(rejection_record)

            await db_session.commit()

            logger.warning(
                f"Strategy {strategy_name} rejected for backtest: "
                f"{rejection_record['reason']}"
            )

            promotion_attempt_total.labels(
                strategy=strategy_name,
                from_status="development",
                to_status="backtest",
                result="rejected",
            ).inc()

            return False

    async def promote_to_paper(
        self,
        strategy_name: str,
        db_session: AsyncSession,
    ) -> bool:
        """Promote strategy from backtest to paper trading.

        Manual approval step (no automatic thresholds).

        Args:
            strategy_name: Strategy to promote
            db_session: Database session

        Returns:
            True if promoted

        Raises:
            ValueError: If strategy not in backtest status
        """
        logger.info(f"Promoting to paper trading: {strategy_name}")

        strategy = await self._get_strategy(strategy_name, db_session)

        if strategy.status != StrategyStatus.backtest:
            raise ValueError(
                f"Strategy {strategy_name} is {strategy.status.value}, "
                "expected backtest"
            )

        # Promote to paper
        strategy.status = StrategyStatus.paper
        strategy.paper_start_date = datetime.utcnow()
        strategy.updated_at = datetime.utcnow()

        promotion_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "from_status": "backtest",
            "to_status": "paper",
            "result": "approved",
        }
        strategy.promotion_history.append(promotion_record)

        await db_session.commit()

        logger.info(f"Strategy {strategy_name} promoted to paper trading")

        promotion_attempt_total.labels(
            strategy=strategy_name,
            from_status="backtest",
            to_status="paper",
            result="approved",
        ).inc()

        return True

    async def promote_to_live(
        self,
        strategy_name: str,
        db_session: AsyncSession,
    ) -> bool:
        """Promote strategy from paper to live trading.

        Requires minimum paper trading duration and trade count.

        Args:
            strategy_name: Strategy to promote
            db_session: Database session

        Returns:
            True if promoted, False if rejected

        Raises:
            ValueError: If strategy not in paper status
        """
        logger.info(f"Attempting live promotion: {strategy_name}")

        strategy = await self._get_strategy(strategy_name, db_session)

        if strategy.status != StrategyStatus.paper:
            raise ValueError(
                f"Strategy {strategy_name} is {strategy.status.value}, "
                "expected paper"
            )

        # Check paper trading requirements
        if strategy.paper_start_date is None:
            raise ValueError(f"Strategy {strategy_name} has no paper start date")

        paper_days = (datetime.utcnow() - strategy.paper_start_date).days
        paper_trades = strategy.paper_trade_count or 0

        passed = (
            paper_days >= self.min_paper_days and paper_trades >= self.min_paper_trades
        )

        if passed:
            # Promote to live
            strategy.status = StrategyStatus.live
            strategy.paper_end_date = datetime.utcnow()
            strategy.live_start_date = datetime.utcnow()
            strategy.updated_at = datetime.utcnow()

            promotion_record = {
                "timestamp": datetime.utcnow().isoformat(),
                "from_status": "paper",
                "to_status": "live",
                "result": "approved",
                "metrics": {
                    "paper_days": paper_days,
                    "paper_trades": paper_trades,
                    "paper_pnl": strategy.paper_pnl,
                },
            }
            strategy.promotion_history.append(promotion_record)

            await db_session.commit()

            logger.info(f"Strategy {strategy_name} promoted to live")

            promotion_attempt_total.labels(
                strategy=strategy_name,
                from_status="paper",
                to_status="live",
                result="approved",
            ).inc()

            return True
        else:
            logger.warning(
                f"Strategy {strategy_name} rejected for live: "
                f"paper_days={paper_days} (need {self.min_paper_days}), "
                f"paper_trades={paper_trades} (need {self.min_paper_trades})"
            )

            promotion_attempt_total.labels(
                strategy=strategy_name,
                from_status="paper",
                to_status="live",
                result="rejected",
            ).inc()

            return False

    def _check_backtest_thresholds(self, result: WalkForwardValidationResult) -> bool:
        """Check if validation result passes thresholds."""
        return bool(
            result.overall_sharpe >= self.min_sharpe
            and result.overall_max_dd <= self.max_drawdown
            and result.overall_win_rate >= self.min_win_rate
            and result.overall_total_trades >= self.min_trades
        )

    def _get_rejection_reason(self, result: WalkForwardValidationResult) -> str:
        """Generate human-readable rejection reason."""
        reasons = []

        if result.overall_sharpe < self.min_sharpe:
            reasons.append(f"Sharpe {result.overall_sharpe:.2f} < {self.min_sharpe}")

        if result.overall_max_dd > self.max_drawdown:
            reasons.append(
                f"Max DD {result.overall_max_dd:.1f}% > {self.max_drawdown}%"
            )

        if result.overall_win_rate < self.min_win_rate:
            reasons.append(
                f"Win rate {result.overall_win_rate:.1f}% < {self.min_win_rate}%"
            )

        if result.overall_total_trades < self.min_trades:
            reasons.append(f"Trades {result.overall_total_trades} < {self.min_trades}")

        return "; ".join(reasons)

    async def _get_strategy(
        self, strategy_name: str, db_session: AsyncSession
    ) -> StrategyMetadata:
        """Load strategy metadata from database."""
        from sqlalchemy import select

        result = await db_session.execute(
            select(StrategyMetadata).where(StrategyMetadata.name == strategy_name)
        )
        strategy = result.scalar_one_or_none()

        if strategy is None:
            raise ValueError(f"Strategy {strategy_name} not found")

        return strategy
