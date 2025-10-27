# PR-034 PHASE 2: QUICK START REFERENCE

**Phase**: Core Payment Handler Implementation
**Duration**: 30 minutes
**Files to Create**: 1 main file + updates
**Lines of Code**: 500-700 estimated

---

## 🎯 PHASE 2 OBJECTIVES

✅ Create TelegramPaymentHandler class
✅ Implement send_invoice() method
✅ Implement validate_pre_checkout() method
✅ Implement handle_successful_payment() method
✅ Add Prometheus telemetry

---

## 📁 FILES TO CREATE/MODIFY

### NEW: `backend/app/telegram/payments.py`

```python
# Core structure needed:

from typing import Optional, Dict
from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram, Gauge
import structlog
from telegram import Bot

# ===== TELEMETRY METRICS =====
telegram_payments_total = Counter(
    'telegram_payments_total',
    'Total Telegram payment attempts',
    ['result', 'plan_code']  # result: sent, success, failed, cancelled
)

telegram_payment_value_total = Counter(
    'telegram_payment_value_total',
    'Total value of Telegram payments (pence)',
    ['plan_code', 'currency']
)

telegram_payment_processing_seconds = Histogram(
    'telegram_payment_processing_seconds',
    'Payment processing latency',
    buckets=[0.5, 1.0, 2.0, 5.0]
)

telegram_precheck_total = Counter(
    'telegram_precheck_total',
    'Pre-checkout queries',
    ['result']  # result: ok, rejected
)

# ===== SCHEMAS =====

class SendInvoiceRequest(BaseModel):
    plan_code: str = Field(..., regex="^[a-z_0-9]+$")

class SendInvoiceResponse(BaseModel):
    invoice_id: str
    plan_code: str
    amount_cents: int
    currency: str

class ValidatePreCheckoutRequest(BaseModel):
    pre_checkout_query_id: str
    from_id: int
    currency: str
    total_amount: int
    invoice_payload: str

class ValidatePreCheckoutResponse(BaseModel):
    ok: bool
    error_message: Optional[str] = None

# ===== MAIN HANDLER CLASS =====

class TelegramPaymentHandler:
    """Handle Telegram native payments."""

    def __init__(self, bot_token: str, price_map: Dict[str, int]):
        """
        Initialize handler.

        Args:
            bot_token: Telegram bot token
            price_map: {plan_code: cents} e.g. {"gold_1m": 2500}
        """
        self.bot = Bot(token=bot_token)
        self.price_map = price_map
        self.logger = structlog.get_logger(__name__)

    async def send_invoice(
        self,
        user_id: str,
        telegram_user_id: int,
        telegram_chat_id: int,
        plan_code: str
    ) -> SendInvoiceResponse:
        """
        Send invoice to user.

        Args:
            user_id: Database user ID (UUID)
            telegram_user_id: Telegram user ID (BIGINT)
            telegram_chat_id: Telegram chat ID (BIGINT)
            plan_code: Plan code (e.g., 'gold_1m')

        Returns:
            SendInvoiceResponse with invoice_id

        Raises:
            ValueError: If plan_code invalid or user already premium
            RateLimitError: If user exceeded rate limit

        Example:
            >>> response = await handler.send_invoice(
            ...     user_id="123e4567",
            ...     telegram_user_id=111222333,
            ...     telegram_chat_id=111222333,
            ...     plan_code="gold_1m"
            ... )
            >>> print(response.invoice_id)
        """
        # TODO: Implement
        pass

    async def validate_pre_checkout(
        self,
        pre_checkout_query_id: str,
        from_id: int,
        total_amount: int,
        invoice_payload: str
    ) -> ValidatePreCheckoutResponse:
        """
        Validate pre-checkout query before charging.

        Args:
            pre_checkout_query_id: Telegram query ID
            from_id: Telegram user ID
            total_amount: Amount in cents (pence)
            invoice_payload: Original payload from send_invoice

        Returns:
            ValidatePreCheckoutResponse with ok/error

        Example:
            >>> response = await handler.validate_pre_checkout(
            ...     pre_checkout_query_id="query_123",
            ...     from_id=111222333,
            ...     total_amount=2500,
            ...     invoice_payload="gold_1m_1698432000"
            ... )
            >>> assert response.ok is True
        """
        # TODO: Implement
        pass

    async def handle_successful_payment(
        self,
        telegram_user_id: int,
        telegram_payment_charge_id: str,
        invoice_payload: str,
        amount_cents: int,
        currency: str
    ) -> bool:
        """
        Process successful payment webhook.

        Args:
            telegram_user_id: Telegram user ID
            telegram_payment_charge_id: Unique charge ID from Telegram
            invoice_payload: Original payload (contains plan_code)
            amount_cents: Amount charged (pence)
            currency: Currency code (GBP)

        Returns:
            True if success, False if failed

        Example:
            >>> success = await handler.handle_successful_payment(
            ...     telegram_user_id=111222333,
            ...     telegram_payment_charge_id="charge_abc123",
            ...     invoice_payload="gold_1m_1698432000",
            ...     amount_cents=2500,
            ...     currency="GBP"
            ... )
            >>> assert success is True
        """
        # TODO: Implement
        pass
```

---

## 🔑 KEY IMPLEMENTATION DETAILS

### 1. Rate Limiting (send_invoice)
```python
# Pseudo-code (use Redis)
key = f"telegram_invoice:{user_id}:rate_limit"
current = redis.incr(key)
if current == 1:
    redis.expire(key, 60)  # 1-minute window
if current > 5:
    raise RateLimitError("Max 5 attempts per minute")
```

### 2. Invoice Payload Format
```
Format: "{plan_code}_{timestamp}"
Example: "gold_1m_1698432000"
Purpose: Link payment back to original plan choice
```

### 3. Validation Chain
```python
# In validate_pre_checkout():
1. Parse invoice_payload → extract plan_code + timestamp
2. Validate timestamp < 1 hour old (prevent replay)
3. Validate plan_code exists in price_map
4. Validate amount_cents == price_map[plan_code]
5. Return ok=True or ok=False + error reason
```

### 4. Successful Payment Processing
```python
# In handle_successful_payment():
1. Parse invoice_payload → plan_code
2. Create TelegramPaymentEvent record (INSERT)
3. Call activate_entitlement(user_id, plan_code)
4. Record metrics
5. Send confirmation message
6. Return True if all succeeded
```

### 5. Telemetry Recording
```python
# After successful send:
telegram_payments_total.labels(result="sent", plan_code="gold_1m").inc()

# After successful charge:
telegram_payments_total.labels(result="success", plan_code="gold_1m").inc()
telegram_payment_value_total.labels(plan_code="gold_1m", currency="GBP").inc(2500)
```

---

## 📝 IMPLEMENTATION CHECKLIST

- [ ] Create `backend/app/telegram/payments.py`
- [ ] Define all Prometheus metrics (5 total)
- [ ] Define Pydantic schemas (request/response)
- [ ] Create TelegramPaymentHandler class
- [ ] Implement send_invoice()
  - [ ] Validate plan_code
  - [ ] Check user not already premium
  - [ ] Rate limiting (5/min)
  - [ ] Call Telegram API
  - [ ] Log + telemetry
- [ ] Implement validate_pre_checkout()
  - [ ] Parse invoice_payload
  - [ ] Timestamp validation (< 1 hour)
  - [ ] Amount reconciliation with price_map
  - [ ] Telemetry
- [ ] Implement handle_successful_payment()
  - [ ] Create DB record (TelegramPaymentEvent)
  - [ ] Call activate_entitlement()
  - [ ] Send confirmation message
  - [ ] Update metrics
- [ ] Add comprehensive docstrings + examples
- [ ] Add type hints to all functions
- [ ] Add error handling on all external calls
- [ ] Add structured logging with context

---

## ⚠️ DEPENDENCIES TO IMPORT

```python
# Telegram
from telegram import Bot, TelegramError

# Database
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.db import get_db

# Entitlements (PR-028)
from backend.app.billing.entitlements import activate_entitlement

# Prices (PR-028)
from backend.app.billing.catalog import get_plan_price

# Models
from backend.app.telegram.models import TelegramPaymentEvent
from backend.app.users.models import User

# Utilities
from backend.app.core.logging import get_logger
from prometheus_client import Counter, Histogram
import structlog
from datetime import datetime, timedelta
```

---

## 🧪 FIRST TEST CASE (To Validate Implementation)

```python
@pytest.mark.asyncio
async def test_send_invoice_valid_plan():
    """Test sending invoice for valid plan."""

    # Setup
    handler = TelegramPaymentHandler(
        bot_token="123:ABC",
        price_map={"gold_1m": 2500}
    )

    # Execute
    response = await handler.send_invoice(
        user_id="user_123",
        telegram_user_id=111222333,
        telegram_chat_id=111222333,
        plan_code="gold_1m"
    )

    # Assert
    assert response.invoice_id is not None
    assert response.plan_code == "gold_1m"
    assert response.amount_cents == 2500
    assert response.currency == "GBP"
```

---

## 📊 SUCCESS CRITERIA FOR PHASE 2

✅ All 3 methods implemented (send_invoice, validate_pre_checkout, handle_successful_payment)
✅ 500-700 lines of code
✅ All functions have docstrings + type hints
✅ All external calls have error handling
✅ Telemetry integrated (5 metrics)
✅ Structured logging with context
✅ Zero TODOs in code
✅ No hardcoded values (use config/env)

---

## ⏱️ TIMING BREAKDOWN

- File creation + imports: 5 min
- Schemas definition: 5 min
- send_invoice() implementation: 10 min
- validate_pre_checkout() implementation: 5 min
- handle_successful_payment() implementation: 5 min
- **Total: 30 minutes**

---

## 📌 NOTES

- Keep methods focused (single responsibility)
- All external API calls should have retry logic + error handling
- Rate limiting uses Redis (ensure Redis available)
- Logging should include: user_id, plan_code, amount_cents, telegram_user_id
- No secrets/tokens should be logged
- Sensitive amounts: log only for audit trail, no debug logs

---

**Next: Begin implementation immediately**
