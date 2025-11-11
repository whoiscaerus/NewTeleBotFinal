"""Web3 NFT Access API routes.

Endpoints for wallet linking, NFT minting/revocation, and access checks.
Behind feature flag: NFT_ACCESS_ENABLED=false by default.
"""

import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.dependencies import get_current_user
from backend.app.core.db import get_db
from backend.app.users.models import User
from backend.app.web3.nft_access import NFTAccessService
from backend.app.web3.wallet_link import WalletLinkService

router = APIRouter(prefix="/api/v1/web3", tags=["web3"])


# Feature flag check
def check_nft_feature_enabled():
    """Check if NFT access feature is enabled."""
    if os.getenv("NFT_ACCESS_ENABLED", "false").lower() != "true":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="NFT access feature is not enabled",
        )


# Pydantic schemas
class WalletLinkRequest(BaseModel):
    """Request to link a wallet to user account."""

    wallet_address: str = Field(..., min_length=42, max_length=42)
    signature: str = Field(..., min_length=132, max_length=132)
    message: str = Field(..., min_length=10, max_length=500)
    chain_id: int = Field(default=1, ge=1)


class WalletLinkResponse(BaseModel):
    """Response after linking wallet."""

    id: str
    user_id: str
    wallet_address: str
    chain_id: int
    verified_at: datetime
    is_active: bool


class NFTMintRequest(BaseModel):
    """Request to mint NFT access token (owner/admin only)."""

    user_id: str = Field(..., min_length=36, max_length=36)
    wallet_address: str = Field(..., min_length=42, max_length=42)
    entitlement_key: str = Field(
        ..., min_length=3, max_length=50, pattern=r"^[a-z._]+$"
    )
    expires_at: datetime | None = None
    token_id: str | None = None
    contract_address: str | None = None
    chain_id: int = Field(default=1, ge=1)
    meta: dict | None = None


class NFTRevokeRequest(BaseModel):
    """Request to revoke NFT access token (owner/admin only)."""

    nft_id: str = Field(..., min_length=36, max_length=36)
    reason: str = Field(..., min_length=3, max_length=255)


class NFTAccessResponse(BaseModel):
    """Response for NFT access token."""

    id: str
    user_id: str
    wallet_address: str
    entitlement_key: str
    token_id: str | None
    contract_address: str | None
    chain_id: int
    is_active: bool
    minted_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    revoke_reason: str | None


class AccessCheckResponse(BaseModel):
    """Response for access check."""

    has_access: bool
    nft: NFTAccessResponse | None


# Routes
@router.post("/link", status_code=status.HTTP_201_CREATED)
async def link_wallet(
    request: WalletLinkRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WalletLinkResponse:
    """Link a Web3 wallet to user account.

    Requires:
        - Valid Ethereum address
        - Valid ECDSA signature proving wallet ownership
        - Wallet not already linked to another user

    Args:
        request: Wallet link request
        current_user: Authenticated user
        db: Database session

    Returns:
        WalletLinkResponse: Created wallet link

    Raises:
        400: Invalid address, signature, or wallet already linked
    """
    service = WalletLinkService(db)

    try:
        link = await service.link_wallet(
            user_id=current_user.id,
            wallet_address=request.wallet_address,
            signature=request.signature,
            message=request.message,
            chain_id=request.chain_id,
        )

        return WalletLinkResponse(
            id=link.id,
            user_id=link.user_id,
            wallet_address=link.wallet_address,
            chain_id=link.chain_id,
            verified_at=link.verified_at,
            is_active=link.is_valid,
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/link/{wallet_address}", status_code=status.HTTP_200_OK)
async def revoke_wallet(
    wallet_address: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WalletLinkResponse:
    """Revoke a wallet link.

    Args:
        wallet_address: Wallet address to revoke
        current_user: Authenticated user
        db: Database session

    Returns:
        WalletLinkResponse: Revoked wallet link

    Raises:
        404: Wallet not found
    """
    service = WalletLinkService(db)

    try:
        link = await service.revoke_wallet(
            user_id=current_user.id,
            wallet_address=wallet_address,
            actor_id=current_user.id,
            actor_role=current_user.role.upper(),
        )

        return WalletLinkResponse(
            id=link.id,
            user_id=link.user_id,
            wallet_address=link.wallet_address,
            chain_id=link.chain_id,
            verified_at=link.verified_at,
            is_active=link.is_valid,
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/wallets", status_code=status.HTTP_200_OK)
async def get_my_wallets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WalletLinkResponse]:
    """Get all linked wallets for current user.

    Args:
        current_user: Authenticated user
        db: Database session

    Returns:
        List of wallet links
    """
    service = WalletLinkService(db)
    wallets = await service.get_user_wallets(current_user.id)

    return [
        WalletLinkResponse(
            id=w.id,
            user_id=w.user_id,
            wallet_address=w.wallet_address,
            chain_id=w.chain_id,
            verified_at=w.verified_at,
            is_active=w.is_valid,
        )
        for w in wallets
    ]


@router.post("/nft/mint", status_code=status.HTTP_201_CREATED)
async def mint_nft_access(
    request: NFTMintRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NFTAccessResponse:
    """Mint NFT access token (owner/admin only).

    Requires:
        - Feature flag NFT_ACCESS_ENABLED=true
        - Owner or admin role
        - Valid wallet link for target user

    Args:
        request: NFT mint request
        current_user: Authenticated user
        db: Database session

    Returns:
        NFTAccessResponse: Created NFT access token

    Raises:
        403: Not owner/admin
        400: Invalid wallet or user already has NFT
        503: Feature not enabled
    """
    check_nft_feature_enabled()

    # Only owner/admin can mint
    if current_user.role.lower() not in ["owner", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owner/admin can mint NFT access",
        )

    service = NFTAccessService(db)

    try:
        nft = await service.mint(
            user_id=request.user_id,
            wallet_address=request.wallet_address,
            entitlement_key=request.entitlement_key,
            expires_at=request.expires_at,
            token_id=request.token_id,
            contract_address=request.contract_address,
            chain_id=request.chain_id,
            meta=request.meta,
            actor_id=current_user.id,
            actor_role=current_user.role.upper(),
        )

        return NFTAccessResponse(
            id=nft.id,
            user_id=nft.user_id,
            wallet_address=nft.wallet_address,
            entitlement_key=nft.entitlement_key,
            token_id=nft.token_id,
            contract_address=nft.contract_address,
            chain_id=nft.chain_id,
            is_active=nft.is_valid,
            minted_at=nft.minted_at,
            expires_at=nft.expires_at,
            revoked_at=nft.revoked_at,
            revoke_reason=nft.revoke_reason,
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/nft/revoke", status_code=status.HTTP_200_OK)
async def revoke_nft_access(
    request: NFTRevokeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NFTAccessResponse:
    """Revoke NFT access token (owner/admin only).

    Args:
        request: NFT revoke request
        current_user: Authenticated user
        db: Database session

    Returns:
        NFTAccessResponse: Revoked NFT access token

    Raises:
        403: Not owner/admin
        404: NFT not found
        503: Feature not enabled
    """
    check_nft_feature_enabled()

    # Only owner/admin can revoke
    if current_user.role.lower() not in ["owner", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owner/admin can revoke NFT access",
        )

    service = NFTAccessService(db)

    try:
        nft = await service.revoke(
            nft_id=request.nft_id,
            reason=request.reason,
            actor_id=current_user.id,
            actor_role=current_user.role.upper(),
        )

        return NFTAccessResponse(
            id=nft.id,
            user_id=nft.user_id,
            wallet_address=nft.wallet_address,
            entitlement_key=nft.entitlement_key,
            token_id=nft.token_id,
            contract_address=nft.contract_address,
            chain_id=nft.chain_id,
            is_active=nft.is_valid,
            minted_at=nft.minted_at,
            expires_at=nft.expires_at,
            revoked_at=nft.revoked_at,
            revoke_reason=nft.revoke_reason,
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/access/{wallet_address}/{entitlement_key}", status_code=status.HTTP_200_OK
)
async def check_access(
    wallet_address: str,
    entitlement_key: str,
    db: AsyncSession = Depends(get_db),
) -> AccessCheckResponse:
    """Check if wallet has NFT access for an entitlement (public endpoint).

    Args:
        wallet_address: Wallet address to check
        entitlement_key: Feature key to check
        db: Database session

    Returns:
        AccessCheckResponse: Access status and NFT details

    Raises:
        503: Feature not enabled
    """
    check_nft_feature_enabled()

    service = NFTAccessService(db)
    has_access, nft = await service.check_access(wallet_address, entitlement_key)

    nft_response = None
    if nft:
        nft_response = NFTAccessResponse(
            id=nft.id,
            user_id=nft.user_id,
            wallet_address=nft.wallet_address,
            entitlement_key=nft.entitlement_key,
            token_id=nft.token_id,
            contract_address=nft.contract_address,
            chain_id=nft.chain_id,
            is_active=nft.is_valid,
            minted_at=nft.minted_at,
            expires_at=nft.expires_at,
            revoked_at=nft.revoked_at,
            revoke_reason=nft.revoke_reason,
        )

    return AccessCheckResponse(has_access=has_access, nft=nft_response)


@router.get("/nfts", status_code=status.HTTP_200_OK)
async def get_my_nfts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[NFTAccessResponse]:
    """Get all NFT access tokens for current user.

    Args:
        current_user: Authenticated user
        db: Database session

    Returns:
        List of NFT access tokens

    Raises:
        503: Feature not enabled
    """
    check_nft_feature_enabled()

    service = NFTAccessService(db)
    nfts = await service.get_user_nfts(current_user.id, active_only=False)

    return [
        NFTAccessResponse(
            id=nft.id,
            user_id=nft.user_id,
            wallet_address=nft.wallet_address,
            entitlement_key=nft.entitlement_key,
            token_id=nft.token_id,
            contract_address=nft.contract_address,
            chain_id=nft.chain_id,
            is_active=nft.is_valid,
            minted_at=nft.minted_at,
            expires_at=nft.expires_at,
            revoked_at=nft.revoked_at,
            revoke_reason=nft.revoke_reason,
        )
        for nft in nfts
    ]
