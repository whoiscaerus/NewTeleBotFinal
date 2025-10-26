"""
Account Linking API Routes

Endpoints:
- POST /api/v1/accounts/link - Link new MT5 account
- GET /api/v1/accounts - List user's linked accounts
- GET /api/v1/accounts/{id} - Get account details
- PUT /api/v1/accounts/{id}/primary - Set primary account
- DELETE /api/v1/accounts/{id} - Unlink account
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.accounts.service import (
    AccountLinkCreate,
    AccountLinkingService,
    AccountLinkOut,
)
from backend.app.auth.dependencies import get_current_user
from backend.app.auth.models import User
from backend.app.core.db import get_db
from backend.app.core.errors import NotFoundError, ValidationError
from backend.app.trading.mt5.manager import MT5SessionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])


# ============================================================================
# DEPENDENCIES
# ============================================================================


async def get_account_service(
    db: AsyncSession = Depends(get_db),
) -> AccountLinkingService:
    """Get account linking service."""
    mt5_manager = MT5SessionManager()
    return AccountLinkingService(db, mt5_manager)


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.post("", status_code=status.HTTP_201_CREATED, response_model=AccountLinkOut)
async def link_account(
    request: AccountLinkCreate,
    current_user: User = Depends(get_current_user),
    service: AccountLinkingService = Depends(get_account_service),
) -> AccountLinkOut:
    """
    Link new MT5 account to user.

    Verifies account accessibility before creating link.

    Args:
        request: Account linking request (mt5_account_id, mt5_login)
        current_user: Authenticated user
        service: Account linking service

    Returns:
        Created account link details

    Raises:
        HTTPException: 400 if validation fails, 401 if unauthorized, 500 on error

    Example:
        >>> response = await link_account(
        ...     AccountLinkCreate(
        ...         mt5_account_id="12345678",
        ...         mt5_login="demo1234"
        ...     ),
        ...     current_user=user,
        ...     service=service
        ... )
        >>> assert response.verified_at is not None
    """
    try:
        logger.info(
            f"Linking account for user: {current_user.id}",
            extra={
                "user_id": current_user.id,
                "account_id": request.mt5_account_id,
            },
        )

        link = await service.link_account(
            user_id=current_user.id,
            mt5_account_id=request.mt5_account_id,
            mt5_login=request.mt5_login,
        )

        logger.info(
            "Account linked successfully",
            extra={
                "user_id": current_user.id,
                "link_id": link.id,
                "account_id": request.mt5_account_id,
            },
        )

        return AccountLinkOut.model_validate(link)

    except ValidationError as e:
        logger.warning(f"Account validation failed: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    except NotFoundError as e:
        logger.warning(f"Account not found: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    except Exception as e:
        logger.error(f"Error linking account: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to link account",
        )


@router.get("", response_model=list[AccountLinkOut])
async def list_accounts(
    current_user: User = Depends(get_current_user),
    service: AccountLinkingService = Depends(get_account_service),
) -> list[AccountLinkOut]:
    """
    List all accounts linked to user.

    Returns accounts ordered by primary first, then creation date.

    Args:
        current_user: Authenticated user
        service: Account linking service

    Returns:
        List of linked accounts

    Example:
        >>> accounts = await list_accounts(current_user=user)
        >>> assert accounts[0].is_primary
    """
    try:
        logger.info(f"Listing accounts for user: {current_user.id}")

        accounts = await service.get_user_accounts(current_user.id)

        return [AccountLinkOut.model_validate(acc) for acc in accounts]

    except Exception as e:
        logger.error(f"Error listing accounts: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list accounts",
        )


@router.get("/{account_id}", response_model=AccountLinkOut)
async def get_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
    service: AccountLinkingService = Depends(get_account_service),
) -> AccountLinkOut:
    """
    Get account details.

    Args:
        account_id: Account link ID
        current_user: Authenticated user
        service: Account linking service

    Returns:
        Account link details

    Raises:
        HTTPException: 404 if not found or doesn't belong to user

    Example:
        >>> account = await get_account(account_id="abc123", current_user=user)
        >>> assert account.verified_at is not None
    """
    try:
        logger.info(f"Getting account: {account_id}")

        link = await service.get_account(account_id)

        # Verify ownership
        if link.user_id != current_user.id:
            logger.warning(f"Unauthorized access to account: {account_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot access this account",
            )

        return AccountLinkOut.model_validate(link)

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    except Exception as e:
        logger.error(f"Error getting account: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get account",
        )


@router.put("/{account_id}/primary", response_model=AccountLinkOut)
async def set_primary_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
    service: AccountLinkingService = Depends(get_account_service),
) -> AccountLinkOut:
    """
    Set account as primary for user.

    Unsets previous primary.

    Args:
        account_id: Account link ID to make primary
        current_user: Authenticated user
        service: Account linking service

    Returns:
        Updated account link

    Raises:
        HTTPException: 400 if validation fails, 404 if not found

    Example:
        >>> account = await set_primary_account(account_id="abc123", current_user=user)
        >>> assert account.is_primary
    """
    try:
        logger.info(
            f"Setting primary account: {account_id}",
            extra={"user_id": current_user.id},
        )

        link = await service.set_primary_account(current_user.id, account_id)

        logger.info(
            "Primary account updated",
            extra={"user_id": current_user.id, "account_id": account_id},
        )

        return AccountLinkOut.model_validate(link)

    except ValidationError as e:
        logger.warning(f"Validation failed: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    except Exception as e:
        logger.error(f"Error setting primary account: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to set primary account",
        )


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
    service: AccountLinkingService = Depends(get_account_service),
) -> None:
    """
    Unlink account from user.

    Cannot unlink if only account remains.

    Args:
        account_id: Account link ID to unlink
        current_user: Authenticated user
        service: Account linking service

    Raises:
        HTTPException: 400 if validation fails (only account), 404 if not found

    Example:
        >>> await unlink_account(account_id="abc123", current_user=user)
        >>> accounts = await list_accounts(current_user=user)
        >>> assert len(accounts) == original_count - 1
    """
    try:
        logger.info(
            f"Unlinking account: {account_id}",
            extra={"user_id": current_user.id},
        )

        await service.unlink_account(current_user.id, account_id)

        logger.info(
            "Account unlinked",
            extra={"user_id": current_user.id, "account_id": account_id},
        )

    except ValidationError as e:
        logger.warning(f"Validation failed: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    except Exception as e:
        logger.error(f"Error unlinking account: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unlink account",
        )
