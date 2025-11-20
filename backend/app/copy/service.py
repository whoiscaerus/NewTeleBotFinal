"""
Copy Registry Service

Business logic for managing copy entries and resolving text.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.copy.models import CopyEntry, CopyStatus, CopyVariant
from backend.app.copy.schemas import CopyEntryCreate, CopyEntryUpdate, CopyVariantCreate

logger = logging.getLogger(__name__)


class CopyService:
    """Service for copy registry operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_entry(
        self, data: CopyEntryCreate, user_id: str | None = None
    ) -> CopyEntry:
        """
        Create a new copy entry with variants.

        Args:
            data: Copy entry creation data
            user_id: ID of user creating entry

        Returns:
            Created CopyEntry

        Raises:
            ValueError: If key already exists
        """
        # Check for duplicate key
        existing = await self.get_entry_by_key(data.key)
        if existing:
            raise ValueError(f"Copy entry with key '{data.key}' already exists")

        # Create entry
        entry = CopyEntry(
            key=data.key,
            type=data.type,
            description=data.description,
            entry_metadata=data.metadata,
            created_by=user_id,
            updated_by=user_id,
        )

        # Create variants
        for variant_data in data.variants:
            variant = CopyVariant(
                locale=variant_data.locale,
                ab_group=variant_data.ab_group,
                is_control=variant_data.is_control,
                text=variant_data.text,
                variant_metadata=variant_data.metadata,
            )
            entry.variants.append(variant)

        self.db.add(entry)
        await self.db.commit()
        await self.db.refresh(entry)

        logger.info(
            f"Created copy entry: {entry.key}",
            extra={
                "copy_key": entry.key,
                "copy_type": entry.type,
                "variant_count": len(entry.variants),
            },
        )

        return entry

    async def get_entry(self, entry_id: str) -> CopyEntry | None:
        """Get copy entry by ID."""
        result = await self.db.execute(
            select(CopyEntry)
            .where(CopyEntry.id == entry_id)
            .options(selectinload(CopyEntry.variants))
        )
        return result.scalars().first()

    async def get_entry_by_key(self, key: str) -> CopyEntry | None:
        """Get copy entry by key."""
        result = await self.db.execute(
            select(CopyEntry)
            .where(CopyEntry.key == key)
            .options(selectinload(CopyEntry.variants))
        )
        return result.scalars().first()

    async def list_entries(
        self,
        type: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CopyEntry]:
        """List copy entries with filters."""
        query = select(CopyEntry).options(selectinload(CopyEntry.variants))

        if type:
            query = query.where(CopyEntry.type == type)
        if status:
            query = query.where(CopyEntry.status == status)

        query = query.limit(limit).offset(offset).order_by(CopyEntry.key)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_entry(
        self, entry_id: str, data: CopyEntryUpdate, user_id: str | None = None
    ) -> CopyEntry | None:
        """Update copy entry."""
        entry = await self.get_entry(entry_id)
        if not entry:
            return None

        if data.type is not None:
            entry.type = data.type
        if data.status is not None:
            entry.status = data.status
        if data.description is not None:
            entry.description = data.description
        if data.metadata is not None:
            entry.entry_metadata = data.metadata

        entry.updated_by = user_id

        await self.db.commit()
        await self.db.refresh(entry)

        logger.info(
            f"Updated copy entry: {entry.key}",
            extra={"copy_key": entry.key, "updated_by": user_id},
        )

        return entry

    async def add_variant(
        self, entry_id: str, variant_data: CopyVariantCreate
    ) -> CopyVariant | None:
        """Add variant to existing entry."""
        entry = await self.get_entry(entry_id)
        if not entry:
            return None

        variant = CopyVariant(
            entry_id=entry_id,
            locale=variant_data.locale,
            ab_group=variant_data.ab_group,
            is_control=variant_data.is_control,
            text=variant_data.text,
            variant_metadata=variant_data.metadata,
        )

        self.db.add(variant)
        await self.db.commit()
        await self.db.refresh(variant)

        logger.info(
            f"Added variant to copy entry: {entry.key}",
            extra={
                "copy_key": entry.key,
                "locale": variant.locale,
                "ab_group": variant.ab_group,
            },
        )

        return variant

    async def resolve_copy(
        self,
        keys: list[str],
        locale: str = "en",
        ab_group: str | None = None,
        record_impression: bool = False,
    ) -> tuple[dict[str, str], list[str]]:
        """
        Resolve copy text for given keys.

        Args:
            keys: List of copy keys to resolve
            locale: Desired locale
            ab_group: A/B test group
            record_impression: Whether to record impressions

        Returns:
            Tuple of (resolved_copy_dict, missing_keys)
        """
        # Load entries by keys (published only)
        result = await self.db.execute(
            select(CopyEntry)
            .where(CopyEntry.key.in_(keys))
            .where(CopyEntry.status == CopyStatus.PUBLISHED)
            .options(selectinload(CopyEntry.variants))
        )
        entries = {entry.key: entry for entry in result.scalars().all()}

        resolved = {}
        missing = []

        for key in keys:
            entry = entries.get(key)
            if not entry:
                missing.append(key)
                logger.warning(f"Copy key not found: {key}")
                continue

            # Get variant
            variant = entry.get_variant(locale=locale, ab_group=ab_group)
            if not variant:
                missing.append(key)
                logger.warning(
                    f"No variant found for key: {key} (locale={locale}, ab_group={ab_group})"
                )
                continue

            resolved[key] = variant.text

            # Record impression if requested
            if record_impression:
                variant.record_impression()

        # Commit impression updates
        if record_impression:
            await self.db.commit()

        return resolved, missing

    async def record_impression(
        self, key: str, locale: str = "en", ab_group: str | None = None
    ) -> bool:
        """Record impression for copy variant."""
        entry = await self.get_entry_by_key(key)
        if not entry:
            return False

        variant = entry.get_variant(locale=locale, ab_group=ab_group)
        if not variant:
            return False

        variant.record_impression()
        await self.db.commit()

        return True

    async def record_conversion(
        self, key: str, locale: str = "en", ab_group: str | None = None
    ) -> bool:
        """Record conversion for copy variant."""
        entry = await self.get_entry_by_key(key)
        if not entry:
            return False

        variant = entry.get_variant(locale=locale, ab_group=ab_group)
        if not variant:
            return False

        variant.record_conversion()
        await self.db.commit()

        logger.info(
            f"Recorded conversion for copy: {key}",
            extra={
                "copy_key": key,
                "locale": locale,
                "ab_group": ab_group,
                "conversion_rate": variant.conversion_rate,
            },
        )

        return True

    async def delete_entry(self, entry_id: str) -> bool:
        """Delete copy entry (and cascade variants)."""
        entry = await self.get_entry(entry_id)
        if not entry:
            return False

        await self.db.delete(entry)
        await self.db.commit()

        logger.info(f"Deleted copy entry: {entry.key}", extra={"copy_key": entry.key})

        return True
