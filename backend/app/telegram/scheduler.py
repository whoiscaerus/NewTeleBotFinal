"""GuideBot scheduler: Periodic posting of guides to Telegram groups.

This module uses APScheduler to periodically post guides to configured chat groups
every 4 hours, with error handling and logging.

Example:
    >>> from telegram import Bot
    >>> from backend.app.telegram.handlers.guides import GuideHandler
    >>> from backend.app.telegram.scheduler import GuideScheduler
    >>>
    >>> bot = Bot(token="YOUR_TOKEN")
    >>> guide_handler = GuideHandler(bot=bot)
    >>> scheduler = GuideScheduler(
    ...     bot=bot,
    ...     guide_handler=guide_handler,
    ...     guide_chat_ids=[-1001234567890, -1001234567891],
    ... )
    >>> scheduler.start()  # Start posting every 4 hours
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


class GuideScheduler:
    """Scheduler for periodic guide posting."""

    # Default guides to post (can be extended)
    DEFAULT_GUIDES = [
        {
            "id": "guide_1",
            "title": "📚 Trading Fundamentals",
            "description": "Learn the basics of technical analysis and trading strategies.",
            "url": "https://www.telegraph.com/finance-trading-basics",
        },
        {
            "id": "guide_2",
            "title": "📊 Chart Analysis Guide",
            "description": "Master candlestick patterns, support/resistance levels, and trend analysis.",
            "url": "https://www.telegraph.com/chart-analysis-guide",
        },
        {
            "id": "guide_3",
            "title": "💰 Risk Management",
            "description": "Essential techniques for managing risk and protecting your capital.",
            "url": "https://www.telegraph.com/risk-management",
        },
        {
            "id": "guide_4",
            "title": "🎯 Entry and Exit Strategies",
            "description": "Learn proven entry and exit techniques for profitable trades.",
            "url": "https://www.telegraph.com/entry-exit-strategies",
        },
    ]

    def __init__(
        self,
        bot: Bot,
        guide_chat_ids: list[int],
        interval_hours: int = 4,
        db_session: Any | None = None,
    ):
        """Initialize the guide scheduler.

        Args:
            bot: The Telegram bot instance.
            guide_chat_ids: List of chat IDs to post guides to.
            interval_hours: Hours between guide posts (default: 4).
            db_session: Optional database session for logging.

        Example:
            >>> bot = Bot(token="YOUR_TOKEN")
            >>> scheduler = GuideScheduler(
            ...     bot=bot,
            ...     guide_chat_ids=[-1001234567890],
            ...     interval_hours=4,
            ... )
        """
        self.bot = bot
        self.guide_chat_ids = guide_chat_ids
        self.interval_hours = interval_hours
        self.db_session = db_session
        self.logger = logger
        self.scheduler = AsyncIOScheduler()
        self.is_running = False
        self.last_guide_index = 0

    def start(self) -> None:
        """Start the scheduler.

        Begins periodic guide posting. If scheduler is already running, does nothing.

        Example:
            >>> scheduler = GuideScheduler(bot=bot, guide_chat_ids=[-1001234567890])
            >>> scheduler.start()
            >>> print("Scheduler started")
        """
        if self.is_running:
            self.logger.warning("Scheduler already running")
            return

        try:
            # Add job to schedule
            self.scheduler.add_job(
                self._post_guide,
                trigger=IntervalTrigger(hours=self.interval_hours),
                id="guide_posting_job",
                name="Post guides to channels",
                replace_existing=True,
            )

            # Start scheduler
            self.scheduler.start()
            self.is_running = True

            self.logger.info(
                "Guide scheduler started",
                extra={
                    "interval_hours": self.interval_hours,
                    "chat_ids": self.guide_chat_ids,
                },
            )

        except Exception as e:
            self.logger.error(
                "Failed to start guide scheduler",
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
            self.logger.info("Guide scheduler stopped")
        except Exception as e:
            self.logger.error(
                "Error stopping scheduler", extra={"error": str(e)}, exc_info=True
            )

    async def _post_guide(self) -> None:
        """Post a guide to all configured chat IDs.

        This method is called by the scheduler at regular intervals.
        Selects a guide from DEFAULT_GUIDES, creates keyboard buttons,
        and posts to all configured channels.

        Errors in posting don't crash the job - they're logged and continue.
        """
        try:
            # Select guide (rotate through available guides)
            guide = self.DEFAULT_GUIDES[self.last_guide_index]
            self.last_guide_index = (self.last_guide_index + 1) % len(
                self.DEFAULT_GUIDES
            )

            # Create message with inline keyboard
            text = f"{guide['title']}\n\n{guide['description']}"
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton(text="📖 Read Guide", url=guide["url"])]]
            )

            posted_to_chats = []
            failed_chats = []

            # Post to all configured chats
            for chat_id in self.guide_chat_ids:
                try:
                    message = await self.bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        reply_markup=keyboard,
                        parse_mode=ParseMode.MARKDOWN_V2,
                    )

                    posted_to_chats.append(chat_id)

                    self.logger.info(
                        "Guide posted successfully",
                        extra={
                            "guide_id": guide["id"],
                            "chat_id": chat_id,
                            "message_id": message.message_id,
                        },
                    )

                    # Record telemetry
                    get_metrics().guides_posts_total.inc()

                except TelegramError as e:
                    failed_chats.append(chat_id)

                    self.logger.error(
                        "Failed to post guide to chat",
                        extra={
                            "guide_id": guide["id"],
                            "chat_id": chat_id,
                            "error": str(e),
                        },
                    )

                except Exception as e:
                    failed_chats.append(chat_id)

                    self.logger.error(
                        "Unexpected error posting guide",
                        extra={
                            "guide_id": guide["id"],
                            "chat_id": chat_id,
                            "error": str(e),
                        },
                        exc_info=True,
                    )

            # Log summary
            self.logger.info(
                "Guide posting cycle completed",
                extra={
                    "guide_id": guide["id"],
                    "posted_to": len(posted_to_chats),
                    "failed": len(failed_chats),
                    "posted_to_chats": posted_to_chats,
                    "failed_chats": failed_chats,
                },
            )

            # Log to database if session available
            if self.db_session is not None:
                await self._log_schedule_event(
                    guide_id=guide["id"],
                    posted_to=len(posted_to_chats),
                    failed=len(failed_chats),
                )

        except Exception as e:
            self.logger.error(
                "Error in guide posting job", extra={"error": str(e)}, exc_info=True
            )

    async def _log_schedule_event(
        self,
        guide_id: str,
        posted_to: int,
        failed: int,
    ) -> None:
        """Log schedule event to database.

        Args:
            guide_id: ID of posted guide.
            posted_to: Number of successful posts.
            failed: Number of failed posts.
        """
        try:
            from backend.app.telegram.models import GuideScheduleLog

            log_entry = GuideScheduleLog(
                id=str(__import__("uuid").uuid4()),
                guide_id=guide_id,
                posted_to=posted_to,
                failed=failed,
                created_at=datetime.utcnow(),
            )
            self.db_session.add(log_entry)
            await self.db_session.commit()

            self.logger.debug("Schedule event logged", extra={"guide_id": guide_id})

        except Exception as e:
            self.logger.error(
                "Failed to log schedule event",
                extra={"guide_id": guide_id, "error": str(e)},
                exc_info=True,
            )

    def is_running(self) -> bool:
        """Check if scheduler is running.

        Returns:
            True if running, False otherwise.
        """
        return self.is_running

    def get_next_run_time(self) -> datetime | None:
        """Get the next scheduled run time.

        Returns:
            datetime of next run, or None if not scheduled.
        """
        try:
            job = self.scheduler.get_job("guide_posting_job")
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
            job = self.scheduler.get_job("guide_posting_job")
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
        guides_chat_ids_json: str,
        db_session: Any | None = None,
    ) -> "GuideScheduler":
        """Create scheduler from environment configuration.

        Args:
            bot: Telegram bot instance.
            guides_chat_ids_json: JSON string with chat IDs: '[-1001234567890, -1001234567891]'
            db_session: Optional database session.

        Returns:
            GuideScheduler instance.

        Raises:
            ValueError: If JSON is invalid.

        Example:
            >>> scheduler = GuideScheduler.create_from_env(
            ...     bot=bot,
            ...     guides_chat_ids_json='[-1001234567890]',
            ... )
        """
        try:
            guide_chat_ids = json.loads(guides_chat_ids_json)
            if not isinstance(guide_chat_ids, list):
                raise ValueError("GUIDES_CHAT_IDS_JSON must be a JSON array")

            return cls(
                bot=bot,
                guide_chat_ids=guide_chat_ids,
                db_session=db_session,
            )

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid GUIDES_CHAT_IDS_JSON: {e}") from e
