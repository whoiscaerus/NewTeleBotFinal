# PHASE 1A COMPLETE EXECUTION PLAN
**Status**: Ready for Full Implementation
**Date**: October 24, 2025
**Target Duration**: 3-4 weeks (60-70 hours total)
**Total PRs**: 10 (5 complete, 5 remaining)

---

## 🎯 PHASE 1A OVERVIEW

**Goal**: Complete end-to-end trading workflow from signal generation → order construction → broker integration

**Current Progress**: 50% (5/10 PRs complete)
- ✅ PR-011: MT5 Session Manager
- ✅ PR-012: Market Hours & Timezone Gating
- ✅ PR-013: Data Pull Pipelines
- ✅ PR-014: Fib-RSI Strategy Module (66 tests, 80% coverage)
- ✅ PR-015: Order Construction (53 tests, 82% coverage)

**Remaining**: 5 PRs
- ⏳ PR-016: Local Trade Store Migration (SQLite → Postgres)
- ⏳ PR-017: Signal Serialization + HMAC Signing
- ⏳ PR-018: Resilient Retries/Backoff & Telegram Alerts
- ⏳ PR-019: Live Trading Bot Enhancements
- ⏳ PR-020: Charting/Exports Refactor

---

## 📋 PHASE 1A DEPENDENCY GRAPH

```
PR-011 (MT5 Session) ──┐
                       ├─→ PR-013 (Data Fetch) ──→ PR-014 (Strategy) ──→ PR-015 (Orders)
PR-012 (Market Hours) ─┘                                                       │
                                                                              │
                                                    PR-016 (Trade Store) ←─┘
                                                            │
                                PR-017 (Serialization) ────→├─→ PR-019 (Live Bot)
                                PR-018 (Retries) ───────────┘      │
                                                                   │
                                                    PR-020 (Charts) ←

Tier Dependencies:
- Tier 1A1 (PR-011, 012, 013): Foundation — must complete first
- Tier 1A2 (PR-014, 015, 016): Core logic — depends on Tier 1A1
- Tier 1A3 (PR-017, 018): Delivery — can start once PR-015 ready
- Tier 1A4 (PR-019, 020): Runtime — depends on all above
```

---

## 🔄 EXECUTION SEQUENCE (Next 5 PRs)

### PR-016: Local Trade Store Migration (SQLite → Postgres)
**Current Status**: Not started
**Priority**: HIGH (blocker for PR-019)
**Effort**: 8-10 hours
**Dependencies**: PR-010 (DB baseline) ✅, PR-015 (Orders) ✅

#### Scope
- Create Postgres models for trades, positions, performance
- Alembic migration from SQLite schema
- Query service layer with filtering/sorting
- Reconciliation hooks for manual MT5 trades

#### Deliverables
```
backend/app/trading/store/
  models.py              # Trade, Position, Performance models
  service.py             # TradeService with query/filter logic
  routes.py              # REST endpoints (GET trades, GET positions)
  reconciliation.py      # Detect manual MT5 trades
backend/alembic/versions/
  XXXX_create_trade_models.py
backend/tests/
  test_trade_store.py    # 20+ tests
docs/prs/
  PR-016-IMPLEMENTATION-PLAN.md
  PR-016-IMPLEMENTATION-COMPLETE.md
  PR-016-ACCEPTANCE-CRITERIA.md
  PR-016-BUSINESS-IMPACT.md
```

#### Key Features
- [x] Trade history with entry/exit/P&L
- [x] Position tracking (open/closed)
- [x] Performance analytics (daily/weekly/monthly)
- [x] Reconciliation with MT5 (detect orphaned trades)
- [x] Query by symbol, date range, status
- [x] 90%+ test coverage

#### Acceptance Criteria
1. Create trade → query returns accurate P&L
2. Migration up/down clean
3. Reconciliation detects manual MT5 trades
4. Performance calculations correct

---

### PR-017: Signal Serialization + HMAC Signing for Server Ingest
**Current Status**: Not started
**Priority**: HIGH (required for outbound delivery)
**Effort**: 6-8 hours
**Dependencies**: PR-007 (Secrets) ✅, PR-015 (Orders) ✅

#### Scope
- Serialize OrderParams to JSON with field ordering
- HMAC-SHA256 signing for tamper-proof delivery
- Signature verification on receiving end
- Payload versioning for backward compatibility

#### Deliverables
```
backend/app/trading/outbound/
  client.py              # HTTP client with retries
  hmac.py                # HMAC signing/verification
  schemas.py             # SignalPayload, SignatureEnvelope
backend/tests/
  test_signal_serialization.py
  test_hmac_signing.py   # 15+ tests
docs/prs/
  PR-017-IMPLEMENTATION-PLAN.md
  PR-017-IMPLEMENTATION-COMPLETE.md
  PR-017-ACCEPTANCE-CRITERIA.md
```

#### Key Features
- [x] OrderParams → JSON serialization
- [x] HMAC-SHA256 signing
- [x] Timestamp + nonce for replay protection
- [x] Signature verification
- [x] Schema versioning (v1, v2, etc.)

#### Acceptance Criteria
1. Sign signal → receiver verifies signature
2. Modified payload → verification fails
3. Timestamp prevents replay attacks
4. Version negotiation works

---

### PR-018: Resilient Retries/Backoff & Telegram Error Alerts
**Current Status**: Not started
**Priority**: HIGH (required for reliability)
**Effort**: 5-7 hours
**Dependencies**: PR-007 (Secrets) ✅, PR-003 (Logging) ✅, PR-017 (can run in parallel)

#### Scope
- Exponential backoff retry logic (configurable)
- Jitter to prevent thundering herd
- Circuit breaker for cascading failures
- Telegram alerts on critical errors

#### Deliverables
```
backend/app/core/
  retry.py               # RetryPolicy, exponential_backoff
  circuit_breaker.py     # CircuitBreaker state machine
backend/app/ops/
  alerts.py              # TelegramAlerter service
backend/tests/
  test_retry.py          # 12+ tests
  test_circuit_breaker.py
  test_alerts.py
docs/prs/
  PR-018-IMPLEMENTATION-PLAN.md
  PR-018-IMPLEMENTATION-COMPLETE.md
```

#### Key Features
- [x] Exponential backoff (1s → 32s max)
- [x] Jitter to spread retries
- [x] Circuit breaker (CLOSED → OPEN → HALF_OPEN)
- [x] Telegram notifications for alerts
- [x] Configurable retry policies per service

#### Acceptance Criteria
1. POST fails 3x → automatic retry with backoff
2. Too many failures → circuit breaker opens
3. Circuit open → fast fail (no retries)
4. Telegram alert within 30s of critical error

---

### PR-019: Live Trading Bot Enhancements (heartbeat, drawdown caps, analytics hooks)
**Current Status**: Not started
**Priority**: CRITICAL (combines everything)
**Effort**: 10-12 hours
**Dependencies**: PR-011 ✅, PR-014 ✅, PR-015 ✅, PR-016 ✅, PR-017 ✅, PR-018 ✅

#### Scope
- Main trading loop orchestration
- Heartbeat monitoring (system health)
- Drawdown guard (auto-close on % loss)
- Analytics hooks for performance tracking
- Event publishing for downstream consumers

#### Deliverables
```
backend/app/trading/runtime/
  loop.py                # Main event loop
  heartbeat.py           # Health monitoring
  drawdown_guard.py      # Auto-close logic
  events.py              # Event publishing
backend/tests/
  test_trading_loop.py   # 20+ integration tests
docs/prs/
  PR-019-IMPLEMENTATION-PLAN.md
  PR-019-IMPLEMENTATION-COMPLETE.md
  PR-019-ACCEPTANCE-CRITERIA.md
  PR-019-BUSINESS-IMPACT.md
```

#### Key Features
- [x] Main loop: fetch data → run strategy → build order → submit
- [x] Heartbeat: check MT5 health every 30s
- [x] Drawdown guard: close all if portfolio down >20%
- [x] Event publishing (signal_detected, order_submitted, trade_closed)
- [x] Performance metrics tracking
- [x] Graceful shutdown on errors

#### Acceptance Criteria
1. Run loop for 5 min → all steps execute
2. Heartbeat logs every 30s
3. Portfolio down 20% → auto-close triggered
4. Events published for each state change
5. Error doesn't crash loop (continues with retry)

---

### PR-020: Charting/Exports Refactor (matplotlib backend, caching)
**Current Status**: Not started
**Priority**: MEDIUM (optimization, not blocking)
**Effort**: 6-8 hours
**Dependencies**: PR-001 (Cache config) ✅, PR-002 (Settings) ✅

#### Scope
- Chart rendering with matplotlib/plotly
- Caching layer (Redis) for performance
- EXIF data stripping for privacy
- Export formats (PNG, SVG, PDF)

#### Deliverables
```
backend/app/media/
  render.py              # Chart rendering
  storage.py             # S3/disk storage
  cache.py               # Redis caching
backend/tests/
  test_charting.py       # 10+ tests
docs/prs/
  PR-020-IMPLEMENTATION-PLAN.md
  PR-020-IMPLEMENTATION-COMPLETE.md
```

#### Key Features
- [x] Render OHLC charts with indicators
- [x] Cache rendered charts (1 hour TTL)
- [x] Strip EXIF data
- [x] Multiple export formats (PNG, SVG)
- [x] Responsive sizing for web/mobile

#### Acceptance Criteria
1. Render 500-bar chart → saved to disk
2. Second render of same data → served from cache
3. Chart metadata stripped
4. Format conversion works (PNG → SVG)

---

## 📊 PHASE 1A EXECUTION TIMELINE

### Week 1: PR-016 + PR-017 (Foundation + Delivery)
```
Mon: PR-016 Phase 1-2 (8 hours)
Tue: PR-016 Phase 3-4 (6 hours) + PR-017 Phase 1 (2 hours)
Wed: PR-017 Phase 2-3 (6 hours)
Thu: PR-017 Phase 4 (2 hours) + Buffer (2 hours)
Fri: Testing/Integration (8 hours)

Total: 40 hours | Progress: 70% (7/10)
```

### Week 2: PR-018 + PR-019 (Reliability + Orchestration)
```
Mon: PR-018 Phase 1-2 (6 hours) + PR-019 Phase 1 (2 hours)
Tue: PR-018 Phase 3-4 (4 hours) + PR-019 Phase 2 (4 hours)
Wed: PR-019 Phase 3 (8 hours)
Thu: PR-019 Phase 4 (6 hours)
Fri: Integration Testing (6 hours)

Total: 40 hours | Progress: 90% (9/10)
```

### Week 3: PR-020 + Buffer
```
Mon: PR-020 Phase 1-2 (6 hours) + Edge cases (2 hours)
Tue: PR-020 Phase 3-4 (6 hours)
Wed: PR-020 Testing (4 hours) + Integration (2 hours)
Thu-Fri: Buffer/Rework (10 hours)

Total: 30 hours | Progress: 100% (10/10)

Grand Total: 110 hours (realistic estimate: 70-80 hours actual)
```

---

## 🎯 SUCCESS METRICS

### Code Quality
- ✅ All 5 PRs: ≥80% test coverage (target ≥90%)
- ✅ All 5 PRs: Zero TODOs/FIXMEs/hardcoded values
- ✅ All 5 PRs: Black formatted, type hints 100%
- ✅ All 5 PRs: Complete docstrings with examples

### Testing
- ✅ 70+ new test cases across 5 PRs
- ✅ All tests passing locally before push
- ✅ GitHub Actions CI/CD green on every PR

### Documentation
- ✅ 4 docs per PR × 5 PRs = 20 documents
- ✅ Implementation plans complete before code
- ✅ Acceptance criteria verified before merge

### Performance
- ✅ Trade store query <100ms (50 trades)
- ✅ Chart rendering cached <1s after first render
- ✅ Live bot loop processes signal <500ms

### Integration
- ✅ End-to-end: Market data → Strategy → Order → Trade Store
- ✅ Error resilience: Retry/backoff on transient failures
- ✅ Monitoring: Heartbeat + drawdown guard active
- ✅ Charting: Charts available for all trades

---

## 🚀 PHASE 1A COMPLETION CHECKLIST

### Pre-Kickoff
- [ ] Read this plan (15 min)
- [ ] Review master PR doc for all 5 remaining PRs (30 min)
- [ ] Set up local dev environment (5 min)
- [ ] Run existing tests to confirm baseline (10 min)

### During Implementation (Per PR)
- [ ] Phase 1: Discovery & Planning (30-45 min)
- [ ] Phase 2: Implementation (3-8 hours)
- [ ] Phase 3: Testing (1-3 hours)
- [ ] Phase 4: Verification (30 min - 1 hour)
- [ ] Phase 5-7: Documentation & Integration (2-3 hours total)

### Post-Phase 1A
- [ ] Merge all 5 PRs to main
- [ ] Run full regression suite (PR-011 through PR-020)
- [ ] Create PHASE_1A_COMPLETE_BANNER.txt
- [ ] Update CHANGELOG with all 10 PRs
- [ ] Plan Phase 1B (Signal Ingestion APIs)

---

## 📌 CRITICAL SUCCESS FACTORS

1. **Dependency Order**: Strictly follow TIER dependencies (don't start PR-019 before PR-018)
2. **Test Coverage**: No PR merges with <80% coverage
3. **Documentation**: All 4 required docs before merge
4. **Integration Testing**: Test against previous PRs (not in isolation)
5. **Git Hygiene**: One PR per branch, clean commit history

---

## 🔗 REFERENCES

**Master Documents**:
- `/base_files/Final_Master_Prs.md` (PR specifications, all 102+)
- `/base_files/COMPLETE_BUILD_PLAN_ORDERED.md` (execution order)
- `/base_files/FULL_BUILD_TASK_BOARD.md` (checklist format)

**Completed PRs** (Reference):
- `/docs/prs/PR-014-IMPLEMENTATION-COMPLETE.md` (Template for quality)
- `/docs/prs/PR-015-IMPLEMENTATION-COMPLETE.md` (Template for quality)

**Copilot Instructions**:
- `.github/copilot-instructions.md` (7-phase workflow, quality gates, all guidelines)

---

## 🎬 READY TO START?

Next step: **Begin PR-016 Phase 1 (Discovery & Planning)**

Key question to clarify:
- Do you want to proceed sequentially (PR-016 → 17 → 18 → 19 → 20)?
- Or work in parallel where possible (PR-017 + 018 while PR-016 Phase 2-3)?

**Recommendation**: Sequential for simplicity + focus. Each PR will have dependencies on previous ones ready.

Type "start pr-016" when ready! 🚀
