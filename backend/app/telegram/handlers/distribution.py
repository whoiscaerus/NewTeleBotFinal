"""Content distribution handler: Admin posts content to Telegram groups by keyword.

This module implements the ContentDistributor which allows admins to post content once
and have it automatically distributed to the correct Telegram groups based on keywords
(gold, crypto, sp500, etc.).

Flow:
    1. Admin submits content with keywords ["gold", "crypto"]
    2. ContentDistributor finds all groups configured for those keywords
    3. Distributes the message to all matched groups
    4. Logs each distribution (success/failure) to audit trail
    5. Returns detailed report with confirmation
"""

import logging
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from backend.app.observability.metrics import get_metrics

logger = logging.getLogger(__name__)


class ContentDistributor:
    """Distributes admin content to Telegram groups based on keywords."""

    def __init__(
        self,
        bot: Bot,
        group_map: Optional[dict[str, list[int]]] = None,
    ):
        """Initialize the content distributor.

        Args:
            bot: The Telegram bot instance.
            group_map: Mapping of keywords to group chat IDs.
                      Example: {"gold": [-1001234567890], "crypto": [-1001234567891]}

        Example:
            >>> from telegram import Bot
            >>> bot = Bot(token="YOUR_TOKEN")
            >>> group_map = {"gold": [-1001234567890], "crypto": [-1001234567891]}
            >>> distributor = ContentDistributor(bot, group_map)
        """
        self.bot = bot
        self.logger = logger
        self.group_map = group_map or {}

    def add_keyword_mapping(self, keyword: str, group_ids: list[int]) -> None:
        """Add or update keyword-to-groups mapping.

        Args:
            keyword: The keyword (case-insensitive).
            group_ids: List of Telegram group chat IDs.

        Example:
            >>> distributor.add_keyword_mapping("gold", [-1001234567890])
        """
        keyword_lower = keyword.lower().strip()
        self.group_map[keyword_lower] = group_ids
        self.logger.info(
            "Keyword mapping added/updated",
            extra={
                "keyword": keyword_lower,
                "group_count": len(group_ids),
            },
        )

    def find_matching_groups(
        self,
        text: str,
        keywords: list[str],
    ) -> dict[str, list[int]]:
        """Find groups matching the provided keywords.

        Args:
            text: The content text (used for validation/logging).
            keywords: List of keywords to match (case-insensitive).

        Returns:
            Dictionary mapping keyword -> list of group IDs.

        Example:
            >>> matched = distributor.find_matching_groups(
            ...     "Gold update",
            ...     ["gold", "market"]
            ... )
            >>> # Returns: {"gold": [-1001234567890]}
        """
        matched_groups: dict[str, list[int]] = {}

        for keyword in keywords:
            keyword_lower = keyword.lower().strip()

            if keyword_lower in self.group_map:
                group_ids = self.group_map[keyword_lower]
                matched_groups[keyword_lower] = group_ids
                self.logger.debug(
                    "Keyword matched",
                    extra={
                        "keyword": keyword_lower,
                        "group_count": len(group_ids),
                    },
                )
            else:
                self.logger.debug(
                    "Keyword has no configured groups", extra={"keyword": keyword_lower}
                )

        return matched_groups

    async def distribute_content(
        self,
        text: str,
        keywords: list[str],
        parse_mode: str = ParseMode.MARKDOWN_V2,
        db_session: Optional[AsyncSession] = None,
    ) -> dict[str, Any]:
        """Distribute admin content to groups matching keywords.

        This is the main distribution method. It validates input, finds matching
        groups, sends messages to all groups, logs results, and returns a detailed
        report.

        Args:
            text: The content to distribute.
            keywords: Keywords to match against groups.
            parse_mode: Telegram parse mode (MARKDOWN_V2, HTML, or None).
            db_session: Database session for audit logging (optional).

        Returns:
            Dictionary with distribution results:
            {
                "success": bool,
                "distribution_id": str,
                "keywords_requested": List[str],
                "keywords_matched": Dict[str, int],
                "groups_targeted": int,
                "messages_sent": int,
                "messages_failed": int,
                "results": Dict,
                "timestamp": str,
                "error": Optional[str]
            }

        Example:
            >>> result = await distributor.distribute_content(
            ...     text="📊 GOLD is up 2.5% today!",
            ...     keywords=["gold"],
            ... )
            >>> print(f"Sent to {result['groups_targeted']} groups")
        """
        distribution_id = str(uuid4())
        timestamp = datetime.utcnow().isoformat()
        results: dict[str, list[dict[str, Any]]] = {}
        messages_sent = 0
        messages_failed = 0

        try:
            # Validate input
            if not text or not text.strip():
                error_msg = "Content text cannot be empty"
                self.logger.warning(
                    error_msg, extra={"distribution_id": distribution_id}
                )
                return {
                    "success": False,
                    "distribution_id": distribution_id,
                    "keywords_requested": keywords,
                    "keywords_matched": {},
                    "groups_targeted": 0,
                    "messages_sent": 0,
                    "messages_failed": 0,
                    "results": {},
                    "timestamp": timestamp,
                    "error": error_msg,
                }

            if not keywords or len(keywords) == 0:
                error_msg = "At least one keyword must be provided"
                self.logger.warning(
                    error_msg, extra={"distribution_id": distribution_id}
                )
                return {
                    "success": False,
                    "distribution_id": distribution_id,
                    "keywords_requested": keywords,
                    "keywords_matched": {},
                    "groups_targeted": 0,
                    "messages_sent": 0,
                    "messages_failed": 0,
                    "results": {},
                    "timestamp": timestamp,
                    "error": error_msg,
                }

            # Find matching groups
            matched_groups = self.find_matching_groups(text, keywords)

            if not matched_groups:
                error_msg = "No groups matched the provided keywords"
                self.logger.warning(
                    error_msg,
                    extra={"distribution_id": distribution_id, "keywords": keywords},
                )
                return {
                    "success": False,
                    "distribution_id": distribution_id,
                    "keywords_requested": keywords,
                    "keywords_matched": {},
                    "groups_targeted": 0,
                    "messages_sent": 0,
                    "messages_failed": 0,
                    "results": {},
                    "timestamp": timestamp,
                    "error": error_msg,
                }

            # Count total unique groups
            all_group_ids: set[int] = set()
            for group_ids in matched_groups.values():
                all_group_ids.update(group_ids)
            groups_targeted = len(all_group_ids)

            self.logger.info(
                "Starting content distribution",
                extra={
                    "distribution_id": distribution_id,
                    "keywords": keywords,
                    "groups_targeted": groups_targeted,
                },
            )

            # Send to all matched groups
            for keyword, group_ids in matched_groups.items():
                results[keyword] = []

                for chat_id in group_ids:
                    try:
                        # Send message
                        message = await self.bot.send_message(
                            chat_id=chat_id,
                            text=text,
                            parse_mode=parse_mode,
                        )

                        result_entry = {
                            "chat_id": chat_id,
                            "message_id": message.message_id,
                            "success": True,
                        }
                        results[keyword].append(result_entry)
                        messages_sent += 1

                        self.logger.info(
                            "Message sent successfully",
                            extra={
                                "distribution_id": distribution_id,
                                "chat_id": chat_id,
                                "message_id": message.message_id,
                                "keyword": keyword,
                            },
                        )

                        # Record telemetry
                        get_metrics().distribution_messages_total.labels(
                            channel=keyword
                        ).inc()

                    except TelegramError as e:
                        result_entry = {
                            "chat_id": chat_id,
                            "error": str(e),
                            "success": False,
                        }
                        results[keyword].append(result_entry)
                        messages_failed += 1

                        self.logger.error(
                            "Failed to send message",
                            extra={
                                "distribution_id": distribution_id,
                                "chat_id": chat_id,
                                "keyword": keyword,
                                "error": str(e),
                            },
                        )

                    except Exception as e:
                        result_entry = {
                            "chat_id": chat_id,
                            "error": str(e),
                            "success": False,
                        }
                        results[keyword].append(result_entry)
                        messages_failed += 1

                        self.logger.error(
                            "Unexpected error sending message",
                            extra={
                                "distribution_id": distribution_id,
                                "chat_id": chat_id,
                                "keyword": keyword,
                            },
                            exc_info=True,
                        )

            # Log to DB if session provided
            if db_session is not None:
                await self._log_distribution_to_db(
                    db_session,
                    distribution_id,
                    keywords,
                    matched_groups,
                    messages_sent,
                    messages_failed,
                    results,
                )

            success = messages_failed == 0

            self.logger.info(
                "Distribution completed",
                extra={
                    "distribution_id": distribution_id,
                    "messages_sent": messages_sent,
                    "messages_failed": messages_failed,
                    "success": success,
                },
            )

            return {
                "success": success,
                "distribution_id": distribution_id,
                "keywords_requested": keywords,
                "keywords_matched": {k: len(v) for k, v in matched_groups.items()},
                "groups_targeted": groups_targeted,
                "messages_sent": messages_sent,
                "messages_failed": messages_failed,
                "results": results,
                "timestamp": timestamp,
                "error": None,
            }

        except Exception as e:
            self.logger.error(
                "Distribution failed",
                extra={"distribution_id": distribution_id, "error": str(e)},
                exc_info=True,
            )
            return {
                "success": False,
                "distribution_id": distribution_id,
                "keywords_requested": keywords,
                "keywords_matched": {},
                "groups_targeted": 0,
                "messages_sent": 0,
                "messages_failed": 0,
                "results": {},
                "timestamp": timestamp,
                "error": str(e),
            }

    async def _log_distribution_to_db(
        self,
        db_session: AsyncSession,
        distribution_id: str,
        keywords: list[str],
        matched_groups: dict[str, list[int]],
        messages_sent: int,
        messages_failed: int,
        results: dict[str, list[dict[str, Any]]],
    ) -> None:
        """Log distribution to database for audit trail.

        Args:
            db_session: Database session.
            distribution_id: Unique distribution ID.
            keywords: Keywords used.
            matched_groups: Matched groups.
            messages_sent: Count of successful sends.
            messages_failed: Count of failed sends.
            results: Detailed results.
        """
        try:
            from backend.app.telegram.models import DistributionAuditLog

            audit_log = DistributionAuditLog(
                id=distribution_id,
                keywords=keywords,
                matched_groups=matched_groups,
                messages_sent=messages_sent,
                messages_failed=messages_failed,
                results=results,
                created_at=datetime.utcnow(),
            )
            db_session.add(audit_log)
            await db_session.commit()

            self.logger.debug(
                "Distribution logged to audit trail",
                extra={"distribution_id": distribution_id},
            )
        except Exception as e:
            self.logger.error(
                "Failed to log to database",
                extra={"distribution_id": distribution_id, "error": str(e)},
                exc_info=True,
            )


# Alias for backward compatibility
MessageDistributor = ContentDistributor
