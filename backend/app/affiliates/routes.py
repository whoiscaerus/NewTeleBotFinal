"""API routes for affiliate program."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.affiliates.schema import AffiliateStatsOut, PayoutCreate, PayoutOut
from backend.app.affiliates.service import AffiliateService
from backend.app.auth.dependencies import get_current_user
from backend.app.core.db import get_db
from backend.app.core.errors import APIError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/affiliates", tags=["affiliates"])


@router.post("/register", status_code=201)
async def register_affiliate(
    db: AsyncSession = Depends(get_db),  # noqa: B008
    current_user=Depends(get_current_user),  # noqa: B008
):
    """Register for affiliate program.

    Returns:
        Referral token for creating referral links

    Raises:
        400: Invalid request
        401: Unauthorized
        409: Already registered
    """
    try:
        service = AffiliateService(db)
        token = await service.register_affiliate(current_user.id)

        logger.info(
            f"Affiliate registered: {current_user.id}",
            extra={"user_id": current_user.id},
        )

        return {"token": token, "share_url": f"https://app.example.com/invite/{token}"}

    except APIError as e:
        raise e.to_http_exception() from e
    except Exception as e:
        logger.error(f"Registration failed: {e}", exc_info=True)
        raise APIError(
            status_code=500,
            code="REGISTER_ERROR",
            message="Failed to register affiliate",
        ).to_http_exception() from e


@router.get("/link")
async def get_referral_link(
    db: AsyncSession = Depends(get_db),  # noqa: B008
    current_user=Depends(get_current_user),  # noqa: B008
):
    """Get referral link for affiliate.

    Returns:
        Referral token and full share URL
    """
    try:
        from sqlalchemy import select

        from backend.app.affiliates.models import Affiliate

        result = await db.execute(
            select(Affiliate).where(Affiliate.user_id == current_user.id)
        )
        affiliate = result.scalar()

        if not affiliate:
            raise APIError(
                status_code=404,
                code="NOT_AFFILIATE",
                message="User is not registered as affiliate",
            )

        return {
            "token": affiliate.referral_token,
            "share_url": f"https://app.example.com/invite/{affiliate.referral_token}",
        }

    except APIError as e:
        raise e.to_http_exception() from e
    except Exception as e:
        logger.error(f"Link retrieval failed: {e}", exc_info=True)
        raise APIError(
            status_code=500,
            code="LINK_ERROR",
            message="Failed to get referral link",
        ).to_http_exception() from e


@router.get("/stats", response_model=AffiliateStatsOut)
async def get_stats(
    db: AsyncSession = Depends(get_db),  # noqa: B008
    current_user=Depends(get_current_user),  # noqa: B008
) -> AffiliateStatsOut:
    """Get affiliate earnings statistics.

    Returns:
        Earnings stats and referral metrics
    """
    try:
        service = AffiliateService(db)
        stats = await service.get_stats(current_user.id)
        return stats

    except APIError as e:
        raise e.to_http_exception() from e
    except Exception as e:
        logger.error(f"Stats retrieval failed: {e}", exc_info=True)
        raise APIError(
            status_code=500,
            code="STATS_ERROR",
            message="Failed to retrieve stats",
        ).to_http_exception() from e


@router.post("/payout", response_model=PayoutOut, status_code=201)
async def request_payout(
    request: PayoutCreate,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    current_user=Depends(get_current_user),  # noqa: B008
) -> PayoutOut:
    """Request commission payout.

    Args:
        request: Payout request with amount

    Returns:
        Payout record
    """
    try:
        service = AffiliateService(db)
        payout = await service.request_payout(current_user.id, request.amount)

        logger.info(
            f"Payout requested: {current_user.id} {request.amount}",
            extra={"user_id": current_user.id, "amount": request.amount},
        )

        return payout

    except APIError as e:
        raise e.to_http_exception() from e
    except Exception as e:
        logger.error(f"Payout request failed: {e}", exc_info=True)
        raise APIError(
            status_code=500,
            code="PAYOUT_ERROR",
            message="Failed to request payout",
        ).to_http_exception() from e


@router.get("/history")
async def get_commission_history(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    current_user=Depends(get_current_user),  # noqa: B008
):
    """Get commission history.

    Args:
        limit: Results limit (max 100)
        offset: Results offset

    Returns:
        List of commissions
    """
    try:
        limit = min(limit, 100)

        service = AffiliateService(db)
        commissions = await service.get_commission_history(
            current_user.id,
            limit=limit,
            offset=offset,
        )

        return {"items": commissions, "count": len(commissions), "offset": offset}

    except APIError as e:
        raise e.to_http_exception() from e
    except Exception as e:
        logger.error(f"History retrieval failed: {e}", exc_info=True)
        raise APIError(
            status_code=500,
            code="HISTORY_ERROR",
            message="Failed to retrieve history",
        ).to_http_exception() from e
