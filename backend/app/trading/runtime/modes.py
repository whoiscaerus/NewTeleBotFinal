"""Paper trading mode and order routing.

Routes orders based on strategy status:
- development/backtest: Rejected (not ready)
- paper: Virtual fills with simulated slippage
- live: Real broker execution

Example:
    >>> engine = PaperTradingEngine(initial_balance=10000.0)
    >>> # On entry signal
    >>> position = await engine.execute_entry(
    ...     signal=signal,
    ...     strategy_name="fib_rsi",
    ...     db_session=session,
    ... )
    >>> # Later on exit
    >>> pnl = await engine.execute_exit(
    ...     position_id=position.id,
    ...     exit_price=1955.50,
    ...     reason="take_profit",
    ...     db_session=session,
    ... )
"""

import logging
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from prometheus_client import Counter, Gauge
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.research.models import (
    ResearchPaperTrade,
    StrategyMetadata,
    StrategyStatus,
)

logger = logging.getLogger(__name__)

# Telemetry
paper_orders_total = Counter(
    "paper_orders_total",
    "Total paper trading orders",
    ["strategy", "symbol", "status", "reason"],
)

paper_portfolio_balance_gauge = Gauge(
    "paper_portfolio_balance",
    "Paper trading portfolio balance",
    ["strategy"],
)


class TradingMode(str, Enum):
    """Trading execution mode."""

    paper = "paper"
    live = "live"


class PaperTradingEngine:
    """Virtual portfolio with simulated order execution.

    Simulates fills with slippage, maintains virtual balance, tracks PnL.
    Separate ledger from live trades for safety.

    Example:
        >>> engine = PaperTradingEngine(initial_balance=10000.0)
        >>> position = await engine.execute_entry(
        ...     signal=signal,
        ...     strategy_name="fib_rsi",
        ...     db_session=session,
        ... )
        >>> assert position.side == 0  # Buy
        >>> # Later...
        >>> pnl = await engine.execute_exit(
        ...     position_id=position.id,
        ...     exit_price=1955.50,
        ...     reason="take_profit",
        ...     db_session=session,
        ... )
    """

    def __init__(
        self,
        initial_balance: float = 10000.0,
        slippage_pips: float = 2.0,
        pip_value: float = 10.0,
    ):
        """Initialize paper trading engine.

        Args:
            initial_balance: Starting virtual balance (USD)
            slippage_pips: Slippage applied to market orders (pips)
            pip_value: Value per pip for PnL calculation (USD/pip)
        """
        self.initial_balance = initial_balance
        self.slippage_pips = slippage_pips
        self.pip_value = pip_value

        logger.info(
            f"PaperTradingEngine initialized: "
            f"balance=${initial_balance}, slippage={slippage_pips} pips"
        )

    async def execute_entry(
        self,
        signal: Any,  # Signal object from PR-030
        strategy_name: str,
        db_session: AsyncSession,
        size: float = 1.0,
    ) -> ResearchPaperTrade:
        """Execute entry order with simulated fill.

        Args:
            signal: Entry signal (from signal generation)
            strategy_name: Strategy executing trade
            db_session: Database session
            size: Position size (lots)

        Returns:
            ResearchPaperTrade record with simulated fill

        Example:
            >>> position = await engine.execute_entry(
            ...     signal=signal,
            ...     strategy_name="fib_rsi",
            ...     db_session=session,
            ...     size=1.0,
            ... )
            >>> assert position.entry_price > signal.price  # Slippage applied
        """
        logger.info(
            f"Executing paper entry: {strategy_name} {signal.instrument} "
            f"{signal.side} @ {signal.price}"
        )

        # Apply slippage
        if signal.side == "buy" or signal.side == 0:
            # Buy: Slippage increases entry price
            fill_price = signal.price + (self.slippage_pips * 0.0001)
            side = 0
        else:
            # Sell: Slippage decreases entry price
            fill_price = signal.price - (self.slippage_pips * 0.0001)
            side = 1

        # Create paper trade record
        paper_trade = ResearchPaperTrade(
            id=str(uuid.uuid4()),
            strategy_name=strategy_name,
            signal_id=signal.id,
            symbol=signal.instrument,
            side=side,
            entry_price=fill_price,
            entry_time=datetime.utcnow(),
            size=size,
            slippage_applied=self.slippage_pips,
            fill_reason="market_order",
        )

        db_session.add(paper_trade)
        await db_session.commit()
        await db_session.refresh(paper_trade)

        logger.info(
            f"Paper entry filled: {paper_trade.id} @ {fill_price:.5f} "
            f"(slippage {self.slippage_pips} pips)"
        )

        paper_orders_total.labels(
            strategy=strategy_name,
            symbol=signal.instrument,
            status="filled",
            reason="market_order",
        ).inc()

        return paper_trade

    async def execute_exit(
        self,
        position_id: str,
        exit_price: float,
        reason: str,
        db_session: AsyncSession,
    ) -> float:
        """Execute exit order and calculate PnL.

        Args:
            position_id: ResearchPaperTrade ID to close
            exit_price: Exit price (before slippage)
            reason: Exit reason (take_profit, stop_loss, signal, manual)
            db_session: Database session

        Returns:
            Realized PnL (USD)

        Example:
            >>> pnl = await engine.execute_exit(
            ...     position_id=position.id,
            ...     exit_price=1955.50,
            ...     reason="take_profit",
            ...     db_session=session,
            ... )
            >>> assert pnl > 0  # Profitable trade
        """
        logger.info(f"Executing paper exit: {position_id} @ {exit_price}")

        # Load position
        from sqlalchemy import select

        result = await db_session.execute(
            select(ResearchPaperTrade).where(ResearchPaperTrade.id == position_id)
        )
        position = result.scalar_one_or_none()

        if position is None:
            raise ValueError(f"Position {position_id} not found")

        if position.exit_price is not None:
            raise ValueError(f"Position {position_id} already closed")

        # Apply slippage
        if position.side == 0:
            # Long: Slippage decreases exit price
            fill_price = exit_price - (self.slippage_pips * 0.0001)
        else:
            # Short: Slippage increases exit price
            fill_price = exit_price + (self.slippage_pips * 0.0001)

        # Calculate PnL
        if position.side == 0:
            # Long: PnL = (exit - entry) * size * pip_value / 0.0001
            pnl = (
                (fill_price - position.entry_price)
                * position.size
                * self.pip_value
                / 0.0001
            )
        else:
            # Short: PnL = (entry - exit) * size * pip_value / 0.0001
            pnl = (
                (position.entry_price - fill_price)
                * position.size
                * self.pip_value
                / 0.0001
            )

        # Update position
        position.exit_price = fill_price
        position.exit_time = datetime.utcnow()
        position.pnl = pnl
        position.fill_reason = reason

        await db_session.commit()

        logger.info(
            f"Paper exit filled: {position_id} @ {fill_price:.5f}, " f"PnL ${pnl:.2f}"
        )

        paper_orders_total.labels(
            strategy=position.strategy_name,
            symbol=position.symbol,
            status="filled",
            reason=reason,
        ).inc()

        # Update strategy paper metrics
        await self._update_strategy_paper_metrics(position.strategy_name, db_session)

        return pnl

    async def get_portfolio_state(
        self, strategy_name: str, db_session: AsyncSession
    ) -> dict[str, Any]:
        """Get current portfolio state for strategy.

        Args:
            strategy_name: Strategy to query
            db_session: Database session

        Returns:
            Portfolio state: balance, open_positions, closed_trades, total_pnl

        Example:
            >>> state = await engine.get_portfolio_state("fib_rsi", session)
            >>> print(f"Balance: ${state['balance']:.2f}")
            >>> print(f"Open: {len(state['open_positions'])}")
            >>> print(f"Total PnL: ${state['total_pnl']:.2f}")
        """
        from sqlalchemy import select

        # Get strategy metadata
        result = await db_session.execute(
            select(StrategyMetadata).where(StrategyMetadata.name == strategy_name)
        )
        strategy = result.scalar_one_or_none()

        if strategy is None:
            raise ValueError(f"Strategy {strategy_name} not found")

        # Get open positions
        result = await db_session.execute(
            select(ResearchPaperTrade).where(
                ResearchPaperTrade.strategy_name == strategy_name,
                ResearchPaperTrade.exit_price.is_(None),
            )
        )
        open_positions = result.scalars().all()

        # Get closed trades
        result = await db_session.execute(
            select(ResearchPaperTrade).where(
                ResearchPaperTrade.strategy_name == strategy_name,
                ResearchPaperTrade.exit_price.isnot(None),
            )
        )
        closed_trades = result.scalars().all()

        # Calculate total PnL
        total_pnl = sum(t.pnl for t in closed_trades if t.pnl is not None)

        # Current balance
        balance = self.initial_balance + total_pnl

        # Update gauge
        paper_portfolio_balance_gauge.labels(strategy=strategy_name).set(balance)

        return {
            "strategy_name": strategy_name,
            "balance": balance,
            "initial_balance": self.initial_balance,
            "total_pnl": total_pnl,
            "open_positions": len(open_positions),
            "closed_trades": len(closed_trades),
            "paper_start_date": strategy.paper_start_date,
        }

    async def _update_strategy_paper_metrics(
        self, strategy_name: str, db_session: AsyncSession
    ) -> None:
        """Update strategy paper trading metrics after trade close."""
        from sqlalchemy import select

        # Get strategy
        result = await db_session.execute(
            select(StrategyMetadata).where(StrategyMetadata.name == strategy_name)
        )
        strategy = result.scalar_one_or_none()

        if strategy is None:
            return

        # Get all closed paper trades
        result = await db_session.execute(
            select(ResearchPaperTrade).where(
                ResearchPaperTrade.strategy_name == strategy_name,
                ResearchPaperTrade.exit_price.isnot(None),
            )
        )
        closed_trades = result.scalars().all()

        # Update metrics
        strategy.paper_trade_count = len(closed_trades)
        strategy.paper_pnl = sum(t.pnl for t in closed_trades if t.pnl is not None)
        strategy.updated_at = datetime.utcnow()

        await db_session.commit()


class OrderRouter:
    """Routes orders to paper or live execution based on strategy status.

    Example:
        >>> router = OrderRouter()
        >>> mode = await router.get_trading_mode("fib_rsi", session)
        >>> if mode == TradingMode.paper:
        ...     engine = router.get_paper_engine()
        ...     await engine.execute_entry(signal, "fib_rsi", session)
    """

    def __init__(
        self,
        paper_engine: PaperTradingEngine | None = None,
        live_engine: Any | None = None,
    ):
        """Initialize order router.

        Args:
            paper_engine: Paper trading engine instance
            live_engine: Live trading engine instance (from PR-XXX)
        """
        self.paper_engine = paper_engine or PaperTradingEngine()
        self.live_engine = live_engine

        logger.info("OrderRouter initialized")

    async def get_trading_mode(
        self, strategy_name: str, db_session: AsyncSession
    ) -> TradingMode:
        """Determine trading mode for strategy.

        Args:
            strategy_name: Strategy to query
            db_session: Database session

        Returns:
            TradingMode.paper or TradingMode.live

        Raises:
            ValueError: If strategy not found or in development/backtest

        Example:
            >>> mode = await router.get_trading_mode("fib_rsi", session)
            >>> assert mode in [TradingMode.paper, TradingMode.live]
        """
        from sqlalchemy import select

        result = await db_session.execute(
            select(StrategyMetadata).where(StrategyMetadata.name == strategy_name)
        )
        strategy = result.scalar_one_or_none()

        if strategy is None:
            raise ValueError(f"Strategy {strategy_name} not found")

        if strategy.status == StrategyStatus.paper:
            return TradingMode.paper
        elif strategy.status == StrategyStatus.live:
            return TradingMode.live
        else:
            raise ValueError(
                f"Strategy {strategy_name} status is {strategy.status.value}, "
                "not ready for trading"
            )

    def get_paper_engine(self) -> PaperTradingEngine:
        """Get paper trading engine instance."""
        return self.paper_engine

    def get_live_engine(self) -> Any:
        """Get live trading engine instance."""
        if self.live_engine is None:
            raise ValueError("Live trading engine not configured")
        return self.live_engine
