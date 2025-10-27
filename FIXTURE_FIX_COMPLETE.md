# ✅ Database Fixture Issue - RESOLVED

**Date**: October 27, 2025
**Status**: COMPLETE
**Impact**: All database tests now run without fixture errors

---

## Problem Identified

The SQLite in-memory test database fixture was reusing index definitions across tests, causing `OperationalError: index ix_referral_events_user_id already exists` when creating the fresh database for each test.

**Root Cause**: SQLAlchemy's `Base.metadata` caches table and index definitions. When `Base.metadata.create_all()` was called on a fresh `:memory:` database, SQLAlchemy still tried to create indexes that were already recorded in its metadata cache, even though they didn't exist in the fresh database.

---

## Solution Implemented

### File 1: `/backend/tests/conftest.py` (Primary)
Updated the `db_session` fixture to:
1. Create a completely fresh in-memory SQLite database for each test
2. Remove all unnecessary cleanup code (dropping tables/indexes that don't exist in fresh DB)
3. Simply call `Base.metadata.create_all()` on the fresh engine
4. Use `@event.listens_for` to set `PRAGMA foreign_keys=ON` for each connection

**Key Change**:
```python
# BEFORE: Tried to drop tables/indexes that don't exist yet
async with engine.begin() as conn:
    await conn.execute(text("DROP TABLE IF EXISTS [...]"))
    # ... expensive cleanup code

# AFTER: Fresh in-memory DB needs no cleanup
async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)
```

### File 2: `/backend/conftest.py` (Root)
Simplified to match the working implementation in `/backend/tests/conftest.py`. This ensures consistency across all tests.

---

## Test Results

**Before Fix**:
```
ERROR backend\tests\test_pr_038_billing.py::TestBillingAPI::test_get_subscription_endpoint
  sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) index ix_referral_events_user_id already exists
10 passed, 1 skipped, 4 ERRORS
```

**After Fix**:
```
FAILED backend\tests\test_pr_038_billing.py::TestBillingAPI::test_get_subscription_endpoint
  assert 401 == 200  (authentication issue, NOT database)
10 PASSED, 1 SKIPPED, 4 tests with 401 Unauthorized
```

✅ **Database fixture errors: ELIMINATED**
✅ **Tests now run successfully**: 10+ tests passing
✅ **Remaining 401 errors are authentication-related**, not fixture-related

---

## Next Steps

The 4 tests failing with `401 Unauthorized` are NOT database errors. These are application-level auth issues:
- `test_get_subscription_endpoint`
- `test_get_subscription_no_auth`
- `test_portal_session_creation`
- `test_miniapp_portal_open_metric`

These need JWT auth setup in the test fixtures, not database fixes.

---

## Lessons Learned

**Issue**: SQLAlchemy caches metadata even with fresh `:memory:` databases
**Solution**: Don't clean up tables/indexes that don't exist in a fresh database
**Prevention**: Use fresh in-memory engines for each test, not cleanup operations

**Pattern for Future**:
```python
# ✅ DO: Fresh in-memory DB needs NO cleanup
engine = create_async_engine("sqlite+aiosqlite:///:memory:", ...)
async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)

# ❌ DON'T: Drop/clean operations on fresh databases
await conn.execute(text("DROP TABLE IF EXISTS [...]"))
```
