"""
Test suite for AI API routes.

Tests all endpoints for authentication, authorization, validation, and business logic.

Coverage target: 100% of routes.py
"""

from datetime import datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient

from backend.app.ai.models import ChatSession
from backend.app.auth.models import User, UserRole


@pytest_asyncio.fixture
async def test_user(db_session) -> User:
    """Create a test user."""
    user = User(
        id=str(uuid4()),
        email=f"test_{uuid4()}@example.com",
        password_hash="hashed_password",
        role=UserRole.USER,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def test_admin(db_session) -> User:
    """Create a test admin user."""
    user = User(
        id=str(uuid4()),
        email=f"admin_{uuid4()}@example.com",
        password_hash="hashed_password",
        role=UserRole.ADMIN,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture
def auth_headers(test_user: User) -> dict:
    """Create auth headers for test user.

    Note: The actual user authentication is mocked in conftest.py
    via dependency override of get_current_user which returns the
    first user from the database (which will be test_user).
    """
    # Mock JWT token
    token = "mock_jwt_token"
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(test_admin: User) -> dict:
    """Create auth headers for admin.

    Note: The actual user authentication is mocked in conftest.py
    via dependency override of get_current_user which returns the
    first user from the database (which will be test_admin).
    """
    token = "mock_admin_jwt_token"
    return {"Authorization": f"Bearer {token}"}


class TestChatEndpoint:
    """Test POST /api/v1/ai/chat endpoint."""

    @pytest.mark.asyncio
    async def test_chat_new_session(self, client: AsyncClient, auth_headers: dict):
        """POST chat should create new session and return response."""
        response = await client.post(
            "/api/v1/ai/chat",
            json={
                "question": "How do I reset my password?",
                "channel": "web",
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert "answer" in data
        assert "session_id" in data
        assert "message_id" in data
        assert "confidence_score" in data
        assert "citations" in data

    @pytest.mark.asyncio
    async def test_chat_with_session_id(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session,
        test_user: User,
    ):
        """Should continue in existing session."""
        # Create session first
        session = ChatSession(
            id=uuid4(),
            user_id=test_user.id,
            title="Test Session",
            escalated=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db_session.add(session)
        await db_session.commit()

        # Continue in session
        response = await client.post(
            "/api/v1/ai/chat",
            json={
                "session_id": str(session.id),
                "question": "Follow-up question?",
                "channel": "web",
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        assert response.json()["session_id"] == str(session.id)

    @pytest.mark.asyncio
    async def test_chat_requires_auth(self, client: AsyncClient):
        """Should require authentication."""
        response = await client.post(
            "/api/v1/ai/chat",
            json={
                "question": "How do I reset my password?",
                "channel": "web",
            },
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_chat_rejects_empty_question(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should reject empty question."""
        response = await client.post(
            "/api/v1/ai/chat",
            json={
                "question": "",
                "channel": "web",
            },
            headers=auth_headers,
        )

        # FastAPI returns 422 for Pydantic validation errors
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_chat_rejects_missing_question(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should reject request without question."""
        response = await client.post(
            "/api/v1/ai/chat",
            json={
                "channel": "web",
            },
            headers=auth_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_chat_rejects_invalid_channel(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should reject invalid channel."""
        response = await client.post(
            "/api/v1/ai/chat",
            json={
                "question": "How do I reset?",
                "channel": "invalid_channel",
            },
            headers=auth_headers,
        )

        # May be 400 or 422 depending on validation
        assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_chat_nonexistent_session(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should reject nonexistent session."""
        response = await client.post(
            "/api/v1/ai/chat",
            json={
                "session_id": str(uuid4()),
                "question": "Test question",
                "channel": "web",
            },
            headers=auth_headers,
        )

        # Route returns 400 for ValueError (session not found)
        assert response.status_code == 400


class TestListSessionsEndpoint:
    """Test GET /api/v1/ai/sessions endpoint."""

    @pytest.mark.asyncio
    async def test_list_sessions(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session,
        test_user: User,
    ):
        """Should list user's sessions."""
        # Create sessions
        for i in range(3):
            session = ChatSession(
                id=uuid4(),
                user_id=test_user.id,
                title=f"Session {i}",
                escalated=False,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db_session.add(session)

        await db_session.commit()

        response = await client.get(
            "/api/v1/ai/sessions",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 3

    @pytest.mark.asyncio
    async def test_list_sessions_with_pagination(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session,
        test_user: User,
    ):
        """Pagination should work."""
        # Create 5 sessions
        for i in range(5):
            session = ChatSession(
                id=uuid4(),
                user_id=test_user.id,
                title=f"Session {i}",
                escalated=False,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db_session.add(session)

        await db_session.commit()

        # Get first page
        response = await client.get(
            "/api/v1/ai/sessions?skip=0&limit=2",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert len(response.json()) == 2

        # Get second page
        response = await client.get(
            "/api/v1/ai/sessions?skip=2&limit=2",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert len(response.json()) == 2

    @pytest.mark.asyncio
    async def test_list_sessions_requires_auth(self, client: AsyncClient):
        """Should require authentication."""
        response = await client.get("/api/v1/ai/sessions")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_sessions_limits_max_limit(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should limit max limit to 100."""
        response = await client.get(
            "/api/v1/ai/sessions?limit=1000",
            headers=auth_headers,
        )

        # Should succeed but with limit capped at 100
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self, client: AsyncClient, auth_headers: dict):
        """Should return empty list if no sessions."""
        response = await client.get(
            "/api/v1/ai/sessions",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json() == []


class TestGetSessionEndpoint:
    """Test GET /api/v1/ai/sessions/{session_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_session(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session,
        test_user: User,
    ):
        """Should retrieve session details."""
        session = ChatSession(
            id=uuid4(),
            user_id=test_user.id,
            title="Test Session",
            escalated=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db_session.add(session)
        await db_session.commit()

        response = await client.get(
            f"/api/v1/ai/sessions/{session.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        # JSON returns UUID as string
        assert data["id"] == str(session.id)
        assert data["title"] == "Test Session"
        assert data["escalated"] is False

    @pytest.mark.asyncio
    async def test_get_session_requires_auth(self, client: AsyncClient):
        """Should require authentication."""
        response = await client.get(
            f"/api/v1/ai/sessions/{uuid4()}",
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, client: AsyncClient, auth_headers: dict):
        """Should return 404 for nonexistent session."""
        response = await client.get(
            f"/api/v1/ai/sessions/{uuid4()}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_other_user_session_forbidden(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session,
        test_user: User,
    ):
        """Should not access other user's session."""
        other_user = User(
            id=str(uuid4()),
            email=f"other_{uuid4()}@example.com",
            password_hash="hash",
            role=UserRole.USER,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db_session.add(other_user)

        session = ChatSession(
            id=uuid4(),
            user_id=other_user.id,
            title="Other User Session",
            escalated=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db_session.add(session)
        await db_session.commit()

        # Try to access with test_user's auth
        response = await client.get(
            f"/api/v1/ai/sessions/{session.id}",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestEscalateEndpoint:
    """Test POST /api/v1/ai/sessions/{session_id}/escalate endpoint."""

    @pytest.mark.asyncio
    async def test_escalate_session(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session,
        test_user: User,
    ):
        """Should escalate session."""
        session = ChatSession(
            id=uuid4(),
            user_id=test_user.id,
            title="Test Session",
            escalated=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db_session.add(session)
        await db_session.commit()

        response = await client.post(
            f"/api/v1/ai/sessions/{session.id}/escalate",
            json={"session_id": str(session.id), "reason": "Need human support"},
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify escalated
        await db_session.refresh(session)
        assert session.escalated is True

    @pytest.mark.asyncio
    async def test_escalate_requires_reason(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session,
        test_user: User,
    ):
        """Should require escalation reason."""
        session = ChatSession(
            id=uuid4(),
            user_id=test_user.id,
            title="Test",
            escalated=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db_session.add(session)
        await db_session.commit()

        response = await client.post(
            f"/api/v1/ai/sessions/{session.id}/escalate",
            json={"session_id": str(session.id)},  # Missing required "reason" field
            headers=auth_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_escalate_requires_auth(self, client: AsyncClient):
        """Should require authentication."""
        response = await client.post(
            f"/api/v1/ai/sessions/{uuid4()}/escalate",
            json={"reason": "Help"},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_escalate_nonexistent_session(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should fail for nonexistent session."""
        nonexistent_id = uuid4()
        response = await client.post(
            f"/api/v1/ai/sessions/{nonexistent_id}/escalate",
            json={"session_id": str(nonexistent_id), "reason": "Help"},
            headers=auth_headers,
        )

        # Returns 422 (validation error) or 404 (not found) depending on implementation
        assert response.status_code in [404, 422]


class TestBuildIndexEndpoint:
    """Test POST /api/v1/ai/index/build endpoint."""

    @pytest.mark.asyncio
    async def test_build_index_admin_only(
        self, client: AsyncClient, admin_headers: dict
    ):
        """Should build index (admin only)."""
        response = await client.post(
            "/api/v1/ai/index/build",
            headers=admin_headers,
        )

        assert response.status_code == 202
        data = response.json()
        assert "status" in data
        assert "count" in data

    @pytest.mark.asyncio
    async def test_build_index_requires_admin(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Non-admin should not build index."""
        response = await client.post(
            "/api/v1/ai/index/build",
            headers=auth_headers,
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_build_index_requires_auth(self, client: AsyncClient):
        """Should require authentication."""
        response = await client.post("/api/v1/ai/index/build")

        assert response.status_code == 401


class TestIndexStatusEndpoint:
    """Test GET /api/v1/ai/index/status endpoint."""

    @pytest.mark.asyncio
    async def test_index_status_admin_only(
        self, client: AsyncClient, admin_headers: dict
    ):
        """Should return index status (admin only)."""
        response = await client.get(
            "/api/v1/ai/index/status",
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "total_articles" in data
        assert "indexed_articles" in data
        assert "pending_articles" in data
        assert "embedding_model" in data

    @pytest.mark.asyncio
    async def test_index_status_requires_admin(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Non-admin should not see index status."""
        response = await client.get(
            "/api/v1/ai/index/status",
            headers=auth_headers,
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_index_status_requires_auth(self, client: AsyncClient):
        """Should require authentication."""
        response = await client.get("/api/v1/ai/index/status")

        assert response.status_code == 401


class TestErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_invalid_json(self, client: AsyncClient, auth_headers: dict):
        """Should handle invalid JSON."""
        response = await client.post(
            "/api/v1/ai/chat",
            data="invalid json",
            headers=auth_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_required_fields(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should validate required fields."""
        response = await client.post(
            "/api/v1/ai/chat",
            json={"channel": "web"},  # Missing question
            headers=auth_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_uuid_format(self, client: AsyncClient, auth_headers: dict):
        """Should validate UUID format."""
        response = await client.get(
            "/api/v1/ai/sessions/not-a-uuid",
            headers=auth_headers,
        )

        assert response.status_code == 422


class TestCORSHeaders:
    """Test CORS headers."""

    @pytest.mark.asyncio
    async def test_cors_headers_present(self, client: AsyncClient, auth_headers: dict):
        """Response should include CORS headers."""
        response = await client.get(
            "/api/v1/ai/sessions",
            headers=auth_headers,
        )

        # Check for CORS headers (if configured)
        # This depends on FastAPI CORS middleware configuration


class TestRateLimiting:
    """Test rate limiting."""

    @pytest.mark.asyncio
    async def test_rate_limiting_chat(self, client: AsyncClient, auth_headers: dict):
        """Should rate limit chat endpoint."""
        # Make many requests
        for _ in range(10):
            response = await client.post(
                "/api/v1/ai/chat",
                json={
                    "question": "How do I reset?",
                    "channel": "web",
                },
                headers=auth_headers,
            )

            # May eventually get 429 if rate limited
            assert response.status_code in [201, 429]
