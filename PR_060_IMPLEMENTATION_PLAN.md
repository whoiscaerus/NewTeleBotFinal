# PR-060 IMPLEMENTATION PLAN: Messaging Bus & Templates

**Status**: 🔴 NOT IMPLEMENTED (0% complete)
**Date**: January 2025
**Dependencies**: PR-059 (User Preferences) ✅ COMPLETE

---

## 📋 OVERVIEW

**Goal**: Centralize multi-channel messaging infrastructure for:
- Alerts (price alerts, position failures, execution failures)
- Onboarding (welcome sequences, tutorials)
- Dunning (payment failures, subscription expiry)
- Education (course materials, daily insights)

**Architecture**:
```
┌─────────────┐
│   Feature   │ (alerts, onboarding, etc.)
└──────┬──────┘
       │
       ▼
┌─────────────────────────┐
│   Messaging Bus         │ Redis/Celery queue facade
│   - Campaign lane       │ (marketing, education)
│   - Transactional lane  │ (alerts, failures - URGENT)
└──────┬──────────────────┘
       │
       ▼
┌─────────────────────────┐
│   Template System       │
│   - Jinja2 (email)      │
│   - MarkdownV2 (Telegram)│
│   - JSON (PWA push)     │
└──────┬──────────────────┘
       │
       ├─► Email Sender (SMTP + retry)
       ├─► Telegram Sender (Bot API + rate limit)
       └─► Push Sender (PWA web-push)
```

**Integration Points**:
- **PR-059 (User Preferences)**: Filter notifications by user's enabled channels/instruments/alert types
- **PR-104 (Position Tracking)**: Send position failure alerts (entry failed, SL/TP auto-close failed)
- **PR-044 (Price Alerts)**: Send price alert notifications via messaging bus

---

## 🎯 ACCEPTANCE CRITERIA (from Master Doc)

### Core Messaging Infrastructure
1. ✅ **Message Queue Facade**: Redis/Celery queue with campaign + transactional lanes
2. ✅ **Template System**: Jinja2 email, MarkdownV2 Telegram, JSON push templates
3. ✅ **Senders**: Email (SMTP), Telegram (Bot API), Push (PWA web-push)
4. ✅ **API Endpoint**: POST /api/v1/messaging/test (owner-only) for testing

### Position Failure Templates (PR-104 Integration)
5. ✅ **Entry Failure Template**: ⚠️ Manual Action Required (trade entry failed)
   - Channels: Telegram, Email, Push
   - Fields: instrument, side, entry_price, volume, error_reason, approval_id
   - Email subject: "⚠️ Manual Trade Entry Required - {instrument}"

6. ✅ **Exit SL Template**: 🛑 URGENT Stop Loss hit but auto-close failed
   - Channels: Telegram, Email, Push
   - Fields: position_details, current_price, loss_amount, broker_ticket
   - Email subject: "🚨 URGENT: Manual Stop Loss Close Required"

7. ✅ **Exit TP Template**: ✅ Take Profit hit but auto-close failed
   - Channels: Telegram, Email, Push
   - Fields: position_details, current_price, profit_amount, broker_ticket
   - Email subject: "✅ Manual Take Profit Close Required"

### Security
8. ✅ Telegram bot tokens via environment variables (no hardcoded secrets)
9. ✅ SMTP sender address allowlist (prevent spoofing)
10. ✅ Owner-only access to test endpoint

### Telemetry
11. ✅ Prometheus metrics: `messages_sent_total{channel,type}`, `message_fail_total{reason}`
12. ✅ NEW metric: `position_failure_alerts_sent_total{type,channel}`

### Testing
13. ✅ Template render snapshot tests (all channels)
14. ✅ Channel fallback tests (email if push disabled)
15. ✅ Position failure templates render with all required fields
16. ✅ 100% business logic coverage (no shortcuts)

---

## 📁 FILE STRUCTURE

### Backend (7 files + tests)
```
backend/app/messaging/
  __init__.py                           # Package init
  bus.py                                # Queue facade (Redis/Celery)
  templates.py                          # Template system (Jinja2/MarkdownV2)
  routes.py                             # POST /messaging/test endpoint
  senders/
    __init__.py                         # Senders package init
    email.py                            # SMTP sender with retry
    telegram.py                         # Bot API sender with rate limit
    push.py                             # PWA web-push sender
  templates/
    __init__.py                         # Templates package init
    position_failures.py                # Entry/SL/TP failure templates
```

### Email Templates (3 HTML files)
```
email/templates/
  position_failure_entry.html           # Entry execution failed
  position_failure_sl.html              # Stop loss auto-close failed
  position_failure_tp.html              # Take profit auto-close failed
```

### Frontend (PWA integration)
```
frontend/miniapp/lib/push.ts            # registerServiceWorker(), subscribe()
```

### Tests (4 test files)
```
backend/tests/
  test_messaging_bus.py                 # Queue operations with fakeredis
  test_messaging_templates.py           # Template rendering (all channels)
  test_messaging_senders.py             # Email/Telegram/Push senders
  test_messaging_routes.py              # POST /messaging/test endpoint
```

### Documentation
```
PR_060_IMPLEMENTATION_PLAN.md           # This file
PR_060_IMPLEMENTATION_COMPLETE.md       # Created after implementation
```

---

## 🔨 IMPLEMENTATION PHASES

### Phase 1: Core Infrastructure (2-3 hours)

#### 1.1 Create Directory Structure
```powershell
New-Item -ItemType Directory -Force backend/app/messaging/senders
New-Item -ItemType Directory -Force backend/app/messaging/templates
New-Item -ItemType Directory -Force email/templates
```

#### 1.2 Messaging Bus (backend/app/messaging/bus.py)
**Purpose**: Queue facade for Redis/Celery with priority lanes

**Key Functions**:
```python
async def enqueue_message(
    user_id: str,
    channel: str,  # "email", "telegram", "push"
    template_name: str,
    template_vars: dict,
    priority: str = "transactional"  # or "campaign"
) -> str:  # Returns message_id
    """Enqueue message to Redis/Celery queue.

    Priority lanes:
    - transactional: Alerts, failures, critical notifications (immediate)
    - campaign: Marketing, education, non-urgent (batched)

    Returns message_id for tracking.
    """

async def enqueue_campaign(
    user_ids: list[str],
    channel: str,
    template_name: str,
    template_vars_fn: Callable[[str], dict],  # Function to get vars per user
    batch_size: int = 100
) -> dict:  # Returns {"queued": 1234, "failed": 5}
    """Enqueue campaign messages in batches."""
```

**Business Logic**:
- Transactional messages: Immediate delivery (position failures, price alerts)
- Campaign messages: Batched delivery (marketing, education)
- Retry logic: Exponential backoff (1s, 2s, 4s, 8s, 16s max)
- Dead letter queue: After 5 failures, move to DLQ for manual review
- Metrics: `messages_enqueued_total{priority,channel}`

**Dependencies**:
- Redis client (from core/cache.py)
- Celery app (from core/celery_app.py)
- Prometheus metrics (from observability/metrics.py)

---

#### 1.3 Template System (backend/app/messaging/templates.py)
**Purpose**: Render messages for all channels (email, Telegram, push)

**Key Functions**:
```python
def render_email(template_name: str, template_vars: dict) -> dict:
    """Render email template using Jinja2.

    Returns:
        {
            "subject": "Subject line",
            "html": "<html>...</html>",
            "text": "Plain text fallback"
        }
    """

def render_telegram(template_name: str, template_vars: dict) -> str:
    """Render Telegram message with MarkdownV2 escaping.

    MarkdownV2 special chars: _*[]()~`>#+-=|{}.!
    Must escape: \.  \*  \[  etc.
    """

def render_push(template_name: str, template_vars: dict) -> dict:
    """Render PWA push notification.

    Returns:
        {
            "title": "Notification title",
            "body": "Notification body",
            "icon": "/icon-192x192.png",
            "badge": "/badge-96x96.png",
            "data": {"url": "/dashboard/positions"}
        }
    """
```

**Business Logic**:
- Validate template_vars: All required fields present (raise ValueError if missing)
- MarkdownV2 escaping: Escape special chars for Telegram (prevent parse errors)
- Email: Generate both HTML and plain text versions
- Template caching: Load templates once, cache in memory

**Templates Location**:
- Email: `email/templates/{template_name}.html` (Jinja2)
- Telegram: Inline in templates.py (Python f-strings with escaping)
- Push: Inline in templates.py (JSON dict)

---

### Phase 2: Position Failure Templates (1 hour)

#### 2.1 Position Failures Module (backend/app/messaging/templates/position_failures.py)
**Purpose**: Templates for PR-104 position execution failures

**Template 1: Entry Execution Failed**
```python
ENTRY_FAILURE_EMAIL = {
    "subject": "⚠️ Manual Trade Entry Required - {instrument}",
    "required_vars": ["instrument", "side", "entry_price", "volume", "error_reason", "approval_id"],
}

ENTRY_FAILURE_TELEGRAM = """
⚠️ **Manual Action Required**

Your trade entry failed and requires manual execution:

**Instrument**: {instrument}
**Side**: {side_emoji} {side}
**Entry Price**: {entry_price}
**Volume**: {volume} lots
**Error**: {error_reason}

Please execute this trade manually in your broker platform.

Approval ID: `{approval_id}`
"""

ENTRY_FAILURE_PUSH = {
    "title": "⚠️ Manual Trade Entry Required",
    "body": "{instrument} {side} entry failed - manual execution needed",
    "data": {"url": "/dashboard/approvals/{approval_id}"}
}
```

**Template 2: Stop Loss Auto-Close Failed**
```python
SL_FAILURE_EMAIL = {
    "subject": "🚨 URGENT: Manual Stop Loss Close Required",
    "required_vars": ["instrument", "side", "entry_price", "current_price", "loss_amount", "broker_ticket"],
}

SL_FAILURE_TELEGRAM = """
🛑 **URGENT: Stop Loss Hit**

Your position hit stop loss but auto-close failed:

**Instrument**: {instrument}
**Side**: {side_emoji} {side}
**Entry**: {entry_price}
**Current**: {current_price}
**Loss**: {loss_amount} {currency}
**Broker Ticket**: {broker_ticket}

**ACTION REQUIRED**: Close this position manually NOW to prevent further losses.
"""
```

**Template 3: Take Profit Auto-Close Failed**
```python
TP_FAILURE_EMAIL = {
    "subject": "✅ Manual Take Profit Close Required",
    "required_vars": ["instrument", "side", "entry_price", "current_price", "profit_amount", "broker_ticket"],
}

TP_FAILURE_TELEGRAM = """
✅ **Take Profit Hit**

Your position hit take profit but auto-close failed:

**Instrument**: {instrument}
**Side**: {side_emoji} {side}
**Entry**: {entry_price}
**Current**: {current_price}
**Profit**: +{profit_amount} {currency}
**Broker Ticket**: {broker_ticket}

**ACTION REQUIRED**: Close this position manually to secure your profit.
"""
```

---

#### 2.2 HTML Email Templates (3 files)

**email/templates/position_failure_entry.html**:
```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Manual Trade Entry Required</title>
</head>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin-bottom: 20px;">
        <h2 style="margin: 0; color: #856404;">⚠️ Manual Action Required</h2>
    </div>

    <p>Your trade entry failed and requires manual execution:</p>

    <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
        <tr>
            <td style="padding: 10px; border-bottom: 1px solid #ddd; font-weight: bold;">Instrument</td>
            <td style="padding: 10px; border-bottom: 1px solid #ddd;">{{ instrument }}</td>
        </tr>
        <tr>
            <td style="padding: 10px; border-bottom: 1px solid #ddd; font-weight: bold;">Side</td>
            <td style="padding: 10px; border-bottom: 1px solid #ddd;">{{ side }}</td>
        </tr>
        <tr>
            <td style="padding: 10px; border-bottom: 1px solid #ddd; font-weight: bold;">Entry Price</td>
            <td style="padding: 10px; border-bottom: 1px solid #ddd;">{{ entry_price }}</td>
        </tr>
        <tr>
            <td style="padding: 10px; border-bottom: 1px solid #ddd; font-weight: bold;">Volume</td>
            <td style="padding: 10px; border-bottom: 1px solid #ddd;">{{ volume }} lots</td>
        </tr>
        <tr>
            <td style="padding: 10px; border-bottom: 1px solid #ddd; font-weight: bold;">Error</td>
            <td style="padding: 10px; border-bottom: 1px solid #ddd; color: #d32f2f;">{{ error_reason }}</td>
        </tr>
    </table>

    <p style="background: #f5f5f5; padding: 15px; border-radius: 5px;">
        Please execute this trade manually in your broker platform.
    </p>

    <p style="font-size: 12px; color: #666; margin-top: 30px;">
        Approval ID: {{ approval_id }}
    </p>
</body>
</html>
```

**(Similar structure for position_failure_sl.html and position_failure_tp.html - adjust colors, urgency, fields)**

---

### Phase 3: Message Senders (2-3 hours)

#### 3.1 Email Sender (backend/app/messaging/senders/email.py)
**Purpose**: SMTP sender with retry logic and bounce handling

**Key Functions**:
```python
async def send_email(
    to: str,
    subject: str,
    html: str,
    text: str,
    retry_count: int = 3
) -> dict:
    """Send email via SMTP with retry logic.

    Returns:
        {"status": "sent"|"failed", "message_id": "...", "error": "..."}
    """
```

**Business Logic**:
- SMTP config from environment: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`
- Retry logic: 3 attempts with exponential backoff (1s, 2s, 4s)
- Bounce handling: Catch `SMTPRecipientsRefused`, log + disable user's email notifications
- Rate limiting: Max 100 emails/minute (prevent IP blacklist)
- Metrics: `emails_sent_total`, `email_send_duration_seconds`, `email_failures_total{reason}`

---

#### 3.2 Telegram Sender (backend/app/messaging/senders/telegram.py)
**Purpose**: Bot API sender with rate limiting

**Key Functions**:
```python
async def send_telegram(
    chat_id: str,
    text: str,
    parse_mode: str = "MarkdownV2",
    retry_count: int = 3
) -> dict:
    """Send Telegram message via Bot API.

    Returns:
        {"status": "sent"|"failed", "message_id": "...", "error": "..."}
    """
```

**Business Logic**:
- Bot token from environment: `TELEGRAM_BOT_TOKEN`
- Rate limiting: Telegram API allows 30 messages/second (enforce 20/s for safety)
- Retry logic: 3 attempts with exponential backoff
- Error handling: Catch `TelegramError` (user blocked bot, chat not found)
- Metrics: `telegram_messages_sent_total`, `telegram_api_errors_total{error_type}`

---

#### 3.3 Push Sender (backend/app/messaging/senders/push.py)
**Purpose**: PWA push notifications via web-push library

**Key Functions**:
```python
async def send_push(
    subscription_info: dict,
    title: str,
    body: str,
    data: dict,
    retry_count: int = 2
) -> dict:
    """Send PWA push notification.

    Args:
        subscription_info: {"endpoint": "...", "keys": {"p256dh": "...", "auth": "..."}}

    Returns:
        {"status": "sent"|"failed", "error": "..."}
    """
```

**Business Logic**:
- VAPID keys from environment: `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_CLAIM_EMAIL`
- Subscription management: Delete expired subscriptions (410 Gone response)
- Fallback: If push fails, fallback to email/Telegram (per user preferences)
- Metrics: `push_notifications_sent_total`, `push_subscription_expired_total`

---

### Phase 4: API Routes (30 minutes)

#### 4.1 Routes (backend/app/messaging/routes.py)
**Purpose**: Test endpoint for owner to verify message delivery

**Endpoint**:
```python
@router.post("/api/v1/messaging/test", status_code=200)
async def test_message_delivery(
    request: TestMessageRequest,
    current_user: User = Depends(require_owner)
):
    """Test message delivery (owner-only).

    Request:
        {
            "user_id": "user-uuid",
            "channel": "email"|"telegram"|"push",
            "template_name": "position_failure_entry",
            "template_vars": {
                "instrument": "GOLD",
                "side": "buy",
                ...
            }
        }

    Response:
        {
            "status": "sent"|"failed",
            "message_id": "...",
            "delivery_time_ms": 123,
            "error": "..."
        }
    """
```

**Business Logic**:
- Auth: Owner-only (role check via `require_owner` dependency)
- Validation: Template name exists, required vars present
- Synchronous send: Wait for delivery confirmation (no queue)
- Logging: Log test message details + delivery status

---

### Phase 5: Comprehensive Testing (3-4 hours)

#### 5.1 Messaging Bus Tests (backend/tests/test_messaging_bus.py)
**Test Categories**:
1. **Queue Operations** (5 tests):
   - test_enqueue_transactional_message
   - test_enqueue_campaign_message
   - test_message_priority_order (transactional before campaign)
   - test_concurrent_enqueue (thread safety)
   - test_message_serialization (dict → JSON → dict)

2. **Retry Logic** (4 tests):
   - test_retry_on_failure (exponential backoff)
   - test_max_retries_exceeded (5 failures → DLQ)
   - test_dead_letter_queue
   - test_retry_timing (1s, 2s, 4s, 8s, 16s)

3. **Metrics** (2 tests):
   - test_metrics_messages_enqueued
   - test_metrics_messages_failed

**Coverage Target**: 100% (all queue operations, retry paths, DLQ)

---

#### 5.2 Template Tests (backend/tests/test_messaging_templates.py)
**Test Categories**:
1. **Email Templates** (6 tests):
   - test_render_email_entry_failure
   - test_render_email_sl_failure
   - test_render_email_tp_failure
   - test_email_missing_required_var (ValueError)
   - test_email_html_and_text_both_generated
   - test_email_subject_line_substitution

2. **Telegram Templates** (6 tests):
   - test_render_telegram_entry_failure
   - test_render_telegram_sl_failure
   - test_render_telegram_tp_failure
   - test_telegram_markdownv2_escaping (special chars)
   - test_telegram_missing_required_var (ValueError)
   - test_telegram_emoji_rendering

3. **Push Templates** (4 tests):
   - test_render_push_entry_failure
   - test_render_push_sl_failure
   - test_render_push_tp_failure
   - test_push_data_url_generation

4. **Snapshot Tests** (3 tests):
   - test_email_snapshot (compare HTML output)
   - test_telegram_snapshot (compare text output)
   - test_push_snapshot (compare JSON output)

**Coverage Target**: 100% (all templates, all channels, error paths)

---

#### 5.3 Sender Tests (backend/tests/test_messaging_senders.py)
**Test Categories**:
1. **Email Sender** (7 tests):
   - test_send_email_success
   - test_send_email_retry_on_timeout
   - test_send_email_max_retries_exceeded
   - test_send_email_bounce_handling (SMTPRecipientsRefused)
   - test_send_email_rate_limiting (100/minute max)
   - test_send_email_invalid_recipient
   - test_send_email_metrics

2. **Telegram Sender** (6 tests):
   - test_send_telegram_success
   - test_send_telegram_retry_on_api_error
   - test_send_telegram_user_blocked_bot
   - test_send_telegram_chat_not_found
   - test_send_telegram_rate_limiting (20/second)
   - test_send_telegram_metrics

3. **Push Sender** (6 tests):
   - test_send_push_success
   - test_send_push_subscription_expired (410 Gone)
   - test_send_push_invalid_subscription
   - test_send_push_fallback_to_email (on failure)
   - test_send_push_retry_logic
   - test_send_push_metrics

**Coverage Target**: 100% (success paths, all error scenarios, rate limiting, metrics)

---

#### 5.4 Routes Tests (backend/tests/test_messaging_routes.py)
**Test Categories**:
1. **Authentication** (3 tests):
   - test_test_endpoint_requires_auth (401 without token)
   - test_test_endpoint_owner_only (403 for regular user)
   - test_test_endpoint_owner_success

2. **Validation** (4 tests):
   - test_invalid_channel (400)
   - test_invalid_template_name (400)
   - test_missing_required_template_vars (400)
   - test_invalid_user_id (404)

3. **Delivery** (3 tests):
   - test_send_email_success (synchronous send)
   - test_send_telegram_success
   - test_send_push_success

4. **Metrics** (1 test):
   - test_test_endpoint_metrics (delivery_time_ms)

**Coverage Target**: 100% (auth, validation, delivery, metrics)

---

### Phase 6: Documentation & Commit (30 minutes)

#### 6.1 Create Implementation Complete Document
**File**: `PR_060_IMPLEMENTATION_COMPLETE.md`

**Contents**:
- ✅ Completed work summary (bus, templates, senders, routes)
- ✅ Test results (coverage %)
- ✅ Integration points (PR-059, PR-104)
- ✅ Business impact (centralized messaging, position failure alerts)
- ✅ Next steps (PR-061: Knowledge Base CMS)

#### 6.2 Commit & Push
```powershell
# Stage all files
git add backend/app/messaging/ email/templates/ backend/tests/test_messaging_*.py PR_060_*.md

# Commit
git commit -m "feat(messaging): Complete PR-060 messaging bus & templates with 100% coverage"

# Push
git push origin main
```

---

## 🔍 BUSINESS LOGIC TO VALIDATE

### Messaging Bus
1. ✅ Transactional messages delivered before campaign messages (priority queue)
2. ✅ Retry logic: Exponential backoff (1s, 2s, 4s, 8s, 16s max)
3. ✅ Dead letter queue: After 5 failures, message moved to DLQ
4. ✅ Concurrent enqueueing: Thread-safe queue operations
5. ✅ Message serialization: Dict → JSON → Dict preserves data

### Templates
1. ✅ Email: HTML + plain text versions generated
2. ✅ Telegram: MarkdownV2 special chars escaped (prevent parse errors)
3. ✅ Push: JSON format with title, body, icon, data
4. ✅ Required vars: ValueError if missing (fail fast)
5. ✅ Template caching: Load once, reuse in memory

### Position Failure Templates
1. ✅ Entry failure: All fields present (instrument, side, price, volume, error, approval_id)
2. ✅ SL failure: URGENT urgency, loss amount highlighted
3. ✅ TP failure: Success tone, profit amount highlighted
4. ✅ All channels: Email, Telegram, Push for each failure type

### Senders
1. ✅ Email: Retry on timeout, bounce handling (disable user's email)
2. ✅ Telegram: Rate limiting (20 msg/s), user blocked bot handling
3. ✅ Push: Subscription expiry (410 Gone → delete subscription), fallback to email
4. ✅ Metrics: All send operations logged (success/failure)

### API Routes
1. ✅ Owner-only access (403 for regular users)
2. ✅ Template validation (invalid template name → 400)
3. ✅ Required vars validation (missing vars → 400)
4. ✅ Synchronous delivery (wait for confirmation)

---

## 📊 TESTING STANDARDS (Per User Requirements)

1. **Use REAL implementations with fake backends**:
   - ✅ fakeredis for Redis/Celery queue
   - ✅ Mock SMTP server for email sender
   - ✅ Mock Telegram Bot API for Telegram sender
   - ✅ Mock web-push for PWA push sender

2. **Test REAL business logic, not mocks**:
   - ✅ Queue priority: Verify transactional messages processed first
   - ✅ Retry logic: Verify exponential backoff timing
   - ✅ Template rendering: Verify MarkdownV2 escaping, HTML generation
   - ✅ Rate limiting: Verify sender respects rate limits
   - ✅ Fallback channels: Verify push → email fallback on failure

3. **NO SKIPPING - fix root causes**:
   - ✅ If test fails, debug and fix (don't skip or comment out)
   - ✅ If coverage < 100%, add missing test cases
   - ✅ If error handling missing, add try/except + logging

4. **100% coverage**:
   - ✅ All success paths tested
   - ✅ All error paths tested (timeout, rate limit, invalid data)
   - ✅ All edge cases tested (empty lists, boundary conditions)

---

## 🔗 INTEGRATION POINTS

### PR-059 (User Preferences) - COMPLETE ✅
**Integration**: Filter notifications by user's preferences
```python
# Before sending message:
prefs = await get_user_preferences(db, user_id)

# Check if user has channel enabled
if channel == "email" and not prefs.notify_via_email:
    logger.info(f"User {user_id} has email notifications disabled")
    return {"status": "skipped", "reason": "channel_disabled"}

# Check if user has instrument enabled
if instrument not in prefs.instruments_enabled:
    logger.info(f"User {user_id} has {instrument} notifications disabled")
    return {"status": "skipped", "reason": "instrument_disabled"}

# Check if in quiet hours
if should_send_notification(prefs, alert_type, instrument, check_time=datetime.utcnow()):
    await enqueue_message(user_id, channel, template_name, template_vars)
else:
    logger.info(f"User {user_id} in quiet hours, message deferred")
```

### PR-104 (Position Tracking) - NOT IMPLEMENTED ❌
**Integration**: Send position failure alerts
```python
# When position entry fails (PR-104 Phase 3):
await enqueue_message(
    user_id=position.user_id,
    channel="telegram",  # or user's preferred channel
    template_name="position_failure_entry",
    template_vars={
        "instrument": position.instrument,
        "side": "buy" if position.side == 0 else "sell",
        "entry_price": position.entry_price,
        "volume": position.volume,
        "error_reason": "Broker rejected order: insufficient margin",
        "approval_id": position.approval_id,
    },
    priority="transactional"  # URGENT
)

# When SL auto-close fails (PR-104 Phase 4):
await enqueue_message(
    user_id=position.user_id,
    channel="telegram",
    template_name="position_failure_sl",
    template_vars={
        "instrument": position.instrument,
        "side": "buy" if position.side == 0 else "sell",
        "entry_price": position.entry_price,
        "current_price": position.current_price,
        "loss_amount": abs(position.current_pnl),
        "broker_ticket": position.broker_ticket,
    },
    priority="transactional"  # URGENT
)
```

### PR-044 (Price Alerts) - NOT VERIFIED ❌
**Integration**: Send price alert notifications
```python
# When price alert triggers:
await enqueue_message(
    user_id=alert.user_id,
    channel="telegram",
    template_name="price_alert_triggered",
    template_vars={
        "instrument": alert.instrument,
        "trigger_price": alert.trigger_price,
        "current_price": current_price,
        "condition": alert.condition,  # "above", "below"
    },
    priority="transactional"
)
```

---

## 📈 PROMETHEUS METRICS

### Core Metrics
```python
messages_enqueued_total = Counter(
    "messages_enqueued_total",
    "Total messages enqueued",
    ["priority", "channel"]  # transactional/campaign, email/telegram/push
)

messages_sent_total = Counter(
    "messages_sent_total",
    "Total messages sent successfully",
    ["channel", "type"]  # email/telegram/push, alert/campaign/etc
)

message_fail_total = Counter(
    "message_fail_total",
    "Total message send failures",
    ["reason", "channel"]  # timeout/bounce/rate_limit, email/telegram/push
)

message_send_duration_seconds = Histogram(
    "message_send_duration_seconds",
    "Message send duration",
    ["channel"]
)
```

### Position Failure Metrics (NEW)
```python
position_failure_alerts_sent_total = Counter(
    "position_failure_alerts_sent_total",
    "Total position failure alerts sent",
    ["type", "channel"]  # entry/sl/tp, email/telegram/push
)
```

---

## 🚀 NEXT STEPS AFTER PR-060

1. **PR-061**: Knowledge Base CMS (for Education Hub & AI support)
2. **PR-104**: Position Tracking (entry/SL/TP execution failure detection)
3. **PR-044**: Price Alerts (wire to messaging bus)

---

## 📝 NOTES

- **Frontend PWA push integration** (frontend/miniapp/lib/push.ts) deferred to later (focus on backend first)
- **SMTP config**: Use environment variables (never hardcode)
- **Telegram bot token**: Reuse from existing bot.py configuration
- **Rate limiting**: Essential to prevent API bans (Telegram: 20/s, Email: 100/min)
- **Fallback channels**: If primary channel fails, try alternatives (push → telegram → email)

---

**STATUS**: 🔴 READY TO IMPLEMENT (0% complete)
**NEXT ACTION**: Create directory structure, implement messaging bus (bus.py)
