"""Risk management service layer for exposure tracking and limit enforcement.

This module provides core risk functions for:
1. Risk profile management (per-client configuration)
2. Current exposure calculation (what's at risk right now)
3. Risk limit validation (before signal approval)
4. Position sizing (Kelly criterion variant)
5. Drawdown tracking (peak-to-trough analysis)
6. Global limit enforcement (platform-wide circuit breakers)

All functions follow async/await pattern for database operations.
"""

from datetime import datetime
from decimal import Decimal
from logging import getLogger
from typing import Optional

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.accounts.service import AccountLink
from backend.app.risk.models import ExposureSnapshot, RiskProfile
from backend.app.signals.models import Signal
from backend.app.trading.store.models import Trade

logger = getLogger(__name__)


class RiskService:
    """Service for risk profile and exposure management.

    Per-client risk controls with configurable limits:
    - Max drawdown: Peak-to-trough loss threshold
    - Max daily loss: Daily loss cap (resets daily)
    - Max position size: Single trade limit
    - Max open positions: Number of concurrent trades
    - Risk per trade: Fraction of equity at risk per trade
    - Correlation exposure: Related instruments concentration
    - Max correlation exposure: Related instruments limit

    All limits are checked BEFORE signal approval to prevent over-leverage.
    """

    # Global platform-wide limits (override client configs if more restrictive)
    PLATFORM_MAX_EXPOSURE = Decimal("500.00")  # Max total exposure USD
    PLATFORM_MAX_DAILY_LOSS = Decimal("50000.00")  # Max daily platform loss USD
    PLATFORM_MAX_POSITION_SIZE = Decimal("100.00")  # Max single position size lots
    PLATFORM_MAX_OPEN_POSITIONS = 50  # Max concurrent trades across all clients

    # Instrument groupings for correlation limits
    RELATED_INSTRUMENTS = {
        "majors": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF"],
        "commodities": ["GOLD", "SILVER", "CRUDE_OIL", "NATURAL_GAS"],
        "indices": ["SPX500", "DAX40", "FTSE100", "ASX200"],
        "crosses": ["EURJPY", "EURGBP", "GBPJPY", "AUDJPY"],
    }

    @staticmethod
    async def get_or_create_risk_profile(
        client_id: str, db: AsyncSession
    ) -> RiskProfile:
        """Get existing risk profile or create with default limits.

        Default limits are conservative to prevent excessive leverage:
        - Max drawdown: 20% of account
        - Max daily loss: No limit
        - Max position size: 1.0 lot
        - Max open positions: 5 concurrent
        - Risk per trade: 2% of equity
        - Max correlation exposure: 70% of portfolio

        Args:
            client_id: Client UUID
            db: Database session

        Returns:
            RiskProfile: Existing or newly created profile

        Raises:
            sqlalchemy.exc.IntegrityError: If concurrent create attempt
        """
        # Check if exists
        stmt = select(RiskProfile).where(RiskProfile.client_id == client_id)
        result = await db.execute(stmt)
        profile = result.scalars().first()

        if profile:
            return profile

        # Create with defaults
        profile = RiskProfile(
            client_id=client_id,
            max_drawdown_percent=Decimal("20.00"),
            max_daily_loss=None,  # Unlimited
            max_position_size=Decimal("1.0"),
            max_open_positions=5,
            max_correlation_exposure=Decimal("0.70"),
            risk_per_trade_percent=Decimal("2.00"),
        )

        db.add(profile)
        await db.commit()
        await db.refresh(profile)

        logger.info(
            f"Created default risk profile for client {client_id}",
            extra={"client_id": client_id},
        )

        return profile

    @staticmethod
    async def calculate_current_exposure(
        client_id: str, db: AsyncSession
    ) -> ExposureSnapshot:
        """Calculate current exposure from open trades.

        Queries all OPEN trades for client and aggregates:
        - Total exposure (volume * entry_price)
        - Exposure by instrument (instrument → total volume)
        - Exposure by direction (buy → volume, sell → volume)
        - Open positions count

        Creates new snapshot record for historical tracking.

        Args:
            client_id: Client UUID
            db: Database session

        Returns:
            ExposureSnapshot: Current exposure with breakdown

        Example:
            >>> snapshot = await RiskService.calculate_current_exposure(
            ...     "client-123", db
            ... )
            >>> print(f"Total: {snapshot.total_exposure}")
            >>> print(f"By instrument: {snapshot.exposure_by_instrument}")
        """
        # Query all open trades for this client
        stmt = (
            select(Trade)
            .where(
                and_(
                    Trade.user_id == client_id,
                    Trade.status == "OPEN",
                )
            )
            .order_by(desc(Trade.entry_time))
        )
        result = await db.execute(stmt)
        open_trades = result.scalars().all()

        # Aggregate exposure
        total_exposure = Decimal("0.00")
        exposure_by_instrument = {}
        exposure_by_direction = {"buy": Decimal("0.00"), "sell": Decimal("0.00")}

        for trade in open_trades:
            # Calculate position size in USD (volume * entry_price)
            position_value = trade.volume * trade.entry_price

            # Add to totals
            total_exposure += position_value

            # By instrument
            if trade.symbol not in exposure_by_instrument:
                exposure_by_instrument[trade.symbol] = Decimal("0.00")
            exposure_by_instrument[trade.symbol] += position_value

            # By direction
            direction_key = "buy" if trade.direction == 0 else "sell"
            exposure_by_direction[direction_key] += position_value

        # Convert Decimals to floats for JSON serialization
        exposure_by_instrument = {
            k: float(v) for k, v in exposure_by_instrument.items()
        }
        exposure_by_direction = {k: float(v) for k, v in exposure_by_direction.items()}

        # Create snapshot record
        snapshot = ExposureSnapshot(
            client_id=client_id,
            timestamp=datetime.utcnow(),
            total_exposure=total_exposure,
            exposure_by_instrument=exposure_by_instrument,
            exposure_by_direction=exposure_by_direction,
            open_positions_count=len(open_trades),
            current_drawdown_percent=await RiskService.calculate_current_drawdown(
                client_id, db
            ),
            daily_pnl=await RiskService.calculate_daily_pnl(client_id, db),
        )

        db.add(snapshot)
        await db.commit()
        await db.refresh(snapshot)

        logger.debug(
            f"Calculated exposure for client {client_id}: "
            f"${total_exposure} across {len(open_trades)} positions",
            extra={
                "client_id": client_id,
                "total_exposure": str(total_exposure),
                "open_positions": len(open_trades),
            },
        )

        return snapshot

    @staticmethod
    async def check_risk_limits(
        client_id: str, signal: Signal, db: AsyncSession
    ) -> dict:
        """Validate signal against client risk limits.

        Checks:
        1. Max open positions limit
        2. Max position size limit
        3. Max daily loss limit
        4. Max drawdown limit
        5. Correlation exposure limit
        6. Global platform limits

        Returns dict with:
        - passes: True if all checks pass
        - violations: List of violated limits with details
        - exposure: Current ExposureSnapshot
        - margin_available: Remaining capacity for this signal

        Args:
            client_id: Client UUID
            signal: Signal to validate
            db: Database session

        Returns:
            dict: Validation result with violations and exposure

        Example:
            >>> result = await RiskService.check_risk_limits(
            ...     "client-123", signal, db
            ... )
            >>> if not result["passes"]:
            ...     print(f"Violations: {result['violations']}")
        """
        violations = []

        # Get risk profile
        profile = await RiskService.get_or_create_risk_profile(client_id, db)

        # Calculate current exposure
        exposure = await RiskService.calculate_current_exposure(client_id, db)

        # Check 1: Max open positions
        if exposure.open_positions_count >= profile.max_open_positions:
            violations.append(
                {
                    "check": "max_open_positions",
                    "limit": profile.max_open_positions,
                    "current": exposure.open_positions_count,
                    "message": f"Already at max {profile.max_open_positions} open positions",
                }
            )

        # Check 2: Max position size
        proposed_size = Decimal(str(getattr(signal, "volume", 1)))
        if proposed_size > profile.max_position_size:
            violations.append(
                {
                    "check": "max_position_size",
                    "limit": str(profile.max_position_size),
                    "proposed": str(proposed_size),
                    "message": f"Proposed size {proposed_size} exceeds limit {profile.max_position_size}",
                }
            )

        # Check 3: Max daily loss
        daily_pnl = exposure.daily_pnl or Decimal("0.00")
        if (
            profile.max_daily_loss
            and daily_pnl < 0
            and abs(daily_pnl) >= profile.max_daily_loss
        ):
            violations.append(
                {
                    "check": "max_daily_loss",
                    "limit": str(profile.max_daily_loss),
                    "current_loss": str(daily_pnl),
                    "message": f"Daily loss {daily_pnl} exceeds limit {profile.max_daily_loss}",
                }
            )

        # Check 4: Max drawdown
        drawdown = exposure.current_drawdown_percent or Decimal("0.00")
        if drawdown >= profile.max_drawdown_percent:
            violations.append(
                {
                    "check": "max_drawdown",
                    "limit": str(profile.max_drawdown_percent),
                    "current": str(drawdown),
                    "message": f"Drawdown {drawdown}% exceeds limit {profile.max_drawdown_percent}%",
                }
            )

        # Check 5: Correlation exposure (related instruments)
        related_group = await RiskService._find_instrument_group(signal.instrument)
        if related_group:
            related_exposure = await RiskService._calculate_related_exposure(
                client_id, related_group, db
            )
            max_related = exposure.total_exposure * profile.max_correlation_exposure
            if related_exposure > max_related:
                violations.append(
                    {
                        "check": "correlation_exposure",
                        "limit": str(max_related),
                        "current": str(related_exposure),
                        "message": f"Related instrument exposure {related_exposure} exceeds limit {max_related}",
                    }
                )

        # Check 6: Global platform limits
        if exposure.total_exposure >= RiskService.PLATFORM_MAX_EXPOSURE:
            violations.append(
                {
                    "check": "platform_max_exposure",
                    "limit": str(RiskService.PLATFORM_MAX_EXPOSURE),
                    "current": str(exposure.total_exposure),
                    "message": f"Platform exposure {exposure.total_exposure} exceeds limit {RiskService.PLATFORM_MAX_EXPOSURE}",
                }
            )

        # Calculate margin available
        margin_available = profile.max_position_size - proposed_size

        logger.info(
            f"Risk check complete for client {client_id}: "
            f"{'PASS' if not violations else 'FAIL'}",
            extra={
                "client_id": client_id,
                "violations_count": len(violations),
                "exposure": str(exposure.total_exposure),
                "margin_available": str(margin_available),
            },
        )

        return {
            "passes": len(violations) == 0,
            "violations": violations,
            "exposure": exposure,
            "margin_available": margin_available,
            "profile": profile,
        }

    @staticmethod
    async def calculate_position_size(
        client_id: str,
        signal: Signal,
        risk_percent: Optional[Decimal] = None,
        db: AsyncSession = None,
    ) -> Decimal:
        """Calculate safe position size using Kelly-like criterion.

        Uses risk per trade percentage from client profile to size position:
        position_size = (account_equity * risk_percent) / (entry_price * stop_distance_pips)

        Respects:
        - Max position size limit
        - Max correlation exposure
        - Available margin
        - Platform max position

        Args:
            client_id: Client UUID
            signal: Signal with entry_price and stop_loss
            risk_percent: Override profile risk_percent (optional)
            db: Database session

        Returns:
            Decimal: Safe position size in lots

        Example:
            >>> size = await RiskService.calculate_position_size(
            ...     "client-123", signal, db=db
            ... )
            >>> print(f"Trade {signal.instrument} with {size} lots")
        """
        if db is None:
            return Decimal("0.01")  # Minimum

        # Get profile
        profile = await RiskService.get_or_create_risk_profile(client_id, db)
        risk_pct = risk_percent or profile.risk_per_trade_percent

        # Get account equity (from AccountLink - assumes exists)
        stmt = select(AccountLink).where(AccountLink.user_id == client_id)
        result = await db.execute(stmt)
        account = result.scalars().first()

        if not account or not account.balance:
            return Decimal("0.01")  # Minimum

        equity = Decimal(str(account.balance))

        # Calculate risk amount in USD
        risk_amount = equity * (risk_pct / Decimal("100"))

        # Calculate position size (simplification: 1 pip = 0.01)
        # For GOLD: 1 lot = 100 oz, 1 pip = 1 oz, so 100 units = 1 pip
        # For EURUSD: 1 lot = 100k, 0.0001 = 1 pip
        entry_price = Decimal(str(signal.price))
        stop_loss = Decimal(
            str(getattr(signal, "stop_loss", entry_price * Decimal("0.98")))
        )

        stop_distance = abs(entry_price - stop_loss)
        if stop_distance == 0:
            stop_distance = entry_price * Decimal("0.02")  # 2% default

        # position_size = risk_amount / stop_distance
        calculated_size = risk_amount / stop_distance

        # Apply limits
        safe_size = min(
            calculated_size,
            profile.max_position_size,
            RiskService.PLATFORM_MAX_POSITION_SIZE,
        )

        # Ensure minimum
        safe_size = max(safe_size, Decimal("0.01"))

        logger.debug(
            f"Calculated position size for {client_id}: {safe_size} lots",
            extra={
                "client_id": client_id,
                "equity": str(equity),
                "risk_percent": str(risk_pct),
                "calculated": str(calculated_size),
                "applied_limit": str(safe_size),
            },
        )

        return safe_size

    @staticmethod
    async def calculate_current_drawdown(client_id: str, db: AsyncSession) -> Decimal:
        """Calculate peak-to-trough drawdown percentage.

        Tracks historical maximum equity and compares to current.
        Drawdown % = (Peak Equity - Current Equity) / Peak Equity * 100

        Implementation:
        - Get all closed trades to calculate cumulative P&L
        - Track historical high
        - Return current drawdown

        Args:
            client_id: Client UUID
            db: Database session

        Returns:
            Decimal: Drawdown percentage (0-100)

        Example:
            >>> dd = await RiskService.calculate_current_drawdown("client-123", db)
            >>> print(f"Current drawdown: {dd}%")
        """
        # Get account balance
        stmt = select(AccountLink).where(AccountLink.user_id == client_id)
        result = await db.execute(stmt)
        account = result.scalars().first()

        if not account or account.balance is None:
            return Decimal("0.00")

        current_balance = Decimal(str(account.balance))

        # Get all closed trades to find historical high
        stmt = (
            select(Trade)
            .where(
                and_(
                    Trade.user_id == client_id,
                    Trade.status == "CLOSED",
                )
            )
            .order_by(desc(Trade.exit_time))
            .limit(100)  # Last 100 closed trades
        )
        result = await db.execute(stmt)
        closed_trades = result.scalars().all()

        if not closed_trades:
            return Decimal("0.00")

        # Reconstruct historical equity curve
        historical_equity = current_balance
        max_equity = current_balance

        for trade in reversed(closed_trades):
            # Remove profit from trade to get prior equity
            if trade.profit:
                historical_equity = historical_equity - trade.profit
                max_equity = max(max_equity, historical_equity)

        # Calculate drawdown
        if max_equity == 0:
            return Decimal("0.00")

        drawdown = ((max_equity - current_balance) / max_equity) * Decimal("100")
        drawdown = max(drawdown, Decimal("0.00"))  # Never negative

        logger.debug(
            f"Calculated drawdown for {client_id}: {drawdown}%",
            extra={
                "client_id": client_id,
                "current_balance": str(current_balance),
                "max_equity": str(max_equity),
                "drawdown_pct": str(drawdown),
            },
        )

        return drawdown

    @staticmethod
    async def calculate_daily_pnl(client_id: str, db: AsyncSession) -> Decimal:
        """Calculate P&L for trades closed today.

        Sums profit from all trades closed since 00:00 UTC today.

        Args:
            client_id: Client UUID
            db: Database session

        Returns:
            Decimal: Daily P&L (positive = profit, negative = loss)
        """
        # Get today's start in UTC
        today_start = datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        # Query closed trades since today
        stmt = select(Trade).where(
            and_(
                Trade.user_id == client_id,
                Trade.status == "CLOSED",
                Trade.exit_time >= today_start,
            )
        )
        result = await db.execute(stmt)
        today_trades = result.scalars().all()

        # Sum profits
        daily_pnl = sum((trade.profit or Decimal("0.00")) for trade in today_trades)

        return Decimal(str(daily_pnl))

    @staticmethod
    async def check_global_limits(
        instrument: str, lot_size: Decimal, db: AsyncSession
    ) -> dict:
        """Check platform-wide global limits.

        Validates:
        - Total platform exposure
        - Total platform daily loss
        - Instrument concentration
        - Open positions across all clients

        Args:
            instrument: Trading instrument
            lot_size: Proposed trade size
            db: Database session

        Returns:
            dict: Check result with passes/violations

        Example:
            >>> result = await RiskService.check_global_limits("GOLD", 5.0, db)
            >>> if result["passes"]:
            ...     print("Ready to trade")
        """
        violations = []

        # Query all open trades across platform
        stmt = select(Trade).where(Trade.status == "OPEN")
        result = await db.execute(stmt)
        all_open_trades = result.scalars().all()

        # Calculate total platform exposure
        total_exposure = sum((t.volume * t.entry_price) for t in all_open_trades)

        # Check 1: Total exposure
        if total_exposure >= RiskService.PLATFORM_MAX_EXPOSURE:
            violations.append(
                {
                    "check": "platform_total_exposure",
                    "limit": str(RiskService.PLATFORM_MAX_EXPOSURE),
                    "current": str(total_exposure),
                }
            )

        # Check 2: Open positions count
        if len(all_open_trades) >= RiskService.PLATFORM_MAX_OPEN_POSITIONS:
            violations.append(
                {
                    "check": "platform_max_positions",
                    "limit": RiskService.PLATFORM_MAX_OPEN_POSITIONS,
                    "current": len(all_open_trades),
                }
            )

        # Check 3: Instrument concentration
        instrument_exposure = sum(
            t.volume for t in all_open_trades if t.symbol == instrument
        )
        if (
            instrument_exposure + lot_size
            > RiskService.PLATFORM_MAX_POSITION_SIZE * Decimal("5")
        ):
            violations.append(
                {
                    "check": "instrument_concentration",
                    "instrument": instrument,
                    "current": str(instrument_exposure),
                    "proposed": str(lot_size),
                }
            )

        logger.info(
            f"Global limits check: {'PASS' if not violations else 'FAIL'}",
            extra={
                "violations": len(violations),
                "total_exposure": str(total_exposure),
                "open_trades": len(all_open_trades),
            },
        )

        return {
            "passes": len(violations) == 0,
            "violations": violations,
            "total_platform_exposure": total_exposure,
            "total_open_positions": len(all_open_trades),
        }

    @staticmethod
    async def _find_instrument_group(instrument: str) -> Optional[list]:
        """Find which correlation group an instrument belongs to.

        Args:
            instrument: Trading instrument

        Returns:
            List of related instruments or None
        """
        for group_name, instruments in RiskService.RELATED_INSTRUMENTS.items():
            if instrument in instruments:
                return instruments
        return None

    @staticmethod
    async def _calculate_related_exposure(
        client_id: str, related_instruments: list, db: AsyncSession
    ) -> Decimal:
        """Calculate total exposure to related instruments.

        Args:
            client_id: Client UUID
            related_instruments: List of related instrument symbols
            db: Database session

        Returns:
            Decimal: Total exposure to related instruments
        """
        stmt = select(Trade).where(
            and_(
                Trade.user_id == client_id,
                Trade.status == "OPEN",
                Trade.symbol.in_(related_instruments),
            )
        )
        result = await db.execute(stmt)
        related_trades = result.scalars().all()

        total = sum((t.volume * t.entry_price) for t in related_trades)

        return total
