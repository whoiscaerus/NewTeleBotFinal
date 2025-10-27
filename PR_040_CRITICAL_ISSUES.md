# PR-040: CRITICAL ISSUES & FIXES REQUIRED

**Status**: 🔴 **INCOMPLETE** - 3 blocking issues prevent production deployment

---

## ISSUE #1: MISSING TELEMETRY METRICS 🔴

**Severity**: BLOCKING
**Impact**: Can't monitor security attacks, can't measure idempotency effectiveness

### Problem
PR-040 spec requires:
```
* `billing_webhook_replay_block_total`, `idempotent_hits_total`
```

**Current State**: ❌ MISSING from `backend/app/observability/metrics.py`

Also: Code references undefined metric `billing_webhook_invalid_sig_total`:
```python
# File: backend/app/billing/webhooks.py, line 89
metrics.billing_webhook_invalid_sig_total.inc()  # ← CRASHES! Metric doesn't exist
```

### The Fix
**File**: `backend/app/observability/metrics.py`

**ADD to `MetricsCollector.__init__()`**:
```python
# PR-040: Webhook security metrics
self.billing_webhook_replay_block_total = Counter(
    "billing_webhook_replay_block_total",
    "Total webhook replay attacks blocked",
    registry=self.registry,
)

self.billing_webhook_invalid_sig_total = Counter(
    "billing_webhook_invalid_sig_total",
    "Total invalid webhook signatures received",
    registry=self.registry,
)

self.idempotent_hits_total = Counter(
    "idempotent_hits_total",
    "Total idempotent cache hits (replayed events)",
    ["operation"],  # operation: "webhook", "checkout", etc.
    registry=self.registry,
)
```

**THEN UPDATE**: `backend/app/billing/security.py`

Add metric recording:
```python
# In check_replay_cache() method, line 130:
if is_new:
    logger.info(f"New webhook event: {event_id}")
    from backend.app.observability.metrics import get_metrics
    metrics = get_metrics()
    # (Don't record for new events - only for replays)
    return True
else:
    logger.warning(f"Duplicate webhook event: {event_id}")
    metrics = get_metrics()
    metrics.idempotent_hits_total.labels(operation="webhook").inc()  # ← ADD THIS
    metrics.billing_webhook_replay_block_total.inc()  # ← ADD THIS
    return False
```

**Validation**:
- ✅ `pytest backend/tests/test_pr_040_security.py::TestTelemetry -v`
- ✅ Verify metrics appear in `/metrics` endpoint

---

## ISSUE #2: ENTITLEMENTS NOT ACTIVATED 🔴

**Severity**: BUSINESS-CRITICAL
**Impact**: Users pay for premium but don't get premium features

### Problem
When payment webhook succeeds, entitlements should activate. Currently it's a TODO placeholder:

**File**: `backend/app/billing/webhooks.py`, Lines 345-365

```python
async def _activate_entitlements(
    self,
    user_id: str,
    plan_code: str,
) -> None:
    """Activate entitlements for a user after successful payment."""
    try:
        # In a real implementation, this would:
        # 1. Look up entitlements for this plan_code (from PR-028)
        # 2. Create/update user entitlement records
        # 3. Set expiry dates based on subscription term
        # 4. Log to audit trail

        self.logger.info(
            "Activating entitlements",
            extra={"user_id": user_id, "plan_code": plan_code}
        )

        # Placeholder: In real implementation, call entitlement service
        # from backend.app.billing.entitlements import EntitlementService
        # entitlement_service = EntitlementService(db_session=self.db_session)
        # await entitlement_service.activate_plan(user_id, plan_code)
        # ↑ ONLY LOGGING, NO ACTUAL ACTIVATION!
```

### Current Flow
```
User pays for premium
  ↓
Stripe webhook: checkout.session.completed
  ↓
_activate_entitlements() called
  ↓
LOGS MESSAGE BUT DOES NOTHING
  ↓
❌ User still has FREE tier features
```

### The Fix
**Replace** the entire `_activate_entitlements()` method with working code:

```python
async def _activate_entitlements(
    self,
    user_id: str,
    plan_code: str,
) -> None:
    """Activate entitlements for a user after successful payment (PR-040).

    Maps plan_code to entitlements and stores in database.

    Example:
        >>> await handler._activate_entitlements("usr_123", "premium")
        # User now has premium entitlements
    """
    try:
        from backend.app.billing.models import UserEntitlement
        from uuid import uuid4
        from datetime import datetime

        # Map plan codes to entitlements
        entitlements_map = {
            "free": {
                "signals_enabled": True,
                "max_devices": 1,
                "analytics_level": "basic",
            },
            "premium": {
                "signals_enabled": True,
                "max_devices": 5,
                "analytics_level": "advanced",
                "copy_trading": False,
            },
            "vip": {
                "signals_enabled": True,
                "max_devices": 10,
                "analytics_level": "pro",
                "copy_trading": True,
            },
            "enterprise": {
                "signals_enabled": True,
                "max_devices": 999,
                "analytics_level": "enterprise",
                "copy_trading": True,
                "dedicated_support": True,
            },
        }

        # Get entitlements for this plan
        if plan_code not in entitlements_map:
            self.logger.error(
                f"Unknown plan code: {plan_code}",
                extra={"user_id": user_id}
            )
            raise ValueError(f"Unknown plan: {plan_code}")

        entitlements = entitlements_map[plan_code]

        # Check if user already has entitlements
        existing = await self.db_session.query(UserEntitlement).filter(
            UserEntitlement.user_id == user_id
        ).first()

        if existing:
            # Update existing record
            existing.entitlements = entitlements
            existing.updated_at = datetime.utcnow()
            self.logger.info(
                "Updated user entitlements",
                extra={"user_id": user_id, "plan": plan_code}
            )
        else:
            # Create new record
            ent = UserEntitlement(
                id=str(uuid4()),
                user_id=user_id,
                plan_code=plan_code,
                entitlements=entitlements,
                activated_at=datetime.utcnow(),
                created_at=datetime.utcnow(),
            )
            self.db_session.add(ent)
            self.logger.info(
                "Created user entitlements",
                extra={"user_id": user_id, "plan": plan_code}
            )

        # Commit the transaction
        await self.db_session.commit()

        self.logger.info(
            "Entitlements activated successfully",
            extra={
                "user_id": user_id,
                "plan_code": plan_code,
                "entitlements": list(entitlements.keys()),
            }
        )

    except ValueError as e:
        self.logger.error(f"Entitlement validation failed: {e}")
        raise
    except Exception as e:
        self.logger.error(
            f"Error activating entitlements: {e}",
            extra={"user_id": user_id, "plan_code": plan_code},
            exc_info=True
        )
        raise
```

**Validation**:
- ✅ Query database: `SELECT * FROM user_entitlements WHERE user_id='usr_123'`
- ✅ Verify entitlements object has correct features
- ✅ Test with webhook: Send payment webhook, check DB

---

## ISSUE #3: PAYMENT EVENTS NOT LOGGED 🔴

**Severity**: COMPLIANCE-CRITICAL
**Impact**: No audit trail for payments, fails compliance audits

### Problem
When payment succeeds, event should be logged to database. Currently it's a TODO placeholder:

**File**: `backend/app/billing/webhooks.py`, Lines 390-437

```python
async def _log_payment_event(
    self,
    # ... parameters ...
) -> None:
    """Log payment event to database for audit trail."""
    try:
        # Placeholder: In real implementation, insert into payment_events table
        # from backend.app.billing.models import PaymentEvent
        # event = PaymentEvent(...)
        # ↑ ONLY PLACEHOLDER, NOTHING LOGGED!

        self.logger.debug(
            "Payment event logged",  # ← LOGS MESSAGE BUT NOT ACTUAL EVENT!
            extra={...}
        )

    except Exception as e:
        self.logger.error(...)
```

### Current Flow
```
Stripe webhook received
  ↓
_log_payment_event() called
  ↓
LOGS MESSAGE TO APP LOG
  ↓
❌ NO ENTRY IN payment_events TABLE
  ↓
Cannot audit who paid what and when
```

### The Fix
**Replace** the entire `_log_payment_event()` method with working code:

```python
async def _log_payment_event(
    self,
    user_id: Optional[str],
    event_type: str,
    plan_code: Optional[str] = None,
    customer_id: Optional[str] = None,
    invoice_id: Optional[str] = None,
    subscription_id: Optional[str] = None,
    amount: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Log payment event to database for audit trail (PR-040).

    Creates audit log entry for all payment events.

    Args:
        user_id: User making the payment
        event_type: "checkout_completed", "invoice_payment_succeeded", etc.
        plan_code: Plan purchased (e.g., "premium")
        customer_id: Stripe customer ID
        invoice_id: Stripe invoice ID
        subscription_id: Stripe subscription ID
        amount: Amount in cents
        metadata: Additional data to store

    Example:
        >>> await handler._log_payment_event(
        ...     user_id="usr_123",
        ...     event_type="checkout_completed",
        ...     plan_code="premium",
        ...     amount=2999,  # $29.99
        ... )
    """
    try:
        from backend.app.billing.models import PaymentEvent
        from backend.app.audit.models import AuditLog
        from uuid import uuid4
        from datetime import datetime

        # Create payment event record
        event = PaymentEvent(
            id=str(uuid4()),
            user_id=user_id,
            event_type=event_type,
            plan_code=plan_code,
            customer_id=customer_id,
            invoice_id=invoice_id,
            subscription_id=subscription_id,
            amount=amount,  # Store in cents for precision
            metadata=metadata or {},
            created_at=datetime.utcnow(),
        )

        # Add to session
        self.db_session.add(event)

        # Also log to audit log for compliance
        if user_id:
            audit = AuditLog(
                id=str(uuid4()),
                user_id=user_id,
                action="payment.event",
                resource_type="payment",
                resource_id=event.id,
                details={
                    "event_type": event_type,
                    "plan_code": plan_code,
                    "amount": amount,
                },
                created_at=datetime.utcnow(),
            )
            self.db_session.add(audit)

        # Commit both
        await self.db_session.commit()

        self.logger.info(
            "Payment event logged to database",
            extra={
                "event_id": event.id,
                "event_type": event_type,
                "user_id": user_id,
                "amount": amount,
            }
        )

    except Exception as e:
        self.logger.error(
            "Error logging payment event",
            extra={
                "event_type": event_type,
                "user_id": user_id,
                "error": str(e),
            },
            exc_info=True
        )
        # Don't raise - logging errors shouldn't crash webhook processing
        # But alert ops that logging failed (important for compliance!)
        try:
            from backend.app.ops.alerts import send_owner_alert
            await send_owner_alert(
                f"Payment event logging failed: {event_type} for user {user_id}"
            )
        except:
            pass  # If alerts also fail, just log
```

**Validation**:
- ✅ Query database: `SELECT * FROM payment_events ORDER BY created_at DESC LIMIT 5`
- ✅ Verify event_type, user_id, amount are correct
- ✅ Test with webhook: Send payment webhook, check audit log

---

## ISSUE #4: WRONG FILE LOCATION 🟡

**Severity**: MEDIUM
**Impact**: Generic idempotency decorator not reusable, code duplication

### Problem
PR-040 spec says:
```
backend/app/core/idempotency.py    # Generic decorator
```

**Current State**:
```
backend/app/billing/idempotency.py # ← WRONG LOCATION
```

**Issue**: Generic decorator should be in `/core/` for use by all modules, not buried in `/billing/`.

### Current Architecture
```
backend/app/billing/security.py
  └─ WebhookReplayProtection         # Uses Redis
  └─ WebhookSecurityValidator        # Coordinates validation

backend/app/billing/idempotency.py
  └─ IdempotencyHandler              # NEVER USED! (duplicate logic in security.py)
  └─ WebhookReplayLog
```

### Fix: Move & Consolidate
1. **Move** `idempotency.py`:
   ```
   backend/app/billing/idempotency.py → backend/app/core/idempotency.py
   ```

2. **Update import** in `security.py`:
   ```python
   # OLD:
   # (duplicate code in this file)

   # NEW:
   from backend.app.core.idempotency import IdempotencyHandler
   ```

3. **Consolidate** `WebhookReplayProtection` to use `IdempotencyHandler`:
   ```python
   class WebhookReplayProtection:
       def __init__(self, redis_client: redis.Redis):
           self.handler = IdempotencyHandler(redis_client, ttl_seconds=600)

       def check_replay_cache(self, event_id: str) -> bool:
           return self.handler.get_cached(event_id) is None
   ```

**Result**:
- ✅ Generic decorator available for all modules
- ✅ No code duplication
- ✅ Easier maintenance

---

## ISSUE #5: INCOMPLETE TESTS 🟡

**Severity**: HIGH
**Impact**: Can't verify webhook endpoint security

### Problem
3 integration tests are empty stubs:

**File**: `backend/tests/test_pr_040_security.py`, Lines 333-370

```python
@pytest.mark.asyncio
async def test_webhook_endpoint_requires_valid_signature(
    self, client: AsyncClient
):
    """Test webhook endpoint rejects invalid signatures."""
    pass  # ← NOT IMPLEMENTED

@pytest.mark.asyncio
async def test_webhook_endpoint_rejects_replay_attacks(
    self, client: AsyncClient, db_session: AsyncSession
):
    """Test webhook endpoint prevents replay attacks."""
    pass  # ← NOT IMPLEMENTED

@pytest.mark.asyncio
async def test_webhook_endpoint_returns_rfc7807_on_error(
    self, client: AsyncClient
):
    """Test webhook error responses use RFC7807 format."""
    pass  # ← NOT IMPLEMENTED
```

### The Fix
**Replace with real implementations**:

```python
@pytest.mark.asyncio
async def test_webhook_endpoint_requires_valid_signature(
    self, client: AsyncClient
):
    """Test webhook endpoint rejects invalid signatures."""
    # Send webhook with invalid signature
    response = await client.post(
        "/api/v1/billing/webhooks",
        content=b'{"id": "evt_test", "type": "charge.succeeded"}',
        headers={
            "Stripe-Signature": "t=1234567890,v1=invalid_hash_value"
        }
    )

    # Should reject with 403 Forbidden
    assert response.status_code == 403
    assert "signature" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_webhook_endpoint_rejects_replay_attacks(
    self, client: AsyncClient, db_session: AsyncSession
):
    """Test webhook endpoint prevents replay attacks."""
    import hmac
    import hashlib
    import time
    import json

    webhook_secret = "whsec_test"
    payload = json.dumps({
        "id": "evt_replay_test",
        "type": "charge.succeeded",
        "data": {"object": {"amount": 2999}}
    }).encode()

    timestamp = str(int(time.time()))
    signed_content = f"{timestamp}.{payload.decode()}"
    signature_hash = hmac.new(
        webhook_secret.encode(),
        signed_content.encode(),
        hashlib.sha256
    ).hexdigest()

    signature = f"t={timestamp},v1={signature_hash}"

    # First webhook: should succeed
    response1 = await client.post(
        "/api/v1/billing/webhooks",
        content=payload,
        headers={"Stripe-Signature": signature}
    )
    assert response1.status_code == 200
    assert response1.json()["status"] == "success"

    # Second webhook (identical): should return cached result
    response2 = await client.post(
        "/api/v1/billing/webhooks",
        content=payload,
        headers={"Stripe-Signature": signature}
    )
    assert response2.status_code == 200
    # Should return same result (from cache)
    assert response2.json() == response1.json()


@pytest.mark.asyncio
async def test_webhook_endpoint_returns_rfc7807_on_error(
    self, client: AsyncClient
):
    """Test webhook error responses use RFC7807 format."""
    response = await client.post(
        "/api/v1/billing/webhooks",
        content=b'invalid json',
        headers={
            "Stripe-Signature": "t=1234567890,v1=invalid"
        }
    )

    assert response.status_code >= 400

    # RFC7807 format:
    # {
    #   "type": "https://api.example.com/errors/invalid-webhook",
    #   "title": "Invalid Webhook",
    #   "status": 400,
    #   "detail": "Invalid webhook payload",
    #   "instance": "/api/v1/billing/webhooks"
    # }
    error = response.json()
    assert "type" in error
    assert "title" in error
    assert "status" in error
    assert "detail" in error
    assert error["status"] >= 400
```

**Validation**:
- ✅ `pytest backend/tests/test_pr_040_security.py::TestWebhookEndpointSecurity -v`

---

## SUMMARY OF FIXES

| Issue | File | Lines | Fix Type | Time |
|-------|------|-------|----------|------|
| Missing metrics | metrics.py | +20 | ADD | 15 min |
| Entitlements TODO | webhooks.py | 345-365 | REPLACE | 30 min |
| Events logging TODO | webhooks.py | 390-437 | REPLACE | 20 min |
| Wrong file location | idempotency.py | — | MOVE | 20 min |
| Incomplete tests | test_pr_040_security.py | 333-370 | REPLACE | 45 min |
| **TOTAL** | | | | **2h** |

---

## DEPLOYMENT CHECKLIST

Before marking PR-040 complete:

- [ ] Fix Issue #1: Add missing metrics (15 min)
- [ ] Fix Issue #2: Implement entitlements activation (30 min)
- [ ] Fix Issue #3: Implement payment event logging (20 min)
- [ ] Fix Issue #4: Move idempotency.py to /core/ (20 min)
- [ ] Fix Issue #5: Implement integration tests (45 min)
- [ ] Run full test suite: `pytest backend/tests/test_pr_040_security.py -v`
- [ ] Verify coverage: `pytest --cov=backend/app/billing`
- [ ] Manual test: Send test webhook, verify all steps work
- [ ] Verify no regressions in other tests

**Estimated Total Time**: ~2.5 hours
