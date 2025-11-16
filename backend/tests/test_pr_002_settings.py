"""
PR-002: Central Config & Typed Settings Integration Tests

Tests for Pydantic v2 settings, environment loading, configuration
validation, and production safety checks.
"""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

# Import REAL Settings classes
from backend.app.core.settings import (
    AppSettings,
    DbSettings,
    RedisSettings,
    SecuritySettings,
    TelemetrySettings,
)


class TestSettingsLoading:
    """Test configuration loading from environment."""

    def test_app_settings_loads_from_env(self):
        """REAL TEST: Verify AppSettings loads from environment variables."""
        with patch.dict(
            os.environ,
            {
                "APP_ENV": "production",
                "APP_LOG_LEVEL": "ERROR",
                "APP_NAME": "test-app",
                "APP_VERSION": "1.0.0",
            },
            clear=False,
        ):
            settings = AppSettings()
            assert settings.env == "production"
            assert settings.log_level == "ERROR"
            assert settings.name == "test-app"
            assert settings.version == "1.0.0"

    def test_app_settings_uses_defaults_when_env_missing(self):
        """REAL TEST: Verify AppSettings provides defaults."""
        # Create a clean environment without APP_ prefixed vars
        with patch.dict(os.environ, {}, clear=True):
            settings = AppSettings()
            assert settings.env == "development"  # Default
            assert settings.log_level == "INFO"  # Default
            assert settings.name == "trading-signal-platform"  # Default
            assert settings.version == "0.1.0"  # Default

    def test_db_settings_validates_dsn_format(self):
        """REAL TEST: Verify DbSettings validates DSN format."""
        # Valid DSN should work
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://user:pass@localhost:5432/db"},
            clear=False,
        ):
            settings = DbSettings()
            assert settings.url.startswith("postgresql")
            assert "localhost" in settings.url

        # Invalid DSN should raise ValidationError
        with patch.dict(
            os.environ, {"DATABASE_URL": "mysql://localhost/db"}, clear=False
        ):
            with pytest.raises(ValidationError, match="Unsupported database URL"):
                DbSettings()

    def test_db_settings_rejects_empty_url(self):
        """REAL TEST: Verify DbSettings rejects empty DATABASE_URL."""
        with patch.dict(os.environ, {"DATABASE_URL": ""}, clear=False):
            with pytest.raises(ValidationError, match="DATABASE_URL cannot be empty"):
                DbSettings()


class TestEnvironmentLayering:
    """Test environment-specific configuration."""

    def test_app_settings_accepts_development_env(self):
        """REAL TEST: Verify AppSettings accepts 'development' env."""
        with patch.dict(os.environ, {"APP_ENV": "development"}, clear=False):
            settings = AppSettings()
            assert settings.env == "development"

    def test_app_settings_accepts_staging_env(self):
        """REAL TEST: Verify AppSettings accepts 'staging' env."""
        with patch.dict(os.environ, {"APP_ENV": "staging"}, clear=False):
            settings = AppSettings()
            assert settings.env == "staging"

    def test_app_settings_accepts_production_env(self):
        """REAL TEST: Verify AppSettings accepts 'production' env."""
        with patch.dict(os.environ, {"APP_ENV": "production"}, clear=False):
            settings = AppSettings()
            assert settings.env == "production"

    def test_app_settings_rejects_invalid_env(self):
        """REAL TEST: Verify AppSettings rejects invalid environment."""
        with patch.dict(os.environ, {"APP_ENV": "invalid_env"}, clear=False):
            with pytest.raises(ValidationError, match="Input should be 'development'"):
                AppSettings()


class TestProductionValidation:
    """Test production-specific safety checks."""

    def test_app_settings_accepts_version_in_production(self):
        """REAL TEST: Verify AppSettings accepts version in production."""
        with patch.dict(
            os.environ, {"APP_ENV": "production", "APP_VERSION": "1.2.3"}, clear=False
        ):
            settings = AppSettings()
            assert settings.env == "production"
            assert settings.version == "1.2.3"

    def test_app_settings_has_version_field(self):
        """REAL TEST: Verify AppSettings tracks version."""
        settings = AppSettings()
        assert hasattr(settings, "version")
        assert settings.version is not None
        assert len(settings.version) > 0

    def test_development_uses_default_version(self):
        """REAL TEST: Verify development allows default APP_VERSION."""
        # In test environment, conftest sets APP_VERSION to "0.1.0-test"
        # This test verifies that the version is correctly loaded from env
        with patch.dict(os.environ, {"APP_ENV": "development"}, clear=False):
            settings = AppSettings()
            assert settings.env == "development"
            # Version is set by conftest to "0.1.0-test" for testing
            assert settings.version.startswith(
                "0.1.0"
            ), f"Version should start with 0.1.0, got {settings.version}"

    def test_app_settings_rejects_invalid_log_level(self):
        """REAL TEST: Verify AppSettings rejects invalid log level."""
        with patch.dict(os.environ, {"APP_LOG_LEVEL": "INVALID_LEVEL"}, clear=False):
            with pytest.raises(ValidationError, match="Input should be 'DEBUG'"):
                AppSettings()


class TestDatabaseSettings:
    """Test database configuration."""

    def test_db_settings_loads_with_valid_url(self):
        """REAL TEST: Verify DbSettings loads with valid DATABASE_URL."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://user:pass@localhost:5432/testdb"},
            clear=False,
        ):
            settings = DbSettings()
            assert settings.url == "postgresql://user:pass@localhost:5432/testdb"
            assert settings.pool_size == 20  # Default
            assert settings.max_overflow == 10  # Default

    def test_db_settings_validates_pool_size_minimum(self):
        """REAL TEST: Verify DbSettings enforces pool_size >= 1."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/db", "POOL_SIZE": "0"},
            clear=False,
        ):
            with pytest.raises(ValidationError, match="greater than or equal to 1"):
                DbSettings()

    def test_db_settings_validates_max_overflow_non_negative(self):
        """REAL TEST: Verify DbSettings enforces max_overflow >= 0."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/db", "MAX_OVERFLOW": "-1"},
            clear=False,
        ):
            with pytest.raises(ValidationError, match="greater than or equal to 0"):
                DbSettings()

    def test_db_settings_accepts_custom_pool_settings(self):
        """REAL TEST: Verify DbSettings accepts custom pool configuration."""
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://localhost/db",
                "POOL_SIZE": "50",
                "MAX_OVERFLOW": "25",
            },
            clear=False,
        ):
            settings = DbSettings()
            assert settings.pool_size == 50
            assert settings.max_overflow == 25


class TestRedisSettings:
    """Test Redis configuration."""

    def test_redis_settings_loads_with_valid_url(self):
        """REAL TEST: Verify RedisSettings loads with valid REDIS_URL."""
        with patch.dict(
            os.environ, {"REDIS_URL": "redis://localhost:6379/0"}, clear=False
        ):
            settings = RedisSettings()
            assert settings.url == "redis://localhost:6379/0"

    def test_redis_settings_accepts_sentinel_url(self):
        """REAL TEST: Verify RedisSettings accepts sentinel URL."""
        with patch.dict(
            os.environ, {"REDIS_URL": "redis+sentinel://sentinel:26379"}, clear=False
        ):
            settings = RedisSettings()
            assert "sentinel" in settings.url


class TestSecuritySettings:
    """Test security configuration."""

    def test_security_settings_loads_with_defaults(self):
        """REAL TEST: Verify SecuritySettings loads with defaults."""
        with patch.dict(os.environ, {}, clear=True):
            settings = SecuritySettings()
            assert settings.jwt_algorithm == "HS256"
            assert settings.jwt_expiration_hours == 24
            assert settings.argon2_time_cost == 2

    def test_security_settings_accepts_custom_jwt_config(self):
        """REAL TEST: Verify SecuritySettings accepts custom JWT config."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": "my-super-secret-key-that-is-very-long-and-secure",
                "JWT_ALGORITHM": "HS512",
                "JWT_EXPIRATION_HOURS": "48",
            },
            clear=False,
        ):
            settings = SecuritySettings()
            assert (
                settings.jwt_secret_key
                == "my-super-secret-key-that-is-very-long-and-secure"
            )
            assert settings.jwt_algorithm == "HS512"
            assert settings.jwt_expiration_hours == 48

    def test_security_settings_validates_jwt_expiration_positive(self):
        """REAL TEST: Verify SecuritySettings enforces positive JWT expiration."""
        with patch.dict(os.environ, {"JWT_EXPIRATION_HOURS": "0"}, clear=False):
            with pytest.raises(ValidationError, match="greater than or equal to 1"):
                SecuritySettings()

    def test_security_settings_validates_argon2_parameters(self):
        """REAL TEST: Verify SecuritySettings enforces Argon2 parameter minimums."""
        with patch.dict(os.environ, {"ARGON2_TIME_COST": "0"}, clear=False):
            with pytest.raises(ValidationError, match="greater than or equal to 1"):
                SecuritySettings()


class TestTelemetrySettings:
    """Test observability configuration."""

    def test_telemetry_settings_loads_with_defaults(self):
        """REAL TEST: Verify TelemetrySettings loads with default values."""
        with patch.dict(os.environ, {}, clear=True):
            settings = TelemetrySettings()
            assert settings.otel_enabled is False
            assert settings.otel_exporter_endpoint == "http://localhost:4318"
            assert settings.prometheus_enabled is True
            assert settings.prometheus_port == 9090

    def test_telemetry_settings_accepts_custom_otel_endpoint(self):
        """REAL TEST: Verify TelemetrySettings accepts custom OpenTelemetry endpoint."""
        with patch.dict(
            os.environ,
            {
                "OTEL_ENABLED": "true",
                "OTEL_EXPORTER_OTLP_ENDPOINT": "http://otel-collector:4317",
            },
            clear=False,
        ):
            settings = TelemetrySettings()
            assert settings.otel_enabled is True
            assert settings.otel_exporter_endpoint == "http://otel-collector:4317"

    def test_telemetry_settings_validates_prometheus_port_range(self):
        """REAL TEST: Verify TelemetrySettings enforces valid Prometheus port range (1-65535)."""
        # Test invalid port below minimum
        with patch.dict(os.environ, {"PROMETHEUS_PORT": "0"}, clear=False):
            with pytest.raises(ValidationError, match="greater than or equal to 1"):
                TelemetrySettings()

        # Test invalid port above maximum
        with patch.dict(os.environ, {"PROMETHEUS_PORT": "70000"}, clear=False):
            with pytest.raises(ValidationError, match="less than or equal to 65535"):
                TelemetrySettings()


class TestSettingsPydanticIntegration:
    """Test Pydantic v2 integration."""

    def test_settings_use_pydantic_v2_basesettings(self):
        """REAL TEST: Verify settings classes inherit from Pydantic v2 BaseSettings."""
        from pydantic_settings import BaseSettings as PydanticBaseSettings

        # Verify all settings classes inherit from Pydantic v2 BaseSettings
        assert issubclass(AppSettings, PydanticBaseSettings)
        assert issubclass(DbSettings, PydanticBaseSettings)
        assert issubclass(SecuritySettings, PydanticBaseSettings)
        assert issubclass(TelemetrySettings, PydanticBaseSettings)

    def test_settings_have_model_config_dict(self):
        """REAL TEST: Verify settings use Pydantic v2 model_config (not v1 Config class)."""
        # Pydantic v2 uses model_config attribute instead of Config inner class
        assert hasattr(AppSettings, "model_config")
        assert hasattr(DbSettings, "model_config")
        assert hasattr(SecuritySettings, "model_config")

        # Verify model_config is a dict with expected keys (v2 style)
        assert isinstance(AppSettings.model_config, dict)
        assert "env_file" in AppSettings.model_config
        assert "env_file_encoding" in AppSettings.model_config
        assert AppSettings.model_config["env_file"] == ".env"

    def test_settings_field_validators_enforce_constraints(self):
        """REAL TEST: Verify settings field validators enforce business constraints."""
        # DbSettings has pool_size validator (must be >= 1)
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/db", "POOL_SIZE": "0"},
            clear=False,
        ):
            with pytest.raises(ValidationError, match="greater than or equal to 1"):
                DbSettings()

        # SecuritySettings has jwt_expiration_hours validator (must be >= 1)
        with patch.dict(os.environ, {"JWT_EXPIRATION_HOURS": "0"}, clear=False):
            with pytest.raises(ValidationError, match="greater than or equal to 1"):
                SecuritySettings()


class TestSettingsEnvFileLoading:
    """Test .env file loading."""

    def test_settings_model_config_specifies_env_file(self):
        """REAL TEST: Verify settings classes specify .env file in model_config."""
        # Pydantic v2 BaseSettings uses model_config to specify .env file
        assert hasattr(AppSettings, "model_config")
        assert AppSettings.model_config.get("env_file") == ".env"

        assert hasattr(DbSettings, "model_config")
        assert DbSettings.model_config.get("env_file") == ".env"

        assert hasattr(SecuritySettings, "model_config")
        assert SecuritySettings.model_config.get("env_file") == ".env"

    def test_settings_load_from_environment_variables(self):
        """REAL TEST: Verify settings prioritize environment variables over .env file."""
        # Environment variables should override .env file values
        with patch.dict(
            os.environ,
            {"APP_ENV": "production", "APP_NAME": "OverriddenName"},
            clear=False,
        ):
            settings = AppSettings()
            assert settings.env == "production"
            assert settings.name == "OverriddenName"

    def test_settings_env_file_encoding_utf8(self):
        """REAL TEST: Verify settings specify UTF-8 encoding for .env file."""
        # All settings should use UTF-8 encoding for .env files
        assert AppSettings.model_config.get("env_file_encoding") == "utf-8"
        assert DbSettings.model_config.get("env_file_encoding") == "utf-8"
        assert SecuritySettings.model_config.get("env_file_encoding") == "utf-8"


class TestSettingsDocumentation:
    """Test settings documentation and defaults."""

    def test_settings_classes_have_docstrings(self):
        """REAL TEST: Verify settings classes have documentation."""
        # All Settings classes should have docstrings explaining their purpose
        assert AppSettings.__doc__ is not None
        assert (
            "application" in AppSettings.__doc__.lower()
            or "app" in AppSettings.__doc__.lower()
        )

        assert DbSettings.__doc__ is not None
        assert (
            "database" in DbSettings.__doc__.lower()
            or "db" in DbSettings.__doc__.lower()
        )

        assert SecuritySettings.__doc__ is not None
        assert (
            "security" in SecuritySettings.__doc__.lower()
            or "auth" in SecuritySettings.__doc__.lower()
        )

    def test_settings_fields_have_defaults_or_required(self):
        """REAL TEST: Verify settings fields either have defaults or are explicitly required."""
        # Create settings with minimal environment to check defaults exist
        with patch.dict(os.environ, {}, clear=True):
            settings = AppSettings()
            # These should have defaults
            assert settings.env in ["development", "staging", "production"]
            assert settings.name is not None
            assert settings.version is not None
            assert settings.log_level in [
                "DEBUG",
                "INFO",
                "WARNING",
                "ERROR",
                "CRITICAL",
            ]

    def test_settings_case_insensitive_loading(self):
        """REAL TEST: Verify settings load environment variables case-insensitively."""
        # Pydantic BaseSettings should be case-insensitive by default
        with patch.dict(
            os.environ,
            {"app_env": "staging", "APP_NAME": "TestApp"},  # lowercase  # uppercase
            clear=False,
        ):
            settings = AppSettings()
            assert settings.env == "staging"
            assert settings.name == "TestApp"


class TestSettingsIntegration:
    """Integration tests for settings system."""

    def test_app_settings_instantiates_successfully_with_defaults(self):
        """REAL TEST: Verify AppSettings instantiates with all required defaults."""
        with patch.dict(os.environ, {}, clear=True):
            settings = AppSettings()
            assert settings.env in ["development", "staging", "production"]
            assert settings.name is not None
            assert settings.version is not None
            assert settings.log_level in [
                "DEBUG",
                "INFO",
                "WARNING",
                "ERROR",
                "CRITICAL",
            ]
            assert isinstance(settings.debug, bool)

    def test_db_settings_requires_database_url(self):
        """REAL TEST: Verify DbSettings fails early without DATABASE_URL."""
        with patch.dict(os.environ, {}, clear=True):
            # DbSettings should require DATABASE_URL (no default for production safety)
            with pytest.raises(ValidationError):
                DbSettings()

    def test_security_settings_requires_jwt_secret_in_production(self):
        """REAL TEST: Verify SecuritySettings enforces JWT_SECRET_KEY length in production."""
        # In production, JWT_SECRET_KEY must be >= 32 characters
        with patch.dict(
            os.environ,
            {"APP_ENV": "production", "JWT_SECRET_KEY": "short"},  # Too short!
            clear=False,
        ):
            with pytest.raises(
                ValidationError, match="JWT_SECRET_KEY must be ≥32 characters"
            ):
                SecuritySettings()

        # Valid production JWT secret (>=32 chars) should work
        with patch.dict(
            os.environ,
            {
                "APP_ENV": "production",
                "JWT_SECRET_KEY": "this-is-a-very-long-secure-jwt-secret-key-for-production-use",
            },
            clear=False,
        ):
            settings = SecuritySettings()
            assert (
                settings.jwt_secret_key
                == "this-is-a-very-long-secure-jwt-secret-key-for-production-use"
            )

    def test_all_settings_can_be_instantiated_together(self):
        """REAL TEST: Verify all Settings classes can coexist (no conflicts)."""
        with patch.dict(
            os.environ, {"DATABASE_URL": "postgresql://localhost/testdb"}, clear=False
        ):
            app_settings = AppSettings()
            db_settings = DbSettings()
            security_settings = SecuritySettings()
            telemetry_settings = TelemetrySettings()

            # All should instantiate without errors
            assert app_settings is not None
            assert db_settings is not None
            assert security_settings is not None
            assert telemetry_settings is not None
