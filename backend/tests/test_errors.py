"""Error taxonomy and validation tests."""

import pytest
from httpx import AsyncClient

from backend.app.core.errors import (
    ERROR_TYPES,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ProblemDetail,
    RateLimitError,
    ServerError,
)
from backend.app.core.errors import ValidationError as APIValidationError
from backend.app.core.validation import (
    EmailValidator,
    InstrumentValidator,
    PriceValidator,
    RoleValidator,
    SideValidator,
    UUIDValidator,
)


class TestProblemDetailModel:
    """Test RFC 7807 ProblemDetail model."""

    def test_problem_detail_basic(self):
        """Test creating basic ProblemDetail."""
        problem = ProblemDetail(
            type=ERROR_TYPES["validation"],
            title="Validation Error",
            status=422,
            detail="Email must be unique",
        )

        assert problem.type == ERROR_TYPES["validation"]
        assert problem.title == "Validation Error"
        assert problem.status == 422
        assert problem.detail == "Email must be unique"

    def test_problem_detail_with_errors(self):
        """Test ProblemDetail with field-level errors."""
        errors = [
            {"field": "email", "message": "Already registered"},
            {"field": "password", "message": "Too weak"},
        ]
        problem = ProblemDetail(
            type=ERROR_TYPES["validation"],
            title="Validation Error",
            status=422,
            detail="Request validation failed",
            errors=errors,
        )

        assert len(problem.errors) == 2
        assert problem.errors[0]["field"] == "email"

    def test_problem_detail_json_serialization(self):
        """Test ProblemDetail serializes to JSON correctly."""
        problem = ProblemDetail(
            type=ERROR_TYPES["authentication"],
            title="Authentication Error",
            status=401,
            detail="Invalid credentials",
            request_id="abc-123",
        )

        data = problem.model_dump(exclude_none=True)
        assert data["type"] == ERROR_TYPES["authentication"]
        assert data["status"] == 401
        assert data["request_id"] == "abc-123"


class TestAPIExceptions:
    """Test API exception classes."""

    def test_validation_error(self):
        """Test ValidationError exception."""
        exc = APIValidationError(
            detail="Email invalid",
            errors=[{"field": "email", "message": "Invalid format"}],
        )

        assert exc.status_code == 422
        assert exc.error_type == "validation"
        assert exc.detail == "Email invalid"
        assert len(exc.errors) == 1

    def test_authentication_error(self):
        """Test AuthenticationError exception."""
        exc = AuthenticationError("Credentials required")

        assert exc.status_code == 401
        assert exc.error_type == "authentication"

    def test_authorization_error(self):
        """Test AuthorizationError exception."""
        exc = AuthorizationError("Admin role required")

        assert exc.status_code == 403
        assert exc.error_type == "authorization"

    def test_not_found_error(self):
        """Test NotFoundError exception."""
        exc = NotFoundError("User", "user-123")

        assert exc.status_code == 404
        assert exc.error_type == "not_found"
        assert "User not found" in exc.detail

    def test_conflict_error(self):
        """Test ConflictError exception."""
        exc = ConflictError("Email already registered")

        assert exc.status_code == 409
        assert exc.error_type == "conflict"

    def test_rate_limit_error(self):
        """Test RateLimitError exception."""
        exc = RateLimitError("Too many login attempts")

        assert exc.status_code == 429
        assert exc.error_type == "rate_limit"

    def test_server_error(self):
        """Test ServerError exception."""
        exc = ServerError("Database connection failed")

        assert exc.status_code == 500
        assert exc.error_type == "server_error"

    def test_exception_to_problem_detail(self):
        """Test converting exception to ProblemDetail."""
        exc = AuthenticationError("Invalid credentials")
        problem = exc.to_problem_detail(request_id="req-456")

        assert problem.type == ERROR_TYPES["authentication"]
        assert problem.status == 401
        assert problem.request_id == "req-456"
        assert problem.timestamp is not None


class TestEmailValidator:
    """Test email validation."""

    def test_email_valid(self):
        """Test valid email addresses."""
        valid_emails = [
            "user@example.com",
            "test.user@sub.example.co.uk",
            "user+tag@example.com",
        ]

        for email in valid_emails:
            result = EmailValidator.validate_email(email)
            assert result == email.lower()

    def test_email_invalid(self):
        """Test invalid email addresses."""
        invalid_emails = [
            "user",
            "@example.com",
            "user@",
            "user @example.com",
        ]

        for email in invalid_emails:
            with pytest.raises(ValueError):
                EmailValidator.validate_email(email)

    def test_email_lowercase(self):
        """Test email converted to lowercase."""
        result = EmailValidator.validate_email("User@EXAMPLE.COM")
        assert result == "user@example.com"


class TestInstrumentValidator:
    """Test trading instrument validation."""

    def test_instrument_valid(self):
        """Test valid trading instruments."""
        valid = ["EURUSD", "XAUUSD", "GBPUSD"]

        for instrument in valid:
            result = InstrumentValidator.validate_instrument(instrument)
            assert result == instrument.upper()

    def test_instrument_lowercase(self):
        """Test instrument converted to uppercase."""
        result = InstrumentValidator.validate_instrument("eurusd")
        assert result == "EURUSD"

    def test_instrument_invalid(self):
        """Test invalid instrument raises ValueError."""
        with pytest.raises(ValueError, match="Unknown instrument"):
            InstrumentValidator.validate_instrument("INVALID")


class TestPriceValidator:
    """Test price validation."""

    def test_price_valid(self):
        """Test valid prices."""
        valid_prices = [0.001, 1.0, 100.0, 50000.0]

        for price in valid_prices:
            result = PriceValidator.validate_price(price)
            assert result == price

    def test_price_negative_rejected(self):
        """Test negative price rejected."""
        with pytest.raises(ValueError, match="positive"):
            PriceValidator.validate_price(-10.0)

    def test_price_zero_rejected(self):
        """Test zero price rejected."""
        with pytest.raises(ValueError, match="positive"):
            PriceValidator.validate_price(0)

    def test_price_too_large_rejected(self):
        """Test price exceeding max rejected."""
        with pytest.raises(ValueError, match="exceeds maximum"):
            PriceValidator.validate_price(10_000_000.0)


class TestRoleValidator:
    """Test role validation."""

    def test_role_valid(self):
        """Test valid roles."""
        for role in ["OWNER", "ADMIN", "USER"]:
            result = RoleValidator.validate_role(role)
            assert result == role

    def test_role_lowercase(self):
        """Test role converted to uppercase."""
        result = RoleValidator.validate_role("user")
        assert result == "USER"

    def test_role_invalid(self):
        """Test invalid role rejected."""
        with pytest.raises(ValueError, match="Invalid role"):
            RoleValidator.validate_role("SUPERUSER")


class TestSideValidator:
    """Test trade side validation."""

    def test_side_valid(self):
        """Test valid trade sides."""
        for side in ["BUY", "SELL"]:
            result = SideValidator.validate_side(side)
            assert result == side

    def test_side_lowercase(self):
        """Test side converted to uppercase."""
        assert SideValidator.validate_side("buy") == "BUY"
        assert SideValidator.validate_side("sell") == "SELL"

    def test_side_invalid(self):
        """Test invalid side rejected."""
        with pytest.raises(ValueError, match="BUY or SELL"):
            SideValidator.validate_side("SHORT")


class TestUUIDValidator:
    """Test UUID validation."""

    def test_uuid_valid_v4(self):
        """Test valid UUID v4."""
        valid_uuid = "550e8400-e29b-41d4-a716-446655440000"
        result = UUIDValidator.validate_uuid(valid_uuid)
        assert result == valid_uuid

    def test_uuid_case_insensitive(self):
        """Test UUID accepts uppercase."""
        uuid_upper = "550E8400-E29B-41D4-A716-446655440000"
        result = UUIDValidator.validate_uuid(uuid_upper)
        assert result == uuid_upper

    def test_uuid_invalid(self):
        """Test invalid UUID rejected."""
        with pytest.raises(ValueError, match="Invalid UUID"):
            UUIDValidator.validate_uuid("not-a-uuid")


class TestErrorResponses:
    """Integration tests for error responses."""

    @pytest.mark.asyncio
    async def test_validation_error_response(self, client: AsyncClient):
        """Test validation error returns RFC 7807 response."""
        # Try to register with invalid email
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "not-an-email", "password": "password123"},
        )

        assert response.status_code == 422
        data = response.json()
        assert "type" in data
        assert data["type"] == ERROR_TYPES["validation"]
        assert "title" in data
        assert "detail" in data
        assert "status" in data
        assert data["status"] == 422

    @pytest.mark.asyncio
    async def test_authentication_error_response(self, client: AsyncClient):
        """Test authentication error returns RFC 7807 response."""
        # Try to login with wrong credentials
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "nonexistent@example.com", "password": "wrong"},
        )

        assert response.status_code == 401
        data = response.json()
        assert data["type"] == ERROR_TYPES["authentication"]
        assert data["status"] == 401

    @pytest.mark.asyncio
    async def test_missing_auth_header(self, client: AsyncClient):
        """Test missing auth header returns error."""
        response = await client.get("/api/v1/auth/me")

        # 401 Unauthorized is correct when no credentials provided
        assert response.status_code == 401
        data = response.json()
        assert (
            "Not authenticated" in data["detail"]
            or "Missing Authorization" in data["detail"]
        )
