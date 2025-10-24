"""Tests for settings module."""

import pytest

from backend.app.core.settings import (
    AppSettings,
    DbSettings,
    RedisSettings,
    SecuritySettings,
    Settings,
    TelemetrySettings,
)


class TestAppSettings:
    """Test AppSettings configuration."""

    def test_defaults(self):
        """Test default values."""
        settings = AppSettings()
        assert settings.env == "development"
        assert settings.name == "trading-signal-platform"
        assert settings.version == "0.1.0"
        assert settings.log_level == "INFO"
        assert settings.debug is False

    def test_from_env(self, monkeypatch):
        """Test loading from environment variables."""
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("APP_LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("DEBUG", "true")

        settings = AppSettings()
        assert settings.env == "production"
        assert settings.log_level == "DEBUG"
        assert settings.debug is True


class TestDbSettings:
    """Test DbSettings configuration."""

    def test_postgresql_url_valid(self, monkeypatch):
        """Test PostgreSQL URL validation."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        settings = DbSettings()
        assert settings.url == "postgresql://user:pass@localhost:5432/db"

    def test_postgresql_asyncpg_url_valid(self, monkeypatch):
        """Test PostgreSQL asyncpg URL validation."""
        monkeypatch.setenv(
            "DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db"
        )
        settings = DbSettings()
        assert settings.url == "postgresql+asyncpg://user:pass@localhost:5432/db"

    def test_sqlite_url_valid(self, monkeypatch):
        """Test SQLite URL validation."""
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
        settings = DbSettings()
        assert settings.url == "sqlite+aiosqlite:///:memory:"

    def test_invalid_url_raises_error(self, monkeypatch):
        """Test invalid database URL raises error."""
        monkeypatch.setenv("DATABASE_URL", "mysql://localhost/db")
        with pytest.raises(ValueError, match="Unsupported database URL"):
            DbSettings()

    def test_empty_url_raises_error(self, monkeypatch):
        """Test empty database URL raises error."""
        monkeypatch.setenv("DATABASE_URL", "")
        with pytest.raises(ValueError, match="cannot be empty"):
            DbSettings()

    def test_pool_constraints(self):
        """Test pool size constraints."""
        # Valid
        settings = DbSettings(
            url="sqlite+aiosqlite:///:memory:",
            pool_size=50,
            max_overflow=25,
        )
        assert settings.pool_size == 50
        assert settings.max_overflow == 25

        # Invalid pool_size
        with pytest.raises(ValueError):
            DbSettings(url="sqlite+aiosqlite:///:memory:", pool_size=0)

        with pytest.raises(ValueError):
            DbSettings(url="sqlite+aiosqlite:///:memory:", pool_size=101)

    def test_from_env(self, monkeypatch):
        """Test loading from environment variables."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
        settings = DbSettings()
        assert settings.url == "postgresql://user:pass@localhost/db"


class TestRedisSettings:
    """Test RedisSettings configuration."""

    def test_defaults(self):
        """Test default values."""
        settings = RedisSettings()
        assert settings.url == "redis://localhost:6379/0"
        assert settings.enabled is True

    def test_from_env(self, monkeypatch):
        """Test loading from environment variables."""
        monkeypatch.setenv("REDIS_URL", "redis://cache:6379/1")
        settings = RedisSettings()
        assert settings.url == "redis://cache:6379/1"


class TestSecuritySettings:
    """Test SecuritySettings configuration."""

    def test_defaults(self):
        """Test default values."""
        settings = SecuritySettings()
        assert settings.jwt_algorithm == "HS256"
        assert settings.jwt_expiration_hours == 24
        assert settings.argon2_time_cost == 2

    def test_jwt_expiration_constraint(self):
        """Test JWT expiration must be >= 1."""
        with pytest.raises(ValueError):
            SecuritySettings(**{"JWT_EXPIRATION_HOURS": 0})

    def test_jwt_secret_production_validation(self, monkeypatch):
        """Test JWT secret validation in production."""
        monkeypatch.setenv("APP_ENV", "production")

        # Should fail with default secret
        with pytest.raises(ValueError, match="must be ≥32 characters"):
            SecuritySettings(**{"JWT_SECRET_KEY": "change-me-in-production"})

        # Should succeed with long secret
        settings = SecuritySettings(**{"JWT_SECRET_KEY": "a" * 32})
        assert len(settings.jwt_secret_key) == 32

    def test_from_env(self, monkeypatch):
        """Test loading from environment variables."""
        monkeypatch.setenv("JWT_ALGORITHM", "HS512")
        monkeypatch.setenv("JWT_EXPIRATION_HOURS", "48")
        settings = SecuritySettings(jwt_secret_key="test-secret-key")
        assert settings.jwt_algorithm == "HS512"
        assert settings.jwt_expiration_hours == 48


class TestTelemetrySettings:
    """Test TelemetrySettings configuration."""

    def test_defaults(self):
        """Test default values."""
        settings = TelemetrySettings()
        assert settings.otel_enabled is False
        assert settings.prometheus_enabled is True
        assert settings.prometheus_port == 9090

    def test_prometheus_port_constraint(self):
        """Test Prometheus port constraint."""
        with pytest.raises(ValueError):
            TelemetrySettings(**{"PROMETHEUS_PORT": 0})

        with pytest.raises(ValueError):
            TelemetrySettings(**{"PROMETHEUS_PORT": 65536})

        settings = TelemetrySettings(**{"PROMETHEUS_PORT": 9091})
        assert settings.prometheus_port == 9091


class TestMainSettings:
    """Test main Settings class."""

    def test_nested_settings(self):
        """Test nested settings objects."""
        settings = Settings()
        assert isinstance(settings.app, AppSettings)
        assert isinstance(settings.db, DbSettings)
        assert isinstance(settings.redis, RedisSettings)
        assert isinstance(settings.security, SecuritySettings)
        assert isinstance(settings.telemetry, TelemetrySettings)

    def test_all_subconfigs_initialized(self):
        """Test all sub-configurations are properly initialized."""
        settings = Settings()
        assert settings.app.name == "trading-signal-platform"
        assert settings.redis.enabled is True
        assert settings.security.jwt_algorithm == "HS256"
        assert settings.telemetry.prometheus_enabled is True
