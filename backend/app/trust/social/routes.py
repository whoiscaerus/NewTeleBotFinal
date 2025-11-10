"""Social Verification Graph - API Routes.

PR-094: Public endpoints for peer verification.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import get_db
from backend.app.core.logging import get_logger
from backend.app.trust.social.service import (
    AntiSybilError,
    DuplicateVerificationError,
    RateLimitError,
    SelfVerificationError,
    VerificationError,
    calculate_influence_score,
    get_user_verifications,
    verify_peer,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/trust/social", tags=["trust", "social"])


# ============================================================================
# Pydantic Schemas
# ============================================================================


class VerifyPeerRequest(BaseModel):
    """Request schema for peer verification."""

    notes: str | None = Field(
        None, max_length=500, description="Optional verification note"
    )


class VerificationEdgeOut(BaseModel):
    """Response schema for verification edge."""

    id: str
    verifier_id: str
    verified_id: str
    weight: float
    created_at: str
    notes: str | None = None

    class Config:
        from_attributes = True


class UserVerificationsOut(BaseModel):
    """Response schema for user verifications (given + received)."""

    user_id: str
    given: list[VerificationEdgeOut]
    received: list[VerificationEdgeOut]
    influence_score: float = Field(..., ge=0.0, le=1.0)


# ============================================================================
# Routes
# ============================================================================


@router.post("/verify/{peer_id}", response_model=VerificationEdgeOut, status_code=201)
async def verify_peer_endpoint(
    peer_id: str,
    request: Request,
    body: VerifyPeerRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Verify a peer user, creating a trust edge.

    This endpoint creates a directed verification: current user → peer_id.
    Comprehensive anti-sybil checks are applied:
    - Cannot verify yourself
    - Cannot verify same peer twice
    - Rate limits: 5/hour, 20/day per user
    - Anti-sybil: 10/day per IP, 15/day per device
    - Account must be at least 7 days old

    Args:
        peer_id: User ID to verify
        request: FastAPI request (for IP extraction)
        body: Verification request body
        db: Database session

    Returns:
        Created VerificationEdge

    Raises:
        HTTPException:
            - 400: Self-verification or duplicate verification
            - 404: Peer user not found
            - 429: Rate limit exceeded
            - 403: Anti-sybil check failed

    Example:
        POST /api/v1/trust/social/verify/user456
        {
            "notes": "Known trader from Telegram"
        }
        → 201 Created
    """
    # Get current user from JWT (mocked for now - would come from auth middleware)
    # In production, this would be: current_user = Depends(get_current_user)
    # For testing, we'll extract from request state or use a default
    verifier_id = getattr(request.state, "user_id", "test_user_id")

    # Extract IP address from request
    ip_address = request.client.host if request.client else None

    # Extract device fingerprint from headers (if available)
    device_fingerprint = request.headers.get("X-Device-Fingerprint")

    try:
        edge = await verify_peer(
            verifier_id=verifier_id,
            verified_id=peer_id,
            ip_address=ip_address,
            device_fingerprint=device_fingerprint,
            notes=body.notes,
            db=db,
        )

        logger.info(
            f"Verification created via API: {verifier_id} → {peer_id}",
            extra={"verifier_id": verifier_id, "verified_id": peer_id},
        )

        return VerificationEdgeOut(
            id=edge.id,
            verifier_id=edge.verifier_id,
            verified_id=edge.verified_id,
            weight=edge.weight,
            created_at=edge.created_at.isoformat(),
            notes=edge.notes,
        )

    except SelfVerificationError as e:
        logger.warning(f"Self-verification attempted: {verifier_id}")
        raise HTTPException(status_code=400, detail=str(e))

    except DuplicateVerificationError as e:
        logger.warning(f"Duplicate verification attempted: {verifier_id} → {peer_id}")
        raise HTTPException(status_code=400, detail=str(e))

    except RateLimitError as e:
        logger.warning(f"Rate limit exceeded for {verifier_id}: {e}")
        raise HTTPException(status_code=429, detail=str(e))

    except AntiSybilError as e:
        logger.warning(f"Anti-sybil check failed for {verifier_id}: {e}")
        raise HTTPException(status_code=403, detail=str(e))

    except VerificationError as e:
        logger.error(f"Verification error: {e}", exc_info=True)
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error(f"Unexpected error in verify_peer_endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/me", response_model=UserVerificationsOut)
async def get_my_verifications(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Get all verifications for current user (given and received).

    Returns:
        UserVerificationsOut with:
        - given: List of verifications given by user
        - received: List of verifications received by user
        - influence_score: Calculated influence score (0.0-1.0)

    Example:
        GET /api/v1/trust/social/me
        → {
            "user_id": "user123",
            "given": [...],
            "received": [...],
            "influence_score": 0.75
        }
    """
    # Get current user from request state
    user_id = getattr(request.state, "user_id", "test_user_id")

    try:
        verifications = await get_user_verifications(user_id, db)
        influence_score = await calculate_influence_score(user_id, db)

        given_out = [
            VerificationEdgeOut(
                id=edge.id,
                verifier_id=edge.verifier_id,
                verified_id=edge.verified_id,
                weight=edge.weight,
                created_at=edge.created_at.isoformat(),
                notes=edge.notes,
            )
            for edge in verifications["given"]
        ]

        received_out = [
            VerificationEdgeOut(
                id=edge.id,
                verifier_id=edge.verifier_id,
                verified_id=edge.verified_id,
                weight=edge.weight,
                created_at=edge.created_at.isoformat(),
                notes=edge.notes,
            )
            for edge in verifications["received"]
        ]

        logger.info(
            f"Retrieved verifications for {user_id} via API",
            extra={
                "user_id": user_id,
                "given_count": len(given_out),
                "received_count": len(received_out),
                "influence_score": influence_score,
            },
        )

        return UserVerificationsOut(
            user_id=user_id,
            given=given_out,
            received=received_out,
            influence_score=influence_score,
        )

    except Exception as e:
        logger.error(
            f"Error retrieving verifications for {user_id}: {e}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/influence/{user_id}", response_model=dict[str, Any])
async def get_user_influence(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get influence score for a specific user.

    Public endpoint - anyone can query any user's influence score.

    Args:
        user_id: User to get influence for
        db: Database session

    Returns:
        Dict with user_id and influence_score

    Example:
        GET /api/v1/trust/social/influence/user456
        → {
            "user_id": "user456",
            "influence_score": 0.85
        }
    """
    try:
        influence_score = await calculate_influence_score(user_id, db)

        logger.info(
            f"Retrieved influence score for {user_id}",
            extra={"user_id": user_id, "influence_score": influence_score},
        )

        return {"user_id": user_id, "influence_score": influence_score}

    except Exception as e:
        logger.error(f"Error calculating influence for {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
