# PR-002 Settings - Complete Business Logic Audit

## Executive Summary

**Status**: ✅ **AUDIT COMPLETE - Comprehensive business logic identified**

**Finding**: 37 existing tests provide good foundation BUT **9 critical gaps found** that leave business logic unvalidated:

1. ❌ DSN password redaction in logging (security requirement)
2. ❌ Environment variable priority order (env overrides .env)
3. ❌ Pydantic v2 SettingsConfigDict behavior (case_sensitive=False)
4. ❌ Field validators for production mode cross-field validation
5. ❌ Boundary values and edge cases for numeric fields
6. ❌ Type coercion (string→int, string→bool)
7. ❌ Integration between main Settings and subsettings
8. ❌ .env file encoding verification
9. ❌ Extra fields allowed validation

---

## Part 1: Business Logic Inventory

### A. AppSettings Class

**Purpose**: Application-level configuration

**Fields**:
| Field | Type | Default | Constraint | Business Logic |
|-------|------|---------|-----------|-----------------|
| env | Literal | "development" | ✅ Must be exactly: development, staging, production | Enforcement of valid environments only |
| name | str | "trading-signal-platform" | ✅ None | App identifier |
| version | str | "0.1.0" | ✅ None | Version tracking |
| log_level | Literal | "INFO" | ✅ Must be: DEBUG, INFO, WARNING, ERROR, CRITICAL | Logging severity enforcement |
| debug | bool | False | ✅ None | Debug flag |

**Business Logic Rules**:
- ✅ Env must be literal (no typos)
- ✅ Log level must be literal (no invalid levels)
- ✅ Environment variable loading is case-insensitive (case_sensitive=False)

**Configuration**:
- env_file=".env" → Loads from .env file
- case_sensitive=False → "APP_ENV" loads env, "app_env" loads env, "App_Env" loads env
- extra="allow" → Allows unknown fields (permissive)

---

### B. DbSettings Class

**Purpose**: Database connection configuration with connection pooling

**Fields**:
| Field | Type | Default | Constraint | Business Logic |
|-------|------|---------|-----------|-----------------|
| url | str | **REQUIRED** (no default) | ✅ Validator: format check | MUST be provided, cannot be empty, must be valid DSN |
| echo | bool | False | ✅ None | SQL logging flag |
| pool_size | int | 20 | ✅ 1 ≤ value ≤ 100 | Connection pool size bounded |
| max_overflow | int | 10 | ✅ 0 ≤ value ≤ 50 | Connection overflow bounded |
| pool_pre_ping | bool | True | ✅ None | Pre-ping connections before using |
| pool_recycle | int | 3600 | ✅ value ≥ 300 | Recycle connections after 300+ seconds |

**Business Logic Rules**:

**URL Validation** (Two-stage validation):

1. **Before coercion** (mode="before"):
   - Check if value is empty string or whitespace-only
   - Reason: Catch empty values before Pydantic type coercion
   - Error: "DATABASE_URL cannot be empty"

2. **After coercion** (mode="after"):
   - Check if value starts with valid DB protocol:
     - ✅ `postgresql`
     - ✅ `postgresql+psycopg`
     - ✅ `postgresql+asyncpg`
     - ✅ `sqlite`
     - ✅ `sqlite+aiosqlite`
   - Reject unknown database types (e.g., "mysql://", "oracle://")
   - Error: "Unsupported database URL: {v}"

**Connection Pooling Logic**:
- pool_size [1, 100]: Number of connections to keep in pool
- max_overflow [0, 50]: Additional connections beyond pool_size
- pool_pre_ping: Prevents "connection lost" errors
- pool_recycle ≥ 300: Recycles connections after 5+ minutes (prevents DB timeouts)

---

### C. RedisSettings Class

**Purpose**: Redis cache configuration

**Fields**:
| Field | Type | Default | Constraint | Business Logic |
|-------|------|---------|-----------|-----------------|
| url | str | "redis://localhost:6379/0" | ✅ None | Redis connection string with default |
| enabled | bool | True | ✅ None | Can disable Redis entirely |

**Business Logic Rules**:
- ✅ Has reasonable default for local dev
- ✅ Can be disabled (enabled=False)

---

### D. SecuritySettings Class

**Purpose**: JWT and password hashing configuration

**Fields**:
| Field | Type | Default | Constraint | Business Logic |
|-------|------|---------|-----------|-----------------|
| jwt_secret_key | str | "change-me-in-production" | ✅ Validator: production check | INSECURE default, but validated in production |
| jwt_algorithm | str | "HS256" | ✅ None | JWT signing algorithm |
| jwt_expiration_hours | int | 24 | ✅ value ≥ 1 | Token lifetime must be at least 1 hour |
| argon2_time_cost | int | 2 | ✅ value ≥ 1 | Password hashing time cost |
| argon2_memory_cost | int | 65536 | ✅ value ≥ 1024 | Password hashing memory cost (bytes) |
| argon2_parallelism | int | 4 | ✅ value ≥ 1 | Password hashing parallelism |

**Business Logic Rules**:

**JWT Secret Production Validation** (mode="after"):
- In production (APP_ENV == "production"):
  - Reject default: "change-me-in-production"
  - Require minimum length: 32 characters
  - Error: "JWT_SECRET_KEY must be ≥32 characters in production"
- In dev/staging: Allow any value (for testing)

**Password Hashing Parameters**:
- All Argon2 parameters have minimum values to prevent DoS
- argon2_time_cost ≥ 1: Prevents 0-cost hashing
- argon2_memory_cost ≥ 1024 bytes: Reasonable minimum
- argon2_parallelism ≥ 1: At least one thread

---

### E. PaymentSettings Class

**Purpose**: Payment provider credentials (Stripe, Telegram)

**Fields**:
| Field | Type | Default | Constraint | Business Logic |
|-------|------|---------|-----------|-----------------|
| stripe_secret_key | str | "" | ✅ None | Stripe API key (optional) |
| stripe_webhook_secret | str | "" | ✅ None | Stripe webhook signing key (optional) |
| stripe_price_map | dict | {"premium_monthly": "price_1234"} | ✅ None | Price ID mapping |
| telegram_payment_provider_token | str | "" | ✅ None | Telegram payment provider token |
| telegram_payment_plans | dict | (complex nested) | ✅ None | Telegram payment plan definitions |

**Business Logic Rules**:
- ✅ All optional (empty string defaults)
- ✅ stripe_price_map has sensible default
- ✅ telegram_payment_plans has complete nested structure

---

### F. SignalsSettings Class

**Purpose**: Trading signals ingestion and validation

**Fields**:
| Field | Type | Default | Constraint | Business Logic |
|-------|------|---------|-----------|-----------------|
| hmac_key | str | "change-me-in-production" | ✅ Validator: production check | HMAC signing key, validated in production |
| hmac_enabled | bool | True | ✅ None | Can disable HMAC verification |
| dedup_window_seconds | int | 300 | ✅ 10 ≤ value ≤ 3600 | Duplicate signal window (10 sec to 1 hour) |
| max_payload_bytes | int | 32768 | ✅ 1024 ≤ value ≤ 1048576 | Max signal payload (1KB to 1MB) |

**Business Logic Rules**:

**HMAC Key Production Validation** (mode="after"):
- In production (APP_ENV == "production"):
  - Reject default: "change-me-in-production"
  - Require minimum length: 32 characters
  - Error: "SIGNALS_HMAC_KEY must be ≥32 characters in production"
- In dev/staging: Allow any value (for testing)

**Dedup Window** [10, 3600]:
- Minimum 10 seconds: Prevents too-sensitive dedup
- Maximum 3600 seconds (1 hour): Prevents duplicate signals for too long

**Max Payload** [1024, 1048576]:
- Minimum 1024 bytes: Allows realistic signal data
- Maximum 1MB: Prevents DoS with huge payloads

---

### G. TelegramSettings Class

**Purpose**: Telegram bot configuration

**Fields**:
| Field | Type | Default | Constraint | Business Logic |
|-------|------|---------|-----------|-----------------|
| bot_token | str | "" | ✅ None | Telegram bot API token (optional) |
| bot_username | str | "SampleBot" | ✅ None | Bot display name |

**Business Logic Rules**:
- ✅ Token optional (empty string)
- ✅ Username has sensible default

---

### H. TelemetrySettings Class

**Purpose**: OpenTelemetry and Prometheus monitoring

**Fields**:
| Field | Type | Default | Constraint | Business Logic |
|-------|------|---------|-----------|-----------------|
| otel_enabled | bool | False | ✅ None | OTEL tracing disabled by default |
| otel_exporter_endpoint | str | "http://localhost:4318" | ✅ None | OTEL collector endpoint |
| prometheus_enabled | bool | True | ✅ None | Prometheus metrics enabled by default |
| prometheus_port | int | 9090 | ✅ 1 ≤ value ≤ 65535 | Valid port number |

**Business Logic Rules**:
- ✅ prometheus_port bounded to valid port range [1, 65535]
- ✅ OTEL disabled by default (optional)
- ✅ Prometheus enabled by default

---

### I. MediaSettings Class

**Purpose**: Media/charting storage configuration

**Fields**:
| Field | Type | Default | Constraint | Business Logic |
|-------|------|---------|-----------|-----------------|
| media_dir | str | "media" | ✅ None | Directory to store media files |
| media_ttl_seconds | int | 86400 | ✅ None | TTL before cleanup (24 hours default) |
| media_max_bytes | int | 5000000 | ✅ None | Max file size (5MB default) |

**Business Logic Rules**:
- ✅ All have reasonable defaults
- ✅ No validators (permissive)

---

### J. Main Settings Class

**Purpose**: Aggregate all settings subsections

**Fields**:
| Field | Type | Default | Business Logic |
|-------|------|---------|-----------------|
| app | AppSettings | default_factory | Uses AppSettings() constructor |
| db | DbSettings | default_factory | Uses DbSettings() constructor (URL required) |
| redis | RedisSettings | default_factory | Uses RedisSettings() constructor |
| security | SecuritySettings | default_factory | Uses SecuritySettings() constructor |
| payments | PaymentSettings | default_factory | Uses PaymentSettings() constructor |
| signals | SignalsSettings | default_factory | Uses SignalsSettings() constructor |
| telegram | TelegramSettings | default_factory | Uses TelegramSettings() constructor |
| telemetry | TelemetrySettings | default_factory | Uses TelemetrySettings() constructor |
| media | MediaSettings | default_factory | Uses MediaSettings() constructor |

**Business Logic Rules**:
- ✅ All subsettings use `default_factory` to create instances
- ✅ Backward compatibility properties for direct attribute access
- ✅ `get_settings()` function provides global instance

**Backward Compatibility Properties**:
```python
settings.stripe_secret_key → settings.payments.stripe_secret_key
settings.telegram_bot_token → settings.telegram.bot_token
settings.media_dir → settings.media.media_dir
```

---

## Part 2: Test Coverage Analysis

### Tests Inventory (37 tests total)

#### TestSettingsLoading (4 tests)
| Test | Business Logic Validated | ✅/❌ |
|------|--------------------------|-------|
| test_default_settings_load | Default values are applied | ✅ |
| test_settings_load_from_env | Environment variables override defaults | ✅ |
| test_invalid_database_url_format | URL validator rejects invalid formats | ✅ |
| test_empty_database_url_rejected | URL validator rejects empty strings | ✅ |

**Coverage**: 4/4 basic loading scenarios

---

#### TestEnvironmentLayering (4 tests)
| Test | Business Logic Validated | ✅/❌ |
|------|--------------------------|-------|
| test_dev_environment | env="development" accepted | ✅ |
| test_staging_environment | env="staging" accepted | ✅ |
| test_production_environment | env="production" accepted | ✅ |
| test_invalid_environment_rejected | env literal validation rejects invalid | ✅ |

**Coverage**: 4/4 environment validation scenarios

---

#### TestProductionValidation (4 tests)
| Test | Business Logic Validated | ✅/❌ |
|------|--------------------------|-------|
| test_production_requires_version | APP_VERSION exists in production | ✅ |
| test_invalid_log_level_rejected | log_level literal validation rejects invalid | ✅ |
| test_default_log_level_applied | log_level="INFO" default applied | ✅ |
| test_invalid_version_rejected_in_production | Production validation works | ✅ |

**Coverage**: 4/4 production mode scenarios

---

#### TestDatabaseSettings (4 tests)
| Test | Business Logic Validated | ✅/❌ |
|-------|--------------------------|-------|
| test_database_url_required | URL field required (no default) | ✅ |
| test_pool_size_minimum_enforced | pool_size ≥ 1 | ✅ |
| test_max_overflow_minimum_enforced | max_overflow ≥ 0 | ✅ |
| test_custom_pool_configuration | Custom pool values accepted | ✅ |

**Coverage**: 4/4 DB connection pool scenarios

---

#### TestRedisSettings (2 tests)
| Test | Business Logic Validated | ✅/❌ |
|-------|--------------------------|-------|
| test_default_redis_settings_load | Redis defaults applied | ✅ |
| test_custom_redis_url_loaded | Custom Redis URL accepted | ✅ |

**Coverage**: 2/2 Redis scenarios

---

#### TestSecuritySettings (4 tests)
| Test | Business Logic Validated | ✅/❌ |
|-------|--------------------------|-------|
| test_default_security_settings | Security defaults loaded | ✅ |
| test_custom_jwt_configuration | Custom JWT values accepted | ✅ |
| test_jwt_expiration_minimum_enforced | jwt_expiration_hours ≥ 1 | ✅ |
| test_argon2_parameters_validated | Argon2 parameters have minimums | ✅ |

**Coverage**: 4/4 security scenarios

---

#### TestTelemetrySettings (3 tests)
| Test | Business Logic Validated | ✅/❌ |
|-------|--------------------------|-------|
| test_default_telemetry_settings | Telemetry defaults loaded | ✅ |
| test_custom_otel_endpoint | Custom OTEL endpoint accepted | ✅ |
| test_prometheus_port_validated | prometheus_port [1, 65535] enforced | ✅ |

**Coverage**: 3/3 telemetry scenarios

---

#### TestSettingsPydanticIntegration (3 tests)
| Test | Business Logic Validated | ✅/❌ |
|-------|--------------------------|-------|
| test_settings_inherit_from_basesettings | Inheritance structure correct | ✅ |
| test_settings_use_config_dict | SettingsConfigDict used | ✅ |
| test_field_validators_enforce_constraints | Validators work | ✅ |

**Coverage**: 3/3 Pydantic integration scenarios

---

#### TestSettingsEnvFileLoading (3 tests)
| Test | Business Logic Validated | ✅/❌ |
|-------|--------------------------|-------|
| test_settings_load_from_env_file | .env file loaded | ✅ |
| test_environment_variables_override_env_file | ENV overrides .env | ✅ |
| test_env_file_encoding_utf8 | UTF-8 encoding used | ✅ |

**Coverage**: 3/3 .env file scenarios

---

#### TestSettingsDocumentation (3 tests)
| Test | Business Logic Validated | ✅/❌ |
|-------|--------------------------|-------|
| test_settings_classes_documented | Docstrings present | ✅ |
| test_settings_fields_have_defaults | Default values present | ✅ |
| test_case_insensitive_env_loading | case_sensitive=False works | ✅ |

**Coverage**: 3/3 documentation/config scenarios

---

#### TestSettingsIntegration (4 tests)
| Test | Business Logic Validated | ✅/❌ |
|-------|--------------------------|-------|
| test_settings_instantiate_successfully | Can create Settings() | ✅ |
| test_database_settings_require_url | DbSettings.url required | ✅ |
| test_production_jwt_secret_validation | JWT secret validated in production | ✅ |
| test_all_settings_classes_instantiate_together | All subsettings work together | ✅ |

**Coverage**: 4/4 integration scenarios

---

## Part 3: Critical Gaps Found (⚠️ Business Logic NOT Tested)

### Gap 1: JWT Secret Production Validation ❌

**Business Logic**: In production, JWT_SECRET_KEY must be ≥32 characters and not "change-me-in-production"

**Current Test**: `test_production_jwt_secret_validation` in TestSettingsIntegration exists

**Problem**: Test doesn't actually SET APP_ENV to "production" to trigger validator

**Example of Missing Tests**:
```python
# MISSING: Test that rejects short JWT secret in production
def test_production_jwt_secret_too_short():
    with patch.dict(os.environ, {"APP_ENV": "production", "JWT_SECRET_KEY": "short"}):
        with pytest.raises(ValidationError, match="must be ≥32 characters"):
            SecuritySettings()

# MISSING: Test that rejects default value in production
def test_production_jwt_secret_rejects_default():
    with patch.dict(os.environ, {"APP_ENV": "production", "JWT_SECRET_KEY": "change-me-in-production"}):
        with pytest.raises(ValidationError, match="must be ≥32 characters"):
            SecuritySettings()

# MISSING: Test that ALLOWS short secret in dev
def test_dev_jwt_secret_allows_short():
    with patch.dict(os.environ, {"APP_ENV": "development", "JWT_SECRET_KEY": "short"}):
        settings = SecuritySettings()
        assert settings.jwt_secret_key == "short"
```

**Impact**: If JWT secret is left as default in production, system won't catch it at startup

---

### Gap 2: HMAC Secret Production Validation ❌

**Business Logic**: In production, SIGNALS_HMAC_KEY must be ≥32 characters and not "change-me-in-production"

**Current Test**: No specific test for this validator

**Missing Tests**:
```python
# MISSING: All 3 test cases above, but for HMAC secret
def test_production_hmac_key_too_short():
def test_production_hmac_key_rejects_default():
def test_dev_hmac_key_allows_short():
```

**Impact**: If HMAC key left as default in production, system won't catch it

---

### Gap 3: Database URL Validator - All DB Types Not Tested ❌

**Business Logic**: DATABASE_URL must start with one of these protocols:
- postgresql
- postgresql+psycopg
- postgresql+asyncpg
- sqlite
- sqlite+aiosqlite

**Current Test**: `test_invalid_database_url_format` exists but only tests one invalid case

**Missing Tests**:
```python
# MISSING: Test each VALID database type
def test_postgresql_url_accepted():
    settings = DbSettings(url="postgresql://user:pass@localhost/db")
    assert settings.url == "postgresql://user:pass@localhost/db"

def test_postgresql_asyncpg_url_accepted():
    settings = DbSettings(url="postgresql+asyncpg://user:pass@localhost/db")

def test_sqlite_url_accepted():
    settings = DbSettings(url="sqlite:///path/to/db.sqlite")

def test_sqlite_aiosqlite_url_accepted():
    settings = DbSettings(url="sqlite+aiosqlite:///path/to/db.sqlite")

# MISSING: Test that REJECTS unsupported database types
def test_mysql_url_rejected():
    with pytest.raises(ValidationError, match="Unsupported database URL"):
        DbSettings(url="mysql://user:pass@localhost/db")

def test_oracle_url_rejected():
    with pytest.raises(ValidationError, match="Unsupported database URL"):
        DbSettings(url="oracle://user:pass@localhost/db")

def test_mongodb_url_rejected():
    with pytest.raises(ValidationError, match="Unsupported database URL"):
        DbSettings(url="mongodb://user:pass@localhost/db")
```

**Impact**: If someone accidentally uses a MySQL or Oracle URL, system should reject it at startup

---

### Gap 4: Pool Configuration Boundary Values Not Tested ❌

**Business Logic**:
- pool_size: 1 ≤ value ≤ 100
- max_overflow: 0 ≤ value ≤ 50
- pool_recycle: value ≥ 300

**Current Test**: `test_pool_size_minimum_enforced` and `test_max_overflow_minimum_enforced` exist

**Missing Tests**:
```python
# MISSING: Test MAXIMUM pool_size
def test_pool_size_maximum_enforced():
    with pytest.raises(ValidationError, match="less than or equal to 100"):
        DbSettings(url="postgresql://localhost/db", pool_size=101)

# MISSING: Test MAXIMUM max_overflow
def test_max_overflow_maximum_enforced():
    with pytest.raises(ValidationError, match="less than or equal to 50"):
        DbSettings(url="postgresql://localhost/db", max_overflow=51)

# MISSING: Test pool_recycle minimum
def test_pool_recycle_minimum_enforced():
    with pytest.raises(ValidationError, match="greater than or equal to 300"):
        DbSettings(url="postgresql://localhost/db", pool_recycle=299)

# MISSING: Test all boundary values at valid edges
def test_pool_size_boundary_values():
    # Min boundary
    settings = DbSettings(url="postgresql://localhost/db", pool_size=1)
    assert settings.pool_size == 1

    # Max boundary
    settings = DbSettings(url="postgresql://localhost/db", pool_size=100)
    assert settings.pool_size == 100

def test_max_overflow_boundary_values():
    # Min boundary
    settings = DbSettings(url="postgresql://localhost/db", max_overflow=0)
    assert settings.max_overflow == 0

    # Max boundary
    settings = DbSettings(url="postgresql://localhost/db", max_overflow=50)
    assert settings.max_overflow == 50

def test_pool_recycle_boundary_value():
    # Min boundary (exactly 300 should pass)
    settings = DbSettings(url="postgresql://localhost/db", pool_recycle=300)
    assert settings.pool_recycle == 300
```

**Impact**: If pool_size set to 500, system should reject it (would waste memory)

---

### Gap 5: Environment Variable Priority Order Not Tested ❌

**Business Logic**: Environment variables OVERRIDE .env file values

**Current Test**: `test_environment_variables_override_env_file` exists

**Problem**: Test doesn't verify the ACTUAL priority order behavior with multiple settings

**Missing Tests**:
```python
# MISSING: Comprehensive priority order test
def test_env_variable_priority_order(tmp_path):
    """Test: ENV variable overrides .env file"""
    env_file = tmp_path / ".env"
    env_file.write_text("APP_ENV=staging\nAPP_LOG_LEVEL=DEBUG")

    with patch.dict(os.environ, {"APP_ENV": "production"}):
        settings = AppSettings(_env_file=str(env_file))
        # ENV should win over .env
        assert settings.env == "production"
        # .env should still be used for unset env vars
        assert settings.log_level == "DEBUG"

# MISSING: Test that if .env file doesn't exist, ENV is used
def test_env_used_if_no_env_file():
    with patch.dict(os.environ, {"APP_ENV": "production"}, clear=True):
        settings = AppSettings()
        assert settings.env == "production"
```

**Impact**: If .env and environment have different values, need to know which takes priority

---

### Gap 6: Type Coercion Not Tested ❌

**Business Logic**: Pydantic converts string environment variables to proper types

**Current Test**: None explicitly test type coercion

**Missing Tests**:
```python
# MISSING: String to int coercion
def test_pool_size_string_to_int_coercion():
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/db", "POOL_SIZE": "25"}):
        settings = DbSettings()
        assert settings.pool_size == 25
        assert isinstance(settings.pool_size, int)

def test_jwt_expiration_string_to_int_coercion():
    with patch.dict(os.environ, {"JWT_EXPIRATION_HOURS": "48"}):
        settings = SecuritySettings()
        assert settings.jwt_expiration_hours == 48
        assert isinstance(settings.jwt_expiration_hours, int)

def test_prometheus_port_string_to_int_coercion():
    with patch.dict(os.environ, {"PROMETHEUS_PORT": "8888"}):
        settings = TelemetrySettings()
        assert settings.prometheus_port == 8888
        assert isinstance(settings.prometheus_port, int)

# MISSING: String to bool coercion
def test_redis_enabled_string_to_bool_coercion():
    with patch.dict(os.environ, {"REDIS_ENABLED": "true"}):
        settings = RedisSettings()
        assert settings.enabled is True
        assert isinstance(settings.enabled, bool)

def test_hmac_enabled_string_to_bool_coercion():
    with patch.dict(os.environ, {"SIGNALS_HMAC_ENABLED": "false"}):
        settings = SignalsSettings()
        assert settings.hmac_enabled is False
        assert isinstance(settings.hmac_enabled, bool)

# MISSING: Invalid type coercion should fail
def test_invalid_pool_size_string_coercion_fails():
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/db", "POOL_SIZE": "not-a-number"}):
        with pytest.raises(ValidationError, match="Input should be a valid integer"):
            DbSettings()
```

**Impact**: If env var "POOL_SIZE=abc", system should reject at startup, not fail randomly later

---

### Gap 7: Case-Insensitive Environment Loading Not Tested ❌

**Business Logic**: case_sensitive=False means env variables can be any case

**Current Test**: `test_case_insensitive_env_loading` exists in TestSettingsDocumentation

**Problem**: Test just checks if case_sensitive=False is set, doesn't verify it WORKS

**Missing Tests**:
```python
# MISSING: Verify all case variations work
def test_env_variable_lowercase():
    with patch.dict(os.environ, {"app_env": "production"}):
        settings = AppSettings()
        assert settings.env == "production"

def test_env_variable_uppercase():
    with patch.dict(os.environ, {"APP_ENV": "production"}):
        settings = AppSettings()
        assert settings.env == "production"

def test_env_variable_mixedcase():
    with patch.dict(os.environ, {"App_Env": "production"}):
        settings = AppSettings()
        assert settings.env == "production"

def test_database_url_lowercase():
    with patch.dict(os.environ, {"database_url": "postgresql://localhost/db"}):
        settings = DbSettings()
        assert settings.url.startswith("postgresql")

def test_database_url_uppercase():
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/db"}):
        settings = DbSettings()
        assert settings.url.startswith("postgresql")
```

**Impact**: If app uses "app_env" instead of "APP_ENV", settings should still load correctly

---

### Gap 8: All Literal Values Not Tested ❌

**Business Logic**:
- AppSettings.env must be EXACTLY one of: development, staging, production
- AppSettings.log_level must be EXACTLY one of: DEBUG, INFO, WARNING, ERROR, CRITICAL
- SignalsSettings.dedup_window_seconds [10, 3600]
- SignalsSettings.max_payload_bytes [1024, 1048576]

**Current Test**: Basic invalid cases tested, but not ALL valid cases

**Missing Tests**:
```python
# MISSING: Test each VALID log level
def test_all_valid_log_levels():
    for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
        with patch.dict(os.environ, {"APP_LOG_LEVEL": level}):
            settings = AppSettings()
            assert settings.log_level == level

# MISSING: Test INVALID log level variations
def test_invalid_log_level_lowercase():
    with patch.dict(os.environ, {"APP_LOG_LEVEL": "debug"}):
        with pytest.raises(ValidationError, match="Input should be 'DEBUG'"):
            AppSettings()

# MISSING: Test dedup window boundaries
def test_dedup_window_minimum_boundary():
    settings = SignalsSettings(dedup_window_seconds=10)
    assert settings.dedup_window_seconds == 10

def test_dedup_window_maximum_boundary():
    settings = SignalsSettings(dedup_window_seconds=3600)
    assert settings.dedup_window_seconds == 3600

def test_dedup_window_below_minimum():
    with pytest.raises(ValidationError, match="greater than or equal to 10"):
        SignalsSettings(dedup_window_seconds=9)

def test_dedup_window_above_maximum():
    with pytest.raises(ValidationError, match="less than or equal to 3600"):
        SignalsSettings(dedup_window_seconds=3601)

# MISSING: Test payload size boundaries
def test_payload_minimum_boundary():
    settings = SignalsSettings(max_payload_bytes=1024)
    assert settings.max_payload_bytes == 1024

def test_payload_maximum_boundary():
    settings = SignalsSettings(max_payload_bytes=1048576)
    assert settings.max_payload_bytes == 1048576

def test_payload_below_minimum():
    with pytest.raises(ValidationError, match="greater than or equal to 1024"):
        SignalsSettings(max_payload_bytes=1023)

def test_payload_above_maximum():
    with pytest.raises(ValidationError, match="less than or equal to 1048576"):
        SignalsSettings(max_payload_bytes=1048577)
```

**Impact**: If someone sets max_payload_bytes=0, system should reject, not allow tiny payloads

---

### Gap 9: Settings Backward Compatibility Properties Not Tested ❌

**Business Logic**: Main Settings class has properties for backward compatibility

**Current Test**: None test the backward compatibility properties

**Missing Tests**:
```python
# MISSING: Test backward compatibility properties
def test_backward_compat_stripe_secret_key():
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/db", "STRIPE_SECRET_KEY": "sk_test_123"}):
        settings = Settings()
        # Old way: settings.stripe_secret_key (property)
        assert settings.stripe_secret_key == "sk_test_123"
        # New way: settings.payments.stripe_secret_key (direct)
        assert settings.payments.stripe_secret_key == "sk_test_123"

def test_backward_compat_telegram_bot_token():
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/db", "TELEGRAM_BOT_TOKEN": "bot_token_123"}):
        settings = Settings()
        assert settings.telegram_bot_token == "bot_token_123"
        assert settings.telegram.bot_token == "bot_token_123"

def test_backward_compat_media_dir():
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/db", "MEDIA_DIR": "/custom/media"}):
        settings = Settings()
        assert settings.media_dir == "/custom/media"
        assert settings.media.media_dir == "/custom/media"

# MISSING: Test that all backward compat properties work
def test_all_backward_compat_properties():
    settings = Settings()
    # Verify all properties exist and don't raise AttributeError
    assert hasattr(settings, 'stripe_secret_key')
    assert hasattr(settings, 'stripe_webhook_secret')
    assert hasattr(settings, 'stripe_price_map')
    assert hasattr(settings, 'telegram_payment_provider_token')
    assert hasattr(settings, 'telegram_payment_plans')
    assert hasattr(settings, 'telegram_bot_token')
    assert hasattr(settings, 'telegram_bot_username')
    assert hasattr(settings, 'media_dir')
    assert hasattr(settings, 'media_ttl_seconds')
    assert hasattr(settings, 'media_max_bytes')
```

**Impact**: Old code using `settings.stripe_secret_key` should work, not break with AttributeError

---

## Part 4: Gap Summary Table

| Gap # | Category | What's Missing | Impact Level | Effort |
|-------|----------|-----------------|--------------|--------|
| 1 | Production Validation | JWT secret production checks incomplete | 🔴 HIGH | 3 tests |
| 2 | Production Validation | HMAC secret production checks missing | 🔴 HIGH | 3 tests |
| 3 | URL Validation | DB URL validator not tested for all types | 🟡 MEDIUM | 5 tests |
| 4 | Boundary Testing | Pool config max values not tested | 🟡 MEDIUM | 5 tests |
| 5 | Env Priority | Priority order not fully tested | 🟡 MEDIUM | 3 tests |
| 6 | Type Coercion | String→int, string→bool coercion not tested | 🟡 MEDIUM | 8 tests |
| 7 | Case Sensitivity | case_insensitive behavior not verified | 🟡 MEDIUM | 5 tests |
| 8 | Literal Values | Not all valid/invalid literal values tested | 🟡 MEDIUM | 12 tests |
| 9 | Backward Compat | Properties for old API not tested | 🟡 MEDIUM | 5 tests |

**Total Missing Tests**: ~49 tests needed to reach 90-100% business logic coverage

**Current Tests**: 37
**Gap Tests**: 49
**Target Coverage**: 86 tests total

---

## Part 5: Summary & Recommendations

### ✅ What Works Well

1. **Core Structure**: Settings classes properly use Pydantic v2
2. **Validation Architecture**: Two-stage validators (before/after) properly implemented
3. **Field Constraints**: Numeric boundaries enforced with ge/le
4. **Literal Types**: Enum-like validation with Literal types
5. **Environment Loading**: .env file loading works correctly
6. **Default Values**: Sensible defaults for all optional fields

### ❌ What Needs Testing

1. **Production Mode Validation**: JWT/HMAC secrets need ≥32 chars - NOT fully tested
2. **Database URL Types**: All 5 supported DB types not validated
3. **Boundary Values**: Max values for pool configs not checked
4. **Type Coercion**: String→int/bool conversion not tested
5. **Case Insensitivity**: case_sensitive=False not verified
6. **Literal Values**: Not all valid/invalid enum values tested
7. **Backward Compatibility**: Old property API not tested

### 🎯 Next Action

Create comprehensive new test file: `test_pr_002_settings_gaps.py` with ~49 new tests covering all 9 gaps above.

**Expected Result**: 86 total tests, 90-100% business logic coverage, production-ready validation.
