"""Exception classes for outbound signal module."""


class OutboundError(Exception):
    """Base exception for outbound signal module."""

    pass


class OutboundClientError(OutboundError):
    """Signal posting to server failed.

    Attributes:
        message: Human-readable error description
        http_code: HTTP status code (if applicable)
        details: Additional error details (dict)

    Example:
        >>> raise OutboundClientError(
        ...     "Signal validation failed",
        ...     http_code=400,
        ...     details={"field": "instrument", "error": "must be non-empty"}
        ... )
    """

    def __init__(
        self,
        message: str,
        http_code: int | None = None,
        details: dict | None = None,
    ) -> None:
        """Initialize OutboundClientError.

        Args:
            message: Error description
            http_code: HTTP status code if applicable
            details: Additional error details

        Example:
            >>> error = OutboundClientError("Connection failed", http_code=500)
            >>> error.message
            'Connection failed'
        """
        self.message = message
        self.http_code = http_code
        self.details = details or {}
        super().__init__(self.message)

    def __repr__(self) -> str:
        """Return detailed string representation."""
        parts = [f"OutboundClientError({self.message!r}"]
        if self.http_code:
            parts.append(f", http_code={self.http_code}")
        if self.details:
            parts.append(f", details={self.details}")
        return "".join(parts) + ")"


class OutboundSignatureError(OutboundError):
    """HMAC signature generation or verification failed.

    Example:
        >>> raise OutboundSignatureError("Invalid timestamp format")
    """

    pass
