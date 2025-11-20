"""Authentication tests."""

from datetime import UTC

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.models import User, UserRole
from backend.app.auth.utils import create_access_token, hash_password, verify_password


class TestPasswordHashing:
    """Test password hashing and verification."""

    def test_hash_password_creates_hash(self):
        """Test that hash_password creates a non-empty hash."""
        hashed = hash_password("password123")
        assert hashed
        assert hashed != "password123"

    def test_verify_password_valid(self):
        """Test verify_password with correct password."""
        password = "correct_password"
        hashed = hash_password(password)
        assert verify_password(password, hashed)

    def test_verify_password_invalid(self):
        """Test verify_password with incorrect password."""
        password = "correct_password"
        hashed = hash_password(password)
        assert not verify_password("wrong_password", hashed)

    def test_verify_password_empty_string(self):
        """Test verify_password with empty string."""
        hashed = hash_password("password")
        assert not verify_password("", hashed)


class TestJWT:
    """Test JWT token creation and validation."""

    def test_create_access_token_valid(self):
        """Test creating valid JWT token."""
        from backend.app.auth.utils import decode_token

        token = create_access_token(subject="user123", role="USER")
        assert token
        assert isinstance(token, str)

        # Validate token can be decoded
        payload = decode_token(token)
        assert payload["sub"] == "user123"
        assert payload["role"] == "USER"

    def test_create_access_token_with_expiry(self):
        """Test creating JWT with custom expiry."""
        from datetime import timedelta

        from backend.app.auth.utils import decode_token

        token = create_access_token(
            subject="user123",
            role="ADMIN",
            expires_delta=timedelta(hours=1),
        )
        payload = decode_token(token)
        assert payload["sub"] == "user123"
        assert payload["role"] == "ADMIN"

    def test_decode_token_invalid(self):
        """Test decoding invalid token raises ValueError."""
        from backend.app.auth.utils import decode_token

        with pytest.raises(ValueError):
            decode_token("invalid.token.here")

    def test_decode_token_expired(self):
        """Test decoding expired token raises ValueError."""
        from datetime import datetime, timedelta

        import jwt

        from backend.app.core.settings import get_settings

        settings = get_settings()
        payload = {
            "sub": "user123",
            "role": "USER",
            "exp": datetime.now(UTC) - timedelta(hours=1),
        }
        expired_token = jwt.encode(
            payload,
            settings.security.jwt_secret_key,
            algorithm=settings.security.jwt_algorithm,
        )

        from backend.app.auth.utils import decode_token

        with pytest.raises(ValueError):
            decode_token(expired_token)


class TestUserModel:
    """Test User SQLAlchemy model."""

    @pytest.mark.asyncio
    async def test_user_model_creation(self, db_session: AsyncSession):
        """Test creating and saving User model."""
        user = User(
            email="test@example.com",
            password_hash="hashed_password",
            role=UserRole.USER,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.id
        assert user.email == "test@example.com"
        assert user.role == UserRole.USER

    @pytest.mark.asyncio
    async def test_user_default_role(self, db_session: AsyncSession):
        """Test User defaults to USER role."""
        user = User(
            email="test2@example.com",
            password_hash="hashed_password",
        )
        assert user.role == UserRole.USER

    @pytest.mark.asyncio
    async def test_user_unique_email(self, db_session: AsyncSession):
        """Test User email uniqueness constraint."""
        from sqlalchemy.exc import IntegrityError

        user1 = User(email="duplicate@example.com", password_hash="hash1")
        db_session.add(user1)
        await db_session.commit()

        user2 = User(email="duplicate@example.com", password_hash="hash2")
        db_session.add(user2)

        with pytest.raises(IntegrityError):
            await db_session.commit()


class TestRegisterEndpoint:
    """Test POST /api/v1/auth/register endpoint."""

    @pytest.mark.asyncio
    async def test_register_valid(self, client: AsyncClient, db_session: AsyncSession):
        """Test successful user registration."""
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "newuser@example.com", "password": "password123"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert data["role"] == "user"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_register_duplicate_email(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test registration fails with duplicate email."""
        # Create existing user
        user = User(
            email="existing@example.com", password_hash=hash_password("password")
        )
        db_session.add(user)
        await db_session.commit()

        # Try to register with same email
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "existing@example.com", "password": "password456"},
        )

        assert response.status_code == 400
        assert "already registered" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_register_invalid_email(self, client: AsyncClient):
        """Test registration fails with invalid email."""
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "not-an-email", "password": "password123"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_weak_password(self, client: AsyncClient):
        """Test registration fails with weak password."""
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "user@example.com", "password": "weak"},
        )

        assert response.status_code == 422


class TestLoginEndpoint:
    """Test POST /api/v1/auth/login endpoint."""

    @pytest.mark.asyncio
    async def test_login_valid(self, client: AsyncClient, db_session: AsyncSession):
        """Test successful login."""
        # Create user
        password = "correct_password"
        user = User(email="testuser@example.com", password_hash=hash_password(password))
        db_session.add(user)
        await db_session.commit()

        # Login
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "testuser@example.com", "password": password},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == "testuser@example.com"

    @pytest.mark.asyncio
    async def test_login_invalid_password(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test login fails with wrong password."""
        # Create user
        user = User(
            email="testuser2@example.com",
            password_hash=hash_password("correct_password"),
        )
        db_session.add(user)
        await db_session.commit()

        # Try wrong password
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "testuser2@example.com", "password": "wrong_password"},
        )

        assert response.status_code == 401
        assert "Invalid email or password" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Test login fails with nonexistent user."""
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "nonexistent@example.com", "password": "password123"},
        )

        assert response.status_code == 401
        assert "Invalid email or password" in response.json()["detail"]


class TestMeEndpoint:
    """Test GET /api/v1/auth/me endpoint."""

    @pytest.mark.asyncio
    async def test_me_with_valid_token(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test getting current user with valid token."""
        from backend.app.auth.jwt_handler import JWTHandler

        # Create user
        user = User(
            email="current@example.com", password_hash=hash_password("password")
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # Verify user was created with ID
        assert user.id is not None, "User ID should be auto-generated"

        # Get token using JWTHandler
        handler = JWTHandler()
        token = handler.create_token(user_id=user.id, role=user.role.value)

        # Get current user
        response = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "current@example.com"
        assert data["id"] == user.id

    @pytest.mark.asyncio
    async def test_me_without_token(self, client: AsyncClient):
        """Test /me fails without Authorization header."""
        response = await client.get("/api/v1/auth/me")

        # 401 Unauthorized is correct when no credentials provided
        assert response.status_code == 401
        assert "Not authenticated" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_me_with_invalid_token(self, client: AsyncClient):
        """Test /me fails with invalid token."""
        response = await client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer invalid_token"}
        )

        assert response.status_code == 401
        assert "Not authenticated" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_me_with_deleted_user(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test /me fails if user deleted after token creation."""
        # Create user
        user = User(
            email="deleted@example.com", password_hash=hash_password("password")
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # Create token
        token = create_access_token(subject=user.id, role=user.role.value)

        # Delete user
        await db_session.delete(user)
        await db_session.commit()

        # Try to access /me
        response = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 401
        assert "Not authenticated" in response.json()["detail"]


class TestAdminEndpoint:
    """Test protected admin endpoint."""

    @pytest.mark.asyncio
    async def test_admin_endpoint_owner(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test admin endpoint accessible to OWNER."""
        # Create owner
        user = User(
            email="owner@example.com",
            password_hash=hash_password("password"),
            role=UserRole.OWNER,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # Get token
        token = create_access_token(subject=user.id, role=user.role.value)

        # Access admin endpoint
        response = await client.post(
            "/api/v1/auth/protected-admin",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_endpoint_admin(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test admin endpoint accessible to ADMIN."""
        # Create admin
        user = User(
            email="admin@example.com",
            password_hash=hash_password("password"),
            role=UserRole.ADMIN,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # Get token
        token = create_access_token(subject=user.id, role=user.role.value)

        # Access admin endpoint
        response = await client.post(
            "/api/v1/auth/protected-admin",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_endpoint_user_denied(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test admin endpoint denies regular USER."""
        # Create regular user
        user = User(
            email="user@example.com",
            password_hash=hash_password("password"),
            role=UserRole.USER,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # Get token
        token = create_access_token(subject=user.id, role=user.role.value)

        # Try to access admin endpoint
        response = await client.post(
            "/api/v1/auth/protected-admin",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403
        assert "permission" in response.text.lower()
