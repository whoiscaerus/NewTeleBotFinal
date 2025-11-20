"""Fraud detection API routes (admin-only)."""

import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.dependencies import require_admin
from backend.app.auth.models import User
from backend.app.core.db import get_db
from backend.app.fraud.models import AnomalyEvent, AnomalySeverity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/fraud", tags=["fraud"])


class AnomalyEventOut(BaseModel):
    """Anomaly event response schema."""

    event_id: str
    user_id: str
    trade_id: str | None = None
    anomaly_type: str
    severity: str
    score: float
    details: dict
    detected_at: datetime
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    status: str
    resolution_note: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True

    @field_validator("details", mode="before")
    @classmethod
    def parse_details(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return {}
        return v


class AnomalyListOut(BaseModel):
    """Paginated anomaly list response."""

    events: list[AnomalyEventOut]
    total: int
    page: int
    page_size: int


class AnomalySummaryOut(BaseModel):
    """Anomaly summary statistics."""

    total_events: int
    by_type: dict[str, int]
    by_severity: dict[str, int]
    by_status: dict[str, int]
    recent_critical: int  # Count in last 24h


class ReviewAnomalyRequest(BaseModel):
    """Request to review an anomaly."""

    status: str = Field(..., pattern="^(investigating|resolved|false_positive)$")
    resolution_note: str | None = Field(None, max_length=2000)


@router.get("/events", response_model=AnomalyListOut)
async def get_fraud_events(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),  # Admin-only
    anomaly_type: str | None = Query(None, description="Filter by anomaly type"),
    severity: str | None = Query(None, description="Filter by severity"),
    status: str | None = Query(None, description="Filter by status"),
    user_id: str | None = Query(None, description="Filter by user_id"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
):
    """Get fraud detection events (admin-only).

    Returns paginated list of detected anomalies with filtering options.

    Business Logic:
        - Admin-only endpoint (requires admin role)
        - Supports filtering by type, severity, status, user
        - Ordered by detected_at DESC (newest first)
        - Pagination with max 100 items per page
    """
    # Build query with filters
    conditions = []

    if anomaly_type:
        conditions.append(AnomalyEvent.anomaly_type == anomaly_type)
    if severity:
        conditions.append(AnomalyEvent.severity == severity)
    if status:
        conditions.append(AnomalyEvent.status == status)
    if user_id:
        conditions.append(AnomalyEvent.user_id == user_id)

    if conditions:
        where_clause = and_(*conditions)
    else:
        where_clause = true()

    # Count total
    count_stmt = select(func.count(AnomalyEvent.event_id)).where(where_clause)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # Fetch page
    offset = (page - 1) * page_size
    stmt = (
        select(AnomalyEvent)
        .where(where_clause)
        .order_by(AnomalyEvent.detected_at.desc())
        .limit(page_size)
        .offset(offset)
    )

    result = await db.execute(stmt)
    events = result.scalars().all()

    logger.info(
        f"Admin {current_user.id} fetched fraud events: "
        f"{len(events)} of {total} (page {page})"
    )

    return AnomalyListOut(
        events=[AnomalyEventOut.model_validate(e) for e in events],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/summary", response_model=AnomalySummaryOut)
async def get_fraud_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),  # Admin-only
):
    """Get fraud detection summary statistics (admin-only).

    Returns aggregated counts by type, severity, and status.

    Business Logic:
        - Admin-only endpoint
        - Counts all anomalies grouped by type/severity/status
        - Includes recent critical count (last 24h)
    """
    # Total events
    total_stmt = select(func.count(AnomalyEvent.event_id))
    total_result = await db.execute(total_stmt)
    total_events = total_result.scalar() or 0

    # By type
    type_stmt = select(
        AnomalyEvent.anomaly_type, func.count(AnomalyEvent.event_id)
    ).group_by(AnomalyEvent.anomaly_type)
    type_result = await db.execute(type_stmt)
    by_type = {row[0]: row[1] for row in type_result.all()}

    # By severity
    severity_stmt = select(
        AnomalyEvent.severity, func.count(AnomalyEvent.event_id)
    ).group_by(AnomalyEvent.severity)
    severity_result = await db.execute(severity_stmt)
    by_severity = {row[0]: row[1] for row in severity_result.all()}

    # By status
    status_stmt = select(
        AnomalyEvent.status, func.count(AnomalyEvent.event_id)
    ).group_by(AnomalyEvent.status)
    status_result = await db.execute(status_stmt)
    by_status = {row[0]: row[1] for row in status_result.all()}

    # Recent critical (last 24h)
    from datetime import timedelta

    recent_cutoff = datetime.utcnow() - timedelta(hours=24)
    recent_stmt = select(func.count(AnomalyEvent.event_id)).where(
        and_(
            AnomalyEvent.severity == AnomalySeverity.CRITICAL.value,
            AnomalyEvent.detected_at >= recent_cutoff,
        )
    )
    recent_result = await db.execute(recent_stmt)
    recent_critical = recent_result.scalar() or 0

    logger.info(f"Admin {current_user.id} fetched fraud summary")

    return AnomalySummaryOut(
        total_events=total_events,
        by_type=by_type,
        by_severity=by_severity,
        by_status=by_status,
        recent_critical=recent_critical,
    )


@router.get("/events/{event_id}", response_model=AnomalyEventOut)
async def get_fraud_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),  # Admin-only
):
    """Get single fraud event by ID (admin-only).

    Business Logic:
        - Admin-only endpoint
        - Returns 404 if event not found
    """
    stmt = select(AnomalyEvent).where(AnomalyEvent.event_id == event_id)
    result = await db.execute(stmt)
    event: AnomalyEvent | None = result.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=404, detail="Anomaly event not found")

    logger.info(f"Admin {current_user.id} viewed fraud event {event_id}")

    return AnomalyEventOut.model_validate(event)


@router.post("/events/{event_id}/review", response_model=AnomalyEventOut)
async def review_fraud_event(
    event_id: str,
    request: ReviewAnomalyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),  # Admin-only
):
    """Review and update anomaly event status (admin-only).

    Business Logic:
        - Admin-only endpoint
        - Updates status to investigating/resolved/false_positive
        - Records reviewer and timestamp
        - Validates status transitions (open → investigating → resolved/false_positive)
    """
    # Fetch event
    stmt = select(AnomalyEvent).where(AnomalyEvent.event_id == event_id)
    result = await db.execute(stmt)
    event: AnomalyEvent | None = result.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=404, detail="Anomaly event not found")

    # Validate status transition
    valid_transitions: dict[str, list[str]] = {
        "open": ["investigating", "false_positive"],
        "investigating": ["resolved", "false_positive"],
        "resolved": [],  # Terminal state
        "false_positive": [],  # Terminal state
    }

    if request.status not in valid_transitions.get(str(event.status), []):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status transition: {event.status} → {request.status}",
        )

    # Update event
    event.status = request.status
    event.reviewed_at = datetime.utcnow()
    event.reviewed_by = current_user.id
    if request.resolution_note:
        event.resolution_note = request.resolution_note

    await db.commit()
    await db.refresh(event)

    logger.info(
        f"Admin {current_user.id} reviewed fraud event {event_id}: "
        f"status={request.status}"
    )

    return AnomalyEventOut.model_validate(event)
