# COMPLETE BUILD PLAN — LOGICAL EXECUTION ORDER
**Date**: October 24, 2025  
**Status**: Production-Ready Sequencing  
**Total PRs**: 102+ features across 4 phases

---

## Executive Summary

This document provides the **optimal execution order** for all 102+ PRs across the enterprise trading platform. The sequence:
1. ✅ Minimizes dependency violations (no PR starts before its dependencies complete)
2. ✅ Enables parallel work where possible (non-dependent PRs run simultaneously)
3. ✅ Sequences by domain and risk level (foundational → core trading → user-facing → advanced)
4. ✅ Groups related functionality for context efficiency
5. ✅ Includes validation checkpoints between phases

---

## PHASE 0 — FOUNDATIONS (Weeks 1–2)
**Goal**: Establish platform rails, no business logic yet  
**Exit Criteria**: CI/CD green, database connected, health checks live

### TIER 0A — Core Infrastructure (Must complete before anything else)

**PR-001: Monorepo Bootstrap, Envs, Secrets, Pre-Commit, CI/CD**
- Files: GitHub Actions, Docker, Makefile, .gitignore, .pre-commit-config
- Dependencies: None
- Time: 3 hours
- Checkpoint: `make up` runs, CI green on commit
- ✅ Creates foundation for all subsequent PRs

**PR-002: Central Config & Typed Settings (12-Factor)**
- Files: `backend/app/core/settings.py`, `backend/app/core/env.py`
- Dependencies: PR-001 (Makefile, CI/CD)
- Time: 1.5 hours
- Checkpoint: `pytest backend/app/core/tests/test_settings.py` passes
- ✅ Enables environment-aware code for all services

**PR-003: Structured JSON Logging + Request IDs + Correlation**
- Files: `backend/app/core/logging.py`, `backend/app/core/middleware.py`
- Dependencies: PR-001, PR-002 (settings, env setup)
- Time: 2 hours
- Checkpoint: Logs appear as JSON on stdout; `X-Request-Id` propagates
- ✅ Required for observability chain (PR-009)

### TIER 0B — Security Foundation

**PR-004: AuthN/AuthZ Core (JWT sessions, roles: owner/admin/user)**
- Files: `backend/app/auth/{models,routes,rbac,schemas}.py`
- Dependencies: PR-001, PR-002, PR-003 (config, logging)
- Time: 3 hours
- Checkpoint: `POST /auth/login` returns JWT; `/me` requires token
- ✅ Every subsequent PR depends on JWT/RBAC

**PR-005: Rate Limiting, Abuse Controls & IP Throttling**
- Files: `backend/app/core/rate_limit.py`, `backend/app/core/decorators.py`, `backend/app/core/abuse.py`
- Dependencies: PR-001, PR-002 (Redis config, settings)
- Time: 2 hours
- Checkpoint: Hit `/health` 70x/min → 429 on 71st request
- ✅ Protects all public endpoints

**PR-006: API Error Taxonomy (RFC7807) & Input Validation**
- Files: `backend/app/core/errors.py`, `backend/app/core/validation.py`
- Dependencies: PR-001, PR-002, PR-003 (logging for error context)
- Time: 2 hours
- Checkpoint: POST with invalid data returns 422 with field errors
- ✅ Standardizes error responses across all routes

**PR-007: Secrets Management (dotenv → Vault/KMS rotation)**
- Files: `backend/app/core/secrets.py`
- Dependencies: PR-001, PR-002 (settings, env)
- Time: 1.5 hours
- Checkpoint: Secrets load from multiple providers; redaction verified
- ✅ Used by PR-011 (MT5 creds), PR-025 (Telegram token), PR-033 (Stripe key)

### TIER 0C — Observability & Audit

**PR-008: Audit Log & Admin Activity Trails**
- Files: `backend/app/audit/{models,service,middleware}.py`
- Dependencies: PR-001, PR-002, PR-003, PR-004 (auth for actor_id)
- Time: 2 hours
- Checkpoint: Create user → audit log entry; select from audit table
- ✅ Required by PR-022 (approvals), PR-025 (device changes), PR-033 (billing)

**PR-009: Observability Stack (metrics, traces, dashboards)**
- Files: `backend/app/observability/{metrics,tracing}.py`, Prometheus/Grafana configs
- Dependencies: PR-001, PR-002, PR-003 (logging, settings)
- Time: 2.5 hours
- Checkpoint: `GET /metrics` returns Prometheus output; Grafana loads
- ✅ Enables monitoring for all subsequent services

### TIER 0D — Database

**PR-010: Data Model Baseline (Postgres + Alembic migrations)**
- Files: `backend/app/core/db.py`, `backend/app/core/models.py`, `backend/alembic/env.py`, baseline migration
- Dependencies: PR-001, PR-002 (DB config, settings)
- Time: 2 hours
- Checkpoint: `alembic upgrade head` succeeds; `users` table exists with 5 rows
- ✅ Foundation for all domain tables (signals, approvals, trades, devices)

---

## PHASE 1A — TRADING CORE (Weeks 3–5)
**Goal**: Signals ingestion, strategy execution, trade recording  
**Exit Criteria**: Strategy → signal → approval → execution flow works end-to-end

### TIER 1A1 — MT5 & Data Infrastructure

**PR-011: MT5 Session Manager & Credentials Vaulting**
- Files: `backend/app/trading/mt5/{manager,health}.py`
- Dependencies: PR-007 (secrets), PR-002 (settings)
- Time: 2 hours
- Checkpoint: `MT5SessionManager.connect()` succeeds; health probe reports live
- ✅ Required by PR-013 (data fetch), PR-019 (trade monitoring), PR-023 (reconciliation)

**PR-012: Market Hours & Timezone Gating**
- Files: `backend/app/trading/time/{market_calendar,tz}.py`
- Dependencies: PR-001 (baseline)
- Time: 1 hour
- Checkpoint: `is_market_open("GOLD", friday_17_00)` returns False
- ✅ Required by PR-014 (strategy signal gating)

**PR-013: Data Pull Pipelines (H1/H15, windows, monitor bars)**
- Files: `backend/app/trading/data/{fetch,cache}.py`
- Dependencies: PR-011 (MT5 connection), PR-002 (settings)
- Time: 2 hours
- Checkpoint: `get_candles("GOLD", "H1", 200)` returns DataFrame with correct schema
- ✅ Required by PR-014 (strategy engine input)

### TIER 1A2 — Strategy & Order Logic

**PR-014: Fib-RSI Strategy Module (spec-locked to your logic)**
- Files: `backend/app/strategy/fib_rsi/{engine,indicators,schema}.py`
- Dependencies: PR-013 (data fetch), PR-012 (market gating)
- Time: 3 hours
- Checkpoint: Run against 200-bar GOLD H1 data → signal matches your script
- ✅ Core business logic; required by PR-021 (signals API)

**PR-015: Order Construction (entry/SL/TP/expiry, min stop distance)**
- Files: `backend/app/trading/orders/{builder,schema}.py`
- Dependencies: PR-014 (signal output), PR-002 (settings for RR ratio)
- Time: 1.5 hours
- Checkpoint: `build_order(signal)` returns OrderParams with valid RR
- ✅ Required by PR-021 (signal enrichment before storage)

**PR-016: Local Trade Store Migration (SQLite → Postgres)**
- Files: `backend/app/trading/store/{models,service}.py`, migration file
- Dependencies: PR-010 (DB baseline, Alembic)
- Time: 2 hours
- Checkpoint: Create trade → query trades; migration up/down clean
- ✅ Required by PR-023 (reconciliation)

### TIER 1A3 — Outbound Signal Delivery

**PR-017: Signal Serialization + HMAC Signing for Server Ingest**
- Files: `backend/app/trading/outbound/{client,hmac}.py`
- Dependencies: PR-007 (secrets for HMAC key)
- Time: 1.5 hours
- Checkpoint: POST to mock endpoint with correct HMAC signature
- ✅ Required by PR-019 (runtime loop posts signals)

**PR-018: Resilient Retries/Backoff & Telegram Error Alerts**
- Files: `backend/app/core/retry.py`, `backend/app/ops/alerts.py`
- Dependencies: PR-007 (Telegram token), PR-003 (logging)
- Time: 1.5 hours
- Checkpoint: Post fails 3x → alert sent to Telegram within 30s
- ✅ Required by PR-017 (outbound client retry), PR-019 (loop resilience)

### TIER 1A4 — Runtime & Monitoring

**PR-019: Live Trading Bot Enhancements (heartbeat, drawdown caps, analytics hooks)**
- Files: `backend/app/trading/runtime/{loop,events}.py`
- Dependencies: PR-011 (MT5), PR-014 (strategy), PR-015 (orders), PR-017 (posting), PR-018 (retries)
- Time: 2.5 hours
- Checkpoint: Run loop for 5 min → heartbeat logs + drawdown guard active
- ✅ Orchestrates trading workflow

**PR-020: Charting/Exports Refactor (matplotlib backend, caching)**
- Files: `backend/app/media/{render,storage}.py`
- Dependencies: PR-001, PR-002 (settings, cache config)
- Time: 2 hours
- Checkpoint: Render 500-bar chart → saved to disk, EXIF stripped
- ✅ Used by PR-025 (Telegram chart messages), PR-035 (Mini App charts)

---

## PHASE 1B — CORE APIs (Weeks 5–6)
**Goal**: Signal ingestion, approvals, trade monitoring  
**Exit Criteria**: Complete signal → approval → execution flow

### TIER 1B1 — Signal Ingestion

**PR-021: Signals API (ingest, schema, dedupe, payload limits)**
- Files: `backend/app/signals/{models,service,routes,schema}.py`, migration
- Dependencies: PR-010 (DB), PR-006 (validation/errors), PR-004 (auth/RBAC)
- Time: 2 hours
- Checkpoint: `POST /api/v1/signals` with valid HMAC returns 201
- ✅ Entry point for strategy signals

**PR-022: Approvals API (approve/reject, consent text versioning, audit)**
- Files: `backend/app/approvals/{models,service,routes,schema}.py`, migration
- Dependencies: PR-010 (DB), PR-021 (signals), PR-004 (auth), PR-008 (audit)
- Time: 2 hours
- Checkpoint: `POST /api/v1/approve {signal_id, decision}` records approval
- ✅ User interaction point for signal confirmation

### TIER 1B2 — Account Reconciliation & Risk Management

**PR-023: Account Reconciliation & Trade Monitoring (MT5 Position Sync + Auto-Close)**
- Files: `backend/app/trading/reconciliation/{models,service,routes}.py`, `backend/app/trading/monitoring/{drawdown_guard,liquidation}.py`, migration
- Dependencies: PR-011 (MT5), PR-016 (trade store), PR-021 (signals), PR-022 (approvals), PR-018 (alerts)
- Time: 3 hours
- Checkpoint: Place trade in MT5 manually → reconciliation detects it; 20% drawdown → auto-close logged
- ✅ **CRITICAL** for risk management; prevents catastrophic loss

---

## PHASE 1C — ORGANIC GROWTH (Week 6)
**Goal**: Referral system for user acquisition  
**Exit Criteria**: Affiliate tracking, commission payouts, dashboard live

### TIER 1C1 — Affiliate System

**PR-024: Affiliate & Referral System (Tracking, Payouts, Dashboards)**
- Files: `backend/app/affiliates/{models,service,routes,fraud}.py`, migration
- Dependencies: PR-010 (DB), PR-004 (auth), PR-008 (audit), PR-033 (payments, for payouts)
- Time: 2.5 hours
- Checkpoint: Generate referral code → share → signup with code → track event → payout scheduled
- ✅ Revenue driver; self-contained subdomain

---

## PHASE 1D — TELEGRAM BOT INTEGRATION (Weeks 6–7)
**Goal**: User-facing bot for approvals, billing, device management  
**Exit Criteria**: Shop, payments, approvals, device management all working via Telegram

### TIER 1D1 — Device & Device Management

**PR-025: Device Registry & Poll/Ack (Device registrations, HMAC keys, polling loop)**
- Files: `backend/app/clients/devices/{models,service,routes}.py`, migration
- Dependencies: PR-010 (DB), PR-004 (auth), PR-007 (secrets for keys), PR-008 (audit)
- Time: 2 hours
- Checkpoint: Register device → get HMAC key; `/poll` returns pending signals
- ✅ Required by PR-026 (exec store), PR-027 (Telegram webhook)

**PR-026: Execution Store (Device reports order fills/acks, reconcile with signals)**
- Files: `backend/app/clients/exec/{models,service,routes}.py`, migration
- Dependencies: PR-025 (device registry), PR-021 (signals), PR-016 (trades)
- Time: 1.5 hours
- Checkpoint: Device ACKs signal → `ack_signal(device_id, signal_id)` updates DB
- ✅ Closes EA feedback loop

### TIER 1D2 — Telegram Webhook & Commands

**PR-027: Telegram Webhook Router (webhook ingestion, routing by command)**
- Files: `backend/app/telegram/webhook.py`, `backend/app/telegram/router.py`
- Dependencies: PR-001, PR-002 (settings), PR-007 (Telegram token)
- Time: 1.5 hours
- Checkpoint: Telegram message → webhook → routes to correct handler
- ✅ Plumbing for all Telegram handlers

**PR-028: Telegram Catalog & Entitlements (Product catalog, tier permissions)**
- Files: `backend/app/billing/catalog/{models,service}.py`, `backend/app/billing/entitlements/{models,service}.py`, migration
- Dependencies: PR-010 (DB), PR-004 (auth/roles)
- Time: 2 hours
- Checkpoint: Load catalog; check `is_user_premium()` returns True/False correctly
- ✅ Required by PR-029 (pricing), PR-030 (shop)

**PR-029: Dynamic Quotes & Pricing (Real-time pricing, upsell rules)**
- Files: `backend/app/billing/pricing/{calculator,rules}.py`
- Dependencies: PR-028 (catalog), PR-013 (market data for fx rates)
- Time: 1.5 hours
- Checkpoint: Fetch price for tier → includes regional markup + affiliate bonus
- ✅ Required by PR-030 (shop checkout)

**PR-030: Telegram Shop & Checkout (Product list, order creation, payment flow)**
- Files: `backend/app/telegram/handlers/shop.py`, `backend/app/telegram/handlers/checkout.py`
- Dependencies: PR-027 (routing), PR-028 (catalog), PR-029 (pricing), PR-031 (payment)
- Time: 2 hours
- Checkpoint: `/shop` command → inline buttons → user clicks → checkout started
- ✅ User revenue entry point

**PR-031: Stripe Webhook Integration (Payment events, idempotent handling)**
- Files: `backend/app/billing/stripe/webhooks.py`, `backend/app/billing/stripe/handlers.py`
- Dependencies: PR-007 (secrets for Stripe key), PR-004 (auth), PR-008 (audit)
- Time: 2 hours
- Checkpoint: Simulate Stripe webhook → entitlement granted
- ✅ Required by PR-030 (checkout complete)

**PR-032: Telegram Payments (Telegram Stars integration, direct payment channel)**
- Files: `backend/app/telegram/payments.py`
- Dependencies: PR-027 (routing), PR-031 (payment handler)
- Time: 1.5 hours
- Checkpoint: Pay via Telegram Stars → entitlement granted same as Stripe
- ✅ Alternative payment channel for users without Stripe

**PR-033: Content Distribution & Marketing (Broadcast templates, CTA buttons, analytics)**
- Files: `backend/app/marketing/{broadcasts,templates,cta}.py`, `backend/app/telegram/handlers/marketing.py`
- Dependencies: PR-027 (routing), PR-002 (settings)
- Time: 1.5 hours
- Checkpoint: Send promotional message to cohort; track CTAs
- ✅ Required by PR-034 (guides), engagement driver

**PR-034: Guides & Reference (Onboarding guides, help commands, FAQ linking)**
- Files: `backend/app/telegram/handlers/guides.py`, `backend/app/knowledge/faq.py`
- Dependencies: PR-027 (routing)
- Time: 1 hour
- Checkpoint: `/help` → guides menu; user selects topic → content delivered
- ✅ UX polish, retention

---

## PHASE 2A — MINI APP & ANALYTICS (Weeks 7–8)
**Goal**: Web UX for mobile users; analytics warehouse  
**Exit Criteria**: Mini App approvals/billing/devices working; analytics dashboards live

### TIER 2A1 — Mini App Foundation

**PR-035: Mini App Auth & Initialization (OAuth bridge, session creation, device registration)**
- Files: `backend/app/oauth/mini_app.py`, `frontend/miniapp/auth.tsx`
- Dependencies: PR-004 (JWT), PR-025 (devices)
- Time: 2 hours
- Checkpoint: QR code → Mini App → JWT created; user authenticated
- ✅ Mini App entry point

**PR-036: Mini App Approvals UI (Signal approval interface, real-time updates)**
- Files: `frontend/miniapp/approvals.tsx`, `backend/app/telegram/api/approvals.py`
- Dependencies: PR-022 (approvals API), PR-035 (auth)
- Time: 2 hours
- Checkpoint: Mini App loads pending signals; click approve → API call succeeds
- ✅ Primary UX for approvals (vs. text commands)

**PR-037: Mini App Billing & Devices (Account settings, subscription view, device management)**
- Files: `frontend/miniapp/billing.tsx`, `frontend/miniapp/devices.tsx`
- Dependencies: PR-028 (entitlements), PR-025 (devices), PR-035 (auth)
- Time: 2 hours
- Checkpoint: View current tier; unlink/relink device; subscription countdown
- ✅ User settings hub

**PR-038: Mini App Payment Hardening (Idempotent checkout, retry logic, error recovery)**
- Files: `backend/app/billing/idempotency.py`, `frontend/miniapp/payment.tsx`
- Dependencies: PR-031 (Stripe), PR-038 (retry logic)
- Time: 1.5 hours
- Checkpoint: Pay → network fails → retry → idempotency key prevents double charge
- ✅ Critical for payment reliability

### TIER 2A2 — Account Linking & Live Positions

**PR-039: Account Linking (Telegram → MT5 mapping, multi-account support, consent)**
- Files: `backend/app/accounts/{models,service,routes}.py`, migration
- Dependencies: PR-010 (DB), PR-004 (auth), PR-025 (devices)
- Time: 1.5 hours
- Checkpoint: User links Telegram → MT5 account; can manage multiple accounts
- ✅ Multi-tenant foundation

**PR-040: Live Positions Display (Show open positions, equity, drawdown in Mini App)**
- Files: `backend/app/positions/{service,routes}.py`, `frontend/miniapp/positions.tsx`
- Dependencies: PR-039 (account linking), PR-011 (MT5 data), PR-023 (reconciliation)
- Time: 2 hours
- Checkpoint: Mini App → Positions tab shows live P&L
- ✅ Real-time engagement

### TIER 2A3 — Alerts & Automations

**PR-041: Price Alerts (Set price alerts for instruments, Telegram notifications)**
- Files: `backend/app/alerts/{models,service,routes}.py`, migration
- Dependencies: PR-010 (DB), PR-004 (auth), PR-013 (market data)
- Time: 1.5 hours
- Checkpoint: Set alert "GOLD > 2000" → price hits 2001 → Telegram alert sent
- ✅ Engagement loop

**PR-042: Owner Journeys & Automations (Custom workflows, scheduled actions)**
- Files: `backend/app/journeys/{models,service,routes}.py`, migration
- Dependencies: PR-010 (DB), PR-041 (alerts), PR-018 (scheduling/tasks)
- Time: 2 hours
- Checkpoint: Create journey "After first trade, send congratulations in 1 hour" → automation runs
- ✅ Retention driver

### TIER 2A4 — Analytics & Performance

**PR-043: Analytics Warehouse (Fact tables, dimension tables, ETL pipeline)**
- Files: `backend/app/analytics/{warehouse,etl}.py`
- Dependencies: PR-010 (DB), PR-016 (trades), PR-028 (subscriptions)
- Time: 2.5 hours
- Checkpoint: Run ETL → `dim_users`, `fact_trades` populated from operational DB
- ✅ Foundation for reporting

**PR-044: Performance Dashboards (Equity curves, win rates, drawdown, trade analytics)**
- Files: `backend/app/analytics/dashboards.py`, Grafana dashboards
- Dependencies: PR-043 (warehouse), PR-009 (Prometheus)
- Time: 2 hours
- Checkpoint: Navigate to dashboard → see equity curve, monthly returns
- ✅ User engagement tool

**PR-045: CSV/PNG Exports (Trade history, performance charts, compliance reporting)**
- Files: `backend/app/analytics/exports.py`
- Dependencies: PR-043 (warehouse), PR-020 (charting)
- Time: 1.5 hours
- Checkpoint: Click "Export trades" → CSV/PNG downloaded
- ✅ Compliance + user transparency

---

## PHASE 2B — COPY-TRADING & RISK (Weeks 8–9)
**Goal**: Copy-trading with risk enforcement; advanced risk controls  
**Exit Criteria**: Copy-trading toggle works; +30% markup applied; risk caps enforced

### TIER 2B1 — Copy-Trading

**PR-046: Copy-Trading Engine (Copy settings, +30% markup, risk/compliance enforcement)**
- Files: `backend/app/copytrading/{models,service,routes}.py`, migration
- Dependencies: PR-010 (DB), PR-015 (orders), PR-025 (devices), PR-023 (reconciliation)
- Time: 3 hours
- Checkpoint: Master trader places order → copy-trader gets signal at +30% markup; equity sync works
- ✅ Revenue multiplier; core feature for P2

### TIER 2B2 — Advanced Risk Controls

**PR-047: Paper Trading Mode (Simulate trades without real execution, backtesting integration)**
- Files: `backend/app/trading/paper/{engine,service}.py`, migration
- Dependencies: PR-014 (strategy), PR-016 (trade store), PR-013 (data)
- Time: 2 hours
- Checkpoint: Toggle paper mode on → trades not sent to MT5, recorded in separate table
- ✅ Risk mitigation; user education

**PR-048: Quotas & Rate Limiting on Trades (Max trades/day, max position size, cooldowns)**
- Files: `backend/app/trading/quotas/{models,service,enforcement}.py`, migration
- Dependencies: PR-010 (DB), PR-021 (signals)
- Time: 1.5 hours
- Checkpoint: User hits quota → signal rejected with clear reason
- ✅ Compliance + protection

---

## PHASE 2C — PUBLIC PERFORMANCE & SOCIAL (Weeks 9–10)
**Goal**: Public performance page, social proof, third-party transparency  
**Exit Criteria**: Public leaderboards, trust scoring, performance visible to prospects

### TIER 2C1 — Public Performance

**PR-049: Public Performance Page (Delayed equity curve, anon trader stats, top performers)**
- Files: `frontend/web/performance.tsx`, `backend/app/analytics/public.py`
- Dependencies: PR-043 (warehouse), PR-044 (dashboards)
- Time: 2 hours
- Checkpoint: Visit `/performance` → see top 10 traders by return (anonymized)
- ✅ Social proof for acquisition

**PR-050: Third-Party Performance Tracing (MyFXBook/Myfxbook integration, audit trail)**
- Files: `backend/app/analytics/tracing.py`
- Dependencies: PR-043 (warehouse), PR-008 (audit)
- Time: 1.5 hours
- Checkpoint: Export performance data to third-party → verified badge
- ✅ Trust signal

### TIER 2C2 — Social Features & Trust

**PR-051: Social Graph & Following (Follow traders, view their signals, trust scoring)**
- Files: `backend/app/social/{models,service,routes}.py`, migration
- Dependencies: PR-010 (DB), PR-049 (public performance)
- Time: 2 hours
- Checkpoint: Follow trader → see their recent signals; trust score calculates
- ✅ Engagement loop

**PR-052: Trust Index & Public Ledger (Transparent performance, fraud scoring, public audit)**
- Files: `backend/app/trust/{models,service,routes}.py`, migration
- Dependencies: PR-051 (social graph), PR-008 (audit)
- Time: 2 hours
- Checkpoint: View any trader's trust score + detailed audit trail
- ✅ Regulatory transparency

---

## PHASE 3A — AI & KNOWLEDGE (Weeks 10–12)
**Goal**: AI support, knowledge base, education  
**Exit Criteria**: AI assistant live; KB searchable; courses available; support tickets working

### TIER 3A1 — Knowledge & Support Foundation

**PR-053: Knowledge Base CMS (Store guides, FAQs, blog posts, multi-language)**
- Files: `backend/app/knowledge/{models,service,routes}.py`, migration
- Dependencies: PR-010 (DB)
- Time: 1.5 hours
- Checkpoint: Admin creates FAQ → appears in `/help` menu
- ✅ Foundation for PR-054 (AI RAG)

**PR-054: AI Support Assistant (RAG over KB, guardrails, escalation to human)**
- Files: `backend/app/ai/{embeddings,rag,guards}.py`
- Dependencies: PR-053 (KB), PR-018 (alerts for escalation)
- Time: 3 hours
- Checkpoint: User asks "How do I set a SL?" → AI retrieves relevant KB articles
- ✅ 24/7 support automation

**PR-055: Support Ticketing System (User → AI → tickets → agent routing)**
- Files: `backend/app/support/{models,service,routes}.py`, migration
- Dependencies: PR-054 (AI), PR-004 (auth), PR-008 (audit)
- Time: 2 hours
- Checkpoint: User escalates from AI → ticket created; agent notified
- ✅ Human escalation path

### TIER 3A2 — Education & Gamification

**PR-056: Education Courses & Quizzes (Course modules, progress tracking, completion certificates)**
- Files: `backend/app/education/{models,service,routes}.py`, migration
- Dependencies: PR-010 (DB), PR-053 (KB for content)
- Time: 2 hours
- Checkpoint: Complete course → certificate generated
- ✅ User skill building

**PR-057: Rewards & Gamification (Points, badges, leaderboards, referral bonuses)**
- Files: `backend/app/gamification/{models,service,routes}.py`, migration
- Dependencies: PR-056 (education), PR-051 (social)
- Time: 1.5 hours
- Checkpoint: Complete course → earn 100 points; redeem for discount
- ✅ Engagement multiplier

---

## PHASE 3B — STRATEGY ORCHESTRATION & QUALITY (Weeks 12–14)
**Goal**: Unified strategy system; backtesting; canary deployments  
**Exit Criteria**: Multi-strategy support; walk-forward testing; canary/shadow modes

### TIER 3B1 — Strategy Versioning & Deployment

**PR-058: Strategy Versioning & Canary Deployments (A/B test new versions, shadow mode)**
- Files: `backend/app/strategy/{versioning,canary}.py`, migration
- Dependencies: PR-014 (strategy), PR-047 (paper trading)
- Time: 2.5 hours
- Checkpoint: Deploy v2 to 10% of users; monitor metrics; roll forward/back
- ✅ Risk-free feature rollout

**PR-059: Strategy Decision Logs (Store every signal decision, inputs, outputs for audit)**
- Files: `backend/app/strategy/decisions.py`, migration
- Dependencies: PR-014 (strategy), PR-008 (audit)
- Time: 1.5 hours
- Checkpoint: Generate signal → decision log records all inputs/parameters
- ✅ Explainability

### TIER 3B2 — Backtesting & Research

**PR-060: Backtesting Engine (Walk-forward, optimization, metrics)**
- Files: `backend/app/research/backtest.py`
- Dependencies: PR-013 (data), PR-014 (strategy)
- Time: 3 hours
- Checkpoint: Run backtest 2020–2024 GOLD H1 → get CAGR/Sharpe
- ✅ Strategy validation

**PR-061: Walk-Forward Analysis (Out-of-sample testing, parameter stability)**
- Files: `backend/app/research/walk_forward.py`
- Dependencies: PR-060 (backtest)
- Time: 2 hours
- Checkpoint: Walk-forward test shows consistent OOS returns
- ✅ Overfitting protection

**PR-062: Research & Feature Store (A/B test ideas, feature engineering, experimentation)**
- Files: `backend/app/research/{features,experiments}.py`, migration
- Dependencies: PR-060 (backtest), PR-058 (canary)
- Time: 2 hours
- Checkpoint: Engineer new indicator → add to feature store → test on historical data
- ✅ Innovation engine

### TIER 3B3 — Strategy Quality

**PR-063: Strategy Decision Explainability (Why was this signal generated? Feature contribution)**
- Files: `backend/app/strategy/explain.py`
- Dependencies: PR-059 (decision logs)
- Time: 1.5 hours
- Checkpoint: Signal → explain endpoint returns feature importance scores
- ✅ Trust transparency

**PR-064: Unified Risk Management (Sharpe ratio gates, correlation checks, portfolio limits)**
- Files: `backend/app/trading/risk/unified.py`
- Dependencies: PR-023 (reconciliation), PR-048 (quotas)
- Time: 2 hours
- Checkpoint: Portfolio correlation with copy-trader > 0.9 → reject new trade
- ✅ Systemic risk control

**PR-065: Performance Attribution (What drove profits? Strategy, copy traders, affiliates)**
- Files: `backend/app/analytics/attribution.py`
- Dependencies: PR-043 (warehouse), PR-046 (copytrading), PR-024 (affiliates)
- Time: 1.5 hours
- Checkpoint: Query "What drove Q4 profit?" → breakdown by source
- ✅ Business intelligence

---

## PHASE 3C — GLOBALIZATION & PRIVACY (Weeks 14–15)
**Goal**: Multi-language support; GDPR compliance; privacy center  
**Exit Criteria**: UI fully internationalized; DSAR working; privacy center live

### TIER 3C1 — Internationalization

**PR-066: i18n Infrastructure (Translation strings, language selection, RTL support)**
- Files: `backend/app/i18n/{models,service}.py`, `frontend/i18n.ts`, translations/*.json
- Dependencies: PR-001 (baseline)
- Time: 2 hours
- Checkpoint: Select language → UI updates; Telegram bot messages translated
- ✅ Global market access

**PR-067: Regional Compliance & Pricing (GDPR, FCA, CFTC rules, regional pricing tiers)**
- Files: `backend/app/compliance/{models,service}.py`
- Dependencies: PR-029 (pricing)
- Time: 2 hours
- Checkpoint: User in EU → FCA warnings shown; leverage caps applied
- ✅ Regulatory adherence

### TIER 3C2 — Privacy & Data

**PR-068: Privacy Center & DSAR (Data export, deletion, retention policies)**
- Files: `backend/app/privacy/{models,service,routes}.py`
- Dependencies: PR-010 (DB), PR-004 (auth), PR-008 (audit)
- Time: 2 hours
- Checkpoint: User requests DSAR → export generated in 7 days; deletion approved
- ✅ GDPR compliance

**PR-069: Backup & Disaster Recovery (Snapshots, point-in-time recovery, failover)**
- Files: `ops/backup.sh`, `ops/restore.sh`, `backend/app/health/dr.py`
- Dependencies: PR-001 (Docker), PR-010 (DB)
- Time: 1.5 hours
- Checkpoint: Restore from backup → DB consistent; data correct
- ✅ Business continuity

---

## PHASE 3D — WEB PLATFORM & DASHBOARD (Weeks 15–17)
**Goal**: Next-gen web interface; SEO; advanced features  
**Exit Criteria**: Web platform live; search engine indexed; responsive design

### TIER 3D1 — Web Foundation

**PR-070: Web Platform Foundation (Next.js app, design system, responsive layout)**
- Files: `frontend/web/`, `frontend/packages/ui/`
- Dependencies: PR-001 (baseline)
- Time: 2.5 hours
- Checkpoint: `npm run dev` → web app loads; design system components render
- ✅ Web UX foundation

**PR-071: SEO & CDN (Meta tags, sitemap, CDN caching, Core Web Vitals)**
- Files: `frontend/web/seo.ts`, `frontend/middleware.ts`, vercel.json
- Dependencies: PR-070 (web)
- Time: 1.5 hours
- Checkpoint: Google bot crawls site; Core Web Vitals > 90
- ✅ Organic traffic

**PR-072: Telegram OAuth & Deep Linking (TG login, share links, bot command auto-population)**
- Files: `backend/app/oauth/telegram.py`, `frontend/web/auth.tsx`
- Dependencies: PR-027 (Telegram webhook)
- Time: 2 hours
- Checkpoint: Click "Login with Telegram" → auth complete; deep link populates form
- ✅ Seamless TG ↔ web integration

### TIER 3D2 — Web Dashboards

**PR-073: Web Dashboard (Portfolio overview, equity curve, signals, approvals)**
- Files: `frontend/web/dashboard.tsx`
- Dependencies: PR-070 (web), PR-040 (positions), PR-036 (approvals UI)
- Time: 2 hours
- Checkpoint: Desktop user sees full portfolio with equity chart
- ✅ Power user interface

**PR-074: Web Admin Panel (User management, billing, feature flags, incidents)**
- Files: `frontend/web/admin/`, `backend/app/admin/routes.py`
- Dependencies: PR-070 (web), PR-028 (catalog), PR-065 (attribution)
- Time: 2.5 hours
- Checkpoint: Admin logs in → can view all users, toggle features
- ✅ Operations hub

**PR-075: Web Settings & Preferences (Profile, notifications, integrations, 2FA)**
- Files: `frontend/web/settings.tsx`, `backend/app/prefs/routes.py`
- Dependencies: PR-070 (web), PR-041 (alerts), PR-066 (i18n)
- Time: 1.5 hours
- Checkpoint: User changes timezone preference → timestamps render correctly everywhere
- ✅ Personalization

### TIER 3D3 — Advanced Web Features

**PR-076: AI Insights & Outlook (AI-generated market outlook, signal recommendations)**
- Files: `frontend/web/insights.tsx`, `backend/app/ai/insights.py`
- Dependencies: PR-054 (AI), PR-044 (dashboards)
- Time: 2 hours
- Checkpoint: Dashboard shows "AI Outlook: ↑ Technical setup forming on GOLD daily"
- ✅ Value-add content

**PR-077: Anomaly Detection & Alerts (Unusual account activity, suspicious trades)**
- Files: `backend/app/fraud/anomaly.py`
- Dependencies: PR-043 (warehouse), PR-041 (alerts)
- Time: 1.5 hours
- Checkpoint: Unusual 100-lot trade → user alerted
- ✅ Fraud protection

**PR-078: Ledger & Transaction History (Complete money trail, audit-ready exports)**
- Files: `backend/app/ledger/{models,service,routes}.py`, migration
- Dependencies: PR-010 (DB), PR-031 (payments), PR-024 (affiliates)
- Time: 2 hours
- Checkpoint: View ledger → see all debits/credits with references
- ✅ Compliance + transparency

---

## PHASE 3E — PARTNERS & OPERATIONS (Weeks 17–19)
**Goal**: Affiliate portal; admin automation; autonomous health checking  
**Exit Criteria**: Partners can manage payouts; admin portal runs business; health auto-heals

### TIER 3E1 — Partner Portal

**PR-079: Affiliate Portal (Earn tracking, payout requests, performance reports)**
- Files: `frontend/web/affiliate/`, `backend/app/affiliates/routes.py`
- Dependencies: PR-024 (affiliates), PR-073 (dashboards)
- Time: 1.5 hours
- Checkpoint: Affiliate logs in → sees earnings, clicks payout → request submitted
- ✅ Partner self-service

**PR-080: CRM & Campaign Management (Lead tracking, email templates, campaigns)**
- Files: `backend/app/crm/{models,service}.py`, migration
- Dependencies: PR-010 (DB)
- Time: 2 hours
- Checkpoint: Create campaign "Holiday Sale" → send emails to segment
- ✅ Growth automation

### TIER 3E2 — Autonomous Operations

**PR-081: Health Checks & Synthetic Monitoring (Endpoint probes, alerting, auto-remediation)**
- Files: `backend/app/health/{synthetics,remediator}.py`
- Dependencies: PR-009 (observability), PR-018 (alerts)
- Time: 2 hours
- Checkpoint: API endpoint stops responding → health check fails → auto-remediation kicks in
- ✅ 99.9% uptime

**PR-082: Incident Management & Escalation (Auto-incident creation, on-call routing)**
- Files: `backend/app/health/incidents.py`
- Dependencies: PR-081 (health), PR-018 (alerts)
- Time: 1.5 hours
- Checkpoint: Critical metric crosses threshold → incident created; on-call notified
- ✅ Fast MTTR

### TIER 3E3 — Admin Operations

**PR-083: Admin Portal & Business Controls (User suspensions, refunds, feature toggles)**
- Files: `frontend/web/admin/controls.tsx`, `backend/app/admin/controls.py`
- Dependencies: PR-074 (admin panel), PR-078 (ledger)
- Time: 2 hours
- Checkpoint: Admin suspends user → all accounts locked; issue refund → ledger updated
- ✅ Full operational control

**PR-084: Autonomous Reporting & Dashboards (Daily reports, KPI dashboards, alerts)**
- Files: `backend/app/reporting/`, Grafana dashboards
- Dependencies: PR-043 (warehouse), PR-065 (attribution)
- Time: 1.5 hours
- Checkpoint: Daily email with KPIs; CEO dashboard shows MRR/ARR/churn
- ✅ Business visibility

---

## PHASE 3F — ADVANCED FEATURES & OPTIMIZATION (Weeks 19–21)
**Goal**: Feature completeness; performance optimization; edge cases  
**Exit Criteria**: All major features complete; load tested; ready for production scale

### TIER 3F1 — Advanced Trading

**PR-085: Multi-Strategy Support (Run multiple strategies, correlation checks, position limits)**
- Files: `backend/app/strategy/{orchestrator,multi}.py`
- Dependencies: PR-014 (strategy), PR-064 (risk)
- Time: 2.5 hours
- Checkpoint: Run Fib-RSI + another strategy simultaneously; risk limits enforced
- ✅ Strategy diversification

**PR-086: Algo Order Types (VWAP, TWAP, iceberg orders, smart order routing)**
- Files: `backend/app/trading/algos/`
- Dependencies: PR-015 (orders)
- Time: 2 hours
- Checkpoint: Place VWAP order → executes intelligently across time
- ✅ Execution optimization

**PR-087: Drawdown Recovery Automations (Scale down after DD, scale up after profit)**
- Files: `backend/app/trading/recovery/`
- Dependencies: PR-023 (reconciliation)
- Time: 1.5 hours
- Checkpoint: Hit 15% DD → auto-reduce position size; recovery → auto-increase
- ✅ Risk adaptation

### TIER 3F2 — Analytics & Reporting

**PR-088: Real-Time Data Warehouse (Streaming updates, sub-second latency)**
- Files: `backend/app/analytics/streaming.py`
- Dependencies: PR-043 (warehouse)
- Time: 2 hours
- Checkpoint: Dashboard updates live without page refresh
- ✅ Real-time insight

**PR-089: Custom Report Builder (Drag-and-drop metrics, scheduled exports)**
- Files: `backend/app/analytics/builder.py`
- Dependencies: PR-043 (warehouse)
- Time: 1.5 hours
- Checkpoint: User drags metrics → builds custom report → schedules delivery
- ✅ Self-service reporting

**PR-090: Compliance & Audit Reports (Generated on-demand, signed exports)**
- Files: `backend/app/compliance/reporting.py`
- Dependencies: PR-078 (ledger), PR-008 (audit)
- Time: 1.5 hours
- Checkpoint: Generate audit report → signed PDF with compliance marks
- ✅ Regulatory readiness

### TIER 3F3 — Content & UX Polish

**PR-091: Dynamic Content & Personalization (AI-selected content, user preferences)**
- Files: `backend/app/marketing/personalization.py`
- Dependencies: PR-054 (AI), PR-075 (preferences)
- Time: 1.5 hours
- Checkpoint: Each user sees personalized content based on behavior/preferences
- ✅ Engagement optimization

**PR-092: In-App Notifications & Toast Messages (Unread badge, sound alerts, persistence)**
- Files: `backend/app/messaging/notifications.py`, `frontend/ui/notifications.tsx`
- Dependencies: PR-075 (preferences)
- Time: 1 hour
- Checkpoint: Signal approved → toast shown; unread count updated
- ✅ UX responsiveness

**PR-093: Mobile Responsiveness (Touch optimization, viewport fixes, offline mode)**
- Files: `frontend/web/responsive.ts`, service worker
- Dependencies: PR-070 (web)
- Time: 1.5 hours
- Checkpoint: Mobile user approves signal with one tap; works offline
- ✅ Full mobile support

### TIER 3F4 — Performance & Scaling

**PR-094: Database Query Optimization (Indexes, query plans, caching strategies)**
- Files: Backend performance improvements, migration optimizations
- Dependencies: PR-010 (DB)
- Time: 1.5 hours
- Checkpoint: /dashboard loads < 100ms; p99 < 200ms
- ✅ Fast UX

**PR-095: API Response Caching (Redis layer, cache invalidation, CDN)**
- Files: `backend/app/core/cache.py`
- Dependencies: PR-001 (Redis)
- Time: 1 hour
- Checkpoint: Frequently accessed endpoints return from cache; validation correct
- ✅ Throughput multiplier

**PR-096: Load Testing & Capacity Planning (k6 tests, traffic simulation, bottleneck analysis)**
- Files: `ops/load_tests/`, k6 scripts
- Dependencies: All of P3
- Time: 2 hours
- Checkpoint: Run 10k concurrent users → system handles gracefully
- ✅ Production readiness

---

## PHASE 3G — OPTIONAL & FUTURE (Weeks 21+)
**Goal**: Advanced features, experimental, nice-to-haves  
**Exit Criteria**: Feature-flagged; ready for future rollout or deprecation

### TIER 3G1 — Experimental

**PR-097: NFT Access Control (NFT holders get premium tier, blockchain verification)**
- Files: `backend/app/web3/{nft_verify,access}.py`
- Dependencies: PR-028 (entitlements), PR-067 (compliance)
- **Status**: FEATURE-FLAGGED OFF by default
- Time: 2 hours
- Checkpoint: Deploy with flag=false; verify endpoint access blocked
- ⚠️ High compliance risk; staging only

**PR-098: Social Trading (Copy specific traders, sentiment analysis, consensus trades)**
- Files: `backend/app/social/copying.py`, `backend/app/ai/sentiment.py`
- Dependencies: PR-051 (social graph), PR-046 (copytrading)
- Time: 2 hours
- Checkpoint: Follow trader → auto-copy all their signals
- ✅ Engagement multiplier

**PR-099: Voice/Audio Commands (Transcribe Telegram audio, execute trades via voice)**
- Files: `backend/app/telegram/voice.py`
- Dependencies: PR-027 (Telegram routing)
- Time: 1.5 hours
- Checkpoint: Record audio "buy GOLD" → transcribe → execute
- ✅ Accessibility

**PR-100: ML Model Observability (Track model drift, retraining triggers, A/B test results)**
- Files: `backend/app/ml/observability.py`
- Dependencies: PR-054 (AI), PR-058 (canary)
- Time: 1 hour
- Checkpoint: Monitor model performance; alert on degradation
- ✅ ML ops

### TIER 3G2 — Future / Out-of-scope

* **PR-101+**: Additional integrations (Binance API, other brokers), advanced ML models, blockchain features

---

## BUILD SEQUENCING RULES

### **MUST-DO IN ORDER** (Critical path)
```
PR-001 → PR-002 → PR-003 → PR-004 → PR-005 → PR-006
    ↓
   PR-007 → PR-008 → PR-009 → PR-010
        ↓
PR-011 → PR-012 → PR-013 → PR-014 → PR-015 → PR-016 → PR-017 → PR-018 → PR-019
    ↓
PR-021 → PR-022 → PR-023
    ↓
PR-025 → PR-027 → PR-028 → PR-029 → PR-030 → PR-031
```

### **CAN PARALLELIZE** (Independent work)
* **PR-005, PR-006, PR-007, PR-008, PR-009** can run in parallel (all depend on PR-001, PR-002, PR-003)
* **PR-011, PR-012** can run in parallel (independent utilities)
* **PR-025, PR-027, PR-028** can partially overlap (slight reordering OK)
* **PR-035–PR-042** can run partially in parallel (each depends on different P1 components)
* **PR-053–PR-057** fully parallelizable (AI/education independent)
* **PR-066–PR-069** fully parallelizable (i18n, compliance independent)
* **PR-070–PR-078** web features can overlap (different pages/features)

### **DO NOT START UNTIL** (Dependency blocking)
* Don't start PR-014 until PR-012, PR-013 complete
* Don't start PR-021 until PR-010, PR-014, PR-015 complete
* Don't start PR-023 until PR-021, PR-022, PR-011, PR-016 complete
* Don't start PR-035 until PR-004, PR-025 complete
* Don't start PR-046 until PR-010, PR-015, PR-025 complete
* Don't start Phase 2A until all Phase 1 complete (Mini App depends on APIs)
* Don't start Phase 3 until Phase 2 complete (Web depends on analytics)

---

## VALIDATION CHECKPOINTS

### After Phase 0 (Foundations)
```
✅ CI/CD green on all commits
✅ /health endpoint live
✅ /metrics endpoint accessible
✅ Database connected; alembic head applied
✅ JWT login works
✅ Rate limiting active
✅ Error responses RFC7807 compliant
✅ Secrets loading from provider
✅ Audit log table exists
```

### After Phase 1A (Trading Core)
```
✅ MT5 connection established
✅ Market calendar gating works
✅ Data fetch returns correct schema
✅ Strategy generates signals (golden tests)
✅ Orders build with correct parameters
✅ Trade records stored in Postgres
✅ HMAC signatures valid
✅ Retry logic triggers on failure
✅ Heartbeat logs appear; drawdown guard blocks
```

### After Phase 1B (APIs)
```
✅ Signals API receives POST requests
✅ Signals deduplicate correctly
✅ Approvals record user decisions
✅ Reconciliation detects position matches
✅ Drawdown guards auto-close positions
```

### After Phase 1C (Affiliates)
```
✅ Referral codes generate
✅ Signup with code tracked
✅ Commission calculates correctly
```

### After Phase 1D (Telegram)
```
✅ Device registers and gets HMAC key
✅ `/poll` returns pending signals
✅ Device ACKs signal
✅ Telegram webhook routes correctly
✅ Catalog loads
✅ Shop shows products
✅ Stripe checkout works
✅ Entitlements grant after payment
```

### After Phase 2A (Mini App)
```
✅ OAuth flow completes
✅ Mini App approves signals
✅ Positions display real-time
✅ Analytics warehouse populated
✅ Dashboards render
✅ Exports generate correctly
```

### After Phase 2B (Copy-Trading)
```
✅ Copy-trading toggle works
✅ +30% markup applied
✅ Risk limits enforced
✅ Paper mode isolates trades
✅ Quotas block excess
```

### After Phase 2C (Public Performance)
```
✅ Public page shows performance
✅ Social features work
✅ Trust index calculates
```

### After Phase 3A (AI/Knowledge)
```
✅ KB searchable
✅ AI assistant responds
✅ Tickets escalate to human
✅ Courses completable
✅ Rewards/badges grant
```

### After Phase 3B (Strategy Quality)
```
✅ Strategy versioning works
✅ Canary deployments control rollout
✅ Backtest engine returns metrics
✅ Walk-forward testing validates
```

### After Phase 3C (Globalization)
```
✅ UI fully translated
✅ Regional pricing applied
✅ DSAR export/delete works
✅ Backup/restore tested
```

### After Phase 3D (Web)
```
✅ Web app loads
✅ Dashboard fully functional
✅ Admin panel operates
✅ Settings personalize
```

### After Phase 3E (Operations)
```
✅ Health checks auto-remediate
✅ Incidents escalate
✅ Admin controls suspend/refund
✅ Daily reports deliver
```

### After Phase 3F (Optimization)
```
✅ Multi-strategy support
✅ Real-time warehouse live
✅ Custom reports build
✅ Compliance reports generate
✅ Performance tests pass
```

### Before Production Cutover
```
✅ Load test: 10k concurrent users
✅ Security scan: 0 critical vulnerabilities
✅ Backup/restore: tested in staging
✅ Incident response: runbook validated
✅ GDPR: DSAR flow confirmed working
✅ All 96 PRs implemented and tested
✅ Rollout plan with feature flags
✅ Documentation complete (runbooks, API docs)
```

---

## RISK MITIGATION

| Phase | Risk | Mitigation |
|-------|------|-----------|
| P0 | Secrets leak to CI/CD logs | PR-007 secrets provider + log redaction (PR-003) |
| P1A | MT5 connection fails | Circuit breaker + backoff (PR-011, PR-018) |
| P1B | Signal loss → incomplete trade | Audit log (PR-008) + idempotency on acks |
| P1D | Telegram webhook spam | Rate limiting (PR-005) + IP allowlist |
| P2A | Mini App auth token leakage | Short TTL + refresh token rotation |
| P2B | Copy-trader losses | +30% markup + risk caps (PR-046) |
| P3A | AI hallucinations | Guardrails + human escalation (PR-054) |
| P3B | Overfitted strategy backtest | Walk-forward testing (PR-061) |
| P3D | Web DDoS | WAF + rate limiting + CDN caching |
| P3E | Auto-remediation cascades failure | Manual override + escalation (PR-082) |

---

## EFFORT ESTIMATES

| Phase | Duration | Team Size | Total Effort |
|-------|----------|-----------|------------|
| P0 (PR-001–010) | 2 weeks | 2 | 80 hours |
| P1A (PR-011–020) | 2 weeks | 2 | 85 hours |
| P1B (PR-021–023) | 1 week | 2 | 45 hours |
| P1C (PR-024) | 3 days | 1 | 20 hours |
| P1D (PR-025–034) | 2 weeks | 3 | 100 hours |
| P2A (PR-035–045) | 2 weeks | 3 | 95 hours |
| P2B (PR-046–048) | 1 week | 2 | 50 hours |
| P2C (PR-049–052) | 1 week | 2 | 45 hours |
| P3A (PR-053–057) | 1.5 weeks | 2 | 60 hours |
| P3B (PR-058–065) | 1.5 weeks | 2 | 65 hours |
| P3C (PR-066–069) | 1 week | 2 | 40 hours |
| P3D (PR-070–078) | 2 weeks | 2 | 75 hours |
| P3E (PR-079–084) | 1.5 weeks | 2 | 60 hours |
| P3F (PR-085–096) | 2 weeks | 2 | 80 hours |
| P3G (PR-097–100) | 1 week | 1 | 30 hours |
| **TOTAL** | **~22 weeks** | **2–3 avg** | **985 hours** |

**Translation**: ~5–6 months for full platform with 2–3 developers

---

## NEXT STEPS

1. **Decide on team structure** (1 full-stack, 2 backend, 1 frontend, etc.)
2. **Confirm Phase 0 PRs** are your starting point (infrastructure must be done first)
3. **Begin with PR-001** (monorepo bootstrap)
4. **Follow dependency graph** when parallelizing work
5. **Validate after each checkpoint** before moving to next tier
6. **Track progress** using GitHub Projects (one card per PR)
7. **Update this document** as new PRs or dependencies emerge

---

**Status**: READY FOR IMPLEMENTATION  
**Last Updated**: October 24, 2025  
**Maintainer**: GitHub Copilot + Team

