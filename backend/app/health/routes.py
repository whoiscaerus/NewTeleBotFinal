"""
Health Monitoring API Routes - PR-100

Public and admin endpoints for health monitoring and incident management.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import get_db
from backend.app.health.incidents import (
    get_incident,
    get_incidents,
    get_system_health_status,
    investigate_incident,
    resolve_incident,
)
from backend.app.health.models import IncidentSeverity, IncidentStatus

router = APIRouter(prefix="/api/v1/health", tags=["health"])


# Pydantic Schemas


class IncidentOut(BaseModel):
    """Incident response schema."""

    id: int
    type: str
    severity: str
    status: str
    opened_at: str
    resolved_at: Optional[str]
    closed_at: Optional[str]
    notes: Optional[str]
    error_message: Optional[str]
    owner_notified: int

    class Config:
        from_attributes = True


class InvestigateIncidentRequest(BaseModel):
    """Request to mark incident as investigating."""

    admin_user: str = Field(..., description="Admin user investigating")


class ResolveIncidentRequest(BaseModel):
    """Request to resolve an incident."""

    resolution: str = Field(..., min_length=10, description="Resolution description")


class SyntheticCheckOut(BaseModel):
    """Synthetic check response schema."""

    id: int
    probe_name: str
    status: str
    latency_ms: Optional[float]
    checked_at: str
    error_message: Optional[str]

    class Config:
        from_attributes = True


class SystemHealthStatus(BaseModel):
    """System health status for public page."""

    status: str
    uptime_percent: float
    open_incidents: dict
    last_check: Optional[str]
    recent_incidents: list[dict]


# Routes


@router.get("/status", response_model=SystemHealthStatus)
async def get_status(db: AsyncSession = Depends(get_db)):
    """
    Get current system health status (PUBLIC).

    Returns incident summary, uptime %, last check timestamp.
    Used by public status page.

    Business Logic:
        - Count open incidents by severity
        - Calculate uptime from recent checks
        - Return overall status: operational/degraded/down
    """
    status = await get_system_health_status(db)
    return status


@router.get("/incidents", response_model=list[IncidentOut])
async def list_incidents(
    status: Optional[str] = Query(None, description="Filter by status"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    List incidents with pagination and filtering.

    Args:
        status: Filter by status (open, investigating, resolved, closed)
        severity: Filter by severity (low, medium, high, critical)
        limit: Max results (1-100)
        offset: Pagination offset

    Returns:
        List of incidents

    Business Logic:
        - Query incidents from database
        - Apply filters if provided
        - Order by opened_at descending (newest first)
        - Return paginated results
    """
    # Validate status
    status_enum = None
    if status:
        try:
            status_enum = IncidentStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    # Validate severity
    severity_enum = None
    if severity:
        try:
            severity_enum = IncidentSeverity(severity)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid severity: {severity}")

    incidents = await get_incidents(
        db, status=status_enum, severity=severity_enum, limit=limit, offset=offset
    )

    return [
        IncidentOut(
            id=i.id,
            type=i.type,
            severity=i.severity.value,
            status=i.status.value,
            opened_at=i.opened_at.isoformat(),
            resolved_at=i.resolved_at.isoformat() if i.resolved_at else None,
            closed_at=i.closed_at.isoformat() if i.closed_at else None,
            notes=i.notes,
            error_message=i.error_message,
            owner_notified=i.owner_notified,
        )
        for i in incidents
    ]


@router.get("/incidents/{incident_id}", response_model=IncidentOut)
async def get_incident_detail(incident_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get detailed information about a specific incident.

    Args:
        incident_id: Incident ID

    Returns:
        Incident details

    Business Logic:
        - Fetch incident from database
        - Return 404 if not found
        - Return full incident details
    """
    incident = await get_incident(db, incident_id)

    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")

    return IncidentOut(
        id=incident.id,
        type=incident.type,
        severity=incident.severity.value,
        status=incident.status.value,
        opened_at=incident.opened_at.isoformat(),
        resolved_at=incident.resolved_at.isoformat() if incident.resolved_at else None,
        closed_at=incident.closed_at.isoformat() if incident.closed_at else None,
        notes=incident.notes,
        error_message=incident.error_message,
        owner_notified=incident.owner_notified,
    )


@router.post("/incidents/{incident_id}/investigate", response_model=IncidentOut)
async def investigate(
    incident_id: int,
    request: InvestigateIncidentRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Mark incident as under investigation (ADMIN ONLY).

    Args:
        incident_id: Incident ID
        request: Investigation request with admin user

    Returns:
        Updated incident

    Business Logic:
        - Validate incident exists
        - Validate state transition (open → investigating)
        - Update incident status
        - Log admin action
    """
    # In production, this would require admin authentication
    # current_user = Depends(get_current_admin_user)

    try:
        incident = await investigate_incident(db, incident_id, request.admin_user)
        return IncidentOut(
            id=incident.id,
            type=incident.type,
            severity=incident.severity.value,
            status=incident.status.value,
            opened_at=incident.opened_at.isoformat(),
            resolved_at=(
                incident.resolved_at.isoformat() if incident.resolved_at else None
            ),
            closed_at=incident.closed_at.isoformat() if incident.closed_at else None,
            notes=incident.notes,
            error_message=incident.error_message,
            owner_notified=incident.owner_notified,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/incidents/{incident_id}/resolve", response_model=IncidentOut)
async def resolve(
    incident_id: int,
    request: ResolveIncidentRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Resolve an incident (ADMIN ONLY).

    Args:
        incident_id: Incident ID
        request: Resolution request with description

    Returns:
        Updated incident

    Business Logic:
        - Validate incident exists
        - Validate state transition (investigating → resolved)
        - Calculate downtime
        - Update incident status
    """
    # In production, this would require admin authentication
    # current_user = Depends(get_current_admin_user)

    try:
        incident = await resolve_incident(db, incident_id, request.resolution)
        return IncidentOut(
            id=incident.id,
            type=incident.type,
            severity=incident.severity.value,
            status=incident.status.value,
            opened_at=incident.opened_at.isoformat(),
            resolved_at=(
                incident.resolved_at.isoformat() if incident.resolved_at else None
            ),
            closed_at=incident.closed_at.isoformat() if incident.closed_at else None,
            notes=incident.notes,
            error_message=incident.error_message,
            owner_notified=incident.owner_notified,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/synthetics", response_model=list[SyntheticCheckOut])
async def list_synthetic_checks(
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    List recent synthetic check results.

    Args:
        limit: Max results (1-100)

    Returns:
        List of synthetic check results

    Business Logic:
        - Query recent synthetic checks
        - Order by checked_at descending
        - Return results for status dashboard
    """
    from sqlalchemy import select

    from backend.app.health.models import SyntheticCheck

    stmt = (
        select(SyntheticCheck).order_by(SyntheticCheck.checked_at.desc()).limit(limit)
    )
    result = await db.execute(stmt)
    checks = result.scalars().all()

    return [
        SyntheticCheckOut(
            id=c.id,
            probe_name=c.probe_name,
            status=c.status.value,
            latency_ms=c.latency_ms,
            checked_at=c.checked_at.isoformat(),
            error_message=c.error_message,
        )
        for c in checks
    ]
