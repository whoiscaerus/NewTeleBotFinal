# 🚀 Full Build Task Board — P0 → P3 (104 PRs Total)

Complete implementation roadmap with phase organization, PR numbers, and status tracking.

**Last Updated:** October 24, 2025  
**Total PRs:** 104  
**Target Launch:** P0 Complete → P1 Complete (Signals MVP)

---

## 📊 Phase Summary

| Phase | PRs | Timeline | Status |
|-------|-----|----------|--------|
| **P0** | PR-001 to PR-010 | 6-8 weeks | ⏳ Not Started |
| **P1** | PR-011 to PR-036 | 12-16 weeks | ⏳ Not Started |
| **P2** | PR-037 to PR-070 | 16-20 weeks | ⏳ Not Started |
| **P3** | PR-071 to PR-104 | 20-24 weeks | ⏳ Not Started |

---

## ✅ P0 — Foundations (Weeks 1-8)

**Goal:** Production-grade infrastructure, auth, logging, observability

### Core Infrastructure (PR-001 to PR-010)

- [ ] **PR-001** — Monorepo Bootstrap, Envs, Secrets, Pre-Commit, CI/CD
  - Scope: Docker, Makefile, GitHub Actions, devcontainer
  - Deliverables: .github/workflows, docker/, scripts/, pyproject.toml
  - Exit: `make up` works; CI green

- [ ] **PR-002** — Central Config & Typed Settings (12-Factor)
  - Scope: Pydantic BaseSettings, environment loading
  - Deliverables: backend/app/core/settings.py, env validation
  - Exit: All settings typed; prod validation tested

- [ ] **PR-003** — Structured JSON Logging + Request IDs + Correlation
  - Scope: JSON formatter, request ID middleware, contextvar tracing
  - Deliverables: backend/app/core/logging.py, middleware.py
  - Exit: All logs are JSON; request_id propagates

- [ ] **PR-004** — AuthN/AuthZ Core (JWT sessions, roles: owner/admin/user)
  - Scope: RS256 JWT, password hashing (Argon2id), RBAC decorators
  - Deliverables: backend/app/auth/{models,schemas,routes,rbac}.py
  - Exit: JWT login works; roles enforced

- [ ] **PR-005** — Rate Limiting, Abuse Controls & IP Throttling
  - Scope: Redis-backed token bucket, endpoint decorators
  - Deliverables: backend/app/core/rate_limit.py, abuse guards
  - Exit: Rate limits work; brute-force throttled

- [ ] **PR-006** — API Error Taxonomy (RFC7807) & Input Validation
  - Scope: ProblemDetail responses, Pydantic validation
  - Deliverables: backend/app/core/{errors,validation}.py
  - Exit: All errors RFC7807 compliant

- [ ] **PR-007** — Secrets Management (dotenv → Vault/KMS rotation)
  - Scope: SecretProvider abstraction, env/dotenv/Vault pluggable
  - Deliverables: backend/app/core/secrets.py
  - Exit: Secrets load from env; Vault-ready

- [ ] **PR-008** — Audit Log & Admin Activity Trails
  - Scope: Audit table, write-only model, middleware capture
  - Deliverables: backend/app/audit/{models,middleware,routes}.py
  - Exit: All sensitive operations logged; immutable

- [ ] **PR-009** — Observability Stack (metrics, traces, dashboards)
  - Scope: OpenTelemetry, Prometheus exporter, /metrics endpoint
  - Deliverables: backend/app/observability/{metrics,tracing}.py
  - Exit: Metrics scraped; dashboards show API latency

- [ ] **PR-010** — Data Model Baseline (Postgres + Alembic migrations)
  - Scope: SQLAlchemy 2.0, users table, baseline migration
  - Deliverables: backend/app/core/{db,models}.py, alembic/versions/0001_baseline.py
  - Exit: `alembic upgrade head` succeeds

**P0 Exit Criteria:**
- [ ] CI all green (lint, type, tests, build)
- [ ] `/health`, `/ready`, `/metrics` live
- [ ] JWT login: `POST /auth/login` → token works
- [ ] Alembic baseline applied to test DB
- [ ] Logging: all events JSON + request_id
- [ ] Rate limits: test endpoint hits limit → 429

---

## ✅ P1 — Trading Core, Ingestion, Telegram, Payments (Weeks 9-24)

**Goal:** End-to-end signal flow: predict → approve → execute → close

### A) Trading Core (PR-011 to PR-022)

- [ ] **PR-011** — MT5 Session Manager & Credentials Vaulting
  - Scope: MT5 login/reconnect, session lifecycle, circuit breaker
  - Deliverables: backend/app/trading/mt5/{session,health}.py
  - Exit: MT5 connects; health checks pass

- [ ] **PR-012** — Market Hours & Timezone Gating
  - Scope: FX market calendar, NY close rules, trading windows
  - Deliverables: backend/app/trading/time/{market_calendar,tz}.py
  - Exit: `is_market_open(symbol)` works; weekends blocked

- [ ] **PR-013** — Data Pull Pipelines (H1/H15, windows, monitor bars)
  - Scope: MT5 candle fetch, window sizing, cache
  - Deliverables: backend/app/trading/data/{fetch,cache}.py
  - Exit: Fetch 200 H1 bars; schema validated

- [ ] **PR-014** — Fib-RSI Strategy Module (spec-locked to your logic)
  - Scope: RSI + Fibonacci strategy, signal generation
  - Deliverables: backend/app/strategy/fib_rsi/{engine,schema}.py
  - Exit: Signals generated; match historical outputs

- [ ] **PR-015** — Order Construction (entry/SL/TP/expiry, min stop distance)
  - Scope: Entry/SL/TP calculation, RR validation
  - Deliverables: backend/app/trading/orders/{builder,schema}.py
  - Exit: Orders built; SL distance enforced

- [ ] **PR-016** — Local Trade Store Migration (SQLite → Postgres)
  - Scope: Trade, EquityPoint, ValidationLog tables; Alembic migration
  - Deliverables: backend/app/trading/store/{models,service}.py, alembic/versions/0002_trading_store.py
  - Exit: Trade CRUD works; historical data migrated

- [ ] **PR-017** — Signal Serialization + HMAC Signing for Server Ingest
  - Scope: Signal body canonicalization, HMAC-SHA256 signing
  - Deliverables: backend/app/trading/outbound/{client,hmac}.py
  - Exit: Signed signal sent; server verifies

- [ ] **PR-018** — Resilient Retries/Backoff & Telegram Error Alerts
  - Scope: Exponential backoff, max retries, Telegram DM on failure
  - Deliverables: backend/app/core/retry.py, backend/app/ops/alerts.py
  - Exit: Failed outbound → retry → Telegram alert after exhaust

- [ ] **PR-019** — Live Trading Bot Enhancements (heartbeat, drawdown caps, analytics hooks)
  - Scope: Periodic heartbeat, drawdown threshold checks, loop event hooks
  - Deliverables: backend/app/trading/runtime/{loop,events}.py
  - Exit: Heartbeat emitted; drawdown cap enforced

- [ ] **PR-020** — Charting/Exports Refactor (matplotlib backend, caching)
  - Scope: Server-side chart rendering, EXIF stripping, TTL cache
  - Deliverables: backend/app/media/{render,storage}.py
  - Exit: Candle chart rendered; file cached

- [ ] **PR-021** — **Signals API** (ingest, schema, dedupe, payload limits)
  - Scope: POST /api/v1/signals endpoint, HMAC verification, 32KB limit
  - Deliverables: backend/app/signals/{models,schemas,routes}.py, alembic/versions/0003_signals.py
  - Exit: Signal created; 201 response; HMAC verified

- [ ] **PR-022** — **Approvals API** (approve/reject, consent versioning, audit)
  - Scope: POST /api/v1/approvals endpoint, decision enum, unique constraint
  - Deliverables: backend/app/approvals/{models,schemas,routes}.py, alembic/versions/0004_approvals.py
  - Exit: Signal approved; Approval logged; audit written

### B) Account Reconciliation & Risk Management (NEW PRs-023)

- [ ] **PR-023** — **Account Reconciliation & Trade Monitoring** (MT5 Position Sync + Auto-Close)
  - Scope: Real-time position sync from MT5, drawdown guards, auto-liquidation
  - Deliverables: backend/app/trading/reconciliation/{mt5_sync,auto_close}.py, backend/app/trading/monitoring/{drawdown_guard,liquidation}.py, alembic/versions/0005_reconciliation.py
  - Exit: Positions sync every 10s; 20% drawdown triggers auto-close; audit trail complete

### C) Affiliate & Growth (NEW PR-024)

- [ ] **PR-024** — **Affiliate & Referral System** (Tracking, Payouts, Dashboards)
  - Scope: Referral code generation, conversion tracking, commission automation, fraud detection
  - Deliverables: backend/app/affiliates/{models,service,routes,fraud}.py, backend/schedulers/affiliate_payout_runner.py, alembic/versions/0006_affiliates.py
  - Exit: Referral link generated; commission calculated; payout triggered

### D) Device & EA Management (Original PR-023 → PR-025, etc.)

- [ ] **PR-025** — Device Registry & HMAC Secrets
  - Scope: Device registration, secret generation, list/revoke
  - Deliverables: backend/app/clients/{models,routes}.py, alembic/versions/0007_devices.py
  - Exit: Device registered; secret returned once

- [ ] **PR-026** — EA Poll/Ack API (HMAC, Nonce, Freshness)
  - Scope: /api/v1/poll endpoint, signature verification, pending signals
  - Deliverables: backend/app/ea/{poll,ack}.py
  - Exit: EA polls; receives signal; acks execution

- [ ] **PR-027** — Execution Store & Broker Ticketing
  - Scope: Execution log, trade confirmations, broker ticket links
  - Deliverables: backend/app/execution/{models,service}.py, alembic/versions/0008_execution.py
  - Exit: Execution logged; broker ticket recorded

### E) Telegram Integration (Original PR-026 → PR-028, etc.)

- [ ] **PR-028** — Telegram Webhook Service & Signature Verification
  - Scope: Webhook receiver, signature validation, message routing
  - Deliverables: backend/app/telegram/{webhook,crypto}.py
  - Exit: Webhook receives update; signature verified

- [ ] **PR-029** — Bot Command Router & Permissions
  - Scope: Command dispatch, role-based access, error handling
  - Deliverables: backend/app/telegram/{router,permissions}.py
  - Exit: `/start` command works; only owner can `/admin`

- [ ] **PR-030** — Shop: Products/Plans & Entitlements Mapping
  - Scope: Plan catalog, feature tiers, entitlement checks
  - Deliverables: backend/app/billing/{catalog,entitlements}.py, alembic/versions/0009_billing.py
  - Exit: Plans defined; entitlements gate premium routes

- [ ] **PR-031** — RateFetcher Integration & Dynamic Quotes
  - Scope: Price feed from broker, quote engine
  - Deliverables: backend/app/trading/quotes/{fetcher,cache}.py
  - Exit: Live quotes cached; edge bot serves quotes

- [ ] **PR-032** — Content Distribution Router (Keywords → Channels)
  - Scope: Route signals by asset/strategy to Telegram channels
  - Deliverables: backend/app/telegram/distribution.py
  - Exit: GOLD signal → #gold-channel; EUR/USD → #eur-usd-channel

- [ ] **PR-033** — GuideBot: Buttons, Links & Scheduler
  - Scope: Educational content, inline buttons, scheduled sends
  - Deliverables: backend/app/telegram/guidebot/{commands,scheduler}.py
  - Exit: `/guides` command shows options; scheduled tips sent

- [ ] **PR-034** — MarketingBot: Broadcasts, CTAs & JobQueue
  - Scope: Promotional messages, call-to-action buttons, job queue
  - Deliverables: backend/app/telegram/marketingbot/{broadcast,cta}.py
  - Exit: Owner sends broadcast; all subscribers get message

### F) Payments (Original PR-033 → PR-035, etc.)

- [ ] **PR-035** — Fiat Payments via Stripe (Checkout + Portal)
  - Scope: Stripe Checkout integration, billing portal, invoice management
  - Deliverables: backend/app/billing/{stripe,webhook}.py
  - Exit: Checkout flow works; invoice generated

- [ ] **PR-036** — Telegram Native Payments (optional)
  - Scope: Telegram Stars payment support
  - Deliverables: backend/app/telegram/payments.py
  - Exit: User can pay via Telegram; subscription activated

**P1 Exit Criteria:**
- [ ] Signals flow: strategy → signed POST → stored → user approves → EA polls → executes → ack stored
- [ ] Telegram shop online with Stripe test mode working
- [ ] Position sync works; drawdown guard tested
- [ ] Affiliate system tracking conversions
- [ ] Premium entitlements gate paid features
- [ ] All 26 PRs merged; 86+ tests passing; ≥90% coverage

---

## ✅ P2 — Mini App, Copy-Trading, Analytics, Web (Weeks 25-44)

**Goal:** Secondary UX (Mini App), performance analytics, copy-trading engine

### A) Mini App Bootstrap (PR-037 to PR-039)

- [ ] **PR-037** — Telegram Mini App Bootstrap (Next.js WebApp)
  - Scope: Mini App auth, JWT bridge from Telegram
  - Deliverables: frontend/miniapp/app/page.tsx, backend/app/oauth/tg_jwt.py
  - Exit: Mini App loads; user authenticated

- [ ] **PR-038** — Mini App: Approval Console
  - Scope: Real-time pending signals, approve/reject UI
  - Deliverables: frontend/miniapp/app/approvals/page.tsx
  - Exit: Pending signals listed; user can approve

- [ ] **PR-039** — Mini App: Billing (Stripe Checkout + Portal)
  - Scope: Plan selection, checkout link, subscription status
  - Deliverables: frontend/miniapp/app/billing/page.tsx
  - Exit: User can upgrade to premium; subscription shows

### B) Payment Hardening & Security (PR-040 to PR-042)

- [ ] **PR-040** — Payment Security Hardening (Replay Protection, PCI Scoping)
  - Scope: Idempotency keys, webhook replay protection, payment state machine
  - Deliverables: backend/app/billing/security.py, backend/app/core/idempotency.py
  - Exit: Duplicate Stripe events handled safely

- [ ] **PR-041** — MT5 EA SDK & Reference EA (Copy/Approval Modes)
  - Scope: MQL5 SDK for copy-trading, reference EA code
  - Deliverables: ea-sdk/reference_ea.mq5, ea-sdk/README.md
  - Exit: EA compiles; handles approval mode

- [ ] **PR-042** — Encrypted Signal Transport (E2E to EA)
  - Scope: AEAD encryption for signal payload to EA
  - Deliverables: backend/app/trading/encryption.py, ea-sdk/decrypt.mq5
  - Exit: Signal encrypted; EA decrypts

### C) Account Linking & Position Tracking (PR-043 to PR-044)

- [ ] **PR-043** — Live Position Tracking & Account Linking (MT5 Verify)
  - Scope: OAuth/API key linking to MT5, position polling
  - Deliverables: backend/app/accounts/{linking,positions}.py
  - Exit: User links MT5 account; live positions displayed

- [ ] **PR-044** — Price Alerts & Notifications (User-Specific)
  - Scope: Price level alerts, notification delivery (Telegram/push)
  - Deliverables: backend/app/alerts/{alerts,delivery}.py, alembic/versions/00XX_alerts.py
  - Exit: User sets alert; gets notified when price hit

### D) Copy-Trading (PR-045 to PR-046)

- [ ] **PR-045** — Copy-Trading Integration (FXPro) & +30% Pricing
  - Scope: FXPro MAM integration, mirror positions, +30% markup
  - Deliverables: backend/app/copytrading/{broker,engine}.py
  - Exit: Copy-trading positions opened; markup charged

- [ ] **PR-046** — Copy-Trading Risk & Compliance Controls
  - Scope: Max trade size, max drawdown, risk tier checks
  - Deliverables: backend/app/copytrading/risk_controls.py
  - Exit: Risk limits enforced; trades blocked if over limit

### E) Public Performance & Trust (PR-047 to PR-050)

- [ ] **PR-047** — Public Performance Page (Read-only)
  - Scope: Historical performance charts, win rate, Sharpe ratio (delayed data)
  - Deliverables: frontend/web/app/performance/page.tsx, backend/app/analytics/public.py
  - Exit: Page loads; performance metrics visible (delayed)

- [ ] **PR-048** — Auto-Trace to Third-Party Tracers (Post-Close)
  - Scope: Report closed trades to Darwinex/Myfxchoice/tradingview
  - Deliverables: backend/app/trading/tracers/{darwinex,myfxchoice}.py
  - Exit: Closed trade pushed to tracers; verified in tracers

- [ ] **PR-049** — Network Trust Scoring (Graph & Influence)
  - Scope: User reputation, copy-trader influence, validation metrics
  - Deliverables: backend/app/trust/scoring.py, alembic/versions/00XX_trust.py
  - Exit: Scores calculated; reputation index exists

- [ ] **PR-050** — Public Trust Index (Site Widget + API)
  - Scope: Public-facing trust metrics, embeddable widget
  - Deliverables: frontend/web/components/TrustWidget.tsx, backend/app/trust/routes.py
  - Exit: Widget shows trader reputation; API serves data

### F) Analytics Warehouse & KPIs (PR-051 to PR-058)

- [ ] **PR-051** — Analytics: Trades Warehouse & Rollups
  - Scope: Aggregate trade table, hourly/daily/monthly rollups
  - Deliverables: backend/app/analytics/{warehouse,rollups}.py, backend/schedulers/analytics_runner.py
  - Exit: Trade data rolled up; queries fast

- [ ] **PR-052** — Equity & Drawdown Engine (Server)
  - Scope: Equity curve, max drawdown, recovery metrics
  - Deliverables: backend/app/analytics/equity.py
  - Exit: Equity curve calculated; max drawdown known

- [ ] **PR-053** — Performance Metrics (Sharpe, Sortino, Calmar, Profit Factor)
  - Scope: Strategy performance KPIs
  - Deliverables: backend/app/analytics/metrics.py
  - Exit: All metrics calculated; cached

- [ ] **PR-054** — Time-Bucketed Analytics (Hour/Day/Month + Heatmaps)
  - Scope: Hourly/daily/monthly PnL, heatmaps
  - Deliverables: backend/app/analytics/timebucket.py
  - Exit: Heatmaps generated; trends visible

- [ ] **PR-055** — Client Analytics UI (Mini App) + PNG/CSV Export
  - Scope: Charts, export buttons
  - Deliverables: frontend/miniapp/app/analytics/page.tsx
  - Exit: User sees performance dashboard; can export

- [ ] **PR-056** — Operator Revenue & Cohorts (MRR/ARR, Churn, ARPU)
  - Scope: Owner analytics (revenue, cohorts, churn)
  - Deliverables: backend/app/analytics/business.py, alembic/versions/00XX_cohorts.py
  - Exit: Owner dashboard shows MRR, churn rate

- [ ] **PR-057** — CSV/JSON Export & Public Share Links (Redacted)
  - Scope: Export trades, results; shareable links (PII redacted)
  - Deliverables: backend/app/exports/{csv,share}.py
  - Exit: Export works; share link generates

- [ ] **PR-058** — Owner/Operator Analytics Panels (Grafana + Alerts)
  - Scope: Grafana dashboards, alert thresholds
  - Deliverables: grafana/dashboards/*.json, prometheus/alerts.yml
  - Exit: Grafana live; dashboards show KPIs

**P2 Exit Criteria:**
- [ ] Mini App is primary UX for approvals/billing/analytics
- [ ] Copy-trading auto with +30% markup & risk caps enforced
- [ ] Analytics warehouse live; dashboards working
- [ ] Public performance page (delayed data)
- [ ] Third-party tracers updated post-trade
- [ ] All 22 PRs merged; tests passing

---

## ✅ P3 — AI, Education, Owner Automation, Web Platform (Weeks 45-68+)

### Phase P3 contains 46 PRs covering:

- PR-059 to PR-070: **Messaging, KB, AI, Automation** (preferences, messaging bus, CMS, AI support, tickets, education, alerts, journeys, backup, privacy)
- PR-071 to PR-083: **Strategy & Research** (orchestrator, PPO, decision logs, backtests, walk-forward, versioning, feature store, paper-trading, quotas)
- PR-084 to PR-095: **Web Platform** (web app, TG OAuth, SEO, next-gen dashboard, gamification, education hub, themes, AI outlook, fraud, ledger, social, trust)
- PR-096 to PR-104: **Partners & Scale** (affiliates, AI upsell, CRM, admin portal, autonomous health, AI reports, health monitoring, owner journey, compliance, onboarding)

**P3 Goals:**
- 24/7 AI support + human escalation
- Education hub with quizzes & rewards
- Internationalized UI/bots
- Paper-trading & quotas
- Admin portal operating business end-to-end
- Autonomous health monitoring & self-healing
- AI-generated reports (daily/weekly/monthly)
- Public trust index live

---

## 📊 Master Checklist

### Critical Path (Must Complete in Order)

- [ ] **P0 Complete** (PR-001 to PR-010)
  - Exit: Infrastructure ready, CI/CD working, auth functional
  
- [ ] **P1-Core Complete** (PR-011 to PR-027)
  - Exit: Signals flow end-to-end, position monitoring, affiliate system
  
- [ ] **P1-Full Complete** (PR-028 to PR-036)
  - Exit: Telegram bots + payments working
  
- [ ] **P2-Mini App Complete** (PR-037 to PR-046)
  - Exit: Users can approve trades + manage billing in Mini App
  
- [ ] **P2-Analytics Complete** (PR-047 to PR-058)
  - Exit: Performance visible; public + owner dashboards live
  
- [ ] **P3-AI/Core Complete** (PR-059 to PR-070)
  - Exit: AI support, education, automation, messaging
  
- [ ] **P3-Platform Complete** (PR-071 to PR-104)
  - Exit: Web platform, admin portal, autonomous health, partner ecosystem

---

## 🎯 Quick Reference

**If you need to ship MVP (Signals only):** Complete P0 + P1-Core (PR-001 to PR-027)  
**If you need full user experience:** Add P2 (Mini App + Analytics)  
**If you need enterprise features:** Add P3 (AI, automation, platform)

---

**Maintenance Notes:**

- Keep this board updated as PRs complete (mark [ ] → [x])
- Link each PR to GitHub PR number once created
- Track test coverage + deployment status
- Update phase timelines based on actual velocity

---
