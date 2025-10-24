"""Application settings and configuration using Pydantic v2."""

import os
from typing import Literal

from pydantic import ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings


class AppSettings(BaseSettings):
    """Application settings."""

    env: Literal["development", "staging", "production"] = Field(
        default="development", alias="APP_ENV"
    )
    name: str = Field(default="trading-signal-platform", alias="APP_NAME")
    version: str = Field(default="0.1.0", alias="APP_VERSION")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", alias="APP_LOG_LEVEL"
    )
    debug: bool = Field(default=False, alias="DEBUG")

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow"
    )


class DbSettings(BaseSettings):
    """Database settings."""

    url: str = Field(..., alias="DATABASE_URL")
    echo: bool = Field(default=False)
    pool_size: int = Field(default=20, ge=1, le=100)
    max_overflow: int = Field(default=10, ge=0, le=50)
    pool_pre_ping: bool = Field(default=True)
    pool_recycle: int = Field(default=3600, ge=300)

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow"
    )

    @field_validator("url", mode="after")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        """Validate database URL format."""
        if not v:
            raise ValueError("DATABASE_URL cannot be empty")

        if not v.startswith(
            (
                "postgresql",
                "postgresql+psycopg",
                "postgresql+asyncpg",
                "sqlite",
                "sqlite+aiosqlite",
            )
        ):
            raise ValueError(
                f"Unsupported database URL: {v}. "
                "Supported: postgresql, postgresql+asyncpg, sqlite"
            )

        return v


class RedisSettings(BaseSettings):
    """Redis cache settings."""

    url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    enabled: bool = Field(default=True)

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow"
    )


class SecuritySettings(BaseSettings):
    """Security settings (JWT, hashing, etc.)."""

    jwt_secret_key: str = Field(default="change-me-in-production", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expiration_hours: int = Field(default=24, alias="JWT_EXPIRATION_HOURS", ge=1)

    argon2_time_cost: int = Field(default=2, alias="ARGON2_TIME_COST", ge=1)
    argon2_memory_cost: int = Field(default=65536, alias="ARGON2_MEMORY_COST", ge=1024)
    argon2_parallelism: int = Field(default=4, alias="ARGON2_PARALLELISM", ge=1)

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow"
    )

    @field_validator("jwt_secret_key", mode="after")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        """Validate JWT secret in production."""
        if os.getenv("APP_ENV") == "production":
            if v == "change-me-in-production" or len(v) < 32:
                raise ValueError(
                    "JWT_SECRET_KEY must be ≥32 characters in production"
                )
        return v


class TelemetrySettings(BaseSettings):
    """Observability and telemetry settings."""

    otel_enabled: bool = Field(default=False, alias="OTEL_ENABLED")
    otel_exporter_endpoint: str = Field(
        default="http://localhost:4318", alias="OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    prometheus_enabled: bool = Field(default=True, alias="PROMETHEUS_ENABLED")
    prometheus_port: int = Field(default=9090, alias="PROMETHEUS_PORT", ge=1, le=65535)

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow"
    )


class Settings(BaseSettings):
    """Main settings combining all config objects."""

    app: AppSettings = Field(default_factory=AppSettings)
    db: DbSettings = Field(default_factory=DbSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    telemetry: TelemetrySettings = Field(default_factory=TelemetrySettings)

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow"
    )


def get_settings() -> Settings:
    """Get global settings instance."""
    return Settings()


# Global instance
settings = get_settings()
