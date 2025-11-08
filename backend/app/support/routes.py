"""Support ticket API routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from prometheus_client import Counter
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.dependencies import get_current_user
from backend.app.core.db import get_db
from backend.app.messaging.integrations import telegram_owner
from backend.app.support import service
from backend.app.support.schemas import (
    TicketCloseIn,
    TicketCreateIn,
    TicketListOut,
    TicketOut,
    TicketUpdateIn,
)
from backend.app.auth.models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/support", tags=["support"])

# Prometheus metrics
tickets_opened_total = Counter(
    "tickets_opened_total",
    "Total support tickets opened (severity: low|medium|high|urgent)",
    ["severity"],
)

tickets_resolved_total = Counter(
    "tickets_resolved_total",
    "Total support tickets resolved",
)


@router.post("/tickets", status_code=status.HTTP_201_CREATED, response_model=TicketOut)
async def create_ticket(
    request: TicketCreateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new support ticket.

    Creates a ticket for human support escalation. Tickets can originate from
    AI chat escalation, web form, Telegram bot, or API.

    **Business Rules:**
    - User must be authenticated
    - Subject: 3-200 characters
    - Body: minimum 10 characters
    - Severity: low, medium, high, urgent
    - Urgent tickets trigger Telegram notification to owner

    **Telemetry:** Increments `tickets_opened_total{severity}`

    **Example:**
    ```json
    {
        "subject": "Unable to approve signals",
        "body": "When I try to approve a GOLD signal, I get error 500",
        "severity": "high",
        "channel": "web",
        "context": {"session_id": "abc-123", "signal_id": "xyz-789"}
    }
    ```

    Returns:
        TicketOut: Created ticket with ID
    """
    try:
        # Create ticket
        ticket = await service.create_ticket(
            db=db,
            user_id=current_user.id,
            subject=request.subject,
            body=request.body,
            severity=request.severity,
            channel=request.channel,
            context=request.context,
        )

        # Increment telemetry
        tickets_opened_total.labels(severity=request.severity).inc()

        # Send urgent notification to owner
        if request.severity == "urgent":
            await telegram_owner.send_owner_notification(
                ticket_id=ticket.id,
                user_id=current_user.id,
                subject=request.subject,
                severity=request.severity,
                channel=request.channel,
            )

        logger.info(
            f"Ticket created: {ticket.id}",
            extra={
                "ticket_id": ticket.id,
                "user_id": current_user.id,
                "severity": request.severity,
                "channel": request.channel,
            },
        )

        return ticket

    except ValueError as e:
        logger.error(f"Validation error creating ticket: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    except Exception as e:
        logger.error(f"Error creating ticket: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create ticket",
        )


@router.get("/tickets", response_model=TicketListOut)
async def list_tickets(
    status_filter: str | None = None,
    severity: str | None = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List support tickets for current user.

    Returns paginated list of tickets created by the authenticated user.
    Admins can see all tickets (future enhancement).

    **Query Parameters:**
    - `status_filter`: Filter by status (open, in_progress, resolved, closed)
    - `severity`: Filter by severity (low, medium, high, urgent)
    - `skip`: Pagination offset (default 0)
    - `limit`: Max results (default 50, max 100)

    **Business Rules:**
    - Users see only their own tickets
    - Sorted by: status ASC, severity DESC, created_at DESC
    - Open/urgent tickets appear first

    Returns:
        TicketListOut: Paginated ticket list with total count
    """
    try:
        tickets, total = await service.list_tickets(
            db=db,
            user_id=current_user.id,  # Regular users see only their tickets
            status=status_filter,
            severity=severity,
            skip=skip,
            limit=limit,
        )

        logger.info(
            f"Tickets listed: {len(tickets)}",
            extra={
                "user_id": current_user.id,
                "total": total,
                "skip": skip,
                "limit": limit,
            },
        )

        return TicketListOut(tickets=tickets, total=total, skip=skip, limit=limit)

    except Exception as e:
        logger.error(f"Error listing tickets: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list tickets",
        )


@router.get("/tickets/{ticket_id}", response_model=TicketOut)
async def get_ticket(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get a specific support ticket by ID.

    Retrieves full ticket details including subject, body, status, resolution notes.

    **Business Rules:**
    - User can only access their own tickets
    - Returns 404 if ticket not found or access denied

    Returns:
        TicketOut: Full ticket details
    """
    try:
        ticket = await service.get_ticket(
            db=db,
            ticket_id=ticket_id,
            user_id=current_user.id,  # Access control
        )

        if not ticket:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ticket not found: {ticket_id}",
            )

        logger.info(
            f"Ticket retrieved: {ticket.id}",
            extra={
                "ticket_id": ticket.id,
                "user_id": current_user.id,
            },
        )

        return ticket

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error retrieving ticket: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve ticket",
        )


@router.patch("/tickets/{ticket_id}", response_model=TicketOut)
async def update_ticket(
    ticket_id: str,
    request: TicketUpdateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update a support ticket (Admin/Owner only - future enhancement).

    Updates ticket status, assignment, notes. Currently restricted to ticket owner
    for self-service updates. Admin functionality will be added in future PR.

    **Business Rules:**
    - Cannot reopen closed tickets
    - Changing to "resolved" sets resolved_at timestamp
    - Resolution note visible to user, internal notes are staff-only

    Returns:
        TicketOut: Updated ticket
    """
    try:
        # Verify access (for now, only ticket owner can update)
        ticket = await service.get_ticket(
            db=db, ticket_id=ticket_id, user_id=current_user.id
        )
        if not ticket:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ticket not found: {ticket_id}",
            )

        # Update ticket
        updated_ticket = await service.update_ticket(
            db=db,
            ticket_id=ticket_id,
            status=request.status,
            assigned_to=request.assigned_to,
            resolution_note=request.resolution_note,
            internal_notes=request.internal_notes,
        )

        logger.info(
            f"Ticket updated: {ticket_id}",
            extra={
                "ticket_id": ticket_id,
                "user_id": current_user.id,
                "status": request.status,
            },
        )

        return updated_ticket

    except HTTPException:
        raise

    except ValueError as e:
        logger.error(f"Validation error updating ticket: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    except Exception as e:
        logger.error(f"Error updating ticket: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update ticket",
        )


@router.post("/tickets/{ticket_id}/close", response_model=TicketOut)
async def close_ticket(
    ticket_id: str,
    request: TicketCloseIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Close a support ticket with resolution note (Admin/Owner only - future).

    Marks ticket as closed with required resolution summary. Currently allows
    ticket owner to close own tickets. Admin functionality will be added in future PR.

    **Business Rules:**
    - Resolution note required (minimum 10 characters)
    - Sets closed_at timestamp
    - Cannot close already-closed ticket
    - If not already resolved, also sets resolved_at

    **Telemetry:** Increments `tickets_resolved_total`

    Returns:
        TicketOut: Closed ticket with resolution note
    """
    try:
        # Verify access (for now, only ticket owner can close)
        ticket = await service.get_ticket(
            db=db, ticket_id=ticket_id, user_id=current_user.id
        )
        if not ticket:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ticket not found: {ticket_id}",
            )

        # Close ticket
        closed_ticket = await service.close_ticket(
            db=db,
            ticket_id=ticket_id,
            resolution_note=request.resolution_note,
        )

        # Increment telemetry
        tickets_resolved_total.inc()

        logger.info(
            f"Ticket closed: {ticket_id}",
            extra={
                "ticket_id": ticket_id,
                "user_id": current_user.id,
                "resolution_length": len(request.resolution_note),
            },
        )

        return closed_ticket

    except HTTPException:
        raise

    except ValueError as e:
        logger.error(f"Validation error closing ticket: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    except Exception as e:
        logger.error(f"Error closing ticket: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to close ticket",
        )
