# PR-046 Telemetry Integration Quick Reference

## Overview

PR-046 requires integration with Prometheus metrics and Telegram alerting. Most code is already in place; this guide covers verification and final integration.

---

## 1. Prometheus Metrics

### Metrics to Implement

#### Counter: `copy_risk_block_total`
Incremented when a trade is blocked due to risk breach.

```python
# In backend/app/copytrading/risk.py
from prometheus_client import Counter

copy_risk_block_counter = Counter(
    'copy_risk_block_total',
    'Total number of trades blocked due to risk limits',
    ['reason', 'user_tier']  # Labels for filtering
)

# In RiskEvaluator._handle_breach()
async def _handle_breach(self, db, user_id, settings, breach_reason, detailed_message):
    # ... existing pause logic ...

    # Add metric increment
    user_tier = await self._get_user_tier(db, user_id)  # "free", "premium", "vip"
    copy_risk_block_counter.labels(
        reason=breach_reason,  # "max_leverage", "max_trade_risk", etc.
        user_tier=user_tier
    ).inc()
```

#### Counter: `copy_consent_signed_total`
Incremented when user accepts a disclosure.

```python
# In backend/app/copytrading/disclosures.py
from prometheus_client import Counter

copy_consent_counter = Counter(
    'copy_consent_signed_total',
    'Total number of consent acceptances',
    ['version', 'user_tier']  # Labels for filtering
)

# In DisclosureService.record_consent()
async def record_consent(self, db, user_id, disclosure_version, ip_address, user_agent):
    # ... existing consent record logic ...

    # Add metric increment
    user_tier = await self._get_user_tier(db, user_id)
    copy_consent_counter.labels(
        version=disclosure_version,
        user_tier=user_tier
    ).inc()

    # ... rest of method ...
```

### Integration Steps

1. **Check if Prometheus available** in your backend:
   ```bash
   pip list | grep prometheus
   ```
   If not installed:
   ```bash
   pip install prometheus-client
   ```

2. **Register metrics** in FastAPI app:
   ```python
   # backend/main.py
   from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
   from fastapi import Response

   @app.get("/metrics")
   async def metrics():
       return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
   ```

3. **Add to risk.py**:
   ```python
   # Lines to add at top of file
   from prometheus_client import Counter

   copy_risk_block_counter = Counter(
       'copy_risk_block_total',
       'Total number of trades blocked due to risk limits',
       ['reason', 'user_tier']
   )
   ```

4. **Add to disclosures.py**:
   ```python
   # Lines to add at top of file
   from prometheus_client import Counter

   copy_consent_counter = Counter(
       'copy_consent_signed_total',
       'Total number of consent acceptances',
       ['version', 'user_tier']
   )
   ```

5. **Add metric calls**:
   - In `risk.py`, line after updating `is_paused = True`
   - In `disclosures.py`, line after creating UserConsent record

---

## 2. Telegram Alert Integration

### Current Status

Risk breaches already call: `self.telegram_service.send_user_alert()`

**File**: `backend/app/copytrading/risk.py`, line ~180 in `_handle_breach()`

### What to Verify

1. **Check if Telegram service exists**:
   ```bash
   find backend -name "*telegram*" -type f | head -20
   ```

2. **Verify service interface**:
   ```bash
   grep -r "send_user_alert" backend/app --include="*.py" | head -5
   ```

3. **Expected service location**: `backend/app/telegram/service.py` or similar

### Integration Verification

In `risk.py`:

```python
# Current code (already in place)
async def _handle_breach(self, db, user_id, settings, breach_reason, detailed_message):
    # ... pause logic ...

    # Telegram alert
    if self.telegram_service:
        try:
            await self.telegram_service.send_user_alert(
                user_id=user_id,
                title="⚠️ Copy-Trading Limit Breach",
                message=f"Trading paused: {detailed_message}",
                alert_type="risk_breach"  # For filtering in Telegram bot
            )
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}", exc_info=True)
            # Don't fail the pause if Telegram is unavailable
```

### Testing Telegram Integration

1. **Mock in unit tests** (already done):
   ```python
   # In test file
   @patch("backend.app.copytrading.risk.RiskEvaluator")
   async def test_telegram_alert_on_breach(mock_service):
       risk_evaluator.telegram_service = AsyncMock()
       # ... test code ...
       risk_evaluator.telegram_service.send_user_alert.assert_called()
   ```

2. **Test in development**:
   - Set `COPY_TELEGRAM_ALERTS_ENABLED=true` in .env
   - Set `TELEGRAM_BOT_TOKEN=your_token` (if needed)
   - Trigger a breach manually
   - Verify alert received in Telegram

3. **Verify fallback**:
   - Disable Telegram service
   - Trigger breach
   - Verify trading still paused even if alert fails

---

## 3. Audit Log Integration

### Current Status

Consent recording already calls: `self.audit_service.log_event()`

**File**: `backend/app/copytrading/disclosures.py`, line ~250 in `record_consent()`

### What to Verify

1. **Check if Audit service exists** (PR-008):
   ```bash
   find backend -name "*audit*" -type f | head -20
   ```

2. **Verify interface**:
   ```bash
   grep -r "log_event\|audit" backend/app --include="*.py" | grep "class\|def " | head -10
   ```

3. **Expected location**: `backend/app/core/audit.py` or `backend/app/audit/service.py`

### Integration Verification

In `disclosures.py`:

```python
# Current code (already in place)
async def record_consent(self, db, user_id, disclosure_version, ip_address, user_agent):
    # ... create UserConsent record ...

    # Audit logging (PR-008 integration)
    if self.audit_service:
        try:
            await self.audit_service.log_event(
                action="CONSENT_ACCEPTED",
                user_id=user_id,
                entity_type="disclosure",
                entity_id=disclosure_version,
                details={
                    "version": disclosure_version,
                    "ip_address": ip_address,
                    "user_agent": user_agent
                },
                immutable=True  # Cannot be modified
            )
        except Exception as e:
            logger.error(f"Failed to log consent audit: {e}", exc_info=True)
            # Still create consent even if audit fails
```

Similarly for breaches in `risk.py`:

```python
# In RiskEvaluator._handle_breach()
if self.audit_service:
    try:
        await self.audit_service.log_event(
            action="COPY_TRADING_PAUSED",
            user_id=user_id,
            entity_type="copy_trade_settings",
            entity_id=settings.id,
            details={
                "reason": breach_reason,
                "message": detailed_message,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    except Exception as e:
        logger.error(f"Failed to log breach audit: {e}", exc_info=True)
```

---

## 4. Quick Integration Checklist

### Prometheus Metrics

- [ ] Install prometheus-client: `pip install prometheus-client`
- [ ] Add `/metrics` endpoint to FastAPI app
- [ ] Import Counter in `risk.py`
- [ ] Create `copy_risk_block_total` counter
- [ ] Add metric increment in `_handle_breach()`
- [ ] Import Counter in `disclosures.py`
- [ ] Create `copy_consent_signed_total` counter
- [ ] Add metric increment in `record_consent()`
- [ ] Test metric generation: `curl http://localhost:8000/metrics | grep copy_`

### Telegram Alerts

- [ ] Locate Telegram service in codebase
- [ ] Verify `send_user_alert()` method signature
- [ ] Test alert in development environment
- [ ] Verify fallback if Telegram unavailable
- [ ] Check alert formatting is clear

### Audit Logging

- [ ] Locate Audit service in codebase
- [ ] Verify `log_event()` method signature
- [ ] Test audit trail creation for consent
- [ ] Test audit trail creation for breaches
- [ ] Verify immutability flag is set

---

## 5. Testing Integration

### Run Tests

```bash
cd backend
python -m pytest tests/test_pr_046_risk_compliance.py -v
```

### Coverage Report

```bash
python -m pytest tests/test_pr_046_risk_compliance.py --cov=app.copytrading --cov-report=html
open htmlcov/index.html
```

### Manual Testing Flow

```bash
# 1. Start backend
cd backend
python -m uvicorn app.main:app --reload

# 2. In another terminal, trigger a breach
curl -X POST http://localhost:8000/api/v1/copy/risk \
  -H "Authorization: Bearer YOUR_JWT" \
  -H "Content-Type: application/json" \
  -d '{"max_leverage": 50}'  # Violates max_leverage limit

# 3. Check metrics
curl http://localhost:8000/metrics | grep copy_risk_block

# 4. Check audit logs (if available)
sqlite3 backend/audit.db "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 5;"

# 5. Check Telegram (should receive alert)
# Look for alert message in Telegram app
```

---

## 6. Dependencies

### Required Packages

```bash
# Prometheus metrics
pip install prometheus-client

# Already in requirements.txt (verify)
pip install fastapi
pip install sqlalchemy
pip install pytest-asyncio
```

### Verify Installation

```bash
python -c "from prometheus_client import Counter; print('✓ Prometheus available')"
python -c "import telegram; print('✓ Telegram available')" || echo "⚠ Telegram not installed (but not required for alerts)"
```

---

## 7. Error Handling

All integrations should be non-blocking:

```python
# WRONG: Fails if Telegram unavailable
async def _handle_breach(...):
    await self.telegram_service.send_user_alert(...)  # Can raise exception

# CORRECT: Graceful degradation
async def _handle_breach(...):
    try:
        if self.telegram_service:
            await self.telegram_service.send_user_alert(...)
    except Exception as e:
        logger.error(f"Telegram alert failed: {e}")
        # Continue with pause, don't fail the whole operation
```

---

## 8. Monitoring

### Prometheus Dashboard Queries

After implementation, use these queries in Prometheus/Grafana:

```promql
# Rate of blocked trades over last hour
rate(copy_risk_block_total[1h])

# Breakdown by breach reason
sum(copy_risk_block_total) by (reason)

# Breakdown by user tier
sum(copy_risk_block_total) by (user_tier)

# Consent acceptance rate
rate(copy_consent_signed_total[1d])

# Most accepted disclosure version
topk(5, copy_consent_signed_total)
```

---

## 9. Files to Update

| File | What to Add | Lines |
|------|-----------|-------|
| `backend/app/copytrading/risk.py` | Import Counter, increment metric in `_handle_breach()` | +15 |
| `backend/app/copytrading/disclosures.py` | Import Counter, increment metric in `record_consent()` | +15 |
| `backend/main.py` | Add `/metrics` endpoint | +10 |
| `backend/requirements.txt` | Add prometheus-client (if not already) | +1 |

**Total**: ~40 lines to add

---

## 10. Success Criteria

After completing telemetry integration:

- ✅ `copy_risk_block_total` counter increments on breaches
- ✅ `copy_consent_signed_total` counter increments on consent
- ✅ `/metrics` endpoint returns Prometheus format
- ✅ Metrics visible via `curl http://localhost:8000/metrics`
- ✅ Telegram alerts sent on breaches (mocked in tests)
- ✅ Audit logs created for consents and breaches
- ✅ All integrations have error handling
- ✅ Tests pass with mocked services
- ✅ Production ready with graceful degradation

---

**Next Action**: Execute these integration steps, then run full test suite to verify 90%+ coverage.
