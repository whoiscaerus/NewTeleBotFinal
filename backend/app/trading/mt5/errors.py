"""MT5 session-related exceptions."""


class MT5Error(Exception):
    """Base exception for MT5-related errors."""

    pass


class MT5InitError(MT5Error):
    """Raised when MT5 initialization fails."""

    def __init__(self, message: str, terminal_path: str | None = None):
        """Initialize MT5InitError.

        Args:
            message: Error description
            terminal_path: Path to MT5 terminal (if applicable)
        """
        self.message = message
        self.terminal_path = terminal_path
        super().__init__(f"MT5 init failed: {message}")


class MT5AuthError(MT5Error):
    """Raised when MT5 authentication/login fails."""

    def __init__(self, message: str, login: str | None = None):
        """Initialize MT5AuthError.

        Args:
            message: Error description
            login: Account login (if applicable)
        """
        self.message = message
        self.login = login
        super().__init__(f"MT5 auth failed: {message}")


class MT5Disconnected(MT5Error):
    """Raised when MT5 becomes unexpectedly disconnected."""

    def __init__(
        self,
        message: str,
        retry_after_seconds: int | None = None,
    ):
        """Initialize MT5Disconnected.

        Args:
            message: Error description
            retry_after_seconds: Suggested wait time before reconnect attempt
        """
        self.message = message
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"MT5 disconnected: {message}"
            + (f" (retry after {retry_after_seconds}s)" if retry_after_seconds else "")
        )


class MT5CircuitBreakerOpen(MT5Error):
    """Raised when MT5 circuit breaker is open (too many failures)."""

    def __init__(
        self,
        message: str,
        failure_count: int,
        max_failures: int,
        reset_after_seconds: int | None = None,
    ):
        """Initialize MT5CircuitBreakerOpen.

        Args:
            message: Error description
            failure_count: Current failure count
            max_failures: Threshold that triggered the breaker
            reset_after_seconds: Time until circuit breaker resets
        """
        self.message = message
        self.failure_count = failure_count
        self.max_failures = max_failures
        self.reset_after_seconds = reset_after_seconds
        super().__init__(
            f"MT5 circuit breaker open: {message} "
            f"({failure_count}/{max_failures} failures)"
            + (f", reset in {reset_after_seconds}s" if reset_after_seconds else "")
        )
