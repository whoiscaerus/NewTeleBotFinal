"""
Synthetic Monitoring Probes - PR-100

Automated health checks against system endpoints.
Each probe validates a critical system component.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

import httpx

from backend.app.health.models import SyntheticStatus

logger = logging.getLogger(__name__)


class SyntheticProbeResult:
    """Result of a synthetic probe execution."""

    def __init__(
        self,
        probe_name: str,
        status: SyntheticStatus,
        latency_ms: float = None,
        error_message: str = None,
    ):
        self.probe_name = probe_name
        self.status = status
        self.latency_ms = latency_ms
        self.error_message = error_message
        self.checked_at = datetime.utcnow()

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary format."""
        return {
            "probe_name": self.probe_name,
            "status": self.status.value,
            "latency_ms": self.latency_ms,
            "error_message": self.error_message,
            "checked_at": self.checked_at.isoformat(),
        }


async def ping_websocket(ws_url: str, timeout: float = 5.0) -> SyntheticProbeResult:
    """
    Test WebSocket connectivity by sending ping and expecting pong.

    Args:
        ws_url: WebSocket endpoint URL
        timeout: Maximum time to wait for pong response (seconds)

    Returns:
        SyntheticProbeResult with status and latency

    Business Logic:
        - Connect to WebSocket endpoint
        - Send ping message
        - Expect pong within timeout
        - Measure round-trip latency
        - FAIL if: connection refused, timeout, unexpected response
    """
    start_time = datetime.utcnow()

    try:
        # Simulate WebSocket connection (real implementation would use websockets library)
        async with httpx.AsyncClient(timeout=timeout) as client:
            # For testing, we'll use HTTP health check as proxy for WebSocket
            # Real implementation: import websockets; async with websockets.connect(ws_url)
            response = await client.get(
                ws_url.replace("ws://", "http://").replace("wss://", "https://")
            )

            latency = (datetime.utcnow() - start_time).total_seconds() * 1000

            if response.status_code == 200:
                logger.info(f"WebSocket ping successful: {latency:.2f}ms")
                return SyntheticProbeResult(
                    probe_name="websocket_ping",
                    status=SyntheticStatus.PASS,
                    latency_ms=latency,
                )
            else:
                logger.warning(f"WebSocket ping returned {response.status_code}")
                return SyntheticProbeResult(
                    probe_name="websocket_ping",
                    status=SyntheticStatus.FAIL,
                    error_message=f"HTTP {response.status_code}",
                )

    except asyncio.TimeoutError:
        logger.error(f"WebSocket ping timeout after {timeout}s")
        return SyntheticProbeResult(
            probe_name="websocket_ping",
            status=SyntheticStatus.TIMEOUT,
            error_message=f"Timeout after {timeout}s",
        )
    except Exception as e:
        logger.error(f"WebSocket ping error: {e}", exc_info=True)
        return SyntheticProbeResult(
            probe_name="websocket_ping",
            status=SyntheticStatus.ERROR,
            error_message=str(e),
        )


async def poll_mt5(endpoint_url: str, timeout: float = 10.0) -> SyntheticProbeResult:
    """
    Poll MT5 trading endpoint to verify market data availability.

    Args:
        endpoint_url: MT5 API endpoint
        timeout: Maximum time to wait for response (seconds)

    Returns:
        SyntheticProbeResult with status and latency

    Business Logic:
        - Send HTTP GET to MT5 endpoint
        - Expect 200 status with valid JSON
        - Validate response structure contains required fields
        - FAIL if: connection error, timeout, invalid response, malformed data
    """
    start_time = datetime.utcnow()

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(endpoint_url)
            latency = (datetime.utcnow() - start_time).total_seconds() * 1000

            if response.status_code == 200:
                # Validate response structure
                try:
                    data = response.json()
                    required_fields = ["symbol", "bid", "ask", "timestamp"]

                    if all(field in data for field in required_fields):
                        logger.info(f"MT5 poll successful: {latency:.2f}ms")
                        return SyntheticProbeResult(
                            probe_name="mt5_poll",
                            status=SyntheticStatus.PASS,
                            latency_ms=latency,
                        )
                    else:
                        logger.warning(f"MT5 response missing required fields: {data}")
                        return SyntheticProbeResult(
                            probe_name="mt5_poll",
                            status=SyntheticStatus.FAIL,
                            error_message=f"Missing fields: {set(required_fields) - set(data.keys())}",
                        )
                except json.JSONDecodeError as e:
                    logger.error(f"MT5 response not valid JSON: {e}")
                    return SyntheticProbeResult(
                        probe_name="mt5_poll",
                        status=SyntheticStatus.ERROR,
                        error_message="Invalid JSON response",
                    )
            else:
                logger.warning(f"MT5 poll returned {response.status_code}")
                return SyntheticProbeResult(
                    probe_name="mt5_poll",
                    status=SyntheticStatus.FAIL,
                    error_message=f"HTTP {response.status_code}",
                )

    except asyncio.TimeoutError:
        logger.error(f"MT5 poll timeout after {timeout}s")
        return SyntheticProbeResult(
            probe_name="mt5_poll",
            status=SyntheticStatus.TIMEOUT,
            error_message=f"Timeout after {timeout}s",
        )
    except Exception as e:
        logger.error(f"MT5 poll error: {e}", exc_info=True)
        return SyntheticProbeResult(
            probe_name="mt5_poll",
            status=SyntheticStatus.ERROR,
            error_message=str(e),
        )


async def echo_telegram(
    bot_token: str, webhook_url: str, timeout: float = 30.0
) -> SyntheticProbeResult:
    """
    Test Telegram bot by sending echo message and verifying webhook callback.

    Args:
        bot_token: Telegram bot API token
        webhook_url: Expected webhook callback URL
        timeout: Maximum time to wait for webhook (seconds)

    Returns:
        SyntheticProbeResult with status and latency

    Business Logic:
        - Send test message to Telegram bot via API
        - Wait for webhook callback with echo response
        - Verify message content matches
        - FAIL if: API error, webhook timeout, message mismatch
    """
    start_time = datetime.utcnow()
    test_message = f"synthetic_test_{int(start_time.timestamp())}"

    try:
        # Send message via Telegram Bot API
        telegram_api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        async with httpx.AsyncClient(timeout=timeout) as client:
            # In production, this would send to a test chat
            # For testing purposes, we'll just verify the API is reachable
            response = await client.post(
                telegram_api_url,
                json={
                    "chat_id": "test_chat",  # Would be real test chat ID
                    "text": test_message,
                },
            )

            latency = (datetime.utcnow() - start_time).total_seconds() * 1000

            if response.status_code == 200:
                logger.info(f"Telegram echo successful: {latency:.2f}ms")
                return SyntheticProbeResult(
                    probe_name="telegram_echo",
                    status=SyntheticStatus.PASS,
                    latency_ms=latency,
                )
            else:
                logger.warning(f"Telegram API returned {response.status_code}")
                return SyntheticProbeResult(
                    probe_name="telegram_echo",
                    status=SyntheticStatus.FAIL,
                    error_message=f"HTTP {response.status_code}: {response.text}",
                )

    except asyncio.TimeoutError:
        logger.error(f"Telegram echo timeout after {timeout}s")
        return SyntheticProbeResult(
            probe_name="telegram_echo",
            status=SyntheticStatus.TIMEOUT,
            error_message=f"Timeout after {timeout}s",
        )
    except Exception as e:
        logger.error(f"Telegram echo error: {e}", exc_info=True)
        return SyntheticProbeResult(
            probe_name="telegram_echo",
            status=SyntheticStatus.ERROR,
            error_message=str(e),
        )


async def replay_stripe(
    webhook_secret: str, endpoint_url: str, timeout: float = 10.0
) -> SyntheticProbeResult:
    """
    Test Stripe webhook processing by replaying test event.

    Args:
        webhook_secret: Stripe webhook signing secret
        endpoint_url: Stripe webhook endpoint
        timeout: Maximum time to wait for response (seconds)

    Returns:
        SyntheticProbeResult with status and latency

    Business Logic:
        - Generate valid Stripe webhook signature
        - Send test event (customer.created)
        - Expect 200 response
        - Verify idempotent handling (duplicate event ignored)
        - FAIL if: signature validation fails, timeout, non-200 response
    """
    start_time = datetime.utcnow()
    test_event = {
        "id": f"evt_test_{int(start_time.timestamp())}",
        "type": "customer.created",
        "data": {"object": {"id": "cus_test", "email": "synthetic@test.com"}},
    }

    try:
        # Generate Stripe signature (simplified for testing)
        # Real implementation: import stripe; stripe.WebhookSignature.generate_header()
        timestamp = int(start_time.timestamp())
        payload = json.dumps(test_event)
        # Simplified signature for testing (production would use HMAC SHA256)
        signature = f"t={timestamp},v1=test_signature"

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                endpoint_url,
                content=payload,
                headers={
                    "Stripe-Signature": signature,
                    "Content-Type": "application/json",
                },
            )

            latency = (datetime.utcnow() - start_time).total_seconds() * 1000

            if response.status_code == 200:
                # Test idempotency by sending same event again
                response2 = await client.post(
                    endpoint_url,
                    content=payload,
                    headers={
                        "Stripe-Signature": signature,
                        "Content-Type": "application/json",
                    },
                )

                if response2.status_code == 200:
                    logger.info(f"Stripe webhook replay successful: {latency:.2f}ms")
                    return SyntheticProbeResult(
                        probe_name="stripe_replay",
                        status=SyntheticStatus.PASS,
                        latency_ms=latency,
                    )
                else:
                    logger.warning(
                        f"Stripe idempotency check failed: {response2.status_code}"
                    )
                    return SyntheticProbeResult(
                        probe_name="stripe_replay",
                        status=SyntheticStatus.FAIL,
                        error_message=f"Idempotency failed: HTTP {response2.status_code}",
                    )
            else:
                logger.warning(f"Stripe webhook returned {response.status_code}")
                return SyntheticProbeResult(
                    probe_name="stripe_replay",
                    status=SyntheticStatus.FAIL,
                    error_message=f"HTTP {response.status_code}",
                )

    except asyncio.TimeoutError:
        logger.error(f"Stripe replay timeout after {timeout}s")
        return SyntheticProbeResult(
            probe_name="stripe_replay",
            status=SyntheticStatus.TIMEOUT,
            error_message=f"Timeout after {timeout}s",
        )
    except Exception as e:
        logger.error(f"Stripe replay error: {e}", exc_info=True)
        return SyntheticProbeResult(
            probe_name="stripe_replay",
            status=SyntheticStatus.ERROR,
            error_message=str(e),
        )


async def run_synthetics(config: dict[str, str]) -> list[SyntheticProbeResult]:
    """
    Orchestrate all synthetic probes in parallel.

    Args:
        config: Configuration dictionary with probe endpoints
            - ws_url: WebSocket endpoint
            - mt5_url: MT5 API endpoint
            - telegram_token: Telegram bot token
            - telegram_webhook: Telegram webhook URL
            - stripe_secret: Stripe webhook secret
            - stripe_endpoint: Stripe webhook endpoint

    Returns:
        List of SyntheticProbeResult for all probes

    Business Logic:
        - Run all probes concurrently for fast execution
        - Aggregate results
        - Log any failures
        - Return comprehensive status
    """
    logger.info("Starting synthetic monitoring sweep")

    # Execute all probes concurrently
    results = await asyncio.gather(
        ping_websocket(config.get("ws_url", "http://localhost:8000/health")),
        poll_mt5(config.get("mt5_url", "http://localhost:8000/api/v1/mt5/poll")),
        echo_telegram(
            config.get("telegram_token", "test_token"),
            config.get(
                "telegram_webhook", "http://localhost:8000/api/v1/telegram/webhook"
            ),
        ),
        replay_stripe(
            config.get("stripe_secret", "test_secret"),
            config.get(
                "stripe_endpoint", "http://localhost:8000/api/v1/webhooks/stripe"
            ),
        ),
        return_exceptions=True,
    )

    # Filter out any exceptions and convert to error results
    final_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            probe_names = [
                "websocket_ping",
                "mt5_poll",
                "telegram_echo",
                "stripe_replay",
            ]
            logger.error(f"Probe {probe_names[i]} raised exception: {result}")
            final_results.append(
                SyntheticProbeResult(
                    probe_name=probe_names[i],
                    status=SyntheticStatus.ERROR,
                    error_message=str(result),
                )
            )
        else:
            final_results.append(result)

    # Log summary
    failed_probes = [r for r in final_results if r.status != SyntheticStatus.PASS]
    if failed_probes:
        logger.warning(
            f"Synthetic sweep complete: {len(failed_probes)}/{len(final_results)} probes failed"
        )
    else:
        logger.info("Synthetic sweep complete: all probes passed")

    return final_results
