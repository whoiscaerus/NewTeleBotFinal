"""Structured audit logging for content distribution.

This module provides audit trail functionality for all content distributions,
logging success/failure of each message sent to each group.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)


class DistributionAuditLogger:
    """Audit logger for content distributions."""

    def __init__(self, db_session: Optional[AsyncSession] = None):
        """Initialize the audit logger.

        Args:
            db_session: Optional database session for logging to DB.
        """
        self.db_session = db_session
        self.logger = logger

    async def log_distribution(
        self,
        distribution_id: str,
        keywords: list[str],
        matched_groups: dict[str, list[int]],
        messages_sent: int,
        messages_failed: int,
        results: dict[str, list[dict[str, Any]]],
    ) -> bool:
        """Log a distribution event to the database.

        Args:
            distribution_id: Unique distribution ID.
            keywords: Keywords used for distribution.
            matched_groups: Groups that matched the keywords.
            messages_sent: Count of successful sends.
            messages_failed: Count of failed sends.
            results: Detailed results per keyword.

        Returns:
            True if logged successfully, False otherwise.

        Example:
            >>> logger = DistributionAuditLogger(db_session)
            >>> success = await logger.log_distribution(
            ...     distribution_id="123e4567-e89b-12d3-a456-426614174000",
            ...     keywords=["gold"],
            ...     matched_groups={"gold": [-1001234567890]},
            ...     messages_sent=1,
            ...     messages_failed=0,
            ...     results={"gold": [{"chat_id": -1001234567890, "message_id": 123, "success": True}]},
            ... )
        """
        if not self.db_session:
            self.logger.warning("No database session available for logging")
            return False

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
            self.db_session.add(audit_log)
            await self.db_session.commit()

            self.logger.info(
                "Distribution logged to audit trail",
                extra={
                    "distribution_id": distribution_id,
                    "messages_sent": messages_sent,
                    "messages_failed": messages_failed,
                },
            )
            return True

        except Exception as e:
            self.logger.error(
                "Failed to log distribution",
                extra={"distribution_id": distribution_id, "error": str(e)},
                exc_info=True,
            )
            return False

    async def get_distribution_log(
        self,
        distribution_id: str,
    ) -> Optional[dict[str, Any]]:
        """Retrieve a distribution log by ID.

        Args:
            distribution_id: The distribution ID.

        Returns:
            Dictionary with log details, or None if not found.
        """
        if not self.db_session:
            return None

        try:
            from backend.app.telegram.models import DistributionAuditLog

            stmt = select(DistributionAuditLog).where(
                DistributionAuditLog.id == distribution_id
            )
            result = await self.db_session.execute(stmt)
            log = result.scalar_one_or_none()

            if log:
                return {
                    "id": log.id,
                    "keywords": log.keywords,
                    "matched_groups": log.matched_groups,
                    "messages_sent": log.messages_sent,
                    "messages_failed": log.messages_failed,
                    "results": log.results,
                    "created_at": log.created_at.isoformat(),
                }
            return None

        except Exception as e:
            self.logger.error(
                "Failed to retrieve distribution log",
                extra={"distribution_id": distribution_id, "error": str(e)},
                exc_info=True,
            )
            return None

    async def get_distributions_by_keyword(
        self,
        keyword: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get recent distributions for a keyword.

        Args:
            keyword: The keyword.
            limit: Maximum results to return.

        Returns:
            List of distribution logs.
        """
        if not self.db_session:
            return []

        try:
            from backend.app.telegram.models import DistributionAuditLog

            stmt = (
                select(DistributionAuditLog)
                .where(DistributionAuditLog.keywords.contains([keyword]))
                .order_by(DistributionAuditLog.created_at.desc())
                .limit(limit)
            )
            result = await self.db_session.execute(stmt)
            logs = result.scalars().all()

            return [
                {
                    "id": log.id,
                    "keywords": log.keywords,
                    "messages_sent": log.messages_sent,
                    "messages_failed": log.messages_failed,
                    "created_at": log.created_at.isoformat(),
                }
                for log in logs
            ]

        except Exception as e:
            self.logger.error(
                "Failed to retrieve distributions",
                extra={"keyword": keyword, "error": str(e)},
                exc_info=True,
            )
            return []

    async def get_summary_stats(self) -> dict[str, Any]:
        """Get summary statistics of all distributions.

        Returns:
            Dictionary with summary statistics.
        """
        if not self.db_session:
            return {}

        try:
            from sqlalchemy import func

            from backend.app.telegram.models import DistributionAuditLog

            stmt = select(
                func.count(DistributionAuditLog.id).label("total_distributions"),
                func.sum(DistributionAuditLog.messages_sent).label("total_sent"),
                func.sum(DistributionAuditLog.messages_failed).label("total_failed"),
            )
            result = await self.db_session.execute(stmt)
            row = result.first()

            return {
                "total_distributions": row[0] or 0,
                "total_messages_sent": row[1] or 0,
                "total_messages_failed": row[2] or 0,
                "success_rate": (
                    (row[1] / (row[1] + row[2]) * 100)
                    if (row[1] or 0) + (row[2] or 0) > 0
                    else 0
                ),
            }

        except Exception as e:
            self.logger.error(
                "Failed to get summary stats", extra={"error": str(e)}, exc_info=True
            )
            return {}
