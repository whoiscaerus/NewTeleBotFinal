"""Marketing clicks store: Persistent tracking of user CTA interactions.

This module tracks when users click on marketing CTAs, enabling conversion
tracking and analytics for marketing effectiveness.

Example:
    >>> from backend.app.marketing.clicks_store import ClicksStore
    >>>
    >>> store = ClicksStore(db_session=db_session)
    >>> await store.log_click(user_id="123", promo_id="promo_1", cta_text="Upgrade")
    >>> clicks = await store.get_user_clicks(user_id="123")
"""

import logging
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.observability.metrics import get_metrics

logger = logging.getLogger(__name__)


class ClicksStore:
    """Store for tracking marketing CTA clicks."""

    def __init__(self, db_session: AsyncSession):
        """Initialize the clicks store.

        Args:
            db_session: Async database session.

        Example:
            >>> store = ClicksStore(db_session=db_session)
        """
        self.db_session = db_session
        self.logger = logger

    async def log_click(
        self,
        user_id: str,
        promo_id: str,
        cta_text: str,
        chat_id: Optional[int] = None,
        message_id: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        """Log a CTA click for tracking and analytics.

        Args:
            user_id: Telegram user ID.
            promo_id: ID of the promo that was clicked.
            cta_text: Text of the CTA button clicked.
            chat_id: Optional Telegram chat ID.
            message_id: Optional Telegram message ID.
            metadata: Optional additional metadata (JSON).

        Returns:
            ID of the logged click.

        Example:
            >>> click_id = await store.log_click(
            ...     user_id="123456789",
            ...     promo_id="promo_1",
            ...     cta_text="Upgrade to Premium",
            ...     metadata={"conversion": "pending"}
            ... )
        """
        try:
            from backend.app.marketing.models import MarketingClick

            click = MarketingClick(
                id=str(uuid4()),
                user_id=user_id,
                promo_id=promo_id,
                cta_text=cta_text,
                chat_id=chat_id,
                message_id=message_id,
                metadata=metadata or {},
                clicked_at=datetime.utcnow(),
            )

            self.db_session.add(click)
            await self.db_session.commit()

            self.logger.info(
                "CTA click logged",
                extra={
                    "click_id": click.id,
                    "user_id": user_id,
                    "promo_id": promo_id,
                    "cta_text": cta_text,
                },
            )

            # Record telemetry
            get_metrics().marketing_clicks_total.inc()

            return click.id

        except Exception as e:
            self.logger.error(
                "Failed to log CTA click",
                extra={
                    "user_id": user_id,
                    "promo_id": promo_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

    async def get_user_clicks(
        self,
        user_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get all clicks for a user.

        Args:
            user_id: Telegram user ID.
            limit: Maximum number of clicks to return.

        Returns:
            List of click records.

        Example:
            >>> clicks = await store.get_user_clicks(user_id="123456789")
            >>> for click in clicks:
            ...     print(f"{click['promo_id']}: {click['cta_text']}")
        """
        try:
            from backend.app.marketing.models import MarketingClick

            query = (
                select(MarketingClick)
                .where(MarketingClick.user_id == user_id)
                .order_by(MarketingClick.clicked_at.desc())
                .limit(limit)
            )

            result = await self.db_session.execute(query)
            clicks = result.scalars().all()

            return [
                {
                    "id": click.id,
                    "user_id": click.user_id,
                    "promo_id": click.promo_id,
                    "cta_text": click.cta_text,
                    "clicked_at": click.clicked_at.isoformat(),
                    "metadata": click.metadata or {},
                }
                for click in clicks
            ]

        except Exception as e:
            self.logger.error(
                "Failed to get user clicks",
                extra={"user_id": user_id, "error": str(e)},
                exc_info=True,
            )
            raise

    async def get_promo_clicks(
        self,
        promo_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get all clicks for a promo.

        Args:
            promo_id: ID of the promo.
            limit: Maximum number of clicks to return.

        Returns:
            List of click records.

        Example:
            >>> clicks = await store.get_promo_clicks(promo_id="promo_1")
            >>> print(f"Total clicks: {len(clicks)}")
        """
        try:
            from backend.app.marketing.models import MarketingClick

            query = (
                select(MarketingClick)
                .where(MarketingClick.promo_id == promo_id)
                .order_by(MarketingClick.clicked_at.desc())
                .limit(limit)
            )

            result = await self.db_session.execute(query)
            clicks = result.scalars().all()

            return [
                {
                    "id": click.id,
                    "user_id": click.user_id,
                    "promo_id": click.promo_id,
                    "cta_text": click.cta_text,
                    "clicked_at": click.clicked_at.isoformat(),
                    "metadata": click.metadata or {},
                }
                for click in clicks
            ]

        except Exception as e:
            self.logger.error(
                "Failed to get promo clicks",
                extra={"promo_id": promo_id, "error": str(e)},
                exc_info=True,
            )
            raise

    async def get_click_count(self, promo_id: str) -> int:
        """Get total click count for a promo.

        Args:
            promo_id: ID of the promo.

        Returns:
            Number of clicks for this promo.

        Example:
            >>> count = await store.get_click_count(promo_id="promo_1")
            >>> print(f"Promo received {count} clicks")
        """
        try:
            from backend.app.marketing.models import MarketingClick

            query = select(MarketingClick).where(MarketingClick.promo_id == promo_id)
            result = await self.db_session.execute(query)
            return len(result.scalars().all())

        except Exception as e:
            self.logger.error(
                "Failed to get click count",
                extra={"promo_id": promo_id, "error": str(e)},
                exc_info=True,
            )
            return 0

    async def get_conversion_rate(self, promo_id: str) -> float:
        """Get conversion rate estimate for a promo.

        Requires clicks to be tagged with conversion metadata.

        Args:
            promo_id: ID of the promo.

        Returns:
            Conversion rate as percentage (0-100).

        Example:
            >>> rate = await store.get_conversion_rate(promo_id="promo_1")
            >>> print(f"Conversion rate: {rate:.1f}%")
        """
        try:
            from backend.app.marketing.models import MarketingClick

            # Get all clicks for this promo
            all_clicks_query = select(MarketingClick).where(
                MarketingClick.promo_id == promo_id
            )
            all_result = await self.db_session.execute(all_clicks_query)
            all_clicks = all_result.scalars().all()

            if not all_clicks:
                return 0.0

            # Count conversions (metadata.conversion == "completed")
            conversions = sum(
                1
                for click in all_clicks
                if click.metadata and click.metadata.get("conversion") == "completed"
            )

            return (conversions / len(all_clicks)) * 100.0

        except Exception as e:
            self.logger.error(
                "Failed to get conversion rate",
                extra={"promo_id": promo_id, "error": str(e)},
                exc_info=True,
            )
            return 0.0

    async def update_click_metadata(
        self,
        click_id: str,
        metadata: dict[str, Any],
    ) -> None:
        """Update metadata for a recorded click (e.g., mark as converted).

        Args:
            click_id: ID of the click record.
            metadata: Metadata to update/merge.

        Example:
            >>> await store.update_click_metadata(
            ...     click_id=click_id,
            ...     metadata={"conversion": "completed", "plan": "premium"}
            ... )
        """
        try:
            from backend.app.marketing.models import MarketingClick

            query = select(MarketingClick).where(MarketingClick.id == click_id)
            result = await self.db_session.execute(query)
            click = result.scalar_one_or_none()

            if not click:
                self.logger.warning(f"Click not found: {click_id}")
                return

            # Merge metadata
            click.metadata = {**(click.metadata or {}), **metadata}
            await self.db_session.commit()

            self.logger.info(
                "Click metadata updated",
                extra={"click_id": click_id, "metadata": metadata},
            )

        except Exception as e:
            self.logger.error(
                "Failed to update click metadata",
                extra={"click_id": click_id, "error": str(e)},
                exc_info=True,
            )
            raise
