"""Configuration management for FXPro Trading Bot platform.

Settings are loaded from environment variables with validation and type checking.
Production deployments require explicit APP_VERSION and APP_BUILD.
"""

import subprocess
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    APP_NAME: str = Field(default="fxpro-trading-bot", description="Application name")
    APP_ENV: Literal["development", "staging", "production"] = Field(
        default="development", description="Environment name"
    )
    APP_VERSION: str = Field(
        default="0.1.0", description="Application semantic version"
    )
    APP_BUILD: str = Field(default="local", description="Build identifier (git SHA)")
    APP_LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    APP_REQUEST_ID_HEADER: str = Field(
        default="X-Request-Id", description="Request ID header name"
    )

    # Database configuration
    DB_DSN: str = Field(
        default="postgresql+psycopg://user:pass@localhost:5432/app",
        description="PostgreSQL connection string",
    )
    DB_POOL_SIZE: int = Field(default=10, description="Connection pool size")
    DB_MAX_OVERFLOW: int = Field(default=10, description="Maximum overflow connections")
    DB_POOL_PRE_PING: bool = Field(
        default=True, description="Test connections before using"
    )
    DB_ECHO: bool = Field(default=False, description="Echo SQL queries")

    # Security
    HMAC_PRODUCER_ENABLED: bool = Field(
        default=False, description="Enable HMAC signature validation for producers"
    )
    HMAC_PRODUCER_SECRET: str = Field(
        default="", description="Secret key for HMAC validation"
    )

    # Validation
    SIGNALS_PAYLOAD_MAX_BYTES: int = Field(
        default=32768, description="Maximum signal payload size"
    )

    class Config:
        """Pydantic config."""

        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

    def __init__(self, **data):
        """Initialize settings and validate production requirements."""
        super().__init__(**data)

        # Production validation
        if self.APP_ENV == "production":
            if self.APP_VERSION == "0.1.0":
                raise ValueError(
                    "APP_VERSION must be explicitly set for production (not default)"
                )
            if self.APP_BUILD == "local":
                raise ValueError(
                    "APP_BUILD must be explicitly set for production (git SHA or CI build ID)"
                )

    @staticmethod
    def get_build_info() -> str:
        """Get git SHA or fallback to 'unknown'."""
        try:
            sha = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            return sha
        except (subprocess.CalledProcessError, FileNotFoundError):
            return "unknown"


# Global settings instance
settings = Settings()
