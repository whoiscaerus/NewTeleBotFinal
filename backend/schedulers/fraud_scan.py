"""Fraud detection scheduler for automated scanning.

Runs periodic scans of recent trades to detect anomalies.
"""

import asyncio
import logging
from datetime import datetime


from backend.app.core.db import async_session_maker
from backend.app.fraud.detectors import scan_recent_trades
from backend.app.observability.metrics import metrics_collector

logger = logging.getLogger(__name__)


async def run_fraud_scan(hours: int = 24) -> int:
    """Run fraud detection scan on recent trades.

    Args:
        hours: How many hours back to scan (default 24)

    Returns:
        Number of anomalies detected

    Business Logic:
        1. Fetch trades from last N hours
        2. Run all fraud detectors (slippage, latency, out-of-band)
        3. Persist detected anomalies to DB
        4. Increment fraud_events_total metric for each type
        5. Log summary
    """
    logger.info(f"Starting fraud scan for last {hours} hours")
    start_time = datetime.utcnow()

    async with async_session_maker() as db:
        try:
            # Run scan
            anomalies = await scan_recent_trades(db, hours=hours)

            # Increment metrics by type
            for anomaly in anomalies:
                metrics_collector.fraud_events_total.labels(
                    type=anomaly.anomaly_type
                ).inc()

            # Log summary
            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.info(
                f"Fraud scan complete: detected {len(anomalies)} anomalies "
                f"in {duration:.2f}s"
            )

            # Group by type for detailed logging
            by_type = {}
            for anomaly in anomalies:
                by_type[anomaly.anomaly_type] = by_type.get(anomaly.anomaly_type, 0) + 1

            if by_type:
                logger.info(f"Anomalies by type: {by_type}")

            return len(anomalies)

        except Exception as e:
            logger.error(f"Fraud scan failed: {e}", exc_info=True)
            raise


async def fraud_scan_daemon(interval_hours: int = 1):
    """Continuous fraud scanning daemon.

    Args:
        interval_hours: How often to run scans (default every 1 hour)

    Business Logic:
        - Runs fraud scan every N hours
        - Handles errors gracefully (logs but continues)
        - Never exits (daemon mode)
    """
    logger.info(f"Starting fraud scan daemon (interval={interval_hours}h)")

    while True:
        try:
            await run_fraud_scan(hours=24)
        except Exception as e:
            logger.error(f"Fraud scan daemon error: {e}", exc_info=True)

        # Sleep until next scan
        await asyncio.sleep(interval_hours * 3600)


if __name__ == "__main__":
    # Run scan once (for manual execution or cron jobs)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    asyncio.run(run_fraud_scan(hours=24))
