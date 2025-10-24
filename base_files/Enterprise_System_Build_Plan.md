
# Enterprise_System_Build_Plan.md

## 0) How to use this document

* Treat each **PR** below as one GitHub Pull Request with its own checklist.
* Follow the **phase roadmap** for execution order.
* Use the **dependency graph** to parallelize safely.
* Copy the **repo layout & conventions** so Copilot consistently scaffolds files.

---

## 1) Repo layout (monorepo)

```
/backend/                # FastAPI services, workers, schedulers
  app/
    core/                # settings, db, errors, logging, rate-limit, secrets, idempotency
    auth/                # JWT, RBAC
    observability/       # metrics, tracing, health
    audit/               # audit log
    gateway/             # edge routes + legacy shims
    signals/ approvals/  # ingestion + approvals
    clients/ ea/         # device registry, poll/ack, crypto, exec store
    trading/ strategy/   # mt5 session, data, orders, loops, versioning
    analytics/           # warehouse, equity, metrics, buckets, routes
    billing/ pricing/    # catalog, entitlements, stripe, webhooks, gates
    telegram/            # webhook router, handlers, payments, i18n
    marketing/           # broadcasts, CTA, clicks
    prefs/ messaging/    # preferences + multi-channel messaging
    kb/ ai/ support/     # knowledge base, assistant (RAG), ticketing
    education/           # courses, quizzes, rewards
    risk/ paper/ quotas/ # risk guards, sandbox, quotas
    trust/               # tracer, ledger, social graph, public trust index
    features/ explain/   # feature store, quality, explainability
    research/ backtest/  # walk-forward, promotion, backtest
    copytrading/         # copy settings, risk/compliance
    revenue/ exports/    # MRR/ARR cohorts, CSV/PNG exports
    accounts/ positions/ # linking, live positions
    alerts/ journeys/    # price alerts, owner automations
    health/              # synthetics, remediator, incidents
    oauth/ miniapp/      # TG OAuth + WebApp JWT bridge
    web3/                # NFT access (flagged, staging only)
  alembic/               # migrations
  schedulers/            # cron/queue runners
  media/                 # chart renderer + cache
/frontend/
  miniapp/               # Telegram Mini App (Next.js)
  web/                   # Marketing + dashboard (Next.js)
  packages/ui/           # shared design system (charts, cards, meters)
/ea-sdk/                 # MQL5 SDK + ReferenceEA
/grafana/ prometheus/    # dashboards & scrape
/ops/                    # backups, promote, infra scripts
/docs/                   # runbooks, permissions, style guides
```

---

## 2) Engineering conventions

* **Python 3.11**, **FastAPI**, SQLAlchemy 2.0 + Alembic, Redis for rate-limit & queues.
* **Type safety**: mypy; **style**: ruff+black+isort; **tests**: pytest + coverage ≥ 90%.
* **Secrets**: PR-007 providers (Vault/KMS in prod).
* **Logging**: JSON structured with `request_id` (PR-003).
* **Errors**: RFC7807 problem+json (PR-006).
* **Observability**: OpenTelemetry + Prometheus (PR-009).
* **RBAC**: owner/admin/user (PR-004).
* **Security**: HMAC on producer/device, AEAD encryption to EA, idempotency on webhooks/payments.

---

## 3) Phase roadmap (P0 → P3)

### P0 — Foundations (ship in 1–2 sprints)

* **PR-001 → PR-010** (monorepo, settings, logging, auth, rate-limit, errors, secrets, audit, observability, DB baseline)

**Exit criteria**

* CI green; /health, /ready, /metrics live; JWT login works; Alembic baseline applied.

---

### P1 — Trading core, ingestion, Telegram, payments (parallelizable)

* **PR-011 → PR-022** (MT5 session; market gating; data; Fib-RSI engine; order builder; trade store; HMAC producer; retries/alerts; runtime guards; charting; Signals API; Approvals)
* **NEW PR-023** (Account reconciliation & trade monitoring: position sync, drawdown guards, auto-close)
* **NEW PR-024** (Affiliate & referral system: tracking, payouts, dashboards)
* **PR-025 → PR-036** (Device registry; EA poll/ack; execution store; Telegram webhook/router/commands; catalog/entitlements; dynamic quotes; content distribution; guides; marketing; Stripe/Telegram payments)

**Exit criteria**

* Signals flow: strategy → signed POST → stored → user approves → EA polls → executes → ack stored.
* Telegram shop online with Stripe test mode; entitlements gate premium routes.

---

### P2 — Mini App + Copy-trading + Analytics + Web

* **PR-035 → PR-046** (Mini App auth+UI: approvals/billing/devices; payment hardening; EA SDK; encrypted transport; positions+account link; price alerts; copy-trading + +30% markup and risk/compliance)
* **PR-047 → PR-058** (public performance; third-party tracer; trust scoring & index; analytics warehouse/equity/metrics/heatmaps; client analytics UI; revenue KPIs; exports; Grafana panels)

**Exit criteria**

* Mini App is primary UX for clients; copy-trading toggle works with risk caps; analytics charts/rendering and exports working; public performance page online (post-close).

---

### P3 — AI, Education, Owner automation, Globalization, Final polish

* **PR-059 → PR-070** (preferences; messaging bus; KB CMS; AI support + tickets; education+quizzes; smart alerts; owner journeys; backups/DR; privacy center; i18n across web+bots)
* **PR-071 → PR-083** (strategy orchestrator incl. PPO; precise new-candle; decision logs; unified risk; trading controls; backtests; walk-forward; versioning/canary/shadow; feature store; explainability; paper-trading; quotas; Flask decommission)
* **PR-084 → PR-095** (web platform, TG OAuth/deep links, SEO/CDN; next-gen web dashboard; gamification; web education hub; themes; AI outlook; fraud/anomaly; ledger; social graph; public trust)
* **PR-096 → PR-101** (affiliates; AI upsell; CRM automations; admin portal; autonomous health; AI reports)
* **PR-102** (NFT access prototype — **feature-flagged OFF**)

**Exit criteria**

* 24/7 AI support + human escalation; education hub live; internationalized UI/bots; paper-trading & quotas; admin portal operating business end-to-end; health auto-healing; AI reports delivered.

---

## 4) Dependency graph (high-level)

```
P0: [001..010]
   └─▶ P1A Trading Core [011..022] ─┐
                                     ├─▶ P1B Account Reconciliation [023] ◀─ (Risk Management)
P1B Telegram+Billing [025..036] ─────┤
                                     ├─▶ P1C Affiliate System [024] (Organic Growth)
P1C Catalog/Entitlements [028..029,033..034] ──┐
                                               ├─▶ P2A Mini App [035..039]
P2C Analytics [051..055] ───────────────────────┤
                                                ├─▶ P2B Copy/Risk [045..046]
P2E EA SDK/Security [041..042] ─────────────────┘
P3A AI/KB/Tickets [061..063,091,101] ◀─ Analytics
P3B Education/Alerts [064..065,089]  ◀─ KB, Messaging
P3C Owner Automations/DR [066..067,098] ◀─ Messaging, Revenue
P3D Globalization/Privacy [068..070]
P3E Research/Quality [071..080]
P3G Web Platform/SEO/TG OAuth [084..086] → Dashboards [087..090]
P3H Partners/Upsell/Admin/Health [096..100]
P3I NFT Prototype [102] (isolated; optional)
```

---

## 5) Security & compliance highlights (must-haves before production)

* **AuthN/Z**: RS256 JWT; short-lived Mini App tokens; RBAC checks on every admin route.
* **Transport & integrity**: HMAC (producer/device); **AEAD** encryption to EA.
* **Payments**: idempotency + webhook replay protection; PCI scope limited to Stripe Portal/Checkout.
* **Privacy/GDPR**: DSAR export/delete center (PR-068); audit logs append-only (PR-008).
* **Rate-limits & quotas**: IP rate-limit (PR-005) + feature quotas (PR-082).
* **Secrets**: prod must use Vault/KMS provider (PR-007).
* **Observability**: golden signals + business KPIs + alerts (PR-009, PR-058, PR-100).

---

## 6) Testing strategy

* **Unit** per module with fixtures (≥90% coverage).
* **Integration**: MT5 mocked; Stripe test; Telegram webhook simulator.
* **E2E**: strategy→signal→approval→EA poll/ack; shop→checkout→entitlement; Mini App flows.
* **Load/chaos**: burst against poll/ack & webhooks; kill services to validate PR-100 remediations.
* **Data parity**: backtest vs live metrics parity checks (PR-076/052/053).

---

## 7) Operational runbooks (docs/)

* **deploy.md**: promote script (ops/promote/release.sh), DB migrations, cache warm.
* **incidents.md**: how synthetics escalate & self-heal; manual overrides.
* **billing.md**: refund/credit flows; dunning; disputes.
* **privacy.md**: DSAR export/delete; retention periods.
* **bots.md**: setting webhook secrets, rotating tokens, IP allowlist.
* **ea.md**: device registration, HMAC keys, AEAD rotation, ReferenceEA settings.

---

## 8) Acceptance criteria per phase (summary)

**P0**

* All core rails in place; unit tests green; metrics visible; non-root containers.

**P1**

* Signals ingestion end-to-end; approvals recorded; EA executes and acks; Telegram shop with Stripe test flow; entitlements gate.

**P2**

* Mini App drives daily use (approvals/billing/devices).
* Copy-trading auto path with +30% markup & risk caps.
* Analytics warehouse + dashboards + exports live.
* Public performance page (delayed) + third-party tracing.

**P3**

* AI support (RAG) + tickets; education & quizzes w/ rewards.
* Paper trading mode, quotas, canary/shadow strategies.
* Admin portal runs the business; autonomous health fixes outages.
* Internationalized product; privacy center; AI reports delivered.
* (Optional) NFT access internally demoed, **flag OFF**.

---

## 9) Issue labels & PR template

**Labels**: `area:trading`, `area:telegram`, `area:miniapp`, `area:analytics`, `area:billing`, `area:ai`, `area:infra`, `type:feature`, `type:bug`, `type:refactor`, `security`, `docs`, `breaking`
**PR template**:

* Summary
* Linked PRs / dependencies
* Screenshots / API examples
* Rollout plan & feature flags
* Metrics to watch & alerts
* Test plan (unit/integration/e2e)
* Security/Privacy notes

---

## 10) Phase-by-phase “go live” checklist (abridged)

**Before P1 prod toggle**

* Stripe webhooks verified; Telegram webhooks with IP allowlist; EA poll/ack tested; HMAC secrets rotated.

**Before P2 prod**

* Copy-trading consent wording locked; risk limits enforced; public performance delay set; Grafana dashboards published.

**Before P3 prod**

* AI assistant guardrails & refusal policies tested; DSAR flows validated; i18n reviewed; admin RBAC audited; synthetics + remediator runbook tested.

---

## 11) Final notes

* Keep **feature flags** for risky surfaces (copy-auto, ledger, social graph, upsell variants, NFT access).
* Default everything to **opt-in** for public exposure (leaderboards, trust pages).
* Maintain **post-trade delay** to prevent signal leakage.

---

