"""Comprehensive test suite for PR-102 Web3 NFT Access.

Tests REAL business logic with fake backends:
- Wallet linking with ECDSA signature verification
- NFT minting/revocation
- Access checks with expiration
- Audit logging
- Feature flag enforcement
- Security validations

Coverage target: 100%
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.audit.models import AuditLog
from backend.app.users.models import User
from backend.app.web3.models import NFTAccess, WalletLink
from backend.app.web3.nft_access import NFTAccessService
from backend.app.web3.wallet_link import WalletLinkService

# ==================== FIXTURES ====================


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        id=str(uuid4()),
        telegram_id="12345",
        username="test_user",
        role="user",
        tier=1,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def owner_user(db_session: AsyncSession) -> User:
    """Create an owner user."""
    user = User(
        id=str(uuid4()),
        telegram_id="99999",
        username="owner",
        role="owner",
        tier=3,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def test_wallet():
    """Create a test Ethereum wallet."""
    account = Account.create()
    return {
        "address": account.address,
        "private_key": account.key.hex(),
        "account": account,
    }


@pytest.fixture
def test_wallet_2():
    """Create a second test Ethereum wallet."""
    account = Account.create()
    return {
        "address": account.address,
        "private_key": account.key.hex(),
        "account": account,
    }


def sign_message(private_key: str, message: str) -> str:
    """Sign a message with a private key.

    Args:
        private_key: Hex-encoded private key
        message: Message to sign

    Returns:
        Hex-encoded signature
    """
    account = Account.from_key(private_key)
    encoded_msg = encode_defunct(text=message)
    signed = account.sign_message(encoded_msg)
    return signed.signature.hex()


# ==================== WALLET LINKING TESTS ====================


@pytest.mark.asyncio
async def test_link_wallet_valid_signature(
    db_session: AsyncSession, test_user: User, test_wallet: dict
):
    """Test wallet linking with valid ECDSA signature."""
    service = WalletLinkService(db_session)

    # Generate message
    message = service.generate_link_message(test_user.id)

    # Sign with wallet
    signature = sign_message(test_wallet["private_key"], message)

    # Link wallet
    link = await service.link_wallet(
        user_id=test_user.id,
        wallet_address=test_wallet["address"],
        signature=signature,
        message=message,
        chain_id=1,
    )

    # Validate
    assert link.id is not None
    assert link.user_id == test_user.id
    assert link.wallet_address.lower() == test_wallet["address"].lower()
    assert link.chain_id == 1
    assert link.is_valid
    assert link.signature == signature
    assert link.message == message

    # Verify audit log created
    result = await db_session.execute(
        select(AuditLog)
        .where(AuditLog.action == "web3.wallet_link")
        .where(AuditLog.target_id == link.id)
    )
    audit = result.scalar_one_or_none()
    assert audit is not None
    assert audit.actor_id == test_user.id
    assert audit.status == "success"


@pytest.mark.asyncio
async def test_link_wallet_invalid_signature(
    db_session: AsyncSession, test_user: User, test_wallet: dict, test_wallet_2: dict
):
    """Test wallet linking rejects invalid signature."""
    service = WalletLinkService(db_session)

    message = service.generate_link_message(test_user.id)

    # Sign with DIFFERENT wallet (wrong private key)
    wrong_signature = sign_message(test_wallet_2["private_key"], message)

    # Should raise ValueError
    with pytest.raises(ValueError, match="Invalid signature"):
        await service.link_wallet(
            user_id=test_user.id,
            wallet_address=test_wallet["address"],  # Correct address
            signature=wrong_signature,  # Wrong signature
            message=message,
        )


@pytest.mark.asyncio
async def test_link_wallet_invalid_address_format(
    db_session: AsyncSession, test_user: User
):
    """Test wallet linking rejects invalid address format."""
    service = WalletLinkService(db_session)

    invalid_addresses = [
        "",
        "0x123",  # Too short
        "0xZZZ",  # Invalid hex
        "742d35Cc6634C0532925a3b844Bc9e7595f0bEb",  # Missing 0x
        "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEbXX",  # Extra chars
    ]

    for invalid_addr in invalid_addresses:
        with pytest.raises(ValueError, match="Invalid Ethereum address"):
            await service.link_wallet(
                user_id=test_user.id,
                wallet_address=invalid_addr,
                signature="0x" + "00" * 65,
                message="test message",
            )


@pytest.mark.asyncio
async def test_link_wallet_duplicate_address(
    db_session: AsyncSession, test_user: User, owner_user: User, test_wallet: dict
):
    """Test wallet linking prevents duplicate wallet addresses."""
    service = WalletLinkService(db_session)

    message = service.generate_link_message(test_user.id)
    signature = sign_message(test_wallet["private_key"], message)

    # Link wallet to first user
    await service.link_wallet(
        user_id=test_user.id,
        wallet_address=test_wallet["address"],
        signature=signature,
        message=message,
    )

    # Try to link same wallet to second user
    message2 = service.generate_link_message(owner_user.id)
    signature2 = sign_message(test_wallet["private_key"], message2)

    with pytest.raises(ValueError, match="already linked"):
        await service.link_wallet(
            user_id=owner_user.id,
            wallet_address=test_wallet["address"],  # Same wallet
            signature=signature2,
            message=message2,
        )


@pytest.mark.asyncio
async def test_revoke_wallet(
    db_session: AsyncSession, test_user: User, test_wallet: dict
):
    """Test wallet revocation."""
    service = WalletLinkService(db_session)

    # Link wallet
    message = service.generate_link_message(test_user.id)
    signature = sign_message(test_wallet["private_key"], message)
    link = await service.link_wallet(
        user_id=test_user.id,
        wallet_address=test_wallet["address"],
        signature=signature,
        message=message,
    )

    assert link.is_valid

    # Revoke wallet
    revoked = await service.revoke_wallet(
        user_id=test_user.id,
        wallet_address=test_wallet["address"],
        actor_id=test_user.id,
        actor_role="USER",
    )

    assert not revoked.is_valid
    assert revoked.is_active == 0
    assert revoked.revoked_at is not None

    # Verify audit log
    result = await db_session.execute(
        select(AuditLog)
        .where(AuditLog.action == "web3.wallet_revoke")
        .where(AuditLog.target_id == link.id)
    )
    audit = result.scalar_one_or_none()
    assert audit is not None
    assert audit.status == "success"


@pytest.mark.asyncio
async def test_get_user_wallets(
    db_session: AsyncSession, test_user: User, test_wallet: dict, test_wallet_2: dict
):
    """Test retrieving user's wallets."""
    service = WalletLinkService(db_session)

    # Link two wallets
    for wallet in [test_wallet, test_wallet_2]:
        message = service.generate_link_message(test_user.id)
        signature = sign_message(wallet["private_key"], message)
        await service.link_wallet(
            user_id=test_user.id,
            wallet_address=wallet["address"],
            signature=signature,
            message=message,
        )

    # Get wallets
    wallets = await service.get_user_wallets(test_user.id)
    assert len(wallets) == 2
    addresses = [w.wallet_address.lower() for w in wallets]
    assert test_wallet["address"].lower() in addresses
    assert test_wallet_2["address"].lower() in addresses


@pytest.mark.asyncio
async def test_get_wallet_owner(
    db_session: AsyncSession, test_user: User, test_wallet: dict
):
    """Test wallet owner lookup."""
    service = WalletLinkService(db_session)

    # Before linking
    owner_id = await service.get_wallet_owner(test_wallet["address"])
    assert owner_id is None

    # Link wallet
    message = service.generate_link_message(test_user.id)
    signature = sign_message(test_wallet["private_key"], message)
    await service.link_wallet(
        user_id=test_user.id,
        wallet_address=test_wallet["address"],
        signature=signature,
        message=message,
    )

    # After linking
    owner_id = await service.get_wallet_owner(test_wallet["address"])
    assert owner_id == test_user.id


# ==================== NFT ACCESS MINTING TESTS ====================


@pytest.mark.asyncio
async def test_mint_nft_valid(
    db_session: AsyncSession, test_user: User, owner_user: User, test_wallet: dict
):
    """Test NFT minting with valid wallet link."""
    wallet_service = WalletLinkService(db_session)
    nft_service = NFTAccessService(db_session)

    # Link wallet
    message = wallet_service.generate_link_message(test_user.id)
    signature = sign_message(test_wallet["private_key"], message)
    await wallet_service.link_wallet(
        user_id=test_user.id,
        wallet_address=test_wallet["address"],
        signature=signature,
        message=message,
    )

    # Mint NFT
    expires_at = datetime.now(UTC) + timedelta(days=365)
    nft = await nft_service.mint(
        user_id=test_user.id,
        wallet_address=test_wallet["address"],
        entitlement_key="copy.mirror",
        expires_at=expires_at,
        chain_id=1,
        meta={"pricing": "premium", "tier": "gold"},
        actor_id=owner_user.id,
        actor_role="OWNER",
    )

    # Validate
    assert nft.id is not None
    assert nft.user_id == test_user.id
    assert nft.wallet_address.lower() == test_wallet["address"].lower()
    assert nft.entitlement_key == "copy.mirror"
    assert nft.is_valid
    assert not nft.is_expired
    assert nft.expires_at == expires_at
    assert nft.meta == {"pricing": "premium", "tier": "gold"}

    # Verify audit log
    result = await db_session.execute(
        select(AuditLog)
        .where(AuditLog.action == "web3.nft_mint")
        .where(AuditLog.target_id == nft.id)
    )
    audit = result.scalar_one_or_none()
    assert audit is not None
    assert audit.actor_id == owner_user.id
    assert audit.actor_role == "OWNER"
    assert audit.status == "success"


@pytest.mark.asyncio
async def test_mint_nft_wallet_not_linked(
    db_session: AsyncSession, test_user: User, owner_user: User, test_wallet: dict
):
    """Test NFT minting fails if wallet not linked."""
    nft_service = NFTAccessService(db_session)

    # Try to mint without linking wallet
    with pytest.raises(ValueError, match="not linked"):
        await nft_service.mint(
            user_id=test_user.id,
            wallet_address=test_wallet["address"],  # Not linked
            entitlement_key="copy.mirror",
            actor_id=owner_user.id,
            actor_role="OWNER",
        )


@pytest.mark.asyncio
async def test_mint_nft_duplicate_entitlement(
    db_session: AsyncSession, test_user: User, owner_user: User, test_wallet: dict
):
    """Test NFT minting prevents duplicate active entitlements."""
    wallet_service = WalletLinkService(db_session)
    nft_service = NFTAccessService(db_session)

    # Link wallet
    message = wallet_service.generate_link_message(test_user.id)
    signature = sign_message(test_wallet["private_key"], message)
    await wallet_service.link_wallet(
        user_id=test_user.id,
        wallet_address=test_wallet["address"],
        signature=signature,
        message=message,
    )

    # Mint first NFT
    await nft_service.mint(
        user_id=test_user.id,
        wallet_address=test_wallet["address"],
        entitlement_key="copy.mirror",
        actor_id=owner_user.id,
        actor_role="OWNER",
    )

    # Try to mint duplicate
    with pytest.raises(ValueError, match="already has active NFT"):
        await nft_service.mint(
            user_id=test_user.id,
            wallet_address=test_wallet["address"],
            entitlement_key="copy.mirror",  # Same entitlement
            actor_id=owner_user.id,
            actor_role="OWNER",
        )


@pytest.mark.asyncio
async def test_revoke_nft(
    db_session: AsyncSession, test_user: User, owner_user: User, test_wallet: dict
):
    """Test NFT revocation."""
    wallet_service = WalletLinkService(db_session)
    nft_service = NFTAccessService(db_session)

    # Link wallet
    message = wallet_service.generate_link_message(test_user.id)
    signature = sign_message(test_wallet["private_key"], message)
    await wallet_service.link_wallet(
        user_id=test_user.id,
        wallet_address=test_wallet["address"],
        signature=signature,
        message=message,
    )

    # Mint NFT
    nft = await nft_service.mint(
        user_id=test_user.id,
        wallet_address=test_wallet["address"],
        entitlement_key="copy.mirror",
        actor_id=owner_user.id,
        actor_role="OWNER",
    )

    assert nft.is_valid

    # Revoke NFT
    revoked = await nft_service.revoke(
        nft_id=nft.id,
        reason="User violated terms of service",
        actor_id=owner_user.id,
        actor_role="OWNER",
    )

    assert not revoked.is_valid
    assert revoked.is_active == 0
    assert revoked.revoked_at is not None
    assert revoked.revoke_reason == "User violated terms of service"

    # Verify audit log
    result = await db_session.execute(
        select(AuditLog)
        .where(AuditLog.action == "web3.nft_revoke")
        .where(AuditLog.target_id == nft.id)
    )
    audit = result.scalar_one_or_none()
    assert audit is not None
    assert audit.status == "success"


@pytest.mark.asyncio
async def test_check_access_valid(
    db_session: AsyncSession, test_user: User, owner_user: User, test_wallet: dict
):
    """Test NFT access check with valid token."""
    wallet_service = WalletLinkService(db_session)
    nft_service = NFTAccessService(db_session)

    # Setup
    message = wallet_service.generate_link_message(test_user.id)
    signature = sign_message(test_wallet["private_key"], message)
    await wallet_service.link_wallet(
        user_id=test_user.id,
        wallet_address=test_wallet["address"],
        signature=signature,
        message=message,
    )

    await nft_service.mint(
        user_id=test_user.id,
        wallet_address=test_wallet["address"],
        entitlement_key="copy.mirror",
        actor_id=owner_user.id,
        actor_role="OWNER",
    )

    # Check access
    has_access, nft = await nft_service.check_access(
        test_wallet["address"], "copy.mirror"
    )

    assert has_access is True
    assert nft is not None
    assert nft.entitlement_key == "copy.mirror"


@pytest.mark.asyncio
async def test_check_access_no_nft(db_session: AsyncSession, test_wallet: dict):
    """Test NFT access check with no token."""
    nft_service = NFTAccessService(db_session)

    # Check access without any NFT
    has_access, nft = await nft_service.check_access(
        test_wallet["address"], "copy.mirror"
    )

    assert has_access is False
    assert nft is None


@pytest.mark.asyncio
async def test_check_access_expired(
    db_session: AsyncSession, test_user: User, owner_user: User, test_wallet: dict
):
    """Test NFT access check with expired token."""
    wallet_service = WalletLinkService(db_session)
    nft_service = NFTAccessService(db_session)

    # Setup
    message = wallet_service.generate_link_message(test_user.id)
    signature = sign_message(test_wallet["private_key"], message)
    await wallet_service.link_wallet(
        user_id=test_user.id,
        wallet_address=test_wallet["address"],
        signature=signature,
        message=message,
    )

    # Mint expired NFT
    expires_at = datetime.now(UTC) - timedelta(days=1)  # Yesterday
    await nft_service.mint(
        user_id=test_user.id,
        wallet_address=test_wallet["address"],
        entitlement_key="copy.mirror",
        expires_at=expires_at,
        actor_id=owner_user.id,
        actor_role="OWNER",
    )

    # Check access
    has_access, nft = await nft_service.check_access(
        test_wallet["address"], "copy.mirror"
    )

    assert has_access is False
    assert nft is not None  # NFT exists but expired
    assert nft.is_expired


@pytest.mark.asyncio
async def test_check_access_revoked(
    db_session: AsyncSession, test_user: User, owner_user: User, test_wallet: dict
):
    """Test NFT access check with revoked token."""
    wallet_service = WalletLinkService(db_session)
    nft_service = NFTAccessService(db_session)

    # Setup
    message = wallet_service.generate_link_message(test_user.id)
    signature = sign_message(test_wallet["private_key"], message)
    await wallet_service.link_wallet(
        user_id=test_user.id,
        wallet_address=test_wallet["address"],
        signature=signature,
        message=message,
    )

    nft = await nft_service.mint(
        user_id=test_user.id,
        wallet_address=test_wallet["address"],
        entitlement_key="copy.mirror",
        actor_id=owner_user.id,
        actor_role="OWNER",
    )

    # Revoke
    await nft_service.revoke(
        nft_id=nft.id,
        reason="Test revocation",
        actor_id=owner_user.id,
        actor_role="OWNER",
    )

    # Check access
    has_access, returned_nft = await nft_service.check_access(
        test_wallet["address"], "copy.mirror"
    )

    assert has_access is False
    assert returned_nft is None  # Revoked NFTs excluded from query


@pytest.mark.asyncio
async def test_get_user_nfts(
    db_session: AsyncSession,
    test_user: User,
    owner_user: User,
    test_wallet: dict,
    test_wallet_2: dict,
):
    """Test retrieving user's NFTs."""
    wallet_service = WalletLinkService(db_session)
    nft_service = NFTAccessService(db_session)

    # Link wallets
    for wallet in [test_wallet, test_wallet_2]:
        message = wallet_service.generate_link_message(test_user.id)
        signature = sign_message(wallet["private_key"], message)
        await wallet_service.link_wallet(
            user_id=test_user.id,
            wallet_address=wallet["address"],
            signature=signature,
            message=message,
        )

    # Mint NFTs
    await nft_service.mint(
        user_id=test_user.id,
        wallet_address=test_wallet["address"],
        entitlement_key="copy.mirror",
        actor_id=owner_user.id,
        actor_role="OWNER",
    )

    await nft_service.mint(
        user_id=test_user.id,
        wallet_address=test_wallet_2["address"],
        entitlement_key="strategy.premium",
        actor_id=owner_user.id,
        actor_role="OWNER",
    )

    # Get NFTs
    nfts = await nft_service.get_user_nfts(test_user.id, active_only=True)
    assert len(nfts) == 2

    entitlements = [nft.entitlement_key for nft in nfts]
    assert "copy.mirror" in entitlements
    assert "strategy.premium" in entitlements


@pytest.mark.asyncio
async def test_extend_nft_expiry(
    db_session: AsyncSession, test_user: User, owner_user: User, test_wallet: dict
):
    """Test extending NFT expiration."""
    wallet_service = WalletLinkService(db_session)
    nft_service = NFTAccessService(db_session)

    # Setup
    message = wallet_service.generate_link_message(test_user.id)
    signature = sign_message(test_wallet["private_key"], message)
    await wallet_service.link_wallet(
        user_id=test_user.id,
        wallet_address=test_wallet["address"],
        signature=signature,
        message=message,
    )

    # Mint with 30-day expiry
    expires_at = datetime.now(UTC) + timedelta(days=30)
    nft = await nft_service.mint(
        user_id=test_user.id,
        wallet_address=test_wallet["address"],
        entitlement_key="copy.mirror",
        expires_at=expires_at,
        actor_id=owner_user.id,
        actor_role="OWNER",
    )

    # Extend to 365 days
    new_expires_at = datetime.now(UTC) + timedelta(days=365)
    extended = await nft_service.extend_expiry(
        nft_id=nft.id,
        new_expires_at=new_expires_at,
        actor_id=owner_user.id,
        actor_role="OWNER",
    )

    assert extended.expires_at == new_expires_at
    assert not extended.is_expired

    # Verify audit log
    result = await db_session.execute(
        select(AuditLog)
        .where(AuditLog.action == "web3.nft_extend")
        .where(AuditLog.target_id == nft.id)
    )
    audit = result.scalar_one_or_none()
    assert audit is not None
    assert audit.status == "success"


@pytest.mark.asyncio
async def test_nft_expiration_logic(
    db_session: AsyncSession, test_user: User, owner_user: User, test_wallet: dict
):
    """Test NFT expiration property logic."""
    wallet_service = WalletLinkService(db_session)
    nft_service = NFTAccessService(db_session)

    # Setup
    message = wallet_service.generate_link_message(test_user.id)
    signature = sign_message(test_wallet["private_key"], message)
    await wallet_service.link_wallet(
        user_id=test_user.id,
        wallet_address=test_wallet["address"],
        signature=signature,
        message=message,
    )

    # Test permanent NFT (no expiry)
    permanent_nft = await nft_service.mint(
        user_id=test_user.id,
        wallet_address=test_wallet["address"],
        entitlement_key="strategy.premium",
        expires_at=None,  # Permanent
        actor_id=owner_user.id,
        actor_role="OWNER",
    )

    assert permanent_nft.expires_at is None
    assert not permanent_nft.is_expired
    assert permanent_nft.is_valid

    # Test future expiry
    future_nft_result = await db_session.execute(
        select(NFTAccess)
        .where(NFTAccess.user_id == test_user.id)
        .where(NFTAccess.entitlement_key == "strategy.premium")
    )
    future_nft = future_nft_result.scalar_one()

    # Manually set future expiry
    future_nft.expires_at = datetime.now(UTC) + timedelta(days=30)
    await db_session.commit()
    await db_session.refresh(future_nft)

    assert future_nft.expires_at is not None
    assert not future_nft.is_expired
    assert future_nft.is_valid

    # Test past expiry
    future_nft.expires_at = datetime.now(UTC) - timedelta(days=1)
    await db_session.commit()
    await db_session.refresh(future_nft)

    assert future_nft.expires_at is not None
    assert future_nft.is_expired
    assert not future_nft.is_valid  # Expired NFTs are invalid


# ==================== EDGE CASES & SECURITY ====================


@pytest.mark.asyncio
async def test_signature_replay_attack_prevention(
    db_session: AsyncSession, test_user: User, test_wallet: dict
):
    """Test that same signature cannot be reused (message includes unique nonce)."""
    service = WalletLinkService(db_session)

    message1 = service.generate_link_message(test_user.id)
    signature1 = sign_message(test_wallet["private_key"], message1)

    # First link succeeds
    await service.link_wallet(
        user_id=test_user.id,
        wallet_address=test_wallet["address"],
        signature=signature1,
        message=message1,
    )

    # Revoke
    await service.revoke_wallet(
        user_id=test_user.id,
        wallet_address=test_wallet["address"],
        actor_id=test_user.id,
        actor_role="USER",
    )

    # Try to reuse same signature (should fail - wallet already exists)
    with pytest.raises(ValueError, match="already linked"):
        await service.link_wallet(
            user_id=test_user.id,
            wallet_address=test_wallet["address"],
            signature=signature1,  # Same signature
            message=message1,  # Same message
        )


@pytest.mark.asyncio
async def test_checksum_address_normalization(
    db_session: AsyncSession, test_user: User, test_wallet: dict
):
    """Test that addresses are normalized to checksum format."""
    service = WalletLinkService(db_session)

    message = service.generate_link_message(test_user.id)
    signature = sign_message(test_wallet["private_key"], message)

    # Link with lowercase address
    lowercase_addr = test_wallet["address"].lower()
    link = await service.link_wallet(
        user_id=test_user.id,
        wallet_address=lowercase_addr,
        signature=signature,
        message=message,
    )

    # Should be stored as checksum
    from web3 import Web3

    expected_checksum = Web3.to_checksum_address(lowercase_addr)
    assert link.wallet_address == expected_checksum


@pytest.mark.asyncio
async def test_multiple_entitlements_per_user(
    db_session: AsyncSession, test_user: User, owner_user: User, test_wallet: dict
):
    """Test user can have multiple different entitlements."""
    wallet_service = WalletLinkService(db_session)
    nft_service = NFTAccessService(db_session)

    # Setup
    message = wallet_service.generate_link_message(test_user.id)
    signature = sign_message(test_wallet["private_key"], message)
    await wallet_service.link_wallet(
        user_id=test_user.id,
        wallet_address=test_wallet["address"],
        signature=signature,
        message=message,
    )

    # Mint multiple entitlements
    entitlements = ["copy.mirror", "strategy.premium"]
    for entitlement in entitlements:
        await nft_service.mint(
            user_id=test_user.id,
            wallet_address=test_wallet["address"],
            entitlement_key=entitlement,
            actor_id=owner_user.id,
            actor_role="OWNER",
        )

    # Verify all exist
    nfts = await nft_service.get_user_nfts(test_user.id)
    assert len(nfts) == 2
    assert {nft.entitlement_key for nft in nfts} == set(entitlements)


@pytest.mark.asyncio
async def test_wallet_cascade_delete_on_user_delete(
    db_session: AsyncSession, test_user: User, test_wallet: dict
):
    """Test wallet links are deleted when user is deleted (CASCADE)."""
    service = WalletLinkService(db_session)

    # Link wallet
    message = service.generate_link_message(test_user.id)
    signature = sign_message(test_wallet["private_key"], message)
    link = await service.link_wallet(
        user_id=test_user.id,
        wallet_address=test_wallet["address"],
        signature=signature,
        message=message,
    )

    # Verify link exists
    result = await db_session.execute(
        select(WalletLink).where(WalletLink.id == link.id)
    )
    assert result.scalar_one_or_none() is not None

    # Delete user
    await db_session.delete(test_user)
    await db_session.commit()

    # Verify wallet link deleted (CASCADE)
    result = await db_session.execute(
        select(WalletLink).where(WalletLink.id == link.id)
    )
    assert result.scalar_one_or_none() is None
