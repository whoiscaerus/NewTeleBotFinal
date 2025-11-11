"""
Health Monitoring Scheduler - PR-100

Periodic task runner for autonomous health monitoring.
Runs synthetic probes every 60s, creates incidents, triggers remediation.
"""

import asyncio
import logging
import os
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from backend.app.core.db import get_db
from backend.app.health.incidents import create_incident, resolve_incident
from backend.app.health.models import IncidentSeverity
from backend.app.health.remediator import execute_remediation
from backend.app.health.synthetics import SyntheticStatus, run_synthetics

logger = logging.getLogger(__name__)

# Configuration from environment
SYNTHETICS_INTERVAL_SECONDS = int(os.getenv("SYNTHETICS_INTERVAL_SECONDS", 60))

# Remediation mapping: probe failure type → remediation action
REMEDIATION_MAP = {
    "websocket_ping_failure": {
        "action_type": "restart_service",
        "params": {"service_name": "websocket_service", "orchestrator": "docker"},
    },
    "mt5_poll_failure": {
        "action_type": "restart_service",
        "params": {"service_name": "mt5_bridge", "orchestrator": "docker"},
    },
    "telegram_echo_failure": {
        "action_type": "rotate_token",
        "params": {"token_type": "telegram_bot", "config_path": "/etc/app/config.json"},
    },
    "stripe_replay_failure": {
        "action_type": "restart_service",
        "params": {"service_name": "webhook_processor", "orchestrator": "docker"},
    },
}


async def run_health_check_cycle():
    """
    Execute one health monitoring cycle.

    Business Logic:
        1. Run all synthetic probes
        2. For each failure:
           a. Create incident (or update existing)
           b. Trigger appropriate remediation
           c. Log result
        3. For each success (after previous failure):
           a. Resolve incident
           b. Log recovery

    This function is called periodically by the scheduler.
    """
    logger.info("Starting health check cycle")
    start_time = datetime.utcnow()

    try:
        # Get synthetic probe configuration
        config = {
            "ws_url": os.getenv("WEBSOCKET_URL", "http://localhost:8000/health"),
            "mt5_url": os.getenv("MT5_URL", "http://localhost:8000/api/v1/mt5/poll"),
            "telegram_token": os.getenv("TELEGRAM_BOT_TOKEN", "test_token"),
            "telegram_webhook": os.getenv(
                "TELEGRAM_WEBHOOK_URL", "http://localhost:8000/api/v1/telegram/webhook"
            ),
            "stripe_secret": os.getenv("STRIPE_WEBHOOK_SECRET", "test_secret"),
            "stripe_endpoint": os.getenv(
                "STRIPE_WEBHOOK_URL", "http://localhost:8000/api/v1/webhooks/stripe"
            ),
        }

        # Run all synthetic probes
        results = await run_synthetics(config)

        # Get database session
        async for db in get_db():
            # Process results
            for result in results:
                if result.status == SyntheticStatus.PASS:
                    logger.debug(f"Probe {result.probe_name} passed")
                    # TODO: Check if there's an open incident for this probe and resolve it
                    # For now, we'll just log success

                else:
                    # Probe failed - create incident
                    logger.warning(
                        f"Probe {result.probe_name} failed: {result.error_message}"
                    )

                    # Determine severity based on probe failure type
                    severity = IncidentSeverity.HIGH
                    if result.status == SyntheticStatus.ERROR:
                        severity = IncidentSeverity.CRITICAL
                    elif result.status == SyntheticStatus.TIMEOUT:
                        severity = IncidentSeverity.HIGH
                    elif result.status == SyntheticStatus.FAIL:
                        severity = IncidentSeverity.MEDIUM

                    # Create incident
                    incident = await create_incident(
                        db,
                        result,
                        severity=severity,
                        notify_owner=(severity == IncidentSeverity.CRITICAL),
                    )

                    # Trigger remediation
                    incident_type = f"{result.probe_name}_failure"
                    if incident_type in REMEDIATION_MAP:
                        remediation_config = REMEDIATION_MAP[incident_type]
                        logger.info(
                            f"Triggering remediation for incident {incident.id}: {remediation_config['action_type']}"
                        )

                        remediation_result = await execute_remediation(
                            action_type=remediation_config["action_type"],
                            params=remediation_config["params"],
                        )

                        if remediation_result.success:
                            logger.info(
                                f"Remediation successful for incident {incident.id}, auto-resolving"
                            )
                            # Auto-resolve incident if remediation succeeded
                            await resolve_incident(
                                db,
                                incident.id,
                                resolution=f"Auto-remediated: {remediation_result.message}",
                                remediation_result=remediation_result,
                            )
                        else:
                            logger.error(
                                f"Remediation failed for incident {incident.id}: {remediation_result.message}"
                            )
                            # Incident remains open for manual investigation
                    else:
                        logger.warning(
                            f"No remediation configured for incident type: {incident_type}"
                        )

            # Commit all changes
            await db.commit()
            break  # Exit after first iteration (get_db is async generator)

        elapsed = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"Health check cycle complete in {elapsed:.2f}s")

    except Exception as e:
        logger.error(f"Error in health check cycle: {e}", exc_info=True)


def start_health_monitoring(app=None):
    """
    Start the health monitoring scheduler.

    Args:
        app: Optional FastAPI app for lifespan integration

    Business Logic:
        - Create AsyncIOScheduler
        - Schedule run_health_check_cycle every SYNTHETICS_INTERVAL_SECONDS
        - Start scheduler
        - Log startup
    """
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        run_health_check_cycle,
        trigger=IntervalTrigger(seconds=SYNTHETICS_INTERVAL_SECONDS),
        id="health_monitoring",
        name="Autonomous Health Monitoring",
        replace_existing=True,
        max_instances=1,  # Prevent overlapping runs
    )

    scheduler.start()
    logger.info(
        f"Health monitoring scheduler started (interval: {SYNTHETICS_INTERVAL_SECONDS}s)"
    )

    return scheduler


def stop_health_monitoring(scheduler):
    """
    Stop the health monitoring scheduler.

    Args:
        scheduler: APScheduler instance

    Business Logic:
        - Shutdown scheduler gracefully
        - Wait for any running jobs to complete
    """
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=True)
        logger.info("Health monitoring scheduler stopped")


# For manual testing
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    async def test_health_monitoring():
        """Run one health check cycle for testing."""
        logger.info("Running test health check cycle")
        await run_health_check_cycle()

    asyncio.run(test_health_monitoring())
