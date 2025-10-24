"""RFC 7807 Problem Details error handling."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Request, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ProblemDetail(BaseModel):
    """RFC 7807 Problem Detail model for API errors.
    
    Spec: https://tools.ietf.org/html/rfc7807
    
    Example:
        {
            "type": "https://api.example.com/errors/validation",
            "title": "Validation Error",
            "status": 422,
            "detail": "Request validation failed",
            "instance": "/api/v1/users",
            "request_id": "550e8400-e29b-41d4-a716-446655440000",
            "timestamp": "2024-01-15T10:30:00Z",
            "errors": [
                {"field": "email", "message": "Invalid email format"}
            ]
        }
    """

    type: str = Field(
        ...,
        description="URI identifying error type (e.g., https://api.example.com/errors/validation)",
    )
    title: str = Field(..., description="Short error title (e.g., 'Validation Error')")
    status: int = Field(..., description="HTTP status code")
    detail: str = Field(..., description="Detailed error message for client")
    instance: Optional[str] = Field(
        None, description="URI of problematic resource (e.g., /api/v1/users/123)"
    )
    request_id: Optional[str] = Field(
        None, description="Correlation ID for tracing (from X-Request-Id)"
    )
    timestamp: Optional[str] = Field(
        None, description="ISO 8601 timestamp when error occurred"
    )
    errors: Optional[list[dict[str, str]]] = Field(
        None, description="Field-level validation errors"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "type": "https://api.example.com/errors/validation",
                "title": "Validation Error",
                "status": 422,
                "detail": "Request body validation failed",
                "instance": "/api/v1/users",
                "request_id": "550e8400-e29b-41d4-a716-446655440000",
                "timestamp": "2024-01-15T10:30:00Z",
                "errors": [{"field": "email", "message": "Invalid email format"}],
            }
        }


# Error type URIs (use consistent domain for your API)
ERROR_TYPES = {
    "validation": "https://api.tradingsignals.local/errors/validation",
    "authentication": "https://api.tradingsignals.local/errors/authentication",
    "authorization": "https://api.tradingsignals.local/errors/authorization",
    "not_found": "https://api.tradingsignals.local/errors/not-found",
    "conflict": "https://api.tradingsignals.local/errors/conflict",
    "rate_limit": "https://api.tradingsignals.local/errors/rate-limit",
    "server_error": "https://api.tradingsignals.local/errors/server-error",
}


class APIException(Exception):
    """Base class for API exceptions that map to RFC 7807 responses.
    
    Example:
        raise APIException(
            status_code=400,
            error_type="validation",
            title="Invalid Input",
            detail="Email must be unique",
            errors=[{"field": "email", "message": "Already registered"}]
        )
    """

    def __init__(
        self,
        status_code: int,
        error_type: str,
        title: str,
        detail: str,
        instance: Optional[str] = None,
        errors: Optional[list[dict[str, str]]] = None,
    ):
        """Initialize API exception.
        
        Args:
            status_code: HTTP status code (400, 401, 403, 404, 409, 422, 429, 500)
            error_type: Key from ERROR_TYPES (validation, authentication, etc.)
            title: Short error title
            detail: Detailed error message
            instance: Optional URI of problematic resource
            errors: Optional list of field-level errors
        """
        self.status_code = status_code
        self.error_type = error_type
        self.title = title
        self.detail = detail
        self.instance = instance
        self.errors = errors
        super().__init__(detail)

    def to_problem_detail(self, request_id: Optional[str] = None) -> ProblemDetail:
        """Convert exception to RFC 7807 ProblemDetail.
        
        Args:
            request_id: Correlation ID for tracing
        
        Returns:
            ProblemDetail: RFC 7807 formatted error response
        """
        return ProblemDetail(
            type=ERROR_TYPES.get(self.error_type, ERROR_TYPES["server_error"]),
            title=self.title,
            status=self.status_code,
            detail=self.detail,
            instance=self.instance,
            request_id=request_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            errors=self.errors,
        )


class ValidationError(APIException):
    """Validation error (422)."""

    def __init__(
        self,
        detail: str,
        instance: Optional[str] = None,
        errors: Optional[list[dict[str, str]]] = None,
    ):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_type="validation",
            title="Validation Error",
            detail=detail,
            instance=instance,
            errors=errors,
        )


class AuthenticationError(APIException):
    """Authentication error (401)."""

    def __init__(self, detail: str = "Authentication required"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_type="authentication",
            title="Authentication Error",
            detail=detail,
        )


class AuthorizationError(APIException):
    """Authorization error (403)."""

    def __init__(self, detail: str = "Insufficient permissions"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            error_type="authorization",
            title="Authorization Error",
            detail=detail,
        )


class NotFoundError(APIException):
    """Not found error (404)."""

    def __init__(self, resource: str, resource_id: Optional[str] = None):
        detail = f"{resource} not found"
        instance = f"/{resource.lower()}/{resource_id}" if resource_id else None
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            error_type="not_found",
            title="Not Found",
            detail=detail,
            instance=instance,
        )


class ConflictError(APIException):
    """Conflict error (409)."""

    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            error_type="conflict",
            title="Conflict",
            detail=detail,
        )


class RateLimitError(APIException):
    """Rate limit error (429)."""

    def __init__(self, detail: str = "Too many requests"):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error_type="rate_limit",
            title="Rate Limit Exceeded",
            detail=detail,
        )


class ServerError(APIException):
    """Server error (500)."""

    def __init__(self, detail: str = "Internal server error"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_type="server_error",
            title="Server Error",
            detail=detail,
        )


async def problem_detail_exception_handler(request: Request, exc: APIException):
    """FastAPI exception handler for APIException.
    
    Converts APIException to RFC 7807 ProblemDetail response.
    
    Args:
        request: HTTP request
        exc: APIException instance
    
    Returns:
        JSONResponse: RFC 7807 formatted error response
    """
    from fastapi.responses import JSONResponse

    # Get request ID from headers
    request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))

    # Convert to problem detail
    problem_detail = exc.to_problem_detail(request_id=request_id)

    # Log error
    logger.warning(
        f"API Error: {exc.title}",
        extra={
            "status_code": exc.status_code,
            "error_type": exc.error_type,
            "request_id": request_id,
            "path": request.url.path,
        },
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=problem_detail.model_dump(exclude_none=True),
    )


async def pydantic_validation_exception_handler(request: Request, exc: Exception):
    """Handle Pydantic validation errors and convert to RFC 7807.
    
    Args:
        request: HTTP request
        exc: Exception from Pydantic
    
    Returns:
        JSONResponse: RFC 7807 formatted validation error response
    """
    from fastapi.responses import JSONResponse
    from pydantic_core import ValidationError as PydanticValidationError

    # Extract field errors from Pydantic ValidationError
    errors = []
    if isinstance(exc, PydanticValidationError):
        for error in exc.errors():
            field_path = ".".join(str(p) for p in error["loc"])
            errors.append({
                "field": field_path,
                "message": error["msg"],
                "type": error["type"],
            })

    request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))

    problem_detail = ProblemDetail(
        type=ERROR_TYPES["validation"],
        title="Request Validation Error",
        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Request body validation failed",
        instance=request.url.path,
        request_id=request_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        errors=errors if errors else None,
    )

    logger.warning(
        "Validation error",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "errors": errors,
        },
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=problem_detail.model_dump(exclude_none=True),
    )


async def generic_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions and convert to RFC 7807.
    
    Args:
        request: HTTP request
        exc: Unexpected exception
    
    Returns:
        JSONResponse: RFC 7807 formatted server error response
    """
    from fastapi.responses import JSONResponse

    request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))

    # Log full error in production
    logger.error(
        "Unexpected error",
        exc_info=exc,
        extra={
            "request_id": request_id,
            "path": request.url.path,
        },
    )

    problem_detail = ProblemDetail(
        type=ERROR_TYPES["server_error"],
        title="Internal Server Error",
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An unexpected error occurred",
        instance=request.url.path,
        request_id=request_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=problem_detail.model_dump(exclude_none=True),
    )
