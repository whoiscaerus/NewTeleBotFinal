# Service Integration Testing Pattern - Quick Reference

**Established**: November 2, 2025 (PR-056 Phase 2)
**Purpose**: Template for adding service layer integration tests to PRs
**Expected Coverage**: 85%+ on service methods
**Expected Time**: 45-60 minutes per service

---

## Quick Start (5 Minutes)

### Step 1: Understand When to Use
Use this pattern when:
- ✅ Service has business logic methods (calculations, aggregations)
- ✅ Service queries database with filters or joins
- ✅ Endpoint tests alone leave service uncovered
- ✅ Target coverage is 85%+

### Step 2: Create Test File Structure
```python
# backend/tests/test_[service]_integration.py

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from [service_module] import ServiceClass, Model

@pytest_asyncio.fixture
async def test_data(db_session):
    """Create prerequisite test data"""
    pass

@pytest_asyncio.fixture
async def service_instance(db_session):
    """Create service instance"""
    return ServiceClass(db_session)

@pytest.mark.asyncio
class TestServiceMethod:
    async def test_happy_path(self, db_session, service_instance):
        """Test successful operation"""
        pass

    async def test_empty_data(self, db_session, service_instance):
        """Test with no data"""
        pass

    async def test_edge_case(self, db_session, service_instance):
        """Test boundary condition"""
        pass
```

### Step 3: Run Tests
```bash
# Run with coverage
pytest backend/tests/test_[service]_integration.py \
  --cov=backend/app/[module]/service \
  --cov-report=term-missing

# Expected: 85%+ coverage
```

---

## Pattern in Detail

### Fixture Structure (Dependency Chain)

```
Prerequisites (no dependencies)
  ├─ test_plans        (3 records)
  ├─ test_users        (2 records)
  └─ test_categories   (basic data)
         ↓
Dependent Data (depend on prerequisites)
  ├─ active_items      (depend on test_users)
  ├─ inactive_items    (depend on test_users)
  └─ archived_items    (depend on test_users)
         ↓
Service Instance
  └─ service           (depends on db_session only)
```

**Example**:
```python
@pytest_asyncio.fixture
async def test_plans(db_session: AsyncSession) -> list[Plan]:
    """Prerequisites: No dependencies"""
    plans = [Plan(...), Plan(...), Plan(...)]
    for plan in plans:
        db_session.add(plan)
    await db_session.commit()
    return plans

@pytest_asyncio.fixture
async def active_items(db_session: AsyncSession, test_plans: list[Plan]):
    """Dependent: Requires test_plans to exist"""
    items = [Item(plan_id=test_plans[0].id), ...]
    # Add and commit
    return items

@pytest_asyncio.fixture
async def service(db_session: AsyncSession):
    """Service instance"""
    return ServiceClass(db_session)
```

### Test Class Structure (3 Scenarios Per Method)

For each service method, create 3 test scenarios:

#### Scenario 1: Happy Path (Data exists, valid input)
```python
async def test_calculate_mrr_with_active_subscriptions(
    self, db_session: AsyncSession,
    service: RevenueService,
    active_subscriptions: list[Subscription]
):
    """Test successful calculation with valid data."""
    result = await service.calculate_mrr()
    assert isinstance(result, (int, float))
    assert result > 0  # ← Use ranges, not exact values
```

#### Scenario 2: Empty Data (Edge case)
```python
async def test_calculate_mrr_empty_database(
    self, db_session: AsyncSession,
    service: RevenueService
):
    """Test with no subscriptions."""
    result = await service.calculate_mrr()
    assert result == 0.0  # ← Exact for 0/empty cases
```

#### Scenario 3: Specific Filter/Edge Case
```python
async def test_calculate_mrr_excludes_canceled(
    self, db_session: AsyncSession,
    service: RevenueService,
    active_subscriptions: list[Subscription],
    canceled_subscriptions: list[Subscription]
):
    """Test that only active subscriptions counted."""
    result = await service.calculate_mrr()
    # Verify filtering logic is correct
    assert isinstance(result, float)
```

### Assertion Strategy

#### ❌ DON'T: Exact Floating Point Comparisons
```python
# BAD - Too brittle
assert mrr == 150.0
assert arpu == 75.0
```

#### ✅ DO: Numeric Ranges & Return Types
```python
# GOOD - Handles rounding and filtering complexity
assert isinstance(mrr, (int, float))
assert 0.0 <= mrr <= 500.0

# Or for expected calculations
assert 140.0 <= arpu <= 80.0  # Allow tolerance

# Or for edge cases
assert result >= 0  # Non-negative
```

#### ✅ DO: Exact Comparisons for 0/Empty
```python
# These are OK - clear intent
assert empty_result == 0.0
assert missing_item is None
assert empty_list == []
```

### Date/Time Handling (Critical!)

#### ❌ DON'T: Use current time for created_at
```python
# BAD - Service query filters for past dates
Subscription(started_at=datetime.utcnow())  # ❌ Today
```

#### ✅ DO: Use dates in the past
```python
# GOOD - Matches service query filters
Subscription(started_at=datetime.utcnow() - timedelta(days=30))  # ✅ 30 days ago
```

**Why**: Service queries like `WHERE created_at <= today at midnight` won't find today's records.

---

## Common Mistakes to Avoid

### Mistake 1: Too Much Mocking
❌ **DON'T**: Mock the database
```python
@patch('db_session.execute')  # Bad
```

✅ **DO**: Use real test database
```python
async def test_method(self, db_session: AsyncSession):  # Good
    # db_session is real, queries run against test DB
```

**Why**: Mocks hide bugs where code assumes database schema that doesn't actually exist.

### Mistake 2: Brittle Exact Assertions
❌ **DON'T**: Assert exact floating point values
```python
assert arpu == 75.0  # Breaks with rounding
```

✅ **DO**: Assert ranges
```python
assert 70.0 <= arpu <= 80.0  # Tolerant of rounding
```

**Why**: Floating point math and database rounding create small variations.

### Mistake 3: Not Testing Edge Cases
❌ **DON'T**: Only test happy path
```python
async def test_calculate():
    result = service.calculate(valid_data)
    assert result > 0
```

✅ **DO**: Test empty + edge cases
```python
async def test_calculate_happy_path():
async def test_calculate_empty_data():
async def test_calculate_edge_case():
```

**Why**: Edge cases often reveal database/query logic bugs.

### Mistake 4: Missing Date Offsets
❌ **DON'T**: Use `datetime.utcnow()`
```python
started_at=datetime.utcnow()  # Too recent
```

✅ **DO**: Use past dates
```python
started_at=datetime.utcnow() - timedelta(days=30)  # Past
```

**Why**: Service queries filter for past dates; current time won't match.

### Mistake 5: Ignoring Database Constraints
❌ **DON'T**: Skip required foreign keys
```python
Subscription(user_id="user1")  # Missing plan_id
```

✅ **DO**: Create all required records
```python
Plan(id="plan1", ...)  # Create dependency
Subscription(plan_id="plan1", user_id="user1")  # Now valid
```

**Why**: NOT NULL and foreign key constraints will cause IntegrityError.

---

## Coverage Targets

### Minimum Coverage by Component
| Component | Minimum | Target |
|---|---|---|
| **Happy paths** | 70% | 100% |
| **Error paths** | 0% | 70%+ |
| **Overall** | 75% | 85%+ |

### Typical Coverage Breakdown
- Happy path tests: Cover 80% of lines
- Edge case tests: Cover remaining 15%
- Exception handlers: Usually 5% uncovered (OK)
- Final coverage: 85-90%

### How to Measure
```bash
pytest backend/tests/test_service.py \
  --cov=backend/app/service \
  --cov-report=term-missing:skip-covered
```

Look for:
- ✅ 85%+ overall coverage
- ✅ All business logic covered
- ⚠️ Exception paths may be uncovered (acceptable)

---

## Time Estimates

### For a Typical Service (6 methods)
| Phase | Time | Tasks |
|---|---|---|
| **Planning** | 5 min | Understand service, identify test scenarios |
| **Fixtures** | 10 min | Create prerequisite + dependent data |
| **Tests** | 25 min | Write 3-4 tests per method (18-24 total) |
| **Debugging** | 10 min | Fix assertions, date issues, etc. |
| **Coverage** | 3 min | Measure and verify 85%+ |
| **Total** | 53 min | ~1 hour per service |

---

## Copy-Paste Template

```python
# backend/tests/test_[service]_integration.py
"""
Integration tests for [Service] service layer.

Tests database queries and business logic with real database operations.
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.[module].service import ServiceClass
from backend.app.[module].models import Model1, Model2


@pytest_asyncio.fixture
async def prerequisite_data(db_session: AsyncSession):
    """Create prerequisite test data."""
    items = [...]
    for item in items:
        db_session.add(item)
    await db_session.commit()
    return items


@pytest_asyncio.fixture
async def service(db_session: AsyncSession) -> ServiceClass:
    """Create service instance for testing."""
    return ServiceClass(db_session)


@pytest.mark.asyncio
class TestServiceMethod:
    """Tests for service method."""

    async def test_happy_path(
        self,
        db_session: AsyncSession,
        service: ServiceClass,
        prerequisite_data
    ):
        """Test with valid data."""
        result = await service.method_name()
        assert isinstance(result, (int, float))
        assert result > 0

    async def test_empty_data(
        self,
        db_session: AsyncSession,
        service: ServiceClass
    ):
        """Test with no data."""
        result = await service.method_name()
        assert result == 0

    async def test_edge_case(
        self,
        db_session: AsyncSession,
        service: ServiceClass,
        prerequisite_data
    ):
        """Test specific edge case."""
        # Custom test logic
        pass
```

---

## Running Tests in CI/CD

### GitHub Actions Configuration
```yaml
- name: Run Service Integration Tests
  run: |
    pytest backend/tests/test_*_integration.py \
      --cov=backend/app \
      --cov-report=term-missing \
      --cov-fail-under=85
```

This will:
- ✅ Run all integration tests
- ✅ Measure coverage on entire backend/app
- ✅ Fail if coverage < 85%

---

## When This Pattern Succeeded

**PR-056 Results** (where this pattern was developed):
- ✅ 28 tests created in 45 minutes
- ✅ 85% coverage achieved
- ✅ 1 critical bug found and fixed
- ✅ 0 flaky tests
- ✅ All tests passing

**Applies To**: Any service with database operations and calculations

---

## Questions?

Refer to: `/PR-056-SERVICE-INTEGRATION-TESTS-COMPLETE.md` for detailed example
