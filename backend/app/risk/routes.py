"""Risk management API routes for profile and exposure management.

REST API endpoints:
- GET /api/v1/risk/profile - Get client risk profile
- PATCH /api/v1/risk/profile - Update risk limits
- GET /api/v1/risk/exposure - Get current exposure snapshot
- GET /api/v1/admin/risk/global-exposure - Platform-wide exposure (admin only)

PR-075 Trading Control endpoints:
- PATCH /api/v1/trading/pause - Pause trading (stops signal generation)
- PATCH /api/v1/trading/resume - Resume trading (restarts on next candle)
- PUT /api/v1/trading/size - Update position size override
- GET /api/v1/trading/status - Get trading control status

All endpoints require authentication. Admin endpoints require premium tier.
"""

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.models import User, UserRole
from backend.app.core.db import get_db
from backend.app.risk.service import RiskService
from backend.app.risk.trading_controls import TradingControlService

router = APIRouter(prefix="/api/v1/risk", tags=["risk"])
admin_router = APIRouter(prefix="/api/v1/admin/risk", tags=["risk-admin"])
trading_router = APIRouter(prefix="/api/v1/trading", tags=["trading-controls"])


# ============================================================================
# Request/Response Models
# ============================================================================


class RiskLimitUpdate(BaseModel):
    """Request model for updating risk limits."""

    max_drawdown_percent: Decimal | None = Field(
        None,
        ge=Decimal("1"),
        le=Decimal("100"),
        description="Maximum drawdown threshold (1-100%)",
    )
    max_daily_loss: Decimal | None = Field(
        None,
        ge=Decimal("0"),
        description="Maximum daily loss in account currency (0=unlimited)",
    )
    max_position_size: Decimal | None = Field(
        None,
        ge=Decimal("0.01"),
        le=Decimal("100"),
        description="Maximum position size per trade (0.01-100 lots)",
    )
    max_open_positions: int | None = Field(
        None, ge=1, le=100, description="Maximum concurrent open trades"
    )
    max_correlation_exposure: Decimal | None = Field(
        None,
        ge=Decimal("0"),
        le=Decimal("1"),
        description="Max exposure to related instruments (0-1)",
    )
    risk_per_trade_percent: Decimal | None = Field(
        None,
        ge=Decimal("0.1"),
        le=Decimal("10"),
        description="Risk per trade as % of equity (0.1-10%)",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "max_drawdown_percent": "25.00",
                "max_daily_loss": "10000.00",
                "max_position_size": "2.0",
                "max_open_positions": 8,
                "risk_per_trade_percent": "2.50",
            }
        }


class RiskProfileOut(BaseModel):
    """Response model for risk profile."""

    id: str
    client_id: str
    max_drawdown_percent: Decimal
    max_daily_loss: Decimal | None
    max_position_size: Decimal
    max_open_positions: int
    max_correlation_exposure: Decimal
    risk_per_trade_percent: Decimal
    updated_at: datetime

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "client_id": "client-123",
                "max_drawdown_percent": "20.00",
                "max_daily_loss": None,
                "max_position_size": "1.0",
                "max_open_positions": 5,
                "max_correlation_exposure": "0.70",
                "risk_per_trade_percent": "2.00",
                "updated_at": "2025-01-15T10:30:00Z",
            }
        }


class ExposureOut(BaseModel):
    """Response model for current exposure."""

    id: str
    client_id: str
    timestamp: datetime
    total_exposure: Decimal
    exposure_by_instrument: dict
    exposure_by_direction: dict
    open_positions_count: int
    current_drawdown_percent: Decimal
    daily_pnl: Decimal | None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440001",
                "client_id": "client-123",
                "timestamp": "2025-01-15T10:30:00Z",
                "total_exposure": "15000.50",
                "exposure_by_instrument": {
                    "EURUSD": "5000.00",
                    "GOLD": "10000.50",
                },
                "exposure_by_direction": {"buy": "12000.00", "sell": "3000.50"},
                "open_positions_count": 3,
                "current_drawdown_percent": "5.25",
                "daily_pnl": "500.00",
            }
        }


class GlobalExposureOut(BaseModel):
    """Response model for platform-wide exposure."""

    total_platform_exposure: Decimal
    total_open_positions: int
    max_exposure_limit: Decimal
    max_positions_limit: int
    exposure_utilization_percent: Decimal
    positions_utilization_percent: Decimal

    class Config:
        json_schema_extra = {
            "example": {
                "total_platform_exposure": "450000.00",
                "total_open_positions": 42,
                "max_exposure_limit": "500.00",
                "max_positions_limit": 50,
                "exposure_utilization_percent": "90.00",
                "positions_utilization_percent": "84.00",
            }
        }


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/profile", response_model=RiskProfileOut)
async def get_risk_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get client's current risk profile.

    Returns default profile if none exists.

    Args:
        db: Database session
        current_user: Authenticated user

    Returns:
        RiskProfileOut: Client risk profile with all limits

    Raises:
        HTTPException: 401 if unauthorized

    Example:
        >>> response = await client.get("/api/v1/risk/profile")
        >>> print(response.json()["max_drawdown_percent"])
        "20.00"
    """
    profile = await RiskService.get_or_create_risk_profile(current_user.id, db)
    return RiskProfileOut.model_validate(profile)


@router.patch("/profile", response_model=RiskProfileOut)
async def update_risk_profile(
    request: RiskLimitUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update client risk profile limits.

    Only non-None fields are updated. Others retain current value.

    Args:
        request: Risk limit updates
        db: Database session
        current_user: Authenticated user

    Returns:
        RiskProfileOut: Updated risk profile

    Raises:
        HTTPException: 400 if invalid values, 401 if unauthorized, 500 on error

    Example:
        >>> response = await client.patch(
        ...     "/api/v1/risk/profile",
        ...     json={"max_drawdown_percent": "25.00"}
        ... )
        >>> assert response.status_code == 200
    """
    try:
        profile = await RiskService.get_or_create_risk_profile(current_user.id, db)

        # Update only provided fields
        if request.max_drawdown_percent is not None:
            profile.max_drawdown_percent = request.max_drawdown_percent
        if request.max_daily_loss is not None:
            profile.max_daily_loss = request.max_daily_loss
        if request.max_position_size is not None:
            profile.max_position_size = request.max_position_size
        if request.max_open_positions is not None:
            profile.max_open_positions = request.max_open_positions
        if request.max_correlation_exposure is not None:
            profile.max_correlation_exposure = request.max_correlation_exposure
        if request.risk_per_trade_percent is not None:
            profile.risk_per_trade_percent = request.risk_per_trade_percent

        db.add(profile)
        await db.commit()
        await db.refresh(profile)

        return RiskProfileOut.model_validate(profile)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/exposure", response_model=ExposureOut)
async def get_current_exposure(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get client's current exposure snapshot.

    Returns aggregated exposure across all open trades:
    - Total position value
    - Breakdown by instrument
    - Breakdown by direction (buy vs sell)
    - Open positions count
    - Current drawdown %
    - Daily P&L

    Args:
        db: Database session
        current_user: Authenticated user

    Returns:
        ExposureOut: Current exposure with breakdowns

    Raises:
        HTTPException: 401 if unauthorized, 500 on error

    Example:
        >>> response = await client.get("/api/v1/risk/exposure")
        >>> data = response.json()
        >>> print(f"Total exposure: ${data['total_exposure']}")
        >>> print(f"Open positions: {data['open_positions_count']}")
    """
    try:
        exposure = await RiskService.calculate_current_exposure(current_user.id, db)
        return ExposureOut.model_validate(exposure)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.get("/global-exposure", response_model=GlobalExposureOut)
async def get_global_exposure(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get platform-wide risk exposure (admin only).

    Returns aggregated exposure across all clients and positions.

    Requires: Admin role with premium subscription

    Args:
        db: Database session
        current_user: Authenticated user (must be admin)

    Returns:
        GlobalExposureOut: Platform exposure statistics

    Raises:
        HTTPException: 401 if unauthorized, 403 if not admin, 500 on error

    Example:
        >>> response = await client.get("/api/v1/admin/risk/global-exposure")
        >>> data = response.json()
        >>> print(f"Utilization: {data['exposure_utilization_percent']}%")
    """
    # Check admin role
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        result = await RiskService.check_global_limits("DUMMY", Decimal("0"), db)

        total_exposure = result["total_platform_exposure"]
        total_positions = result["total_open_positions"]

        exposure_util = (
            (total_exposure / RiskService.PLATFORM_MAX_EXPOSURE) * 100
            if RiskService.PLATFORM_MAX_EXPOSURE > 0
            else Decimal("0")
        )
        positions_util = (
            (total_positions / RiskService.PLATFORM_MAX_OPEN_POSITIONS) * 100
            if RiskService.PLATFORM_MAX_OPEN_POSITIONS > 0
            else Decimal("0")
        )

        return GlobalExposureOut(
            total_platform_exposure=total_exposure,
            total_open_positions=total_positions,
            max_exposure_limit=RiskService.PLATFORM_MAX_EXPOSURE,
            max_positions_limit=RiskService.PLATFORM_MAX_OPEN_POSITIONS,
            exposure_utilization_percent=exposure_util,
            positions_utilization_percent=positions_util,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PR-075: Trading Control Endpoints
# ============================================================================


class PauseRequest(BaseModel):
    """Request model for pausing trading."""

    reason: str | None = Field(
        None, max_length=500, description="Optional reason for pause"
    )

    class Config:
        json_schema_extra = {"example": {"reason": "Manual pause for risk review"}}


class PositionSizeUpdate(BaseModel):
    """Request model for position size override."""

    position_size: Decimal | None = Field(
        None,
        ge=Decimal("0.01"),
        le=Decimal("100"),
        description="Position size in lots (None = use default risk %)",
    )

    class Config:
        json_schema_extra = {
            "example": {"position_size": "0.5"}  # Override to 0.5 lots
        }


class TradingStatusOut(BaseModel):
    """Response model for trading status."""

    is_paused: bool
    paused_at: str | None
    paused_by: str | None
    pause_reason: str | None
    position_size_override: float | None
    notifications_enabled: bool
    updated_at: str

    class Config:
        json_schema_extra = {
            "example": {
                "is_paused": False,
                "paused_at": None,
                "paused_by": None,
                "pause_reason": None,
                "position_size_override": None,
                "notifications_enabled": True,
                "updated_at": "2025-01-15T10:30:00Z",
            }
        }


@trading_router.patch("/pause", response_model=TradingStatusOut)
async def pause_trading(
    request: PauseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pause trading for current user.

    Business Logic:
    - Sets is_paused=True, stops signal generation in strategy scheduler
    - Existing open positions are NOT automatically closed
    - User can manually close positions if desired
    - Resume via PATCH /trading/resume

    Args:
        request: Pause request with optional reason
        db: Database session
        current_user: Authenticated user

    Returns:
        TradingStatusOut: Updated trading status with paused state

    Raises:
        HTTPException: 400 if already paused, 500 on error

    Example:
        >>> response = await client.patch(
        ...     "/api/v1/trading/pause",
        ...     json={"reason": "Risk breach"}
        ... )
        >>> assert response.json()["is_paused"] is True
    """
    try:
        await TradingControlService.pause_trading(
            user_id=current_user.id,
            db=db,
            actor="user",
            reason=request.reason,
        )

        status = await TradingControlService.get_trading_status(current_user.id, db)
        return TradingStatusOut(**status)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@trading_router.patch("/resume", response_model=TradingStatusOut)
async def resume_trading(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Resume trading for current user.

    Business Logic:
    - Sets is_paused=False, signal generation resumes on NEXT candle bar
    - No retroactive signals generated for missed bars during pause
    - Preserves pause audit history (paused_at, paused_by, pause_reason)

    Args:
        db: Database session
        current_user: Authenticated user

    Returns:
        TradingStatusOut: Updated trading status with running state

    Raises:
        HTTPException: 400 if already running, 500 on error

    Example:
        >>> response = await client.patch("/api/v1/trading/resume")
        >>> assert response.json()["is_paused"] is False
    """
    try:
        await TradingControlService.resume_trading(
            user_id=current_user.id, db=db, actor="user"
        )

        status = await TradingControlService.get_trading_status(current_user.id, db)
        return TradingStatusOut(**status)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@trading_router.put("/size", response_model=TradingStatusOut)
async def update_position_size(
    request: PositionSizeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update position size override.

    Business Logic:
    - position_size=None → use default risk % from PR-074 guards
    - position_size=X → force all trades to X lots (subject to broker constraints)
    - Size validation happens in PR-074 position_size.py before order placement

    Args:
        request: Position size update (None = use default)
        db: Database session
        current_user: Authenticated user

    Returns:
        TradingStatusOut: Updated trading status with new size

    Raises:
        HTTPException: 400 if invalid size, 500 on error

    Example:
        >>> response = await client.put(
        ...     "/api/v1/trading/size",
        ...     json={"position_size": "0.5"}
        ... )
        >>> assert response.json()["position_size_override"] == 0.5
    """
    try:
        await TradingControlService.update_position_size(
            user_id=current_user.id,
            db=db,
            position_size=request.position_size,
        )

        status = await TradingControlService.get_trading_status(current_user.id, db)
        return TradingStatusOut(**status)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@trading_router.get("/status", response_model=TradingStatusOut)
async def get_trading_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current trading control status.

    Returns comprehensive status:
    - Trading paused/running
    - Pause metadata (when, who, why)
    - Position size override (if any)
    - Notification preferences

    Args:
        db: Database session
        current_user: Authenticated user

    Returns:
        TradingStatusOut: Current trading status

    Raises:
        HTTPException: 500 on error

    Example:
        >>> response = await client.get("/api/v1/trading/status")
        >>> print(f"Trading: {'PAUSED' if response.json()['is_paused'] else 'RUNNING'}")
    """
    try:
        status = await TradingControlService.get_trading_status(current_user.id, db)
        return TradingStatusOut(**status)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
