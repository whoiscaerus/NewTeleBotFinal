"""
Paper Trading Engine

Simulates trade execution with configurable fill prices and slippage models.
"""

import random
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.observability.metrics import metrics
from backend.app.paper.models import PaperAccount, PaperPosition, PaperTrade, TradeSide


class FillPriceMode(Enum):
    """Fill price calculation mode"""

    MID = "mid"  # (bid + ask) / 2
    BID = "bid"  # Best bid (sell at this)
    ASK = "ask"  # Best ask (buy at this)


class SlippageMode(Enum):
    """Slippage simulation mode"""

    NONE = "none"  # No slippage
    FIXED = "fixed"  # Fixed pips/points
    RANDOM = "random"  # Random within range


class PaperTradingEngine:
    """
    Paper trading execution engine with configurable fill rules.

    Simulates order fills, tracks positions, calculates PnL.
    """

    def __init__(
        self,
        fill_mode: FillPriceMode = FillPriceMode.MID,
        slippage_mode: SlippageMode = SlippageMode.FIXED,
        slippage_pips: float = 2.0,
    ):
        """
        Initialize paper trading engine.

        Args:
            fill_mode: How to calculate fill price (mid/bid/ask)
            slippage_mode: How to simulate slippage (none/fixed/random)
            slippage_pips: Slippage in pips (for fixed) or max (for random)
        """
        self.fill_mode = fill_mode
        self.slippage_mode = slippage_mode
        self.slippage_pips = slippage_pips

    async def fill_order(
        self,
        db: AsyncSession,
        account: PaperAccount,
        symbol: str,
        side: TradeSide,
        volume: Decimal,
        bid: Decimal,
        ask: Decimal,
    ) -> PaperTrade:
        """
        Execute paper trade order.

        Args:
            db: Database session
            account: Paper account
            symbol: Trading symbol
            side: BUY or SELL
            volume: Order volume
            bid: Current bid price
            ask: Current ask price

        Returns:
            PaperTrade: Executed trade record

        Raises:
            ValueError: If insufficient balance

        Example:
            >>> trade = await engine.fill_order(
            ...     db, account, "GOLD", TradeSide.BUY, Decimal("1.0"),
            ...     Decimal("1950.00"), Decimal("1950.50")
            ... )
            >>> assert trade.entry_price == Decimal("1950.25")  # Mid price
        """
        # Calculate base fill price
        if self.fill_mode == FillPriceMode.MID:
            base_price = (bid + ask) / Decimal("2")
        elif self.fill_mode == FillPriceMode.BID:
            base_price = bid
        else:  # ASK
            base_price = ask

        # Apply slippage
        slippage = self._calculate_slippage(side)
        fill_price = base_price + Decimal(str(slippage))

        # Calculate required margin (simplified: full cost)
        required_margin = fill_price * volume
        if account.balance < required_margin:
            raise ValueError(
                f"Insufficient balance: {account.balance} < {required_margin}"
            )

        # Deduct from balance (for buy side, margin requirement)
        # Simplified: deduct full cost on entry, return on exit
        account.balance -= required_margin

        # Create trade record
        trade = PaperTrade(
            account_id=account.id,
            symbol=symbol,
            side=side,
            volume=volume,
            entry_price=fill_price,
            slippage=Decimal(str(abs(slippage))),
            filled_at=datetime.utcnow(),
        )
        db.add(trade)

        # Create or update position
        await self._update_position(db, account, symbol, side, volume, fill_price)

        # Update account equity
        await self._update_account_equity(db, account)

        await db.commit()
        # await db.refresh(trade)

        # Telemetry
        metrics.paper_fills_total.labels(symbol=symbol, side=side.value).inc()

        return trade

    async def close_position(
        self,
        db: AsyncSession,
        account: PaperAccount,
        position: PaperPosition,
        bid: Decimal,
        ask: Decimal,
    ) -> PaperTrade:
        """
        Close an open paper position.

        Args:
            db: Database session
            account: Paper account
            position: Position to close
            bid: Current bid price
            ask: Current ask price

        Returns:
            PaperTrade: Closed trade with realized PnL

        Example:
            >>> trade = await engine.close_position(db, account, position,
            ...     Decimal("1960.00"), Decimal("1960.50"))
            >>> assert trade.realized_pnl > 0  # Profitable
        """
        # Calculate exit price (opposite side of entry)
        exit_side = TradeSide.SELL if position.side == TradeSide.BUY else TradeSide.BUY

        if self.fill_mode == FillPriceMode.MID:
            base_price = (bid + ask) / Decimal("2")
        elif self.fill_mode == FillPriceMode.BID:
            base_price = bid
        else:  # ASK
            base_price = ask

        # Apply slippage
        slippage = self._calculate_slippage(exit_side)
        exit_price = base_price + Decimal(str(slippage))

        # Calculate realized PnL
        if position.side == TradeSide.BUY:
            pnl = (exit_price - position.entry_price) * position.volume
        else:
            pnl = (position.entry_price - exit_price) * position.volume

        # Update balance
        account.balance += position.entry_price * position.volume  # Return margin
        account.balance += pnl  # Add/subtract profit/loss

        # Create exit trade record
        trade = PaperTrade(
            account_id=account.id,
            symbol=position.symbol,
            side=exit_side,
            volume=position.volume,
            entry_price=position.entry_price,
            exit_price=exit_price,
            realized_pnl=pnl,
            slippage=Decimal(str(abs(slippage))),
            filled_at=position.opened_at,
            closed_at=datetime.utcnow(),
        )
        db.add(trade)

        # Remove position
        await db.delete(position)
        await db.flush()

        # Update account equity
        await self._update_account_equity(db, account)

        await db.commit()
        # await db.refresh(trade)

        # Telemetry
        metrics.paper_fills_total.labels(
            symbol=position.symbol, side=exit_side.value
        ).inc()
        metrics.paper_pnl_total.set(float(account.equity - Decimal("10000")))

        return trade

    def _calculate_slippage(self, side: TradeSide) -> float:
        """
        Calculate slippage based on mode.

        Args:
            side: Trade direction

        Returns:
            float: Slippage in price units (positive for worse fill)
        """
        if self.slippage_mode == SlippageMode.NONE:
            return 0.0

        # Convert pips to price units (assuming 1 pip = 0.01 for simplicity)
        pip_value = 0.01

        if self.slippage_mode == SlippageMode.FIXED:
            slippage_pips = self.slippage_pips
        else:  # RANDOM
            slippage_pips = random.uniform(0, self.slippage_pips)

        # Slippage always worsens the fill
        # BUY: higher price (positive slippage)
        # SELL: lower price (negative slippage, but we return positive magnitude)
        if side == TradeSide.BUY:
            return slippage_pips * pip_value
        else:
            return -slippage_pips * pip_value

    async def _update_position(
        self,
        db: AsyncSession,
        account: PaperAccount,
        symbol: str,
        side: TradeSide,
        volume: Decimal,
        price: Decimal,
    ):
        """
        Update or create position.

        Args:
            db: Database session
            account: Paper account
            symbol: Trading symbol
            side: Trade side
            volume: Trade volume
            price: Fill price
        """
        # Find existing position
        stmt = select(PaperPosition).where(
            PaperPosition.account_id == account.id,
            PaperPosition.symbol == symbol,
            PaperPosition.side == side,
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Average entry price
            total_volume = existing.volume + volume
            existing.entry_price = (
                existing.entry_price * existing.volume + price * volume
            ) / total_volume
            existing.volume = total_volume
            existing.current_price = price
            existing.updated_at = datetime.utcnow()
        else:
            # Create new position
            position = PaperPosition(
                account_id=account.id,
                symbol=symbol,
                side=side,
                volume=volume,
                entry_price=price,
                current_price=price,
                unrealized_pnl=Decimal("0"),
            )
            db.add(position)

    async def _update_account_equity(self, db: AsyncSession, account: PaperAccount):
        """
        Recalculate account equity from balance + unrealized PnL.

        Args:
            db: Database session
            account: Paper account
        """
        # Fetch all positions for the account
        stmt = select(PaperPosition).where(PaperPosition.account_id == account.id)
        result = await db.execute(stmt)
        positions = result.scalars().all()

        unrealized_pnl = Decimal("0")
        for pos in positions:
            if pos.side == TradeSide.BUY:
                pos_pnl = (pos.current_price - pos.entry_price) * pos.volume
            else:
                pos_pnl = (pos.entry_price - pos.current_price) * pos.volume

            pos.unrealized_pnl = pos_pnl
            unrealized_pnl += pos_pnl

        account.equity = account.balance + unrealized_pnl
        account.updated_at = datetime.utcnow()
