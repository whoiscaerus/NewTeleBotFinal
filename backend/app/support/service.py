"""Support ticket service layer - business logic for ticketing system."""

import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.models import User
from backend.app.support.models import Ticket, TicketSeverity, TicketStatus

logger = logging.getLogger(__name__)


async def create_ticket(
    db: AsyncSession,
    user_id: str,
    subject: str,
    body: str,
    severity: str = "medium",
    channel: str = "web",
    context: Optional[dict[str, Any]] = None,
) -> Ticket:
    """
    Create a new support ticket.

    Args:
        db: Database session
        user_id: User creating the ticket
        subject: Brief ticket summary
        body: Detailed description
        severity: Urgency level (low, medium, high, urgent)
        channel: Origin channel (ai_chat, web, telegram, email, api)
        context: Additional metadata (session_id, escalation_reason, etc.)

    Returns:
        Created Ticket object

    Raises:
        ValueError: If user not found or invalid parameters

    Business Rules:
        - Subject must be 3-200 characters
        - Body must be at least 10 characters
        - Severity must be one of: low, medium, high, urgent
        - Tickets default to "open" status
        - SLA clock starts at created_at timestamp
    """
    # Validate user exists
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError(f"User not found: {user_id}")

    # Validate severity
    valid_severities = [s.value for s in TicketSeverity]
    if severity not in valid_severities:
        raise ValueError(
            f"Invalid severity: {severity}. Must be one of: {valid_severities}"
        )

    # Create ticket
    ticket = Ticket(
        user_id=user_id,
        subject=subject,
        body=body,
        severity=severity,
        status=TicketStatus.OPEN.value,
        channel=channel,
        context=context or {},
    )

    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)

    logger.info(
        f"Ticket created: {ticket.id}",
        extra={
            "ticket_id": ticket.id,
            "user_id": user_id,
            "severity": severity,
            "channel": channel,
        },
    )

    return ticket


async def get_ticket(
    db: AsyncSession, ticket_id: str, user_id: Optional[str] = None
) -> Optional[Ticket]:
    """
    Get a ticket by ID with optional user access control.

    Args:
        db: Database session
        ticket_id: Ticket UUID
        user_id: If provided, only return if user owns or is assigned to ticket

    Returns:
        Ticket object or None if not found/access denied

    Business Rules:
        - Regular users can only see their own tickets
        - Admins can see all tickets
        - Assignees can see tickets assigned to them
    """
    query = select(Ticket).where(Ticket.id == ticket_id)

    # Apply user access control
    if user_id:
        query = query.where(
            or_(Ticket.user_id == user_id, Ticket.assigned_to == user_id)
        )

    result = await db.execute(query)
    return result.scalar_one_or_none()


async def list_tickets(
    db: AsyncSession,
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    assigned_to: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[Ticket], int]:
    """
    List tickets with filtering and pagination.

    Args:
        db: Database session
        user_id: Filter by ticket creator (None = all users)
        status: Filter by status (open, in_progress, etc.)
        severity: Filter by severity (low, medium, high, urgent)
        assigned_to: Filter by assignee user_id
        skip: Pagination offset
        limit: Max results (capped at 100)

    Returns:
        Tuple of (ticket list, total count)

    Business Rules:
        - Max limit is 100 to prevent performance issues
        - Default sort: created_at DESC (newest first)
        - Open tickets sorted by severity (urgent > high > medium > low)
    """
    # Cap limit
    limit = min(limit, 100)

    # Build base query
    query = select(Ticket)
    count_query = select(func.count(Ticket.id))

    # Apply filters
    filters = []
    if user_id:
        filters.append(Ticket.user_id == user_id)
    if status:
        filters.append(Ticket.status == status)
    if severity:
        filters.append(Ticket.severity == severity)
    if assigned_to:
        filters.append(Ticket.assigned_to == assigned_to)

    if filters:
        query = query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))

    # Sort: open tickets by severity, then created_at DESC
    query = query.order_by(
        Ticket.status.asc(),  # Open tickets first
        Ticket.severity.desc(),  # Urgent > high > medium > low
        Ticket.created_at.desc(),  # Newest first
    )

    # Pagination
    query = query.offset(skip).limit(limit)

    # Execute
    result = await db.execute(query)
    tickets = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    return list(tickets), total


async def update_ticket(
    db: AsyncSession,
    ticket_id: str,
    status: Optional[str] = None,
    assigned_to: Optional[str] = None,
    resolution_note: Optional[str] = None,
    internal_notes: Optional[str] = None,
) -> Ticket:
    """
    Update an existing ticket.

    Args:
        db: Database session
        ticket_id: Ticket UUID
        status: New status (optional)
        assigned_to: User ID to assign (optional)
        resolution_note: Resolution summary (optional, visible to user)
        internal_notes: Internal staff notes (optional, not visible to user)

    Returns:
        Updated Ticket object

    Raises:
        ValueError: If ticket not found or invalid parameters

    Business Rules:
        - Changing status to "resolved" sets resolved_at timestamp
        - Cannot change status from closed back to open
        - Assigned user must exist in database
        - updated_at timestamp is automatically updated
    """
    # Get existing ticket
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise ValueError(f"Ticket not found: {ticket_id}")

    # Validate status transition
    if (
        status
        and ticket.status == TicketStatus.CLOSED.value
        and status != TicketStatus.CLOSED.value
    ):
        raise ValueError("Cannot reopen a closed ticket")

    # Validate assigned user exists
    if assigned_to:
        result = await db.execute(select(User).where(User.id == assigned_to))
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError(f"Assignee user not found: {assigned_to}")
        ticket.assigned_to = assigned_to

    # Update fields
    if status:
        old_status = ticket.status
        ticket.status = status

        # Set resolved_at if transitioning to resolved
        if (
            status == TicketStatus.RESOLVED.value
            and old_status != TicketStatus.RESOLVED.value
        ):
            ticket.resolved_at = datetime.utcnow()

    if resolution_note is not None:
        ticket.resolution_note = resolution_note

    if internal_notes is not None:
        ticket.internal_notes = internal_notes

    ticket.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(ticket)

    logger.info(
        f"Ticket updated: {ticket.id}",
        extra={
            "ticket_id": ticket.id,
            "status": ticket.status,
            "assigned_to": ticket.assigned_to,
        },
    )

    return ticket


async def close_ticket(
    db: AsyncSession,
    ticket_id: str,
    resolution_note: str,
) -> Ticket:
    """
    Close a ticket with resolution note.

    Args:
        db: Database session
        ticket_id: Ticket UUID
        resolution_note: Required resolution summary (visible to user)

    Returns:
        Closed Ticket object

    Raises:
        ValueError: If ticket not found or already closed

    Business Rules:
        - Ticket must be in "open", "in_progress", "waiting", or "resolved" state
        - Resolution note is required (min 10 characters)
        - Sets closed_at timestamp
        - Cannot close an already-closed ticket
        - If not already resolved, also sets resolved_at
    """
    # Get existing ticket
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise ValueError(f"Ticket not found: {ticket_id}")

    # Validate not already closed
    if ticket.status == TicketStatus.CLOSED.value:
        raise ValueError(f"Ticket already closed: {ticket_id}")

    # Validate resolution note
    if not resolution_note or len(resolution_note.strip()) < 10:
        raise ValueError("Resolution note must be at least 10 characters")

    # Update ticket
    ticket.status = TicketStatus.CLOSED.value
    ticket.resolution_note = resolution_note
    ticket.closed_at = datetime.utcnow()

    # Set resolved_at if not already set
    if not ticket.resolved_at:
        ticket.resolved_at = datetime.utcnow()

    ticket.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(ticket)

    logger.info(
        f"Ticket closed: {ticket.id}",
        extra={
            "ticket_id": ticket.id,
            "user_id": ticket.user_id,
            "resolution_length": len(resolution_note),
        },
    )

    return ticket


async def get_ticket_stats(
    db: AsyncSession, user_id: Optional[str] = None
) -> dict[str, Any]:
    """
    Get ticket statistics.

    Args:
        db: Database session
        user_id: If provided, stats for specific user only

    Returns:
        Dictionary with ticket counts by status and severity

    Business Rules:
        - Provides overview for support dashboard
        - Counts by status (open, in_progress, resolved, closed)
        - Counts by severity (urgent, high, medium, low)
        - Average resolution time for closed tickets
    """
    # Build base queries
    filters = []
    if user_id:
        filters.append(Ticket.user_id == user_id)

    # Count by status
    status_query = select(Ticket.status, func.count(Ticket.id)).group_by(Ticket.status)
    if filters:
        status_query = status_query.where(and_(*filters))

    # Count by severity
    severity_query = select(Ticket.severity, func.count(Ticket.id)).group_by(
        Ticket.severity
    )
    if filters:
        severity_query = severity_query.where(and_(*filters))

    # Execute queries
    status_result = await db.execute(status_query)
    severity_result = await db.execute(severity_query)

    status_counts = {row[0]: row[1] for row in status_result}
    severity_counts = {row[0]: row[1] for row in severity_result}

    # Calculate average resolution time (for closed tickets)
    avg_resolution_query = select(
        func.avg(func.extract("epoch", Ticket.closed_at - Ticket.created_at))
    ).where(Ticket.closed_at.isnot(None))
    if filters:
        avg_resolution_query = avg_resolution_query.where(and_(*filters))

    avg_result = await db.execute(avg_resolution_query)
    avg_resolution_seconds = avg_result.scalar() or 0

    return {
        "by_status": status_counts,
        "by_severity": severity_counts,
        "avg_resolution_time_hours": (
            round(avg_resolution_seconds / 3600, 2) if avg_resolution_seconds else 0
        ),
    }
