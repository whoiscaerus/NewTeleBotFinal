import os
from typing import ClassVar, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Application settings."""

    env: Literal["development", "staging", "production", "test"] = Field(
        default="development", alias="APP_ENV"
    )
    name: str = Field(default="trading-signal-platform", alias="APP_NAME")
    version: str = Field(default="0.1.0", alias="APP_VERSION")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", alias="APP_LOG_LEVEL"
    )
    debug: bool = Field(default=False, alias="DEBUG")

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )


class DbSettings(BaseSettings):
    """Database settings."""

    url: str = Field(..., alias="DATABASE_URL")
    echo: bool = Field(default=False)
    pool_size: int = Field(default=20, ge=1, le=100)
    max_overflow: int = Field(default=10, ge=0, le=50)
    pool_pre_ping: bool = Field(default=True)
    pool_recycle: int = Field(default=3600, ge=300)

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    @field_validator("url", mode="before")
    @classmethod
    def validate_db_url_before(cls, v: str) -> str:
        """Validate database URL is not empty (before coercion)."""
        if not v or (isinstance(v, str) and v.strip() == ""):
            raise ValueError("DATABASE_URL cannot be empty")
        return v

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
    enabled: bool = Field(default=True, alias="REDIS_ENABLED")

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )


class SmtpSettings(BaseSettings):
    """SMTP email settings (PR-060)."""

    host: str = Field(default="smtp.gmail.com", alias="SMTP_HOST")
    port: int = Field(default=587, alias="SMTP_PORT")
    user: str = Field(default="", alias="SMTP_USER")
    password: str = Field(default="", alias="SMTP_PASSWORD")
    from_email: str = Field(default="noreply@example.com", alias="SMTP_FROM")
    use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )


class PushSettings(BaseSettings):
    """Push notification settings for PWA (PR-060)."""

    vapid_private_key: str = Field(default="", alias="PUSH_VAPID_PRIVATE_KEY")
    vapid_public_key: str = Field(default="", alias="PUSH_VAPID_PUBLIC_KEY")
    vapid_email: str = Field(default="admin@example.com", alias="PUSH_VAPID_EMAIL")

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )


class SecuritySettings(BaseSettings):
    """Security settings (JWT, hashing, etc.)."""

    jwt_secret_key: str = Field(
        default="change-me-in-production", alias="JWT_SECRET_KEY"
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expiration_hours: int = Field(default=24, alias="JWT_EXPIRATION_HOURS", ge=1)

    argon2_time_cost: int = Field(default=2, alias="ARGON2_TIME_COST", ge=1)
    argon2_memory_cost: int = Field(default=65536, alias="ARGON2_MEMORY_COST", ge=1024)
    argon2_parallelism: int = Field(default=4, alias="ARGON2_PARALLELISM", ge=1)

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    @field_validator("jwt_secret_key", mode="after")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        """Validate JWT secret in production."""
        if os.getenv("APP_ENV") == "production":
            if v == "change-me-in-production" or len(v) < 32:
                raise ValueError("JWT_SECRET_KEY must be ≥32 characters in production")
        return v


class PaymentSettings(BaseSettings):
    """Payment provider settings (Stripe, Telegram)."""

    stripe_secret_key: str = Field(default="", alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str = Field(default="", alias="STRIPE_WEBHOOK_SECRET")
    stripe_price_map: dict = Field(
        default={"premium_monthly": "price_1234"},
        alias="STRIPE_PRICE_MAP",
    )
    telegram_payment_provider_token: str = Field(
        default="", alias="TELEGRAM_PAYMENT_PROVIDER_TOKEN"
    )
    telegram_payment_plans: dict = Field(
        default={
            "premium_monthly": {
                "label": "Premium (Monthly)",
                "title": "Premium Subscription",
                "description": "Get access to advanced trading signals",
                "amount_cents": 2900,
                "duration_days": 30,
                "entitlement_type": "premium",
            }
        },
        alias="TELEGRAM_PAYMENT_PLANS",
    )

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )


class SignalsSettings(BaseSettings):
    """Signals API settings."""

    hmac_key: str = Field(default="change-me-in-production", alias="SIGNALS_HMAC_KEY")
    hmac_enabled: bool = Field(default=True, alias="SIGNALS_HMAC_ENABLED")
    dedup_window_seconds: int = Field(
        default=300, alias="SIGNALS_DEDUP_WINDOW_SECONDS", ge=10, le=3600
    )
    max_payload_bytes: int = Field(
        default=32768, alias="SIGNALS_MAX_PAYLOAD_BYTES", ge=1024, le=1048576
    )

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    @field_validator("hmac_key", mode="after")
    @classmethod
    def validate_hmac_key(cls, v: str) -> str:
        """Validate HMAC key in production."""
        if os.getenv("APP_ENV") == "production":
            if v == "change-me-in-production" or len(v) < 32:
                raise ValueError(
                    "SIGNALS_HMAC_KEY must be ≥32 characters in production"
                )
        return v


class TelegramSettings(BaseSettings):
    """Telegram bot settings."""

    bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    bot_username: str = Field(default="SampleBot", alias="TELEGRAM_BOT_USERNAME")

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )


class TelemetrySettings(BaseSettings):
    """Observability and telemetry settings."""

    otel_enabled: bool = Field(default=False, alias="OTEL_ENABLED")
    otel_exporter_endpoint: str = Field(
        default="http://localhost:4318", alias="OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    prometheus_enabled: bool = Field(default=True, alias="PROMETHEUS_ENABLED")
    prometheus_port: int = Field(default=9090, alias="PROMETHEUS_PORT", ge=1, le=65535)

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )


class MediaSettings(BaseSettings):
    """Media/charting settings."""

    media_dir: str = Field(default="media", alias="MEDIA_DIR")
    media_ttl_seconds: int = Field(default=86400, alias="MEDIA_TTL_SECONDS")
    media_max_bytes: int = Field(default=5000000, alias="MEDIA_MAX_BYTES")

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )


class GatewaySettings(BaseSettings):
    """Gateway migration settings (PR-083)."""

    flask_compatibility_mode: bool = Field(
        default=True, alias="FLASK_COMPATIBILITY_MODE"
    )
    telegram_user_id: str = Field(default="123456789", alias="TELEGRAM_USER_ID")
    trading_symbol: str = Field(default="XAUUSD", alias="TRADING_SYMBOL")
    exchange_rate: float = Field(default=1.27, alias="EXCHANGE_RATE")

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )


class Settings(BaseSettings):
    """Main settings combining all config objects.

    Pydantic v2 auto-instantiates nested BaseSettings from environment.
    No need for default values - they're created automatically.
    """

    app: AppSettings = Field(default_factory=AppSettings)
    db: DbSettings = Field(default_factory=DbSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    smtp: SmtpSettings = Field(default_factory=SmtpSettings)
    push: PushSettings = Field(default_factory=PushSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    payments: PaymentSettings = Field(default_factory=PaymentSettings)
    signals: SignalsSettings = Field(default_factory=SignalsSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    telemetry: TelemetrySettings = Field(default_factory=TelemetrySettings)
    media: MediaSettings = Field(default_factory=MediaSettings)
    gateway: GatewaySettings = Field(default_factory=GatewaySettings)

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    # Direct attribute access for backward compatibility
    @property
    def stripe_secret_key(self) -> str:
        return self.payments.stripe_secret_key

    @property
    def stripe_webhook_secret(self) -> str:
        return self.payments.stripe_webhook_secret

    @property
    def stripe_price_map(self) -> dict:
        return self.payments.stripe_price_map

    @property
    def telegram_payment_provider_token(self) -> str:
        return self.payments.telegram_payment_provider_token

    @property
    def telegram_payment_plans(self) -> dict:
        return self.payments.telegram_payment_plans

    @property
    def telegram_bot_token(self) -> str:
        return self.telegram.bot_token

    @property
    def telegram_bot_username(self) -> str:
        return self.telegram.bot_username

    @property
    def media_dir(self) -> str:
        return self.media.media_dir

    @property
    def media_ttl_seconds(self) -> int:
        return self.media.media_ttl_seconds

    @property
    def media_max_bytes(self) -> int:
        return self.media.media_max_bytes


def get_settings() -> Settings:
    """Get global settings instance.

    Pydantic BaseSettings auto-instantiates nested settings from environment.
    Mypy doesn't understand this pattern, hence the type ignore.
    """
    return Settings()


# Global instance
settings = get_settings()
