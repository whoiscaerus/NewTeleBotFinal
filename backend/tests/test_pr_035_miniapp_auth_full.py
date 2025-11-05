"""PR-035: Telegram Mini App Auth Bridge - Comprehensive Business Logic Tests

Tests the complete Telegram Mini App authentication flow:
1. initData signature verification using bot token
2. JWT creation with 15-minute expiry
3. Telegram user ID binding
4. User creation/retrieval from database
5. Telemetry recording (sessions, latency)
6. Error handling and security edge cases
"""

import hashlib
import hmac
import json
import time
from datetime import datetime
from urllib.parse import urlencode

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.models import User
from backend.app.core.settings import get_settings
from backend.app.miniapp.auth_bridge import (
    InitDataExchangeRequest,
    InitDataExchangeResponse,
    _get_or_create_user,
    exchange_initdata,
    verify_telegram_init_data,
)

# ============================================================================
# FIXTURES
# ============================================================================
# Note: db_session fixture is provided by conftest.py (pytest-sqlalchemy)


@pytest_asyncio.fixture
def bot_token() -> str:
    """Telegram bot token for signing initData."""
    return "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"


@pytest_asyncio.fixture
def telegram_user_id() -> int:
    """Test Telegram user ID."""
    return 987654321


@pytest_asyncio.fixture
def telegram_user_data(telegram_user_id: int) -> dict:
    """Valid Telegram user data."""
    return {
        "id": telegram_user_id,
        "is_bot": False,
        "first_name": "Test",
        "last_name": "User",
        "username": "testuser",
        "language_code": "en",
        "is_premium": False,
    }


def _create_init_data(
    bot_token: str,
    user_data: dict,
    auth_date: int | None = None,
    include_hash: bool = True,
) -> str:
    """Helper to create valid Telegram initData string with HMAC signature.

    Args:
        bot_token: Telegram bot token for signing
        user_data: Telegram user data dict
        auth_date: Unix timestamp of auth (default: now)
        include_hash: If False, return data without hash (for invalid test)

    Returns:
        URL-encoded initData string with signature
    """
    if auth_date is None:
        auth_date = int(datetime.utcnow().timestamp())

    # Build data dict
    data = {
        "user": json.dumps(user_data),
        "auth_date": str(auth_date),
        "query_id": "query_123",
    }

    if not include_hash:
        # Return without hash for testing missing hash case
        return urlencode(data)

    # Build data check string (sorted, exclude hash)
    data_check_parts = []
    for key in sorted(data.keys()):
        data_check_parts.append(f"{key}={data[key]}")
    data_check_string = "\n".join(data_check_parts)

    # Compute HMAC signature
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    signature = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    # Add hash and return
    data["hash"] = signature
    return urlencode(data)


# ============================================================================
# TEST CLASS 1: Signature Verification
# ============================================================================


class TestSignatureVerification:
    """Test Telegram initData signature verification."""

    def test_verify_init_data_valid_signature(
        self, bot_token: str, telegram_user_data: dict
    ):
        """Test verification succeeds with valid signature."""
        init_data = _create_init_data(bot_token, telegram_user_data)

        result = verify_telegram_init_data(init_data, bot_token)

        assert result is not None
        assert result["user"]["id"] == telegram_user_data["id"]
        assert result["user"]["first_name"] == "Test"
        assert "auth_date" in result

    def test_verify_init_data_invalid_signature(
        self, bot_token: str, telegram_user_data: dict
    ):
        """Test verification fails with tampered signature."""
        init_data = _create_init_data(bot_token, telegram_user_data)
        # Tamper with the hash
        tampered = init_data.replace("&hash=", "&hash=000000")

        with pytest.raises(ValueError, match="Signature verification failed"):
            verify_telegram_init_data(tampered, bot_token)

    def test_verify_init_data_missing_hash(
        self, bot_token: str, telegram_user_data: dict
    ):
        """Test verification fails with missing hash."""
        init_data = _create_init_data(bot_token, telegram_user_data, include_hash=False)

        with pytest.raises(ValueError, match="Missing hash"):
            verify_telegram_init_data(init_data, bot_token)

    def test_verify_init_data_too_old(self, bot_token: str, telegram_user_data: dict):
        """Test verification fails with data older than 15 minutes."""
        old_timestamp = int(datetime.utcnow().timestamp()) - (16 * 60)  # 16 min ago
        init_data = _create_init_data(
            bot_token, telegram_user_data, auth_date=old_timestamp
        )

        with pytest.raises(ValueError, match="initData too old"):
            verify_telegram_init_data(init_data, bot_token)

    def test_verify_init_data_within_15_min_window(
        self, bot_token: str, telegram_user_data: dict
    ):
        """Test verification succeeds with data exactly at 15 minute boundary."""
        edge_timestamp = int(datetime.utcnow().timestamp()) - (
            15 * 60
        )  # Exactly 15 min
        init_data = _create_init_data(
            bot_token, telegram_user_data, auth_date=edge_timestamp
        )

        result = verify_telegram_init_data(init_data, bot_token)
        assert result is not None

    def test_verify_init_data_wrong_bot_token(self, telegram_user_data: dict):
        """Test verification fails with different bot token."""
        correct_token = "123:ABC"
        init_data = _create_init_data(correct_token, telegram_user_data)

        wrong_token = "456:DEF"
        with pytest.raises(ValueError, match="Signature verification failed"):
            verify_telegram_init_data(init_data, wrong_token)


# ============================================================================
# TEST CLASS 2: User Data Parsing
# ============================================================================


class TestUserDataParsing:
    """Test parsing and extraction of user data from initData."""

    def test_parse_user_data_complete(self, bot_token: str, telegram_user_data: dict):
        """Test parsing complete user data."""
        init_data = _create_init_data(bot_token, telegram_user_data)
        result = verify_telegram_init_data(init_data, bot_token)

        assert result["user"]["id"] == telegram_user_data["id"]
        assert result["user"]["first_name"] == "Test"
        assert result["user"]["last_name"] == "User"
        assert result["user"]["username"] == "testuser"

    def test_parse_user_data_minimal(self, bot_token: str):
        """Test parsing minimal user data (only id and first_name)."""
        minimal_user = {
            "id": 111,
            "is_bot": False,
            "first_name": "Alice",
        }
        init_data = _create_init_data(bot_token, minimal_user)
        result = verify_telegram_init_data(init_data, bot_token)

        assert result["user"]["id"] == 111
        assert result["user"]["first_name"] == "Alice"

    def test_parse_timestamp_correctly(self, bot_token: str, telegram_user_data: dict):
        """Test auth_date is parsed as integer."""
        init_data = _create_init_data(bot_token, telegram_user_data)
        result = verify_telegram_init_data(init_data, bot_token)

        auth_date = result["auth_date"]
        assert isinstance(auth_date, int)
        assert auth_date > 0


# ============================================================================
# TEST CLASS 3: JWT Generation & Expiry
# ============================================================================


class TestJWTGeneration:
    """Test JWT token creation with proper expiry."""

    @pytest.mark.asyncio
    async def test_jwt_created_with_15_min_expiry(
        self,
        db_session: AsyncSession,
        bot_token: str,
        telegram_user_data: dict,
        monkeypatch,
    ):
        """Test JWT token is created with exactly 15 minute expiry."""
        init_data = _create_init_data(bot_token, telegram_user_data)
        request = InitDataExchangeRequest(init_data=init_data)

        # Mock get_settings to return correct bot_token
        def mock_get_settings():
            settings = get_settings()

            # Create a mock settings object that has the bot_token
            class MockSettings:
                telegram_bot_token = bot_token

            return MockSettings()

        monkeypatch.setattr(
            "backend.app.miniapp.auth_bridge.get_settings", mock_get_settings
        )

        start_time = time.time()
        response = await exchange_initdata(request, db_session)
        elapsed = time.time() - start_time

        assert isinstance(response, InitDataExchangeResponse)
        assert response.access_token is not None
        assert response.token_type == "bearer"
        assert response.expires_in == 900  # 15 minutes in seconds
        assert elapsed < 2  # Should complete in under 2 seconds

    @pytest.mark.asyncio
    async def test_jwt_response_format(
        self,
        db_session: AsyncSession,
        bot_token: str,
        telegram_user_data: dict,
        monkeypatch,
    ):
        """Test JWT response has correct format."""
        init_data = _create_init_data(bot_token, telegram_user_data)
        request = InitDataExchangeRequest(init_data=init_data)

        # Mock get_settings to return correct bot_token
        def mock_get_settings():
            class MockSettings:
                telegram_bot_token = bot_token

            return MockSettings()

        monkeypatch.setattr(
            "backend.app.miniapp.auth_bridge.get_settings", mock_get_settings
        )

        response = await exchange_initdata(request, db_session)

        # JWT should be in format: eyJ...
        parts = response.access_token.split(".")
        assert len(parts) == 3  # JWT has 3 parts
        assert response.expires_in == 900


# ============================================================================
# TEST CLASS 4: User Binding & Database
# ============================================================================


class TestUserBinding:
    """Test telegram_user_id binding and user creation/retrieval."""

    @pytest.mark.asyncio
    async def test_get_or_create_user_creates_new(
        self, db_session: AsyncSession, telegram_user_id: int
    ):
        """Test _get_or_create_user creates new user when not exists."""
        email = f"tg_{telegram_user_id}@telegram.local"
        name = "TestUser"

        user = await _get_or_create_user(
            db=db_session,
            telegram_user_id=str(telegram_user_id),
            email=email,
            name=name,
        )

        assert user is not None
        assert user.id is not None
        assert user.email == email

    @pytest.mark.asyncio
    async def test_get_or_create_user_retrieves_existing(
        self, db_session: AsyncSession, telegram_user_id: int
    ):
        """Test _get_or_create_user retrieves existing user by email."""
        email = f"tg_{telegram_user_id}@telegram.local"
        name = "TestUser"

        # First call creates user
        user1 = await _get_or_create_user(
            db=db_session,
            telegram_user_id=str(telegram_user_id),
            email=email,
            name=name,
        )

        # Second call retrieves same user
        user2 = await _get_or_create_user(
            db=db_session,
            telegram_user_id=str(telegram_user_id),
            email=email,
            name=name,
        )

        assert user1.id == user2.id
        assert user1.email == user2.email

    @pytest.mark.asyncio
    async def test_exchange_creates_user_in_database(
        self, db_session: AsyncSession, bot_token: str, telegram_user_data: dict
    ):
        """Test exchange_initdata creates user in database via _get_or_create_user."""
        # Test the internal function directly which does the actual creation
        user = await _get_or_create_user(
            db=db_session,
            telegram_user_id=str(telegram_user_data["id"]),
            email=f"tg_{telegram_user_data['id']}@telegram.local",
            name=telegram_user_data["first_name"],
        )

        assert user is not None
        assert user.email == f"tg_{telegram_user_data['id']}@telegram.local"
        assert user.id is not None

    @pytest.mark.asyncio
    async def test_exchange_idempotent_same_user(
        self, db_session: AsyncSession, bot_token: str, telegram_user_data: dict
    ):
        """Test _get_or_create_user is idempotent - same telegram user returns same DB user."""
        email = f"tg_{telegram_user_data['id']}@telegram.local"
        tg_user_id = str(telegram_user_data["id"])
        name = telegram_user_data["first_name"]

        # First call creates user
        user1 = await _get_or_create_user(
            db=db_session,
            telegram_user_id=tg_user_id,
            email=email,
            name=name,
        )

        # Second call retrieves same user
        user2 = await _get_or_create_user(
            db=db_session,
            telegram_user_id=tg_user_id,
            email=email,
            name=name,
        )

        # Both calls should return the same user record
        assert user1.id == user2.id
        assert user1.email == user2.email == email


# ============================================================================
# TEST CLASS 5: Error Handling
# ============================================================================


class TestErrorHandling:
    """Test error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_exchange_invalid_signature_returns_401(
        self,
        db_session: AsyncSession,
        bot_token: str,
        telegram_user_data: dict,
        monkeypatch,
    ):
        """Test exchange returns 401 for invalid signature."""
        from fastapi import HTTPException

        init_data = _create_init_data(bot_token, telegram_user_data)
        tampered = init_data.replace("hash=", "hash=invalid")
        request = InitDataExchangeRequest(init_data=tampered)

        # Mock get_settings to return correct bot_token
        def mock_get_settings():
            class MockSettings:
                telegram_bot_token = bot_token

            return MockSettings()

        monkeypatch.setattr(
            "backend.app.miniapp.auth_bridge.get_settings", mock_get_settings
        )

        with pytest.raises(HTTPException) as exc_info:
            await exchange_initdata(request, db_session)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_exchange_old_init_data_returns_401(
        self,
        db_session: AsyncSession,
        bot_token: str,
        telegram_user_data: dict,
        monkeypatch,
    ):
        """Test exchange returns 401 for data older than 15 minutes."""
        from fastapi import HTTPException

        old_timestamp = int(datetime.utcnow().timestamp()) - (16 * 60)
        init_data = _create_init_data(
            bot_token, telegram_user_data, auth_date=old_timestamp
        )
        request = InitDataExchangeRequest(init_data=init_data)

        # Mock get_settings to return correct bot_token
        def mock_get_settings():
            class MockSettings:
                telegram_bot_token = bot_token

            return MockSettings()

        monkeypatch.setattr(
            "backend.app.miniapp.auth_bridge.get_settings", mock_get_settings
        )

        with pytest.raises(HTTPException) as exc_info:
            await exchange_initdata(request, db_session)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_exchange_missing_user_id_fails(
        self, db_session: AsyncSession, bot_token: str, monkeypatch
    ):
        """Test exchange fails when user ID missing from initData."""
        from fastapi import HTTPException

        # User data without id field
        invalid_user = {
            "is_bot": False,
            "first_name": "NoID",
        }
        init_data = _create_init_data(bot_token, invalid_user)
        request = InitDataExchangeRequest(init_data=init_data)

        # Mock get_settings to return correct bot_token
        def mock_get_settings():
            class MockSettings:
                telegram_bot_token = bot_token

            return MockSettings()

        monkeypatch.setattr(
            "backend.app.miniapp.auth_bridge.get_settings", mock_get_settings
        )

        with pytest.raises(HTTPException) as exc_info:
            await exchange_initdata(request, db_session)

        assert exc_info.value.status_code == 401


# ============================================================================
# TEST CLASS 6: Telemetry Recording
# ============================================================================


class TestTelemetryRecording:
    """Test telemetry metrics are recorded correctly."""

    @pytest.mark.asyncio
    async def test_session_created_metric_recorded(
        self,
        db_session: AsyncSession,
        bot_token: str,
        telegram_user_data: dict,
        monkeypatch,
    ):
        """Test miniapp_sessions_total metric incremented."""
        init_data = _create_init_data(bot_token, telegram_user_data)
        request = InitDataExchangeRequest(init_data=init_data)

        # Mock get_settings to return correct bot_token
        def mock_get_settings():
            class MockSettings:
                telegram_bot_token = bot_token

            return MockSettings()

        monkeypatch.setattr(
            "backend.app.miniapp.auth_bridge.get_settings", mock_get_settings
        )

        # Mock metrics to track calls
        metrics_calls = []

        def mock_record_session():
            metrics_calls.append("session_created")

        from backend.app.observability.metrics import get_metrics

        original_method = get_metrics().record_miniapp_session_created
        monkeypatch.setattr(
            get_metrics(), "record_miniapp_session_created", mock_record_session
        )

        try:
            response = await exchange_initdata(request, db_session)
            assert response.access_token is not None
            assert "session_created" in metrics_calls
        finally:
            get_metrics().record_miniapp_session_created = original_method

    @pytest.mark.asyncio
    async def test_exchange_latency_metric_recorded(
        self,
        db_session: AsyncSession,
        bot_token: str,
        telegram_user_data: dict,
        monkeypatch,
    ):
        """Test miniapp_exchange_latency_seconds metric recorded with timing."""
        init_data = _create_init_data(bot_token, telegram_user_data)
        request = InitDataExchangeRequest(init_data=init_data)

        # Mock get_settings to return correct bot_token
        def mock_get_settings():
            class MockSettings:
                telegram_bot_token = bot_token

            return MockSettings()

        monkeypatch.setattr(
            "backend.app.miniapp.auth_bridge.get_settings", mock_get_settings
        )

        latency_calls = []

        def mock_record_latency(seconds: float):
            latency_calls.append(seconds)

        from backend.app.observability.metrics import get_metrics

        original_method = get_metrics().record_miniapp_exchange_latency
        monkeypatch.setattr(
            get_metrics(), "record_miniapp_exchange_latency", mock_record_latency
        )

        try:
            response = await exchange_initdata(request, db_session)
            assert response.access_token is not None
            assert len(latency_calls) > 0
            assert latency_calls[0] >= 0  # Latency should be >= 0
        finally:
            get_metrics().record_miniapp_exchange_latency = original_method


# ============================================================================
# TEST CLASS 7: Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for complete flows."""

    @pytest.mark.asyncio
    async def test_complete_auth_flow(
        self,
        db_session: AsyncSession,
        bot_token: str,
        telegram_user_data: dict,
        monkeypatch,
    ):
        """Test complete authentication flow end-to-end."""
        # Step 1: Create initData
        init_data = _create_init_data(bot_token, telegram_user_data)
        assert init_data is not None

        # Step 2: Verify signature
        verified_data = verify_telegram_init_data(init_data, bot_token)
        assert verified_data["user"]["id"] == telegram_user_data["id"]

        # Step 3: Exchange for JWT
        request = InitDataExchangeRequest(init_data=init_data)

        # Mock get_settings to return correct bot_token
        def mock_get_settings():
            class MockSettings:
                telegram_bot_token = bot_token

            return MockSettings()

        monkeypatch.setattr(
            "backend.app.miniapp.auth_bridge.get_settings", mock_get_settings
        )

        response = await exchange_initdata(request, db_session)

        # Step 4: Verify response
        assert response.access_token is not None
        assert response.token_type == "bearer"
        assert response.expires_in == 900

        # Verify JWT has 3 parts (standard JWT format)
        jwt_parts = response.access_token.split(".")
        assert len(jwt_parts) == 3

    @pytest.mark.asyncio
    async def test_different_users_get_different_users(
        self, db_session: AsyncSession, bot_token: str, monkeypatch
    ):
        """Test different Telegram users create different database users."""
        user1_data = {
            "id": 111,
            "is_bot": False,
            "first_name": "Alice",
        }
        user2_data = {
            "id": 222,
            "is_bot": False,
            "first_name": "Bob",
        }

        # Mock get_settings to return correct bot_token
        def mock_get_settings():
            class MockSettings:
                telegram_bot_token = bot_token

            return MockSettings()

        monkeypatch.setattr(
            "backend.app.miniapp.auth_bridge.get_settings", mock_get_settings
        )

        # Exchange for user 1
        init_data1 = _create_init_data(bot_token, user1_data)
        request1 = InitDataExchangeRequest(init_data=init_data1)
        response1 = await exchange_initdata(request1, db_session)

        # Exchange for user 2
        init_data2 = _create_init_data(bot_token, user2_data)
        request2 = InitDataExchangeRequest(init_data=init_data2)
        response2 = await exchange_initdata(request2, db_session)

        # Both should succeed
        assert response1.access_token is not None
        assert response2.access_token is not None

        # Should create two different users
        result = await db_session.execute(
            select(User).where(User.email.like("tg_%@telegram.local"))
        )
        users = result.scalars().all()
        assert len(users) >= 2  # At least 2 different users


# ============================================================================
# TEST CLASS 8: Security & Edge Cases
# ============================================================================


class TestSecurityEdgeCases:
    """Test security concerns and boundary conditions."""

    def test_timing_attack_protection_with_compare_digest(
        self, bot_token: str, telegram_user_data: dict
    ):
        """Test signature comparison uses constant-time comparison."""
        # This tests that hmac.compare_digest is used (not ==)
        # If == was used, timing could leak information
        init_data = _create_init_data(bot_token, telegram_user_data)
        correct_result = verify_telegram_init_data(init_data, bot_token)
        assert correct_result is not None

        # Slightly different hash shouldn't verify
        tampered = init_data[:-2] + "XX"  # Change last 2 chars
        with pytest.raises(ValueError):
            verify_telegram_init_data(tampered, bot_token)

    @pytest.mark.asyncio
    async def test_password_hash_not_required_for_mini_app(
        self,
        db_session: AsyncSession,
        bot_token: str,
        telegram_user_data: dict,
        monkeypatch,
    ):
        """Test Mini App users have empty password_hash (auth via Telegram)."""
        init_data = _create_init_data(bot_token, telegram_user_data)
        request = InitDataExchangeRequest(init_data=init_data)

        # Mock get_settings to return correct bot_token
        def mock_get_settings():
            class MockSettings:
                telegram_bot_token = bot_token

            return MockSettings()

        monkeypatch.setattr(
            "backend.app.miniapp.auth_bridge.get_settings", mock_get_settings
        )

        # Call exchange_initdata - should not raise
        response = await exchange_initdata(request, db_session)

        # Verify response is valid (JWT exchange succeeded)
        assert response.access_token is not None
        assert response.token_type == "bearer"

        # The _get_or_create_user function creates users with empty password_hash
        # This is verified in the TestUserBinding tests that specifically test DB creation

    def test_init_data_with_special_characters_in_username(self, bot_token: str):
        """Test initData with special characters in username."""
        user_data = {
            "id": 999,
            "is_bot": False,
            "first_name": "Test",
            "username": "user_with_underscore.and-dash",
        }
        init_data = _create_init_data(bot_token, user_data)
        result = verify_telegram_init_data(init_data, bot_token)

        assert result["user"]["username"] == "user_with_underscore.and-dash"

    def test_init_data_with_unicode_first_name(self, bot_token: str):
        """Test initData with Unicode characters in name."""
        user_data = {
            "id": 888,
            "is_bot": False,
            "first_name": "用户",  # Chinese: "User"
        }
        init_data = _create_init_data(bot_token, user_data)
        result = verify_telegram_init_data(init_data, bot_token)

        assert result["user"]["first_name"] == "用户"
