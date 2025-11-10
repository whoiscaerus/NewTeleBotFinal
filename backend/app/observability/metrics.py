"""OpenTelemetry metrics collection."""

import logging

try:
    from prometheus_client import (
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )
except ImportError as e:
    raise ImportError(
        "prometheus-client not installed. Install with: pip install prometheus-client"
    ) from e

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects and exposes Prometheus metrics."""

    def __init__(self):
        """Initialize metrics collector."""
        self.registry = CollectorRegistry()

        # HTTP metrics
        self.http_requests_total = Counter(
            "http_requests_total",
            "Total HTTP requests",
            ["route", "method", "status"],
            registry=self.registry,
        )

        self.request_duration_seconds = Histogram(
            "request_duration_seconds",
            "HTTP request duration in seconds",
            ["route", "method"],
            buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 5.0),
            registry=self.registry,
        )

        # Authentication metrics
        self.auth_login_total = Counter(
            "auth_login_total",
            "Total login attempts",
            ["result"],  # success, failure
            registry=self.registry,
        )

        self.auth_register_total = Counter(
            "auth_register_total",
            "Total user registrations",
            ["result"],  # success, failure
            registry=self.registry,
        )

        # Rate limiting metrics
        self.ratelimit_block_total = Counter(
            "ratelimit_block_total",
            "Total rate limit rejections",
            ["route"],
            registry=self.registry,
        )

        # Error metrics
        self.errors_total = Counter(
            "errors_total",
            "Total errors",
            ["status", "endpoint"],
            registry=self.registry,
        )

        # Database metrics (placeholder for later)
        self.db_connection_pool_size = Gauge(
            "db_connection_pool_size",
            "Database connection pool size",
            registry=self.registry,
        )

        self.db_query_duration_seconds = Histogram(
            "db_query_duration_seconds",
            "Database query duration",
            ["query_type"],
            buckets=(0.01, 0.05, 0.1, 0.5, 1.0),
            registry=self.registry,
        )

        # Redis metrics
        self.redis_connected = Gauge(
            "redis_connected",
            "Redis connection status (1=connected, 0=disconnected)",
            registry=self.registry,
        )

        # Messaging metrics (PR-060)
        self.messages_enqueued_total = Counter(
            "messages_enqueued_total",
            "Total messages enqueued",
            ["priority", "channel"],  # transactional/campaign, email/telegram/push
            registry=self.registry,
        )

        self.messages_sent_total = Counter(
            "messages_sent_total",
            "Total messages sent successfully",
            ["channel", "type"],  # email/telegram/push, alert/campaign/etc
            registry=self.registry,
        )

        self.message_fail_total = Counter(
            "message_fail_total",
            "Total message send failures",
            ["reason", "channel"],  # timeout/bounce/rate_limit, email/telegram/push
            registry=self.registry,
        )

        self.message_send_duration_seconds = Histogram(
            "message_send_duration_seconds",
            "Message send duration",
            ["channel"],
            buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 5.0),
            registry=self.registry,
        )

        self.position_failure_alerts_sent_total = Counter(
            "position_failure_alerts_sent_total",
            "Total position failure alerts sent (PR-104 integration)",
            ["type", "channel"],  # entry/sl/tp, email/telegram/push
            registry=self.registry,
        )

        # CRM metrics (PR-098)
        self.crm_playbook_fired_total = Counter(
            "crm_playbook_fired_total",
            "Total CRM playbooks started (PR-098: lifecycle automations)",
            [
                "name"
            ],  # payment_failed_rescue, trial_ending, inactivity_nudge, winback, milestone_congrats, churn_risk
            registry=self.registry,
        )

        self.crm_rescue_recovered_total = Counter(
            "crm_rescue_recovered_total",
            "Total payment rescues successful (PR-098: payment_failed_rescue conversions)",
            registry=self.registry,
        )

        # Business metrics (placeholders for trading domains)
        self.signals_ingested_total = Counter(
            "signals_ingested_total",
            "Total trading signals ingested",
            ["source"],
            registry=self.registry,
        )

        self.approvals_total = Counter(
            "approvals_total",
            "Total signal approvals",
            ["result"],  # approved, rejected
            registry=self.registry,
        )

        # Decision log metrics (PR-073)
        self.decision_logs_total = Counter(
            "decision_logs_total",
            "Total trade decisions logged",
            ["strategy"],
            registry=self.registry,
        )

        # Strategy versioning & shadow mode metrics (PR-078)
        self.shadow_decisions_total = Counter(
            "shadow_decisions_total",
            "Total shadow mode decisions generated (PR-078: no execution, log-only)",
            [
                "version",
                "strategy",
                "symbol",
                "decision",
            ],  # v2.0.0, fib_rsi, GOLD, buy/sell/hold
            registry=self.registry,
        )

        self.canary_traffic_percent = Gauge(
            "canary_traffic_percent",
            "Current canary rollout percentage (PR-078: gradual version rollout)",
            ["strategy", "version"],  # fib_rsi, v2.0.0
            registry=self.registry,
        )

        self.version_activations_total = Counter(
            "version_activations_total",
            "Total strategy version activations (PR-078: shadow → canary → active transitions)",
            ["strategy", "version"],  # fib_rsi, v2.0.0
            registry=self.registry,
        )

        # Explainability metrics (PR-080)
        self.explain_requests_total = Counter(
            "explain_requests_total",
            "Total explainability requests (PR-080: attribution, feature importance)",
            registry=self.registry,
        )

        self.decision_search_total = Counter(
            "decision_search_total",
            "Total decision search requests (PR-080: filter, paginate)",
            registry=self.registry,
        )

        # Paper trading metrics (PR-081)
        self.paper_fills_total = Counter(
            "paper_fills_total",
            "Total paper trading fills (PR-081: sandbox orders)",
            ["symbol", "side"],
            registry=self.registry,
        )

        self.paper_pnl_total = Gauge(
            "paper_pnl_total",
            "Total paper trading PnL across all users (PR-081)",
            registry=self.registry,
        )

        # Quota metrics (PR-082)
        self.quota_block_total = Counter(
            "quota_block_total",
            "Total quota limit blocks (PR-082: resource protection)",
            ["key"],  # signals_per_day, alerts_per_day, exports_per_month, etc.
            registry=self.registry,
        )

        # Gateway migration metrics (PR-083)
        self.legacy_calls_total = Counter(
            "legacy_calls_total",
            "Total calls to legacy Flask routes (PR-083: should trend to zero)",
            ["route"],  # /api/price, /api/trades, /api/positions, etc.
            registry=self.registry,
        )

        # Web platform telemetry metrics (PR-084)
        self.web_page_view_total = Counter(
            "web_page_view_total",
            "Total web page views",
            ["route"],  # /, /pricing, /legal/terms, etc.
            registry=self.registry,
        )

        self.web_cwv_lcp_seconds = Histogram(
            "web_cwv_lcp_seconds",
            "Largest Contentful Paint (seconds)",
            buckets=(0.5, 1.0, 2.5, 4.0, 5.0, 10.0),
            registry=self.registry,
        )

        self.web_cwv_fid_seconds = Histogram(
            "web_cwv_fid_seconds",
            "First Input Delay (seconds)",
            buckets=(0.01, 0.05, 0.1, 0.3, 0.5),
            registry=self.registry,
        )

        self.web_cwv_cls_score = Histogram(
            "web_cwv_cls_score",
            "Cumulative Layout Shift (score)",
            buckets=(0.1, 0.25, 0.5, 1.0),
            registry=self.registry,
        )

        self.web_cwv_ttfb_seconds = Histogram(
            "web_cwv_ttfb_seconds",
            "Time to First Byte (seconds)",
            buckets=(0.1, 0.2, 0.5, 1.0, 2.0),
            registry=self.registry,
        )

        self.web_cwv_tti_seconds = Histogram(
            "web_cwv_tti_seconds",
            "Time to Interactive (seconds)",
            buckets=(0.5, 1.0, 2.5, 5.0, 10.0),
            registry=self.registry,
        )

        # A/B Testing metrics (PR-086)
        self.ab_variant_view_total = Counter(
            "ab_variant_view_total",
            "Total A/B test variant views",
            ["experiment", "variant"],  # hero_copy, benefit_focused
            registry=self.registry,
        )

        self.ab_conversion_total = Counter(
            "ab_conversion_total",
            "Total A/B test conversions",
            ["experiment", "variant", "event"],  # hero_copy, benefit_focused, signup
            registry=self.registry,
        )

        # Dashboard WebSocket metrics (PR-087)
        self.dashboard_ws_clients_gauge = Gauge(
            "dashboard_ws_clients",
            "Number of active dashboard WebSocket connections",
            registry=self.registry,
        )

        self.dashboard_card_click_total = Counter(
            "dashboard_card_click_total",
            "Total dashboard card clicks",
            ["name"],  # approvals, positions, equity, signals, etc.
            registry=self.registry,
        )

        # Gamification metrics (PR-088)
        self.badges_awarded_total = Counter(
            "badges_awarded_total",
            "Total badges awarded to users",
            ["name"],  # first_trade, getting_started, trader, veteran, etc.
            registry=self.registry,
        )

        self.leaderboard_optin_total = Counter(
            "leaderboard_optin_total",
            "Total leaderboard opt-ins",
            registry=self.registry,
        )

        # Education metrics (PR-089)
        self.education_lessons_completed_total = Counter(
            "education_lessons_completed_total",
            "Total lessons completed by users",
            ["course_id", "lesson_id"],  # Track which courses/lessons are popular
            registry=self.registry,
        )

        self.education_quiz_pass_total = Counter(
            "education_quiz_pass_total",
            "Total quiz attempts that passed",
            ["quiz_id", "course_id"],  # Track quiz difficulty and engagement
            registry=self.registry,
        )

        self.education_quiz_fail_total = Counter(
            "education_quiz_fail_total",
            "Total quiz attempts that failed",
            ["quiz_id", "course_id"],  # Track which quizzes need improvement
            registry=self.registry,
        )

        self.education_rewards_issued_total = Counter(
            "education_rewards_issued_total",
            "Total rewards issued for course completion",
            ["course_id", "reward_type"],  # discount, credit
            registry=self.registry,
        )

        # Theme metrics (PR-090)
        self.theme_selected_total = Counter(
            "theme_selected_total",
            "Total theme selections by users",
            ["name"],  # professional, darkTrader, goldMinimal
            registry=self.registry,
        )

        # AI Analyst metrics (PR-091)
        self.ai_outlook_published_total = Counter(
            "ai_outlook_published_total",
            "Total AI market outlooks published",
            ["channel"],  # email, telegram
            registry=self.registry,
        )

        # Fraud detection metrics (PR-092)
        self.fraud_events_total = Counter(
            "fraud_events_total",
            "Total fraud detection anomalies flagged",
            ["type"],  # slippage_extreme, latency_spike, out_of_band_fill, etc.
            registry=self.registry,
        )

        # Ledger metrics (PR-093)
        self.ledger_submissions_total = Counter(
            "ledger_submissions_total",
            "Total successful blockchain submissions",
            ["chain"],  # polygon, arbitrum
            registry=self.registry,
        )

        self.ledger_fail_total = Counter(
            "ledger_fail_total",
            "Total failed blockchain submissions after retries",
            ["chain"],  # polygon, arbitrum
            registry=self.registry,
        )

        # Social verification metrics (PR-094)
        self.social_verifications_total = Counter(
            "social_verifications_total",
            "Total verification edges created in social graph",
            ["status"],  # success, self_verification, duplicate, rate_limit, anti_sybil
            registry=self.registry,
        )

        self.social_influence_score_gauge = Gauge(
            "social_influence_score_gauge",
            "User influence scores from social verification graph",
            ["user_id"],
            registry=self.registry,
        )

        # Public trust index metrics (PR-095)
        self.public_trust_index_views_total = Counter(
            "public_trust_index_views_total",
            "Total public trust index API views",
            ["trust_band"],  # unverified, verified, expert, elite
            registry=self.registry,
        )

        self.public_trust_index_calculated_total = Counter(
            "public_trust_index_calculated_total",
            "Total trust index calculations (includes social graph integration)",
            ["trust_band"],
            registry=self.registry,
        )

        # Feature quality metrics (PR-079)
        self.feature_quality_fail_total = Counter(
            "feature_quality_fail_total",
            "Total feature quality check failures (PR-079: staleness, NaNs, drift)",
            [
                "type"
            ],  # missing_features, nan_values, stale_data, drift_detected, low_quality_score
            registry=self.registry,
        )

        # Risk management metrics (PR-074)
        self.risk_block_total = Counter(
            "risk_block_total",
            "Total trades blocked by risk guards",
            [
                "reason"
            ],  # max_drawdown_exceeded, min_equity_breach, max_position_size_exceeded, etc.
            registry=self.registry,
        )

        # Trading control metrics (PR-075)
        self.trading_paused_total = Counter(
            "trading_paused_total",
            "Total trading pause actions",
            ["actor"],  # user, admin, system
            registry=self.registry,
        )

        self.trading_resumed_total = Counter(
            "trading_resumed_total",
            "Total trading resume actions",
            ["actor"],  # user, admin
            registry=self.registry,
        )

        self.trading_size_changed_total = Counter(
            "trading_size_changed_total",
            "Total position size override changes",
            registry=self.registry,
        )

        # Audit metrics
        self.audit_events_total = Counter(
            "audit_events_total",
            "Total audit events recorded",
            ["action", "status"],
            registry=self.registry,
        )

        # Media/charting metrics
        self.media_render_total = Counter(
            "media_render_total",
            "Total media renders",
            ["type"],
            registry=self.registry,
        )

        self.media_cache_hits_total = Counter(
            "media_cache_hits_total",
            "Media cache hits",
            ["type"],
            registry=self.registry,
        )

        # Marketing metrics
        self.marketing_posts_total = Counter(
            "marketing_posts_total",
            "Total marketing promos posted to Telegram groups",
            registry=self.registry,
        )

        self.marketing_clicks_total = Counter(
            "marketing_clicks_total",
            "Total marketing CTA clicks",
            ["promo_id"],
            registry=self.registry,
        )

        # Billing metrics (PR-033)
        self.billing_checkout_started_total = Counter(
            "billing_checkout_started_total",
            "Total Stripe checkout sessions initiated",
            ["plan"],
            registry=self.registry,
        )

        self.billing_payments_total = Counter(
            "billing_payments_total",
            "Total payments processed (webhook events)",
            ["status"],
            registry=self.registry,
        )

        self.signals_create_seconds = Histogram(
            "signals_create_seconds",
            "Signal creation duration in seconds",
            buckets=(0.01, 0.05, 0.1, 0.5, 1.0),
            registry=self.registry,
        )

        # Mini App billing metrics
        self.miniapp_checkout_start_total = Counter(
            "miniapp_checkout_start_total",
            "Total mini app checkout initiations",
            ["plan"],  # free, premium, vip, enterprise
            registry=self.registry,
        )

        self.miniapp_portal_open_total = Counter(
            "miniapp_portal_open_total",
            "Total mini app portal opens",
            registry=self.registry,
        )

        # PR-040: Payment Security Hardening metrics
        self.billing_webhook_replay_block_total = Counter(
            "billing_webhook_replay_block_total",
            "Total webhook replay attacks blocked",
            registry=self.registry,
        )

        self.idempotent_hits_total = Counter(
            "idempotent_hits_total",
            "Total idempotent cache hits (duplicate requests)",
            ["operation"],  # checkout, invoice_payment, subscription_deleted, etc.
            registry=self.registry,
        )

        self.billing_webhook_invalid_sig_total = Counter(
            "billing_webhook_invalid_sig_total",
            "Total webhooks rejected for invalid signature",
            registry=self.registry,
        )

        # PR-041: MT5 EA SDK & Reference EA metrics
        self.ea_requests_total = Counter(
            "ea_requests_total",
            "Total EA API requests (poll, ack)",
            ["endpoint"],  # /poll, /ack
            registry=self.registry,
        )

        self.ea_errors_total = Counter(
            "ea_errors_total",
            "Total EA request errors",
            [
                "endpoint",
                "error_type",
            ],  # endpoint: /poll, /ack; error_type: auth_failed, invalid_signature, timeout, malformed_request, etc.
            registry=self.registry,
        )

        self.ea_poll_duration_seconds = Histogram(
            "ea_poll_duration_seconds",
            "EA poll request duration in seconds",
            buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 5.0),
            registry=self.registry,
        )

        self.ea_ack_duration_seconds = Histogram(
            "ea_ack_duration_seconds",
            "EA ack request duration in seconds",
            buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 5.0),
            registry=self.registry,
        )

        # PR-030: Content distribution metrics
        self.distribution_messages_total = Counter(
            "distribution_messages_total",
            "Total messages distributed to Telegram groups",
            ["channel"],
            registry=self.registry,
        )

        # PR-031: GuideBot metrics
        self.guides_posts_total = Counter(
            "guides_posts_total",
            "Total guide/tutorial posts sent to Telegram groups",
            registry=self.registry,
        )

        # PR-034: Telegram Native Payments metrics
        self.telegram_payments_total = Counter(
            "telegram_payments_total",
            "Total Telegram Stars payments processed",
            ["result"],  # success, failed, cancelled
            registry=self.registry,
        )

        self.telegram_payment_value_total = Counter(
            "telegram_payment_value_total",
            "Total Telegram Stars payment values (sum in smallest unit)",
            ["currency"],  # XTR (Telegram Stars), USD, etc.
            registry=self.registry,
        )

        # PR-035: Telegram Mini App metrics
        self.miniapp_sessions_total = Counter(
            "miniapp_sessions_total",
            "Total Telegram Mini App sessions created via initData exchange",
            registry=self.registry,
        )

        self.miniapp_exchange_latency_seconds = Histogram(
            "miniapp_exchange_latency_seconds",
            "Telegram Mini App initData exchange latency in seconds",
            buckets=(0.01, 0.05, 0.1, 0.5, 1.0),
            registry=self.registry,
        )

        # Mini App Approvals metrics (PR-27)
        self.miniapp_approvals_viewed_total = Counter(
            "miniapp_approvals_viewed_total",
            "Total times approvals console was viewed",
            registry=self.registry,
        )

        self.miniapp_approval_actions_total = Counter(
            "miniapp_approval_actions_total",
            "Total approval actions (approve/reject) from mini app",
            ["decision"],  # approve, reject
            registry=self.registry,
        )

        self.miniapp_approval_latency_seconds = Histogram(
            "miniapp_approval_latency_seconds",
            "Approval action latency from click to backend response",
            buckets=(0.01, 0.05, 0.1, 0.5, 1.0),
            registry=self.registry,
        )

        # PR-070: Telegram Bot Localization metrics
        self.telegram_locale_used_total = Counter(
            "telegram_locale_used_total",
            "Total times a locale was used in Telegram bot",
            ["locale"],  # en, es
            registry=self.registry,
        )

        self.distribution_localized_total = Counter(
            "distribution_localized_total",
            "Total content distributions with localization",
            ["locale"],  # en, es
            registry=self.registry,
        )

        self.position_failure_telegram_sent_total = Counter(
            "position_failure_telegram_sent_total",
            "Total position failure notifications sent via Telegram",
            [
                "locale",
                "type",
            ],  # locale: en, es; type: entry_failure, exit_sl_hit, exit_tp_hit
            registry=self.registry,
        )

        # Device registry metrics (PR-039)
        self.miniapp_device_register_total = Counter(
            "miniapp_device_register_total",
            "Total device registrations",
            registry=self.registry,
        )

        self.miniapp_device_revoke_total = Counter(
            "miniapp_device_revoke_total",
            "Total device revocations",
            registry=self.registry,
        )

        # PR-071: Strategy Engine Integration metrics
        self.strategy_runs_total = Counter(
            "strategy_runs_total",
            "Total strategy execution runs",
            ["name"],  # fib_rsi, ppo_gold, etc.
            registry=self.registry,
        )

        self.strategy_emit_total = Counter(
            "strategy_emit_total",
            "Total signals emitted by strategies",
            ["name"],  # fib_rsi, ppo_gold, etc.
            registry=self.registry,
        )

        # PR-072: Signal Generation & Distribution metrics
        self.signal_publish_total = Counter(
            "signal_publish_total",
            "Total signals published",
            ["route"],  # api, telegram
            registry=self.registry,
        )

        logger.info("Metrics collector initialized")

    def record_http_request(
        self,
        route: str,
        method: str,
        status_code: int,
        duration_seconds: float,
    ):
        """Record HTTP request metrics.

        Args:
            route: API route (e.g., '/api/v1/auth/login')
            method: HTTP method (GET, POST, etc.)
            status_code: HTTP response status code
            duration_seconds: Request duration in seconds
        """
        self.http_requests_total.labels(
            route=route, method=method, status=status_code
        ).inc()
        self.request_duration_seconds.labels(route=route, method=method).observe(
            duration_seconds
        )

    def record_login_attempt(self, success: bool):
        """Record login attempt.

        Args:
            success: Whether login succeeded
        """
        result = "success" if success else "failure"
        self.auth_login_total.labels(result=result).inc()

    def record_registration(self, success: bool):
        """Record user registration.

        Args:
            success: Whether registration succeeded
        """
        result = "success" if success else "failure"
        self.auth_register_total.labels(result=result).inc()

    def record_rate_limit_rejection(self, route: str):
        """Record rate limit rejection.

        Args:
            route: API route that was rate limited
        """
        self.ratelimit_block_total.labels(route=route).inc()

    def record_error(self, status_code: int, endpoint: str):
        """Record error.

        Args:
            status_code: HTTP status code
            endpoint: API endpoint
        """
        self.errors_total.labels(status=status_code, endpoint=endpoint).inc()

    def record_audit_event(self, action: str, status: str):
        """Record audit event.

        Args:
            action: Audit action (e.g., 'auth.login')
            status: Status (success, failure, error)
        """
        self.audit_events_total.labels(action=action, status=status).inc()

    def set_db_connection_pool_size(self, size: int):
        """Set database connection pool size.

        Args:
            size: Number of connections in pool
        """
        self.db_connection_pool_size.set(size)

    def record_db_query(self, query_type: str, duration_seconds: float):
        """Record database query.

        Args:
            query_type: Type of query (select, insert, update, etc.)
            duration_seconds: Query duration
        """
        self.db_query_duration_seconds.labels(query_type=query_type).observe(
            duration_seconds
        )

    def record_miniapp_checkout_start(self, plan: str):
        """Record mini app checkout initiated.

        Args:
            plan: Plan type (free, premium, vip, enterprise)
        """
        self.miniapp_checkout_start_total.labels(plan=plan).inc()

    def record_miniapp_portal_open(self):
        """Record mini app billing portal opened."""
        self.miniapp_portal_open_total.inc()

    def record_billing_webhook_replay_block(self):
        """Record webhook replay attack blocked (PR-040)."""
        self.billing_webhook_replay_block_total.inc()

    def record_idempotent_hit(self, operation: str):
        """Record idempotent cache hit (duplicate request).

        Args:
            operation: Operation name (checkout, invoice_payment, subscription_deleted, etc.)
        """
        self.idempotent_hits_total.labels(operation=operation).inc()

    def record_billing_webhook_invalid_sig(self):
        """Record webhook rejected for invalid signature (PR-040)."""
        self.billing_webhook_invalid_sig_total.inc()

    def record_ea_request(self, endpoint: str):
        """Record EA API request (PR-041).

        Args:
            endpoint: API endpoint ('/poll' or '/ack')
        """
        self.ea_requests_total.labels(endpoint=endpoint).inc()

    def record_ea_error(self, endpoint: str, error_type: str):
        """Record EA API request error (PR-041).

        Args:
            endpoint: API endpoint ('/poll' or '/ack')
            error_type: Error type (auth_failed, invalid_signature, timeout, malformed_request, not_found, etc.)
        """
        self.ea_errors_total.labels(endpoint=endpoint, error_type=error_type).inc()

    def record_ea_poll_duration(self, duration_seconds: float):
        """Record EA poll request duration (PR-041).

        Args:
            duration_seconds: Request duration in seconds
        """
        self.ea_poll_duration_seconds.observe(duration_seconds)

    def record_ea_ack_duration(self, duration_seconds: float):
        """Record EA ack request duration (PR-041).

        Args:
            duration_seconds: Request duration in seconds
        """
        self.ea_ack_duration_seconds.observe(duration_seconds)

    def record_distribution_message(self, channel: str):
        """Record message distribution to Telegram channel/keyword (PR-030).

        Args:
            channel: Distribution channel/keyword (e.g., "gold", "crypto")
        """
        self.distribution_messages_total.labels(channel=channel).inc()

    def record_marketing_post(self):
        """Record marketing promo posted (PR-032)."""
        self.marketing_posts_total.inc()

    def record_billing_checkout_started(self, plan: str):
        """Record Stripe checkout session initiated (PR-033).

        Args:
            plan: Plan code (free, basic, premium, pro)
        """
        self.billing_checkout_started_total.labels(plan=plan).inc()

    def record_billing_payment(self, status: str):
        """Record payment processed via webhook (PR-033).

        Args:
            status: Payment status (success, failed, refunded)
        """
        self.billing_payments_total.labels(status=status).inc()

    def record_telegram_payment(
        self, result: str, amount: int = 0, currency: str = "XTR"
    ):
        """Record Telegram Stars payment processed (PR-034).

        Args:
            result: Payment result (success, failed, cancelled)
            amount: Payment amount (in smallest unit, e.g., kopeks for XTR)
            currency: Payment currency (XTR for Telegram Stars, etc.)
        """
        self.telegram_payments_total.labels(result=result).inc()
        if amount > 0:
            self.telegram_payment_value_total.labels(currency=currency).inc(amount)

    def record_telegram_invoice_created(
        self, product_id: str, tier_level: int, amount_gbp: float
    ):
        """Record Telegram invoice creation (PR-034).

        Args:
            product_id: Product being purchased
            tier_level: Product tier level
            amount_gbp: Amount in GBP
        """
        # Log invoice creation
        pass

    def record_telegram_pre_checkout(
        self, product_id: str, tier_level: int, amount_gbp: float, result: str
    ):
        """Record Telegram pre-checkout validation (PR-034).

        Args:
            product_id: Product being purchased
            tier_level: Product tier level
            amount_gbp: Amount in GBP
            result: Validation result (passed, failed)
        """
        # Log pre-checkout validation
        pass

    def record_telegram_payment_by_product(
        self, product_id: str, tier_level: int, amount_cents: int
    ):
        """Record Telegram payment by product (PR-034).

        Args:
            product_id: Product purchased
            tier_level: Product tier level
            amount_cents: Amount in cents
        """
        # Log payment by product
        pass

    def record_telegram_shop_view(self, user_id: str):
        """Record shop view event (PR-034).

        Args:
            user_id: User viewing shop
        """
        # Log shop view
        pass

    def record_telegram_buy_initiated(self, product_id: str, tier_level: int):
        """Record buy command initiated (PR-034).

        Args:
            product_id: Product being purchased
            tier_level: Product tier level
        """
        # Log buy command
        pass

    def record_telegram_payment_initiated(
        self, payment_method: str, product_id: str, tier_level: int
    ):
        """Record payment initiation (PR-034).

        Args:
            payment_method: Payment method (stripe, stars, etc.)
            product_id: Product being purchased
            tier_level: Product tier level
        """
        # Log payment initiation
        pass

    def record_miniapp_session_created(self):
        """Record Mini App session created via initData exchange (PR-035)."""
        self.miniapp_sessions_total.inc()

    def record_miniapp_exchange_latency(self, latency_seconds: float):
        """Record Mini App initData exchange latency (PR-035).

        Args:
            latency_seconds: Exchange duration in seconds
        """
        self.miniapp_exchange_latency_seconds.observe(latency_seconds)

    def record_miniapp_device_register(self):
        """Record device registration (PR-039).

        Increments counter on successful device registration.
        """
        self.miniapp_device_register_total.inc()

    def record_miniapp_device_revoke(self):
        """Record device revocation (PR-039).

        Increments counter on successful device revocation.
        """
        self.miniapp_device_revoke_total.inc()

    def set_redis_connected(self, connected: bool):
        """Set Redis connection status.

        Args:
            connected: True if connected, False otherwise
        """
        self.redis_connected.set(1 if connected else 0)

    def get_metrics(self) -> bytes:
        """Get metrics in Prometheus format.

        Returns:
            bytes: Prometheus-formatted metrics
        """
        return generate_latest(self.registry)


# Singleton instance
metrics = MetricsCollector()

# Global metrics instance
_metrics: MetricsCollector | None = None


def get_metrics() -> MetricsCollector:
    """Get or initialize global metrics collector.

    Returns:
        MetricsCollector: Global instance
    """
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics


# Export messaging metrics for convenient access (PR-060)
messages_enqueued_total = metrics.messages_enqueued_total
messages_sent_total = metrics.messages_sent_total
message_fail_total = metrics.message_fail_total
message_send_duration_seconds = metrics.message_send_duration_seconds
position_failure_alerts_sent_total = metrics.position_failure_alerts_sent_total

# Export CRM metrics for convenient access (PR-098)
crm_playbook_fired_total = metrics.crm_playbook_fired_total
crm_rescue_recovered_total = metrics.crm_rescue_recovered_total
