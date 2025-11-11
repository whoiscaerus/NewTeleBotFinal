"""NFT Access minting service for tokenized feature access.

Issues non-transferable or time-locked tokens for strategy licensing.
Feature flag: NFT_ACCESS_ENABLED=false by default.
"""

from datetime import UTC, datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.audit.models import AuditLog
from backend.app.web3.models import NFTAccess, WalletLink


class NFTAccessService:
    """Service for minting/revoking NFT-based feature access.

    Security:
        - Validates wallet ownership before minting
        - Never gates critical features (additive only)
        - Audit logs all mint/revoke operations
        - Feature flag: NFT_ACCESS_ENABLED
    """

    def __init__(self, db: AsyncSession):
        """Initialize NFT access service.

        Args:
            db: Database session for queries
        """
        self.db = db

    async def mint(
        self,
        user_id: str,
        wallet_address: str,
        entitlement_key: str,
        expires_at: datetime | None = None,
        token_id: str | None = None,
        contract_address: str | None = None,
        chain_id: int = 1,
        meta: dict | None = None,
        actor_id: str | None = None,
        actor_role: str | None = None,
    ) -> NFTAccess:
        """Mint NFT access token for a user.

        Args:
            user_id: User ID to grant access
            wallet_address: Wallet address to bind NFT to
            entitlement_key: Feature key (e.g., "copy.mirror")
            expires_at: Expiration timestamp (None = permanent)
            token_id: On-chain token ID (optional)
            contract_address: NFT contract address (optional)
            chain_id: Blockchain chain ID
            meta: Additional metadata
            actor_id: ID of user performing mint (usually owner)
            actor_role: Role of actor (OWNER, ADMIN)

        Returns:
            NFTAccess: Created NFT access token

        Raises:
            ValueError: If wallet not linked to user or already has active NFT
        """
        # Validate wallet belongs to user
        result = await self.db.execute(
            select(WalletLink)
            .where(WalletLink.wallet_address == wallet_address)
            .where(WalletLink.user_id == user_id)
            .where(WalletLink.is_active == 1)
        )
        wallet_link = result.scalar_one_or_none()

        if not wallet_link:
            raise ValueError(
                f"Wallet {wallet_address} not linked to user {user_id} or inactive"
            )

        # Check for existing active NFT for this entitlement
        existing = await self.db.execute(
            select(NFTAccess)
            .where(NFTAccess.user_id == user_id)
            .where(NFTAccess.entitlement_key == entitlement_key)
            .where(NFTAccess.is_active == 1)
        )
        if existing.scalar_one_or_none():
            raise ValueError(
                f"User {user_id} already has active NFT for {entitlement_key}"
            )

        # Create NFT access
        nft = NFTAccess(
            id=str(uuid4()),
            user_id=user_id,
            wallet_address=wallet_address,
            entitlement_key=entitlement_key,
            token_id=token_id,
            contract_address=contract_address,
            chain_id=chain_id,
            is_active=1,
            minted_at=datetime.now(UTC),
            expires_at=expires_at,
            meta=meta or {},
        )

        self.db.add(nft)
        await self.db.flush()

        # Audit log
        audit = AuditLog(
            id=str(uuid4()),
            actor_id=actor_id or user_id,
            actor_role=actor_role,
            action="web3.nft_mint",
            target="nft_access",
            target_id=nft.id,
            status="success",
            meta={
                "user_id": user_id,
                "wallet_address": wallet_address,
                "entitlement_key": entitlement_key,
                "expires_at": expires_at.isoformat() if expires_at else None,
            },
        )
        self.db.add(audit)
        await self.db.commit()

        return nft

    async def revoke(
        self,
        nft_id: str,
        reason: str,
        actor_id: str,
        actor_role: str = "OWNER",
    ) -> NFTAccess:
        """Revoke an NFT access token.

        Args:
            nft_id: NFT access ID to revoke
            reason: Reason for revocation
            actor_id: ID of user performing revocation
            actor_role: Role of actor (OWNER, ADMIN)

        Returns:
            NFTAccess: Revoked NFT access token

        Raises:
            ValueError: If NFT not found
        """
        # Find NFT
        result = await self.db.execute(select(NFTAccess).where(NFTAccess.id == nft_id))
        nft = result.scalar_one_or_none()

        if not nft:
            raise ValueError(f"NFT access {nft_id} not found")

        # Revoke
        nft.is_active = 0
        nft.revoked_at = datetime.now(UTC)
        nft.revoke_reason = reason
        await self.db.flush()

        # Audit log
        audit = AuditLog(
            id=str(uuid4()),
            actor_id=actor_id,
            actor_role=actor_role,
            action="web3.nft_revoke",
            target="nft_access",
            target_id=nft.id,
            status="success",
            meta={
                "user_id": nft.user_id,
                "entitlement_key": nft.entitlement_key,
                "reason": reason,
            },
        )
        self.db.add(audit)
        await self.db.commit()

        return nft

    async def check_access(
        self, wallet_address: str, entitlement_key: str
    ) -> tuple[bool, NFTAccess | None]:
        """Check if a wallet has active NFT access for an entitlement.

        Args:
            wallet_address: Wallet address to check
            entitlement_key: Feature key to check

        Returns:
            Tuple of (has_access: bool, nft: Optional[NFTAccess])
        """
        result = await self.db.execute(
            select(NFTAccess)
            .where(NFTAccess.wallet_address == wallet_address)
            .where(NFTAccess.entitlement_key == entitlement_key)
            .where(NFTAccess.is_active == 1)
        )
        nft = result.scalar_one_or_none()

        if not nft:
            return False, None

        # Check expiration
        if nft.is_expired:
            return False, nft

        return True, nft

    async def get_user_nfts(
        self, user_id: str, active_only: bool = True
    ) -> list[NFTAccess]:
        """Get all NFT access tokens for a user.

        Args:
            user_id: User ID
            active_only: If True, only return active/non-expired NFTs

        Returns:
            List of NFT access tokens
        """
        query = select(NFTAccess).where(NFTAccess.user_id == user_id)

        if active_only:
            query = query.where(NFTAccess.is_active == 1)

        result = await self.db.execute(query)
        nfts = list(result.scalars().all())

        # Filter expired if active_only
        if active_only:
            nfts = [nft for nft in nfts if not nft.is_expired]

        return nfts

    async def get_wallet_nfts(
        self, wallet_address: str, active_only: bool = True
    ) -> list[NFTAccess]:
        """Get all NFT access tokens for a wallet address.

        Args:
            wallet_address: Wallet address
            active_only: If True, only return active/non-expired NFTs

        Returns:
            List of NFT access tokens
        """
        query = select(NFTAccess).where(NFTAccess.wallet_address == wallet_address)

        if active_only:
            query = query.where(NFTAccess.is_active == 1)

        result = await self.db.execute(query)
        nfts = list(result.scalars().all())

        # Filter expired if active_only
        if active_only:
            nfts = [nft for nft in nfts if not nft.is_expired]

        return nfts

    async def extend_expiry(
        self,
        nft_id: str,
        new_expires_at: datetime,
        actor_id: str,
        actor_role: str = "OWNER",
    ) -> NFTAccess:
        """Extend expiration of an NFT access token.

        Args:
            nft_id: NFT access ID
            new_expires_at: New expiration timestamp
            actor_id: ID of user performing extension
            actor_role: Role of actor (OWNER, ADMIN)

        Returns:
            NFTAccess: Updated NFT access token

        Raises:
            ValueError: If NFT not found or inactive
        """
        result = await self.db.execute(select(NFTAccess).where(NFTAccess.id == nft_id))
        nft = result.scalar_one_or_none()

        if not nft:
            raise ValueError(f"NFT access {nft_id} not found")

        if not nft.is_active:
            raise ValueError(f"NFT access {nft_id} is revoked")

        old_expires = nft.expires_at
        nft.expires_at = new_expires_at
        await self.db.flush()

        # Audit log
        audit = AuditLog(
            id=str(uuid4()),
            actor_id=actor_id,
            actor_role=actor_role,
            action="web3.nft_extend",
            target="nft_access",
            target_id=nft.id,
            status="success",
            meta={
                "user_id": nft.user_id,
                "entitlement_key": nft.entitlement_key,
                "old_expires_at": old_expires.isoformat() if old_expires else None,
                "new_expires_at": new_expires_at.isoformat(),
            },
        )
        self.db.add(audit)
        await self.db.commit()

        return nft
