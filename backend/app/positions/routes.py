"""
Live Positions API Routes

Endpoints:
- GET /api/v1/positions - Get user's primary account positions
- GET /api/v1/accounts/{account_id}/positions - Get specific account positions
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.accounts.service import AccountLinkingService
from backend.app.auth.dependencies import get_current_user
from backend.app.auth.models import User
from backend.app.core.db import get_db
from backend.app.core.errors import NotFoundError, ValidationError
from backend.app.positions.service import PortfolioOut, PositionsService
from backend.app.trading.mt5.manager import MT5SessionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["positions"])


# ============================================================================
# DEPENDENCIES
# ============================================================================


async def get_positions_service(
    db: AsyncSession = Depends(get_db),
) -> PositionsService:
    """Get positions service."""
    account_service = AccountLinkingService(db, MT5SessionManager())
    return PositionsService(db, account_service, MT5SessionManager())


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.get("/positions", response_model=PortfolioOut)
async def get_user_positions(
    force_refresh: bool = Query(False, description="Skip cache and fetch fresh"),
    current_user: User = Depends(get_current_user),
    service: PositionsService = Depends(get_positions_service),
) -> PortfolioOut:
    """
    Get live positions for user's primary account.

    Returns portfolio with all open positions, P&L, and account info.
    Uses cached positions if fresh (30s default), or fetches from MT5.

    Args:
        force_refresh: Skip cache and fetch fresh from MT5
        current_user: Authenticated user
        service: Positions service

    Returns:
        PortfolioOut with positions list and totals

    Raises:
        HTTPException: 404 if no primary account, 500 on error

    Example:
        >>> portfolio = await get_user_positions(current_user=user)
        >>> assert portfolio.open_positions_count >= 0
        >>> assert portfolio.balance > 0
    """
    try:
        logger.info(
            f"Getting positions for user: {current_user.id}",
            extra={
                "user_id": current_user.id,
                "force_refresh": force_refresh,
            },
        )

        portfolio = await service.get_user_positions(
            current_user.id, force_refresh=force_refresh
        )

        logger.info(
            "Positions fetched",
            extra={
                "user_id": current_user.id,
                "positions_count": portfolio.open_positions_count,
                "total_pnl_usd": portfolio.total_pnl_usd,
            },
        )

        return portfolio

    except NotFoundError as e:
        logger.warning(f"No primary account: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No primary account linked",
        )

    except ValidationError as e:
        logger.warning(f"Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    except Exception as e:
        logger.error(f"Error getting positions: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch positions",
        )


@router.get("/accounts/{account_id}/positions", response_model=PortfolioOut)
async def get_account_positions(
    account_id: str,
    force_refresh: bool = Query(False, description="Skip cache and fetch fresh"),
    current_user: User = Depends(get_current_user),
    service: PositionsService = Depends(get_positions_service),
) -> PortfolioOut:
    """
    Get live positions for specific account.

    Returns portfolio with all open positions, P&L, and account info.

    Args:
        account_id: Account link ID
        force_refresh: Skip cache and fetch fresh from MT5
        current_user: Authenticated user
        service: Positions service

    Returns:
        PortfolioOut with positions list and totals

    Raises:
        HTTPException: 403 if account doesn't belong to user, 404 if not found, 500 on error

    Example:
        >>> portfolio = await get_account_positions(
        ...     account_id="abc123",
        ...     current_user=user
        ... )
        >>> assert portfolio.open_positions_count >= 0
    """
    try:
        logger.info(
            f"Getting positions for account: {account_id}",
            extra={
                "user_id": current_user.id,
                "account_id": account_id,
            },
        )

        # Get account service to check ownership
        db_session = Depends(get_db)
        account_service = AccountLinkingService(db_session, MT5SessionManager())
        link = await account_service.get_account(account_id)

        # Verify ownership
        if link.user_id != current_user.id:
            logger.warning(f"Unauthorized access to account: {account_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot access this account",
            )

        # Get positions
        portfolio = await service.get_positions(account_id, force_refresh=force_refresh)

        logger.info(
            "Positions fetched for account",
            extra={
                "user_id": current_user.id,
                "account_id": account_id,
                "positions_count": portfolio.open_positions_count,
            },
        )

        return portfolio

    except NotFoundError as e:
        logger.warning(f"Account not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    except ValidationError as e:
        logger.warning(f"Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    except Exception as e:
        logger.error(f"Error getting positions: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch positions",
        )
