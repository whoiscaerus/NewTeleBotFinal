---

# PR-001 — Monorepo Bootstrap, Envs, Secrets, Pre-Commit, CI/CD

**Goal**: Stand up a production-grade monorepo with deterministic local dev, lint/format/test gates, and continuous integration.

## Scope

* Top-level repo scaffolding, Docker, `make` targets, devcontainer, pre-commit hooks, GH Actions.
* Python 3.11 runtime; Node 20 placeholder (web app later).
* No business logic—just the rails.

## Deliverables (create/update)

```
/.github/workflows/
  ci.yml                          # lint -> typecheck -> tests -> build
.gitignore
.pre-commit-config.yaml
Makefile
pyproject.toml                    # ruff, black, isort, mypy config
README.md                         # quickstart
docs/CONTRIBUTING.md
docker/
  backend.Dockerfile              # slim python base + uvloop + gunicorn
  dev.dockerfile                  # full toolchain image
docker-compose.yml                # postgres, redis, backend
.devcontainer/devcontainer.json   # VS Code devcontainer (optional)
scripts/
  bootstrap.sh                    # first-run setup
  wait-for.sh                     # service readiness helper
  coverage-check.py               # fail <90% (will pass once tests exist)
```

## ENV & Config

* `.env.example` with **non-secret** defaults; instruct devs to create a private `.env` (ignored).
* Base variables (more added in later PRs):

  * `APP_ENV=development|staging|production`
  * `APP_LOG_LEVEL=INFO`
  * `DB_DSN=postgresql+psycopg://app:app@postgres:5432/app`
  * `REDIS_URL=redis://redis:6379/0`

## Tooling

* **pre-commit**: black, ruff, isort, trailing-whitespace, end-of-file-fixer.
* **CI**: lint → mypy → pytest (unit only for now) → build backend image.
* **Makefile**: `make setup`, `make fmt`, `make lint`, `make typecheck`, `make test`, `make up`, `make down`, `make logs`.

## Security

* `.env` ignored; secrets never committed.
* Minimal base image; non-root user in Docker.

## Telemetry

* None yet (introduced in PR-009).

## Tests

* Smoke test placeholder: assert Python toolchain works.
* CI runs on PR and main.

## Verification

* `make up` starts Postgres/Redis/back-end container (empty app OK).
* CI green.

## Rollout/Rollback

* Additive scaffolding; revert by removing files.

---

# PR-002 — Central Config & Typed Settings (12-Factor)

**Goal**: Centralize configuration with type-safe settings and environment layering.

## Scope

* Pydantic v2 settings, environment loading order, config validation.

## Deliverables

```
backend/app/core/settings.py      # BaseSettings + sub-configs
backend/app/core/env.py           # load .env / priorities
backend/app/__init__.py
backend/app/main.py               # will be replaced in PR-0010
```

**Settings classes**:

* `AppSettings` (env, name, version, log level).
* `DbSettings` (dsn, pool sizes).
* `RedisSettings`.
* `SecuritySettings` (jwt issuer/audience placeholders).
* `TelemetrySettings` (OTel endpoint placeholders).

**Validation rules**:

* In `production`, require `APP_VERSION` and `GIT_SHA`.
* DSN parse check; error early if malformed.

## Security

* No secrets in logs; redact DSN password in dumps.

## Telemetry

* Log resolved config at DEBUG with redaction.

## Tests

* Unit test: defaults load; overrides via env; production validation fails when required vars missing.

## Verification

* `pytest backend/app/core/tests/test_settings.py -q` green.

---

# PR-003 — Structured JSON Logging + Request IDs + Correlation

**Goal**: Deterministic, JSON logs with request correlation for tracing.

## Scope

* Logging formatter, access logs harmonized with app logs, request ID middleware.

## Deliverables

```
backend/app/core/logging.py       # JSON formatter, uvicorn/uvloop harmonization
backend/app/core/middleware.py    # RequestIDMiddleware
backend/app/orchestrator/logging_config.py
```

**Behavior**:

* If `X-Request-Id` absent → generate UUIDv4; echo back.
* Access log JSON fields: `ts, lvl, method, path, status, duration_ms, request_id, client_ip`.
* Application logs include `request_id` from contextvar.

## Security

* Never log sensitive headers (`Authorization`, cookies).
* Cap log line size, sanitize newlines.

## Telemetry

* Log counters appear later in PR-009; for now, log event on startup/shutdown.

## Tests

* Middleware test ensures header propagation.
* Access log includes `request_id`.

## Verification

* Run app; curl `/health`; check logs.

---

# PR-004 — AuthN/AuthZ Core (JWT sessions, roles: owner/admin/user)

**Goal**: Foundation for secure user sessions and role-based access.

## Scope

* JWT issuance/validation; password hashing; RBAC helpers.

## Deliverables

```
backend/app/auth/
  __init__.py
  models.py                        # User(id, email, pass_hash, role, created_at)
  schemas.py                       # LoginIn, LoginOut, UserOut
  service.py                       # create_user, verify_password, mint_jwt
  routes.py                        # POST /api/v1/auth/login, GET /me
  rbac.py                          # require_roles(*roles) decorator
```

**JWT**:

* Algo: `RS256` (generate dev keys; prod uses KMS/HSM later).
* Claims: `sub`, `role`, `exp` (15m), `iat`, `jti`, `aud`, `iss`.
* Refresh tokens will come later (if desired).

**Password**:

* Argon2id hashing parameters (memory/time cost set via env).

## Security

* Brute-force throttle (simple in-memory per-IP counter; replaced by Redis in PR-005).
* Uniform error messages on auth failure.
* Lock account after N failed attempts (configurable).

## Telemetry

* `auth_login_total{result}` counter (success/fail) – stub; wired in PR-009.

## Tests

* Create user → login success; bad password → fail; role guard denies/permits properly.

## Verification

* `POST /auth/login` returns `access_token` with role claim.
* `GET /me` with token returns profile.

---

# PR-005 — Rate Limiting, Abuse Controls & IP Throttling

**Goal**: Protect APIs and bots from abuse, brute force, and scraping.

## Scope

* Token bucket / sliding window rate limits via Redis.
* Endpoint-level decorators; global defaults.

## Deliverables

```
backend/app/core/rate_limit.py     # Redis-backed limiter
backend/app/core/decorators.py     # @rate_limit(...)
backend/app/core/abuse.py          # login throttling, IP blocklist hooks
```

**Defaults**:

* Global: 60 req/min per IP.
* Auth endpoints: 10 req/min per IP + exponential backoff on failure.

## Security

* Maintain allowlist for operator IPs.
* Blocklist CIDR support; deny at middleware before hitting app.

## Telemetry

* `ratelimit_block_total{route}` counter.
* `abuse_login_throttle_total`.

## Tests

* Hit same endpoint > limit → 429.
* Login brute force → throttled.

## Verification

* Configure `REDIS_URL`; run suite; manual curl to confirm 429 behavior.

---

# PR-006 — API Error Taxonomy (RFC7807) & Input Validation

**Goal**: Predictable, client-friendly error contracts and strict validation.

## Scope

* Central exception handlers returning **application/problem+json**.
* Pydantic schemas with strict types.

## Deliverables

```
backend/app/core/errors.py         # ProblemDetail model + handlers
backend/app/core/validation.py     # shared validators (UUID, enums, symbol regex)
```

**Conventions**:

* `type` (URI), `title`, `status`, `detail`, `instance`, `errors` (field-level).
* Map common exceptions: 400, 401, 403, 404, 409, 422, 429, 500.

## Security

* Do not leak stack traces in production; include `request_id` in problem detail.

## Telemetry

* `errors_total{status}` counter, wired in PR-009.

## Tests

* Contract tests for common errors; invalid payloads return 422 with field messages.

## Verification

* Intentionally trigger errors; validate schema.

---

# PR-007 — Secrets Management (dotenv → Vault/KMS rotation)

**Goal**: Controlled secret lifecycle; dev uses `.env`, prod uses secrets manager.

## Scope

* Abstraction for secret retrieval; transparent to services.

## Deliverables

```
backend/app/core/secrets.py        # SecretProvider -> DotenvProvider, EnvProvider, VaultProvider (feature-flag)
```

**Behavior**:

* Local/dev: `.env` (already ignored).
* Staging/prod: environment or Vault/KMS (provider chosen by `SECRETS_PROVIDER`).

**Rotation hooks**:

* JWT private key, DB password, Telegram tokens, MT5 creds (used later by trading services).

## Security

* In prod, fail startup if provider is `.env`.
* Cache secrets in memory with TTL; avoid log printing.

## Tests

* Provider switching; missing secret raises clear error.

## Verification

* Simulate all providers via env vars.

---

# PR-008 — Audit Log & Admin Activity Trails

**Goal**: Immutable audit trails for sensitive operations (auth, billing, approvals, device changes).

## Scope

* DB model + write-once insert API; minimal reads.

## Deliverables

```
backend/app/audit/
  models.py                        # AuditLog(id, ts, actor_id, actor_role, action, target, meta JSON, ip)
  service.py                       # record_event(...)
  middleware.py                    # attach actor/ip to context
```

**Events to capture (baseline)**:

* `auth.login`, `auth.logout`, `user.create`, `user.role.change`
* `billing.checkout.create`, `billing.webhook.received`
* `signal.create`, `approval.create`
* `device.register`, `device.revoke`

## Security

* Prohibit updates/deletes; only append.
* PII minimized in `meta` (no tokens/keys).

## Telemetry

* `audit_events_total{action}` counter.

## Tests

* Inserting events; forbidden updates; redaction verified.

## Verification

* Exercise a few flows and inspect DB.

---

# PR-009 — Observability Stack (metrics, traces, dashboards)

**Goal**: First-class telemetry for reliability and business insight.

## Scope

* OpenTelemetry for traces/metrics; Prometheus exporter; health endpoints.

## Deliverables

```
backend/app/observability/
  metrics.py                       # counters, histograms
  tracing.py                       # OTel tracer provider
backend/app/orchestrator/health.py # /api/v1/health, /ready, /version
prometheus/
  prometheus.yml                   # sample scrape config
grafana/
  dashboards/*.json                # basic API + business dashboards (starter)
```

**Key metrics**:

* HTTP: `http_requests_total{route,code}`, `request_duration_seconds`.
* Auth: `auth_login_total{result}`.
* Rate limit: `ratelimit_block_total{route}`.
* Errors: `errors_total{status}`.
* Business placeholders (wired later): `signals_ingested_total`, `approvals_total`.

**Traces**:

* Propagate `X-Request-Id` as trace id if provided; otherwise standard OTel ids.

## Security

* Metrics endpoint not public; scrape via internal network.

## Tests

* Metrics endpoint returns registries; histogram buckets present.

## Verification

* `curl /metrics` shows counters; run sample requests and confirm increments.

---

# PR-010 — Data Model Baseline (Postgres + Alembic migrations)

**Goal**: Establish normalized database schema + migrations to support upcoming domains.

## Scope

* SQLAlchemy 2.0 models and Alembic baseline.
* Only **foundation tables** here; domain tables come in later PRs.

## Deliverables

```
backend/app/core/db.py             # engine/session mgmt (psycopg3)
backend/app/core/models.py         # Base = declarative_base()
backend/alembic/
  env.py
  script.py.mako
  versions/
    0001_initial_baseline.py       # users, roles, audit_log, api_keys(optional)
backend/app/tests/test_db.py
```

**Tables** *(initial minimal set)*:

* `users`:

  * `id (uuid pk)`, `email (unique)`, `password_hash`, `role (enum: owner|admin|user)`, `created_at`, `last_login_at`
* `audit_log`:

  * `id (uuid)`, `ts timestamptz default now()`, `actor_id uuid null`, `actor_role text`, `action text`, `target text`, `ip inet`, `meta jsonb`
* Optionally `api_keys` (owner/operator tooling later).

**Indexes**

* Users: `ix_users_email`, `ix_users_role`.
* Audit: `ix_audit_ts`, `ix_audit_action`, `ix_audit_actor`.

**Conventions**

* `updated_at` managed by trigger (added later when needed).
* All timestamps in UTC.

## Security

* Use Postgres roles: app user with least privileges.
* Migration requires explicit schema owner.

## Telemetry

* Migration logs to stdout; on startup, log DB connectivity and pool settings at INFO.

## Tests

* `alembic upgrade head` in CI.
* CRUD smoke tests for `users`.
* Transaction rollbacks behave correctly.

## Verification

* `make db-migrate-up` (Makefile target) runs migration and prints head.
* `pytest backend/app/tests/test_db.py -q` green.

---

## What Copilot does next

* **Implements the file scaffolding exactly as above**, ensuring imports are correct and modules compile.
* **Wires PR-003 middleware** into the FastAPI app factory (to be created in PR-011+ when we add the orchestrator endpoints).
* **Adds CI gates** from PR-001 so every new PR runs lint/typecheck/tests and builds a container.
* **Sets up Alembic** from PR-010 so future domain PRs (signals, approvals, devices, payments, bots) can add migrations confidently.


---


# PR-011 — MT5 Session Manager & Credentials Vaulting

**Goal**
Create a robust wrapper for MetaTrader5 lifecycle: initialize, login, reconnect, teardown; centralize credentials + terminal path handling.

**Source alignment**
Your MT5 login/config lives inside the strategy script (login, server, password, terminal path) — pull this into a service with retries and circuit breaker.

**Scope**

* Single place to open/close MT5 sessions.
* Health checks and reconnect rules.
* Circuit breaker + exponential backoff on failures.

**Deliverables**

```
backend/app/trading/mt5/
  __init__.py
  session.py             # MT5SessionManager
  errors.py              # MT5InitError, MT5AuthError, MT5Disconnected
  health.py              # probe() used by /ready
```

**Session API**

* `connect(login, password, server, path) -> bool`
* `ensure_connected() -> None` (relogin if needed)
* `shutdown() -> None`
* Context manager `with MT5SessionManager(settings) as mt5:`.

**Env/Config**

* `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`, `MT5_PATH` (fetched via Secrets provider from PR-007).
* `MT5_MAX_FAILURES=5`, `MT5_BACKOFF_SECONDS=300` (from your resilience pattern).

**Security**

* Credentials only from secrets provider (PR-007).
* Never log creds; redact server path if needed.

**Telemetry**

* `mt5_connect_total{result}` counter
* `mt5_uptime_seconds` gauge
* `mt5_reconnects_total`

**Tests**

* Mock MT5 lib; success/fail init; backoff after N failures; context manager closes properly.

**Verification**

* Start minimal worker that calls `ensure_connected()` every 30s; observe metrics and logs.

---

# PR-012 — Market Hours & Timezone Gating

**Goal**
Codify trading windows (e.g., NY close weekend rule) to avoid placing trades when markets are closed.

**Source alignment**
Your code checks weekend closure using America/New_York timezone. Generalize to a reusable policy.

**Deliverables**

```
backend/app/trading/time/
  market_calendar.py   # is_market_open(symbol, now=utc) -> bool
  tz.py                # TZ helpers
```

**Features**

* Default FX schedule: closed Fri 17:00 → Sun 17:00 (America/New_York).
* Configurable symbol-specific calendars.
* Safe-guard: “close-only” mode near maintenance windows.

**Env**

* `DEFAULT_MARKET_TZ=America/New_York`
* `TRADING_BLOCKLIST_WINDOWS` (cron expressions optional)

**Telemetry**

* `market_closed_decisions_total` counter

**Tests**

* Weekday vs weekend matrix; DST boundaries; symbol override.

**Verification**

* Unit-run gating against a curated timestamp set.

---

# PR-013 — Data Pull Pipelines (H1/H15, windows, monitor bars)

**Goal**
A clean pipeline to fetch candles/ticks with exact window sizes your strategy expects.

**Source alignment**
Exact TF usage (H1), window_size, main_bars, monitor_bars are defined in your config; port as-is.

**Deliverables**

```
backend/app/trading/data/
  fetch.py              # get_candles(symbol, tf, window, end=None)
  normalize.py          # ensure columns: time, open, high, low, close, volume
  cache.py              # in-memory/Redis cache for short TTL
```

**Behavior**

* MT5 pulls with retry; strict schema; timezone to UTC.
* Optional SQLite → Postgres migration hook (PR-016).

**Telemetry**

* `candles_fetched_total{symbol,tf}`
* `fetch_duration_seconds` histogram

**Tests**

* Window length correctness; missing bars handling; cache hits.

**Verification**

* Pull 200 bars H1 for GOLD and verify schema.

---

# PR-014 — Fib-RSI Strategy Module (spec-locked to your logic)

**Goal**
Reimplement your Fib + RSI signal logic as a pure service: deterministic inputs/outputs, unit-tested.

**Source alignment**
Uses RSIIndicator (ta), ROCIndicator, and your payload structure + parameters. Keep behavior identical unless a bug is found.

**Deliverables**

```
backend/app/strategy/fib_rsi/
  __init__.py
  params.py             # risk_per_trade, rr_ratio, min_stop_distance_points, etc.
  indicators.py         # RSI, ROC helpers
  engine.py             # generate_signal(df) -> SignalCandidate
  schema.py             # Pydantic: SignalCandidate, ExecutionPlan
```

**Rules**

* Inputs: OHLCV df with at least `window_size` rows.
* Outputs: `{instrument, side, time, payload:{…}, version}` plus computed entry/SL/TP.
* Reject if `is_market_open` false (PR-012).

**Telemetry**

* `strategy_signals_total{side}`
* `strategy_eval_seconds` histogram

**Tests**

* Golden-input fixtures → golden outputs (JSON snapshots).
* Edge cases: low volume, tiny ATR, missing bars.

**Verification**

* Run against latest candles; compare to current script’s decisions.

---

# PR-015 — Order Construction (entry/SL/TP/expiry, min stop distance)

**Goal**
Centralize trade parameter building with RR enforcement and broker constraints.

**Source alignment**
Your code uses `rr_ratio`, `min_stop_distance_points`, `order_expiry_hours`. Mirror exactly.

**Deliverables**

```
backend/app/trading/orders/
  builder.py           # build_order(signal) -> OrderParams
  constraints.py       # apply_min_stop_distance, round_to_tick
  expiry.py            # compute_expiry(now, hours)
  schema.py            # OrderParams
```

**Rules**

* Validate RR >= configured ratio.
* Enforce min SL distance; adjust entry/TP if needed.
* TTL/expiry embedded for later EA consumption.

**Telemetry**

* `orders_built_total`
* `orders_rejected_total{reason}`

**Tests**

* Cases: small SL violates min distance; R:R rounding interactions.

**Verification**

* Feed a few signals; inspect params.

---

# PR-016 — Local Trade Store Migration (SQLite → Postgres)

**Goal**
Normalize your local `trades`, `equity`, and `validation_logs` tables into Postgres with Alembic migrations.

**Source alignment**
You create/append into SQLite for trades/equity/validation logs. Migrate schema & semantics.

**Deliverables**

```
backend/app/trading/store/models.py   # Trade, EquityPoint, ValidationLog
backend/app/trading/store/service.py  # create_trade(...), log_validation(...), list_trades(...)
backend/alembic/versions/0002_trading_store.py
```

**Trade fields (from your schema)**

* `trade_id (uuid pk)`, `setup_id`, `timeframe`, `trade_type`, `direction`,
  `entry_price`, `exit_price`, `take_profit`, `stop_loss`, `volume`,
  `entry_time`, `exit_time`, `duration_hours`, `profit`, `pips`,
  `risk_reward_ratio`, `percent_equity_return`, `exit_reason`,
  `status`, `symbol`, `strategy` (types normalized).

**Telemetry**

* `trades_inserted_total`, `equity_points_total`

**Tests**

* Migration up/down; CRUD; nullability rules match behavior.

**Verification**

* ETL script to import existing SQLite (optional) then sample query.

---

# PR-017 — Signal Serialization + HMAC Signing for Server Ingest

**Goal**
Reliable, signed outbound signal delivery to the server’s ingestion API.

**Source alignment**
You call out to `send_signal` with a server URL — formalize with HMAC headers + canonical body.

**Deliverables**

```
backend/app/trading/outbound/
  client.py            # post_signal(signal: SignalCandidate) -> Response
  hmac.py              # build_signature(secret, body, timestamp, producer_id)
```

**Headers**

* `X-Producer-Id`, `X-Timestamp` (RFC3339), `X-Signature` (base64 HMAC-SHA256).

**Env**

* `HMAC_PRODUCER_ENABLED=true`, `HMAC_PRODUCER_SECRET`, `PRODUCER_ID`

**Telemetry**

* `signals_posted_total{result,code}`; duration histogram

**Tests**

* Correct signature; stale timestamp rejected by server (integration later).

**Verification**

* Post to a mocked ingestion endpoint; assert 201 path.

---

# PR-018 — Resilient Retries/Backoff & Telegram Error Alerts

**Goal**
Never drop a signal silently; alert ops on persistent failures.

**Source alignment**
You already have retry/backoff patterns + Telegram notices (heartbeat/alerts) in your live bot. Encapsulate it.

**Deliverables**

```
backend/app/core/retry.py        # with_retry/backoff jitter, max_retries
backend/app/ops/alerts.py        # send_owner_alert(text)
```

**Env**

* `MAX_RETRIES=5`, `RETRY_DELAY_SECONDS=5`
* `OPS_TELEGRAM_CHAT_ID`, `OPS_TELEGRAM_BOT_TOKEN` (from secrets)

**Telemetry**

* `retries_total{operation}`, `alerts_sent_total`

**Tests**

* Retry stops on success; alerts after exhausting attempts.

**Verification**

* Force outbound client to fail; observe Telegram DM.

---

# PR-019 — Live Trading Bot Enhancements (heartbeat, drawdown caps, analytics hooks)

**Goal**
Harden the live loop with periodic heartbeat, drawdown guards, and analytics event hooks.

**Source alignment**
Your live bot implements heartbeat, drawdown threshold, MT5/Telegram timeouts, and extensive logging. Lift these ideas into reusable modules.

**Deliverables**

```
backend/app/trading/runtime/
  loop.py                 # run_trader(symbols: list)
  guards.py               # enforce_max_drawdown, min_equity_guard
  heartbeat.py            # periodic heartbeat with lock
  events.py               # emit_analytics_event(...)
```

**Env**

* `MAX_DRAWDOWN=0.10`, `MIN_EQUITY_GBP=500.0` (from your file)
* `CHECK_INTERVAL_SECONDS=10`, `CANDLE_CHECK_WINDOW=60`

**Telemetry**

* `heartbeat_total`, `drawdown_block_total`, `runtime_loop_seconds` histogram

**Tests**

* Guard blocks when thresholds breached; heartbeat emits on schedule.

**Verification**

* Dry-run loop with simulated equity → triggers guards.

---

# PR-020 — Charting/Exports Refactor (matplotlib backend, caching)

**Goal**
Server-side chart generation for candles, equity, histograms with caching and byte caps.

**Source alignment**
Your live bot renders charts and exports (matplotlib/seaborn). Standardize to matplotlib only and strip EXIF.

**Deliverables**

```
backend/app/media/
  render.py              # render_candles(...), render_equity(...), render_histogram(...)
  storage.py             # tmp dir mgmt, cache by content hash, TTL pruning
```

**Env**

* `MEDIA_DIR=/var/tmp/bot_media`
* `MEDIA_TTL_SECONDS=86400`
* `MEDIA_MAX_BYTES=5000000`

**Telemetry**

* `media_render_total{type}`, `media_cache_hits_total{type}`

**Tests**

* Generate example images; EXIF stripped; size < limit; deterministic caching.

**Verification**

* Render 500 bar chart; confirm file saved and pruned after TTL (manually adjust).

---

# PR-021 — **Signals API** (ingest, schema, dedupe, payload limits)

**Goal**
Backend endpoint to ingest signed strategy signals from PR-017.

**Deliverables**

```
backend/app/signals/
  models.py               # Signal(id uuid, instrument, side, time, payload jsonb, status, created_at)
  schemas.py              # SignalIn, SignalOut
  service.py              # create_signal(...)
  routes.py               # POST /api/v1/signals
backend/alembic/versions/0003_signals.py
```

**Contract**

* Headers: `X-Producer-Id`, `X-Timestamp`, `X-Signature` (required if HMAC enabled).
* Body: `{instrument, side, time, payload, version}`
* Limits: payload ≤ 32 KB; reject duplicate `(instrument, time, version)` within short window.

**Security**

* HMAC verification (shared secret), 5-minute freshness window.
* Log payload redacted (store in DB, don’t print).

**Telemetry**

* `signals_ingested_total{instrument,side}`
* `signals_create_seconds` histogram

**Tests**

* Valid → 201; missing/invalid HMAC → 401; oversized payload → 413; bad fields → 422.

**Verification**

* Post from PR-017 client → 201, ID returned.

---

# PR-022 — **Approvals API** (approve/reject, consent text versioning, audit)

**Goal**
User-scoped approval endpoints to confirm or reject trades before execution.

**Deliverables**

```
backend/app/approvals/
  models.py               # Approval(id uuid, signal_id fk, user_id fk, decision enum, consent_version, ip, ua, created_at)
  schemas.py              # ApprovalIn, ApprovalOut
  service.py              # create_approval(...)
  routes.py               # POST /api/v1/approve
backend/alembic/versions/0004_approvals.py
```

**Behavior**

* JWT required (from PR-004).
* Unique constraint `(signal_id, user_id)` → 409 on duplicates.
* Capture IP (inet) + UA; write to audit log (PR-008).
* Consent text is versioned string to lock legal wording used.

**Security**

* Rate limit (PR-005) to prevent spam; RBAC: only end users can approve their feed.

**Telemetry**

* `approvals_total{decision}`
* `approval_latency_seconds` histogram

**Tests**

* Approve existing signal → 201; reject → 201; duplicate → 409; no JWT → 401; non-existent signal → 404.

**Verification**

* Create signal (PR-021) → approve via bearer token → DB row exists; audit event recorded.

---

# PR-023 — **Account Reconciliation & Trade Monitoring** (MT5 Position Sync + Auto-Close)

**Goal**
Real-time account reconciliation: sync client positions from MT5, verify trades match bot predictions, and auto-close positions when necessary (profit targets, risk limits, market conditions).

**Depends on**: PR-016 (trade store), PR-021 (signals), PR-022 (approvals)

## Scope

* MT5 account monitoring (equity, open positions, closed trades).
* Trade reconciliation: bot order vs. broker position (entry price, volume, direction).
* Drawdown guards: close all positions if equity drops below threshold.
* Market condition guards: close positions on unexpected market events (gap up/down, liquidity crisis).
* Audit trail of all closes (reason, timestamp, equity at close).

## Deliverables

```
backend/app/trading/reconciliation/
  models.py               # ReconciliationLog(id, user_id, signal_id, mt5_position, bot_position, matched, divergence_reason, created_at)
  mt5_sync.py             # sync_positions(user) → List[Position], verify equity
  auto_close.py           # should_close_position(position, account) → reason: str | None
  routes.py               # GET /api/v1/reconciliation/{user_id}, GET /api/v1/positions (live)
backend/alembic/versions/00XX_reconciliation.py

backend/app/trading/monitoring/
  drawdown_guard.py       # check_max_drawdown(account) → should_liquidate: bool
  market_guard.py         # check_market_conditions(symbol, bid/ask) → safe: bool
  liquidation.py          # close_all_positions(user_id, reason) → List[closed_trade_ids]
```

**Env**

* `MAX_DRAWDOWN_PERCENT=20` (close all if -20% from peak equity)
* `MIN_EQUITY_GBP=100` (minimum account balance, else close all)
* `PRICE_GAP_ALERT_PERCENT=5` (alert if price gaps >5% unexpectedly)
* `LIQUIDITY_CHECK_ENABLED=true`

## Behavior

* **Position Sync** (every 10 seconds):
  - Connect to MT5 terminal
  - Fetch `AccountInfo()`, `Positions()`
  - Compare against `trades` table
  - Log any divergences (slippage, partial fill, broker close)

* **Drawdown Guard** (every 30 seconds):
  - Calculate current equity
  - Compare vs. peak equity (stored in DB)
  - If drawdown > MAX_DRAWDOWN_PERCENT → auto-close all positions
  - Send warning to user 10 seconds before close

* **Market Guard** (on every candle close):
  - Check for unexpected price gaps
  - Check for liquidity dryness (bid-ask spread > threshold)
  - If unsafe → mark position for close

* **Auto-Close**:
  - Close position via MT5 API
  - Log reason (drawdown, market condition, risk limit)
  - Record close price, PnL
  - Notify user immediately (Telegram alert)

## Security

* Drawdown guard is **non-negotiable** (prevents catastrophic loss)
* Only owner or auto-system can trigger liquidation (no user can manually prevent)
* Every close logged to Audit Log (PR-008) with reason + timestamp
* Rate-limit reconciliation to prevent spam

## Telemetry

* `mt5_position_sync_total` counter
* `reconciliation_divergences_total{reason}` counter
* `drawdown_guard_triggers_total`
* `positions_autoclosed_total{reason}`
* `reconciliation_latency_seconds` histogram

## Tests

* Sync position → log matches; manual close in MT5 → detected in sync
* Equity drops 20% → auto-close all; user notified immediately
* Price gap 10% → market guard triggers; positions marked for close
* Partial fill (1 trade → 2 fills) → reconciliation detects + consolidates
* Divergence logged: bot expected +£100 profit, broker shows +£95 (slippage)

## Verification

* Create test account, place manual MT5 trade, sync → reconciliation shows match
* Simulate 20% drawdown → observe auto-close, audit log entry, Telegram alert
* Monitor live account for 24 hours → zero divergences

---

# PR-024 — **Affiliate & Referral System** (Tracking, Payouts, Fraud Detection)

**Goal**
Enable organic growth through referrals: track affiliate links, measure conversions, pay commissions automatically, and provide fraud detection + trade attribution audit to protect against false claims.

**Depends on**: PR-004 (auth), PR-033 (payments), PR-008 (audit), PR-016 (trade store)

## Scope

* Affiliate link generation (unique per user/influencer)
* **Subscription-based commission tracking** (affiliate earns only from subscription revenue, NOT user's trading)
* Commission calculation (tiered: 30% month 1, 15% recurring, 5% performance bonus)
* Automated payout via Stripe/bank transfer
* Affiliate dashboard (earnings, clicks, conversions, payout status)
* **Fraud Detection (Self-Referrals Only)**: Detect users creating fake accounts to earn commission from themselves
* **Trade Attribution Audit**: Prove which trades came from bot signals vs. user's manual trades (protects against false refund claims)

## Critical Business Model

**How Affiliates Earn:**
- ✅ Commission from **subscription purchases only** (£20-50/month)
- ❌ **NOT** from user's trading performance or volume
- User executing own manual trades does **NOT** affect affiliate earnings

**Real Fraud Risk:**
- User subscribes (pays £20-50/month)
- User executes **manual trades** that lose money
- User claims: "Your bot lost me £500! Refund me!"
- **Solution:** Trade attribution proof shows losses from user's manual trades, not your bot

## Deliverables

```
backend/app/affiliates/
  models.py                # Affiliate(id, user_id, referral_code, tier, created_at)
  schemas.py               # AffiliateOut, ReferralStatsOut
  service.py               # generate_code(), track_signup(), calculate_commission(), trigger_payout()
  routes.py                # GET /api/v1/affiliate/me, POST /api/v1/affiliate/claim, GET /api/v1/affiliate/stats
                           # GET /api/v1/admin/trades/{user_id}/attribution (trade attribution report)
  fraud.py                 # check_self_referral(referrer, referee)
                           # get_trade_attribution_report(user_id) → bot vs manual trades breakdown
                           # validate_referral_before_commission(referrer, referee)
backend/alembic/versions/00XX_affiliates.py

backend/schedulers/
  affiliate_payout_runner.py  # Daily: aggregate earnings, trigger Stripe payouts
```

**Env**

* `AFFILIATE_COMMISSION_TIER_1=0.30` (30% of first month MRR)
* `AFFILIATE_COMMISSION_TIER_2=0.15` (15% of recurring)
* `AFFILIATE_PERFORMANCE_BONUS=0.05` (5% bonus if referred client stays 3+ months)
* `AFFILIATE_MIN_PAYOUT_GBP=50` (don't payout < £50)
* `AFFILIATE_PAYOUT_SCHEDULE=monthly` (or weekly)

## Behavior

### Link Generation
- User claims affiliate status (KYC optional; geo-gating for some regions)
- System generates unique `referral_code` (e.g., `ref_abc123xyz`)
- User gets shareable link: `https://yourdomain.com/?ref=abc123xyz`
- Link stored with `utm_source=affiliate`

### Signup Tracking
- New user clicks link → `ReferralEvent(type='signup', referral_code=...)`
- User completes onboarding → `ReferralEvent(type='subscription_created', ...)`
- Commission triggered only on subscription purchase (NOT on first trade)

### Commission Calculation (Daily Batch)
- For each referred user:
  - Month 1: `commission = subscription_price × 0.30`
  - Month 2+: `commission = subscription_price × 0.15`
  - If user stays 3+ months: `bonus = subscription_price × 0.05`
- Store in `AffiliateEarnings` table
- **NOTE:** User's trading activity, win rate, or trade volume does NOT affect commission

### Payout
- Daily: aggregate earnings
- If balance > MIN_PAYOUT: create payout to Stripe/bank
- Async: poll payout status
- Mark as paid in DB

### Fraud Detection: Self-Referral Only
**Why wash trades don't apply:**
- Affiliates earn from subscriptions (fixed revenue)
- Whether user places 0 or 1000 trades, affiliate earns same commission
- User's trading performance is irrelevant to affiliate earnings
- Wash trade detection is for prop firms / copy-trading models (not applicable here)

**Self-Referral Detection:**
1. Same email domain check: Referrer and referee with same `@domain.com`
2. Account creation timing: Accounts created < 2 hours apart
3. Action: Flag for manual review, log to audit log, block commission

### Trade Attribution Audit (False Claim Protection)

**Every trade has:**
- `signal_id` (populated if bot trade, NULL if manual trade)
- `user_id` (links trade to user)
- Entry/exit prices, profit/loss, timestamps

**Report function: `get_trade_attribution_report(user_id, days_lookback=30)`**

Returns:
```json
{
  "bot_trades": 3,
  "manual_trades": 5,
  "bot_profit": 150.00,
  "manual_profit": -300.00,
  "bot_win_rate": 0.67,
  "manual_win_rate": 0.20,
  "trades": [
    {"trade_id": "...", "source": "bot", "profit": 50, "signal_id": "signal_123"},
    {"trade_id": "...", "source": "manual", "profit": -100, "signal_id": null}
  ]
}
```

**Use Case: Dispute Resolution**
```
User: "Your bot lost me £300!"
Admin: *runs attribution report*
Result: Bot: +£150 (67% win rate), Manual: -£300 (20% win rate)
Outcome: Claim rejected with database proof
```

## Security

* Commission payouts are **idempotent** (same transaction ID = no double-pay)
* Affiliate earnings **non-reversible** after 30 days (sunk)
* Rate-limit payout API (1 request per 10 seconds per affiliate)
* Audit every payout (Audit Log: amount, recipient, timestamp)
* Stripe webhook verifies payout status (prevents false claims)
* Trade attribution report immutable (sourced from database only)

## Telemetry

* `affiliate_signups_total` counter
* `affiliate_subscriptions_created_total` counter
* `affiliate_earnings_total` counter
* `affiliate_payouts_total{status}` counter (pending, completed, failed)
* `affiliate_fraud_detections_total{type}` counter (self_referral only)
* `affiliate_conversion_rate` gauge (conversions / clicks)
* `trade_attribution_reports_generated_total` counter

## Tests

* Generate referral link → share → new user signup with link → conversion tracked
* Referred user subscribes → month 1 commission = 30% of MRR; month 2 = 15%
* Self-referral attempt (same domain + close timing) → rejected; logged to fraud queue
* Affiliate balance £100 → payout triggered; confirmed in Stripe logs
* Trade attribution: Bot trades separated from manual trades by `signal_id`
* Dispute scenario: User with 3 bot trades (+£150) and 5 manual trades (-£300) → report proves bot profitability

## Verification

* Create test affiliate, generate link
* Signup with link (test user) → ReferralEvent logged
* Subscribe as test user → commission calculated
* Trigger daily payout batch → Stripe payout created
* Observe affiliate dashboard: earnings, pending payout, conversion metrics
* Generate trade attribution report: bot vs manual trades clearly separated
* **API Endpoint Test**: GET `/api/v1/admin/trades/{user_id}/attribution` returns full report

---

## Notes on Wiring & Dependencies

* PR-011..015 power the **trader** side; PR-016 normalizes persistence; PR-017..018 make outbound delivery resilient; PR-019..020 bring UX/ops polish; PR-021..022 open the **server** side for ingestion + approvals.
* **NEW** PR-023 adds **real-time account reconciliation** (critical for risk management + trader confidence).
* **NEW** PR-024 adds **affiliate system** (critical for organic growth without paid marketing).
* Next set (PR-025..027) will add **Device Registry**, **EA Poll/Ack**, and the **Execution Store**, followed by Telegram bots and payments.

---


# PR-023a — Device Registry & HMAC Secrets

**Goal**
Let each client register one or more “devices” (their MT5 EA instances) and authenticate them via HMAC for server APIs.

**Scope**

* DB models for `clients`, `devices`.
* Device registration API (returns **secret once**).
* List/rename/revoke device endpoints.

**Deliverables**

```
backend/app/clients/
  models.py           # Client(id,email,telegram_id,created_at); Device(id,client_id,name,secret_hash,revoked,last_seen)
  schemas.py          # DeviceRegisterIn, DeviceRegisterOut (shows secret once), DeviceOut
  service.py          # create_device, list_devices, update_name, revoke
  routes.py           # POST /api/v1/devices/register (JWT), GET /api/v1/devices/me, PATCH /api/v1/devices/{id}, POST /{id}/revoke
backend/alembic/versions/0005_clients_devices.py
```

**Behavior**

* `POST /devices/register`: generates `device_secret` (32 bytes URL-safe), stores **argon2id(secret)** only; returns `{device_id, device_secret}` once.
* Uniqueness: `(client_id, name)` must be unique.

**Env**

* `DEVICE_SECRET_BYTES=32`

**Security**

* JWT required (PR-004).
* Secret shown once; never logged.

**Telemetry**

* `devices_registered_total`
* `devices_revoked_total`

**Tests**

* Register → get secret once; list excludes secret; rename/revoke happy-path; duplicate name → 409.

**Verification**

* Create test client; register device; rename; revoke; confirm in DB.

---

# PR-024a — EA Poll/Ack API (HMAC, Nonce, Freshness)

**Goal**
Let EAs poll for **their user’s approved signals**, and **acknowledge** execution results. Prevent replay with nonce + timestamp.

**Scope**

* Device-auth middleware (HMAC).
* Poll endpoint, Ack endpoint.
* Redis nonce store.

**Deliverables**

```
backend/app/ea/
  hmac.py             # build/verify canonical string from method, path, body, X-Device-Id, X-Nonce, X-Timestamp
  auth.py             # DeviceAuth dependency: loads device, checks revoked, verifies signature
  models.py           # Execution(id, approval_id, device_id, status, broker_ticket, error, created_at, updated_at)
  schemas.py          # PollResponse, AckRequest, AckResponse
  routes.py           # GET /api/v1/client/poll?since=... ; POST /api/v1/client/ack
backend/alembic/versions/0006_executions.py
```

**Headers (required)**

* `X-Device-Id`, `X-Nonce`, `X-Timestamp` (RFC3339), `X-Signature` (base64 HMAC-SHA256).

**Logic**

* **Poll**: return approvals (PR-022) for this device’s **client_id**, decision=approved, **not yet acked**, plus full execution params (entry/SL/TP/TTL) from PR-015.
* **Ack**: upsert `Execution` row with `status: placed|failed`, `broker_ticket?`, `error?`.

**Env**

* `HMAC_DEVICE_REQUIRED=true`
* `HMAC_TIMESTAMP_SKEW_SECONDS=300`
* `HMAC_NONCE_TTL_SECONDS=600`

**Security**

* Reject missing headers/revoked devices/signature mismatch/old timestamps/nonce reuse (Redis `SETNX`).

**Telemetry**

* `ea_poll_total{status}`
* `ea_ack_total{result}`
* `ea_poll_duration_seconds` (histogram)

**Tests**

* Valid HMAC → returns only owner approvals; wrong sig → 401; skew > 5m → 401; replayed nonce → 401.

**Verification**

* Register device (PR-023); create approval (PR-022); poll; ack placed; confirm DB.

---

# PR-025 — Execution Store & Broker Ticketing

**Goal**
Formalize storage of device execution outcomes and aggregate status per approval.

**Scope**

* Extend `Execution` model and add **per-approval** aggregate view.
* Admin query endpoints.

**Deliverables**

```
backend/app/ea/aggregate.py   # get_approval_execution_status(approval_id) -> {placed_count, failed_count, last_update}
backend/app/ea/routes.py      # GET /api/v1/executions/{approval_id} (JWT admin)
```

**Security**

* RBAC: owner/admin only for aggregate & raw execution reads.

**Telemetry**

* `executions_total{status}`
* `execution_fail_rate` (computed panel in Grafana)

**Tests**

* Multiple acks from different devices aggregate correctly; RBAC respected.

**Verification**

* Simulate two devices; one placed, one failed; check aggregate.

---

# PR-026 — Telegram Webhook Service & Signature Verification

**Goal**
Move all Telegram bots to a single **webhook service** with per-bot routing and secure verification.

**Source alignment**
Your current bots use polling/simpler setups; consolidate to a webhook layout and centralize tokens/config. (migrates logic from `bot.py`, `ContentDistribution.py`, `GuideBot.py`, `MarketingBot.py`).

**Deliverables**

```
backend/app/telegram/
  router.py            # dispatch by bot token / path
  verify.py            # optional secret token validation, IP allowlist
  handlers/
    shop.py            # shop/catalog commands
    distribution.py    # content forwarding
    guides.py          # guides keyboard
    marketing.py       # broadcast CTA
  webhooks.py          # POST /telegram/{bot_name}/webhook
```

**Env**

* `TELEGRAM_BOT_TOKENS_JSON` (map bot_name→token) via Secrets (PR-007).
* `TELEGRAM_WEBHOOK_SECRET` (optional shared secret).
* `TELEGRAM_IP_ALLOWLIST` (CIDRs).

**Security**

* Verify request origin (IP allowlist) and/or shared secret header.
* Per-bot rate limits (PR-005).

**Telemetry**

* `telegram_updates_total{bot_name, type}`
* `telegram_errors_total`

**Tests**

* Webhook signature/IP checks; command routed to proper handler.

**Verification**

* Set webhook for each bot; send test updates; observe routing.

---

# PR-027 — Bot Command Router & Permissions

**Goal**
Unify command handling with RBAC and structured help.

**Source alignment**
Refactor commands from `bot.py` (shop), `ContentDistribution.py`, `GuideBot.py`, `MarketingBot.py` into modular handlers and apply permissions.

**Deliverables**

```
backend/app/telegram/commands.py   # registry: /start, /help, /plans, /buy, /status, /analytics, /admin ...
backend/app/telegram/rbac.py       # ensure_admin(chat_id) / ensure_owner(user_id)
```

**Features**

* `/help` shows context-aware options.
* Admin-only routes for broadcasts and content routing.

**Telemetry**

* `telegram_command_total{name}`

**Tests**

* Non-admin blocked on admin commands; help renders by role.

**Verification**

* Manual commands through webhook; check behavior.

---

# PR-028 — Shop: Products/Plans & Entitlements Mapping

**Goal**
Define products/plan SKUs & durations and map them to **entitlements** used by backend gates.

**Source alignment**
Your `bot.py` includes rich pricing tables & combinations; formalize as catalog + entitlements.

**Deliverables**

```
backend/app/billing/catalog.py     # plan codes, durations, prices (GBP base)
backend/app/billing/entitlements.py# resolve(plan_code) -> features (signals_enabled, max_devices, copy_trading, analytics_level)
backend/app/billing/routes.py      # GET /api/v1/catalog, GET /api/v1/me/entitlements
backend/alembic/versions/0007_entitlements.py
```

**Behavior**

* `/plans` or `/catalog` used by bots and web to render pricing.
* Entitlement middleware (from earlier PR-006/PR-006b pattern) protects premium routes.

**Tests**

* Plan→entitlement mapping; entitlement listing for user.

**Verification**

* Curl endpoints; inspect JSON.

---

# PR-029 — RateFetcher Integration & Dynamic Quotes

**Goal**
Serve dynamic FX/crypto quotes for the shop and show **local currency equivalents**.

**Source alignment**
Your `RateFetcher.py` calls ExchangeRate-API + CoinGecko and maintains pricing conversions. Migrate to a service with caching & backoff.

**Deliverables**

```
backend/app/pricing/
  rates.py            # fetch_gbp_usd(), fetch_crypto_prices(ids), cache; backoff+retry
  quotes.py           # quote_for(plan_code, currency) -> amount
  routes.py           # GET /api/v1/quotes?plan=gold&currency=USD
```

**Env**

* `FX_API_BASE`, `FX_API_KEY`
* `COINGECKO_BASE` (no key)
* Cache TTL: `RATES_TTL_SECONDS=300`

**Security**

* Rate-limit external calls; sanitize responses.

**Telemetry**

* `pricing_rate_fetch_total{source}`
* `pricing_quote_total{currency}`

**Tests**

* Price math; stale cache fallback; error handling.

**Verification**

* Hit `/quotes`; verify sensible outputs for USD/EUR/GBP.

---

# PR-030 — Content Distribution Router (Keywords → Channels)

**Goal**
Admin can post once; system fans content to the correct Telegram groups based on keywords.

**Source alignment**
From `ContentDistribution.py`: detect “gold/crypto/sp500” in message and forward to specific chat IDs. Harden it with structured routing & logging.

**Deliverables**

```
backend/app/telegram/handlers/distribution.py
backend/app/telegram/routes_config.py  # mapping keywords->chat_id(s)
backend/app/telegram/logging.py        # structured message audit
```

**Features**

* Case-insensitive keyword matcher; multi-keyword support; templated captions.
* Admin confirmation reply listing where it was posted.

**Env**

* `TELEGRAM_GROUP_MAP_JSON` (e.g., {gold: -4608..., sp500: ...}) from your file.

**Telemetry**

* `distribution_messages_total{channel}`

**Tests**

* Keyword matrix; no-match branch; error handling.

**Verification**

* Post sample; verify it reaches expected chats.

---

# PR-031 — GuideBot: Buttons, Links & Scheduler

**Goal**
Serve evergreen education links via inline keyboards; scheduled reposts.

**Source alignment**
Your `GuideBot.py` defines inline buttons for guides (Telegraph links) and periodic posting. Consolidate into handler.

**Deliverables**

```
backend/app/telegram/handlers/guides.py   # /guides command -> inline keyboard
backend/app/telegram/scheduler.py         # run_repeating(post_guides, ...)
```

**Env**

* `GUIDES_CHAT_IDS_JSON` (where to post periodically).

**Telemetry**

* `guides_posts_total`

**Tests**

* Keyboard renders; schedule fires; errors logged not crashing job.

**Verification**

* Trigger `/guides`; confirm buttons & links.

---

# PR-032 — MarketingBot: Broadcasts, CTAs & JobQueue

**Goal**
Scheduled subscription promos with inline CTAs to your main bot.

**Source alignment**
`MarketingBot.py` posts a Markdown V2 promo every 4 hours with a button to `@CaerusTradingBot`. Harden scheduling & persistence of clicked users.

**Deliverables**

```
backend/app/marketing/
  messages.py            # promo text templates (safe MarkdownV2)
  scheduler.py           # run_repeating(send_subscription_message, 4h)
  clicks_store.py        # persist user_id -> clicked_at (Postgres)
backend/app/telegram/handlers/marketing.py  # /start-marketing (admin)
backend/alembic/versions/0008_marketing_clicks.py
```

**Telemetry**

* `marketing_posts_total`
* `marketing_clicks_total`

**Tests**

* Post once on start; schedule repeats; click logged.

**Verification**

* Run job; see message in channel; click button (logs user).

---

# PR-033 — Fiat Payments via Stripe (Checkout + Portal)

**Goal**
End-to-end billing with Stripe: Checkout links, webhooks, and Customer Portal deep links (works from Telegram & Web).

**Scope**

* Stripe SDK setup; products & prices configured by code or dashboard.
* Create checkout sessions; handle webhook events; map to entitlements (PR-028).

**Deliverables**

```
backend/app/billing/stripe.py      # create_checkout_session, create_portal_session
backend/app/billing/webhooks.py    # POST /api/v1/billing/stripe/webhook (verify sig)
backend/app/billing/routes.py      # POST /checkout, GET /portal
backend/alembic/versions/0009_billing_core.py
```

**Flow**

* From bot `/buy` or Mini App → call `/checkout?plan=...` → Stripe hosted checkout.
* On success webhook: activate entitlement for user; store invoice data.

**Env**

* `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_MAP_JSON`

**Security**

* Verify webhook signatures; idempotency keys on create calls.

**Telemetry**

* `billing_checkout_started_total{plan}`
* `billing_payments_total{status}`

**Tests**

* Mock Stripe: session creation; webhook verifies; entitlement flip.

**Verification**

* Test mode: complete a payment; entitlement shows up at `/me/entitlements`.

---

# PR-034 — Telegram Native Payments (optional complement)

**Goal**
Offer native **Telegram Payments** as an alternative checkout for in-chat purchases.

**Scope**

* Telegram Payment flow (invoice, shipping, pre-checkout, successful payment).
* Map paid invoice → entitlement (PR-028).

**Deliverables**

```
backend/app/telegram/payments.py    # send_invoice, handle_pre_checkout, handle_successful_payment
backend/app/telegram/handlers/shop.py  # /buy -> choose Stripe or Telegram Payment
```

**Env**

* `TELEGRAM_PAYMENT_PROVIDER_TOKEN` (from the PSP)
* Product/price mapping aligned with PR-028 catalog

**Security**

* Validate the `payload` and amounts; reconcile with server price to prevent tampering.

**Telemetry**

* `telegram_payments_total{result}`
* `telegram_payment_value_total` (sum)

**Tests**

* Happy path with sandbox provider; mismatch payload → rejected; entitlement flip.

**Verification**

* Send `/buy gold 3m`; try Telegram payment in sandbox; confirm entitlement updated.

---

## how this block fits your system

* **23–25** finalize the MT5 device → server handshake and execution lifecycle.
* **26–32** consolidate and professionalize your Telegram estate (from your actual bot files) into one secure, observable service.
* **33–34** give you **fiat payments** via Stripe and optional **Telegram native payments**, both tied back to **entitlements** (PR-028) used by API gates.

---



# PR-035 — Telegram Mini App Bootstrap (Next.js WebApp)

**Goal**
Stand up a **Next.js 14 (App Router)** project as a Telegram **WebApp** (Mini App) that talks to the backend APIs and respects Telegram’s `initData` auth → server JWT bridge.

**Scope**

* Next.js app, Tailwind, dark mode, PWA baseline.
* Telegram WebApp SDK bootstrapping, theme syncing, safe viewport.
* Backend endpoint to exchange `initData` → short-lived JWT for API calls.

**Deliverables**

```
/frontend/miniapp/
  next.config.js
  package.json
  app/layout.tsx
  app/page.tsx                         # landing/skeleton
  app/_providers/TelegramProvider.tsx  # initData parsing, theme, haptics
  app/(auth)/bridge/route.ts          # API route proxy (optional)
  lib/api.ts                           # fetch wrapper with JWT
  styles/globals.css                   # Tailwind
backend/app/miniapp/
  auth_bridge.py  # POST /api/v1/miniapp/exchange-initdata -> JWT
```

**Env**

* `TELEGRAM_BOT_USERNAME`
* `JWT_MINIAPP_AUDIENCE="miniapp"`

**Security**

* Validate `initData` signature with the bot token; **15 min** JWT; bind to Telegram user id.

**Telemetry**

* `miniapp_sessions_total`, `miniapp_exchange_latency_seconds`

**Tests**

* Unit test: signature verification; e2e with mock `initData`.

**Verification**

* Open Mini App from Telegram → requests JWT and can call `/me`.

---

# PR-036 — Mini App: **Approval Console** (Trade Review & Action)

**Goal**
The main Mini App page for reviewing signals and **Approve / Reject** in one tap.

**Scope**

* List open signals for the user, search/filter, details drawer.
* Approve/Reject calls backend **Approvals API** (PR-022).
* Visuals: “Confidence Meter” & “Signal Maturity” bars (fed by strategy meta).

**Deliverables**

```
frontend/miniapp/app/approvals/page.tsx
frontend/miniapp/components/SignalCard.tsx
frontend/miniapp/components/SignalDetails.tsx
frontend/miniapp/actions/approve.ts   # calls backend
```

**Backend**

* `/api/v1/signals?status=open` (server already PR-021)
* `/api/v1/approve` (PR-022)

**UX**

* Optimistic UI; fallback toast on failure; haptic feedback.

**Telemetry**

* `miniapp_approval_click_total{decision}`, `miniapp_signal_view_total`

**Tests**

* UI state toggles; API called with JWT; errors surfaced gracefully.

---

# PR-037 — Plan Gating Enforcement (Server + Mini App)

**Goal**
Make **entitlements mandatory** across server routes + Mini App UI.

**Scope**

* Middleware to check entitlements (from PR-028).
* UI gating (badges/lock icons) and upgrade CTAs to `/checkout`.

**Deliverables**

```
backend/app/billing/gates.py     # require_entitlement("analytics.pro") etc.
frontend/miniapp/components/Gated.tsx
frontend/miniapp/app/(gated)/analytics/page.tsx
```

**Behavior**

* 403 with RFC7807 body when missing.
* Mini App shows “Upgrade” modal with deep link to `/checkout?plan=...` (PR-033).

**Telemetry**

* `entitlement_denied_total{feature}`

**Tests**

* Gate blocks; UI shows upgrade.

---

# PR-038 — Mini App: **Billing** (Stripe Checkout + Portal)

**Goal**
Expose subscription state, invoices, and **Stripe Customer Portal** inside the Mini App.

**Scope**

* “Current Plan” card, invoice history, “Manage Payment” (portal), “Upgrade Plan” (checkout).

**Deliverables**

```
frontend/miniapp/app/billing/page.tsx
frontend/miniapp/components/BillingCard.tsx
backend/app/billing/routes.py    # already PR-033 → add miniapp-friendly endpoints
```

**UX**

* Portal opens in external browser (security best practice).
* Invoices linkable; “paid/past_due/canceled” badges.

**Telemetry**

* `miniapp_portal_open_total`, `miniapp_checkout_start_total{plan}`

**Tests**

* Portal URL creation; checkout session creation; plan state rendering.

---

# PR-039 — Mini App: **Account & Devices**

**Goal**
Self-service device management (register, rename, revoke) for MT5 EAs.

**Scope**

* UI to list devices + “Add device” (reveals secret **once**).
* Connects to **Device Registry** (PR-023).

**Deliverables**

```
frontend/miniapp/app/devices/page.tsx
frontend/miniapp/components/DeviceList.tsx
frontend/miniapp/components/AddDeviceModal.tsx
```

**Security**

* Device secret shown once; copy-to-clipboard only; not re-rendered.

**Telemetry**

* `miniapp_device_register_total`, `miniapp_device_revoke_total`

**Tests**

* Happy path + revoke; duplicate name → toast error.

---

# PR-040 — Payment Security Hardening (Replay Protection, PCI Scoping)

**Goal**
Bulletproof all billing flows (Stripe, Telegram) against replays/tampering and reduce PCI scope.

**Scope**

* Idempotency keys for checkout; webhook **replay protection**; hash invoice payloads; signature verification.
* Ensure Mini App never touches card data (portal only).

**Deliverables**

```
backend/app/billing/security.py    # verify_stripe_signature, replay_cache
backend/app/billing/webhooks.py    # enforce idempotency & replay window
backend/app/core/idempotency.py    # generic decorator with Redis
```

**Env**

* `WEBHOOK_REPLAY_TTL_SECONDS=600`

**Telemetry**

* `billing_webhook_replay_block_total`, `idempotent_hits_total`

**Tests**

* Replayed webhook → rejected; tampered amount → rejected.

---

# PR-041 — MT5 EA SDK & **Reference EA** (Copy/Approval Modes)

**Goal**
Ship an **MT5 Expert Advisor SDK** + a reference EA that can run in:

1. **Approval mode** (poll/ack PR-024)
2. **Copy-trading mode** (auto-execute)

**Scope**

* C++/MQL5 SDK layer (thin, focused) + docs.
* HMAC auth + nonce; JSON decode of poll responses.

**Deliverables**

```
/ea-sdk/
  include/caerus_auth.mqh
  include/caerus_http.mqh
  include/caerus_models.mqh
  examples/ReferenceEA.mq5      # config toggles: approval/copy
  README.md
```

**Config**

* `API_BASE`, `DEVICE_ID`, `DEVICE_SECRET`, polling interval, slippage, max spread.

**Security**

* Store secrets in EA input params with optional XOR obfuscation; rotate via device revoke.

**Telemetry (server-side)**

* `ea_requests_total{endpoint}`, `ea_errors_total`

**Tests**

* Simulated responses in a harness; signature tests; boundary cases (stale timestamp, nonce reuse).

---

# PR-042 — **Encrypted Signal Transport** (E2E to EA)

**Goal**
Protect signal payloads at rest and in transit even against MITM where HMAC verifies integrity but not confidentiality.

**Scope**

* Add **AEAD** (e.g., AES-GCM) envelope on the signal body after HMAC verification.
* Per-device symmetric key derived from server-side KDF; keys rotated on device reset.

**Deliverables**

```
backend/app/ea/crypto.py     # encrypt/decrypt payload(envelope)
backend/app/ea/auth.py       # issue device encryption material on register (PR-023)
ea-sdk/include/caerus_crypto.mqh   # decrypt AEAD envelope
```

**Env**

* `DEVICE_KEY_KDF_SECRET`, `DEVICE_KEY_ROTATE_DAYS=90`

**Security**

* Server logs show ciphertext length only.
* Rotation policy with grace period.

**Tests**

* Round trip encrypt/decrypt; tamper detection; rotated key fails until device refresh.

---

# PR-043 — Live Position Tracking & Account Linking (MT5 Verify)

**Goal**
Display **live positions** and verify account ownership, enabling transparency and later copy-trading checks.

**Scope**

* Backend endpoint that queries MT5 positions/equity for a linked account (server-side MT5 session manager when owner is the account holder; or via EA acks + summaries).
* Ownership verification: sign a message from the EA or provide a one-off trade tag.

**Deliverables**

```
backend/app/accounts/
  link.py             # start_link, verify_link (token), unlink
  models.py           # LinkedAccount(client_id, broker, account_id, verified_at)
  routes.py           # POST /link, POST /link/verify, DELETE /link
backend/app/positions/routes.py     # GET /positions/live
```

**Mini App UI**

```
frontend/miniapp/app/positions/page.tsx
```

**Telemetry**

* `accounts_link_started_total`, `accounts_verified_total`

**Tests**

* Link/verify; positions return shape; unauthorized blocked.

---

# PR-044 — Price Alerts & Notifications (User-Specific)

**Goal**
Let users set price alerts (above/below) and receive Telegram push + Mini App notifications.

**Scope**

* Alert rules per user/symbol; server cron or stream runner checks quotes (reuse pricing + MT5 tickers where possible).
* Telegram DM + Mini App toast; dedupe/throttle.

**Deliverables**

```
backend/app/alerts/
  models.py           # AlertRule(id, user_id, symbol, op, value, active, last_triggered_at)
  service.py          # evaluate_alerts(), trigger()
  routes.py           # POST/GET/DELETE /alerts
backend/schedulers/alerts_runner.py  # runs every 1m
frontend/miniapp/app/alerts/page.tsx
```

**Telemetry**

* `alerts_triggered_total{symbol}`, `alerts_eval_seconds`

**Tests**

* Boundary triggers; throttle window; invalid symbols 422.

---

# PR-045 — **Copy-Trading Integration (FXPro)** & Pricing Uplift

**Goal**
Offer **100% auto** copy-trading via FXPro (or chosen broker) as an **optional plan**, charging **+30%** on top (as you specified). Non-copy users remain in approval mode.

**Scope**

* “Copy-Trading” entitlement; backend execution path toggles to **auto place**.
* Broker API connector (abstracted), or managed account routing via EA with auto-execute flag.
* Billing rule: if `copy_trading=true` → final price = `base_price * 1.30`.

**Deliverables**

```
backend/app/copytrading/
  models.py           # CopySettings(user_id, enabled, risk_multiplier, max_dd, started_at)
  service.py          # place_copy_trade(approval_id, settings)
  pricing.py          # apply_copy_markup(plan_price)
  routes.py           # POST /copy/enable, POST /copy/disable
frontend/miniapp/app/copy/page.tsx
```

**Security**

* Explicit consent stored (versioned text); audit event on enable/disable.
* Safeguards: max position size cap, daily trade cap.

**Telemetry**

* `copy_trades_total{status}`, `copy_enable_total`

**Tests**

* Pricing uplift; path toggles to auto; risk caps enforced.

---

# PR-046 — Copy-Trading Risk & Compliance Controls

**Goal**
Add the **guard rails** and required disclosures to run auto execution safely.

**Scope**

* Disclosures acceptance (versioned); withdrawal of consent flow.
* Risk parameters per user: max leverage, max per trade risk, total exposure %, daily stop.
* Forced pause on rule breach; alert owner via Telegram.

**Deliverables**

```
backend/app/copytrading/risk.py        # evaluate_risk(user, proposed_trade)
backend/app/copytrading/disclosures.py # consent versioning helpers
backend/app/copytrading/routes.py      # PATCH /copy/risk, GET /copy/status
frontend/miniapp/app/copy/settings/page.tsx
```

**Env**

* Default caps (override per user): `COPY_MAX_EXPOSURE_PCT=50`, `COPY_MAX_TRADE_RISK_PCT=2`, `COPY_DAILY_STOP_PCT=10`.

**Security**

* Immutable consent logs in audit (PR-008).

**Telemetry**

* `copy_risk_block_total{reason}`, `copy_consent_signed_total`

**Tests**

* Breach scenarios; consent upgrade path; pause/unpause flow.

---

## How 35–46 plug into what’s already built

* **35–39** deliver the **Mini App** that users will live in every day: approvals, billing, devices.
* **40** hardens payments flows end-to-end.
* **41–42** give you a professional **EA SDK** with **encrypted** payloads and robust auth.
* **43–44** add **live positions** and **price alerts** (engagement + transparency).
* **45–46** implement **copy-trading** exactly as you want (auto execution with a **+30%** pricing rule) plus compliance/risk controls.

---


# PR-047 — Public Performance Page (Read-only, Marketing-grade)

**Goal**
A public, SEO-friendly page that showcases live stats (delayed, post-trade), equity curve, win rate, RR, and disclaimers.

**Scope**

* Next.js public route `/performance`.
* Server endpoints to serve **redacted**, **post-close** metrics.
* Strong disclaimers + “no forward guidance” copy.

**Deliverables**

```
frontend/web/app/performance/page.tsx
frontend/web/components/PerformanceHero.tsx
frontend/web/components/EquityChartPublic.tsx
frontend/web/components/StatsTiles.tsx
backend/app/public/performance_routes.py   # GET /public/performance/summary, /equity
```

**Data rules**

* Only **closed** trades, **T+X min** delay (configurable).
* No entry/SL/TP leak before close.

**Security**

* Public endpoints return **aggregates only**; no PII.

**Telemetry**

* `public_performance_views_total`

**Tests**

* Delay respected; aggregates match internal analytics.

---

# PR-048 — Auto-Trace to Third-Party Trackers (Post-Close)

**Goal**
Boost trust by pushing **closed trades** to third-party trackers (e.g., Myfxbook) after a safe delay.

**Scope**

* Background job that watches for newly closed trades and posts them.
* Pluggable adapter interface; start with webhook/export file.

**Deliverables**

```
backend/app/trust/trace_adapters.py   # interface + stub adapters
backend/app/trust/tracer.py           # enqueue_closed_trade(trade_id), worker
backend/schedulers/trace_worker.py    # cron/queue consumer
```

**Dependency**
Trade schema & close events from your store (migrated in PR-016, modeled after `DemoNoStochRSI.py`).

**Security**

* Strip client identifiers; delay publish until after exit.

**Telemetry**

* `trust_traces_pushed_total{adapter}`, `trust_trace_fail_total`

**Tests**

* Trade closes → queued → posted; failure → retry/backoff.

---

# PR-049 — Network Trust Scoring (Graph & Influence)

**Goal**
Compute a trust score from performance stability + social endorsements.

**Scope**

* Graph model: nodes(users), edges(verification/endorsement).
* Score = weighted combo of verified performance, tenure, endorsements.

**Deliverables**

```
backend/app/trust/graph.py       # import/export graph, compute scores
backend/app/trust/models.py      # Endorsement(user_id, peer_id, weight)
backend/app/trust/routes.py      # GET /trust/score (user), GET /trust/leaderboard (public)
frontend/web/components/TrustBadge.tsx
```

**Telemetry**

* `trust_scores_calculated_total`

**Tests**

* Deterministic scores on small graphs; anti-gaming checks (cap edge weights).

---

# PR-050 — Public Trust Index (Site Widget + API)

**Goal**
Publicly display **accuracy**, **avg RR**, **% verified trades**, **trust score band**.

**Scope**

* Public API + site widget; embed in affiliate/partner sites later.

**Deliverables**

```
backend/app/public/trust_index.py     # GET /public/trust-index
frontend/web/components/TrustIndex.tsx
```

**Data**

* Feeds from PR-047/048/049.

**Tests**

* Snapshot tests for widget rendering & JSON schema.

---

# PR-051 — Analytics: Trades Warehouse & Rollups

**Goal**
Create a **warehouse layer** that normalizes trades and produces rollups for fast charts.

**Scope**

* Star-ish schema: `trades_fact`, `dim_symbol`, `dim_day`, `daily_rollups`.

**Deliverables**

```
backend/app/analytics/models.py
backend/app/analytics/etl.py          # load_trades(), build_daily_rollups()
backend/alembic/versions/0010_analytics_core.py
```

**Sources**
Migrate fields from your SQLite tables (`trades`, `equity`) into Postgres rollups.

**Telemetry**

* `analytics_rollups_built_total`, `etl_duration_seconds`

**Tests**

* ETL idempotence; day buckets correct across DST/UTC.

---

# PR-052 — Equity & Drawdown Engine (Server)

**Goal**
Server-side services to compute equity curves, max DD, and summary stats from warehouse data.

**Scope**

* Equity from cumulative PnL; drawdown % from peak.
* Robust to gaps and partial days.

**Deliverables**

```
backend/app/analytics/equity.py        # compute_equity_series(range)
backend/app/analytics/drawdown.py      # compute_drawdown(equity_series)
backend/app/analytics/routes.py        # GET /analytics/equity, /analytics/drawdown
```

**Source alignment**
This consolidates functions you built in `LIVEFXPROFinal4.py` (equity, drawdown, P&L histograms).

**Tests**

* Known sequences produce expected DD; empty/short ranges handled.

---

# PR-053 — Performance Metrics: Sharpe, Sortino, Calmar, Profit Factor

**Goal**
Expose professional-grade KPIs computed over rolling windows.

**Scope**

* 30/90/365-day rolling variants; risk-free rate configurable.

**Deliverables**

```
backend/app/analytics/metrics.py   # sharpe, sortino, calmar, profit_factor, recovery_factor
backend/app/analytics/routes.py    # GET /analytics/metrics?window=90d
```

**Source alignment**
Derived from your existing metric functions in `LIVEFXPROFinal4.py`.

**Tests**

* Synthetic series; compare with reference formulas.

---

# PR-054 — Time-Bucketed Analytics (Hour/Day/Month + Heatmaps)

**Goal**
Breakdowns by hour-of-day, day-of-week, and month; output tables + heatmaps.

**Scope**

* Aggregations on trades_fact and daily_rollups.

**Deliverables**

```
backend/app/analytics/buckets.py    # group_by_hour, group_by_dow, group_by_month
backend/app/analytics/routes.py     # GET /analytics/buckets?type=hour|dow|month
frontend/miniapp/app/analytics/page.tsx
frontend/miniapp/components/Heatmap.tsx
```

**Source alignment**
Extends your analytics footprint and charts seen in `LIVEFXPROFinal4.py`.

**Tests**

* Time-zone correctness; empty buckets return zeros not nulls.

---

# PR-055 — Client Analytics UI (Mini App) + PNG/CSV Export

**Goal**
A polished analytics interface in the Mini App with **exports**.

**Scope**

* Equity chart with event markers; win-rate donut; trade distribution by instrument.
* Export buttons (CSV/PNG) using server routes.

**Deliverables**

```
frontend/miniapp/app/analytics/page.tsx
frontend/miniapp/components/Equity.tsx
frontend/miniapp/components/WinRateDonut.tsx
frontend/miniapp/components/Distribution.tsx
```

**Server**

* Reuse chart renderer from PR-020 for PNG; table routes for CSV.

**Telemetry**

* `analytics_exports_total{type}`

**Tests**

* UI snapshots; export files download and correct headers.

---

# PR-056 — Operator Revenue & Cohorts (MRR/ARR, Churn, ARPU)

**Goal**
Give you an owner’s dashboard for revenue KPIs with cohort retention.

**Scope**

* Aggregate Stripe/Telegram payments into `revenue_snapshots`.
* Compute MRR, ARR, churn, ARPU, cohort table (12-month).

**Deliverables**

```
backend/app/revenue/models.py
backend/app/revenue/service.py         # calculate_mrr(), get_cohort_analysis(...)
backend/app/revenue/routes.py          # GET /revenue/summary, /revenue/cohorts
backend/alembic/versions/0011_revenue_snapshots.py
frontend/web/app/admin/revenue/page.tsx
```

**Logic**

* Mirrors the cohort/MRR logic we outlined earlier (now implemented).
* Snapshot daily via scheduled task.

**Tests**

* Mixed annual/monthly subscriptions; cohort math; snapshot TTL.

---

# PR-057 — CSV/JSON Export & Public Share Links (Redacted)

**Goal**
Users can export their trade history and share **public links** with PII stripped.

**Scope**

* One-click export; signed URL valid for 24h; public share token route.

**Deliverables**

```
backend/app/exports/service.py     # generate_export(user_id, format)
backend/app/exports/routes.py      # POST /exports -> {url}, GET /share/{token}
storage/s3.py                      # or local fs
```

**Security**

* Export URLs are single-use, time-boxed; redaction checks.

**Telemetry**

* `exports_generated_total{format}`, `exports_downloaded_total`

**Tests**

* Token expires; PII not present; format schema validated.

---

# PR-058 — Owner/Operator Analytics Panels (Grafana + Alerts)

**Goal**
Ship pre-made Grafana dashboards & alert rules for **business + tech** health.

**Scope**

* Dashboards: API latency, error rates, signal ingestion rate, approvals, copy-trading success rate, billing events, MRR trend.
* Alerting: p95 latency > SLO, payment webhook failures, EA poll error spikes.

**Deliverables**

```
grafana/dashboards/api.json
grafana/dashboards/business.json
grafana/alerts/*.yaml
docs/runbooks/alerts.md
```

**Telemetry**
Uses metrics we’ve been adding (PR-009 + later counters).

**Tests**

* Not code-tests; validation by running Grafana in docker-compose and ensuring panels connect.

---

## Where these connect back to your code

* **Trade data & analytics** are grounded in your current logic/files:

  * Equity/Drawdown/Histograms → `LIVEFXPROFinal4.py` (migrated into PR-052/053/054/055).
  * Trade fields & lifecycle → `DemoNoStochRSI.py` (migrated in PR-016/051).
* **Trust & Transparency** (PR-047–050) tie into your “publish after close” requirement and third-party tracing concept.

---


# PR-059 — User Preferences & Notification Center

**Goal**
Give every user a single place to manage preferences: instruments, risk alerts, notification channels (Telegram, email, web push), quiet hours, and digest frequency.

**Scope**

* DB models for preferences.
* Read/write API + Mini App UI.
* Hooks for alerts (ties into PR-044), billing reminders (PR-033/034), marketing nudges (PR-032).
* Telegram DMs and email templates.

**Deliverables**

```
backend/app/prefs/models.py
backend/app/prefs/schemas.py
backend/app/prefs/service.py
backend/app/prefs/routes.py                 # GET/PUT /api/v1/prefs
frontend/miniapp/app/settings/notifications/page.tsx
frontend/miniapp/components/QuietHours.tsx
email/templates/digest.html
```

**Settings**

* Instruments on/off (gold, sp500, crypto, …).
* Alert types (price, drawdown, copy-risk), frequency, quiet hours (local TZ).
* Channels: Telegram (default), email, web push (PWA).

**Security**

* JWT required; tenant-safe reads; audit write events (PR-008).

**Telemetry**

* `prefs_updated_total`, `digests_sent_total{channel}`

**Tests**

* CRUD + quiet hours enforcement; invalid TZ → 422.

**Relevant wiring**
Billing reminders via Telegram/email tie back to your **MarketingBot** patterns (structured CTAs).

---

# PR-060 — Messaging Bus & Templates (Email/Telegram/Web Push)

**Goal**
Centralize multi-channel messaging so features (alerts, onboarding, dunning, education) send consistent, branded messages.

**Scope**

* Message queue facade (Redis/Celery) with “campaign” + “transactional” lanes.
* Template system (Jinja2 for email/Telegram MarkdownV2-safe); push via PWA.

**Deliverables**

```
backend/app/messaging/bus.py             # enqueue_message(), enqueue_campaign()
backend/app/messaging/templates.py       # render_email(), render_telegram(), render_push()
backend/app/messaging/senders/*.py       # email.py, telegram.py, push.py
backend/app/messaging/routes.py          # POST /api/v1/messaging/test (owner)
frontend/miniapp/lib/push.ts             # registerServiceWorker(), subscribe()
```

**Security**

* Telegram bot tokens via secrets; sender address allowlist.

**Telemetry**

* `messages_sent_total{channel,type}`, `message_fail_total{reason}`

**Tests**

* Template render snapshots; channel fallbacks (e.g., email if push disabled).

**Relevant wiring**
Telegram sender reuses secure webhook service from your **bot.py/handlers** refactor.

---

# PR-061 — Knowledge Base CMS (for Education Hub & AI)

**Goal**
Provide a lightweight CMS to author docs/FAQs/lessons used by **Education Hub (PR-089)** and as **AI knowledge** for support (PR-062).

**Scope**

* Markdown articles with tags, locales, status (draft/published).
* Editor UI (+upload images).
* Versioning & approvals.

**Deliverables**

```
backend/app/kb/models.py                 # Article, Tag, Attachment, Locale
backend/app/kb/routes.py                 # CRUD (owner/admin), public read
frontend/web/app/admin/kb/page.tsx       # editor UI
frontend/miniapp/app/education/page.tsx  # list & read (ties to PR-089)
```

**Security**

* Admin-only writes; public read only for published.

**Telemetry**

* `kb_articles_published_total`, `kb_views_total`

**Tests**

* CRUD, version bump, locale fallback.

**Relevant wiring**
Feeds Education Hub content UI and links that your **GuideBot** previously pushed.

---

# PR-062 — AI Customer Support Assistant (RAG + Guardrails)

**Goal**
24/7 AI support that answers from **your KB** and **product docs** without leaking secrets; escalates to human when needed.

**Scope**

* RAG indexer over KB (PR-061) + selected product specs.
* Safety layer: redaction, policy checks, “no private info” rules.
* Channels: Telegram (inline chat) + Web widget.

**Deliverables**

```
backend/app/ai/indexer.py               # build/refresh embeddings from KB
backend/app/ai/guardrails.py            # no-secrets, no-pii, no-trading-advice limits
backend/app/ai/assistant.py             # chat(session_id, question) -> answer + citations
backend/app/ai/routes.py                # POST /ai/chat
frontend/miniapp/components/SupportChat.tsx
frontend/web/components/SupportWidget.tsx
```

**Security**

* Strip tokens/keys; never reveal config/paths.
* Refuse financial advice; point to disclaimers.

**Telemetry**

* `ai_chat_total{result}`, `ai_guard_block_total{policy}`

**Tests**

* Answers include citations; redaction works; policy refusal paths.

---

# PR-063 — Ticketing & Human Escalation

**Goal**
When AI can’t solve it, hand off to a human support queue with full context.

**Scope**

* Ticket model; create from AI chat/session or user action.
* Owner/Admin portal to triage, respond, close.
* Telegram DM ping for urgent severity.

**Deliverables**

```
backend/app/support/models.py           # Ticket(id,user_id,subject,body,severity,status,channel,context)
backend/app/support/routes.py           # POST /support/tickets, GET/POST /support/tickets/{id}
frontend/web/app/admin/support/page.tsx
backend/app/messaging/integrations/telegram_owner.py  # ping owner
```

**Telemetry**

* `tickets_opened_total{severity}`, `tickets_resolved_total`

**Tests**

* Create from AI chat; SLA clock; close w/ note; owner ping.

---

# PR-064 — Education Content Pipeline & Quiz Engine (backend for PR-089)

**Goal**
Serve **micro-courses** with quizzes, progress tracking, and rewards (credits/discounts).

**Scope**

* Course/lesson/quiz models; attempts; scoring; reward issuance.
* UI wiring for Education Hub (PR-089).

**Deliverables**

```
backend/app/education/models.py         # Course, Lesson, Quiz, Attempt, Reward
backend/app/education/routes.py         # GET courses, POST attempt
backend/app/education/rewards.py        # grant_discount(user, percent, expires_at)
frontend/miniapp/app/education/lesson/[id]/page.tsx
frontend/miniapp/components/Quiz.tsx
```

**Telemetry**

* `education_quiz_attempts_total`, `education_rewards_issued_total`

**Tests**

* Attempt grading; rate-limit retakes; reward issuance recorded.

---

# PR-065 — Price Alerts UX Enhancements (Smart Rules & Cooldowns)

**Goal**
Upgrade alerts (PR-044) with **smart conditions** and a polished UI.

**Scope**

* Conditions: cross-above/below, % change over window, RSI threshold (from strategy indicators), daily high/low touch.
* Cooldown to avoid alert spam; per-rule mute/unmute.
* Multi-channel (Telegram + push + email via PR-060).

**Deliverables**

```
backend/app/alerts/rules.py           # smart rules & evaluation helpers
frontend/miniapp/app/alerts/page.tsx  # enhanced UI (rule builder)
```

**Telemetry**

* `alerts_rule_created_total{type}`, `alerts_muted_total`

**Tests**

* Rule parsing → evaluation; cooldown respected.

---

# PR-066 — Owner Automations: Onboarding & Lifecycle Journeys

**Goal**
Point-and-click **journey builder** for onboarding and retention automations (multi-channel).

**Scope**

* Journey + step models; triggers (signup, first approval, payment fail, churn risk).
* Actions (send DM/email/push, apply tag, schedule next step).
* Visual status and per-user journey logs.

**Deliverables**

```
backend/app/journeys/models.py
backend/app/journeys/engine.py         # evaluate triggers, execute steps
backend/app/journeys/routes.py         # CRUD journeys (owner/admin)
frontend/web/app/admin/journeys/page.tsx
```

**Telemetry**

* `journey_started_total{name}`, `journey_step_fired_total{name,step}`

**Tests**

* Simulate signup→first trade flow; idempotency of steps.

**Relevant wiring**
Uses **MarketingBot** messaging patterns and CTAs.

---

# PR-067 — Owner Automations: Backups, DR, and Env Promotion

**Goal**
Automate daily backups, integrity checks, and safe promotion from dev→staging→prod.

**Scope**

* DB dumps to S3 + restore scripts.
* Encryption at rest; retention policy.
* “Promote” script to tag images, run migrations, warm caches.

**Deliverables**

```
ops/backup/backup.sh
ops/backup/restore.sh
ops/promote/release.sh
docs/runbooks/backup_restore.md
```

**Telemetry**

* `backup_success_total`, `backup_bytes_total`, `release_promoted_total`

**Tests**

* Dry-run backup; checksum verifies; restore into throwaway DB.

---

# PR-068 — Compliance & Privacy Center (DSAR Export/Delete)

**Goal**
User-initiated data export and deletion workflows (GDPR-style) with audit trails.

**Scope**

* Export ZIP (JSON/CSV) of user data (trades redacted, billing refs without PCI).
* Delete request with cooling-off period and confirmation.
* Admin hold override (active disputes/chargebacks).

**Deliverables**

```
backend/app/privacy/models.py              # Request(type: export/delete, status, created_at, processed_at)
backend/app/privacy/routes.py              # POST /privacy/requests (user), GET /privacy/requests/{id}
backend/app/privacy/exporter.py
backend/app/privacy/deleter.py
```

**Security**

* Identity verification; irreversible delete after window; audit log (PR-008).

**Telemetry**

* `privacy_requests_total{type,status}`

**Tests**

* Export bundle schema; delete flow staging; hold condition blocks.

---

# PR-069 — Internationalization (Web/Mini App) & Copy System

**Goal**
Make the UI multi-lingual with professional copy control.

**Scope**

* i18n setup (react-intl or next-intl) with locale files.
* Copy registry for product/legal/marketing text; A/B hooks.

**Deliverables**

```
frontend/miniapp/i18n/config.ts
frontend/miniapp/i18n/en.json
frontend/miniapp/i18n/es.json   # starter
frontend/web/i18n/*.json
docs/copy/style_guide.md
```

**Telemetry**

* `ui_locale_selected_total{locale}`

**Tests**

* Locale switch persists; missing keys detected in CI.

---

# PR-070 — Telegram Bot Localization & Content Localization

**Goal**
Localize bot commands/responses and content distribution to match user locale preferences (PR-059).

**Scope**

* Bot i18n loader; per-user locale detection (Telegram profile + prefs).
* Localized **ContentDistribution** routing captions & **GuideBot** links.

**Deliverables**

```
backend/app/telegram/i18n.py              # get_text(key, locale)
backend/app/telegram/handlers/*.py        # replace literals with i18n keys
content/locales/en/*.md
content/locales/es/*.md
```

**Telemetry**

* `telegram_locale_used_total{locale}`, `distribution_localized_total{locale}`

**Tests**

* Commands render localized; fallback to English; content routes to same groups with localized captions.

**Relevant wiring**
Maps directly onto your **ContentDistribution.py** and **GuideBot.py** behaviors, now with locale-aware captions & links.

---

## how 59–70 fit into the whole build

* **59–60** create the **preferences + messaging spine** used by alerts, billing, marketing, and education.
* **61–63** deliver a **safe AI support loop** with clean escalation.
* **64–65** complete the **Education Hub** + smarter **Alerts** UX.
* **66–67** automate the **owner’s operations**.
* **68** gives you a **compliance-ready privacy center**.
* **69–70** globalize both **web/Mini App** and **Telegram** content.

---


# PR-071 — Strategy Engine Integration (PPO + Multi-Strategy Orchestrator)

**Goal**
Unify classic Fib/RSI and your PPO model into a pluggable “strategy engine” with a scheduler and fan-out to signals API.

**Source alignment**
PPO loop, 15-min candle sync, guards & logging come from `LIVEFXPROFinal4.py`.

**Scope**

* Strategy registry: `fib_rsi`, `ppo_gold`, future variants.
* Shared context: data fetch (PR-013), market gating (PR-012), order builder (PR-015).
* Standard outputs → `SignalCandidate` (PR-014) → POST (PR-017/021).

**Deliverables**

```
backend/app/strategy/registry.py     # register_strategy(name, engine)
backend/app/strategy/scheduler.py    # run_strategies(on_new_candle(...))
backend/app/strategy/ppo/
  runner.py                           # model load, infer, thresholding
  models/                             # model + scaler artifacts loader
```

**Env**
`STRATEGIES_ENABLED=fib_rsi,ppo_gold` • `PPO_MODEL_PATH`, `PPO_THRESHOLD`

**Telemetry**
`strategy_runs_total{name}`, `strategy_emit_total{name}`

**Tests**
Mock model → deterministic emits; disable by env → no emits.

---

# PR-072 — Signal Generation & Distribution (New-Candle Detection, Routing)

**Goal**
Emit signals **exactly at new 15-min bar** boundaries and route to the right client/bot/web channels.

**Source alignment**
New-candle detection window, check interval tuning, and notification toggles live in `LIVEFXPROFinal4.py`.

**Scope**

* `is_new_candle(tf, window)` helper with drift tolerance (CANDLE_CHECK_WINDOW).
* When a signal is accepted → send to Signals API (PR-021) and publish preview to admin Telegram (optional) using your bot patterns.

**Deliverables**

```
backend/app/strategy/candles.py
backend/app/strategy/publisher.py     # to API + optional Telegram admin
```

**Env**
`CHECK_INTERVAL_SECONDS=10` • `CANDLE_CHECK_WINDOW=60` (as in your file).

**Telemetry**
`signal_publish_total{route}`

**Tests**
Boundary times; duplicate prevention in a single bar.

---

# PR-073 — Trade Decision Logging (Full Audit Trail & Analytics Hooks)

**Goal**
Persist **every** decision (features, rationale, thresholds) for replay, ops, and future model governance.

**Source alignment**
Decision/equity/analytics logging in `LIVEFXPROFinal4.py` → migrate to Postgres with JSONB payloads.

**Deliverables**

```
backend/app/strategy/logs/models.py   # DecisionLog(id, ts, strategy, symbol, features jsonb, outcome enum, note)
backend/app/strategy/logs/service.py  # record_decision(...)
backend/alembic/versions/0012_decision_logs.py
```

**Telemetry**
`decision_logs_total{strategy}`

**Tests**
Large feature payload sizes; redaction of PII; query by date range.

---

# PR-074 — Risk Management System (Drawdown, Equity Floor, Position Sizing)

**Goal**
Centralize risk guards & position sizing so **all** strategies obey the same safety rails.

**Source alignment**
Max drawdown %, min equity thresholds, pause/resume in your live bot.

**Deliverables**

```
backend/app/risk/guards.py            # enforce_max_dd(), min_equity()
backend/app/risk/position_size.py     # all-in or fraction, tick rounding
backend/app/risk/routes.py            # GET/PUT org defaults; GET my effective caps
```

**Env**
`MAX_DRAWDOWN=0.10` • `MIN_EQUITY_GBP=500` (defaults from your file).

**Telemetry**
`risk_block_total{reason}`

**Tests**
DD breach blocks trades; equity floor enforced; rounding to broker ticks.

---

# PR-075 — Trading Controls in Mini App (Pause/Resume, Sizing, Toggles)

**Goal**
Expose **pause/resume**, **position size**, and **notifications on/off** in the Mini App (user & owner scopes).

**Scope**

* Wires into guards (PR-074) and runtime loop (PR-019).
* Live status indicator (“Trading: Running/Paused”).

**Deliverables**

```
frontend/miniapp/app/trading/page.tsx
frontend/miniapp/components/TradingControls.tsx
backend/app/risk/routes.py   # add PATCH /trading/pause|resume, PUT /trading/size
```

**Telemetry**
`trading_paused_total{actor}`, `trading_size_changed_total`

**Tests**
Pause stops emits; resume restarts on next bar.

---

# PR-076 — Backtesting Framework (Exact Strategy Parity)

**Goal**
Reproducible **offline** backtests that run Fib/RSI and PPO with the **same code paths** used live.

**Scope**

* Disk data adapters (CSV/Parquet).
* Deterministic engine runner; metrics parity with PR-052/053.

**Deliverables**

```
backend/app/backtest/runner.py       # run(strategy, data_source, params) -> report
backend/app/backtest/report.py       # PnL, equity, DD, metrics; export HTML/CSV
scripts/backtest_fib_rsi.sh
```

**Source alignment**
Parameters/indicators from `DemoNoStochRSI.py` + PPO paths from live file.

**Telemetry**
`backtest_runs_total{strategy}`

**Tests**
Golden fixtures; metrics match expected.

---

# PR-077 — Walk-Forward & Paper-Trade Promotion Pipeline

**Goal**
Automate **walk-forward** evaluation and **paper-trade** dry-run before promoting a model to live.

**Scope**

* K-fold walk-forward schedule; thresholds for promotion.
* Paper-trade mode routes orders to a sandbox account.

**Deliverables**

```
backend/app/research/walkforward.py
backend/app/research/promotion.py       # gate: pass thresholds → set strategy status=paper/live
backend/app/trading/runtime/modes.py    # paper vs live placement
```

**Telemetry**
`promotion_attempt_total{result}`, `paper_orders_total`

**Tests**
Fail thresholds → no promotion; pass → status=live; paper ledger correct.

---

# PR-078 — Strategy Versioning, Canary & Shadow Trading

**Goal**
Run **vNext** alongside **vCurrent** without affecting users; compare outcomes.

**Scope**

* Shadow mode: generate decisions/logs but **do not** publish/execute.
* Canary % rollout for copy-trading users (owner-controlled).

**Deliverables**

```
backend/app/strategy/versioning.py      # register versions, routing rules
backend/app/strategy/shadow.py          # mirror decisions to logs
backend/app/strategy/routes.py          # PATCH /strategy/rollout (owner)
```

**Telemetry**
`shadow_decisions_total{version}`, `canary_traffic_percent`

**Tests**
Shadow emits logs only; canary split respects configured %.

---

# PR-079 — Feature Store & Data Quality Monitor

**Goal**
Central store for **features** (RSI, ROC, ATR, pivots, etc.) with **quality checks** (staleness, NaNs, regime shifts).

**Scope**

* Persist computed features per symbol/timestamp.
* Quality daemon runs checks; raises alerts.

**Deliverables**

```
backend/app/features/store.py            # put/get features
backend/app/features/quality.py          # check_missing, drift
backend/app/ops/alerts.py                # reuse to ping owner on violations
backend/alembic/versions/0013_features.py
```

**Source alignment**
Your features array and scaler warnings in `LIVEFXPROFinal4.py`.

**Telemetry**
`feature_quality_fail_total{type}`

**Tests**
Inject NaNs → alert; stale timestamps → alert.

---

# PR-080 — Model Explainability & Decision Explorer

**Goal**
Surfacing **feature importance/SHAP-like** hints and searchable decision logs.

**Scope**

* Compute per-decision contributions (approx or post-hoc).
* UI to filter by date/strategy/result and inspect “why”.

**Deliverables**

```
backend/app/explain/attribution.py
frontend/web/app/admin/explain/page.tsx
backend/app/strategy/logs/routes.py     # GET /decisions/search
```

**Telemetry**
`explain_requests_total`, `decision_search_total`

**Tests**
Attribution sums to delta within tolerance; filters return correct sets.

---

# PR-081 — Client Paper-Trading (Sandbox) Mode

**Goal**
Any user can opt into **paper trading** to test approvals without risking capital.

**Scope**

* Virtual portfolio per user; fills at mid/bid/ask configurable; slippage model.
* Mini App toggle; analytics count paper separately.

**Deliverables**

```
backend/app/paper/models.py
backend/app/paper/engine.py        # fill rules
backend/app/paper/routes.py        # POST enable/disable, GET statement
frontend/miniapp/app/paper/page.tsx
```

**Telemetry**
`paper_fills_total`, `paper_pnl_total`

**Tests**
Fill math; slippage; toggle isolation.

---

# PR-082 — API Quotas & Trading Ops Limits (Per User/Tenant)

**Goal**
Protect system resources with **quotas** and per-feature limits (signals/day, alerts, exports), distinct from generic rate-limit (PR-005).

**Scope**

* Quota definitions by plan; counters in Redis/Postgres.
* 429 with problem+json + “reset at” time.

**Deliverables**

```
backend/app/quotas/models.py
backend/app/quotas/service.py      # check_and_consume(user, quota_key)
backend/app/quotas/routes.py       # GET /me/quotas
```

**Telemetry**
`quota_block_total{key}`

**Tests**
Exceed → blocked until reset; plan upgrade increases limits.

---

# PR-083 — FlaskAPI Decommission & Gateway Consolidation

**Goal**
Migrate remaining consumers to the new **Gateway** and deprecate legacy `FlaskAPI.py` endpoints cleanly.

**Source alignment**
Legacy routes: price, trades, image serving, auth header checks. Replace with Gateway equivalents introduced earlier.

**Scope**

* One-to-one route mapping, 301/410 as appropriate.
* SocketIO → WebSocket alternative (FastAPI/WebSocket) if used.

**Deliverables**

```
backend/app/gateway/migration.md   # route map old→new
backend/app/gateway/compat.py      # temporary shims (feature flagged)
ops/runbooks/flask_deprecate.md
```

**Telemetry**
`legacy_calls_total` (should trend to zero)

**Tests**
Compat shims return/transform correctly; feature flag off → gone.

---

## how 71–83 slot into your whole build

* **71–75**: your trading intellect, faithfully rebuilt (Fib/RSI + PPO, precise bar timing, risk & controls, Mini App switches).
* **76–80**: pro-grade research + governance rails (backtests, walk-forward, canary/shadow, feature QA, explainability).
* **81–83**: client sandboxing, fair-use guardrails, and final migration off legacy Flask.


---

# PR-084 — Web Platform Bootstrap (Next.js Marketing + Shared UI Library)

**Goal**
Stand up a production-grade **Next.js 14 (App Router)** web platform for landing, docs, and a shared UI kit used by both the marketing site and the Mini App.

**Scope**

* Next.js app (`/frontend/web`) with Tailwind, dark mode, PWA baseline.
* Shared design system (`/frontend/packages/ui`) for charts/cards/modals reused in Mini App.
* Router skeleton for `/`, `/pricing`, `/legal/*`, `/performance` (will use PR-047 later).

**Deliverables**

```
/frontend/web/
  package.json, next.config.js, tsconfig.json
  app/layout.tsx, app/page.tsx
  app/pricing/page.tsx
  app/legal/{terms,privacy,risk,cookies}/page.tsx
  public/icons/*  public/manifest.json
/frontend/packages/ui/
  package.json
  components/{Card.tsx, Badge.tsx, Button.tsx, Modal.tsx, Tabs.tsx}
  charts/{LineChart.tsx, Donut.tsx}     # wrapped around lightweight lib
```

**Env**

* `NEXT_PUBLIC_API_BASE`
* PWA name/description from config (PR-002).

**Security**

* No secrets in client bundle; API base read from env at build.

**Telemetry**

* `web_page_view_total{route}`
* `web_cwv_lcp_seconds` (reported via web-vitals endpoint)

**Tests**

* Rendering snapshots; nav links; 404 route.

**Verification**

* `pnpm dev` → pages render; Lighthouse > 90.

---

# PR-085 — Telegram Deep Linking (TG ↔ Web) & Telegram Login OAuth

**Goal**
Seamless hand-off between Telegram and Web with OAuth-style login via **Telegram Login Widget**.

**Scope**

* Deep links from bots → web (e.g., `/billing`, `/devices`, `/signup?src=tg`).
* “Sign in with Telegram” → verify signature server-side → mint short-lived JWT (aud=web).

**Deliverables**

```
frontend/web/app/(auth)/login/page.tsx         # Telegram login button
backend/app/oauth/telegram.py                   # verify_login_widget(payload) -> user
backend/app/oauth/routes.py                     # POST /oauth/telegram -> JWT
backend/app/deeplinks/helpers.py                # build_deeplink("billing", ctx)
```

**Notes tying to your code**

* Bot buttons in **bot.py / ContentDistribution** will use these deep links (e.g., pricing/checkout, devices), replacing hardcoded links.

**Security**

* Validate Telegram login signature with bot token; 10-minute replay window; bind JWT `sub=telegram_id`.

**Telemetry**

* `oauth_telegram_login_total{result}`

**Tests**

* Valid payload → 200 with JWT; invalid hash → 401; clock skew → 401.

---

# PR-086 — SEO, Performance & CDN + A/B Testing Hooks

**Goal**
Ship a **fast marketing site** with SEO fundamentals and built-in A/B testing to optimize conversion.

**Scope**

* OG/meta tags, JSON-LD, sitemap/robots.txt, image optimization.
* CDN (Cloudfront/Fastly) headers for caching; ISR (revalidate).
* Simple experiment framework (URL param or cookie) to toggle hero copy / CTA.

**Deliverables**

```
frontend/web/app/(marketing)/layout.tsx         # SEO
frontend/web/lib/ab.ts                          # getVariant(), setVariant()
ops/cdn/headers.yaml                            # cache control, security headers
```

**Telemetry**

* `ab_variant_view_total{name,variant}`
* `web_tti_seconds`, `web_cls_score` (web-vitals)

**Tests**

* Variant switch; meta tags present; canonical URLs.

---

# PR-087 — Next-Gen Trading Dashboard (Web + Mobile Responsive)

**Goal**
A **real-time dashboard** with equity curve, open positions, approvals, and visual signals (“Confidence Meter”, “Signal Maturity”).

**Depends on**: PR-084-086, PR-021/022 (Signals/Approvals), PR-052-055 (analytics), PR-081 (paper toggles)

**Deliverables**

```
frontend/web/app/dashboard/page.tsx
frontend/packages/ui/trade/SignalMaturity.tsx
frontend/packages/ui/trade/ConfidenceMeter.tsx
frontend/web/lib/ws.ts                # WebSocket wrapper
```

**Backend**

* `/ws` streams: open approvals, positions, equity deltas (FastAPI WebSocket).
* Reuse analytics services (equity/drawdown) migrated from your live code.

**Telemetry**

* `dashboard_ws_clients_gauge`, `dashboard_card_click_total{name}`

**Tests**

* WS connect/reconnect; meters compute identical values to server meta.

---

# PR-088 — Gamified Client Dashboard

**Goal**
Boost retention with badges, leaderboards (opt-in, privacy-safe), and **Trader Levels**.

**Depends on**: PR-087, PR-051-055

**Deliverables**

```
backend/app/gamification/models.py     # Badge, EarnedBadge, Level, LeaderboardOptIn
backend/app/gamification/service.py
backend/app/gamification/routes.py     # GET /me/badges, POST /leaderboard/opt-in
frontend/web/app/dashboard/gamified/page.tsx
```

**Mechanics**

* Badges: “10 Approved Trades”, “90-Day Profit Streak”.
* Level XP = trades approved + PnL stability (risk-adjusted).
* Leaderboard ranks by % return / risk-adjusted score (opt-in).

**Telemetry**

* `badges_awarded_total{name}`, `leaderboard_optin_total`

**Tests**

* XP accrual; privacy safeguards; leaderboard determinism.

---

# PR-089 — In-App Education Hub

**Goal**
Serve micro-courses (RSI, risk) with quizzes and rewards; integrated with Mini App & web.

**Depends on**: PR-061 (KB CMS), PR-064 (quiz backend)

**Deliverables**

```
frontend/web/app/education/page.tsx
frontend/web/components/CourseCard.tsx, LessonContent.tsx, QuizPane.tsx
```

**Rewards**

* Credits/discounts via PR-064 → updates entitlements/pricing view.

**Telemetry**

* `education_lessons_completed_total`, `education_quiz_pass_total`

**Tests**

* Lesson progress state; reward issuance path.

---

# PR-090 — Custom Client Theme Engine

**Goal**
Per-user theming: “Professional”, “Dark Trader”, “Gold Minimal”. Persisted to profile and applied across web + Mini App.

**Depends on**: PR-084, PR-035 (Mini App bootstrap)

**Deliverables**

```
backend/app/profile/theme.py           # get/set theme
frontend/packages/ui/theme/{professional,darkTrader,goldMinimal}.ts
frontend/web/app/settings/theme/page.tsx
frontend/miniapp/app/settings/theme/page.tsx
```

**Telemetry**

* `theme_selected_total{name}`

**Tests**

* SSR/CSR consistent; persists in JWT profile claims.

---

# PR-091 — Forecast / AI Analyst Mode

**Goal**
Daily **AI-written “Market Outlook”** with volatility zones & correlated risk view.

**Depends on**: PR-052/053 (analytics), PR-062 (AI assistant infra)

**Deliverables**

```
backend/app/ai/analyst.py         # build_outlook(): pulls equities, DD, vol, correlations
backend/schedulers/daily_outlook.py
frontend/web/app/outlook/page.tsx
backend/app/messaging/templates.py # add “Daily Outlook” template (email/Telegram)
```

**Notes from your code**
Use GOLD analytics, RSI/ROC context to annotate narrative sensibly.

**Telemetry**

* `ai_outlook_published_total{channel}`

**Tests**

* Narrative includes data citations; extreme values handled.

---

# PR-092 — AI Fraud & Anomaly Detection

**Goal**
Detect suspicious MT5 execution patterns (slippage, latency bursts, out-of-band fills) → flag in Admin.

**Depends on**: PR-016 (trade store), PR-043 (positions), PR-099 (admin – coming later)

**Deliverables**

```
backend/app/fraud/models.py         # AnomalyEvent(user, trade_id, type, score, details)
backend/app/fraud/detectors.py      # slippage_zscore(), latency_spike()
backend/app/fraud/routes.py         # GET /fraud/events (admin)
backend/schedulers/fraud_scan.py
```

**Telemetry**

* `fraud_events_total{type}`

**Tests**

* Synthetic slippage; false positives < threshold.

---

# PR-093 — Decentralized Trade Ledger (Optional)

**Goal**
Post-close **hashes of trades** to a lightweight chain for public verifiability (opt-in).

**Depends on**: PR-047/048 (public performance, tracer)

**Deliverables**

```
backend/app/trust/ledger/adapters.py    # polygon, arbitrum (stub)
backend/app/trust/ledger/service.py     # submit_hash(closed_trade)
backend/app/trust/ledger/routes.py      # GET /public/proof/{trade_id}
```

**Security**

* Only publish **after close**; redact quantities/params; publish hash & timestamp.

**Telemetry**

* `ledger_submissions_total{chain}`, `ledger_fail_total`

**Tests**

* Hash matches recomputed; chain call retried on fail.

---

# PR-094 — Social Verification Graph

**Goal**
Users verify peers (Telegram/Discord connections), generating an **influence-weighted** trust network.

**Depends on**: PR-093 (proof urls optional), PR-059 (prefs/profile)

**Deliverables**

```
backend/app/trust/social/models.py     # VerificationEdge(user_id, peer_id, weight)
backend/app/trust/social/routes.py     # POST /verify/{peer_id}, GET /me/social
frontend/web/app/trust/social/page.tsx
```

**Telemetry**

* `social_verifications_total`, `social_influence_score_gauge`

**Tests**

* Edge creation limits; anti-sybil checks (cap edges per window).

---

# PR-095 — Public Trust Index

**Goal**
Publish **accuracy**, **avg RR**, **% verified trades**, and **network trust band** as a public widget + API.

**Depends on**: PR-047-050, PR-093-094

**Deliverables**

```
backend/app/public/trust_index.py      # GET /public/trust-index
frontend/web/components/TrustIndex.tsx
frontend/web/app/trust/page.tsx
```

**Computation**

* Accuracy and RR from analytics rollups (PR-051-053).
* Verified % from ledger (PR-093) and tracer (PR-048).
* Trust band from social graph (PR-094) + performance stability.

**Telemetry**

* `public_trust_index_views_total`

**Tests**

* JSON schema contract; widget displays sane values with empty data.

---

## Where these hook into your current code

* **Bots → Web deep links (PR-085)** replace ad-hoc links in your **bot.py**, **ContentDistribution.py**, and **MarketingBot.py** flows so users land in the right web/PWA views for billing, devices, education, etc.
* **Analytics & visuals (PR-087/091)** reuse equity/drawdown/indicator logic you built in **LIVEFXPROFinal4.py**.
* **Public trust (PR-093-095)** implements the “publish after close / third-party proof” concept you asked for, tied to post-trade tracing.

---


# PR-096 — Affiliate & Partner Marketplace

**Goal**
Launch a partner channel for brokers/influencers/affiliates with tracked referrals, commissions, and payouts.

**Depends on**: PR-033/034 (payments), PR-085 (TG↔Web deep links), PR-056 (revenue snapshots)

## Scope

* Affiliates can register, get links/codes, view clicks, trials, and conversions.
* Commission models: CPA (fixed) and RevShare (% of net receipts).
* Payouts via Stripe Connect (or manual bank transfer export).
* UTM tracking across Telegram ↔ Web ↔ Mini App.
* Fraud controls (self-referrals, multi-accounting, cookie abuse).

## Deliverables

```
backend/app/affiliates/models.py     # Affiliate, Program, Link, Click, Conversion, Commission, Payout
backend/app/affiliates/service.py    # record_click(), attribute_conversion(), accrue_commission()
backend/app/affiliates/routes.py     # POST /apply, GET /me/links, GET /me/earnings, POST /payouts/request
backend/app/affiliates/attribution.py# last-touch with decay; TG deep-link param parsing
backend/alembic/versions/0014_affiliates.py
frontend/web/app/partners/apply/page.tsx
frontend/web/app/partners/dashboard/page.tsx
frontend/web/components/AffiliateLinkCard.tsx
```

## Env/Config

* `AFFILIATE_COOKIE_DAYS=30`
* `AFFILIATE_MAX_SELF_REFERRAL=0`
* `AFFILIATE_MIN_PAYOUT_GBP=100`
* Optional: `STRIPE_CONNECT_ENABLED=true`

## Security

* KYC for payouts (collect minimal data).
* Detect self-referrals (same device/IP/Telegram ID).
* Immutable commission ledger; audited writes.

## Telemetry

* `affiliate_clicks_total{source}`
* `affiliate_conversions_total{program}`
* `affiliate_commission_accrued_total`
* `affiliate_payouts_total{status}`

## Tests

* Click→conversion attribution; decay window; self-referral blocked; payout threshold.

## Verification/Rollout

* Dry-run program with test partner; verify earnings; process a test payout in Stripe test mode.

---

# PR-097 — AI-Powered Upsell Engine

**Goal**
Personalize upgrade prompts and price tests using behavioral & performance signals.

**Depends on**: PR-052/053 (analytics), PR-060 (messaging), PR-033/034 (checkout), PR-088/089/091 (engagement)

## Scope

* Features: recommend plan/tier, copy-trading upsell (+30%), analytics pro add-on, device slots.
* Inputs: usage (approvals, alerts), success (PnL stability), intent (visited billing), cohort.
* A/B framework for headline/copy/discount variants.
* Channels: Mini App modals, Telegram DMs, email.

## Deliverables

```
backend/app/upsell/models.py          # Recommendation, Variant, Experiment, Exposure
backend/app/upsell/engine.py          # score_user(user_id) -> recs
backend/app/upsell/routes.py          # GET /upsell/recs (JWT), POST /experiments/expose
frontend/miniapp/components/UpsellModal.tsx
frontend/web/lib/ab.ts (extend)       # record exposure/conversion
```

## Env

* `UPSELL_SCORE_THRESHOLD=0.6`
* `AB_DEFAULT_SPLIT=50`

## Security

* Never use private data in prompts; show clear pricing and terms.

## Telemetry

* `upsell_exposures_total{variant}`
* `upsell_conversions_total{variant,plan}`
* `upsell_ctr{variant}` (panel)

## Tests

* Deterministic scoring on fixtures; exposure logged once; conversion fires on successful checkout webhook.

## Verification

* Run A/B with small cohort; compare uplift; guardrails to auto-end poor variants.

---

# PR-098 — Smart CRM & Retention Automations

**Goal**
Lifecycle engine for cancel-rescue, inactivity nudges, winback, and milestone congrats.

**Depends on**: PR-060 (messaging), PR-056 (revenue), PR-059 (prefs), PR-066 (journeys base)

## Scope

* Event triggers: trial started, trial ending, payment failed, churn risk, new high watermark, inactivity 14d.
* Actions: send DM/email/push, one-time discount code, schedule call (owner DM).
* Do-not-disturb/quiet hours respected.

## Deliverables

```
backend/app/crm/triggers.py           # event listeners
backend/app/crm/playbooks.py          # predefined journeys (JSON)
backend/app/crm/routes.py             # GET/PUT playbooks (owner)
email/templates/{rescue,winback}.html
```

## Telemetry

* `crm_playbook_fired_total{name}`
* `crm_rescue_recovered_total`

## Tests

* Simulated failed payment → 3-step rescue; quiet hours enforced.

## Verification

* Run in staging with synthetic events; confirm messages and conversions.

---

# PR-099 — Unified Admin Portal

**Goal**
One secure web portal to operate everything: signals, users, devices, billing, analytics, fraud, support.

**Depends on**: basically everything core (auth, billing, analytics, support, fraud)

## Scope

* React Admin (or custom Next.js) with role-based sections.
* Live tiles: API health, ingestion rate, payment errors, copy-trading status.
* CRUD/search over users/devices; approve KYC; refund (Stripe) with reason.
* Fraud queue (PR-092); Ticketing (PR-063); Education CMS (PR-061).

## Deliverables

```
frontend/web/app/admin/layout.tsx
frontend/web/app/admin/{users,devices,billing,analytics,fraud,support,kb}/page.tsx
backend/app/admin/routes.py           # owner/admin-only endpoints (proxies)
docs/admin/permissions.md
```

## Security

* Owner vs Admin RBAC; every action → Audit Log (PR-008).
* CSRF on POST/PUT from web (double submit cookie).

## Telemetry

* `admin_actions_total{section,action}`

## Tests

* RBAC gating; refund path uses idempotency; audit writes.

## Verification

* Owner walkthrough of all tabs; simulate fraud event and resolve.

---

# PR-100 — Autonomous Health Monitoring (Self-Healing)

**Goal**
Detect and remediate degraded components automatically, and notify owner proactively.

**Depends on**: PR-009 (observability), PR-018 (alerts), PR-019 (heartbeat)

## Scope

* Synthetics: ping WebSocket, MT5 poll, Telegram webhook echo, Stripe webhook replay test.
* Remediations: restart worker, rotate bot token (secondary), drain queue, fall back to read-replica.
* Incident state machine with status page JSON.

## Deliverables

```
backend/app/health/synthetics.py        # run_synthetics()
backend/app/health/remediator.py        # restart_service(), rotate_token(), etc.
backend/app/health/incidents.py         # Incident model + routes
backend/schedulers/health_runner.py
frontend/web/app/status/page.tsx        # public status JSON viewer
```

## Env

* `SYNTHETICS_INTERVAL_SECONDS=60`
* `INCIDENT_AUTO_CLOSE_MINUTES=30`

## Security

* Remediation actions are owner-signed (API key with scope); audit every action.

## Telemetry

* `synthetics_fail_total{probe}`
* `incidents_open_gauge`, `remediations_total{type}`

## Tests

* Force Telegram webhook fail → synthetic red; remediator rotates to backup; incident resolves.

## Verification

* Staging chaos test (kill service) → see auto-recovery + owner DM.

---

# PR-101 — AI-Generated Reports (Owner & Client)

**Goal**
Daily/weekly/monthly **narrative reports** combining analytics with human-readable summaries sent via Telegram/email and stored as PDFs.

**Depends on**: PR-052/053/055 (analytics), PR-060 (messaging), PR-099 (admin access)

## Scope

* Report types: Client account summary; Owner business summary (MRR, churn, performance highlights, incidents).
* Generation pipeline → HTML → PDF; links stored (S3/local).
* Multi-channel delivery; opt-in per user (PR-059).

## Deliverables

```
backend/app/reports/templates/
  client.html.j2
  owner.html.j2
backend/app/reports/generator.py        # build_report(period, user|owner)
backend/schedulers/reports_runner.py
frontend/web/app/reports/page.tsx       # history viewer (owner & user)
```

## Env

* `REPORTS_TIME_UTC=06:00`
* `REPORTS_STORAGE_BUCKET=...`

## Security

* Reports scoped to user; signed URLs; retention policy.

## Telemetry

* `reports_generated_total{type,period}`, `reports_sent_total{channel}`

## Tests

* Edge cases: zero trades week; negative weeks; PDF builds.

## Verification

* Generate on demand in Admin; confirm HTML/PDF + delivery.

---

# PR-102 — “Client Copy Mirror” NFT Access (Build, Don’t Release Yet)

**Goal**
Prototype tokenized access to mirrored strategies (licensing), **behind a feature flag**. Not for production release yet.

**Depends on**: PR-045/046 (copy-trading), PR-093 (ledger) — optional

## Scope

* Minting service that issues a non-transferable (or time-locked) token/NFT that maps to an entitlement (e.g., `copy.mirror`).
* Ownership check middleware: wallet signature ↔ user account mapping.
* Admin tool to revoke/expire tokens; event log.

## Deliverables

```
backend/app/web3/nft_access.py          # mint(), revoke(), check_access(address)
backend/app/web3/wallet_link.py         # link wallet to user (SIWE or simple sig)
backend/app/web3/routes.py              # POST /web3/link, GET /web3/access
backend/app/billing/entitlements.py     # add "copy.mirror" feature flag
frontend/web/app/web3/page.tsx          # wallet link UI (hidden route)
docs/feature_flags/nft_access.md
```

## Env/Feature Flag

* `NFT_ACCESS_ENABLED=false`
* `WEB3_CHAIN_ID`, `WEB3_RPC_URL`, `NFT_CONTRACT_ADDRESS` (staging only)

## Security

* Never gate critical features only by NFT; this is additive.
* Strict allowlist of wallets in staging; no public mint UI.
* Audit every mint/revoke to Audit Log (PR-008).

## Telemetry

* `nft_access_checks_total{result}`
* `nft_mints_total`, `nft_revokes_total`

## Tests

* Wallet link/sign verification; access check; revoke removes access.

## Verification/Rollout

* Internal staging wallet → mint entitlement → confirm gated endpoint allows; keep **feature flag OFF** in production.

---
