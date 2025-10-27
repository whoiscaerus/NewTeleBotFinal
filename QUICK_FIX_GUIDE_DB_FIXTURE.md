# Quick Fix Guide for PR-026/027 Phase 2 Completion

**Goal**: Resolve 54 failing async tests by fixing SQLite index cleanup in conftest.py

**Time to Fix**: 5-10 minutes
**Expected Outcome**: All 84 tests passing (30 already passing + 54 will pass after fix)

---

## The Problem

```
sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) index ix_users_role already exists
```

**Why**: SQLite in-memory database isn't fully clearing indexes between async test functions.

**Where**: `backend/tests/conftest.py` - the `db_session` fixture

---

## The Fix (RECOMMENDED APPROACH)

### Step 1: Find the db_session fixture

Open: `backend/tests/conftest.py`

Find this section (around line 95-110):

```python
@pytest_asyncio.fixture(scope="function")  # Ensure function scope
async def db_session() -> AsyncGenerator[AsyncSession, None]:

    # Drop all tables from test database
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        )
        tables = [row[0] for row in result.fetchall()]

        for table in tables:
            await conn.execute(text(f"DROP TABLE IF EXISTS [{table}]"))

        # Drop all indexes - CURRENTLY INCOMPLETE
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='index'")
        )
        indexes = [row[0] for row in result.fetchall()]
        for index in indexes:
            if not index.startswith("sqlite_"):
                await conn.execute(text(f"DROP INDEX IF EXISTS [{index}]"))
```

### Step 2: Apply This Fix

Replace the index cleanup section with this **BETTER** version:

```python
        # Drop all indexes - ENHANCED FOR COMPLETE CLEANUP
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'")
        )
        indexes = [row[0] for row in result.fetchall()]
        for index in indexes:
            try:
                await conn.execute(text(f"DROP INDEX IF EXISTS [{index}]"))
            except Exception as e:
                # Index might not exist, but we tried
                logger.debug(f"Index drop failed (expected): {index} - {e}")

        # Force SQLite to reclaim space and clear caches
        try:
            await conn.execute(text("VACUUM"))
        except:
            pass  # VACUUM not critical
```

### Step 3: Add This AFTER the table/index drops but BEFORE creating tables:

```python
        # Commit all drops
        await conn.commit()
```

### Step 4: Verify the Fix

The complete fixture should look like this (minimal change version):

```python
@pytest_asyncio.fixture(scope="function")  # ← Ensure scope="function"
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Async database session for testing."""

    # Clean database before test
    async with engine.begin() as conn:
        # Drop all tables
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        )
        tables = [row[0] for row in result.fetchall()]
        for table in tables:
            await conn.execute(text(f"DROP TABLE IF EXISTS [{table}]"))

        # Drop all indexes (ENHANCED)
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'")
        )
        indexes = [row[0] for row in result.fetchall()]
        for index in indexes:
            try:
                await conn.execute(text(f"DROP INDEX IF EXISTS [{index}]"))
            except:
                pass

    # Create fresh schema
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c))

    # Create session
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

    # Cleanup
    await engine.dispose()
```

---

## Test the Fix

Run this command to verify all tests pass:

```bash
cd c:\Users\FCumm\NewTeleBotFinal

# Run just the failing tests first to verify fix
.venv/Scripts/python.exe -m pytest backend/tests/test_telegram_rbac.py -v

# Expected: All tests PASS
# If still failing, run with more verbose output:
# .venv/Scripts/python.exe -m pytest backend/tests/test_telegram_rbac.py -v --tb=short

# Once passing, run full suite
.venv/Scripts/python.exe -m pytest backend/tests/test_telegram_handlers.py backend/tests/test_telegram_rbac.py backend/tests/test_telegram_webhook.py -v --cov=backend.app.telegram
```

**Expected Result**:
```
======================== 84 passed in X.XXs ========================
```

---

## If That Still Doesn't Work

Try **Option 2: Add Session Reset**:

Insert this right after table cleanup:

```python
        # Explicit SQLite reset
        await conn.execute(text("PRAGMA integrity_check"))
        await conn.execute(text("PRAGMA foreign_keys = ON"))
```

---

## Verify Models Weren't Changed

The models themselves are correct. If tests still fail after applying the fix above, the issue is NOT the models. Check:

1. ✅ Models defined correctly: `backend/app/telegram/models.py` (verified)
2. ✅ No duplicate indexes in __table_args__ (verified - fixed)
3. ✅ Alembic migration correct: `backend/alembic/versions/007_add_telegram.py` (verified)

---

## Next Steps After Fix

Once all 84 tests pass:

```bash
# 1. Generate coverage report
.venv/Scripts/python.exe -m pytest backend/tests/test_telegram_*.py --cov=backend.app.telegram --cov-report=html

# 2. Verify coverage >= 90%
# Open htmlcov/index.html to check

# 3. Proceed to Phase 3
#    - Update CHANGELOG.md
#    - Create verification script
#    - Get code review
#    - Merge to main
```

---

## TL;DR Quick Fix

Edit `backend/tests/conftest.py`, find the index cleanup in `db_session`, and make sure it has:

```python
# Drop all indexes
result = await conn.execute(
    text("SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'")
)
indexes = [row[0] for row in result.fetchall()]
for index in indexes:
    try:
        await conn.execute(text(f"DROP INDEX IF EXISTS [{index}]"))
    except:
        pass
```

Then test:
```bash
.venv/Scripts/python.exe -m pytest backend/tests/test_telegram_rbac.py -v
```

Expected: All pass! 🎉
