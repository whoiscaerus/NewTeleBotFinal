"""
Telegram Client with Circuit Breaker protection.
Wraps python-telegram-bot methods to prevent cascading failures.
"""

from typing import Any, Optional, Union

from telegram import Bot, Message
from telegram.request import HTTPXRequest

from backend.app.core.circuit_breaker import CircuitBreaker
from backend.app.core.logging import get_logger
from backend.app.core.redis_cache import _redis_client
from backend.app.core.settings import settings

logger = get_logger(__name__)


class TelegramClient:
    """
    Wrapper around telegram.Bot with Circuit Breaker pattern.
    """

    def __init__(self, token: str):
        """
        Initialize Telegram Client.

        Args:
            token: Telegram Bot API token
        """
        # Use connection pooling for better performance
        request = HTTPXRequest(connection_pool_size=8)
        self.bot = Bot(token=token, request=request)
        self._circuit_breaker: Optional[CircuitBreaker] = None

    @property
    def circuit_breaker(self) -> Optional[CircuitBreaker]:
        """Lazy load circuit breaker to ensure Redis is connected."""
        if self._circuit_breaker is None and _redis_client:
            self._circuit_breaker = CircuitBreaker(
                name="telegram_api",
                redis=_redis_client,
                failure_threshold=5,
                recovery_timeout=60,
            )
        return self._circuit_breaker

    async def send_message(
        self, chat_id: Union[int, str], text: str, **kwargs
    ) -> Message:
        """
        Send message with circuit breaker protection.

        Args:
            chat_id: Target chat ID
            text: Message text
            **kwargs: Additional arguments for bot.send_message

        Returns:
            Message: Sent message object

        Raises:
            CircuitBreakerOpenException: If circuit is open
            TelegramError: If API call fails
        """
        cb = self.circuit_breaker

        if cb:
            return await cb.call(
                self.bot.send_message, chat_id=chat_id, text=text, **kwargs
            )

        # Fallback if Redis not available
        return await self.bot.send_message(chat_id=chat_id, text=text, **kwargs)

    async def get_me(self) -> Any:
        """Get bot info with circuit breaker."""
        cb = self.circuit_breaker
        if cb:
            return await cb.call(self.bot.get_me)
        return await self.bot.get_me()


# Global client instance
telegram_client = TelegramClient(token=settings.TELEGRAM_BOT_TOKEN)
