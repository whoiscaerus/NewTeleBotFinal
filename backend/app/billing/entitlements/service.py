"""Entitlements service for user permission and tier management."""

import logging
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.billing.entitlements.models import EntitlementType, UserEntitlement

logger = logging.getLogger(__name__)

# Standard tier to entitlements mapping
TIER_ENTITLEMENTS = {
    0: ["basic_access"],  # Free tier
    1: ["basic_access", "premium_signals"],  # Premium
    2: ["basic_access", "premium_signals", "copy_trading"],  # VIP
    3: ["basic_access", "premium_signals", "copy_trading", "vip_support"],  # Enterprise
}

# Web3 NFT-based entitlements (PR-102)
WEB3_ENTITLEMENTS = [
    "copy.mirror",  # NFT-gated copy trading access
    "strategy.premium",  # NFT-gated premium strategy access
]


class EntitlementService:
    """Service for managing user entitlements and permissions.

    Handles:
    - Checking user tier level
    - Granting/revoking entitlements
    - Checking feature access
    - Managing entitlement expiry
    """

    def __init__(self, db: AsyncSession):
        """Initialize entitlements service.

        Args:
            db: Database session
        """
        self.db = db

    async def get_user_tier(self, user_id: str) -> int:
        """Get user's tier level based on entitlements.

        Tier levels: 0=Free, 1=Premium, 2=VIP, 3=Enterprise

        Returns highest active entitlements tier.

        Args:
            user_id: User ID

        Returns:
            Tier level (0-3)
        """
        try:
            # Find highest tier-related entitlement
            query = select(UserEntitlement).where(
                and_(
                    UserEntitlement.user_id == user_id,
                    UserEntitlement.is_active == 1,
                )
            )
            result = await self.db.execute(query)
            entitlements = result.scalars().all()

            # Infer tier from entitlements
            # If has VIP support → tier 3
            # Else if has copy trading → tier 2
            # Else if has premium signals → tier 1
            # Else → tier 0 (free)
            entitlement_names = [
                await self._get_entitlement_name(e.entitlement_type_id)
                for e in entitlements
                if e.is_valid
            ]

            if "vip_support" in entitlement_names:
                return 3
            if "copy_trading" in entitlement_names:
                return 2
            if "premium_signals" in entitlement_names:
                return 1
            return 0

        except Exception as e:
            logger.error(f"Error getting user tier for {user_id}: {e}", exc_info=True)
            raise

    async def is_user_premium(self, user_id: str) -> bool:
        """Check if user has premium access.

        Args:
            user_id: User ID

        Returns:
            True if user has premium_signals entitlement
        """
        return await self.has_entitlement(user_id, "premium_signals")

    async def has_entitlement(self, user_id: str, entitlement_name: str) -> bool:
        """Check if user has specific entitlement.

        Args:
            user_id: User ID
            entitlement_name: Name of entitlement to check

        Returns:
            True if user has active entitlement
        """
        try:
            # Get entitlement type
            query = select(EntitlementType).where(
                EntitlementType.name == entitlement_name
            )
            result = await self.db.execute(query)
            entitlement_type = result.scalars().first()

            if not entitlement_type:
                logger.warning(f"Unknown entitlement: {entitlement_name}")
                return False

            # Check if user has this entitlement
            query = select(UserEntitlement).where(
                and_(
                    UserEntitlement.user_id == user_id,
                    UserEntitlement.entitlement_type_id == entitlement_type.id,
                    UserEntitlement.is_active == 1,
                )
            )
            result = await self.db.execute(query)
            entitlement = result.scalars().first()

            if not entitlement:
                return False

            # Check if expired
            if entitlement.is_expired:
                logger.info(
                    f"Entitlement expired for {user_id}: {entitlement_name}",
                    extra={"user_id": user_id},
                )
                return False

            return True

        except Exception as e:
            logger.error(
                f"Error checking entitlement for {user_id}: {e}",
                exc_info=True,
            )
            raise

    async def grant_entitlement(
        self,
        user_id: str,
        entitlement_name: str,
        duration_days: int | None = None,
    ) -> UserEntitlement:
        """Grant entitlement to user.

        If entitlement already exists, extend expiry.

        Args:
            user_id: User ID
            entitlement_name: Name of entitlement
            duration_days: Days until expiry (None = permanent)

        Returns:
            UserEntitlement object

        Raises:
            ValueError: If entitlement type not found
        """
        try:
            # Get entitlement type
            query = select(EntitlementType).where(
                EntitlementType.name == entitlement_name
            )
            result = await self.db.execute(query)
            entitlement_type = result.scalars().first()

            if not entitlement_type:
                raise ValueError(f"Unknown entitlement: {entitlement_name}")

            # Check if user already has this entitlement
            query = select(UserEntitlement).where(
                and_(
                    UserEntitlement.user_id == user_id,
                    UserEntitlement.entitlement_type_id == entitlement_type.id,
                )
            )
            result = await self.db.execute(query)
            existing = result.scalars().first()

            if existing:
                # Extend existing
                if duration_days:
                    existing.expires_at = datetime.utcnow() + timedelta(
                        days=duration_days
                    )
                else:
                    existing.expires_at = None
                existing.is_active = 1
                self.db.add(existing)
                logger.info(
                    f"Extended entitlement for {user_id}: {entitlement_name}",
                    extra={"user_id": user_id, "days": duration_days},
                )
            else:
                # Create new
                entitlement = UserEntitlement(
                    id=str(uuid4()),
                    user_id=user_id,
                    entitlement_type_id=entitlement_type.id,
                    expires_at=(
                        datetime.utcnow() + timedelta(days=duration_days)
                        if duration_days
                        else None
                    ),
                )
                self.db.add(entitlement)
                logger.info(
                    f"Granted entitlement to {user_id}: {entitlement_name}",
                    extra={"user_id": user_id, "days": duration_days},
                )
                existing = entitlement

            await self.db.commit()
            await self.db.refresh(existing)
            return existing

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error granting entitlement: {e}", exc_info=True)
            raise

    async def revoke_entitlement(self, user_id: str, entitlement_name: str) -> None:
        """Revoke entitlement from user.

        Args:
            user_id: User ID
            entitlement_name: Name of entitlement

        Raises:
            ValueError: If entitlement not found
        """
        try:
            # Get entitlement type
            query = select(EntitlementType).where(
                EntitlementType.name == entitlement_name
            )
            result = await self.db.execute(query)
            entitlement_type = result.scalars().first()

            if not entitlement_type:
                raise ValueError(f"Unknown entitlement: {entitlement_name}")

            # Find and revoke
            query = select(UserEntitlement).where(
                and_(
                    UserEntitlement.user_id == user_id,
                    UserEntitlement.entitlement_type_id == entitlement_type.id,
                    UserEntitlement.is_active == 1,
                )
            )
            result = await self.db.execute(query)
            entitlement = result.scalars().first()

            if not entitlement:
                raise ValueError(
                    f"User {user_id} does not have entitlement {entitlement_name}"
                )

            entitlement.is_active = 0
            self.db.add(entitlement)
            await self.db.commit()

            logger.info(
                f"Revoked entitlement from {user_id}: {entitlement_name}",
                extra={"user_id": user_id},
            )

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error revoking entitlement: {e}", exc_info=True)
            raise

    async def get_user_entitlements(self, user_id: str) -> list[UserEntitlement]:
        """Get all active entitlements for user.

        Args:
            user_id: User ID

        Returns:
            List of active UserEntitlement objects
        """
        try:
            query = select(UserEntitlement).where(
                and_(
                    UserEntitlement.user_id == user_id,
                    UserEntitlement.is_active == 1,
                )
            )
            result = await self.db.execute(query)
            entitlements = result.scalars().all()

            # Filter out expired
            valid = [e for e in entitlements if e.is_valid]

            logger.info(
                f"Loaded {len(valid)} entitlements for user {user_id}",
                extra={"user_id": user_id, "count": len(valid)},
            )
            return valid

        except Exception as e:
            logger.error(
                f"Error getting entitlements for {user_id}: {e}",
                exc_info=True,
            )
            raise

    async def _get_entitlement_name(self, entitlement_type_id: str) -> str | None:
        """Get entitlement name by ID (internal helper).

        Args:
            entitlement_type_id: Entitlement type ID

        Returns:
            Entitlement name or None
        """
        query = select(EntitlementType).where(EntitlementType.id == entitlement_type_id)
        result = await self.db.execute(query)
        entitlement_type = result.scalars().first()
        return entitlement_type.name if entitlement_type else None
