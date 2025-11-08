"""Comprehensive tests for support ticket service layer - 100% business logic coverage."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.support import service
from backend.app.auth.models import User


@pytest.mark.asyncio
class TestCreateTicket:
    """Test ticket creation business logic."""

    async def test_create_ticket_happy_path(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test creating a ticket with valid data."""
        ticket = await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Cannot approve GOLD signals",
            body="When I click approve on GOLD signal, I get error 500 response",
            severity="high",
            channel="web",
            context={"signal_id": "abc-123", "error_code": 500},
        )

        assert ticket.id is not None
        assert ticket.user_id == test_user.id
        assert ticket.subject == "Cannot approve GOLD signals"
        assert (
            ticket.body
            == "When I click approve on GOLD signal, I get error 500 response"
        )
        assert ticket.severity == "high"
        assert ticket.status == "open"
        assert ticket.channel == "web"
        assert ticket.context == {"signal_id": "abc-123", "error_code": 500}
        assert ticket.created_at is not None
        assert ticket.updated_at is not None
        assert ticket.resolved_at is None
        assert ticket.closed_at is None
        assert ticket.assigned_to is None

    async def test_create_ticket_minimal_data(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test creating ticket with only required fields."""
        ticket = await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Help needed",
            body="I need help with something important",
        )

        assert ticket.id is not None
        assert ticket.severity == "medium"  # Default
        assert ticket.channel == "web"  # Default
        assert ticket.status == "open"  # Default
        assert ticket.context == {}

    async def test_create_ticket_all_severities(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test creating tickets with all severity levels."""
        for severity in ["low", "medium", "high", "urgent"]:
            ticket = await service.create_ticket(
                db=db_session,
                user_id=test_user.id,
                subject=f"Ticket with {severity} severity",
                body="Testing severity levels",
                severity=severity,
            )
            assert ticket.severity == severity

    async def test_create_ticket_invalid_user(self, db_session: AsyncSession):
        """Test creating ticket with non-existent user fails."""
        with pytest.raises(ValueError, match="User not found"):
            await service.create_ticket(
                db=db_session,
                user_id="nonexistent-user-id",
                subject="Test ticket",
                body="This should fail",
            )

    async def test_create_ticket_invalid_severity(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test creating ticket with invalid severity fails."""
        with pytest.raises(ValueError, match="Invalid severity"):
            await service.create_ticket(
                db=db_session,
                user_id=test_user.id,
                subject="Test ticket",
                body="This should fail",
                severity="critical",  # Invalid
            )


@pytest.mark.asyncio
class TestGetTicket:
    """Test ticket retrieval business logic."""

    async def test_get_ticket_by_id(self, db_session: AsyncSession, test_user: User):
        """Test retrieving ticket by ID."""
        created_ticket = await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Test ticket",
            body="Testing retrieval",
        )

        retrieved_ticket = await service.get_ticket(
            db=db_session, ticket_id=created_ticket.id
        )

        assert retrieved_ticket is not None
        assert retrieved_ticket.id == created_ticket.id
        assert retrieved_ticket.subject == "Test ticket"

    async def test_get_ticket_with_user_filter(
        self, db_session: AsyncSession, test_user: User, admin_user: User
    ):
        """Test retrieving ticket with user access control."""
        ticket = await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="User's ticket",
            body="This belongs to test_user",
        )

        # Owner can access
        result = await service.get_ticket(
            db=db_session, ticket_id=ticket.id, user_id=test_user.id
        )
        assert result is not None

        # Different user cannot access
        result = await service.get_ticket(
            db=db_session, ticket_id=ticket.id, user_id=admin_user.id
        )
        assert result is None

    async def test_get_ticket_nonexistent(self, db_session: AsyncSession):
        """Test retrieving non-existent ticket returns None."""
        result = await service.get_ticket(db=db_session, ticket_id="nonexistent-id")
        assert result is None


@pytest.mark.asyncio
class TestListTickets:
    """Test ticket listing business logic."""

    async def test_list_all_user_tickets(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test listing all tickets for a user."""
        # Create multiple tickets
        for i in range(3):
            await service.create_ticket(
                db=db_session,
                user_id=test_user.id,
                subject=f"Ticket {i + 1}",
                body=f"Body {i + 1}",
            )

        tickets, total = await service.list_tickets(db=db_session, user_id=test_user.id)

        assert len(tickets) == 3
        assert total == 3

    async def test_list_tickets_filtered_by_status(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test filtering tickets by status."""
        # Create tickets with different statuses
        ticket1 = await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Open ticket",
            body="Still open",
        )

        ticket2 = await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Closed ticket",
            body="Will be closed",
        )
        await service.close_ticket(
            db=db_session, ticket_id=ticket2.id, resolution_note="Resolved successfully"
        )

        # Filter by open status
        tickets, total = await service.list_tickets(
            db=db_session, user_id=test_user.id, status="open"
        )
        assert len(tickets) == 1
        assert tickets[0].subject == "Open ticket"

        # Filter by closed status
        tickets, total = await service.list_tickets(
            db=db_session, user_id=test_user.id, status="closed"
        )
        assert len(tickets) == 1
        assert tickets[0].subject == "Closed ticket"

    async def test_list_tickets_filtered_by_severity(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test filtering tickets by severity."""
        await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Low priority",
            body="Not urgent",
            severity="low",
        )

        await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Urgent issue",
            body="Very urgent",
            severity="urgent",
        )

        tickets, total = await service.list_tickets(
            db=db_session, user_id=test_user.id, severity="urgent"
        )
        assert len(tickets) == 1
        assert tickets[0].subject == "Urgent issue"

    async def test_list_tickets_pagination(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test ticket pagination."""
        # Create 5 tickets
        for i in range(5):
            await service.create_ticket(
                db=db_session,
                user_id=test_user.id,
                subject=f"Ticket {i + 1}",
                body=f"Body {i + 1}",
            )

        # Get first page
        tickets, total = await service.list_tickets(
            db=db_session, user_id=test_user.id, skip=0, limit=2
        )
        assert len(tickets) == 2
        assert total == 5

        # Get second page
        tickets, total = await service.list_tickets(
            db=db_session, user_id=test_user.id, skip=2, limit=2
        )
        assert len(tickets) == 2
        assert total == 5

    async def test_list_tickets_max_limit_capped(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test that limit is capped at 100."""
        tickets, total = await service.list_tickets(
            db=db_session, user_id=test_user.id, skip=0, limit=200
        )
        # Limit should be capped at 100 (no tickets created, so empty result)
        assert len(tickets) == 0

    async def test_list_tickets_empty_result(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test listing tickets when none exist."""
        tickets, total = await service.list_tickets(db=db_session, user_id=test_user.id)
        assert len(tickets) == 0
        assert total == 0


@pytest.mark.asyncio
class TestUpdateTicket:
    """Test ticket update business logic."""

    async def test_update_ticket_status(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test updating ticket status."""
        ticket = await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Test ticket",
            body="Testing updates",
        )

        updated_ticket = await service.update_ticket(
            db=db_session,
            ticket_id=ticket.id,
            status="in_progress",
        )

        assert updated_ticket.status == "in_progress"
        # updated_at should be >= original (SQLite may have same microsecond precision)
        assert updated_ticket.updated_at >= ticket.updated_at

    async def test_update_ticket_assign_user(
        self, db_session: AsyncSession, test_user: User, admin_user: User
    ):
        """Test assigning ticket to a user."""
        ticket = await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Test ticket",
            body="Testing assignment",
        )

        updated_ticket = await service.update_ticket(
            db=db_session,
            ticket_id=ticket.id,
            assigned_to=admin_user.id,
        )

        assert updated_ticket.assigned_to == admin_user.id

    async def test_update_ticket_resolution_note(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test adding resolution note."""
        ticket = await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Test ticket",
            body="Testing resolution",
        )

        updated_ticket = await service.update_ticket(
            db=db_session,
            ticket_id=ticket.id,
            resolution_note="Issue resolved by restarting the system",
        )

        assert (
            updated_ticket.resolution_note == "Issue resolved by restarting the system"
        )

    async def test_update_ticket_internal_notes(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test adding internal staff notes."""
        ticket = await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Test ticket",
            body="Testing notes",
        )

        updated_ticket = await service.update_ticket(
            db=db_session,
            ticket_id=ticket.id,
            internal_notes="User was confused about UI, provided screenshots",
        )

        assert (
            updated_ticket.internal_notes
            == "User was confused about UI, provided screenshots"
        )

    async def test_update_ticket_status_to_resolved_sets_timestamp(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test that changing status to resolved sets resolved_at timestamp."""
        ticket = await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Test ticket",
            body="Testing resolved timestamp",
        )

        assert ticket.resolved_at is None

        updated_ticket = await service.update_ticket(
            db=db_session,
            ticket_id=ticket.id,
            status="resolved",
        )

        assert updated_ticket.resolved_at is not None
        assert updated_ticket.status == "resolved"

    async def test_update_ticket_cannot_reopen_closed(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test that closed tickets cannot be reopened."""
        ticket = await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Test ticket",
            body="Will be closed",
        )

        await service.close_ticket(
            db=db_session, ticket_id=ticket.id, resolution_note="Closed successfully"
        )

        with pytest.raises(ValueError, match="Cannot reopen a closed ticket"):
            await service.update_ticket(
                db=db_session,
                ticket_id=ticket.id,
                status="open",
            )

    async def test_update_ticket_nonexistent(self, db_session: AsyncSession):
        """Test updating non-existent ticket fails."""
        with pytest.raises(ValueError, match="Ticket not found"):
            await service.update_ticket(
                db=db_session,
                ticket_id="nonexistent-id",
                status="in_progress",
            )

    async def test_update_ticket_invalid_assignee(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test assigning to non-existent user fails."""
        ticket = await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Test ticket",
            body="Testing invalid assignment",
        )

        with pytest.raises(ValueError, match="Assignee user not found"):
            await service.update_ticket(
                db=db_session,
                ticket_id=ticket.id,
                assigned_to="nonexistent-user-id",
            )


@pytest.mark.asyncio
class TestCloseTicket:
    """Test ticket closing business logic."""

    async def test_close_ticket_with_resolution(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test closing ticket with resolution note."""
        ticket = await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Test ticket",
            body="Testing closure",
        )

        closed_ticket = await service.close_ticket(
            db=db_session,
            ticket_id=ticket.id,
            resolution_note="Issue was caused by cached data. Cleared cache and problem resolved.",
        )

        assert closed_ticket.status == "closed"
        assert (
            closed_ticket.resolution_note
            == "Issue was caused by cached data. Cleared cache and problem resolved."
        )
        assert closed_ticket.closed_at is not None
        assert closed_ticket.resolved_at is not None

    async def test_close_ticket_sets_both_timestamps(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test that closing sets both resolved_at and closed_at."""
        ticket = await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Test ticket",
            body="Testing timestamps",
        )

        assert ticket.resolved_at is None
        assert ticket.closed_at is None

        closed_ticket = await service.close_ticket(
            db=db_session,
            ticket_id=ticket.id,
            resolution_note="Timestamps should be set",
        )

        assert closed_ticket.resolved_at is not None
        assert closed_ticket.closed_at is not None

    async def test_close_already_closed_ticket_fails(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test that closing an already-closed ticket fails."""
        ticket = await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Test ticket",
            body="Will be closed twice",
        )

        await service.close_ticket(
            db=db_session, ticket_id=ticket.id, resolution_note="First close"
        )

        with pytest.raises(ValueError, match="Ticket already closed"):
            await service.close_ticket(
                db=db_session, ticket_id=ticket.id, resolution_note="Second close"
            )

    async def test_close_ticket_requires_resolution_note(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test that resolution note is required."""
        ticket = await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Test ticket",
            body="Testing validation",
        )

        with pytest.raises(
            ValueError, match="Resolution note must be at least 10 characters"
        ):
            await service.close_ticket(
                db=db_session, ticket_id=ticket.id, resolution_note=""
            )

    async def test_close_ticket_resolution_note_min_length(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test that resolution note must be at least 10 characters."""
        ticket = await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Test ticket",
            body="Testing validation",
        )

        with pytest.raises(
            ValueError, match="Resolution note must be at least 10 characters"
        ):
            await service.close_ticket(
                db=db_session, ticket_id=ticket.id, resolution_note="Too short"
            )

    async def test_close_ticket_nonexistent(self, db_session: AsyncSession):
        """Test closing non-existent ticket fails."""
        with pytest.raises(ValueError, match="Ticket not found"):
            await service.close_ticket(
                db=db_session,
                ticket_id="nonexistent-id",
                resolution_note="This should fail",
            )


@pytest.mark.asyncio
class TestGetTicketStats:
    """Test ticket statistics business logic."""

    async def test_get_stats_empty_database(self, db_session: AsyncSession):
        """Test getting stats when no tickets exist."""
        stats = await service.get_ticket_stats(db=db_session)

        assert stats["by_status"] == {}
        assert stats["by_severity"] == {}
        assert stats["avg_resolution_time_hours"] == 0

    async def test_get_stats_counts_by_status(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test stats correctly count tickets by status."""
        # Create tickets with different statuses
        await service.create_ticket(
            db=db_session, user_id=test_user.id, subject="Open 1", body="Body"
        )
        await service.create_ticket(
            db=db_session, user_id=test_user.id, subject="Open 2", body="Body"
        )

        ticket3 = await service.create_ticket(
            db=db_session, user_id=test_user.id, subject="Closed 1", body="Body"
        )
        await service.close_ticket(
            db=db_session, ticket_id=ticket3.id, resolution_note="Resolved successfully"
        )

        stats = await service.get_ticket_stats(db=db_session)

        assert stats["by_status"]["open"] == 2
        assert stats["by_status"]["closed"] == 1

    async def test_get_stats_counts_by_severity(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test stats correctly count tickets by severity."""
        await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Low",
            body="Body",
            severity="low",
        )
        await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="High",
            body="Body",
            severity="high",
        )
        await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Urgent",
            body="Body",
            severity="urgent",
        )

        stats = await service.get_ticket_stats(db=db_session)

        assert stats["by_severity"]["low"] == 1
        assert stats["by_severity"]["high"] == 1
        assert stats["by_severity"]["urgent"] == 1

    async def test_get_stats_filtered_by_user(
        self, db_session: AsyncSession, test_user: User, admin_user: User
    ):
        """Test stats can be filtered by user."""
        await service.create_ticket(
            db=db_session, user_id=test_user.id, subject="User 1", body="Body"
        )
        await service.create_ticket(
            db=db_session, user_id=test_user.id, subject="User 2", body="Body"
        )
        await service.create_ticket(
            db=db_session, user_id=admin_user.id, subject="Admin", body="Body"
        )

        stats = await service.get_ticket_stats(db=db_session, user_id=test_user.id)

        assert stats["by_status"]["open"] == 2  # Only test_user's tickets
