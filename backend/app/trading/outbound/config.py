"""Configuration management for outbound signal client."""

import os
from dataclasses import dataclass


@dataclass
class OutboundConfig:
    """Configuration for HMAC-signed outbound signal client.

    Attributes:
        producer_id: Unique identifier for this producer (e.g., "mt5-gold-trader")
        producer_secret: Secret key for HMAC-SHA256 signing
        server_base_url: Target server base URL (e.g., "https://api.example.com")
        enabled: Feature flag to enable/disable outbound posting
        timeout_seconds: HTTP request timeout
        max_body_size: Maximum signal body size in bytes (default 64 KB)

    Example:
        >>> config = OutboundConfig(
        ...     producer_id="mt5-trader-1",
        ...     producer_secret="my-secret-key-at-least-16-bytes",
        ...     server_base_url="https://api.example.com",
        ...     enabled=True,
        ...     timeout_seconds=30.0
        ... )
        >>> config.validate()  # Raises ValueError if invalid
    """

    producer_id: str
    producer_secret: str
    server_base_url: str
    enabled: bool = True
    timeout_seconds: float = 30.0
    max_body_size: int = 65536  # 64 KB

    def __post_init__(self) -> None:
        """Validate configuration on initialization."""
        self.validate()

    def validate(self) -> None:
        """Validate configuration parameters.

        Raises:
            ValueError: If any configuration is invalid

        Example:
            >>> config = OutboundConfig(..., timeout_seconds=2.0)
            >>> config.validate()  # Raises ValueError
            Traceback (most recent call last):
                ...
            ValueError: timeout_seconds must be >= 5.0
        """
        if not self.producer_id or not self.producer_id.strip():
            raise ValueError("producer_id must be non-empty")

        if not self.producer_secret or not self.producer_secret.strip():
            raise ValueError("producer_secret must be non-empty")

        if len(self.producer_secret) < 16:
            raise ValueError("producer_secret must be at least 16 bytes")

        if not self.server_base_url or not self.server_base_url.strip():
            raise ValueError("server_base_url must be non-empty")

        if self.timeout_seconds < 5.0:
            raise ValueError("timeout_seconds must be >= 5.0")

        if self.timeout_seconds > 300.0:
            raise ValueError("timeout_seconds must be <= 300.0")

        if self.max_body_size < 1024:
            raise ValueError("max_body_size must be >= 1024 bytes")

        if self.max_body_size > 10_485_760:  # 10 MB
            raise ValueError("max_body_size must be <= 10 MB")

    @classmethod
    def from_env(cls) -> "OutboundConfig":
        """Load configuration from environment variables.

        Environment Variables:
            HMAC_PRODUCER_ENABLED: "true" or "false" (default: "true")
            HMAC_PRODUCER_SECRET: Secret key for HMAC signing (required if enabled)
            PRODUCER_ID: Producer identifier (default: from hostname)
            OUTBOUND_SERVER_URL: Server base URL (required)
            OUTBOUND_TIMEOUT_SECONDS: Request timeout (default: "30")
            OUTBOUND_MAX_BODY_SIZE: Max body size (default: "65536")

        Returns:
            OutboundConfig: Loaded and validated configuration

        Raises:
            ValueError: If required environment variables are missing or invalid

        Example:
            >>> os.environ.update({
            ...     "HMAC_PRODUCER_ENABLED": "true",
            ...     "HMAC_PRODUCER_SECRET": "my-secret-key",
            ...     "PRODUCER_ID": "mt5-trader-1",
            ...     "OUTBOUND_SERVER_URL": "https://api.example.com"
            ... })
            >>> config = OutboundConfig.from_env()
            >>> config.producer_id
            'mt5-trader-1'
        """
        enabled_str = os.getenv("HMAC_PRODUCER_ENABLED", "true").lower()
        enabled = enabled_str in ("true", "1", "yes")

        if not enabled:
            # Return disabled config with minimal required fields
            return cls(
                producer_id="disabled",
                producer_secret="disabled",
                server_base_url="disabled",
                enabled=False,
                timeout_seconds=30.0,
            )

        producer_secret = os.getenv("HMAC_PRODUCER_SECRET")
        if not producer_secret:
            raise ValueError(
                "HMAC_PRODUCER_SECRET environment variable required when "
                "HMAC_PRODUCER_ENABLED=true"
            )

        server_url = os.getenv("OUTBOUND_SERVER_URL")
        if not server_url:
            raise ValueError("OUTBOUND_SERVER_URL environment variable required")

        producer_id = os.getenv("PRODUCER_ID", "unknown-producer")

        timeout_str = os.getenv("OUTBOUND_TIMEOUT_SECONDS", "30")
        try:
            timeout = float(timeout_str)
        except ValueError as e:
            raise ValueError(
                f"OUTBOUND_TIMEOUT_SECONDS must be a float, got {timeout_str!r}"
            ) from e

        max_body_size_str = os.getenv("OUTBOUND_MAX_BODY_SIZE", "65536")
        try:
            max_body_size = int(max_body_size_str)
        except ValueError as e:
            raise ValueError(
                f"OUTBOUND_MAX_BODY_SIZE must be an integer, got {max_body_size_str!r}"
            ) from e

        return cls(
            producer_id=producer_id,
            producer_secret=producer_secret,
            server_base_url=server_url,
            enabled=True,
            timeout_seconds=timeout,
            max_body_size=max_body_size,
        )

    def __repr__(self) -> str:
        """Return string representation (with redacted secret)."""
        secret_masked = f"{self.producer_secret[:4]}...{self.producer_secret[-4:]}"
        return (
            f"OutboundConfig(producer_id={self.producer_id!r}, "
            f"producer_secret={secret_masked!r}, "
            f"server_base_url={self.server_base_url!r}, "
            f"enabled={self.enabled}, "
            f"timeout_seconds={self.timeout_seconds})"
        )
