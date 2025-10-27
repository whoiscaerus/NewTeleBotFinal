# PR-026 & PR-027 Audit - Complete Findings Reference

**Audit Date**: October 27, 2025
**Status**: ❌ INCOMPLETE - Significant Work Remaining
**Severity**: 🔴 CRITICAL - Do Not Deploy

---

## Quick Reference Table

| Component | Expected | Actual | % Complete | Status |
|-----------|----------|--------|-----------|--------|
| **PR-026 Files** | | | | |
| webhook.py | 150 lines | 138 lines | 92% | ⚠️ Partial - Missing IP/secret |
| router.py | 200 lines | 193 lines | 96% | 🔴 STUB - No business logic |
| handlers/distribution.py | 100 lines | 0 lines | 0% | ❌ MISSING |
| handlers/guides.py | 80 lines | 0 lines | 0% | ❌ MISSING |
| handlers/marketing.py | 100 lines | 0 lines | 0% | ❌ MISSING |
| verify.py | 50 lines | 0 lines | 0% | ❌ MISSING |
| **PR-027 Files** | | | | |
| commands.py | 100 lines | 0 lines | 0% | ❌ MISSING |
| rbac.py | 80 lines | 0 lines | 0% | ❌ MISSING |
| **Tests** | | | | |
| test_telegram_*.py | 500+ lines | 0 lines | 0% | ❌ MISSING |
| **Total** | 1,160+ lines | ~330 lines | 28% | 🔴 INCOMPLETE |

---

## Missing Files Detail

### Priority 1: RBAC Security (PR-027)

#### File: `backend/app/telegram/rbac.py` (80 lines needed)

**Purpose**: Enforce role-based access control

**Must Implement**:
```python
async def ensure_admin(user_id: str, db: AsyncSession) -> bool:
    """Check if user has admin role."""
    # Query user from DB
    # Return True if role == "admin"

async def ensure_owner(user_id: str, db: AsyncSession) -> bool:
    """Check if user has owner role."""
    # Query user from DB
    # Return True if role == "owner"

async def require_role(required_role: str):
    """FastAPI dependency."""
    # Raise 403 if user doesn't have role

class RBACError(Exception):
    """Permission denied."""
```

**Usage**:
```python
@router.post("/admin/broadcast")
async def broadcast(
    request: BroadcastRequest,
    user_id: str = Depends(require_role("owner"))
):
    # User must be owner to reach here
```

#### File: `backend/app/telegram/commands.py` (100 lines needed)

**Purpose**: Central command registry with RBAC

**Must Implement**:
```python
class CommandHandler:
    """Single command definition."""
    command: str
    handler: Callable
    required_role: str | None  # None = public
    description: str

class CommandRegistry:
    """Central registry of all Telegram commands."""
    commands = {
        "start": CommandHandler(
            command="/start",
            handler=handle_start,
            required_role=None,
            description="Start the bot"
        ),
        "admin": CommandHandler(
            command="/admin",
            handler=handle_admin,
            required_role="admin",
            description="Admin panel"
        ),
        # ... all commands
    }

    @classmethod
    def get_help_for_user(cls, user_role: str) -> str:
        """Generate context-aware help text."""
        # Filter commands by user role
        # Return formatted help text
```

---

### Priority 2: Security Validation (PR-026)

#### File: `backend/app/telegram/verify.py` (50 lines needed)

**Purpose**: Validate webhook requests (IP allowlist, secret header)

**Must Implement**:
```python
def parse_cidrs(cidr_list: str) -> list[IPv4Network]:
    """Parse CIDR strings into network objects."""
    # Example: "192.168.1.0/24,10.0.0.0/8"
    # Return list of IPv4Network objects

def is_ip_allowed(client_ip: str, allowed_cidrs: list) -> bool:
    """Check if client IP is in allowed CIDRs."""
    ip = IPv4Address(client_ip)
    for cidr in allowed_cidrs:
        if ip in cidr:
            return True
    return False

def verify_secret_header(header: str | None, expected: str) -> bool:
    """Verify optional X-Telegram-Webhook-Secret header."""
    if not header:
        return True  # Optional
    return hmac.compare_digest(header, expected)
```

**Integration into webhook.py**:
```python
@router.post("/api/v1/telegram/webhook")
async def telegram_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    # 1. Verify IP is allowed
    client_ip = request.client.host
    allowed_cidrs = parse_cidrs(settings.TELEGRAM_IP_ALLOWLIST)
    if not is_ip_allowed(client_ip, allowed_cidrs):
        logger.warning(f"Webhook from unauthorized IP: {client_ip}")
        return {"ok": True}  # Don't reveal

    # 2. Verify secret header
    secret = request.headers.get("X-Telegram-Webhook-Secret")
    if not verify_secret_header(secret, settings.TELEGRAM_WEBHOOK_SECRET):
        logger.warning(f"Invalid secret header")
        return {"ok": True}

    # ... rest of webhook processing
```

---

### Priority 3: Handler Implementations (PR-026)

#### File: `backend/app/telegram/handlers/distribution.py` (100 lines needed)

**Purpose**: Route content to channels by keyword

**Must Implement**:
```python
async def handle_distribution_command(message: TelegramMessage, db: AsyncSession) -> None:
    """Route content to appropriate channels based on keywords."""
    # Parse message text for keywords
    # Get mapping of keywords -> channel IDs
    # Send message to each channel
    # Log distribution
    # Notify admin

# Example mapping:
CHANNEL_MAP = {
    "gold": -1001234567890,
    "crypto": -1001234567891,
    "sp500": -1001234567892,
}

async def extract_keywords(text: str) -> list[str]:
    """Extract keywords from message."""

async def get_target_channels(keywords: list[str]) -> list[int]:
    """Get channel IDs for keywords."""

async def send_to_channels(text: str, channels: list[int]) -> None:
    """Send message to multiple channels."""
```

#### File: `backend/app/telegram/handlers/guides.py` (80 lines needed)

**Purpose**: Educational content distribution

**Must Implement**:
```python
async def handle_guides_command(message: TelegramMessage, db: AsyncSession) -> None:
    """Send educational guides via inline keyboard."""
    # Create inline keyboard with guide links
    # Send to user
    # Log interaction

# Example structure:
GUIDES = {
    "beginner": {
        "title": "Beginner's Guide",
        "url": "https://guides.example.com/beginner",
        "description": "Start here"
    },
    "trading": {
        "title": "Trading Basics",
        "url": "https://guides.example.com/trading",
        "description": "Learn trading fundamentals"
    },
}

async def build_guides_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard with guide links."""

async def schedule_periodic_posts() -> None:
    """Post guides periodically."""
```

#### File: `backend/app/telegram/handlers/marketing.py` (100 lines needed)

**Purpose**: Marketing broadcasts and CTAs

**Must Implement**:
```python
async def handle_broadcast_command(message: TelegramMessage, db: AsyncSession) -> None:
    """Send marketing broadcast to channel."""
    # Check admin role
    # Parse message for broadcast text
    # Send to target channels
    # Track metrics
    # Log action

async def schedule_marketing_posts() -> None:
    """Send scheduled promotions."""
    # Every 4 hours: send promo
    # Include CTA button to main bot

async def format_promo_message() -> str:
    """Format marketing message with MarkdownV2."""

async def track_promo_click(user_id: int) -> None:
    """Track when user clicks promo CTA."""
```

---

## Handler Stubs That Need Real Logic

### Current Implementation (All Stubs)

**Problem**: Every handler in `router.py` just does logging:

```python
async def handle_start(self, message: TelegramMessage) -> None:
    """Handle /start command."""
    logger.info(f"Start command from user {message.from_user.id}")
    # ❌ PLACEHOLDER - would send welcome message
```

### Required Implementation

Each handler needs:

1. **Database query** (get user data)
```python
user = await db.query(User).filter(User.telegram_id == user_id).first()
if not user:
    # Send "not registered" message
    return
```

2. **Business logic** (based on user data/tier)
```python
if user.tier == "premium":
    options = PREMIUM_OPTIONS
else:
    options = FREE_OPTIONS
```

3. **Message construction** (formatted for Telegram)
```python
text = "Welcome back!\n\n"
text += f"Your tier: {user.tier}\n"
```

4. **Telegram API call** (send message)
```python
await send_telegram_message(
    chat_id=message.chat.id,
    text=text,
    reply_markup=create_inline_keyboard(options)
)
```

5. **Error handling** (graceful failures)
```python
try:
    # ... logic ...
except DBError as e:
    logger.error(f"Database error: {e}")
    await send_telegram_message(chat_id, "Database error occurred")
```

6. **Logging** (for monitoring)
```python
logger.info(f"Start command processed", extra={
    "user_id": user_id,
    "tier": user.tier,
    "timestamp": datetime.utcnow()
})
```

---

## Test Coverage Gaps

### Tests Needed for PR-026

**1. test_telegram_webhook.py** (signature, IP, secret)
```python
async def test_webhook_valid_signature() -> None:
    """Valid HMAC signature accepted."""

async def test_webhook_invalid_signature() -> None:
    """Invalid HMAC signature rejected."""

async def test_webhook_missing_signature() -> None:
    """Missing signature handled."""

async def test_webhook_ip_allowed() -> None:
    """IP in allowlist accepted."""

async def test_webhook_ip_denied() -> None:
    """IP not in allowlist rejected."""

async def test_webhook_secret_header_valid() -> None:
    """Valid secret header accepted."""

async def test_webhook_secret_header_invalid() -> None:
    """Invalid secret header rejected."""

async def test_webhook_event_logged() -> None:
    """Event persisted to database."""

async def test_webhook_command_routing() -> None:
    """Message routed to correct handler."""

async def test_webhook_callback_routing() -> None:
    """Callback routed to correct handler."""
```

### Tests Needed for PR-027

**2. test_telegram_rbac.py** (permission enforcement)
```python
async def test_admin_command_requires_admin_role() -> None:
    """Non-admin blocked from admin commands."""

async def test_owner_command_requires_owner_role() -> None:
    """Non-owner blocked from owner commands."""

async def test_admin_command_allowed_for_admin() -> None:
    """Admin can access admin commands."""

async def test_public_commands_allowed_for_all() -> None:
    """Public commands accessible to everyone."""

async def test_help_shows_role_aware_commands() -> None:
    """Help text filtered by user role."""

async def test_command_registry_completeness() -> None:
    """All commands present in registry."""

async def test_permission_denied_response() -> None:
    """403 returned for unauthorized access."""
```

### Tests Needed for Handlers

**3. test_telegram_handlers.py** (business logic)
```python
async def test_handle_start_sends_welcome_message() -> None:
    """Start command sends welcome."""

async def test_handle_help_returns_command_list() -> None:
    """Help returns available commands."""

async def test_handle_shop_returns_products() -> None:
    """Shop returns available products."""

async def test_handle_shop_filters_by_tier() -> None:
    """Shop shows only products for user's tier."""

async def test_handle_affiliate_returns_stats() -> None:
    """Affiliate shows user's affiliate stats."""

async def test_handle_stats_returns_user_stats() -> None:
    """Stats returns user's trading statistics."""

async def test_unknown_command_shows_help() -> None:
    """Unknown command shows help text."""

async def test_callback_button_click_handled() -> None:
    """Button clicks processed correctly."""

async def test_error_in_handler_sends_error_message() -> None:
    """Errors reported to user gracefully."""

async def test_database_error_handled() -> None:
    """Database errors don't crash handler."""
```

---

## Implementation Checklist

### Phase 1: Create Missing Security Files (4h)

- [ ] Create `backend/app/telegram/verify.py` (IP allowlist, secret validation)
- [ ] Integrate `verify.py` into `webhook.py`
- [ ] Add IP allowlist env var: `TELEGRAM_IP_ALLOWLIST`
- [ ] Add secret header env var: `TELEGRAM_WEBHOOK_SECRET`
- [ ] Test IP allowlist logic
- [ ] Test secret header logic

### Phase 2: Implement RBAC (3h)

- [ ] Create `backend/app/telegram/rbac.py` (ensure_admin, ensure_owner, require_role)
- [ ] Create `backend/app/telegram/commands.py` (command registry)
- [ ] Add role-aware help generation
- [ ] Test admin permission enforcement
- [ ] Test owner permission enforcement
- [ ] Test help text generation

### Phase 3: Complete Handler Logic (6h)

- [ ] Replace `handle_start()` stub with real implementation
- [ ] Replace `handle_help()` stub with real implementation
- [ ] Replace `handle_shop()` stub with real implementation
- [ ] Replace `handle_affiliate()` stub with real implementation
- [ ] Replace `handle_stats()` stub with real implementation
- [ ] Replace `handle_unknown()` stub with real implementation
- [ ] Create `handlers/distribution.py` (content routing)
- [ ] Create `handlers/guides.py` (guide keyboards)
- [ ] Create `handlers/marketing.py` (broadcasts)
- [ ] Add rate limiting from PR-005
- [ ] Add metrics collection

### Phase 4: Comprehensive Testing (4h)

- [ ] Create `test_telegram_webhook.py` (10+ tests)
- [ ] Create `test_telegram_rbac.py` (8+ tests)
- [ ] Create `test_telegram_handlers.py` (15+ tests)
- [ ] Create integration tests
- [ ] Achieve 90%+ coverage
- [ ] All tests passing locally
- [ ] CI/CD pipeline passing
- [ ] No regressions detected

---

## Success Criteria

To consider PR-026 & PR-027 **COMPLETE**:

✅ **Files**:
- [ ] All 8 files created and filled (no stubs)
- [ ] 100% of expected code written
- [ ] No TODOs or FIXMEs

✅ **Functionality**:
- [ ] All handlers have real business logic
- [ ] RBAC enforcement working
- [ ] IP allowlist working
- [ ] Secret header validation working
- [ ] Rate limiting applied

✅ **Testing**:
- [ ] 90%+ test coverage achieved
- [ ] All 50+ test cases passing
- [ ] No failing tests
- [ ] CI/CD pipeline passing

✅ **Security**:
- [ ] RBAC enforced on admin/owner commands
- [ ] IP allowlist checked on every request
- [ ] Secret header validated
- [ ] Rate limiting active
- [ ] Input validation on all fields

✅ **Acceptance Criteria**:
- [ ] All PR-026 criteria met
- [ ] All PR-027 criteria met
- [ ] Can set webhook and receive updates
- [ ] Commands route correctly
- [ ] Permissions enforced

---

## Deploy Checklist (After Completion)

- [ ] All tests passing locally
- [ ] Coverage ≥90%
- [ ] Code formatted (Black)
- [ ] Type checking passes (mypy)
- [ ] Linting passes (ruff)
- [ ] Security scan passes (bandit)
- [ ] No regressions in existing code
- [ ] CI/CD pipeline passing on GitHub
- [ ] Code review approved (2+ approvers)
- [ ] Ready for production deployment

---

**Report Generated**: October 27, 2025
**Status**: Ready for implementation
**Estimated Time to Completion**: 17 hours
**Next Step**: Begin Phase 1 file creation
