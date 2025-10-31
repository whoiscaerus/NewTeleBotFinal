"""Marketing module: Subscription promos with CTAs and user tracking.

This module handles periodic marketing broadcasts with inline CTAs, tracking
of user clicks, and conversion analytics.

Example:
    >>> from telegram import Bot
    >>> from backend.app.marketing.scheduler import MarketingScheduler
    >>>
    >>> bot = Bot(token="YOUR_TOKEN")
    >>> scheduler = MarketingScheduler(
    ...     bot=bot,
    ...     promo_chat_ids=[-1001234567890],
    ... )
    >>> scheduler.start()  # Start posting promos every 4 hours
"""

import json
import logging
from datetime import datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import TelegramError

from backend.app.observability.metrics import get_metrics

logger = logging.getLogger(__name__)


class MarketingScheduler:
    """Scheduler for periodic marketing broadcast posting."""

    # Default promo messages (can be extended)
    DEFAULT_PROMOS = [
        {
            "id": "promo_1",
            "title": "🚀 Premium Trading Signals",
            "description": "Get exclusive trading signals with 94% win rate.",
            "cta_text": "Upgrade to Premium",
            "cta_url": "https://t.me/CaerusTradingBot?start=premium",
        },
        {
            "id": "promo_2",
            "title": "💎 Copy Trading Features",
            "description": "Automatically copy professional traders' positions.",
            "cta_text": "Enable Copy Trading",
            "cta_url": "https://t.me/CaerusTradingBot?start=copytrading",
        },
        {
            "id": "promo_3",
            "title": "📊 Advanced Analytics",
            "description": "Deep insights into your trading performance.",
            "cta_text": "View Analytics",
            "cta_url": "https://t.me/CaerusTradingBot?start=analytics",
        },
        {
            "id": "promo_4",
            "title": "🎯 VIP Priority Support",
            "description": "Get priority support and dedicated account manager.",
            "cta_text": "Become VIP",
            "cta_url": "https://t.me/CaerusTradingBot?start=vip",
        },
    ]

    def __init__(
        self,
        bot: Bot,
        promo_chat_ids: list[int],
        interval_hours: int = 4,
        db_session: Any | None = None,
    ):
        """Initialize the marketing scheduler.

        Args:
            bot: The Telegram bot instance.
            promo_chat_ids: List of chat IDs to post promos to.
            interval_hours: Hours between promo posts (default: 4).
            db_session: Optional database session for logging clicks.

        Example:
            >>> bot = Bot(token="YOUR_TOKEN")
            >>> scheduler = MarketingScheduler(
            ...     bot=bot,
            ...     promo_chat_ids=[-1001234567890],
            ...     interval_hours=4,
            ... )
        """
        self.bot = bot
        self.promo_chat_ids = promo_chat_ids
        self.interval_hours = interval_hours
        self.db_session = db_session
        self.logger = logger
        self.scheduler = AsyncIOScheduler()
        self.is_running = False
        self.last_promo_index = 0

    def start(self) -> None:
        """Start the scheduler.

        Begins periodic promo posting. If scheduler is already running, does nothing.

        Example:
            >>> scheduler = MarketingScheduler(bot=bot, promo_chat_ids=[-1001234567890])
            >>> scheduler.start()
            >>> print("Scheduler started")
        """
        if self.is_running:
            self.logger.warning("Scheduler already running")
            return

        try:
            # Add job to schedule
            self.scheduler.add_job(
                self._post_promo,
                trigger=IntervalTrigger(hours=self.interval_hours),
                id="marketing_posting_job",
                name="Post marketing promos to channels",
                replace_existing=True,
            )

            # Start scheduler
            self.scheduler.start()
            self.is_running = True

            self.logger.info(
                "Marketing scheduler started",
                extra={
                    "interval_hours": self.interval_hours,
                    "chat_ids": self.promo_chat_ids,
                },
            )

        except Exception as e:
            self.logger.error(
                "Failed to start marketing scheduler",
                extra={"error": str(e)},
                exc_info=True,
            )
            raise

    def stop(self) -> None:
        """Stop the scheduler.

        Example:
            >>> scheduler.stop()
            >>> print("Scheduler stopped")
        """
        if not self.is_running:
            return

        try:
            self.scheduler.shutdown()
            self.is_running = False
            self.logger.info("Marketing scheduler stopped")
        except Exception as e:
            self.logger.error(
                "Error stopping scheduler", extra={"error": str(e)}, exc_info=True
            )

    async def _post_promo(self) -> None:
        """Post a promo to all configured chat IDs.

        This method is called by the scheduler at regular intervals.
        Selects a promo from DEFAULT_PROMOS, creates keyboard button,
        and posts to all configured channels.

        Errors in posting don't crash the job - they're logged and continue.
        """
        try:
            # Select promo (rotate through available promos)
            promo = self.DEFAULT_PROMOS[self.last_promo_index]
            self.last_promo_index = (self.last_promo_index + 1) % len(
                self.DEFAULT_PROMOS
            )

            # Create message with inline keyboard (MarkdownV2 safe)
            text = f"*{promo['title']}*\n\n{promo['description']}"
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton(text=promo["cta_text"], url=promo["cta_url"])]]
            )

            posted_to_chats = []
            failed_chats = []

            # Post to all configured chats
            for chat_id in self.promo_chat_ids:
                try:
                    message = await self.bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        reply_markup=keyboard,
                        parse_mode=ParseMode.MARKDOWN_V2,
                    )

                    posted_to_chats.append(chat_id)

                    self.logger.info(
                        "Promo posted successfully",
                        extra={
                            "promo_id": promo["id"],
                            "chat_id": chat_id,
                            "message_id": message.message_id,
                        },
                    )

                    # Record telemetry
                    get_metrics().record_marketing_post()

                except TelegramError as e:
                    failed_chats.append(chat_id)

                    self.logger.error(
                        "Failed to post promo to chat",
                        extra={
                            "promo_id": promo["id"],
                            "chat_id": chat_id,
                            "error": str(e),
                        },
                    )

                except Exception as e:
                    failed_chats.append(chat_id)

                    self.logger.error(
                        "Unexpected error posting promo",
                        extra={
                            "promo_id": promo["id"],
                            "chat_id": chat_id,
                            "error": str(e),
                        },
                        exc_info=True,
                    )

            # Log summary
            self.logger.info(
                "Promo posting cycle completed",
                extra={
                    "promo_id": promo["id"],
                    "posted_to": len(posted_to_chats),
                    "failed": len(failed_chats),
                    "posted_to_chats": posted_to_chats,
                    "failed_chats": failed_chats,
                },
            )

            # Log to database if session available
            if self.db_session is not None:
                await self._log_promo_event(
                    promo_id=promo["id"],
                    posted_to=len(posted_to_chats),
                    failed=len(failed_chats),
                )

        except Exception as e:
            self.logger.error(
                "Error in promo posting job", extra={"error": str(e)}, exc_info=True
            )

    async def _log_promo_event(
        self,
        promo_id: str,
        posted_to: int,
        failed: int,
    ) -> None:
        """Log promo event to database.

        Args:
            promo_id: ID of posted promo.
            posted_to: Number of successful posts.
            failed: Number of failed posts.
        """
        try:
            from backend.app.marketing.models import MarketingPromoLog

            log_entry = MarketingPromoLog(
                id=str(__import__("uuid").uuid4()),
                promo_id=promo_id,
                posted_to=posted_to,
                failed=failed,
                created_at=datetime.utcnow(),
            )
            if self.db_session is not None:
                self.db_session.add(log_entry)
                await self.db_session.commit()

            self.logger.debug("Promo event logged", extra={"promo_id": promo_id})

        except Exception as e:
            self.logger.error(
                "Failed to log promo event",
                extra={"promo_id": promo_id, "error": str(e)},
                exc_info=True,
            )

    def get_next_run_time(self) -> datetime | None:
        """Get the next scheduled run time.

        Returns:
            datetime of next run, or None if not scheduled.
        """
        try:
            job = self.scheduler.get_job("marketing_posting_job")
            return job.next_run_time if job else None
        except Exception as e:
            self.logger.error(
                "Error getting next run time", extra={"error": str(e)}, exc_info=True
            )
            return None

    def get_job_status(self) -> dict[str, Any]:
        """Get current status of the posting job.

        Returns:
            Dictionary with job status information.
        """
        try:
            job = self.scheduler.get_job("marketing_posting_job")
            if not job:
                return {"status": "not_scheduled"}

            return {
                "status": "scheduled",
                "next_run_time": (
                    job.next_run_time.isoformat() if job.next_run_time else None
                ),
                "last_execution_time": (
                    job.last_run_time.isoformat() if job.last_run_time else None
                ),
            }

        except Exception as e:
            self.logger.error(
                "Error getting job status", extra={"error": str(e)}, exc_info=True
            )
            return {"status": "error"}

    @classmethod
    def create_from_env(
        cls,
        bot: Bot,
        promos_chat_ids_json: str,
        db_session: Any | None = None,
    ) -> "MarketingScheduler":
        """Create scheduler from environment configuration.

        Args:
            bot: Telegram bot instance.
            promos_chat_ids_json: JSON string with chat IDs: '[-1001234567890, -1001234567891]'
            db_session: Optional database session.

        Returns:
            MarketingScheduler instance.

        Raises:
            ValueError: If JSON is invalid.

        Example:
            >>> scheduler = MarketingScheduler.create_from_env(
            ...     bot=bot,
            ...     promos_chat_ids_json='[-1001234567890]',
            ... )
        """
        try:
            promo_chat_ids = json.loads(promos_chat_ids_json)
            if not isinstance(promo_chat_ids, list):
                raise ValueError("PROMOS_CHAT_IDS_JSON must be a JSON array")

            return cls(
                bot=bot,
                promo_chat_ids=promo_chat_ids,
                db_session=db_session,
            )

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid PROMOS_CHAT_IDS_JSON: {e}") from e
