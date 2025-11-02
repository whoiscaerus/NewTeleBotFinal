"""
PR-006: Error Handling - REAL Business Logic Tests

Tests the REAL FastAPI exception handlers with REAL HTTP responses,
REAL RFC 7807 Problem Detail formatting, REAL status codes, REAL request ID tracking.

NO MOCKS - validates actual error responses from FastAPI app.
"""

import json
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.core.errors import (
    ERROR_TYPES,
    APIException,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ProblemDetail,
    RateLimitError,
    ServerError,
    ValidationError,
    problem_detail_exception_handler,
)


class TestProblemDetailModelREAL:
    """✅ REAL TEST: RFC 7807 ProblemDetail model."""

    def test_problem_detail_valid_structure(self):
        """✅ REAL TEST: ProblemDetail creates valid RFC 7807 structure."""
        detail = ProblemDetail(
            type="https://api.example.com/errors/validation",
            title="Validation Error",
            status=422,
            detail="Email is required",
            instance="/api/v1/users",
            request_id="req-123",
            timestamp="2025-01-15T10:00:00Z",
        )

        assert detail.type == "https://api.example.com/errors/validation"
        assert detail.title == "Validation Error"
        assert detail.status == 422
        assert detail.detail == "Email is required"
        assert detail.instance == "/api/v1/users"
        assert detail.request_id == "req-123"

    def test_problem_detail_with_field_errors(self):
        """✅ REAL TEST: ProblemDetail includes field-level errors."""
        detail = ProblemDetail(
            type=ERROR_TYPES["validation"],
            title="Validation Error",
            status=422,
            detail="Request validation failed",
            instance="/api/v1/users",
            request_id="req-456",
            timestamp="2025-01-15T10:00:00Z",
            errors=[
                {"field": "email", "message": "Invalid email format"},
                {"field": "password", "message": "Must be at least 8 characters"},
            ],
        )

        assert len(detail.errors) == 2
        assert detail.errors[0]["field"] == "email"
        assert detail.errors[1]["field"] == "password"

    def test_problem_detail_json_serializable(self):
        """✅ REAL TEST: ProblemDetail serializes to valid JSON."""
        detail = ProblemDetail(
            type=ERROR_TYPES["validation"],
            title="Validation Error",
            status=422,
            detail="Request validation failed",
        )

        # Should be serializable
        json_str = detail.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["type"] == ERROR_TYPES["validation"]
        assert parsed["title"] == "Validation Error"
        assert parsed["status"] == 422

    def test_problem_detail_excludes_none_fields(self):
        """✅ REAL TEST: ProblemDetail excludes None fields when serializing."""
        detail = ProblemDetail(
            type=ERROR_TYPES["validation"],
            title="Validation Error",
            status=422,
            detail="Request validation failed",
            instance=None,
            errors=None,
        )

        data = detail.model_dump(exclude_none=True)

        assert "instance" not in data
        assert "errors" not in data
        assert "type" in data
        assert "title" in data


class TestAPIExceptionREAL:
    """✅ REAL TEST: APIException base class."""

    def test_api_exception_initialization(self):
        """✅ REAL TEST: APIException initializes correctly."""
        exc = APIException(
            status_code=400,
            error_type="validation",
            title="Invalid Input",
            detail="Email is required",
        )

        assert exc.status_code == 400
        assert exc.error_type == "validation"
        assert exc.title == "Invalid Input"
        assert exc.detail == "Email is required"

    def test_api_exception_to_problem_detail(self):
        """✅ REAL TEST: APIException converts to ProblemDetail."""
        exc = APIException(
            status_code=400,
            error_type="validation",
            title="Invalid Input",
            detail="Email is required",
            instance="/api/v1/users",
        )

        detail = exc.to_problem_detail(request_id="req-789")

        assert detail.status == 400
        assert detail.title == "Invalid Input"
        assert detail.request_id == "req-789"
        assert detail.instance == "/api/v1/users"

    def test_api_exception_with_field_errors(self):
        """✅ REAL TEST: APIException includes field-level errors."""
        exc = APIException(
            status_code=422,
            error_type="validation",
            title="Validation Error",
            detail="Request validation failed",
            errors=[
                {"field": "email", "message": "Invalid format"},
                {"field": "age", "message": "Must be positive"},
            ],
        )

        detail = exc.to_problem_detail()

        assert len(detail.errors) == 2
        assert detail.errors[0]["field"] == "email"


class TestValidationErrorREAL:
    """✅ REAL TEST: ValidationError exception."""

    def test_validation_error_422_status(self):
        """✅ REAL TEST: ValidationError returns 422 status code."""
        exc = ValidationError(detail="Email is required")

        assert exc.status_code == 422
        assert exc.error_type == "validation"
        assert exc.title == "Validation Error"

    def test_validation_error_with_field_errors(self):
        """✅ REAL TEST: ValidationError includes field errors."""
        exc = ValidationError(
            detail="Multiple validation errors",
            errors=[
                {"field": "email", "message": "Required"},
                {"field": "password", "message": "Too short"},
            ],
        )

        detail = exc.to_problem_detail()

        assert detail.status == 422
        assert len(detail.errors) == 2


class TestAuthenticationErrorREAL:
    """✅ REAL TEST: AuthenticationError exception."""

    def test_authentication_error_401_status(self):
        """✅ REAL TEST: AuthenticationError returns 401 status code."""
        exc = AuthenticationError()

        assert exc.status_code == 401
        assert exc.error_type == "authentication"
        assert exc.title == "Authentication Error"

    def test_authentication_error_custom_message(self):
        """✅ REAL TEST: AuthenticationError allows custom message."""
        exc = AuthenticationError(detail="Invalid credentials")

        assert exc.detail == "Invalid credentials"


class TestAuthorizationErrorREAL:
    """✅ REAL TEST: AuthorizationError exception."""

    def test_authorization_error_403_status(self):
        """✅ REAL TEST: AuthorizationError returns 403 status code."""
        exc = AuthorizationError()

        assert exc.status_code == 403
        assert exc.error_type == "authorization"
        assert exc.title == "Authorization Error"

    def test_authorization_error_custom_message(self):
        """✅ REAL TEST: AuthorizationError allows custom message."""
        exc = AuthorizationError(detail="User must be admin")

        assert exc.detail == "User must be admin"


class TestNotFoundErrorREAL:
    """✅ REAL TEST: NotFoundError exception."""

    def test_not_found_error_404_status(self):
        """✅ REAL TEST: NotFoundError returns 404 status code."""
        exc = NotFoundError(resource="User")

        assert exc.status_code == 404
        assert exc.error_type == "not_found"
        assert exc.title == "Not Found"
        assert exc.detail == "User not found"

    def test_not_found_error_with_resource_id(self):
        """✅ REAL TEST: NotFoundError includes resource instance."""
        exc = NotFoundError(resource="User", resource_id="usr_123")

        assert exc.instance == "/user/usr_123"
        assert exc.detail == "User not found"

    def test_not_found_error_different_resources(self):
        """✅ REAL TEST: NotFoundError works for different resource types."""
        resources = ["User", "Signal", "Trade", "Portfolio"]

        for resource in resources:
            exc = NotFoundError(resource=resource)
            assert f"{resource} not found" in exc.detail


class TestConflictErrorREAL:
    """✅ REAL TEST: ConflictError exception."""

    def test_conflict_error_409_status(self):
        """✅ REAL TEST: ConflictError returns 409 status code."""
        exc = ConflictError(detail="Email already registered")

        assert exc.status_code == 409
        assert exc.error_type == "conflict"
        assert exc.title == "Conflict"
        assert exc.detail == "Email already registered"


class TestRateLimitErrorREAL:
    """✅ REAL TEST: RateLimitError exception."""

    def test_rate_limit_error_429_status(self):
        """✅ REAL TEST: RateLimitError returns 429 status code."""
        exc = RateLimitError()

        assert exc.status_code == 429
        assert exc.error_type == "rate_limit"
        assert exc.title == "Rate Limit Exceeded"

    def test_rate_limit_error_custom_message(self):
        """✅ REAL TEST: RateLimitError allows custom message."""
        exc = RateLimitError(detail="10 requests per minute limit exceeded")

        assert exc.detail == "10 requests per minute limit exceeded"


class TestServerErrorREAL:
    """✅ REAL TEST: ServerError exception."""

    def test_server_error_500_status(self):
        """✅ REAL TEST: ServerError returns 500 status code."""
        exc = ServerError()

        assert exc.status_code == 500
        assert exc.error_type == "server_error"
        assert exc.title == "Server Error"

    def test_server_error_custom_message(self):
        """✅ REAL TEST: ServerError allows custom message."""
        exc = ServerError(detail="Database connection failed")

        assert exc.detail == "Database connection failed"


class TestExceptionHandlerIntegrationREAL:
    """✅ REAL TEST: FastAPI exception handlers with actual app."""

    @pytest.fixture
    def app_with_handlers(self):
        """Create FastAPI app with exception handlers."""
        app = FastAPI()

        # Add exception handler
        app.add_exception_handler(
            APIException,
            problem_detail_exception_handler,
        )

        # Add test routes
        @app.get("/validation-error")
        def validation_error():
            raise ValidationError(
                detail="Email is required",
                errors=[{"field": "email", "message": "Required"}],
            )

        @app.get("/auth-error")
        def auth_error():
            raise AuthenticationError(detail="Invalid token")

        @app.get("/authz-error")
        def authz_error():
            raise AuthorizationError(detail="Admin only")

        @app.get("/not-found")
        def not_found():
            raise NotFoundError(resource="User", resource_id="123")

        @app.get("/conflict")
        def conflict():
            raise ConflictError(detail="Email already taken")

        @app.get("/rate-limit")
        def rate_limit():
            raise RateLimitError(detail="Limit exceeded")

        @app.get("/server-error")
        def server_error():
            raise ServerError(detail="Database error")

        return app

    def test_validation_error_response(self, app_with_handlers):
        """✅ REAL TEST: Validation error returns 422 with RFC 7807."""
        client = TestClient(app_with_handlers)

        response = client.get("/validation-error")

        assert response.status_code == 422
        data = response.json()
        assert data["type"] == ERROR_TYPES["validation"]
        assert data["title"] == "Validation Error"
        assert data["status"] == 422
        assert len(data["errors"]) > 0

    def test_authentication_error_response(self, app_with_handlers):
        """✅ REAL TEST: Auth error returns 401 with RFC 7807."""
        client = TestClient(app_with_handlers)

        response = client.get("/auth-error")

        assert response.status_code == 401
        data = response.json()
        assert data["type"] == ERROR_TYPES["authentication"]
        assert data["title"] == "Authentication Error"
        assert data["status"] == 401

    def test_authorization_error_response(self, app_with_handlers):
        """✅ REAL TEST: Authz error returns 403 with RFC 7807."""
        client = TestClient(app_with_handlers)

        response = client.get("/authz-error")

        assert response.status_code == 403
        data = response.json()
        assert data["type"] == ERROR_TYPES["authorization"]
        assert data["title"] == "Authorization Error"

    def test_not_found_error_response(self, app_with_handlers):
        """✅ REAL TEST: Not found error returns 404 with RFC 7807."""
        client = TestClient(app_with_handlers)

        response = client.get("/not-found")

        assert response.status_code == 404
        data = response.json()
        assert data["type"] == ERROR_TYPES["not_found"]
        assert data["title"] == "Not Found"
        assert data["instance"] == "/user/123"

    def test_conflict_error_response(self, app_with_handlers):
        """✅ REAL TEST: Conflict error returns 409 with RFC 7807."""
        client = TestClient(app_with_handlers)

        response = client.get("/conflict")

        assert response.status_code == 409
        data = response.json()
        assert data["type"] == ERROR_TYPES["conflict"]
        assert data["status"] == 409

    def test_rate_limit_error_response(self, app_with_handlers):
        """✅ REAL TEST: Rate limit error returns 429 with RFC 7807."""
        client = TestClient(app_with_handlers)

        response = client.get("/rate-limit")

        assert response.status_code == 429
        data = response.json()
        assert data["type"] == ERROR_TYPES["rate_limit"]

    def test_server_error_response(self, app_with_handlers):
        """✅ REAL TEST: Server error returns 500 with RFC 7807."""
        client = TestClient(app_with_handlers)

        response = client.get("/server-error")

        assert response.status_code == 500
        data = response.json()
        assert data["type"] == ERROR_TYPES["server_error"]

    def test_response_includes_request_id(self, app_with_handlers):
        """✅ REAL TEST: Error response includes request_id from header."""
        client = TestClient(app_with_handlers)

        response = client.get(
            "/validation-error", headers={"X-Request-Id": "req-test-123"}
        )

        data = response.json()
        assert data["request_id"] == "req-test-123"

    def test_response_generates_request_id_if_missing(self, app_with_handlers):
        """✅ REAL TEST: Error response generates request_id if not provided."""
        client = TestClient(app_with_handlers)

        response = client.get("/validation-error")

        data = response.json()
        # Should have generated a request_id
        assert "request_id" in data
        assert data["request_id"] is not None
        assert len(data["request_id"]) > 0

    def test_response_includes_timestamp(self, app_with_handlers):
        """✅ REAL TEST: Error response includes ISO 8601 timestamp."""
        client = TestClient(app_with_handlers)

        response = client.get("/validation-error")

        data = response.json()
        assert "timestamp" in data

        # Should be parseable as ISO datetime
        ts = datetime.fromisoformat(data["timestamp"])
        assert ts is not None

    def test_response_has_all_required_fields(self, app_with_handlers):
        """✅ REAL TEST: Error response has all RFC 7807 required fields."""
        client = TestClient(app_with_handlers)

        response = client.get("/validation-error")

        data = response.json()

        # RFC 7807 required fields
        assert "type" in data
        assert "title" in data
        assert "status" in data
        assert "detail" in data


class TestErrorTypeURIsREAL:
    """✅ REAL TEST: Error type URIs are consistent."""

    def test_all_error_types_have_uri(self):
        """✅ REAL TEST: All error types have corresponding URIs."""
        expected_types = {
            "validation",
            "authentication",
            "authorization",
            "not_found",
            "conflict",
            "rate_limit",
            "server_error",
        }

        for error_type in expected_types:
            assert error_type in ERROR_TYPES
            assert ERROR_TYPES[error_type].startswith("https://")

    def test_error_type_uris_unique(self):
        """✅ REAL TEST: Each error type has unique URI."""
        uris = list(ERROR_TYPES.values())
        unique_uris = set(uris)

        assert len(uris) == len(unique_uris)

    def test_error_type_uris_domain_consistent(self):
        """✅ REAL TEST: All URIs use same domain."""
        domains = set()

        for uri in ERROR_TYPES.values():
            # Extract domain from https://domain.com/...
            domain = uri.split("/")[2]
            domains.add(domain)

        # All should be from same domain
        assert len(domains) == 1


class TestErrorResponseContentTypeREAL:
    """✅ REAL TEST: Error responses have correct content type."""

    @pytest.fixture
    def app_with_handlers(self):
        """Create FastAPI app with exception handlers."""
        app = FastAPI()

        app.add_exception_handler(
            APIException,
            problem_detail_exception_handler,
        )

        @app.get("/error")
        def error_endpoint():
            raise ValidationError(detail="Test error")

        return app

    def test_error_response_content_type_json(self, app_with_handlers):
        """✅ REAL TEST: Error response has application/json content type."""
        client = TestClient(app_with_handlers)

        response = client.get("/error")

        assert response.headers["content-type"] == "application/json"


class TestErrorFieldValidationREAL:
    """✅ REAL TEST: Field-level error details."""

    def test_field_error_includes_field_name(self):
        """✅ REAL TEST: Field error includes field name."""
        errors = [{"field": "email", "message": "Invalid format"}]

        exc = ValidationError(detail="Validation failed", errors=errors)

        detail = exc.to_problem_detail()

        assert detail.errors[0]["field"] == "email"

    def test_multiple_field_errors(self):
        """✅ REAL TEST: Can include multiple field errors."""
        errors = [
            {"field": "email", "message": "Invalid format"},
            {"field": "password", "message": "Too short"},
            {"field": "age", "message": "Must be positive"},
        ]

        exc = ValidationError(detail="Validation failed", errors=errors)

        assert len(exc.errors) == 3

    def test_field_error_message_clarity(self):
        """✅ REAL TEST: Field error messages are clear."""
        errors = [
            {"field": "email", "message": "Must be a valid email address"},
            {"field": "password", "message": "Must be at least 8 characters"},
        ]

        exc = ValidationError(detail="Validation failed", errors=errors)
        detail = exc.to_problem_detail()

        # Messages should be user-friendly
        for error in detail.errors:
            assert len(error["message"]) > 0
            assert "field" in error


class TestErrorInstanceURIREAL:
    """✅ REAL TEST: Instance URI in error responses."""

    def test_instance_uri_for_not_found(self):
        """✅ REAL TEST: Not found error includes instance URI."""
        exc = NotFoundError(resource="User", resource_id="usr_123")

        detail = exc.to_problem_detail()

        assert detail.instance == "/user/usr_123"

    def test_instance_uri_optional(self):
        """✅ REAL TEST: Instance URI is optional."""
        exc = ValidationError(detail="Invalid input")

        detail = exc.to_problem_detail()

        # Should serialize without instance
        data = detail.model_dump(exclude_none=True)
        assert "instance" not in data

    def test_instance_uri_included_when_provided(self):
        """✅ REAL TEST: Instance URI included when provided."""
        exc = APIException(
            status_code=400,
            error_type="validation",
            title="Invalid",
            detail="Bad request",
            instance="/api/v1/users/123",
        )

        detail = exc.to_problem_detail()

        assert detail.instance == "/api/v1/users/123"
        # Should be in serialized output
        data = detail.model_dump(exclude_none=True)
        assert data["instance"] == "/api/v1/users/123"
