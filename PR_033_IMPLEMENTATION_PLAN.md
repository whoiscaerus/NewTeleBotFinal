# PR-033 Implementation Plan: Marketing & Broadcasting

**Status**: Ready to Implement
**Date**: October 25, 2025
**Estimated Time**: 1.5 hours
**Priority**: HIGH (Enables PR-034, required for engagement metrics)

---

## Executive Summary

Implement the content distribution and marketing layer for Telegram bot, enabling promotional broadcasts, call-to-action tracking, and engagement analytics.

## Specification

### Goal
Enable platform operators to send targeted broadcasts with tracked CTAs (Call-To-Action buttons) to user cohorts, measure engagement through click analytics.

### Files to Create

```
backend/app/marketing/
├── __init__.py
├── broadcasts.py          # Broadcast model & logic
├── templates.py           # Message templates (Jinja2)
└── cta.py                 # CTA button tracking

backend/app/telegram/handlers/
├── marketing.py           # Telegram handler for marketing commands
└── __init__.py (update)

backend/tests/
├── test_marketing.py      # Marketing service tests
├── test_cta_tracking.py   # CTA analytics tests
└── test_marketing_handlers.py  # Telegram handler tests

backend/alembic/versions/
└── XXXX_add_broadcasts_and_cta.py  # Database migrations
```

### Dependencies

✅ **SATISFIED**:
- PR-001 (CI/CD): Build system ready
- PR-002 (Settings): Config system in place
- PR-004 (Auth/RBAC): User identification
- PR-010 (Database): Alembic migrations available
- PR-027 (Telegram webhook): Router available
- PR-028 (Catalog): Entitlements available

### Database Schema

#### broadcasts table
```sql
CREATE TABLE broadcasts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(100) NOT NULL,
    template_id UUID NOT NULL REFERENCES broadcast_templates(id),
    cohort_query JSONB NOT NULL,  -- Filter logic (user_tier, region, etc.)
    message_template TEXT NOT NULL,
    status INTEGER NOT NULL DEFAULT 0,  -- 0=draft, 1=scheduled, 2=sent, 3=failed
    scheduled_at TIMESTAMP,
    sent_at TIMESTAMP,
    stats JSONB,  -- {total_recipients, clicks, conversions}
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE broadcast_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL UNIQUE,
    content TEXT NOT NULL,  -- Jinja2 template
    cta_buttons JSONB NOT NULL,  -- [{label, action, url}, ...]
    category VARCHAR(50),  -- promotional, educational, urgent, etc.
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE cta_clicks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    broadcast_id UUID NOT NULL REFERENCES broadcasts(id),
    cta_button_id UUID NOT NULL,
    clicked_at TIMESTAMP NOT NULL DEFAULT now(),
    user_agent TEXT,
    ip_address VARCHAR(45),
    converted BOOLEAN DEFAULT false,  -- Did they complete action?
    UNIQUE(user_id, broadcast_id, cta_button_id)
);

CREATE INDEX ix_broadcasts_status_scheduled ON broadcasts(status, scheduled_at);
CREATE INDEX ix_broadcasts_created_by ON broadcasts(created_by);
CREATE INDEX ix_cta_clicks_user_broadcast ON cta_clicks(user_id, broadcast_id);
```

### Data Models

#### Broadcasts Model (`broadcasts.py`)
```python
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, UUID, JSONB, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.core.db import Base

class Broadcast(Base):
    """Marketing broadcast to user cohorts."""
    __tablename__ = "broadcasts"

    id = Column(UUID, primary_key=True, default=uuid4)
    title = Column(String(100), nullable=False)
    template_id = Column(UUID, ForeignKey("broadcast_templates.id"))
    cohort_query = Column(JSONB, nullable=False)  # {"user_tier": "premium", "region": "EU"}
    message_template = Column(String, nullable=False)  # Rendered template
    status = Column(Integer, default=0)  # 0=draft, 1=scheduled, 2=sent, 3=failed
    scheduled_at = Column(DateTime)
    sent_at = Column(DateTime)
    stats = Column(JSONB)  # {total_recipients, clicks, conversions, ctr}
    created_by = Column(UUID, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Properties
    @property
    def is_sent(self) -> bool:
        return self.status == 2

    @property
    def ctr(self) -> float:
        """Click-through rate"""
        if not self.stats or self.stats.get("total_recipients", 0) == 0:
            return 0.0
        return self.stats["clicks"] / self.stats["total_recipients"]

class BroadcastTemplate(Base):
    """Reusable broadcast message templates."""
    __tablename__ = "broadcast_templates"

    id = Column(UUID, primary_key=True, default=uuid4)
    name = Column(String(100), unique=True, nullable=False)
    content = Column(String, nullable=False)  # Jinja2 template
    cta_buttons = Column(JSONB)  # [{label, action, url}, ...]
    category = Column(String(50))  # promotional, educational, urgent
    created_at = Column(DateTime, default=datetime.utcnow)

class CTAClick(Base):
    """Track CTA button clicks for analytics."""
    __tablename__ = "cta_clicks"

    id = Column(UUID, primary_key=True, default=uuid4)
    user_id = Column(UUID, ForeignKey("users.id"), nullable=False)
    broadcast_id = Column(UUID, ForeignKey("broadcasts.id"), nullable=False)
    cta_button_id = Column(UUID, nullable=False)
    clicked_at = Column(DateTime, default=datetime.utcnow)
    user_agent = Column(String)
    ip_address = Column(String(45))
    converted = Column(Boolean, default=False)
```

#### Service Layer (`broadcasts.py` service methods)
```python
class BroadcastService:
    """Manage marketing broadcasts and analytics."""

    async def create_broadcast(
        self,
        db: AsyncSession,
        title: str,
        template_id: UUID,
        cohort_query: dict,
        scheduled_at: Optional[datetime] = None
    ) -> Broadcast:
        """Create new broadcast (draft status)."""

    async def get_recipients(
        self,
        db: AsyncSession,
        cohort_query: dict
    ) -> List[User]:
        """Query users matching cohort criteria."""
        # cohort_query: {"user_tier": "premium", "region": "EU", "no_trades_7d": False}

    async def send_broadcast(
        self,
        db: AsyncSession,
        broadcast_id: UUID,
        telegram_client: TelegramClient
    ) -> dict:
        """Send broadcast to all matching recipients."""

    async def track_cta_click(
        self,
        db: AsyncSession,
        user_id: UUID,
        broadcast_id: UUID,
        cta_button_id: UUID,
        user_agent: str,
        ip_address: str
    ) -> CTAClick:
        """Record CTA click for analytics."""

    async def get_broadcast_analytics(
        self,
        db: AsyncSession,
        broadcast_id: UUID
    ) -> dict:
        """Get engagement stats for broadcast."""
        # Returns: {total_recipients, clicks, conversions, ctr, conversion_rate}
```

#### Telegram Handler (`handlers/marketing.py`)
```python
class MarketingHandler:
    """Telegram commands for marketing/promotions."""

    async def handle_broadcast_command(message: Message) -> None:
        """Admin: /broadcast command → broadcast form"""

    async def handle_cta_button(query: CallbackQuery) -> None:
        """Track CTA click → log analytics → redirect to action"""
```

### API Endpoints (if needed)

```
POST   /api/v1/admin/broadcasts              Create broadcast
GET    /api/v1/admin/broadcasts              List broadcasts
PUT    /api/v1/admin/broadcasts/{id}         Update broadcast (draft only)
POST   /api/v1/admin/broadcasts/{id}/send    Send broadcast now
GET    /api/v1/admin/broadcasts/{id}/stats   Get broadcast analytics
GET    /api/v1/admin/broadcasts/analytics    Dashboard with all broadcasts
```

### Telegram Integration

#### /broadcast Command Flow
```
Admin: /broadcast
Bot: "Choose template: [Promotional] [Educational] [Urgent]"
Admin: Selects template
Bot: Shows template preview with CTA buttons
Admin: "Edit message?" / "Send to cohort?"
Bot: "Which cohort? [All] [Premium] [EU] [Custom]"
Admin: Selects cohort
Bot: "Ready to send to 1,234 users. Confirm? [Yes] [Cancel]"
Admin: Confirms
Bot: Sends to all users, records broadcast_id
```

#### CTA Button Click Flow
```
User: Clicks "Shop Now" button in message
Telegram: Calls webhook with callback_data="{broadcast_id}:{cta_button_id}"
Backend:
  1. Record CTAClick(user_id, broadcast_id, cta_button_id)
  2. Answer callback (removes "loading" state)
  3. Send redirect message or perform action
```

---

## Acceptance Criteria

✅ **Create Broadcasts**
- Admin can select template + message
- Admin can filter cohort (all users, premium tier, region, etc.)
- Admin can schedule or send immediately
- Test: `test_create_broadcast_with_template`

✅ **Track CTAs**
- Each CTA button click recorded in database
- Click includes user_id, broadcast_id, timestamp
- Duplicate clicks prevented (unique constraint)
- Test: `test_track_cta_click`

✅ **Analytics**
- Dashboard shows: total sent, total clicks, CTR (click-through rate)
- Per-broadcast analytics available
- Test: `test_broadcast_analytics_calculation`

✅ **Telegram Integration**
- /broadcast command routes correctly
- CTA buttons send webhook callbacks
- Callbacks parsed and clicks recorded
- Test: `test_telegram_cta_button_click`

✅ **Error Handling**
- Invalid cohort query rejected
- Template not found → error
- Send to 0 users → error
- Test: `test_broadcast_invalid_cohort`

✅ **Test Coverage**
- ≥80% coverage on marketing module
- All happy paths + error cases tested
- Database integration tests with real AsyncSession

---

## Implementation Checklist

### Phase 1: Database & Models (20 min)
- [ ] Create Alembic migration (broadcasts, broadcast_templates, cta_clicks tables)
- [ ] Create SQLAlchemy models (Broadcast, BroadcastTemplate, CTAClick)
- [ ] Add indexes for queries (status, cohort filters)
- [ ] Test: Migration up/down succeeds

### Phase 2: Service Layer (30 min)
- [ ] BroadcastService: create_broadcast()
- [ ] BroadcastService: get_recipients() (query by cohort)
- [ ] BroadcastService: send_broadcast() (iterate users, send Telegram messages)
- [ ] BroadcastService: track_cta_click()
- [ ] BroadcastService: get_broadcast_analytics()
- [ ] Add proper logging + error handling
- [ ] Test: All service methods with mocked DB

### Phase 3: Telegram Handler (20 min)
- [ ] Implement /broadcast command handler
- [ ] Implement CTA button click handler
- [ ] Parse callback_data correctly
- [ ] Send messages via Telegram API
- [ ] Test: Handler routes work

### Phase 4: Tests (30 min)
- [ ] Create test fixtures (db_session, sample templates, users)
- [ ] Test broadcast creation
- [ ] Test recipient querying (cohort filtering)
- [ ] Test CTA click tracking
- [ ] Test analytics calculation
- [ ] Test error scenarios
- [ ] Run coverage: target ≥80%

### Phase 5: Quality & Commit (10 min)
- [ ] Black formatting
- [ ] Ruff linting
- [ ] No TODOs in code
- [ ] Git commit + push

---

## Test Cases

### `test_marketing.py`
```python
async def test_create_broadcast_draft():
    """Create broadcast in draft status."""

async def test_get_recipients_by_cohort():
    """Query recipients matching cohort criteria."""

async def test_get_recipients_empty():
    """No recipients for cohort → return empty list."""

async def test_send_broadcast_to_recipients():
    """Send broadcast updates status to sent."""

async def test_broadcast_stats_calculation():
    """Analytics shows correct CTR and counts."""

async def test_broadcast_invalid_cohort():
    """Invalid cohort_query rejected."""
```

### `test_cta_tracking.py`
```python
async def test_track_cta_click():
    """CTA click recorded with all metadata."""

async def test_track_cta_duplicate_prevented():
    """Duplicate click for same user+broadcast+button prevented."""

async def test_cta_click_with_conversion():
    """Mark CTA click as converted."""
```

### `test_marketing_handlers.py`
```python
async def test_broadcast_command_shows_templates():
    """Admin /broadcast → show template choices."""

async def test_cta_button_click_recorded():
    """User clicks CTA → webhook received → click recorded."""

async def test_cta_button_click_missing_broadcast():
    """Invalid broadcast_id in callback → error handled."""
```

---

## Time Breakdown

| Task | Duration |
|------|----------|
| Database schema + migration | 20 min |
| SQLAlchemy models | 10 min |
| Service layer (core logic) | 30 min |
| Telegram handler integration | 20 min |
| Tests (fixtures + 8 test cases) | 30 min |
| Quality gates (Black, Ruff, lint) | 10 min |
| **TOTAL** | **~120 min (1.5 hours)** |

---

## Dependencies to Verify

Before starting:

```bash
✅ Backend app/core/ configured
✅ Telegram router available (PR-027)
✅ Database migrations running
✅ Entitlements model exists (PR-028)
✅ User model has tier field
```

---

## Success Criteria

✅ **Code Quality**
- Black formatted
- Ruff: 0 issues
- Type hints complete
- Docstrings on all functions
- No TODOs

✅ **Tests**
- 8+ test cases
- ≥80% coverage (target for marketing module)
- 100% pass rate
- All edge cases covered

✅ **Functionality**
- Broadcast creation works (draft status)
- Cohort filtering works (premium, region, etc.)
- CTA click tracking works
- Analytics calculation correct
- Telegram commands work

✅ **Documentation**
- Inline code comments
- Docstring examples
- Database schema documented
- Telegram flow documented

---

## Next PR After This

**PR-034: Guides & Onboarding** (1 hour)
- Onboarding guides, /help command, FAQ linking
- Dependencies: PR-027 (Telegram router)
- Builds on: PR-033 (marketing templates)

---

**Status**: Ready for implementation
**Complexity**: Medium (service layer + Telegram integration)
**Risk**: Low (isolated feature, no payment flow)
**Blocker**: None - all dependencies satisfied
