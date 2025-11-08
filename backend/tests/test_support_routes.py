"""Comprehensive tests for support ticket routes - API contract validation."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.support import service
from backend.app.auth.models import User


@pytest.mark.asyncio
class TestCreateTicketRoute:
    """Test POST /api/v1/support/tickets endpoint."""

    async def test_create_ticket_success(self, client: AsyncClient, test_user: User):
        """Test creating a ticket via API."""
        response = await client.post(
            "/api/v1/support/tickets",
            json={
                "subject": "Cannot approve GOLD signals",
                "body": "When I click approve, I get error 500",
                "severity": "high",
                "channel": "web",
                "context": {"signal_id": "abc-123"},
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["subject"] == "Cannot approve GOLD signals"
        assert data["severity"] == "high"
        assert data["status"] == "open"
        assert data["user_id"] == test_user.id

    async def test_create_ticket_minimal(self, client: AsyncClient, test_user: User):
        """Test creating ticket with minimal data."""
        response = await client.post(
            "/api/v1/support/tickets",
            json={
                "subject": "Help needed",
                "body": "I need help with something",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["severity"] == "medium"  # Default
        assert data["channel"] == "web"  # Default

    async def test_create_ticket_urgent_triggers_notification(
        self, client: AsyncClient, test_user: User, monkeypatch
    ):
        """Test urgent ticket triggers owner notification."""
        notification_called = False
        notification_args = {}

        async def mock_send_notification(**kwargs):
            nonlocal notification_called, notification_args
            notification_called = True
            notification_args = kwargs
            return True

        monkeypatch.setattr(
            "backend.app.support.routes.telegram_owner.send_owner_notification",
            mock_send_notification,
        )

        response = await client.post(
            "/api/v1/support/tickets",
            json={
                "subject": "URGENT: System down",
                "body": "The entire platform is not accessible",
                "severity": "urgent",
            },
        )

        assert response.status_code == 201
        assert notification_called
        assert notification_args["severity"] == "urgent"

    async def test_create_ticket_requires_auth(self, client: AsyncClient):
        """Test creating ticket without authentication fails."""
        # Override to remove auth dependency
        from backend.app.orchestrator.main import app

        app.dependency_overrides.clear()

        response = await client.post(
            "/api/v1/support/tickets",
            json={
                "subject": "Test",
                "body": "Should fail without auth",
            },
        )

        # Should get 401 or 403 depending on auth implementation
        assert response.status_code in [401, 403]

    async def test_create_ticket_invalid_severity(
        self, client: AsyncClient, test_user: User
    ):
        """Test creating ticket with invalid severity fails."""
        response = await client.post(
            "/api/v1/support/tickets",
            json={
                "subject": "Test ticket",
                "body": "Testing validation",
                "severity": "critical",  # Invalid
            },
        )

        assert response.status_code == 422  # Validation error

    async def test_create_ticket_subject_too_short(self, client: AsyncClient):
        """Test creating ticket with too-short subject fails."""
        response = await client.post(
            "/api/v1/support/tickets",
            json={
                "subject": "Hi",  # Too short (< 3 chars)
                "body": "This should fail validation",
            },
        )

        assert response.status_code == 422

    async def test_create_ticket_body_too_short(self, client: AsyncClient):
        """Test creating ticket with too-short body fails."""
        response = await client.post(
            "/api/v1/support/tickets",
            json={
                "subject": "Valid subject",
                "body": "Short",  # Too short (< 10 chars)
            },
        )

        assert response.status_code == 422


@pytest.mark.asyncio
class TestListTicketsRoute:
    """Test GET /api/v1/support/tickets endpoint."""

    async def test_list_user_tickets(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """Test listing user's own tickets."""
        # Create some tickets for this user
        await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Ticket 1",
            body="First ticket body",
        )
        await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Ticket 2",
            body="Second ticket body",
        )

        response = await client.get("/api/v1/support/tickets")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["tickets"]) == 2

    async def test_list_tickets_filtered_by_status(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """Test filtering tickets by status."""
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
            db=db_session,
            ticket_id=ticket2.id,
            resolution_note="Resolved successfully",
        )

        # Filter by open status
        response = await client.get("/api/v1/support/tickets?status_filter=open")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["tickets"][0]["subject"] == "Open ticket"

    async def test_list_tickets_pagination(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """Test ticket list pagination."""
        # Create 5 tickets
        for i in range(5):
            await service.create_ticket(
                db=db_session,
                user_id=test_user.id,
                subject=f"Ticket {i + 1}",
                body=f"Body {i + 1}",
            )

        # Get first page
        response = await client.get("/api/v1/support/tickets?skip=0&limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["tickets"]) == 2
        assert data["total"] == 5
        assert data["skip"] == 0
        assert data["limit"] == 2

    async def test_list_tickets_empty(self, client: AsyncClient):
        """Test listing tickets when none exist."""
        response = await client.get("/api/v1/support/tickets")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["tickets"]) == 0


@pytest.mark.asyncio
class TestGetTicketRoute:
    """Test GET /api/v1/support/tickets/{id} endpoint."""

    async def test_get_ticket_success(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """Test retrieving a specific ticket."""
        ticket = await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Test ticket",
            body="Testing retrieval",
        )

        response = await client.get(f"/api/v1/support/tickets/{ticket.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == ticket.id
        assert data["subject"] == "Test ticket"

    async def test_get_ticket_not_found(self, client: AsyncClient):
        """Test retrieving non-existent ticket returns 404."""
        response = await client.get("/api/v1/support/tickets/nonexistent-id")

        assert response.status_code == 404

    async def test_get_ticket_access_control(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        admin_user: User,
    ):
        """Test user cannot access other user's tickets."""
        # Create ticket for admin_user
        ticket = await service.create_ticket(
            db=db_session,
            user_id=admin_user.id,
            subject="Admin's ticket",
            body="This belongs to admin",
        )

        # Test_user tries to access it (should fail)
        response = await client.get(f"/api/v1/support/tickets/{ticket.id}")

        assert response.status_code == 404  # Not found due to access control


@pytest.mark.asyncio
class TestUpdateTicketRoute:
    """Test PATCH /api/v1/support/tickets/{id} endpoint."""

    async def test_update_ticket_status(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """Test updating ticket status."""
        ticket = await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Test ticket",
            body="Testing updates",
        )

        response = await client.patch(
            f"/api/v1/support/tickets/{ticket.id}",
            json={"status": "in_progress"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "in_progress"

    async def test_update_ticket_resolution_note(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """Test adding resolution note."""
        ticket = await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Test ticket",
            body="Testing resolution",
        )

        response = await client.patch(
            f"/api/v1/support/tickets/{ticket.id}",
            json={"resolution_note": "Issue resolved by restarting"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["resolution_note"] == "Issue resolved by restarting"

    async def test_update_ticket_not_found(self, client: AsyncClient):
        """Test updating non-existent ticket returns 404."""
        response = await client.patch(
            "/api/v1/support/tickets/nonexistent-id",
            json={"status": "in_progress"},
        )

        assert response.status_code == 404

    async def test_update_ticket_cannot_reopen_closed(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """Test cannot reopen closed ticket."""
        ticket = await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Test ticket",
            body="Will be closed",
        )

        await service.close_ticket(
            db=db_session,
            ticket_id=ticket.id,
            resolution_note="Closed successfully",
        )

        response = await client.patch(
            f"/api/v1/support/tickets/{ticket.id}",
            json={"status": "open"},
        )

        assert response.status_code == 400


@pytest.mark.asyncio
class TestCloseTicketRoute:
    """Test POST /api/v1/support/tickets/{id}/close endpoint."""

    async def test_close_ticket_success(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """Test closing a ticket."""
        ticket = await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Test ticket",
            body="Testing closure",
        )

        response = await client.post(
            f"/api/v1/support/tickets/{ticket.id}/close",
            json={
                "resolution_note": "Issue was caused by cached data. Cleared cache and resolved."
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "closed"
        assert (
            data["resolution_note"]
            == "Issue was caused by cached data. Cleared cache and resolved."
        )
        assert data["closed_at"] is not None

    async def test_close_ticket_requires_resolution_note(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """Test closing ticket without resolution note fails."""
        ticket = await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Test ticket",
            body="Testing validation",
        )

        response = await client.post(
            f"/api/v1/support/tickets/{ticket.id}/close",
            json={"resolution_note": ""},
        )

        assert response.status_code == 422  # Validation error

    async def test_close_ticket_resolution_note_too_short(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """Test closing ticket with too-short resolution note fails."""
        ticket = await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Test ticket",
            body="Testing validation",
        )

        response = await client.post(
            f"/api/v1/support/tickets/{ticket.id}/close",
            json={"resolution_note": "Short"},  # Too short
        )

        assert response.status_code == 422

    async def test_close_already_closed_ticket(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """Test closing already-closed ticket fails."""
        ticket = await service.create_ticket(
            db=db_session,
            user_id=test_user.id,
            subject="Test ticket",
            body="Will be closed twice",
        )

        await service.close_ticket(
            db=db_session,
            ticket_id=ticket.id,
            resolution_note="First close",
        )

        response = await client.post(
            f"/api/v1/support/tickets/{ticket.id}/close",
            json={"resolution_note": "Second close attempt"},
        )

        assert response.status_code == 400

    async def test_close_ticket_not_found(self, client: AsyncClient):
        """Test closing non-existent ticket returns 404."""
        response = await client.post(
            "/api/v1/support/tickets/nonexistent-id/close",
            json={"resolution_note": "This should fail"},
        )

        assert response.status_code == 404


@pytest.mark.asyncio
class TestAIEscalationIntegration:
    """Test AI chat escalation creates support tickets."""

    async def test_escalate_session_creates_ticket(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        monkeypatch,
    ):
        """Test AI escalation endpoint creates support ticket."""
        # First need to create an AI chat session
        from uuid import uuid4

        from backend.app.ai.models import ChatSession

        session = ChatSession(
            id=str(uuid4()),
            user_id=test_user.id,
            title="Test AI Session",
            escalated=False,
        )
        db_session.add(session)
        await db_session.commit()

        # Mock telegram notification
        notification_called = False

        async def mock_send_notification(**kwargs):
            nonlocal notification_called
            notification_called = True
            return True

        monkeypatch.setattr(
            "backend.app.support.routes.telegram_owner.send_owner_notification",
            mock_send_notification,
        )

        # Escalate session
        response = await client.post(
            f"/api/v1/ai/sessions/{session.id}/escalate",
            json={"reason": "AI cannot resolve this issue"},
        )

        assert response.status_code == 204

        # Verify ticket was created
        from sqlalchemy import select

        from backend.app.support.models import Ticket

        result = await db_session.execute(
            select(Ticket).where(Ticket.user_id == test_user.id)
        )
        tickets = result.scalars().all()

        assert len(tickets) == 1
        ticket = tickets[0]
        assert ticket.severity == "high"  # Manual escalations are high priority
        assert ticket.channel == "ai_chat"
        assert str(session.id) in ticket.context["session_id"]
        assert notification_called  # High-severity tickets trigger notification
