# PR-048: Acceptance Criteria & Test Mapping

**PR ID**: 048
**Feature**: Risk Controls & Guardrails
**Date**: Jan 15, 2025

---

## 📋 Acceptance Criteria

### AC1: RiskProfile Model Supports 7 Configurable Limits
**Test Case**: `test_get_or_create_risk_profile_creates_with_defaults`
**Expected Behavior**:
- Model has 7 fields: max_drawdown_percent, max_daily_loss, max_position_size, max_open_positions, max_correlation_exposure, risk_per_trade_percent, client_id
- Each field has sensible default
- client_id is UNIQUE constraint
- Field types and ranges enforced by SQLAlchemy

**Verification**:
```python
profile = await RiskService.get_or_create_risk_profile(client_id, db)
assert profile.max_drawdown_percent == Decimal("20.00")
assert profile.max_open_positions == 5
```

---

### AC2: ExposureSnapshot Model Tracks Position Breakdown
**Test Case**: `test_calculate_current_exposure_creates_snapshot`
**Expected Behavior**:
- Model has exposure_by_instrument (JSON)
- Model has exposure_by_direction (JSON)
- Model tracks timestamp and open_positions_count
- Supports drawdown and daily_pnl tracking

**Verification**:
```python
exposure = await RiskService.calculate_current_exposure(user_id, db)
assert "EURUSD" in exposure.exposure_by_instrument
assert exposure.exposure_by_direction["buy"] >= Decimal("0")
```

---

### AC3: Alembic Migration Creates Tables with Indexes
**Test Case**: `test_alembic_migration_creates_tables`
**Expected Behavior**:
- Migration file exists: `backend/alembic/versions/048_add_risk_tables.py`
- upgrade() creates risk_profiles table
- upgrade() creates exposure_snapshots table
- Indexes on client_id for fast lookups
- downgrade() drops tables safely

**Verification**:
```bash
alembic upgrade head  # Tables created
alembic downgrade -1  # Tables dropped
```

---

### AC4: get_or_create_risk_profile Returns Defaults
**Test Cases**:
- `test_get_or_create_risk_profile_creates_with_defaults`
- `test_get_or_create_risk_profile_returns_existing`
- `test_get_or_create_risk_profile_idempotent`

**Expected Behavior**:
- First call creates profile with defaults
- Second call returns existing (idempotent)
- Multiple clients get unique profiles
- Defaults are: DD=20%, OP=5, PS=1.0, RPT=2%

**Verification**:
```python
profile1 = await RiskService.get_or_create_risk_profile(client_id, db)
profile2 = await RiskService.get_or_create_risk_profile(client_id, db)
assert profile1.id == profile2.id  # Same profile
```

---

### AC5: calculate_current_exposure Aggregates All Open Trades
**Test Cases**:
- `test_calculate_current_exposure_empty_when_no_trades`
- `test_calculate_current_exposure_single_buy_trade`
- `test_calculate_current_exposure_multiple_trades`
- `test_calculate_current_exposure_ignores_closed_trades`

**Expected Behavior**:
- Returns zero exposure when no open trades
- Correctly sums by instrument and direction
- Only counts OPEN trades (ignores CLOSED/CANCELLED)
- Calculates total as sum(volume * entry_price)

**Verification**:
```python
exposure = await RiskService.calculate_current_exposure(user_id, db)
assert exposure.total_exposure == Decimal("5000.00")
assert exposure.exposure_by_instrument["EURUSD"] == Decimal("5000.00")
assert exposure.open_positions_count == 1
```

---

### AC6: check_risk_limits Validates All 6 Limit Types
**Test Cases**:
- `test_check_risk_limits_passes_when_under_all_limits`
- `test_check_risk_limits_violates_max_open_positions`
- `test_check_risk_limits_violates_max_position_size`
- `test_check_risk_limits_violates_max_daily_loss`
- `test_check_risk_limits_violates_max_drawdown`
- `test_check_risk_limits_returns_exposure_data`

**Limit 1: Max Open Positions**
- Blocks signals if already at max open positions
- Returns violation with current count and limit

**Limit 2: Max Position Size**
- Blocks if proposed size > profile limit
- Returns violation with sizes

**Limit 3: Max Daily Loss**
- Blocks if daily loss already exceeds limit
- Returns violation with loss amount

**Limit 4: Max Drawdown**
- Blocks if drawdown >= limit
- Returns violation with percentage

**Limit 5: Correlation Exposure**
- Blocks if related instruments exceed concentration
- Uses instrument groupings (majors, commodities, etc.)

**Limit 6: Global Platform Limits**
- Blocks if platform exposure capped
- Returns violation with platform totals

**Verification**:
```python
result = await RiskService.check_risk_limits(user_id, signal, db)
assert result["passes"] is True  # All limits OK
assert len(result["violations"]) == 0

# Violation case
result = await RiskService.check_risk_limits(user_id, signal_big, db)
assert result["passes"] is False
assert result["violations"][0]["check"] == "max_position_size"
```

---

### AC7: calculate_position_size Respects Constraints
**Test Cases**:
- `test_calculate_position_size_respects_min_limit`
- `test_calculate_position_size_respects_max_limit`
- `test_calculate_position_size_uses_kelly_criterion`
- `test_calculate_position_size_with_custom_risk_percent`

**Expected Behavior**:
- Minimum size: 0.01 lots
- Maximum size: Profile max or platform max (100 lots)
- Uses Kelly-like: position_size = (equity * risk%) / stop_distance
- Supports risk_percent override
- Higher risk percent → larger position size (monotonic)

**Verification**:
```python
size1 = await RiskService.calculate_position_size(user_id, signal, risk_percent=Decimal("1.0"), db=db)
size2 = await RiskService.calculate_position_size(user_id, signal, risk_percent=Decimal("3.0"), db=db)
assert Decimal("0.01") <= size1 <= Decimal("1.0")  # Within limits
assert size2 >= size1  # Higher risk = bigger position
```

---

### AC8: calculate_current_drawdown Returns Peak-to-Trough %
**Test Cases**:
- `test_calculate_current_drawdown_zero_when_no_trades`
- `test_calculate_current_drawdown_zero_with_profit_only`
- `test_calculate_current_drawdown_with_loss_trades`

**Expected Behavior**:
- Zero drawdown when no closed trades
- Zero drawdown with only profitable trades
- Positive drawdown with losses
- Formula: (peak_equity - current_equity) / peak_equity * 100
- Never negative (lower bound: 0%)

**Verification**:
```python
drawdown = await RiskService.calculate_current_drawdown(user_id, db)
assert Decimal("0.00") <= drawdown <= Decimal("100.00")  # Valid range
```

---

### AC9: check_global_limits Detects Platform Violations
**Test Cases**:
- `test_check_global_limits_passes_when_under_limits`
- `test_check_global_limits_detects_high_exposure`
- `test_check_global_limits_detects_high_position_count`

**Expected Behavior**:
- Passes when under platform limits
- Returns violation when:
  - Total platform exposure > $500k
  - Total open positions > 50
  - Instrument concentration excessive
- Returns current utilization percentages

**Verification**:
```python
result = await RiskService.check_global_limits("EURUSD", Decimal("1.0"), db)
assert result["passes"] is True
assert result["total_platform_exposure"] < RiskService.PLATFORM_MAX_EXPOSURE
```

---

### AC10: GET /api/v1/risk/profile Returns Current Profile
**Test Case**: `test_api_get_risk_profile_endpoint`
**Expected Behavior**:
- Requires authentication
- Returns 200 with profile data
- Returns default if doesn't exist
- Response includes all 7 fields

**Verification**:
```bash
curl -H "Authorization: Bearer TOKEN" \
     https://api.example.com/api/v1/risk/profile
# Response: 200
# {
#   "id": "...",
#   "max_drawdown_percent": "20.00",
#   "max_position_size": "1.0",
#   ...
# }
```

---

### AC11: PATCH /api/v1/risk/profile Updates Limits
**Test Case**: `test_api_patch_risk_profile_endpoint`
**Expected Behavior**:
- Requires authentication
- Partial updates (only specified fields)
- Validates ranges (prevents invalid values)
- Returns updated profile
- Returns 400 for invalid values

**Verification**:
```bash
curl -X PATCH \
     -H "Authorization: Bearer TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"max_drawdown_percent": "25.00"}' \
     https://api.example.com/api/v1/risk/profile
# Response: 200 with updated profile
```

---

### AC12: GET /api/v1/risk/exposure Returns Exposure Snapshot
**Test Case**: `test_api_get_exposure_endpoint`
**Expected Behavior**:
- Requires authentication
- Returns current exposure snapshot
- Includes breakdowns by instrument and direction
- Returns 0 when no open trades
- Returns timestamp of calculation

**Verification**:
```bash
curl -H "Authorization: Bearer TOKEN" \
     https://api.example.com/api/v1/risk/exposure
# Response: 200
# {
#   "total_exposure": "15000.50",
#   "exposure_by_instrument": {"EURUSD": 5000.00, "GOLD": 10000.50},
#   "exposure_by_direction": {"buy": 12000.00, "sell": 3000.50},
#   "open_positions_count": 3,
#   ...
# }
```

---

### AC13: GET /api/v1/admin/risk/global-exposure Requires Admin
**Test Case**: `test_api_admin_global_exposure_requires_admin_role`
**Expected Behavior**:
- Requires admin role
- Returns 403 for non-admin users
- Returns platform-wide exposure stats
- Shows utilization percentages

**Verification**:
```bash
# As admin
curl -H "Authorization: Bearer ADMIN_TOKEN" \
     https://api.example.com/api/v1/admin/risk/global-exposure
# Response: 200 with platform exposure

# As regular user
curl -H "Authorization: Bearer USER_TOKEN" \
     https://api.example.com/api/v1/admin/risk/global-exposure
# Response: 403 Forbidden
```

---

### AC14: Risk Check Integrated into Approval Flow
**Test Case**: (Integration test in approval module)
**Expected Behavior**:
- Before approval is created, check_risk_limits() called
- If violations exist, returns 403 with violation details
- If passes, approval proceeds normally
- Violation includes message and details

**Verification**:
```python
# Signal violates risk limit
result = await client.post(
    "/api/v1/approvals",
    json={"signal_id": "sig-123", "decision": "approved"},
    headers=auth_headers
)
assert result.status_code == 403
assert "Signal violates risk limits" in result.json()["detail"]["message"]
```

---

### AC15: Exposure Updated After Approval
**Test Case**: (Integration test)
**Expected Behavior**:
- After approval, exposure snapshot created
- Snapshot reflects current positions
- Used for exposure tracking and alerts

**Verification**:
```python
# Approve signal
response = await client.post(
    "/api/v1/approvals",
    json={"signal_id": "sig-123", "decision": "approved"},
    headers=auth_headers
)
assert response.status_code == 201

# Check exposure updated
exposure = await RiskService.calculate_current_exposure(user_id, db)
assert exposure.timestamp >= approval_time
```

---

### AC16: Celery Tasks Execute on Schedule
**Test Case**: (Task tests)
**Expected Behavior**:
- `calculate_exposure_snapshots_task`: Runs every 1 hour
- `check_drawdown_breakers_task`: Runs every 15 minutes
- `cleanup_old_exposure_snapshots_task`: Runs weekly
- Tasks log execution details
- Retries on failure (exponential backoff)

**Verification**:
```bash
# Verify task scheduled
celery -A backend.app.tasks.risk_tasks inspect scheduled
# Response shows periodic task scheduled

# Test task execution
from backend.app.tasks.risk_tasks import calculate_exposure_snapshots_task
result = calculate_exposure_snapshots_task()
assert result["status"] == "success"
```

---

### AC17: Test Coverage ≥ 90% for Risk Module
**Test Case**: All 35+ tests
**Expected Behavior**:
- All risk module functions have tests
- Tests cover:
  - Happy path (normal operation)
  - Error paths (violations, edge cases)
  - Edge cases (empty, boundary values)
  - Concurrency (multiple simultaneous operations)
- Coverage report shows ≥90% coverage

**Verification**:
```bash
pytest backend/tests/test_pr_048_risk_controls.py --cov=backend/app/risk --cov-report=html
# Verify coverage ≥ 90% for:
# - backend/app/risk/models.py
# - backend/app/risk/service.py
# - backend/app/risk/routes.py
```

---

### AC18: All 4 Documentation Files Complete
**Test Case**: Manual review
**Expected Behavior**:
- PR-048-IMPLEMENTATION-PLAN.md: Complete with phases, schema, API
- PR-048-ACCEPTANCE-CRITERIA.md: All 18 criteria with test mapping
- PR-048-IMPLEMENTATION-COMPLETE.md: Final verification and metrics
- PR-048-BUSINESS-IMPACT.md: Revenue, strategic value, ROI

**Verification**:
```bash
ls -la docs/prs/PR-048-*
# Should show 4 files, no TODOs, no placeholders
grep -r "TODO\|FIXME" docs/prs/PR-048-*
# Should return empty (no TODOs)
```

---

## 📊 Test Coverage Summary

| Category | Tests | Coverage |
|----------|-------|----------|
| Risk Profile | 4 | 100% |
| Exposure Calculation | 5 | 100% |
| Risk Limit Validation | 8 | 95% |
| Position Sizing | 4 | 90% |
| Drawdown | 3 | 85% |
| Global Limits | 3 | 90% |
| API Endpoints | 6 | 95% |
| Error Handling | 5+ | 85% |
| **Total** | **35+** | **≥90%** |

---

## ✅ Verification Checklist

Before merging:

- [ ] All 35+ tests passing locally
- [ ] Coverage ≥90% for risk module
- [ ] All API endpoints tested
- [ ] Integration tests for approval flow
- [ ] Task execution verified
- [ ] 4 documentation files complete
- [ ] No TODOs or placeholders in code
- [ ] Black formatting applied
- [ ] No hardcoded values (config/env only)
- [ ] Security validated (input validation, no secrets)
- [ ] GitHub Actions CI/CD passing
- [ ] Code review: 2 approvals
- [ ] Ready to merge ✅

---

**Last Updated**: Jan 15, 2025
**Status**: Complete
