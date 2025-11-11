"""Web3 NFT Access and Wallet Link database models."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, Integer, String

from backend.app.core.db import Base


class WalletLink(Base):
    """Links a Web3 wallet address to a user account.

    SIWE (Sign-In with Ethereum) or simple signature verification.
    One user can link multiple wallets.
    """

    __tablename__ = "wallet_links"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    wallet_address = Column(
        String(42), nullable=False, unique=True, index=True
    )  # 0x... format
    chain_id = Column(Integer, nullable=False, default=1)  # 1=Ethereum mainnet
    signature = Column(String(132), nullable=True)  # Verification signature
    message = Column(String(255), nullable=True)  # Signed message for verification
    verified_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    is_active = Column(Integer, nullable=False, default=1)  # 0=revoked, 1=active
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    revoked_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_wallet_links_user", "user_id"),
        Index("ix_wallet_links_address", "wallet_address"),
        Index("ix_wallet_links_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<WalletLink user={self.user_id} address={self.wallet_address[:10]}...>"

    @property
    def is_valid(self) -> bool:
        """Check if wallet link is currently active."""
        return bool(self.is_active == 1)


class NFTAccess(Base):
    """NFT/token representing access to a feature (e.g., copy.mirror).

    Non-transferable or time-locked tokens for strategy licensing.
    Behind feature flag: NFT_ACCESS_ENABLED=false by default.
    """

    __tablename__ = "nft_access"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    wallet_address = Column(
        String(42),
        ForeignKey("wallet_links.wallet_address", ondelete="CASCADE"),
        nullable=False,
    )
    entitlement_key = Column(
        String(50), nullable=False
    )  # e.g., "copy.mirror", "strategy.premium"
    token_id = Column(String(100), nullable=True)  # On-chain token ID (if minted)
    contract_address = Column(String(42), nullable=True)  # NFT contract address
    chain_id = Column(Integer, nullable=False, default=1)
    is_active = Column(
        Integer, nullable=False, default=1
    )  # 0=revoked/expired, 1=active
    minted_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    expires_at = Column(DateTime, nullable=True)  # None = permanent
    revoked_at = Column(DateTime, nullable=True)
    revoke_reason = Column(String(255), nullable=True)
    meta = Column(JSON, nullable=True)  # Additional metadata (pricing, terms, etc.)

    __table_args__ = (
        Index("ix_nft_access_user", "user_id"),
        Index("ix_nft_access_wallet", "wallet_address"),
        Index("ix_nft_access_entitlement", "entitlement_key"),
        Index("ix_nft_access_active", "is_active", "expires_at"),
    )

    def __repr__(self) -> str:
        return f"<NFTAccess user={self.user_id} entitlement={self.entitlement_key}>"

    @property
    def is_expired(self) -> bool:
        """Check if NFT access has expired."""
        if self.expires_at is not None and self.expires_at < datetime.now(UTC):
            return True
        return False

    @property
    def is_valid(self) -> bool:
        """Check if NFT access is currently valid."""
        return bool(self.is_active == 1 and not self.is_expired)
