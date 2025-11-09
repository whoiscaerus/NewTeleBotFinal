"""Operational alerts service for sending notifications to ops team via Telegram.

This module provides functionality for sending alerts to the ops team via Telegram,
with structured message formatting and error handling. Used for notifying operations
of critical failures, persistent signal delivery issues, and system anomalies.

Environment Variables:
    OPS_TELEGRAM_BOT_TOKEN: Telegram bot token for sending messages
    OPS_TELEGRAM_CHAT_ID: Telegram chat ID for receiving alerts

Examples:
    Send a simple alert:
        await send_owner_alert("Signal delivery failing repeatedly")

    Send a detailed error alert:
        await send_signal_delivery_error(
            signal_id="sig-123",
            error=ex,
            attempts=5
        )
"""

import logging
from datetime import UTC

import httpx

__all__ = [
    "send_owner_alert",
    "send_signal_delivery_error",
    "send_feature_quality_alert",
    "OpsAlertService",
    "AlertConfigError",
]

logger = logging.getLogger(__name__)


# ============================================================================
# Exceptions
# ============================================================================


class AlertConfigError(Exception):
    """Raised when alert service is not properly configured."""

    pass


# ============================================================================
# Alert Service
# ============================================================================


class OpsAlertService:
    """Service for sending operational alerts via Telegram.

    Handles Telegram bot integration, message formatting, and error handling
    for operational alerts. All messages are sent to a configured Telegram chat.

    Attributes:
        telegram_token: Telegram bot token (from environment)
        telegram_chat_id: Telegram chat ID (from environment)
        logger: Logger instance for debugging

    Examples:
        Initialize from environment:
            service = OpsAlertService.from_env()

            # Send alert
            success = await service.send("Critical error occurred")

            # Send structured alert
            success = await service.send_error_alert(
                message="Signal delivery failed",
                error=exception,
                attempts=5
            )
    """

    def __init__(
        self,
        telegram_token: str | None = None,
        telegram_chat_id: str | None = None,
        logger_: logging.Logger | None = None,
    ) -> None:
        """Initialize alert service with Telegram credentials.

        Args:
            telegram_token: Telegram bot token (or from env TELEGRAM_TOKEN)
            telegram_chat_id: Telegram chat ID (or from env TELEGRAM_CHAT_ID)
            logger_: Optional logger instance
        """
        import os

        self.telegram_token = telegram_token or os.getenv("OPS_TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = telegram_chat_id or os.getenv("OPS_TELEGRAM_CHAT_ID")
        self.logger = logger_ or logger

        self.validate_config()

    def validate_config(self) -> None:
        """Validate that Telegram credentials are configured.

        Raises:
            AlertConfigError: If required credentials are missing
        """
        if not self.telegram_token:
            raise AlertConfigError(
                "Telegram bot token not configured. "
                "Set OPS_TELEGRAM_BOT_TOKEN environment variable."
            )
        if not self.telegram_chat_id:
            raise AlertConfigError(
                "Telegram chat ID not configured. "
                "Set OPS_TELEGRAM_CHAT_ID environment variable."
            )

    async def send(
        self,
        message: str,
        severity: str = "ERROR",
        include_timestamp: bool = True,
        timeout: float = 10.0,
    ) -> bool:
        """Send alert message via Telegram.

        Args:
            message: Alert message text
            severity: Alert severity level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            include_timestamp: Include timestamp in message (default: True)
            timeout: HTTP request timeout in seconds (default: 10.0)

        Returns:
            True if message sent successfully, False otherwise

        Examples:
            >>> service = OpsAlertService.from_env()
            >>> success = await service.send("Signal delivery failed")
            >>> print(f"Alert sent: {success}")
        """
        self.validate_config()

        # Format message with severity
        formatted_message = f"[{severity}] {message}"
        if include_timestamp:
            from datetime import datetime

            timestamp = datetime.now(UTC).isoformat()
            formatted_message = f"{formatted_message}\nTimestamp: {timestamp}"

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{self.telegram_token}/sendMessage",
                    json={
                        "chat_id": self.telegram_chat_id,
                        "text": formatted_message,
                        "parse_mode": "HTML",
                    },
                )

                if response.status_code == 200:
                    self.logger.debug(f"Telegram alert sent: {message[:50]}...")
                    return True
                else:
                    self.logger.error(
                        f"Telegram API error: {response.status_code}. "
                        f"Response: {response.text[:200]}"
                    )
                    return False

        except httpx.TimeoutException:
            self.logger.error("Telegram API request timed out")
            return False
        except Exception as e:
            self.logger.error(
                f"Error sending Telegram alert: {type(e).__name__}: {str(e)}",
                exc_info=True,
            )
            return False

    async def send_error_alert(
        self,
        message: str,
        error: Exception | None = None,
        attempts: int | None = None,
        operation: str | None = None,
        timeout: float = 10.0,
    ) -> bool:
        """Send a structured error alert with context.

        Args:
            message: Main error message
            error: Optional exception that occurred
            attempts: Optional number of retry attempts made
            operation: Optional name of operation that failed
            timeout: HTTP request timeout in seconds

        Returns:
            True if message sent successfully, False otherwise

        Examples:
            >>> from backend.app.trading.outbound import OutboundClientError
            >>> try:
            ...     await client.post_signal(signal)
            ... except OutboundClientError as e:
            ...     await service.send_error_alert(
            ...         message="Signal delivery failed",
            ...         error=e,
            ...         attempts=5,
            ...         operation="post_signal"
            ...     )
        """
        # Build detailed error message
        alert_parts = [f"🚨 {message}"]

        if operation:
            alert_parts.append(f"Operation: <b>{operation}</b>")

        if error:
            alert_parts.append(f"Error: <code>{type(error).__name__}</code>")
            alert_parts.append(f"Details: {str(error)[:200]}")

        if attempts is not None:
            alert_parts.append(f"Attempts: {attempts}")

        full_message = "\n".join(alert_parts)

        return await self.send(full_message, severity="CRITICAL", timeout=timeout)

    @classmethod
    def from_env(cls, logger_: logging.Logger | None = None) -> "OpsAlertService":
        """Create alert service from environment variables.

        Environment variables:
            OPS_TELEGRAM_BOT_TOKEN: Required - Telegram bot token
            OPS_TELEGRAM_CHAT_ID: Required - Telegram chat ID

        Args:
            logger_: Optional logger instance

        Returns:
            Configured OpsAlertService instance

        Raises:
            AlertConfigError: If required env vars are missing

        Examples:
            >>> service = OpsAlertService.from_env()
        """
        return cls(logger_=logger_)


# ============================================================================
# Module-Level Functions
# ============================================================================


_alert_service: OpsAlertService | None = None


def _get_alert_service() -> OpsAlertService:
    """Get or initialize the global alert service.

    Returns:
        OpsAlertService instance

    Raises:
        AlertConfigError: If Telegram credentials not configured
    """
    global _alert_service
    if _alert_service is None:
        _alert_service = OpsAlertService.from_env()
    return _alert_service


async def send_owner_alert(
    message: str,
    severity: str = "ERROR",
    logger_: logging.Logger | None = None,
) -> bool:
    """Send alert to ops team via Telegram.

    This is the main entry point for sending operational alerts.
    The message is sent to the configured Telegram chat via the ops bot.

    Args:
        message: Alert message text
        severity: Alert severity (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        logger_: Optional logger for debugging

    Returns:
        True if sent successfully, False if failed

    Raises:
        AlertConfigError: If Telegram credentials not configured

    Examples:
        >>> await send_owner_alert("Signal delivery service is down")
        True

        >>> await send_owner_alert(
        ...     "Multiple signals failed",
        ...     severity="CRITICAL"
        ... )
    """
    try:
        service = _get_alert_service()
        return await service.send(message, severity=severity)
    except AlertConfigError:
        _logger = logger_ or logger
        _logger.error("Alert service not configured. Check Telegram env vars.")
        return False


async def send_signal_delivery_error(
    signal_id: str,
    error: Exception,
    attempts: int,
    operation: str = "post_signal",
    logger_: logging.Logger | None = None,
) -> bool:
    """Send signal delivery error alert to ops team.

    Called when signal delivery fails after all retries are exhausted.
    Formats a structured error message with context about the failure.

    Args:
        signal_id: ID of the signal that failed
        error: Exception that occurred
        attempts: Number of delivery attempts made
        operation: Name of operation (default: post_signal)
        logger_: Optional logger for debugging

    Returns:
        True if alert sent successfully, False otherwise

    Examples:
        >>> from backend.app.trading.outbound import OutboundClientError
        >>> try:
        ...     await client.post_signal(signal)
        ... except OutboundClientError as e:
        ...     await send_signal_delivery_error(
        ...         signal_id=signal.id,
        ...         error=e,
        ...         attempts=5
        ...     )
    """
    try:
        service = _get_alert_service()
        alert_message = (
            f"Signal delivery failed\n"
            f"Signal ID: {signal_id}\n"
            f"Operation: {operation}\n"
            f"Attempts: {attempts}"
        )
        return await service.send_error_alert(
            message=alert_message,
            error=error,
            attempts=attempts,
            operation=operation,
        )
    except AlertConfigError:
        _logger = logger_ or logger
        _logger.error(
            f"Alert service not configured. Signal {signal_id} delivery failed silently."
        )
        return False


async def send_feature_quality_alert(
    violation_type: str,
    symbol: str,
    message: str,
    severity: str = "medium",
    metadata: dict | None = None,
    logger_: logging.Logger | None = None,
) -> bool:
    """Send feature quality violation alert to ops team.

    Called when feature quality checks detect violations (staleness, NaNs, drift).
    Formats a structured alert with violation details for investigation.

    Args:
        violation_type: Type of violation (missing_features, nan_values, stale_data, drift_detected)
        symbol: Trading instrument affected
        message: Human-readable violation description
        severity: Violation severity (low, medium, high)
        metadata: Additional context dict (optional)
        logger_: Optional logger for debugging

    Returns:
        True if alert sent successfully, False otherwise

    Examples:
        >>> await send_feature_quality_alert(
        ...     violation_type="nan_values",
        ...     symbol="GOLD",
        ...     message="2 features contain NaN: rsi_14, roc_10",
        ...     severity="high",
        ...     metadata={"snapshot_id": 123}
        ... )
        True

        >>> await send_feature_quality_alert(
        ...     violation_type="stale_data",
        ...     symbol="XAUUSD",
        ...     message="Data is 600s old (max 300s)",
        ...     severity="medium"
        ... )
    """
    try:
        service = _get_alert_service()

        # Map severity to emoji
        severity_icons = {
            "low": "ℹ️",
            "medium": "⚠️",
            "high": "🚨",
        }
        icon = severity_icons.get(severity.lower(), "⚠️")

        # Format alert message
        alert_parts = [
            f"{icon} <b>Feature Quality Violation</b>",
            f"Type: <code>{violation_type}</code>",
            f"Symbol: <b>{symbol}</b>",
            f"Severity: {severity.upper()}",
            f"",
            f"{message}",
        ]

        # Add metadata if provided
        if metadata:
            alert_parts.append("")
            alert_parts.append("<b>Details:</b>")
            for key, value in metadata.items():
                alert_parts.append(f"  • {key}: {value}")

        full_message = "\n".join(alert_parts)

        return await service.send(
            full_message,
            severity=severity.upper(),
        )

    except AlertConfigError:
        _logger = logger_ or logger
        _logger.error(
            f"Alert service not configured. Feature quality violation for {symbol} not sent."
        )
        return False
