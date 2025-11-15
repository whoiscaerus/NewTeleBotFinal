"""
Paper Trading API Routes

Endpoints for managing paper trading accounts and orders.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.models import User
from backend.app.core.db import get_db
from backend.app.paper.engine import FillPriceMode, PaperTradingEngine, SlippageMode
from backend.app.paper.models import PaperAccount, PaperPosition, PaperTrade, TradeSide

router = APIRouter(prefix="/api/v1/paper", tags=["paper-trading"])


# Pydantic Models
class PaperAccountCreate(BaseModel):
    """Request to enable paper trading"""

    initial_balance: Decimal = Field(
        default=Decimal("10000.00"), ge=Decimal("100"), le=Decimal("1000000")
    )


class PaperAccountResponse(BaseModel):
    """Paper account summary"""

    id: str
    user_id: str
    balance: Decimal
    equity: Decimal
    enabled: bool


class PaperPositionResponse(BaseModel):
    """Open paper position"""

    id: str
    symbol: str
    side: str
    volume: Decimal
    entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal


class PaperTradeResponse(BaseModel):
    """Closed paper trade"""

    id: str
    symbol: str
    side: str
    volume: Decimal
    entry_price: Decimal
    exit_price: Decimal | None
    realized_pnl: Decimal | None
    slippage: Decimal
    filled_at: str
    closed_at: str | None


class PaperOrderRequest(BaseModel):
    """Request to place paper order"""

    symbol: str = Field(..., min_length=2, max_length=20)
    side: TradeSide
    volume: Decimal = Field(..., gt=Decimal("0"), le=Decimal("100"))
    bid: Decimal = Field(..., gt=Decimal("0"))
    ask: Decimal = Field(..., gt=Decimal("0"))


# Dependency: Get current user (stub for now, replace with actual auth)
async def get_current_user(db: AsyncSession = Depends(get_db)) -> User:
    """
    Get authenticated user.

    TODO: Replace with actual JWT auth from PR-003
    """
    # Stub: return first user for testing
    result = await db.execute(select(User).limit(1))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.post("/enable", status_code=201, response_model=PaperAccountResponse)
async def enable_paper_trading(
    request: PaperAccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Enable paper trading for user.

    Creates virtual account with initial balance.

    Args:
        request: Initial balance configuration
        db: Database session
        current_user: Authenticated user

    Returns:
        PaperAccountResponse: Created account

    Raises:
        HTTPException: 400 if already enabled

    Example:
        POST /api/v1/paper/enable
        {
          "initial_balance": 10000.00
        }
        Response: {"id": "uuid", "balance": 10000.00, "enabled": true}
    """
    # Check if already exists
    result = await db.execute(
        select(PaperAccount).where(PaperAccount.user_id == current_user.id)
    )
    existing = result.scalars().first()

    if existing and existing.enabled:
        raise HTTPException(status_code=400, detail="Paper trading already enabled")

    if existing:
        # Re-enable existing account
        existing.enabled = True
        existing.balance = request.initial_balance
        existing.equity = request.initial_balance
        await db.commit()
        await db.refresh(existing)
        account = existing
    else:
        # Create new account
        account = PaperAccount(
            user_id=current_user.id,
            balance=request.initial_balance,
            equity=request.initial_balance,
            enabled=True,
        )
        db.add(account)
        await db.commit()
        await db.refresh(account)

    return PaperAccountResponse(
        id=account.id,
        user_id=account.user_id,
        balance=account.balance,
        equity=account.equity,
        enabled=account.enabled,
    )


@router.post("/disable", status_code=200, response_model=PaperAccountResponse)
async def disable_paper_trading(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Disable paper trading for user.

    Freezes account (preserves balance/positions).

    Args:
        db: Database session
        current_user: Authenticated user

    Returns:
        PaperAccountResponse: Disabled account

    Raises:
        HTTPException: 404 if no paper account

    Example:
        POST /api/v1/paper/disable
        Response: {"enabled": false}
    """
    result = await db.execute(
        select(PaperAccount).where(PaperAccount.user_id == current_user.id)
    )
    account = result.scalars().first()

    if not account:
        raise HTTPException(status_code=404, detail="Paper account not found")

    account.enabled = False
    await db.commit()
    await db.refresh(account)

    return PaperAccountResponse(
        id=account.id,
        user_id=account.user_id,
        balance=account.balance,
        equity=account.equity,
        enabled=account.enabled,
    )


@router.get("/account", response_model=PaperAccountResponse)
async def get_paper_account(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get paper account summary.

    Args:
        db: Database session
        current_user: Authenticated user

    Returns:
        PaperAccountResponse: Account details

    Raises:
        HTTPException: 404 if no paper account

    Example:
        GET /api/v1/paper/account
        Response: {"balance": 10500.00, "equity": 10750.00}
    """
    result = await db.execute(
        select(PaperAccount).where(PaperAccount.user_id == current_user.id)
    )
    account = result.scalars().first()

    if not account:
        raise HTTPException(status_code=404, detail="Paper account not found")

    return PaperAccountResponse(
        id=account.id,
        user_id=account.user_id,
        balance=account.balance,
        equity=account.equity,
        enabled=account.enabled,
    )


@router.get("/positions", response_model=list[PaperPositionResponse])
async def get_paper_positions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get open paper positions.

    Args:
        db: Database session
        current_user: Authenticated user

    Returns:
        List[PaperPositionResponse]: Open positions

    Example:
        GET /api/v1/paper/positions
        Response: [{"symbol": "GOLD", "unrealized_pnl": 250.00}]
    """
    result = await db.execute(
        select(PaperAccount).where(PaperAccount.user_id == current_user.id)
    )
    account = result.scalars().first()

    if not account:
        return []

    result = await db.execute(
        select(PaperPosition).where(PaperPosition.account_id == account.id)
    )
    positions = result.scalars().all()

    return [
        PaperPositionResponse(
            id=pos.id,
            symbol=pos.symbol,
            side=pos.side.value,
            volume=pos.volume,
            entry_price=pos.entry_price,
            current_price=pos.current_price,
            unrealized_pnl=pos.unrealized_pnl,
        )
        for pos in positions
    ]


@router.get("/trades", response_model=list[PaperTradeResponse])
async def get_paper_trades(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get paper trade history.

    Args:
        db: Database session
        current_user: Authenticated user

    Returns:
        List[PaperTradeResponse]: Trade history

    Example:
        GET /api/v1/paper/trades
        Response: [{"symbol": "GOLD", "realized_pnl": 150.00}]
    """
    result = await db.execute(
        select(PaperAccount).where(PaperAccount.user_id == current_user.id)
    )
    account = result.scalars().first()

    if not account:
        return []

    result = await db.execute(
        select(PaperTrade)
        .where(PaperTrade.account_id == account.id)
        .order_by(PaperTrade.filled_at.desc())
    )
    trades = result.scalars().all()

    return [
        PaperTradeResponse(
            id=trade.id,
            symbol=trade.symbol,
            side=trade.side.value,
            volume=trade.volume,
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            realized_pnl=trade.realized_pnl,
            slippage=trade.slippage,
            filled_at=trade.filled_at.isoformat(),
            closed_at=trade.closed_at.isoformat() if trade.closed_at else None,
        )
        for trade in trades
    ]


@router.post("/order", status_code=201, response_model=PaperTradeResponse)
async def place_paper_order(
    request: PaperOrderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Place paper trading order.

    Args:
        request: Order details
        db: Database session
        current_user: Authenticated user

    Returns:
        PaperTradeResponse: Filled trade

    Raises:
        HTTPException: 400 if insufficient balance, 403 if disabled

    Example:
        POST /api/v1/paper/order
        {
          "symbol": "GOLD",
          "side": "buy",
          "volume": 1.0,
          "bid": 1950.00,
          "ask": 1950.50
        }
        Response: {"entry_price": 1950.25, "slippage": 0.02}
    """
    # Get account
    result = await db.execute(
        select(PaperAccount).where(PaperAccount.user_id == current_user.id)
    )
    account = result.scalars().first()

    if not account:
        raise HTTPException(status_code=404, detail="Paper account not found")

    if not account.enabled:
        raise HTTPException(status_code=403, detail="Paper trading disabled")

    # Execute order
    engine = PaperTradingEngine(
        fill_mode=FillPriceMode.MID, slippage_mode=SlippageMode.FIXED, slippage_pips=2.0
    )

    try:
        trade = await engine.fill_order(
            db=db,
            account=account,
            symbol=request.symbol,
            side=request.side,
            volume=request.volume,
            bid=request.bid,
            ask=request.ask,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return PaperTradeResponse(
        id=trade.id,
        symbol=trade.symbol,
        side=trade.side.value,
        volume=trade.volume,
        entry_price=trade.entry_price,
        exit_price=trade.exit_price,
        realized_pnl=trade.realized_pnl,
        slippage=trade.slippage,
        filled_at=trade.filled_at.isoformat(),
        closed_at=trade.closed_at.isoformat() if trade.closed_at else None,
    )
