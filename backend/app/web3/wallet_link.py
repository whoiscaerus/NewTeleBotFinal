"""Wallet linking service for Web3 wallet ↔ user account mapping.

Implements signature verification (SIWE-compatible or simple message signing).
"""

import hashlib
import re
from datetime import UTC, datetime
from typing import Optional
from uuid import uuid4

from eth_account.messages import encode_defunct
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from web3 import Web3

from backend.app.audit.models import AuditLog
from backend.app.web3.models import WalletLink


class WalletLinkService:
    """Service for linking Web3 wallets to user accounts.

    Security:
        - Validates Ethereum address format
        - Verifies ECDSA signature
        - Prevents duplicate wallet links
        - Audit logs all link/revoke operations
    """

    def __init__(self, db: AsyncSession):
        """Initialize wallet link service.

        Args:
            db: Database session for queries
        """
        self.db = db

    async def link_wallet(
        self,
        user_id: str,
        wallet_address: str,
        signature: str,
        message: str,
        chain_id: int = 1,
    ) -> WalletLink:
        """Link a wallet address to a user account.

        Args:
            user_id: User ID to link wallet to
            wallet_address: Ethereum wallet address (0x...)
            signature: ECDSA signature from wallet
            message: Message that was signed
            chain_id: Blockchain chain ID (1=Ethereum mainnet)

        Returns:
            WalletLink: Created wallet link

        Raises:
            ValueError: If address invalid, signature invalid, or wallet already linked
        """
        # Validate address format
        if not self._is_valid_address(wallet_address):
            raise ValueError(f"Invalid Ethereum address: {wallet_address}")

        # Normalize address (checksum)
        wallet_address = Web3.to_checksum_address(wallet_address)

        # Check if wallet already linked
        existing = await self.db.execute(
            select(WalletLink).where(WalletLink.wallet_address == wallet_address)
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Wallet {wallet_address} is already linked to a user")

        # Verify signature
        if not self._verify_signature(wallet_address, message, signature):
            raise ValueError("Invalid signature")

        # Create wallet link
        link = WalletLink(
            id=str(uuid4()),
            user_id=user_id,
            wallet_address=wallet_address,
            chain_id=chain_id,
            signature=signature,
            message=message,
            verified_at=datetime.now(UTC),
            is_active=1,
        )

        self.db.add(link)
        await self.db.flush()

        # Audit log
        audit = AuditLog(
            id=str(uuid4()),
            actor_id=user_id,
            actor_role="USER",
            action="web3.wallet_link",
            target="wallet_link",
            target_id=link.id,
            status="success",
            meta={
                "wallet_address": wallet_address,
                "chain_id": chain_id,
            },
        )
        self.db.add(audit)
        await self.db.commit()

        return link

    async def revoke_wallet(
        self, user_id: str, wallet_address: str, actor_id: str, actor_role: str
    ) -> WalletLink:
        """Revoke a wallet link.

        Args:
            user_id: User ID who owns the wallet
            wallet_address: Wallet address to revoke
            actor_id: ID of user performing revocation (can be owner/admin)
            actor_role: Role of actor (OWNER, ADMIN, USER)

        Returns:
            WalletLink: Revoked wallet link

        Raises:
            ValueError: If wallet not found or not owned by user
        """
        wallet_address = Web3.to_checksum_address(wallet_address)

        # Find wallet link
        result = await self.db.execute(
            select(WalletLink)
            .where(WalletLink.wallet_address == wallet_address)
            .where(WalletLink.user_id == user_id)
        )
        link = result.scalar_one_or_none()

        if not link:
            raise ValueError(f"Wallet {wallet_address} not found for user {user_id}")

        # Revoke
        link.is_active = 0
        link.revoked_at = datetime.now(UTC)
        await self.db.flush()

        # Audit log
        audit = AuditLog(
            id=str(uuid4()),
            actor_id=actor_id,
            actor_role=actor_role,
            action="web3.wallet_revoke",
            target="wallet_link",
            target_id=link.id,
            status="success",
            meta={
                "wallet_address": wallet_address,
                "revoked_by": actor_id,
            },
        )
        self.db.add(audit)
        await self.db.commit()

        return link

    async def get_user_wallets(self, user_id: str) -> list[WalletLink]:
        """Get all active wallet links for a user.

        Args:
            user_id: User ID

        Returns:
            List of active wallet links
        """
        result = await self.db.execute(
            select(WalletLink)
            .where(WalletLink.user_id == user_id)
            .where(WalletLink.is_active == 1)
        )
        return list(result.scalars().all())

    async def get_wallet_owner(self, wallet_address: str) -> str | None:
        """Get user ID that owns a wallet address.

        Args:
            wallet_address: Wallet address to look up

        Returns:
            User ID or None if not linked
        """
        wallet_address = Web3.to_checksum_address(wallet_address)

        result = await self.db.execute(
            select(WalletLink)
            .where(WalletLink.wallet_address == wallet_address)
            .where(WalletLink.is_active == 1)
        )
        link = result.scalar_one_or_none()
        return link.user_id if link else None

    def _is_valid_address(self, address: str) -> bool:
        """Validate Ethereum address format.

        Args:
            address: Address to validate

        Returns:
            True if valid format
        """
        if not address:
            return False
        # Must start with 0x and have 40 hex characters
        pattern = re.compile(r"^0x[a-fA-F0-9]{40}$")
        return bool(pattern.match(address))

    def _verify_signature(
        self, wallet_address: str, message: str, signature: str
    ) -> bool:
        """Verify ECDSA signature from wallet.

        Args:
            wallet_address: Expected signer address
            message: Message that was signed
            signature: Hex-encoded signature

        Returns:
            True if signature valid
        """
        try:
            # Encode message with Ethereum prefix
            encoded_msg = encode_defunct(text=message)

            # Recover address from signature
            from eth_account import Account

            recovered_address = Account.recover_message(
                encoded_msg, signature=signature
            )

            # Compare addresses (case-insensitive)
            return recovered_address.lower() == wallet_address.lower()

        except Exception:
            return False

    def generate_link_message(self, user_id: str, nonce: str | None = None) -> str:
        """Generate a message for wallet signature.

        Args:
            user_id: User ID to link
            nonce: Optional nonce (random string)

        Returns:
            Message to sign
        """
        if nonce is None:
            nonce = hashlib.sha256(str(uuid4()).encode()).hexdigest()[:16]

        timestamp = datetime.now(UTC).isoformat()

        return (
            f"Sign this message to link your wallet to your trading account.\n\n"
            f"User ID: {user_id}\n"
            f"Nonce: {nonce}\n"
            f"Timestamp: {timestamp}\n\n"
            f"This request will not trigger any blockchain transaction or cost any gas fees."
        )
