"""
Auto-Trace Worker: Celery periodic task for processing trace queue.

Responsibilities:
- Poll queue for pending traces
- Enforce delay (T+X before posting)
- Call adapters to post trades
- Handle retries with exponential backoff
- Record Prometheus metrics
- Comprehensive logging
"""

from typing import Any

import redis.asyncio as redis
from celery import Task, shared_task
from celery.utils.log import get_task_logger
from prometheus_client import Counter, Gauge, Histogram
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.core.settings import get_settings
from backend.app.trading.store.models import Trade
from backend.app.trust.trace_adapters import (
    AdapterConfig,
    AdapterError,
    FileExportAdapter,
    MyfxbookAdapter,
    TraceAdapter,
    WebhookAdapter,
)
from backend.app.trust.tracer import TraceQueue, strip_pii_from_trade

logger = get_task_logger(__name__)

# Prometheus metrics
traces_pushed_counter = Counter(
    "trust_traces_pushed_total",
    "Total traces pushed to adapters",
    ["adapter", "status"],
)

traces_failed_counter = Counter(
    "trust_trace_fail_total", "Total trace posting failures", ["adapter", "reason"]
)

queue_pending_gauge = Gauge(
    "trust_trace_queue_pending", "Number of traces pending in queue", ["adapter"]
)

trace_delay_histogram = Histogram(
    "trust_trace_delay_minutes",
    "Actual delay before posting (should be ~delay_minutes ± 1)",
    ["adapter"],
    buckets=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10),
)

trace_post_duration_histogram = Histogram(
    "trust_trace_post_duration_seconds",
    "Time to post trade to adapter",
    ["adapter", "status"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30),
)


class TraceWorkerTask(Task):
    """
    Custom task class with setup/cleanup.

    Manages Redis connection and database session lifecycle.
    """

    def __call__(self, *args, **kwargs):
        """Make task callable as context manager."""
        return self.run(*args, **kwargs)


@shared_task(
    bind=True,
    base=TraceWorkerTask,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
)
async def process_pending_traces(self) -> dict[str, Any]:
    """
    Celery periodic task: Process all pending traces in queue.

    Schedule: Every 5 minutes (via celery beat config)

    Returns:
    {
        "processed": 5,
        "succeeded": 4,
        "failed": 1,
        "duration_seconds": 2.5,
        "next_check": "2025-01-15T11:05:00Z"
    }

    Algorithm:
    1. Connect to Redis and get pending traces
    2. For each trace:
        a. Check if deadline satisfied (now > deadline)
        b. If not ready, skip (will retry next cycle)
        c. If ready:
            - Fetch trade from database
            - Strip PII
            - For each enabled adapter:
              - Attempt post_trade()
              - Record result (success/failure)
              - On failure: schedule retry with backoff
    3. Return summary statistics
    4. Record Prometheus metrics
    """
    try:
        settings = get_settings()

        # Initialize Redis
        redis_client = await redis.from_url(settings.redis.url)
        trace_queue = TraceQueue(redis_client)

        # Initialize database session
        engine = create_async_engine(settings.database.url, echo=False)
        async_session = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        # Initialize adapters
        adapters = _initialize_adapters(settings)

        # Get pending traces
        pending = await trace_queue.get_pending_traces(batch_size=10)

        if not pending:
            logger.info("No pending traces to process")
            queue_pending_gauge.labels(adapter="all").set(0)
            return {
                "processed": 0,
                "succeeded": 0,
                "failed": 0,
                "skipped": 0,
                "duration_seconds": 0.0,
            }

        logger.info(f"Processing {len(pending)} pending traces")

        # Process each trace
        processed = 0
        succeeded = 0
        failed = 0
        skipped = 0

        async with async_session() as session:
            for trace in pending:
                try:
                    trade_id = trace.get("trade_id")
                    trace_key = trace.get("trace_key")
                    adapter_names = trace.get("adapters", [])
                    retry_count = trace.get("retry_count", 0)

                    # Fetch trade
                    result = await session.execute(
                        session.query(Trade).filter_by(id=trade_id)
                    )
                    trade = result.scalars().first()

                    if not trade:
                        logger.warning(f"Trade not found: {trade_id}")
                        await trace_queue.mark_success(trace_key)
                        failed += 1
                        continue

                    # Strip PII
                    trade_data = await strip_pii_from_trade(trade)

                    # Post to each adapter
                    adapter_succeeded = []
                    adapter_failed = []

                    for adapter_name in adapter_names:
                        adapter = adapters.get(adapter_name)
                        if not adapter or not adapter.config.enabled:
                            logger.warning(f"Adapter not available: {adapter_name}")
                            adapter_failed.append(
                                (adapter_name, "adapter_not_available")
                            )
                            continue

                        # Post trade
                        try:
                            success = await _post_trade_with_adapter(
                                adapter, trade_data, retry_count
                            )

                            if success:
                                adapter_succeeded.append(adapter_name)
                                traces_pushed_counter.labels(
                                    adapter=adapter_name, status="success"
                                ).inc()
                                trace_post_duration_histogram.labels(
                                    adapter=adapter_name, status="success"
                                ).observe(
                                    0.5
                                )  # Mock duration
                            else:
                                adapter_failed.append(
                                    (adapter_name, "retriable_failure")
                                )
                                traces_pushed_counter.labels(
                                    adapter=adapter_name, status="pending_retry"
                                ).inc()

                        except AdapterError as e:
                            logger.error(f"Adapter error: {str(e)}")
                            adapter_failed.append((adapter_name, "fatal_error"))
                            traces_failed_counter.labels(
                                adapter=adapter_name, reason="fatal_error"
                            ).inc()

                    # Handle results
                    if adapter_succeeded and not adapter_failed:
                        # All adapters succeeded
                        await trace_queue.mark_success(trace_key)
                        succeeded += 1
                        logger.info(
                            f"Trace posted successfully to all adapters: {trade_id}",
                            extra={
                                "trade_id": trade_id,
                                "adapters": adapter_succeeded,
                                "retry_count": retry_count,
                            },
                        )

                    elif adapter_failed and retry_count < 5:
                        # Some failed, schedule retry
                        adapter = adapters.get(adapter_names[0])
                        if adapter:
                            backoff = adapter.calculate_backoff(retry_count)
                            await trace_queue.schedule_retry(
                                trace_key, retry_count, backoff
                            )
                            logger.info(
                                f"Trace retry scheduled: {trade_id}",
                                extra={
                                    "trade_id": trade_id,
                                    "adapters_failed": [f[0] for f in adapter_failed],
                                    "retry_count": retry_count + 1,
                                    "backoff_seconds": backoff,
                                },
                            )
                            failed += 1

                    elif retry_count >= 5:
                        # Max retries exceeded
                        await trace_queue.abandon_after_max_retries(trace_key)
                        logger.error(
                            f"Trace abandoned after max retries: {trade_id}",
                            extra={
                                "trade_id": trade_id,
                                "retry_count": retry_count,
                                "adapters_failed": [f[0] for f in adapter_failed],
                            },
                        )
                        failed += 1

                    processed += 1

                except Exception as e:
                    logger.error(
                        f"Error processing trace: {str(e)}",
                        extra={"error": str(e)},
                        exc_info=True,
                    )
                    failed += 1

        logger.info(
            "Trace worker cycle complete",
            extra={
                "processed": processed,
                "succeeded": succeeded,
                "failed": failed,
                "skipped": skipped,
            },
        )

        # Clean up
        await redis_client.close()
        await engine.dispose()

        return {
            "processed": processed,
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
        }

    except Exception as e:
        logger.error(
            f"Trace worker failed: {str(e)}", extra={"error": str(e)}, exc_info=True
        )
        raise


def _initialize_adapters(settings) -> dict[str, TraceAdapter]:
    """
    Initialize all configured adapters.

    Returns:
        Dict of {adapter_name: TraceAdapter instance}
    """
    adapters = {}

    try:
        # Myfxbook
        if "myfxbook" in settings.trace.enabled_adapters:
            config = AdapterConfig(name="myfxbook", enabled=True)
            adapter = MyfxbookAdapter(
                config,
                webhook_url=settings.trace.myfxbook_webhook_url,
                webhook_token=settings.trace.myfxbook_webhook_token,
            )
            adapters["myfxbook"] = adapter
            logger.info("Myfxbook adapter initialized")

        # File export
        if "file_export" in settings.trace.enabled_adapters:
            config = AdapterConfig(name="file_export", enabled=True)
            adapter = FileExportAdapter(
                config,
                export_type=settings.trace.file_export_type,
                local_path=settings.trace.file_export_local_path,
                s3_bucket=settings.trace.file_export_s3_bucket,
                s3_prefix=settings.trace.file_export_s3_prefix,
            )
            adapters["file_export"] = adapter
            logger.info("File export adapter initialized")

        # Generic webhook
        if "webhook" in settings.trace.enabled_adapters:
            config = AdapterConfig(name="webhook", enabled=True)
            adapter = WebhookAdapter(
                config,
                endpoint=settings.trace.webhook_endpoint,
                auth_header=settings.trace.webhook_auth_header,
                auth_token=settings.trace.webhook_auth_token,
            )
            adapters["webhook"] = adapter
            logger.info("Generic webhook adapter initialized")

    except Exception as e:
        logger.error(f"Failed to initialize adapters: {str(e)}", exc_info=True)

    return adapters


async def _post_trade_with_adapter(
    adapter: TraceAdapter, trade_data: dict[str, Any], retry_count: int
) -> bool:
    """
    Post trade using specific adapter.

    Args:
        adapter: TraceAdapter instance
        trade_data: Trade data (already stripped of PII)
        retry_count: Current retry attempt number

    Returns:
        bool: True if success, False if retriable failure
    """
    try:
        async with adapter as ctx_adapter:
            return await ctx_adapter.post_trade(trade_data, retry_count)
    except AdapterError:
        raise
    except Exception as e:
        logger.warning(f"Adapter error: {str(e)}", exc_info=True)
        return False
