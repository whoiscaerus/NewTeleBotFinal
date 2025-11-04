# PR-032 Complete Analysis & Implementation Plan

**Date**: 2025-11-04  
**Status**: AUDIT COMPLETE - GAPS IDENTIFIED  

---

## ✅ WHAT EXISTS

### 1. Database Models (`backend/app/marketing/models.py`)
- ✅ `MarketingClick` model - fully implemented
- ✅ Fields: id, user_id, promo_id, cta_text, chat_id, message_id, click_data, clicked_at
- ✅ Indexes on user_id, promo_id, composite (user_id, promo_id)
- ✅ Proper docstrings, type hints

### 2. Scheduler (`backend/app/marketing/scheduler.py`)
- ✅ `MarketingScheduler` class with APScheduler integration
- ✅ Interval-based scheduling (default 4 hours)
- ✅ Promo rotation through DEFAULT_PROMOS array
- ✅ Async posting to multiple chats
- ✅ Error handling per-chat (continues on failure)
- ✅ Telemetry hook: `get_metrics().record_marketing_post()`
- ✅ Optional DB logging

### 3. Clicks Store (`backend/app/marketing/clicks_store.py`)
- ✅ `ClicksStore` class with async methods
- ✅ `log_click()` - creates MarketingClick record, increments telemetry
- ✅ `get_user_clicks()` - fetches user's clicks
- ✅ `get_promo_clicks()` - fetches promo's clicks
- ✅ Error handling and logging

### 4. Telegram Handler (`backend/app/telegram/handlers/marketing.py`)
- ✅ `MarketingHandler` class
- ✅ Broadcast creation, querying, delivery
- ✅ Keyboard generation with CTAs
- ✅ Partial implementation found

### 5. Alembic Migration
- ✅ `012_add_marketing_clicks.py` exists

---

## ❌ WHAT'S MISSING

### 1. **MarketingPromoLog Model** (CRITICAL)
**Current State**: Referenced in `scheduler.py` line 276 but NOT defined in `models.py`
```python
# scheduler.py calls this but model doesn't exist:
from backend.app.marketing.models import MarketingPromoLog
```
**What needs**: Model to track when promos are posted, success/fail counts
**Fields**:
- id (uuid pk)
- promo_id (fk to promo or string id)
- posted_to (count)
- failed (count)
- created_at (timestamp)
- details (json for per-chat status)

### 2. **Messages Module** (IMPORTANT)
**Missing file**: `backend/app/marketing/messages.py`
**What's needed**:
- SAFE MarkdownV2 formatting utilities
- Promo templates
- Text escaping for special chars (`_*[]()~\`>#+-=|{}.!`)
- Helper to build properly formatted promo messages
- VALIDATION that text is MarkdownV2-safe

### 3. **NO TEST COVERAGE** (CRITICAL)
**Current**: 0 tests for PR-032
**Needs**: 
- Scheduler start/stop behavior tests
- Promo posting tests (success/failure)
- Click logging tests
- Deduplication tests
- Error handling tests
- Edge cases (empty chat list, invalid promos, DB errors)
- Telemetry validation
- MarkdownV2 safety validation
- Concurrency tests (multiple posts at once)

### 4. **Telemetry Hooks** (IMPORTANT)
**Current Issue**: 
- `scheduler.py` calls `get_metrics().record_marketing_post()`
- `clicks_store.py` calls `get_metrics().marketing_clicks_total.labels(...).inc()`
**Need to verify**: These methods exist in `backend/app/observability/metrics.py`

---

## BUSINESS LOGIC CHECKLIST

### Scheduling (PR Requirement: "schedule repeats every 4 hours")
- [ ] Scheduler starts without event loop error
- [ ] Job runs at configured interval (default 4 hours)
- [ ] Multiple posts to different chats (parallelizable)
- [ ] Promo rotation (cycles through array)
- [ ] Can be stopped and restarted cleanly
- [ ] Status queries work (next_run_time, last_run_time)
- [ ] Errors don't crash the job

### Click Persistence (PR Requirement: "click logged")
- [ ] Click recorded to database
- [ ] User ID persisted
- [ ] Promo ID persisted
- [ ] CTA text persisted
- [ ] Timestamp correct (UTC)
- [ ] Metadata optional but accepted
- [ ] Duplicate clicks allowed (not deduplicated per-session)
- [ ] Query by user returns all their clicks
- [ ] Query by promo returns all clicks for that promo

### Message Safety (PR Requirement: "MarkdownV2 promo")
- [ ] No unescaped special characters
- [ ] Title escaped safely
- [ ] Description escaped safely
- [ ] CTA text escaped safely
- [ ] Telegram accepts the formatted message
- [ ] Special chars like `*` `_` `[` `]` properly handled

### Error Handling & Resilience
- [ ] One chat posting failure doesn't block others
- [ ] DB connection error logged, job continues
- [ ] Telegram API error caught and logged
- [ ] Invalid promo ID handled gracefully
- [ ] Empty chat list handled (no crashes)
- [ ] Scheduler stops cleanly without errors

### Telemetry
- [ ] `marketing_posts_total` incremented per successful post
- [ ] `marketing_clicks_total` incremented per click
- [ ] Promo ID included in telemetry labels

---

## CRITICAL ISSUES TO FIX

### Issue 1: MarketingPromoLog Model Missing
**Impact**: BLOCKING - Code references non-existent class  
**Fix**: Add model to models.py

### Issue 2: Messages Module Missing  
**Impact**: HIGH - No MarkdownV2 safety guarantees  
**Fix**: Create messages.py with utilities

### Issue 3: Zero Test Coverage
**Impact**: CRITICAL - No validation that business logic works  
**Fix**: Create comprehensive test suite (100 tests minimum)

### Issue 4: No MarkdownV2 Validation Tests
**Impact**: HIGH - Could send malformed Telegram messages  
**Fix**: Add tests that verify escape sequences

### Issue 5: Scheduler Async Issues in Tests
**Impact**: HIGH - APScheduler needs event loop  
**Fix**: Tests must handle asyncio context properly

---

## IMPLEMENTATION ORDER

1. **Add MarketingPromoLog model** (5 min)
2. **Create messages.py** (15 min)
3. **Create comprehensive test suite** (2-3 hours)
4. **Run tests and validate 100% pass + coverage** (30 min)
5. **Verify telemetry hooks exist** (10 min)

---

## ACCEPTANCE CRITERIA

- [x] All 4 main files exist (models.py, scheduler.py, clicks_store.py, handler.py)
- [ ] MarketingPromoLog model defined
- [ ] messages.py created with MarkdownV2 utilities
- [ ] 100+ tests covering all business logic
- [ ] 90%+ code coverage achieved
- [ ] All tests pass locally
- [ ] Telemetry hooks verified
- [ ] No integration test skips
- [ ] Edge cases handled
- [ ] Error paths tested
- [ ] Concurrent scheduling validated
