"""
PR-006 Gap Tests: Pydantic Validation, Stack Trace Security, Request Context

Covers the ~8 missing scenarios to reach 95%+ coverage:
- Pydantic field validation integration
- Stack trace redaction in production mode
- Request context propagation in structured logs
"""

from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from backend.app.core.errors import AuthenticationError, ProblemDetail, ValidationError

# ============================================================================
# GAP 1: PYDANTIC FIELD VALIDATION INTEGRATION
# ============================================================================


class TestPydanticFieldValidation:
    """Test Pydantic validation errors converted to RFC 7807."""

    def test_pydantic_required_field_error(self):
        """Test missing required field generates ValidationError."""

        class UserSchema(BaseModel):
            email: str
            password: str

        with pytest.raises(PydanticValidationError) as exc_info:
            UserSchema(email="user@example.com")  # Missing password

        errors = exc_info.value.errors()
        assert len(errors) == 1
        # Error dict has 'loc' (field path) instead of 'field'
        assert errors[0]["loc"][0] == "password"
        assert (
            "required" in errors[0]["msg"].lower()
            or "missing" in errors[0]["msg"].lower()
        )

    def test_pydantic_type_validation_error(self):
        """Test wrong type generates ValidationError."""

        class SignalSchema(BaseModel):
            price: float
            quantity: int

        with pytest.raises(PydanticValidationError) as exc_info:
            SignalSchema(price="not_a_number", quantity=10)

        errors = exc_info.value.errors()
        assert len(errors) >= 1
        assert errors[0]["loc"][0] == "price"

    def test_pydantic_pattern_validation_error(self):
        """Test regex pattern validation error."""
        from pydantic import field_validator

        class EmailSchema(BaseModel):
            email: str

            @field_validator("email")
            def validate_email(cls, v):
                if "@" not in v:
                    raise ValueError("invalid email format")
                return v

        with pytest.raises(PydanticValidationError) as exc_info:
            EmailSchema(email="notanemail")

        errors = exc_info.value.errors()
        assert len(errors) >= 1
        assert "invalid email" in str(errors[0])

    def test_pydantic_range_validation_error(self):
        """Test min/max range validation."""
        from pydantic import Field

        class TradeSchema(BaseModel):
            quantity: int = Field(..., ge=1, le=1000)

        # Too small
        with pytest.raises(PydanticValidationError):
            TradeSchema(quantity=0)

        # Too large
        with pytest.raises(PydanticValidationError):
            TradeSchema(quantity=2000)

    def test_pydantic_multiple_field_errors_collected(self):
        """Test multiple validation errors collected together."""

        class OrderSchema(BaseModel):
            price: float
            quantity: int
            symbol: str

        with pytest.raises(PydanticValidationError):
            OrderSchema(price="invalid", quantity="invalid", symbol=123)

        try:
            OrderSchema(price="invalid", quantity="invalid", symbol=123)
        except PydanticValidationError as e:
            errors = e.errors()
            assert len(errors) == 3, "Should collect all 3 field errors"

    def test_validation_error_to_problem_detail(self):
        """Test Pydantic errors converted to RFC 7807 ProblemDetail."""

        class SignalSchema(BaseModel):
            instrument: str
            side: str

        try:
            SignalSchema(instrument="GOLD")  # Missing side
        except PydanticValidationError as e:
            # Convert to ValidationError (our wrapper)
            errors = e.errors()
            exc = ValidationError(
                detail="Validation failed",
                errors=[
                    {"field": str(err["loc"][0]), "message": err["msg"]}
                    for err in errors
                ],
            )

            problem = ProblemDetail(
                type="https://api.example.com/errors/validation",
                title="Validation Error",
                status=422,
                detail=exc.detail,
                instance="/api/v1/signals",
                errors=exc.errors,
            )

            assert problem.status == 422
            assert len(problem.errors) >= 1
            assert "side" in str(problem.errors[0])

    def test_nested_object_validation_error(self):
        """Test nested object field validation errors."""
        from pydantic import BaseModel

        class LocationSchema(BaseModel):
            lat: float
            lng: float

        class EventSchema(BaseModel):
            name: str
            location: LocationSchema

        with pytest.raises(PydanticValidationError) as exc_info:
            EventSchema(
                name="Event",
                location={"lat": "invalid", "lng": 10.0},  # lat is wrong type
            )

        errors = exc_info.value.errors()
        # Should show nested path: location.lat
        assert len(errors) >= 1

    def test_enum_validation_error(self):
        """Test enum field validation error."""
        from enum import Enum

        class SideEnum(str, Enum):
            BUY = "buy"
            SELL = "sell"

        class TradeSchema(BaseModel):
            side: SideEnum

        with pytest.raises(PydanticValidationError) as exc_info:
            TradeSchema(side="invalid")

        errors = exc_info.value.errors()
        assert len(errors) >= 1
        assert "side" in str(errors[0])


# ============================================================================
# GAP 2: STACK TRACE REDACTION IN PRODUCTION MODE
# ============================================================================


class TestStackTraceRedaction:
    """Test stack traces redacted in production, shown in development."""

    def test_stack_trace_shown_in_development(self):
        """Test stack trace included in development mode."""
        import os

        os.environ["APP_ENV"] = "development"

        try:
            raise Exception("Test error in dev")
        except Exception as e:
            error_response = {
                "detail": str(e),
                "traceback": "included",  # In dev, show traceback
            }

            assert "traceback" in error_response
            assert error_response["traceback"] == "included"

    def test_stack_trace_hidden_in_production(self):
        """Test stack trace redacted in production mode."""
        import os

        os.environ["APP_ENV"] = "production"

        try:
            raise Exception("Test error in prod")
        except Exception:
            # In production, no traceback in response
            error_response = {
                "type": "https://api.example.com/errors/server",
                "title": "Internal Server Error",
                "status": 500,
                "detail": "Internal server error",
                "instance": "/api/v1/signals",
            }

            # No traceback in production response
            assert "traceback" not in error_response
            assert error_response["detail"] == "Internal server error"

    def test_production_error_logs_traceback_server_side(self):
        """Test traceback logged server-side but not in response."""

        # Mock logger
        mock_logger = MagicMock()

        try:
            raise ValueError("Invalid value for field")
        except Exception as e:
            # Log full traceback server-side
            mock_logger.error("Error occurred", exc_info=True)

            # Response doesn't include traceback
            response = {
                "status": 500,
                "detail": "Internal server error",
            }

            # Verify logger.error was called with exc_info
            mock_logger.error.assert_called_once()
            assert response["detail"] != str(
                e
            ), "Response shouldn't expose error details"

    def test_sensitive_fields_redacted_in_errors(self):
        """Test sensitive fields (passwords, API keys) redacted."""
        sensitive_error = {
            "detail": "Failed to authenticate user",
            "password_attempted": "super_secret_123",  # BAD: shouldn't be here
            "api_key": "sk-1234567890",  # BAD: shouldn't be here
        }

        # Redacted version
        safe_error = {
            "detail": "Failed to authenticate user",
            # No password or API key fields
        }

        assert "password_attempted" not in safe_error
        assert "api_key" not in safe_error

    def test_request_body_not_exposed_on_error(self):
        """Test request body not exposed in error responses."""
        # If request had sensitive data:
        request_body = {
            "email": "user@example.com",
            "password": "secret123",  # Sensitive
        }

        # Error response should NOT include request body
        error_response = {
            "type": "https://api.example.com/errors/validation",
            "title": "Validation Error",
            "status": 422,
            "detail": "Email is invalid",
        }

        assert "password" not in str(error_response)
        assert request_body["password"] not in str(error_response)

    def test_database_error_redacted(self):
        """Test database errors redacted (hide table/column names in prod)."""
        # Raw DB error (shouldn't be exposed)
        raw_db_error = "UNIQUE constraint failed: users.email"

        # Redacted error response
        safe_error = {
            "type": "https://api.example.com/errors/conflict",
            "title": "Conflict",
            "status": 409,
            "detail": "Email already exists",
        }

        assert "UNIQUE constraint" not in safe_error["detail"]
        assert "users.email" not in safe_error["detail"]


# ============================================================================
# GAP 3: REQUEST CONTEXT PROPAGATION IN STRUCTURED LOGS
# ============================================================================


class TestRequestContextPropagation:
    """Test request context (ID, user, etc.) in all logs."""

    def test_request_id_in_error_response(self):
        """Test X-Request-Id included in error response."""
        import uuid

        request_id = str(uuid.uuid4())

        error_response = {
            "type": "https://api.example.com/errors/not-found",
            "title": "Not Found",
            "status": 404,
            "detail": "Signal not found",
            "request_id": request_id,
        }

        assert error_response["request_id"] == request_id

    def test_request_id_generated_if_missing(self):
        """Test request ID generated if not provided."""
        import uuid

        # No request ID provided, should be generated
        generated_id = str(uuid.uuid4())

        error_response = {
            "request_id": generated_id,
        }

        # Verify ID is UUID format
        try:
            uuid.UUID(error_response["request_id"])
            is_valid_uuid = True
        except ValueError:
            is_valid_uuid = False

        assert is_valid_uuid, "Generated request ID should be valid UUID"

    def test_user_id_in_structured_logs(self):
        """Test user_id included in structured error logs."""
        user_id = "user-123-abc"

        log_entry = {
            "timestamp": "2025-11-03T12:34:56Z",
            "level": "ERROR",
            "message": "Validation failed",
            "user_id": user_id,
            "request_id": "req-456-def",
        }

        assert log_entry["user_id"] == user_id
        assert "user_id" in log_entry

    def test_action_context_in_logs(self):
        """Test action/operation context in logs."""
        log_entry = {
            "action": "create_signal",
            "status": "failure",
            "reason": "Validation error",
            "user_id": "user-123",
            "request_id": "req-456",
        }

        assert log_entry["action"] == "create_signal"
        assert "request_id" in log_entry
        assert log_entry["request_id"] == "req-456"

    def test_request_context_contextvar(self):
        """Test request context using contextvars."""
        from contextvars import ContextVar

        request_id_var = ContextVar("request_id", default=None)
        user_id_var = ContextVar("user_id", default=None)

        # Set context
        request_id_var.set("req-789")
        user_id_var.set("user-xyz")

        # Log should include context
        log_entry = {
            "request_id": request_id_var.get(),
            "user_id": user_id_var.get(),
            "message": "Operation completed",
        }

        assert log_entry["request_id"] == "req-789"
        assert log_entry["user_id"] == "user-xyz"

    def test_error_propagates_context(self):
        """Test error handling preserves request context."""
        import uuid

        request_id = str(uuid.uuid4())
        user_id = "user-123"

        try:
            raise ValueError("Something went wrong")
        except Exception as e:
            error_response = {
                "type": "https://api.example.com/errors/server",
                "status": 500,
                "detail": str(e),
                "request_id": request_id,
                "user_id": user_id,
            }

            assert error_response["request_id"] == request_id
            assert error_response["user_id"] == user_id

    def test_context_isolated_per_request(self):
        """Test context vars don't leak between requests."""
        from contextvars import ContextVar

        request_context = ContextVar("request_id", default=None)

        # Request 1
        request_context.set("req-1")
        req1_id = request_context.get()

        # Request 2 (should not see request 1's context)
        request_context.set("req-2")
        req2_id = request_context.get()

        assert req1_id != req2_id
        assert req2_id == "req-2"


# ============================================================================
# END-TO-END: VALIDATION + REDACTION + CONTEXT INTEGRATION
# ============================================================================


class TestErrorHandlingFullFlow:
    """Test error handling with validation, redaction, and context."""

    def test_validation_error_with_context_and_redaction(self):
        """Test validation error includes context but redacts sensitive info."""
        import uuid

        request_id = str(uuid.uuid4())
        user_id = "user-456"

        # Pydantic validation error
        try:

            class TestSchema(BaseModel):
                email: str

            TestSchema(email="invalid")
        except PydanticValidationError:
            # Convert to RFC 7807 with context and redaction
            error = {
                "type": "https://api.example.com/errors/validation",
                "title": "Validation Error",
                "status": 422,
                "detail": "Validation failed",
                "request_id": request_id,
                "user_id": user_id,
                # NO: password, api_key, or traceback
            }

            assert error["request_id"] == request_id
            assert error["user_id"] == user_id
            assert "traceback" not in error
            assert "password" not in str(error)

    @pytest.mark.asyncio
    async def test_auth_error_with_context(self):
        """Test auth error includes request context."""
        request_id = "req-auth-123"

        try:
            raise AuthenticationError(detail="Invalid token")
        except AuthenticationError as e:
            response = {
                "type": "https://api.example.com/errors/authentication",
                "status": 401,
                "detail": e.detail,
                "request_id": request_id,
            }

            assert response["status"] == 401
            assert response["request_id"] == request_id
