"""
PR-046: Copy-Trading Risk & Compliance Controls - REST API endpoints

Endpoints for managing copy-trading risk parameters and compliance:
- PATCH /api/v1/copy/risk - Update user risk parameters
- GET /api/v1/copy/status - Get current status and risk settings
- POST /api/v1/copy/pause - Manually pause copy-trading
- POST /api/v1/copy/resume - Resume copy-trading
- GET /api/v1/copy/disclosure - Get current disclosure
- POST /api/v1/copy/consent - Accept disclosure
- GET /api/v1/copy/consent-history - Get consent history
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.models import User
from backend.app.copytrading.disclosures import DisclosureService
from backend.app.copytrading.risk import RiskEvaluator
from backend.app.copytrading.service import CopyTradeSettings
from backend.app.core.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/copy", tags=["copy-trading"])

# Initialize services
risk_evaluator = RiskEvaluator()
disclosure_service = DisclosureService()


# Pydantic Request/Response Models


class UpdateCopyRiskSettingsRequest(BaseModel):
    """Request to update copy-trading risk parameters."""

    max_leverage: Optional[float] = Field(
        None, ge=1.0, le=10.0, description="Max leverage per trade"
    )
    max_per_trade_risk_percent: Optional[float] = Field(
        None, ge=0.1, le=10.0, description="Max risk per trade as % of account"
    )
    total_exposure_percent: Optional[float] = Field(
        None, ge=20.0, le=100.0, description="Max total exposure % across all positions"
    )
    daily_stop_percent: Optional[float] = Field(
        None, ge=1.0, le=50.0, description="Max daily loss % before pause"
    )


class CopyRiskSettingsResponse(BaseModel):
    """Response with current risk settings."""

    user_id: str
    enabled: bool
    is_paused: bool
    pause_reason: Optional[str]
    risk_parameters: dict = Field(description="Current risk parameter values")
    last_breach_at: Optional[str]
    last_breach_reason: Optional[str]


class CopyStatusResponse(BaseModel):
    """Response with complete copy-trading status."""

    user_id: str
    enabled: bool
    is_paused: bool
    pause_reason: Optional[str]
    paused_at: Optional[str]
    last_breach_at: Optional[str]
    last_breach_reason: Optional[str]
    risk_parameters: dict
    consent_version: str
    consent_accepted_at: Optional[str]


class DisclosureResponse(BaseModel):
    """Response with disclosure details."""

    id: str
    version: str
    title: str
    content: str
    effective_date: str


class ConsentRecordResponse(BaseModel):
    """Response confirming consent acceptance."""

    id: str
    user_id: str
    disclosure_version: str
    accepted_at: str


class ConsentHistoryResponse(BaseModel):
    """Response with user's consent history."""

    user_id: str
    consents: list = Field(description="List of consent acceptance records")


# Endpoints


@router.patch("/risk", status_code=200, response_model=CopyRiskSettingsResponse)
async def update_copy_risk_settings(
    request: UpdateCopyRiskSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CopyRiskSettingsResponse:
    """
    Update copy-trading risk parameters for current user.

    Only authenticated users can update their own settings.
    Each parameter is optional - only provided values are updated.

    Args:
        request: Updated risk parameters
        current_user: Authenticated user
        db: Database session

    Returns:
        Updated risk settings

    Raises:
        404: User has no copy-trading settings
        401: Unauthorized

    Example:
        ```
        PATCH /api/v1/copy/risk
        {
            "max_leverage": 3.0,
            "max_per_trade_risk_percent": 1.5,
            "total_exposure_percent": 40.0,
            "daily_stop_percent": 8.0
        }
        ```
    """
    from sqlalchemy.future import select

    # Get user's settings
    stmt = select(CopyTradeSettings).where(CopyTradeSettings.user_id == current_user.id)
    result = await db.execute(stmt)
    settings = result.scalar_one_or_none()

    if not settings:
        raise HTTPException(status_code=404, detail="Copy-trading settings not found")

    # Update provided fields
    if request.max_leverage is not None:
        settings.max_leverage = request.max_leverage
    if request.max_per_trade_risk_percent is not None:
        settings.max_per_trade_risk_percent = request.max_per_trade_risk_percent
    if request.total_exposure_percent is not None:
        settings.total_exposure_percent = request.total_exposure_percent
    if request.daily_stop_percent is not None:
        settings.daily_stop_percent = request.daily_stop_percent

    db.add(settings)
    await db.commit()

    logger.info(f"Updated risk settings for user {current_user.id}")

    status = await risk_evaluator.get_user_risk_status(db, current_user.id)
    return CopyRiskSettingsResponse(**status)


@router.get("/status", status_code=200, response_model=CopyStatusResponse)
async def get_copy_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CopyStatusResponse:
    """
    Get current copy-trading status and risk parameters.

    Returns complete status including:
    - Whether copy-trading is enabled/paused
    - Current risk parameters
    - Last breach details
    - Consent status

    Args:
        current_user: Authenticated user
        db: Database session

    Returns:
        Current copy-trading status

    Raises:
        404: User has no copy-trading settings
        401: Unauthorized

    Example:
        ```
        GET /api/v1/copy/status
        ```
    """
    from sqlalchemy.future import select

    stmt = select(CopyTradeSettings).where(CopyTradeSettings.user_id == current_user.id)
    result = await db.execute(stmt)
    settings = result.scalar_one_or_none()

    if not settings:
        raise HTTPException(status_code=404, detail="Copy-trading settings not found")

    return CopyStatusResponse(
        user_id=current_user.id,
        enabled=settings.enabled,
        is_paused=settings.is_paused,
        pause_reason=settings.pause_reason,
        paused_at=settings.paused_at.isoformat() if settings.paused_at else None,
        last_breach_at=(
            settings.last_breach_at.isoformat() if settings.last_breach_at else None
        ),
        last_breach_reason=settings.last_breach_reason,
        risk_parameters={
            "max_leverage": settings.max_leverage,
            "max_per_trade_risk_percent": settings.max_per_trade_risk_percent,
            "total_exposure_percent": settings.total_exposure_percent,
            "daily_stop_percent": settings.daily_stop_percent,
        },
        consent_version=settings.consent_version,
        consent_accepted_at=(
            settings.consent_accepted_at.isoformat()
            if settings.consent_accepted_at
            else None
        ),
    )


@router.post("/pause", status_code=200)
async def pause_copy_trading(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Manually pause copy-trading for safety.

    User can pause their own copy-trading at any time.
    Account can be resumed manually or after 24 hours.

    Args:
        current_user: Authenticated user
        db: Database session

    Returns:
        Confirmation with pause details

    Raises:
        404: User has no copy-trading settings
        401: Unauthorized

    Example:
        ```
        POST /api/v1/copy/pause
        ```
    """
    from datetime import datetime as dt

    from sqlalchemy.future import select

    stmt = select(CopyTradeSettings).where(CopyTradeSettings.user_id == current_user.id)
    result = await db.execute(stmt)
    settings = result.scalar_one_or_none()

    if not settings:
        raise HTTPException(status_code=404, detail="Copy-trading settings not found")

    settings.is_paused = True
    settings.pause_reason = "manual_pause"
    settings.paused_at = dt.utcnow()

    db.add(settings)
    await db.commit()

    logger.info(f"User {current_user.id} manually paused copy-trading")

    return {
        "status": "paused",
        "reason": "manual_pause",
        "paused_at": settings.paused_at.isoformat(),
    }


@router.post("/resume", status_code=200)
async def resume_copy_trading(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Resume copy-trading after pause.

    User can resume trading after addressing the breach reason.
    Resume is subject to risk evaluation on next trade.

    Args:
        current_user: Authenticated user
        db: Database session

    Returns:
        Confirmation with resume status

    Raises:
        404: User has no copy-trading settings
        401: Unauthorized
        400: User not paused or auto-resume not yet available

    Example:
        ```
        POST /api/v1/copy/resume
        ```
    """
    can_resume, reason = await risk_evaluator.can_resume_trading(
        db, current_user.id, manual_override=True
    )

    if not can_resume:
        raise HTTPException(status_code=400, detail=reason)

    logger.info(f"User {current_user.id} resumed copy-trading")

    return {"status": "resumed", "reason": reason}


@router.get("/disclosure", status_code=200, response_model=DisclosureResponse)
async def get_current_disclosure(
    db: AsyncSession = Depends(get_db),
) -> DisclosureResponse:
    """
    Get current disclosure version (public - no auth required).

    Returns the active disclosure that users must accept before copy-trading.

    Returns:
        Current disclosure details

    Raises:
        404: No active disclosure found

    Example:
        ```
        GET /api/v1/copy/disclosure
        ```
    """
    disclosure = await disclosure_service.get_current_disclosure(db)

    if not disclosure:
        raise HTTPException(status_code=404, detail="No active disclosure found")

    return DisclosureResponse(**disclosure)


@router.post("/consent", status_code=201, response_model=ConsentRecordResponse)
async def accept_disclosure(
    current_user: User = Depends(get_current_user),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
) -> ConsentRecordResponse:
    """
    Accept current disclosure (immutable audit trail).

    User acceptance is recorded with IP address and user agent for audit.
    Acceptance is required before enabling copy-trading.

    Args:
        current_user: Authenticated user
        request: HTTP request (for IP extraction)
        db: Database session

    Returns:
        Consent record confirmation

    Raises:
        404: No active disclosure found
        400: User already accepted current version
        401: Unauthorized

    Example:
        ```
        POST /api/v1/copy/consent
        ```
    """
    # Get current disclosure
    current = await disclosure_service.get_current_disclosure(db)
    if not current:
        raise HTTPException(status_code=404, detail="No active disclosure found")

    # Check if already accepted
    has_accepted = await disclosure_service.has_accepted_current(db, current_user.id)
    if has_accepted:
        raise HTTPException(
            status_code=400, detail="You have already accepted the current disclosure"
        )

    # Extract client info
    ip_address = request.client.host if request else None
    user_agent = request.headers.get("user-agent") if request else None

    # Record consent
    consent = await disclosure_service.record_consent(
        db,
        current_user.id,
        current["version"],
        ip_address=ip_address,
        user_agent=user_agent,
    )

    logger.info(f"User {current_user.id} accepted disclosure v{current['version']}")

    return ConsentRecordResponse(**consent)


@router.get("/consent-history", status_code=200, response_model=ConsentHistoryResponse)
async def get_consent_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConsentHistoryResponse:
    """
    Get user's consent history (immutable audit trail).

    Shows all disclosure versions accepted by the user with timestamps.
    This is an immutable record for compliance.

    Args:
        current_user: Authenticated user
        db: Database session

    Returns:
        List of consent records in chronological order

    Raises:
        401: Unauthorized

    Example:
        ```
        GET /api/v1/copy/consent-history
        ```
    """
    history = await disclosure_service.get_user_consent_history(db, current_user.id)

    return ConsentHistoryResponse(user_id=current_user.id, consents=history)
