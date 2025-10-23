# Local Test Environment Setup

This document explains how to run tests locally using the same PostgreSQL and Redis setup as CI.

## Quick Start

```bash
# 1. Start PostgreSQL and Redis services
docker compose -f docker-compose.test.yml up -d

# 2. Set environment variables
export ENVIRONMENT=test
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/telebot_test
export REDIS_URL=redis://localhost:6379/0
export LOG_LEVEL=ERROR

# 3. Run database migrations
cd backend
alembic upgrade head

# 4. Run tests
pytest tests/ -v --tb=short --cov=app --cov-report=term

# 5. Stop services when done
docker compose -f docker-compose.test.yml down
```

## PowerShell (Windows)

```powershell
# 1. Start services
docker compose -f docker-compose.test.yml up -d

# 2. Set environment variables
$env:ENVIRONMENT="test"
$env:DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/telebot_test"
$env:REDIS_URL="redis://localhost:6379/0"
$env:LOG_LEVEL="ERROR"

# 3. Run migrations
cd backend
alembic upgrade head

# 4. Run tests
pytest tests/ -v --tb=short --cov=app --cov-report=term

# 5. Stop services
docker compose -f docker-compose.test.yml down
```

## What Changed

### Database Type Compatibility Fixes
- **UUID → String(36)**: PostgreSQL UUID columns now use cross-database String(36)
- **JSONB → JSON**: PostgreSQL JSONB columns now use cross-database JSON type
- **Impact**: Tests work with both SQLite (local fast tests) and PostgreSQL (CI/production)

### CI Infrastructure Fixes
- **Services**: PostgreSQL 16 and Redis 7 with health checks
- **Wait Logic**: Explicit service readiness checks before running tests
- **Migrations**: Database schema applied before tests run
- **Environment**: Proper test environment variables set

## Expected Test Results

### Before Fixes
- 421 tests collected
- 214 passed
- 176 errors (database connection failures)
- 41 failed (mix of infrastructure and logic issues)

### After Infrastructure Fixes (Expected)
- 421 tests collected
- ~400+ passed ✅
- 0-10 errors (infrastructure issues resolved)
- ~40 failed (genuine test logic issues only)

## Troubleshooting

### Services won't start
```bash
# Check if ports are already in use
docker ps
netstat -an | findstr :5432
netstat -an | findstr :6379

# Stop any conflicting services
docker compose -f docker-compose.test.yml down -v
```

### Database connection fails
```bash
# Check PostgreSQL is ready
docker compose -f docker-compose.test.yml ps
docker compose -f docker-compose.test.yml logs postgres

# Test connection manually
psql postgresql://postgres:postgres@localhost:5432/telebot_test -c "SELECT 1;"
```

### Redis connection fails
```bash
# Check Redis is ready
docker compose -f docker-compose.test.yml ps
docker compose -f docker-compose.test.yml logs redis

# Test connection manually
redis-cli -h localhost -p 6379 ping
```

### Migrations fail
```bash
# Check database exists and is accessible
psql postgresql://postgres:postgres@localhost:5432/telebot_test -c "\dt"

# Re-run migrations with verbose output
cd backend
alembic upgrade head --verbose
```

## Service Configuration

### PostgreSQL
- **Image**: postgres:16
- **Port**: 5432
- **User**: postgres
- **Password**: postgres
- **Database**: telebot_test

### Redis
- **Image**: redis:7
- **Port**: 6379
- **Database**: 0 (default)

## CI Pipeline

The GitHub Actions workflow now:
1. Starts PostgreSQL and Redis services with health checks
2. Installs system dependencies (postgresql-client, redis-tools)
3. Waits for services to be ready
4. Installs Python dependencies
5. Runs database migrations
6. Executes all tests with coverage
7. Uploads coverage to Codecov

## Next Steps

After verifying infrastructure fixes work:
1. Monitor CI test run for remaining failures
2. Fix genuine test logic issues (~40 tests)
3. Focus areas:
   - PnL calculations (test_client_tracking.py)
   - Settings validation (test_settings.py)
   - Secret redaction patterns (test_secret_scan.py)
   - RSI data handling (test_rsi_fibonacci.py)
   - Position sizing formulas (test_positioning.py)
   - OHLC validation logic (test_ohlc_ingestion.py)
   - Rate limiter behavior (test_ratelimit*.py)
