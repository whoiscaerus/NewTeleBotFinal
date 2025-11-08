"""Signal publisher for routing to APIs and notification channels.

Routes accepted signals to:
1. Signals API (PR-021) for storage and approval workflow
2. Admin Telegram channel (optional) for monitoring

Includes duplicate prevention, error handling, and telemetry.

Example:
    >>> from backend.app.strategy.publisher import SignalPublisher
    >>> publisher = SignalPublisher(signals_api_base="http://localhost:8000")
    >>>
    >>> signal_data = {
    ...     "instrument": "GOLD",
    ...     "side": "buy",
    ...     "entry_price": 1950.50,
    ...     "stop_loss": 1945.00,
    ...     "take_profit": 1960.00,
    ...     "strategy": "ppo_gold",
    ...     "timestamp": datetime.utcnow(),
    ... }
    >>>
    >>> # Publish to API + optional Telegram
    >>> result = await publisher.publish(signal_data, notify_telegram=True)
"""

import logging
import os
from datetime import datetime
from typing import Any

import httpx
from telegram import Bot

logger = logging.getLogger(__name__)


class SignalPublisher:
    """Publishes signals to API and notification channels.

    Attributes:
        signals_api_base: Base URL for Signals API (PR-021)
        telegram_token: Bot token for admin notifications
        telegram_admin_chat_id: Chat ID for admin notifications
        _telegram_bot: Telegram bot instance (lazy-loaded)
        _published_signals: Cache for duplicate prevention
    """

    def __init__(
        self,
        signals_api_base: str | None = None,
        telegram_token: str | None = None,
        telegram_admin_chat_id: str | None = None,
    ):
        """Initialize signal publisher.

        Args:
            signals_api_base: Signals API base URL (default: from env)
            telegram_token: Telegram bot token (default: from env)
            telegram_admin_chat_id: Admin chat ID (default: from env)

        Example:
            >>> publisher = SignalPublisher(
            ...     signals_api_base="http://localhost:8000",
            ...     telegram_token="1234567890:ABC...",
            ...     telegram_admin_chat_id="-100123456789"
            ... )
        """
        self.signals_api_base = signals_api_base or os.getenv(
            "SIGNALS_API_BASE", "http://localhost:8000"
        )
        self.telegram_token = telegram_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_admin_chat_id = telegram_admin_chat_id or os.getenv(
            "TELEGRAM_ADMIN_CHAT_ID"
        )

        self._telegram_bot: Bot | None = None
        self._published_signals: dict[tuple, datetime] = (
            {}
        )  # (instrument, candle_start) -> timestamp

        # Validate configuration
        if not self.signals_api_base:
            logger.warning("SIGNALS_API_BASE not configured, API publishing disabled")

        if self.telegram_token and self.telegram_admin_chat_id:
            logger.info(
                "SignalPublisher initialized with Telegram notifications",
                extra={
                    "api_base": self.signals_api_base,
                    "telegram_enabled": True,
                },
            )
        else:
            logger.info(
                "SignalPublisher initialized without Telegram notifications",
                extra={"api_base": self.signals_api_base},
            )

    async def publish(
        self,
        signal_data: dict[str, Any],
        notify_telegram: bool = False,
    ) -> dict[str, Any]:
        """Publish signal to API and optionally to Telegram.

        Args:
            signal_data: Signal data dictionary containing:
                - instrument: Trading instrument (e.g., "GOLD")
                - side: "buy" or "sell"
                - entry_price: Entry price
                - stop_loss: Stop loss price
                - take_profit: Take profit price
                - strategy: Strategy name (e.g., "ppo_gold")
                - timestamp: Signal generation timestamp
                - candle_start: Candle start timestamp (for duplicate prevention)
            notify_telegram: Whether to send admin Telegram notification

        Returns:
            Dictionary with publishing results:
                - api_success: Boolean
                - api_response: API response data or None
                - telegram_success: Boolean (if attempted)
                - signal_id: API-assigned signal ID (if successful)

        Raises:
            ValueError: If required fields missing

        Example:
            >>> result = await publisher.publish({
            ...     "instrument": "GOLD",
            ...     "side": "buy",
            ...     "entry_price": 1950.50,
            ...     "stop_loss": 1945.00,
            ...     "take_profit": 1960.00,
            ...     "strategy": "ppo_gold",
            ...     "timestamp": datetime.utcnow(),
            ...     "candle_start": datetime(2025, 1, 1, 10, 15),
            ... }, notify_telegram=True)
            >>> print(result)
            {
                "api_success": True,
                "api_response": {"id": "sig-123", "status": "new"},
                "telegram_success": True,
                "signal_id": "sig-123"
            }
        """
        # Validate required fields
        required_fields = ["instrument", "side", "entry_price", "strategy", "timestamp"]
        missing_fields = [f for f in required_fields if f not in signal_data]
        if missing_fields:
            raise ValueError(f"Missing required fields: {missing_fields}")

        # Check for duplicates
        candle_start = signal_data.get("candle_start")
        if candle_start:
            cache_key = (signal_data["instrument"], candle_start)
            if cache_key in self._published_signals:
                logger.warning(
                    "Duplicate signal detected, skipping publish",
                    extra={
                        "instrument": signal_data["instrument"],
                        "candle_start": candle_start.isoformat(),
                        "previous_publish": self._published_signals[
                            cache_key
                        ].isoformat(),
                    },
                )
                return {
                    "api_success": False,
                    "api_response": None,
                    "telegram_success": False,
                    "signal_id": None,
                    "error": "Duplicate signal",
                }

        result: dict[str, Any] = {
            "api_success": False,
            "api_response": None,
            "telegram_success": False,
            "signal_id": None,
        }

        # Publish to Signals API
        try:
            api_response = await self._publish_to_api(signal_data)
            result["api_success"] = True
            result["api_response"] = api_response
            result["signal_id"] = api_response.get("id")

            logger.info(
                "Signal published to API",
                extra={
                    "instrument": signal_data["instrument"],
                    "signal_id": result["signal_id"],
                    "strategy": signal_data["strategy"],
                },
            )

            # Mark as published (duplicate prevention)
            if candle_start:
                cache_key = (signal_data["instrument"], candle_start)
                self._published_signals[cache_key] = signal_data["timestamp"]

                # Cleanup old entries
                if len(self._published_signals) > 1000:
                    self._cleanup_old_signals()

        except Exception as e:
            logger.error(
                f"Failed to publish signal to API: {e}",
                extra={
                    "instrument": signal_data["instrument"],
                    "strategy": signal_data["strategy"],
                },
                exc_info=True,
            )
            result["error"] = str(e)

        # Optional: Publish to Telegram admin channel
        if notify_telegram and result["api_success"]:
            signal_id = result["signal_id"]
            if isinstance(signal_id, str):
                try:
                    await self._publish_to_telegram(signal_data, signal_id)
                    result["telegram_success"] = True

                    logger.info(
                        "Signal notification sent to Telegram",
                        extra={"signal_id": signal_id},
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to send Telegram notification: {e}",
                        extra={"signal_id": signal_id},
                        exc_info=True,
                    )

        return result

    async def _publish_to_api(self, signal_data: dict[str, Any]) -> dict[str, Any]:
        """Publish signal to Signals API (PR-021).

        Args:
            signal_data: Signal data dictionary

        Returns:
            API response data

        Raises:
            httpx.HTTPError: If API request fails
        """
        if not self.signals_api_base:
            raise ValueError("SIGNALS_API_BASE not configured")

        # Prepare API payload
        payload = {
            "instrument": signal_data["instrument"],
            "side": signal_data["side"],
            "entry_price": signal_data["entry_price"],
            "stop_loss": signal_data.get("stop_loss"),
            "take_profit": signal_data.get("take_profit"),
            "strategy": signal_data["strategy"],
            "timestamp": signal_data["timestamp"].isoformat(),
            "payload": {
                "confidence": signal_data.get("confidence"),
                "features": signal_data.get("features"),
            },
        }

        # Remove None values
        payload = {k: v for k, v in payload.items() if v is not None}

        # Make API request
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.signals_api_base}/api/v1/signals",
                json=payload,
            )
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result

    async def _publish_to_telegram(
        self,
        signal_data: dict[str, Any],
        signal_id: str | None,
    ) -> None:
        """Send admin notification to Telegram.

        Args:
            signal_data: Signal data dictionary
            signal_id: API-assigned signal ID

        Raises:
            TelegramError: If message send fails
        """
        if not self.telegram_token or not self.telegram_admin_chat_id:
            raise ValueError("Telegram not configured")

        # Lazy-load bot
        if self._telegram_bot is None:
            self._telegram_bot = Bot(token=self.telegram_token)

        # Format message
        side_emoji = "🟢" if signal_data["side"] == "buy" else "🔴"
        message = f"""
{side_emoji} <b>New Signal Generated</b>

<b>Instrument:</b> {signal_data['instrument']}
<b>Side:</b> {signal_data['side'].upper()}
<b>Entry:</b> {signal_data.get('entry_price', 'N/A')}
<b>SL:</b> {signal_data.get('stop_loss', 'N/A')}
<b>TP:</b> {signal_data.get('take_profit', 'N/A')}
<b>Strategy:</b> {signal_data['strategy']}
<b>Time:</b> {signal_data['timestamp'].strftime('%Y-%m-%d %H:%M:%S UTC')}
<b>Signal ID:</b> {signal_id or 'N/A'}
        """.strip()

        # Send message
        await self._telegram_bot.send_message(
            chat_id=self.telegram_admin_chat_id,
            text=message,
            parse_mode="HTML",
        )

    def _cleanup_old_signals(self) -> None:
        """Remove oldest signals from cache to prevent memory bloat.

        Keeps only the 500 most recent signals.
        """
        if len(self._published_signals) <= 500:
            return

        # Sort by timestamp and keep 500 most recent
        sorted_items = sorted(
            self._published_signals.items(),
            key=lambda x: x[1],  # Sort by timestamp
            reverse=True,
        )

        # Keep only 500 most recent
        self._published_signals = dict(sorted_items[:500])

        logger.debug(
            "Cleaned up old signals from cache",
            extra={"remaining": len(self._published_signals)},
        )

    def clear_cache(self) -> None:
        """Clear published signals cache.

        Useful for testing or manual resets.
        """
        self._published_signals.clear()
        logger.info("Signal publish cache cleared")


# Singleton instance for convenience
_publisher: SignalPublisher | None = None


def get_signal_publisher() -> SignalPublisher:
    """Get global signal publisher instance.

    Returns:
        Singleton SignalPublisher instance

    Example:
        >>> from backend.app.strategy.publisher import get_signal_publisher
        >>> publisher = get_signal_publisher()
        >>> result = await publisher.publish(signal_data)
    """
    global _publisher
    if _publisher is None:
        _publisher = SignalPublisher()
    return _publisher
