# PR-091 Implementation Plan: Forecast / AI Analyst Mode

## Overview
Daily AI-written "Market Outlook" with volatility zones, correlated risk view, and **owner-controlled testing toggle** (user requirement: test for weeks before client release).

## Dependencies ✅ VERIFIED
- ✅ **PR-052**: Equity/Drawdown Engine (`backend/app/analytics/equity.py` exists)
- ✅ **PR-053**: Performance Metrics (`backend/app/analytics/metrics.py` exists)
- ✅ **PR-062**: AI Assistant Infrastructure (`backend/app/ai/assistant.py` exists)

## File Structure

### Backend
```
backend/app/ai/analyst.py                      # NEW: build_outlook() function
backend/app/core/settings.py                   # MODIFY: Add AIAnalystSettings
backend/schedulers/daily_outlook.py            # NEW: Cron job for daily generation
backend/app/messaging/templates.py             # MODIFY: Add outlook templates
backend/app/observability/metrics.py           # MODIFY: Add ai_outlook_published_total
backend/alembic/versions/091_analyst_toggle.py # NEW: feature_flags table
backend/tests/test_ai_analyst.py               # NEW: Comprehensive tests
```

### Frontend
```
frontend/web/app/outlook/page.tsx              # NEW: Web outlook viewer
frontend/miniapp/app/outlook/page.tsx          # NEW: Mini App outlook viewer (optional)
```

### CLI
```
backend/cli/ai.py                              # NEW: Toggle commands
```

## Database Schema

### Feature Flags Table
```sql
CREATE TABLE feature_flags (
    name VARCHAR(100) PRIMARY KEY,
    enabled BOOLEAN DEFAULT FALSE,
    owner_only BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(36)  -- User ID who toggled
);

-- Insert default row for AI Analyst
INSERT INTO feature_flags (name, enabled, owner_only)
VALUES ('ai_analyst', FALSE, TRUE);
```

## API Endpoints

### Owner Control
- `POST /api/v1/ai/analyst/toggle` (admin only)
  - Body: `{"enabled": true, "owner_only": false}`
  - Returns: `{"status": "enabled", "owner_only": true}`

### Outlook Viewer
- `GET /api/v1/ai/outlook/latest` (auth required, respects owner_only flag)
  - Returns: `OutlookReport` with narrative, volatility zones, correlations

- `GET /api/v1/ai/outlook/history?limit=30` (auth required)
  - Returns: Array of past outlooks

## Implementation Phases

### Phase 1: Owner Toggle Infrastructure (30 min)
1. Create `feature_flags` table migration
2. Add `AIAnalystSettings` to settings.py
3. Create `FeatureFlag` model in `backend/app/ai/models.py`
4. Create toggle API endpoint in `backend/app/ai/routes.py`
5. Create CLI commands in `backend/cli/ai.py`
6. Add `is_analyst_enabled()` and `is_analyst_owner_only()` helpers

### Phase 2: Analyst Service (2 hours)
1. Create `backend/app/ai/analyst.py` with:
   - `build_outlook(db, date) -> OutlookReport`
   - Pull equity curves from PR-052 (90-day window)
   - Pull drawdown data from PR-052
   - Pull Sharpe/Sortino/volatility from PR-053
   - Pull GOLD RSI/ROC context from existing analytics
   - Generate narrative with data citations
   - Handle extreme values gracefully
   - Return structured `OutlookReport` Pydantic model

2. Create Pydantic schemas in `backend/app/ai/schemas.py`:
   - `OutlookReport`: narrative, volatility_zones, correlations, generated_at
   - `VolatilityZone`: level, threshold, description
   - `CorrelationPair`: instrument_a, instrument_b, coefficient

### Phase 3: Scheduler (30 min)
1. Create `backend/schedulers/daily_outlook.py`
2. Check `is_analyst_enabled()` - skip if disabled
3. Call `build_outlook(db, datetime.now())`
4. Check `is_analyst_owner_only()`:
   - If True: Send only to owner (via messaging service)
   - If False: Send to all users (email + Telegram)
5. Increment `ai_outlook_published_total.labels(channel="email").inc()`
6. Log all generations with structured logging

### Phase 4: Messaging Templates (20 min)
1. Add to `backend/app/messaging/templates.py`:
   - `DAILY_OUTLOOK_EMAIL`: HTML template with narrative, zones, correlations
   - `DAILY_OUTLOOK_TELEGRAM`: Markdown template (concise, mobile-friendly)
2. Both templates must include:
   - Data citations (Sharpe: X, Drawdown: Y%)
   - Volatility zones
   - Top 3 correlations
   - Footer: "AI-generated analysis. Not financial advice."

### Phase 5: Metrics (10 min)
1. Add to `backend/app/observability/metrics.py`:
```python
self.ai_outlook_published_total = Counter(
    "ai_outlook_published_total",
    "Total AI outlooks published",
    ["channel"],  # email, telegram
    registry=self.registry,
)
```

### Phase 6: Frontend Outlook Viewer (1 hour)
1. Create `frontend/web/app/outlook/page.tsx`:
   - Fetch latest outlook from API
   - If user is owner: Show toggle switch (enabled/owner_only)
   - If disabled: Show "Feature in testing" message
   - If enabled: Display narrative, volatility zones, correlations
   - Auto-refresh every 24 hours
   - Show timestamp of last generation

2. UI Components:
   - `<OwnerToggle>` (admin only)
   - `<OutlookNarrative>` (rich text with citations highlighted)
   - `<VolatilityZones>` (visual chart)
   - `<CorrelationMatrix>` (heatmap)

### Phase 7: Comprehensive Tests (2 hours)
1. Create `backend/tests/test_ai_analyst.py` with:
   - **Toggle Tests** (8 tests):
     - Default disabled
     - Owner can enable/disable
     - Non-owner gets 403
     - Toggle persists across restarts
     - CLI commands work
     - API endpoint updates DB
   
   - **Outlook Generation Tests** (12 tests):
     - Data citations present (Sharpe, Sortino, DD, RSI, ROC)
     - Extreme values handled (DD > 50%, vol > 100%)
     - Zero trades handled (informative message)
     - Volatility zones calculated correctly
     - Correlations computed (top 3 pairs)
     - Narrative coherence (min 200 words)
     - No PII or secrets leaked
     - Timestamps in UTC
   
   - **Scheduler Tests** (5 tests):
     - Disabled analyst skips generation
     - Enabled analyst generates daily
     - Owner-only sends to owner email only
     - Public mode sends to all users
     - Metrics increment on publish
   
   - **Template Tests** (4 tests):
     - Email template renders HTML correctly
     - Telegram template renders Markdown
     - Data citations formatted correctly
     - Footer disclaimer present

## Owner Testing Workflow

### Enable for Owner Testing
```bash
# Method 1: CLI
python -m backend.cli.ai toggle-analyst --enable --owner-only

# Method 2: API
curl -X POST http://localhost:8000/api/v1/ai/analyst/toggle \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -d '{"enabled": true, "owner_only": true}'

# Method 3: Environment Variable
AI_ANALYST_ENABLED=true
AI_ANALYST_OWNER_ONLY=true
```

### View Outlook (Owner Only)
```bash
# Web UI
http://localhost:3000/outlook

# API
curl http://localhost:8000/api/v1/ai/outlook/latest \
  -H "Authorization: Bearer $OWNER_TOKEN"
```

### Testing Checklist (2-4 weeks)
- [ ] Daily outlook generates without errors
- [ ] Narrative includes accurate data citations
- [ ] Extreme values handled gracefully (no crashes)
- [ ] Volatility zones make sense (checked against charts)
- [ ] Correlations are accurate (verified with manual calculation)
- [ ] Email template renders correctly (desktop + mobile)
- [ ] Telegram template renders correctly
- [ ] No PII or secrets exposed
- [ ] Narrative is coherent and professional
- [ ] Performance acceptable (<5s generation time)

### Enable for Clients (After Testing)
```bash
python -m backend.cli.ai toggle-analyst --enable --no-owner-only
```

## Acceptance Criteria

### Toggle Functionality
- ✅ Disabled by default (safety-first)
- ✅ Only owner (admin role) can toggle
- ✅ Owner-only mode restricts viewing to owner
- ✅ Toggle persists across restarts (DB-backed)
- ✅ Multiple toggle methods (env, DB, API, CLI)
- ✅ Logs all toggle events with user_id

### Outlook Quality
- ✅ Narrative includes data citations (Sharpe, Sortino, DD, RSI, ROC)
- ✅ Extreme values handled (DD > 50%, vol > 100% don't crash)
- ✅ Zero trades handled (informative message, not error)
- ✅ Volatility zones calculated (3 levels: low/med/high)
- ✅ Correlations computed (top 3 pairs with coefficients)
- ✅ GOLD analytics context included (RSI/ROC from existing data)
- ✅ Narrative coherence (min 200 words, professional tone)
- ✅ Timestamps in UTC

### Delivery
- ✅ Scheduler runs daily (respects toggle)
- ✅ Email template renders correctly
- ✅ Telegram template renders correctly
- ✅ Owner-only mode sends to owner email only
- ✅ Public mode sends to all users
- ✅ Metrics increment on publish

### Testing
- ✅ 29 comprehensive tests (toggle 8, generation 12, scheduler 5, templates 4)
- ✅ 100% code coverage of analyst.py
- ✅ All edge cases tested (extreme values, zero trades, disabled state)
- ✅ Integration tests (scheduler → messaging → delivery)

## Rollout Plan

### Week 1-2: Implementation
- Implement all components (toggle, analyst, scheduler, templates, frontend)
- Write comprehensive tests
- Verify all tests passing locally

### Week 3-4: Owner Testing
- Enable with `--owner-only` flag
- Owner receives daily outlook via email
- Monitor quality, data accuracy, narrative coherence
- Fix any issues discovered

### Week 5-6: Extended Testing
- Continue monitoring daily outlooks
- Verify no PII leaks
- Verify no crashes on extreme values
- Validate business value (is outlook useful?)

### Week 7+: Client Release
- If testing successful: `--no-owner-only`
- All users receive daily outlooks
- Monitor metrics: `ai_outlook_published_total{channel}`
- Gather user feedback

## Integration Points

- **PR-052**: Equity curves (`compute_equity_series`)
- **PR-053**: Performance metrics (`sharpe_ratio`, `sortino_ratio`, `max_drawdown`)
- **PR-062**: AI assistant infrastructure (RAG, guardrails)
- **PR-060**: Messaging service (email, Telegram delivery)
- **PR-009**: Observability metrics (`ai_outlook_published_total`)

## Known Limitations

1. **Narrative Quality**: Initial version may lack nuance - iterate based on owner feedback
2. **Volatility Zones**: Simplified (3 levels) - can expand in future PRs
3. **Correlations**: Only top 3 pairs - can make configurable
4. **Frequency**: Daily only - can add weekly/monthly summaries later
5. **Instruments**: GOLD-focused initially - can expand to multi-asset

## Success Metrics

### Technical
- 100% test coverage of analyst.py
- <5s outlook generation time
- Zero PII leaks in narrative
- Zero crashes on extreme values

### Business
- Owner finds outlook useful (qualitative)
- Outlook data citations match manual verification
- Email open rate >30% (after client release)
- Telegram read rate >50%

## Timeline

- **Phase 1**: 30 min (toggle infrastructure)
- **Phase 2**: 2 hours (analyst service)
- **Phase 3**: 30 min (scheduler)
- **Phase 4**: 20 min (templates)
- **Phase 5**: 10 min (metrics)
- **Phase 6**: 1 hour (frontend)
- **Phase 7**: 2 hours (tests)

**Total Implementation**: ~6-7 hours

**Owner Testing Period**: 2-4 weeks (user requirement)

---

**Next Steps**:
1. Create feature_flags migration
2. Implement toggle infrastructure
3. Build analyst.py with real analytics integration
4. Write comprehensive tests
5. Enable for owner testing
6. Iterate based on feedback
7. Release to clients after validation
