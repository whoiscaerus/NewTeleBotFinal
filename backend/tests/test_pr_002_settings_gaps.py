"""
PR-002 Settings - Comprehensive Business Logic Gap Tests

This test file covers 9 critical gaps in settings business logic validation:
1. JWT secret production validation (incomplete)
2. HMAC secret production validation (missing)
3. Database URL validator - all DB types
4. Pool configuration boundary values
5. Environment variable priority order
6. Type coercion (string→int, string→bool)
7. Case-insensitive environment loading
8. All literal value combinations
9. Backward compatibility properties

Total: 49 new tests for 90-100% business logic coverage
"""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from backend.app.core.settings import (
    AppSettings,
    DbSettings,
    RedisSettings,
    SecuritySettings,
    Settings,
    SignalsSettings,
    TelemetrySettings,
)


# ============================================================================
# GAP 1: JWT Secret Production Validation
# ============================================================================
class TestJwtSecretProductionValidation:
    """Test JWT secret validation in production mode."""

    def test_production_jwt_secret_too_short(self):
        """JWT secret must be ≥32 chars in production."""
        with patch.dict(
            os.environ,
            {"APP_ENV": "production", "JWT_SECRET_KEY": "short"},
            clear=False,
        ):
            with pytest.raises(ValidationError, match="must be ≥32 characters"):
                SecuritySettings()

    def test_production_jwt_secret_rejects_default(self):
        """JWT secret must not be default in production."""
        with patch.dict(
            os.environ,
            {
                "APP_ENV": "production",
                "JWT_SECRET_KEY": "change-me-in-production",
            },
            clear=False,
        ):
            with pytest.raises(ValidationError, match="must be ≥32 characters"):
                SecuritySettings()

    def test_production_jwt_secret_accepts_valid_32_chars(self):
        """JWT secret with 32 chars accepted in production."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {"APP_ENV": "production", "JWT_SECRET_KEY": valid_key},
            clear=False,
        ):
            settings = SecuritySettings()
            assert settings.jwt_secret_key == valid_key

    def test_production_jwt_secret_accepts_longer_than_32(self):
        """JWT secret with >32 chars accepted in production."""
        valid_key = "a" * 64
        with patch.dict(
            os.environ,
            {"APP_ENV": "production", "JWT_SECRET_KEY": valid_key},
            clear=False,
        ):
            settings = SecuritySettings()
            assert settings.jwt_secret_key == valid_key

    def test_dev_jwt_secret_allows_short(self):
        """JWT secret can be short in development."""
        with patch.dict(
            os.environ,
            {"APP_ENV": "development", "JWT_SECRET_KEY": "short"},
            clear=False,
        ):
            settings = SecuritySettings()
            assert settings.jwt_secret_key == "short"

    def test_dev_jwt_secret_allows_default(self):
        """JWT secret can use default in development."""
        with patch.dict(
            os.environ,
            {"APP_ENV": "development", "JWT_SECRET_KEY": "change-me-in-production"},
            clear=False,
        ):
            settings = SecuritySettings()
            assert settings.jwt_secret_key == "change-me-in-production"

    def test_staging_jwt_secret_allows_short(self):
        """JWT secret can be short in staging."""
        with patch.dict(
            os.environ,
            {"APP_ENV": "staging", "JWT_SECRET_KEY": "short"},
            clear=False,
        ):
            settings = SecuritySettings()
            assert settings.jwt_secret_key == "short"


# ============================================================================
# GAP 2: HMAC Secret Production Validation
# ============================================================================
class TestHmacSecretProductionValidation:
    """Test HMAC secret validation in production mode."""

    def test_production_hmac_key_too_short(self):
        """HMAC key must be ≥32 chars in production."""
        with patch.dict(
            os.environ,
            {"APP_ENV": "production", "SIGNALS_HMAC_KEY": "short"},
            clear=False,
        ):
            with pytest.raises(ValidationError, match="must be ≥32 characters"):
                SignalsSettings()

    def test_production_hmac_key_rejects_default(self):
        """HMAC key must not be default in production."""
        with patch.dict(
            os.environ,
            {
                "APP_ENV": "production",
                "SIGNALS_HMAC_KEY": "change-me-in-production",
            },
            clear=False,
        ):
            with pytest.raises(ValidationError, match="must be ≥32 characters"):
                SignalsSettings()

    def test_production_hmac_key_accepts_valid_32_chars(self):
        """HMAC key with 32 chars accepted in production."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {"APP_ENV": "production", "SIGNALS_HMAC_KEY": valid_key},
            clear=False,
        ):
            settings = SignalsSettings()
            assert settings.hmac_key == valid_key

    def test_production_hmac_key_accepts_longer_than_32(self):
        """HMAC key with >32 chars accepted in production."""
        valid_key = "a" * 64
        with patch.dict(
            os.environ,
            {"APP_ENV": "production", "SIGNALS_HMAC_KEY": valid_key},
            clear=False,
        ):
            settings = SignalsSettings()
            assert settings.hmac_key == valid_key

    def test_dev_hmac_key_allows_short(self):
        """HMAC key can be short in development."""
        with patch.dict(
            os.environ,
            {"APP_ENV": "development", "SIGNALS_HMAC_KEY": "short"},
            clear=False,
        ):
            settings = SignalsSettings()
            assert settings.hmac_key == "short"

    def test_dev_hmac_key_allows_default(self):
        """HMAC key can use default in development."""
        with patch.dict(
            os.environ,
            {
                "APP_ENV": "development",
                "SIGNALS_HMAC_KEY": "change-me-in-production",
            },
            clear=False,
        ):
            settings = SignalsSettings()
            assert settings.hmac_key == "change-me-in-production"


# ============================================================================
# GAP 3: Database URL Validator - All DB Types
# ============================================================================
class TestDatabaseUrlAllTypes:
    """Test database URL validator accepts all supported database types."""

    def test_postgresql_url_accepted(self):
        """Standard PostgreSQL URL accepted."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://user:pass@localhost/db"},
            clear=False,
        ):
            settings = DbSettings()
            assert settings.url == "postgresql://user:pass@localhost/db"

    def test_postgresql_psycopg_url_accepted(self):
        """PostgreSQL with psycopg driver accepted."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql+psycopg://user:pass@localhost/db"},
            clear=False,
        ):
            settings = DbSettings()
            assert settings.url == "postgresql+psycopg://user:pass@localhost/db"

    def test_postgresql_asyncpg_url_accepted(self):
        """PostgreSQL with asyncpg driver accepted."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db"},
            clear=False,
        ):
            settings = DbSettings()
            assert settings.url == "postgresql+asyncpg://user:pass@localhost/db"

    def test_sqlite_url_accepted(self):
        """SQLite URL accepted."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "sqlite:///path/to/db.sqlite"},
            clear=False,
        ):
            settings = DbSettings()
            assert settings.url == "sqlite:///path/to/db.sqlite"

    def test_sqlite_aiosqlite_url_accepted(self):
        """SQLite with aiosqlite driver accepted."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "sqlite+aiosqlite:///path/to/db.sqlite"},
            clear=False,
        ):
            settings = DbSettings()
            assert settings.url == "sqlite+aiosqlite:///path/to/db.sqlite"

    def test_mysql_url_rejected(self):
        """MySQL URL rejected (unsupported)."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "mysql://user:pass@localhost/db"},
            clear=False,
        ):
            with pytest.raises(ValidationError, match="Unsupported database URL"):
                DbSettings()

    def test_oracle_url_rejected(self):
        """Oracle URL rejected (unsupported)."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "oracle://user:pass@localhost/db"},
            clear=False,
        ):
            with pytest.raises(ValidationError, match="Unsupported database URL"):
                DbSettings()

    def test_mongodb_url_rejected(self):
        """MongoDB URL rejected (unsupported)."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "mongodb://user:pass@localhost/db"},
            clear=False,
        ):
            with pytest.raises(ValidationError, match="Unsupported database URL"):
                DbSettings()

    def test_mssql_url_rejected(self):
        """MSSQL URL rejected (unsupported)."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "mssql+pymssql://user:pass@localhost/db"},
            clear=False,
        ):
            with pytest.raises(ValidationError, match="Unsupported database URL"):
                DbSettings()


# ============================================================================
# GAP 4: Pool Configuration Boundary Values
# ============================================================================
class TestPoolConfigurationBoundaries:
    """Test pool configuration respects min/max boundaries."""

    # pool_size boundaries [1, 100]
    def test_pool_size_minimum_boundary(self):
        """pool_size can be exactly 1 (minimum)."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/db", "POOL_SIZE": "1"},
            clear=False,
        ):
            settings = DbSettings()
            assert settings.pool_size == 1

    def test_pool_size_maximum_boundary(self):
        """pool_size can be exactly 100 (maximum)."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/db", "POOL_SIZE": "100"},
            clear=False,
        ):
            settings = DbSettings()
            assert settings.pool_size == 100

    def test_pool_size_below_minimum(self):
        """pool_size < 1 rejected."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/db", "POOL_SIZE": "0"},
            clear=False,
        ):
            with pytest.raises(ValidationError, match="greater than or equal to 1"):
                DbSettings()

    def test_pool_size_above_maximum(self):
        """pool_size > 100 rejected."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/db", "POOL_SIZE": "101"},
            clear=False,
        ):
            with pytest.raises(ValidationError, match="less than or equal to 100"):
                DbSettings()

    # max_overflow boundaries [0, 50]
    def test_max_overflow_minimum_boundary(self):
        """max_overflow can be exactly 0 (minimum)."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/db", "MAX_OVERFLOW": "0"},
            clear=False,
        ):
            settings = DbSettings()
            assert settings.max_overflow == 0

    def test_max_overflow_maximum_boundary(self):
        """max_overflow can be exactly 50 (maximum)."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/db", "MAX_OVERFLOW": "50"},
            clear=False,
        ):
            settings = DbSettings()
            assert settings.max_overflow == 50

    def test_max_overflow_below_minimum(self):
        """max_overflow < 0 rejected."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/db", "MAX_OVERFLOW": "-1"},
            clear=False,
        ):
            with pytest.raises(ValidationError, match="greater than or equal to 0"):
                DbSettings()

    def test_max_overflow_above_maximum(self):
        """max_overflow > 50 rejected."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/db", "MAX_OVERFLOW": "51"},
            clear=False,
        ):
            with pytest.raises(ValidationError, match="less than or equal to 50"):
                DbSettings()

    # pool_recycle boundaries [≥300]
    def test_pool_recycle_minimum_boundary(self):
        """pool_recycle can be exactly 300 (minimum)."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/db", "POOL_RECYCLE": "300"},
            clear=False,
        ):
            settings = DbSettings()
            assert settings.pool_recycle == 300

    def test_pool_recycle_above_minimum(self):
        """pool_recycle > 300 accepted."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/db", "POOL_RECYCLE": "3600"},
            clear=False,
        ):
            settings = DbSettings()
            assert settings.pool_recycle == 3600

    def test_pool_recycle_below_minimum(self):
        """pool_recycle < 300 rejected."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/db", "POOL_RECYCLE": "299"},
            clear=False,
        ):
            with pytest.raises(ValidationError, match="greater than or equal to 300"):
                DbSettings()


# ============================================================================
# GAP 5: Environment Variable Priority Order
# ============================================================================
class TestEnvVariablePriorityOrder:
    """Test environment variables override defaults."""

    def test_env_overrides_default_app_env(self):
        """Environment variable overrides default env."""
        with patch.dict(os.environ, {"APP_ENV": "production"}, clear=False):
            settings = AppSettings()
            assert settings.env == "production"

    def test_env_overrides_default_log_level(self):
        """Environment variable overrides default log_level."""
        with patch.dict(os.environ, {"APP_LOG_LEVEL": "DEBUG"}, clear=False):
            settings = AppSettings()
            assert settings.log_level == "DEBUG"

    def test_env_overrides_default_jwt_expiration(self):
        """Environment variable overrides default jwt_expiration_hours."""
        with patch.dict(os.environ, {"JWT_EXPIRATION_HOURS": "48"}, clear=False):
            settings = SecuritySettings()
            assert settings.jwt_expiration_hours == 48

    def test_env_overrides_default_pool_size(self):
        """Environment variable overrides default pool_size."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/db", "POOL_SIZE": "50"},
            clear=False,
        ):
            settings = DbSettings()
            assert settings.pool_size == 50

    def test_multiple_env_overrides(self):
        """Multiple environment variables override multiple defaults."""
        with patch.dict(
            os.environ,
            {
                "APP_ENV": "staging",
                "APP_LOG_LEVEL": "WARNING",
                "DATABASE_URL": "postgresql://localhost/db",
                "POOL_SIZE": "30",
            },
            clear=False,
        ):
            app_settings = AppSettings()
            db_settings = DbSettings()

            assert app_settings.env == "staging"
            assert app_settings.log_level == "WARNING"
            assert db_settings.pool_size == 30


# ============================================================================
# GAP 6: Type Coercion (String → int, bool)
# ============================================================================
class TestTypeCoercion:
    """Test Pydantic type coercion from environment variables."""

    # String to int coercion
    def test_pool_size_string_to_int_coercion(self):
        """Environment string POOL_SIZE coerced to int."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/db", "POOL_SIZE": "25"},
            clear=False,
        ):
            settings = DbSettings()
            assert settings.pool_size == 25
            assert isinstance(settings.pool_size, int)

    def test_jwt_expiration_string_to_int_coercion(self):
        """Environment string JWT_EXPIRATION_HOURS coerced to int."""
        with patch.dict(os.environ, {"JWT_EXPIRATION_HOURS": "48"}, clear=False):
            settings = SecuritySettings()
            assert settings.jwt_expiration_hours == 48
            assert isinstance(settings.jwt_expiration_hours, int)

    def test_prometheus_port_string_to_int_coercion(self):
        """Environment string PROMETHEUS_PORT coerced to int."""
        with patch.dict(os.environ, {"PROMETHEUS_PORT": "8888"}, clear=False):
            settings = TelemetrySettings()
            assert settings.prometheus_port == 8888
            assert isinstance(settings.prometheus_port, int)

    def test_dedup_window_string_to_int_coercion(self):
        """Environment string SIGNALS_DEDUP_WINDOW_SECONDS coerced to int."""
        with patch.dict(
            os.environ, {"SIGNALS_DEDUP_WINDOW_SECONDS": "600"}, clear=False
        ):
            settings = SignalsSettings()
            assert settings.dedup_window_seconds == 600
            assert isinstance(settings.dedup_window_seconds, int)

    def test_max_payload_string_to_int_coercion(self):
        """Environment string SIGNALS_MAX_PAYLOAD_BYTES coerced to int."""
        with patch.dict(
            os.environ, {"SIGNALS_MAX_PAYLOAD_BYTES": "65536"}, clear=False
        ):
            settings = SignalsSettings()
            assert settings.max_payload_bytes == 65536
            assert isinstance(settings.max_payload_bytes, int)

    # String to bool coercion
    def test_redis_enabled_true_string_to_bool_coercion(self):
        """Environment string REDIS_ENABLED='true' coerced to bool."""
        with patch.dict(os.environ, {"REDIS_ENABLED": "true"}, clear=False):
            settings = RedisSettings()
            assert settings.enabled is True
            assert isinstance(settings.enabled, bool)

    def test_redis_enabled_false_string_to_bool_coercion(self):
        """Environment string REDIS_ENABLED='false' coerced to bool."""
        with patch.dict(os.environ, {"REDIS_ENABLED": "false"}, clear=False):
            settings = RedisSettings()
            assert settings.enabled is False
            assert isinstance(settings.enabled, bool)

    def test_hmac_enabled_false_string_to_bool_coercion(self):
        """Environment string SIGNALS_HMAC_ENABLED='false' coerced to bool."""
        with patch.dict(os.environ, {"SIGNALS_HMAC_ENABLED": "false"}, clear=False):
            settings = SignalsSettings()
            assert settings.hmac_enabled is False
            assert isinstance(settings.hmac_enabled, bool)

    def test_otel_enabled_true_string_to_bool_coercion(self):
        """Environment string OTEL_ENABLED='true' coerced to bool."""
        with patch.dict(os.environ, {"OTEL_ENABLED": "true"}, clear=False):
            settings = TelemetrySettings()
            assert settings.otel_enabled is True
            assert isinstance(settings.otel_enabled, bool)

    # Invalid type coercion should fail
    def test_invalid_pool_size_string_coercion_fails(self):
        """Invalid int string POOL_SIZE='abc' rejected."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/db", "POOL_SIZE": "not-a-number"},
            clear=False,
        ):
            with pytest.raises(ValidationError):
                DbSettings()

    def test_invalid_jwt_expiration_string_coercion_fails(self):
        """Invalid int string JWT_EXPIRATION_HOURS='abc' rejected."""
        with patch.dict(
            os.environ, {"JWT_EXPIRATION_HOURS": "not-a-number"}, clear=False
        ):
            with pytest.raises(ValidationError):
                SecuritySettings()


# ============================================================================
# GAP 7: Case-Insensitive Environment Loading
# ============================================================================
class TestCaseInsensitiveEnvLoading:
    """Test case_sensitive=False works for all case variations."""

    # AppSettings cases
    def test_app_env_lowercase(self):
        """app_env loads environment (lowercase)."""
        with patch.dict(os.environ, {"app_env": "production"}, clear=False):
            settings = AppSettings()
            assert settings.env == "production"

    def test_app_env_uppercase(self):
        """APP_ENV loads environment (uppercase)."""
        with patch.dict(os.environ, {"APP_ENV": "production"}, clear=False):
            settings = AppSettings()
            assert settings.env == "production"

    def test_app_env_mixedcase(self):
        """App_Env loads environment (mixed case)."""
        with patch.dict(os.environ, {"App_Env": "production"}, clear=False):
            settings = AppSettings()
            assert settings.env == "production"

    def test_app_log_level_lowercase(self):
        """app_log_level loads log level (lowercase)."""
        with patch.dict(os.environ, {"app_log_level": "DEBUG"}, clear=False):
            settings = AppSettings()
            assert settings.log_level == "DEBUG"

    # DbSettings cases
    def test_database_url_lowercase(self):
        """database_url loads URL (lowercase)."""
        with patch.dict(
            os.environ, {"database_url": "postgresql://localhost/db"}, clear=False
        ):
            settings = DbSettings()
            assert settings.url.startswith("postgresql")

    def test_database_url_uppercase(self):
        """DATABASE_URL loads URL (uppercase)."""
        with patch.dict(
            os.environ, {"DATABASE_URL": "postgresql://localhost/db"}, clear=False
        ):
            settings = DbSettings()
            assert settings.url.startswith("postgresql")

    def test_database_url_mixedcase(self):
        """Database_Url loads URL (mixed case)."""
        with patch.dict(
            os.environ, {"Database_Url": "postgresql://localhost/db"}, clear=False
        ):
            settings = DbSettings()
            assert settings.url.startswith("postgresql")

    # Other settings cases
    def test_redis_url_lowercase(self):
        """redis_url loads (lowercase)."""
        with patch.dict(
            os.environ,
            {"redis_url": "redis://custom:6380/0"},
            clear=False,
        ):
            settings = RedisSettings()
            assert settings.url == "redis://custom:6380/0"

    def test_jwt_secret_key_lowercase(self):
        """jwt_secret_key loads (lowercase)."""
        with patch.dict(os.environ, {"jwt_secret_key": "test_secret"}, clear=False):
            settings = SecuritySettings()
            assert settings.jwt_secret_key == "test_secret"


# ============================================================================
# GAP 8: All Literal Value Combinations
# ============================================================================
class TestAllLiteralValues:
    """Test all valid/invalid literal value combinations."""

    # AppSettings.env literal [development, staging, production]
    def test_env_development_valid(self):
        """env='development' accepted."""
        with patch.dict(os.environ, {"APP_ENV": "development"}, clear=False):
            settings = AppSettings()
            assert settings.env == "development"

    def test_env_staging_valid(self):
        """env='staging' accepted."""
        with patch.dict(os.environ, {"APP_ENV": "staging"}, clear=False):
            settings = AppSettings()
            assert settings.env == "staging"

    def test_env_production_valid(self):
        """env='production' accepted."""
        with patch.dict(os.environ, {"APP_ENV": "production"}, clear=False):
            settings = AppSettings()
            assert settings.env == "production"

    def test_env_invalid_typo(self):
        """env='producton' (typo) rejected."""
        with patch.dict(os.environ, {"APP_ENV": "producton"}, clear=False):
            with pytest.raises(ValidationError):
                AppSettings()

    def test_env_invalid_staging_lowercase(self):
        """env='Staging' (wrong case) rejected."""
        with patch.dict(os.environ, {"APP_ENV": "Staging"}, clear=False):
            with pytest.raises(ValidationError):
                AppSettings()

    # AppSettings.log_level literal [DEBUG, INFO, WARNING, ERROR, CRITICAL]
    def test_log_level_debug_valid(self):
        """log_level='DEBUG' accepted."""
        with patch.dict(os.environ, {"APP_LOG_LEVEL": "DEBUG"}, clear=False):
            settings = AppSettings()
            assert settings.log_level == "DEBUG"

    def test_log_level_info_valid(self):
        """log_level='INFO' accepted."""
        with patch.dict(os.environ, {"APP_LOG_LEVEL": "INFO"}, clear=False):
            settings = AppSettings()
            assert settings.log_level == "INFO"

    def test_log_level_warning_valid(self):
        """log_level='WARNING' accepted."""
        with patch.dict(os.environ, {"APP_LOG_LEVEL": "WARNING"}, clear=False):
            settings = AppSettings()
            assert settings.log_level == "WARNING"

    def test_log_level_error_valid(self):
        """log_level='ERROR' accepted."""
        with patch.dict(os.environ, {"APP_LOG_LEVEL": "ERROR"}, clear=False):
            settings = AppSettings()
            assert settings.log_level == "ERROR"

    def test_log_level_critical_valid(self):
        """log_level='CRITICAL' accepted."""
        with patch.dict(os.environ, {"APP_LOG_LEVEL": "CRITICAL"}, clear=False):
            settings = AppSettings()
            assert settings.log_level == "CRITICAL"

    def test_log_level_invalid_lowercase(self):
        """log_level='debug' (lowercase) rejected."""
        with patch.dict(os.environ, {"APP_LOG_LEVEL": "debug"}, clear=False):
            with pytest.raises(ValidationError):
                AppSettings()

    def test_log_level_invalid_value(self):
        """log_level='TRACE' (invalid) rejected."""
        with patch.dict(os.environ, {"APP_LOG_LEVEL": "TRACE"}, clear=False):
            with pytest.raises(ValidationError):
                AppSettings()

    # SignalsSettings.dedup_window_seconds [10, 3600]
    def test_dedup_window_minimum_valid(self):
        """dedup_window_seconds=10 (minimum) accepted."""
        with patch.dict(
            os.environ,
            {"SIGNALS_DEDUP_WINDOW_SECONDS": "10"},
            clear=False,
        ):
            settings = SignalsSettings()
            assert settings.dedup_window_seconds == 10

    def test_dedup_window_maximum_valid(self):
        """dedup_window_seconds=3600 (maximum) accepted."""
        with patch.dict(
            os.environ,
            {"SIGNALS_DEDUP_WINDOW_SECONDS": "3600"},
            clear=False,
        ):
            settings = SignalsSettings()
            assert settings.dedup_window_seconds == 3600

    def test_dedup_window_mid_range_valid(self):
        """dedup_window_seconds=300 (mid-range) accepted."""
        with patch.dict(
            os.environ,
            {"SIGNALS_DEDUP_WINDOW_SECONDS": "300"},
            clear=False,
        ):
            settings = SignalsSettings()
            assert settings.dedup_window_seconds == 300

    def test_dedup_window_below_minimum(self):
        """dedup_window_seconds=9 (below min) rejected."""
        with patch.dict(
            os.environ,
            {"SIGNALS_DEDUP_WINDOW_SECONDS": "9"},
            clear=False,
        ):
            with pytest.raises(ValidationError, match="greater than or equal to 10"):
                SignalsSettings()

    def test_dedup_window_above_maximum(self):
        """dedup_window_seconds=3601 (above max) rejected."""
        with patch.dict(
            os.environ,
            {"SIGNALS_DEDUP_WINDOW_SECONDS": "3601"},
            clear=False,
        ):
            with pytest.raises(ValidationError, match="less than or equal to 3600"):
                SignalsSettings()

    # SignalsSettings.max_payload_bytes [1024, 1048576]
    def test_payload_minimum_valid(self):
        """max_payload_bytes=1024 (minimum) accepted."""
        with patch.dict(
            os.environ,
            {"SIGNALS_MAX_PAYLOAD_BYTES": "1024"},
            clear=False,
        ):
            settings = SignalsSettings()
            assert settings.max_payload_bytes == 1024

    def test_payload_maximum_valid(self):
        """max_payload_bytes=1048576 (maximum) accepted."""
        with patch.dict(
            os.environ,
            {"SIGNALS_MAX_PAYLOAD_BYTES": "1048576"},
            clear=False,
        ):
            settings = SignalsSettings()
            assert settings.max_payload_bytes == 1048576

    def test_payload_mid_range_valid(self):
        """max_payload_bytes=32768 (mid-range) accepted."""
        with patch.dict(
            os.environ,
            {"SIGNALS_MAX_PAYLOAD_BYTES": "32768"},
            clear=False,
        ):
            settings = SignalsSettings()
            assert settings.max_payload_bytes == 32768

    def test_payload_below_minimum(self):
        """max_payload_bytes=1023 (below min) rejected."""
        with patch.dict(
            os.environ,
            {"SIGNALS_MAX_PAYLOAD_BYTES": "1023"},
            clear=False,
        ):
            with pytest.raises(ValidationError, match="greater than or equal to 1024"):
                SignalsSettings()

    def test_payload_above_maximum(self):
        """max_payload_bytes=1048577 (above max) rejected."""
        with patch.dict(
            os.environ,
            {"SIGNALS_MAX_PAYLOAD_BYTES": "1048577"},
            clear=False,
        ):
            with pytest.raises(ValidationError, match="less than or equal to 1048576"):
                SignalsSettings()


# ============================================================================
# GAP 9: Backward Compatibility Properties
# ============================================================================
class TestBackwardCompatibilityProperties:
    """Test backward compatibility properties on Settings class."""

    def test_backward_compat_stripe_secret_key(self):
        """settings.stripe_secret_key property works."""
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://localhost/db",
                "STRIPE_SECRET_KEY": "sk_test_123",
            },
            clear=False,
        ):
            settings = Settings()
            # Old way: via property
            assert settings.stripe_secret_key == "sk_test_123"
            # New way: direct
            assert settings.payments.stripe_secret_key == "sk_test_123"

    def test_backward_compat_stripe_webhook_secret(self):
        """settings.stripe_webhook_secret property works."""
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://localhost/db",
                "STRIPE_WEBHOOK_SECRET": "whsec_test_123",
            },
            clear=False,
        ):
            settings = Settings()
            assert settings.stripe_webhook_secret == "whsec_test_123"
            assert settings.payments.stripe_webhook_secret == "whsec_test_123"

    def test_backward_compat_stripe_price_map(self):
        """settings.stripe_price_map property works."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/db"},
            clear=False,
        ):
            settings = Settings()
            # Should have default price map
            assert "premium_monthly" in settings.stripe_price_map
            assert settings.stripe_price_map == settings.payments.stripe_price_map

    def test_backward_compat_telegram_payment_provider_token(self):
        """settings.telegram_payment_provider_token property works."""
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://localhost/db",
                "TELEGRAM_PAYMENT_PROVIDER_TOKEN": "token_123",
            },
            clear=False,
        ):
            settings = Settings()
            assert settings.telegram_payment_provider_token == "token_123"
            assert settings.payments.telegram_payment_provider_token == "token_123"

    def test_backward_compat_telegram_payment_plans(self):
        """settings.telegram_payment_plans property works."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/db"},
            clear=False,
        ):
            settings = Settings()
            assert "premium_monthly" in settings.telegram_payment_plans
            assert (
                settings.telegram_payment_plans
                == settings.payments.telegram_payment_plans
            )

    def test_backward_compat_telegram_bot_token(self):
        """settings.telegram_bot_token property works."""
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://localhost/db",
                "TELEGRAM_BOT_TOKEN": "123:ABC",
            },
            clear=False,
        ):
            settings = Settings()
            assert settings.telegram_bot_token == "123:ABC"
            assert settings.telegram.bot_token == "123:ABC"

    def test_backward_compat_telegram_bot_username(self):
        """settings.telegram_bot_username property works."""
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://localhost/db",
                "TELEGRAM_BOT_USERNAME": "MyBot",
            },
            clear=False,
        ):
            settings = Settings()
            assert settings.telegram_bot_username == "MyBot"
            assert settings.telegram.bot_username == "MyBot"

    def test_backward_compat_media_dir(self):
        """settings.media_dir property works."""
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://localhost/db",
                "MEDIA_DIR": "/custom/media",
            },
            clear=False,
        ):
            settings = Settings()
            assert settings.media_dir == "/custom/media"
            assert settings.media.media_dir == "/custom/media"

    def test_backward_compat_media_ttl_seconds(self):
        """settings.media_ttl_seconds property works."""
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://localhost/db",
                "MEDIA_TTL_SECONDS": "172800",
            },
            clear=False,
        ):
            settings = Settings()
            assert settings.media_ttl_seconds == 172800
            assert settings.media.media_ttl_seconds == 172800

    def test_backward_compat_media_max_bytes(self):
        """settings.media_max_bytes property works."""
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://localhost/db",
                "MEDIA_MAX_BYTES": "10000000",
            },
            clear=False,
        ):
            settings = Settings()
            assert settings.media_max_bytes == 10000000
            assert settings.media.media_max_bytes == 10000000

    def test_all_backward_compat_properties_exist(self):
        """All backward compat properties exist and don't raise AttributeError."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/db"},
            clear=False,
        ):
            settings = Settings()

            # Verify all properties exist
            assert hasattr(settings, "stripe_secret_key")
            assert hasattr(settings, "stripe_webhook_secret")
            assert hasattr(settings, "stripe_price_map")
            assert hasattr(settings, "telegram_payment_provider_token")
            assert hasattr(settings, "telegram_payment_plans")
            assert hasattr(settings, "telegram_bot_token")
            assert hasattr(settings, "telegram_bot_username")
            assert hasattr(settings, "media_dir")
            assert hasattr(settings, "media_ttl_seconds")
            assert hasattr(settings, "media_max_bytes")

            # Verify they're all accessible without error
            _ = settings.stripe_secret_key
            _ = settings.stripe_webhook_secret
            _ = settings.stripe_price_map
            _ = settings.telegram_payment_provider_token
            _ = settings.telegram_payment_plans
            _ = settings.telegram_bot_token
            _ = settings.telegram_bot_username
            _ = settings.media_dir
            _ = settings.media_ttl_seconds
            _ = settings.media_max_bytes
