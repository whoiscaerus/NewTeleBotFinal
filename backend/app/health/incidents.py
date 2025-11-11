"""
Incident Management System - PR-100

Handles incident lifecycle: creation, investigation, resolution, auto-closure.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.health.models import (
    Incident,
    IncidentSeverity,
    IncidentStatus,
    RemediationAction,
    RemediationStatus,
    SyntheticCheck,
    SyntheticStatus,
)
from backend.app.health.remediator import RemediationResult
from backend.app.health.synthetics import SyntheticProbeResult

logger = logging.getLogger(__name__)


async def create_incident(
    db: AsyncSession,
    probe_result: SyntheticProbeResult,
    severity: IncidentSeverity = IncidentSeverity.MEDIUM,
    notify_owner: bool = True,
) -> Incident:
    """
    Create a new incident from a failed synthetic probe.

    Args:
        db: Database session
        probe_result: Result from synthetic probe
        severity: Incident severity level
        notify_owner: Whether to send notification to system owner

    Returns:
        Created Incident object

    Business Logic:
        - Check for existing open incident of same type (deduplication)
        - If exists, update with latest error
        - If new, create incident record
        - Create SyntheticCheck record
        - Send owner notification if critical
        - Return incident for remediation
    """
    incident_type = f"{probe_result.probe_name}_failure"

    # Check for existing open incident of this type (deduplication)
    stmt = select(Incident).where(
        and_(
            Incident.type == incident_type,
            Incident.status.in_([IncidentStatus.OPEN, IncidentStatus.INVESTIGATING]),
        )
    )
    result = await db.execute(stmt)
    existing_incident = result.scalars().first()

    if existing_incident:
        logger.info(f"Existing incident found: {existing_incident.id}, updating...")
        existing_incident.error_message = probe_result.error_message
        await db.commit()
        await db.refresh(existing_incident)

        # Create new synthetic check linked to existing incident
        synthetic_check = SyntheticCheck(
            probe_name=probe_result.probe_name,
            status=probe_result.status,
            latency_ms=probe_result.latency_ms,
            error_message=probe_result.error_message,
            incident_id=existing_incident.id,
        )
        db.add(synthetic_check)
        await db.commit()

        return existing_incident

    # Create new incident
    incident = Incident(
        type=incident_type,
        severity=severity,
        status=IncidentStatus.OPEN,
        error_message=probe_result.error_message,
        owner_notified=(
            1 if notify_owner and severity == IncidentSeverity.CRITICAL else 0
        ),
    )
    db.add(incident)
    await db.flush()

    # Create synthetic check record
    synthetic_check = SyntheticCheck(
        probe_name=probe_result.probe_name,
        status=probe_result.status,
        latency_ms=probe_result.latency_ms,
        error_message=probe_result.error_message,
        incident_id=incident.id,
    )
    db.add(synthetic_check)

    await db.commit()
    await db.refresh(incident)

    logger.info(
        f"Incident created: {incident.id} ({incident.type}) severity={incident.severity}"
    )

    # Notify owner if critical (in production, send Telegram DM)
    if notify_owner and severity == IncidentSeverity.CRITICAL:
        await _notify_owner(incident)

    return incident


async def investigate_incident(
    db: AsyncSession, incident_id: int, admin_user: str = "system"
) -> Incident:
    """
    Mark incident as under investigation.

    Args:
        db: Database session
        incident_id: Incident ID
        admin_user: Admin user investigating

    Returns:
        Updated Incident object

    Business Logic:
        - Validate incident exists
        - Validate state transition (open → investigating)
        - Update status and notes
        - Log admin action
    """
    stmt = select(Incident).where(Incident.id == incident_id)
    result = await db.execute(stmt)
    incident = result.scalars().first()

    if not incident:
        logger.error(f"Incident {incident_id} not found")
        raise ValueError(f"Incident {incident_id} not found")

    if not incident.can_transition_to(IncidentStatus.INVESTIGATING):
        logger.error(
            f"Invalid transition from {incident.status} to {IncidentStatus.INVESTIGATING}"
        )
        raise ValueError(
            f"Cannot transition from {incident.status} to {IncidentStatus.INVESTIGATING}"
        )

    incident.status = IncidentStatus.INVESTIGATING
    incident.notes = (
        incident.notes or ""
    ) + f"\n[{datetime.utcnow().isoformat()}] Under investigation by {admin_user}"

    await db.commit()
    await db.refresh(incident)

    logger.info(f"Incident {incident_id} marked as investigating by {admin_user}")
    return incident


async def resolve_incident(
    db: AsyncSession,
    incident_id: int,
    resolution: str,
    remediation_result: Optional[RemediationResult] = None,
) -> Incident:
    """
    Mark incident as resolved.

    Args:
        db: Database session
        incident_id: Incident ID
        resolution: Resolution description
        remediation_result: Optional remediation result to link

    Returns:
        Updated Incident object

    Business Logic:
        - Validate incident exists
        - Validate state transition (investigating → resolved)
        - Link remediation action if provided
        - Calculate downtime duration
        - Update status and resolution notes
    """
    stmt = select(Incident).where(Incident.id == incident_id)
    result = await db.execute(stmt)
    incident = result.scalars().first()

    if not incident:
        logger.error(f"Incident {incident_id} not found")
        raise ValueError(f"Incident {incident_id} not found")

    # Allow direct resolution from OPEN state (auto-remediation)
    if incident.status not in [IncidentStatus.OPEN, IncidentStatus.INVESTIGATING]:
        if not incident.can_transition_to(IncidentStatus.RESOLVED):
            logger.error(
                f"Invalid transition from {incident.status} to {IncidentStatus.RESOLVED}"
            )
            raise ValueError(
                f"Cannot transition from {incident.status} to {IncidentStatus.RESOLVED}"
            )

    incident.status = IncidentStatus.RESOLVED
    incident.resolved_at = datetime.utcnow()

    # Calculate downtime
    downtime_minutes = (incident.resolved_at - incident.opened_at).total_seconds() / 60

    incident.notes = (
        (incident.notes or "")
        + f"\n[{incident.resolved_at.isoformat()}] Resolved: {resolution}\nDowntime: {downtime_minutes:.2f} minutes"
    )

    # Link remediation if provided
    if remediation_result:
        remediation_action = RemediationAction(
            incident_id=incident.id,
            action_type=remediation_result.action_type,
            status=(
                RemediationStatus.SUCCESS
                if remediation_result.success
                else RemediationStatus.FAILED
            ),
            executed_at=remediation_result.executed_at,
            completed_at=datetime.utcnow(),
            result=str(remediation_result.to_dict()),
        )
        db.add(remediation_action)

    await db.commit()
    await db.refresh(incident)

    logger.info(f"Incident {incident_id} resolved: {resolution}")
    return incident


async def close_incident(
    db: AsyncSession, incident_id: int, closure_notes: str = "Auto-closed"
) -> Incident:
    """
    Close a resolved incident.

    Args:
        db: Database session
        incident_id: Incident ID
        closure_notes: Closure notes

    Returns:
        Updated Incident object

    Business Logic:
        - Validate incident exists
        - Validate state transition (resolved → closed)
        - Update status and closure notes
    """
    stmt = select(Incident).where(Incident.id == incident_id)
    result = await db.execute(stmt)
    incident = result.scalars().first()

    if not incident:
        logger.error(f"Incident {incident_id} not found")
        raise ValueError(f"Incident {incident_id} not found")

    if not incident.can_transition_to(IncidentStatus.CLOSED):
        logger.error(
            f"Invalid transition from {incident.status} to {IncidentStatus.CLOSED}"
        )
        raise ValueError(
            f"Cannot transition from {incident.status} to {IncidentStatus.CLOSED}"
        )

    incident.status = IncidentStatus.CLOSED
    incident.closed_at = datetime.utcnow()
    incident.notes = (
        incident.notes or ""
    ) + f"\n[{incident.closed_at.isoformat()}] {closure_notes}"

    await db.commit()
    await db.refresh(incident)

    logger.info(f"Incident {incident_id} closed: {closure_notes}")
    return incident


async def auto_close_stale_incidents(
    db: AsyncSession, stale_minutes: int = 30
) -> list[Incident]:
    """
    Auto-close incidents that have been resolved for too long.

    Args:
        db: Database session
        stale_minutes: Minutes after resolution to auto-close

    Returns:
        List of closed incidents

    Business Logic:
        - Query incidents in RESOLVED state
        - Filter by resolved_at older than threshold
        - Close each with auto-close notes
        - Return list of closed incidents
    """
    threshold = datetime.utcnow() - timedelta(minutes=stale_minutes)

    stmt = select(Incident).where(
        and_(
            Incident.status == IncidentStatus.RESOLVED,
            Incident.resolved_at < threshold,
        )
    )
    result = await db.execute(stmt)
    stale_incidents = result.scalars().all()

    closed_incidents = []
    for incident in stale_incidents:
        try:
            closed_incident = await close_incident(
                db,
                incident.id,
                closure_notes=f"Auto-closed after {stale_minutes} minutes",
            )
            closed_incidents.append(closed_incident)
        except Exception as e:
            logger.error(f"Error auto-closing incident {incident.id}: {e}")

    if closed_incidents:
        logger.info(f"Auto-closed {len(closed_incidents)} stale incidents")

    return closed_incidents


async def get_incidents(
    db: AsyncSession,
    status: Optional[IncidentStatus] = None,
    severity: Optional[IncidentSeverity] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Incident]:
    """
    List incidents with optional filtering.

    Args:
        db: Database session
        status: Filter by status (optional)
        severity: Filter by severity (optional)
        limit: Maximum results
        offset: Pagination offset

    Returns:
        List of Incident objects
    """
    stmt = select(Incident)

    if status:
        stmt = stmt.where(Incident.status == status)

    if severity:
        stmt = stmt.where(Incident.severity == severity)

    stmt = stmt.order_by(Incident.opened_at.desc()).limit(limit).offset(offset)

    result = await db.execute(stmt)
    incidents = result.scalars().all()

    return incidents


async def get_incident(db: AsyncSession, incident_id: int) -> Optional[Incident]:
    """Get a single incident by ID."""
    stmt = select(Incident).where(Incident.id == incident_id)
    result = await db.execute(stmt)
    return result.scalars().first()


async def get_system_health_status(db: AsyncSession) -> dict[str, Any]:
    """
    Get current system health status for public status page.

    Returns:
        Dict with incident summary, uptime %, last check timestamp

    Business Logic:
        - Count open incidents by severity
        - Calculate uptime % from incident history
        - Get latest synthetic check results
        - Return summary JSON
    """
    # Count open incidents
    stmt = select(Incident).where(
        Incident.status.in_([IncidentStatus.OPEN, IncidentStatus.INVESTIGATING])
    )
    result = await db.execute(stmt)
    open_incidents = result.scalars().all()

    # Count by severity
    critical_count = sum(
        1 for i in open_incidents if i.severity == IncidentSeverity.CRITICAL
    )
    high_count = sum(1 for i in open_incidents if i.severity == IncidentSeverity.HIGH)
    medium_count = sum(
        1 for i in open_incidents if i.severity == IncidentSeverity.MEDIUM
    )

    # Determine overall status
    if critical_count > 0:
        overall_status = "down"
    elif high_count > 0:
        overall_status = "degraded"
    elif medium_count > 0:
        overall_status = "degraded"
    else:
        overall_status = "operational"

    # Get latest synthetic checks
    stmt = select(SyntheticCheck).order_by(SyntheticCheck.checked_at.desc()).limit(10)
    result = await db.execute(stmt)
    recent_checks = result.scalars().all()

    # Calculate uptime (simplified)
    total_checks = len(recent_checks)
    passed_checks = sum(1 for c in recent_checks if c.status == SyntheticStatus.PASS)
    uptime_percent = (passed_checks / total_checks * 100) if total_checks > 0 else 100

    return {
        "status": overall_status,
        "uptime_percent": round(uptime_percent, 2),
        "open_incidents": {
            "critical": critical_count,
            "high": high_count,
            "medium": medium_count,
            "total": len(open_incidents),
        },
        "last_check": (
            recent_checks[0].checked_at.isoformat() if recent_checks else None
        ),
        "recent_incidents": [
            {
                "id": i.id,
                "type": i.type,
                "severity": i.severity.value,
                "opened_at": i.opened_at.isoformat(),
            }
            for i in open_incidents[:5]
        ],
    }


async def _notify_owner(incident: Incident):
    """
    Send notification to system owner about critical incident.

    In production, this would send a Telegram DM.
    For testing, just log the notification.
    """
    logger.warning(
        f"CRITICAL INCIDENT NOTIFICATION: {incident.type} (ID: {incident.id}) - {incident.error_message}"
    )
    # In production:
    # await telegram_client.send_message(
    #     chat_id=OWNER_CHAT_ID,
    #     text=f"🚨 CRITICAL: {incident.type}\n{incident.error_message}"
    # )
