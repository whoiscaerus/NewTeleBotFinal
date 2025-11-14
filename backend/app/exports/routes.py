"""
PR-057: Export Routes

API endpoints for generating exports and accessing public share links.
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.models import User
from backend.app.core.db import get_db
from backend.app.exports.service import ExportService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/exports", tags=["exports"])


class ExportRequest(BaseModel):
    """Request to create an export."""

    format: str = Field(..., pattern="^(csv|json)$", description="Export format")
    create_share_link: bool = Field(
        False, description="Whether to create a public share link"
    )
    expires_in_hours: int = Field(
        24, ge=1, le=168, description="Share link expiration (hours)"
    )
    max_accesses: int = Field(
        1, ge=1, le=100, description="Maximum access count for share link"
    )


class ExportResponse(BaseModel):
    """Response with export data or share link."""

    format: str
    trade_count: int
    share_token: str | None = None
    share_url: str | None = None
    expires_at: str | None = None
    message: str


@router.post("", summary="Create trade history export", response_model=None)
async def create_export(
    request: ExportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create trade history export for current user.

    Returns either:
    - Direct export data (if create_share_link=False)
    - Public share link (if create_share_link=True)

    Args:
        request: Export request with format and share link options
        current_user: Authenticated user
        db: Database session

    Returns:
        ExportResponse with export details or share link

    Raises:
        400: Invalid format or no trades found
        500: Export generation error
    """
    try:
        service = ExportService(db)

        logger.info(
            f"Export request from user {current_user.id}: format={request.format}, "
            f"share={request.create_share_link}"
        )

        if request.create_share_link:
            # Create share token (PII redacted for public access)
            token = await service.create_share_token(
                user_id=current_user.id,
                format=request.format,
                expires_in_hours=request.expires_in_hours,
                max_accesses=request.max_accesses,
            )

            # Generate share URL
            share_url = f"/api/v1/exports/share/{token.token}"

            # Count trades for response
            export_data = await service.generate_export(
                user_id=current_user.id, format=request.format, redact_pii=True
            )

            logger.info(
                f"exports_generated_total{{format={request.format},type=share}}"
            )

            return ExportResponse(
                format=request.format,
                trade_count=export_data["trade_count"],
                share_token=token.token,
                share_url=share_url,
                expires_at=token.expires_at.isoformat(),
                message=f"Share link created. Valid for {request.expires_in_hours} hours, max {request.max_accesses} accesses.",
            )
        else:
            # Generate direct export (no PII redaction for owner)
            export_data = await service.generate_export(
                user_id=current_user.id, format=request.format, redact_pii=False
            )

            logger.info(
                f"exports_generated_total{{format={request.format},type=direct}}"
            )

            # Return export as downloadable file
            if request.format == "csv":
                return Response(
                    content=export_data["data"],
                    media_type="text/csv",
                    headers={
                        "Content-Disposition": f'attachment; filename="trades_{current_user.id}.csv"'
                    },
                )
            else:  # json
                return Response(
                    content=json.dumps(export_data["data"], indent=2),
                    media_type="application/json",
                    headers={
                        "Content-Disposition": f'attachment; filename="trades_{current_user.id}.json"'
                    },
                )

    except ValueError as e:
        logger.warning(f"Export validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Export generation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate export")


@router.get("/share/{token}", summary="Access public share link")
async def get_shared_export(token: str, db: AsyncSession = Depends(get_db)) -> Response:
    """Access trade history via public share token.

    Token validation:
    - Must not be revoked
    - Must not be expired
    - Must not exceed max accesses

    PII is redacted in shared exports.

    Args:
        token: Share token
        db: Database session

    Returns:
        Export file (CSV or JSON)

    Raises:
        404: Token not found or invalid
        410: Token expired or max accesses reached
        500: Export generation error
    """
    try:
        service = ExportService(db)

        # Fetch token
        export_token = await service.get_token_by_value(token)
        if not export_token:
            logger.warning(f"Share token not found: {token[:8]}...")
            raise HTTPException(status_code=404, detail="Share link not found")

        # Validate token
        if not export_token.is_valid():
            if export_token.revoked:
                reason = "revoked"
            elif export_token.accessed_count >= export_token.max_accesses:
                reason = "max accesses reached"
            else:
                reason = "expired"

            logger.warning(f"Invalid share token: {token[:8]}... ({reason})")
            raise HTTPException(
                status_code=410, detail=f"Share link is no longer valid ({reason})"
            )

        # Generate export with PII redaction
        export_data = await service.generate_export(
            user_id=export_token.user_id, format=export_token.format, redact_pii=True
        )

        # Mark token as accessed
        await service.mark_token_accessed(export_token)

        logger.info(
            f"exports_downloaded_total{{format={export_token.format}}} "
            f"token={token[:8]}..."
        )

        # Return export file
        if export_token.format == "csv":
            return Response(
                content=export_data["data"],
                media_type="text/csv",
                headers={
                    "Content-Disposition": 'attachment; filename="shared_trades.csv"'
                },
            )
        else:  # json
            return Response(
                content=json.dumps(export_data["data"], indent=2),
                media_type="application/json",
                headers={
                    "Content-Disposition": 'attachment; filename="shared_trades.json"'
                },
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Share link access error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to access shared export")


@router.delete("/share/{token}", summary="Revoke share link")
async def revoke_shared_export(
    token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Revoke a public share token.

    Only the token owner can revoke it.

    Args:
        token: Share token to revoke
        current_user: Authenticated user
        db: Database session

    Returns:
        Success message

    Raises:
        404: Token not found
        403: Not token owner
        500: Revocation error
    """
    try:
        service = ExportService(db)

        # Fetch token
        export_token = await service.get_token_by_value(token)
        if not export_token:
            raise HTTPException(status_code=404, detail="Share link not found")

        # Verify ownership
        if export_token.user_id != current_user.id:
            logger.warning(
                f"User {current_user.id} attempted to revoke token owned by {export_token.user_id}"
            )
            raise HTTPException(
                status_code=403, detail="Not authorized to revoke this share link"
            )

        # Revoke token
        await service.revoke_token(export_token)

        return {"message": "Share link revoked successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token revocation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to revoke share link")
