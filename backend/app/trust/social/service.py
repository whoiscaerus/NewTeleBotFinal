"""Social Verification Graph - Business Logic Service.

PR-094: Core verification logic with anti-sybil protections.
"""

import logging
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.trust.social.models import VerificationEdge

logger = logging.getLogger(__name__)

# Anti-sybil configuration
MAX_VERIFICATIONS_PER_HOUR = 5  # Prevent spam verification
MAX_VERIFICATIONS_PER_DAY = 20  # Daily cap
MAX_VERIFICATIONS_PER_IP_PER_DAY = 10  # Prevent IP-based sybil attacks
MAX_VERIFICATIONS_PER_DEVICE_PER_DAY = 15  # Prevent device-based sybil attacks
MIN_ACCOUNT_AGE_DAYS = 7  # Account must be X days old to verify others


class VerificationError(Exception):
    """Base exception for verification errors."""

    pass


class SelfVerificationError(VerificationError):
    """Attempted to verify self."""

    pass


class RateLimitError(VerificationError):
    """Rate limit exceeded."""

    pass


class DuplicateVerificationError(VerificationError):
    """Already verified this peer."""

    pass


class AntiSybilError(VerificationError):
    """Anti-sybil check failed."""

    pass


async def anti_sybil_checks(
    verifier_id: str,
    verified_id: str,
    ip_address: str | None,
    device_fingerprint: str | None,
    db: AsyncSession,
) -> None:
    """
    Run anti-sybil checks before allowing verification.

    Checks:
    1. Self-verification: Cannot verify yourself
    2. Duplicate: Cannot verify same peer twice
    3. Hourly rate limit: Max 5 verifications per hour
    4. Daily rate limit: Max 20 verifications per day
    5. IP-based limit: Max 10 verifications per IP per day
    6. Device-based limit: Max 15 verifications per device per day
    7. Account age: Verifier must be at least 7 days old

    Args:
        verifier_id: User doing the verification
        verified_id: User being verified
        ip_address: IP address of verifier
        device_fingerprint: Device fingerprint of verifier
        db: Database session

    Raises:
        SelfVerificationError: If verifier_id == verified_id
        DuplicateVerificationError: If verification already exists
        RateLimitError: If rate limit exceeded
        AntiSybilError: If anti-sybil check failed

    Example:
        >>> await anti_sybil_checks(verifier, verified, ip, device, db)
        # Raises VerificationError if any check fails
    """
    # Check 1: Self-verification
    if verifier_id == verified_id:
        raise SelfVerificationError("Cannot verify yourself")

    # Check 2: Duplicate verification
    stmt = select(VerificationEdge).where(
        (VerificationEdge.verifier_id == verifier_id)
        & (VerificationEdge.verified_id == verified_id)
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        raise DuplicateVerificationError(f"Already verified user {verified_id}")

    # Check 3: Hourly rate limit
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    stmt = select(func.count(VerificationEdge.id)).where(
        (VerificationEdge.verifier_id == verifier_id)
        & (VerificationEdge.created_at >= one_hour_ago)
    )
    result = await db.execute(stmt)
    hourly_count = result.scalar() or 0

    if hourly_count >= MAX_VERIFICATIONS_PER_HOUR:
        raise RateLimitError(
            f"Hourly verification limit exceeded ({MAX_VERIFICATIONS_PER_HOUR}/hour)"
        )

    # Check 4: Daily rate limit
    one_day_ago = datetime.utcnow() - timedelta(days=1)
    stmt = select(func.count(VerificationEdge.id)).where(
        (VerificationEdge.verifier_id == verifier_id)
        & (VerificationEdge.created_at >= one_day_ago)
    )
    result = await db.execute(stmt)
    daily_count = result.scalar() or 0

    if daily_count >= MAX_VERIFICATIONS_PER_DAY:
        raise RateLimitError(
            f"Daily verification limit exceeded ({MAX_VERIFICATIONS_PER_DAY}/day)"
        )

    # Check 5: IP-based anti-sybil (if IP provided)
    if ip_address:
        stmt = select(func.count(VerificationEdge.id)).where(
            (VerificationEdge.ip_address == ip_address)
            & (VerificationEdge.created_at >= one_day_ago)
        )
        result = await db.execute(stmt)
        ip_count = result.scalar() or 0

        if ip_count >= MAX_VERIFICATIONS_PER_IP_PER_DAY:
            raise AntiSybilError(
                f"Too many verifications from this IP ({MAX_VERIFICATIONS_PER_IP_PER_DAY}/day limit)"
            )

    # Check 6: Device-based anti-sybil (if device fingerprint provided)
    if device_fingerprint:
        stmt = select(func.count(VerificationEdge.id)).where(
            (VerificationEdge.device_fingerprint == device_fingerprint)
            & (VerificationEdge.created_at >= one_day_ago)
        )
        result = await db.execute(stmt)
        device_count = result.scalar() or 0

        if device_count >= MAX_VERIFICATIONS_PER_DEVICE_PER_DAY:
            raise AntiSybilError(
                f"Too many verifications from this device ({MAX_VERIFICATIONS_PER_DEVICE_PER_DAY}/day limit)"
            )

    # Check 7: Account age (verifier must be at least MIN_ACCOUNT_AGE_DAYS old)
    from backend.app.auth.models import User

    stmt = select(User).where(User.id == verifier_id)
    result = await db.execute(stmt)
    verifier_user = result.scalar_one_or_none()

    if not verifier_user:
        raise VerificationError(f"Verifier user {verifier_id} not found")

    account_age = (datetime.utcnow() - verifier_user.created_at).days
    if account_age < MIN_ACCOUNT_AGE_DAYS:
        raise AntiSybilError(
            f"Account must be at least {MIN_ACCOUNT_AGE_DAYS} days old to verify others (current: {account_age} days)"
        )

    logger.info(
        f"Anti-sybil checks passed for {verifier_id} verifying {verified_id}",
        extra={
            "verifier_id": verifier_id,
            "verified_id": verified_id,
            "hourly_count": hourly_count,
            "daily_count": daily_count,
            "ip_count": ip_count if ip_address else 0,
            "device_count": device_count if device_fingerprint else 0,
            "account_age_days": account_age,
        },
    )


async def verify_peer(
    verifier_id: str,
    verified_id: str,
    ip_address: str | None,
    device_fingerprint: str | None,
    notes: str | None,
    db: AsyncSession,
) -> VerificationEdge:
    """
    Verify a peer user, creating a verification edge.

    This creates a directed edge: verifier_id → verified_id with weight 1.0.
    Runs comprehensive anti-sybil checks before allowing verification.

    Args:
        verifier_id: User doing the verification
        verified_id: User being verified
        ip_address: IP address of verifier (for anti-sybil)
        device_fingerprint: Device fingerprint of verifier (for anti-sybil)
        notes: Optional verification note/reason
        db: Database session

    Returns:
        Created VerificationEdge

    Raises:
        VerificationError: If verification fails any validation

    Example:
        >>> edge = await verify_peer(
        ...     verifier_id="user123",
        ...     verified_id="user456",
        ...     ip_address="1.2.3.4",
        ...     device_fingerprint="abc123",
        ...     notes="Known trader from Telegram",
        ...     db=db
        ... )
        >>> edge.weight
        1.0
    """
    # Run all anti-sybil checks
    await anti_sybil_checks(
        verifier_id, verified_id, ip_address, device_fingerprint, db
    )

    # Verify that verified_id user exists
    from backend.app.auth.models import User

    stmt = select(User).where(User.id == verified_id)
    result = await db.execute(stmt)
    verified_user = result.scalar_one_or_none()

    if not verified_user:
        raise VerificationError(f"Verified user {verified_id} not found")

    # Create verification edge
    edge = VerificationEdge(
        id=str(uuid4()),
        verifier_id=verifier_id,
        verified_id=verified_id,
        weight=1.0,  # Default weight
        created_at=datetime.utcnow(),
        ip_address=ip_address,
        device_fingerprint=device_fingerprint,
        notes=notes,
    )

    db.add(edge)
    await db.commit()
    await db.refresh(edge)

    logger.info(
        f"Verification created: {verifier_id} → {verified_id}",
        extra={
            "verifier_id": verifier_id,
            "verified_id": verified_id,
            "weight": edge.weight,
            "has_ip": bool(ip_address),
            "has_device": bool(device_fingerprint),
        },
    )

    return edge


async def get_user_verifications(
    user_id: str, db: AsyncSession
) -> dict[str, list[VerificationEdge]]:
    """
    Get all verifications for a user (given and received).

    Args:
        user_id: User to get verifications for
        db: Database session

    Returns:
        Dict with keys:
        - "given": List of VerificationEdge where user is verifier
        - "received": List of VerificationEdge where user is verified

    Example:
        >>> verifications = await get_user_verifications("user123", db)
        >>> len(verifications["given"])
        5
        >>> len(verifications["received"])
        3
    """
    # Get verifications given by user
    stmt = select(VerificationEdge).where(VerificationEdge.verifier_id == user_id)
    result = await db.execute(stmt)
    given = result.scalars().all()

    # Get verifications received by user
    stmt = select(VerificationEdge).where(VerificationEdge.verified_id == user_id)
    result = await db.execute(stmt)
    received = result.scalars().all()

    logger.info(
        f"Retrieved verifications for {user_id}",
        extra={
            "user_id": user_id,
            "given_count": len(given),
            "received_count": len(received),
        },
    )

    return {"given": list(given), "received": list(received)}


async def calculate_influence_score(user_id: str, db: AsyncSession) -> float:
    """
    Calculate influence score for a user based on verification graph.

    Influence score formula:
    - Base: Count of received verifications (how many users verified this user)
    - Weighted: Sum of weights from all received verifications
    - Normalized: Divide by (1 + received_count) to keep score 0-1 range

    Score ranges:
    - 0.0: No verifications
    - 0.5: ~1 verification
    - 0.75: ~3 verifications
    - 0.9: ~9 verifications
    - 1.0: Asymptotic limit (many verifications)

    Args:
        user_id: User to calculate influence for
        db: Database session

    Returns:
        Influence score (0.0-1.0)

    Example:
        >>> score = await calculate_influence_score("user123", db)
        >>> score
        0.75
    """
    # Get all verifications received by user
    stmt = select(VerificationEdge).where(VerificationEdge.verified_id == user_id)
    result = await db.execute(stmt)
    received = result.scalars().all()

    if not received or len(received) == 0:
        return 0.0

    # Calculate weighted sum of verifications
    weighted_sum: float = sum(edge.weight for edge in received)
    received_count: int = len(received)

    # Normalize to 0-1 range using formula: weighted_sum / (1 + received_count)
    # This creates an asymptotic curve approaching 1.0
    influence_score: float = weighted_sum / (1 + received_count)

    logger.info(
        f"Calculated influence score for {user_id}",
        extra={
            "user_id": user_id,
            "received_count": received_count,
            "weighted_sum": weighted_sum,
            "influence_score": influence_score,
        },
    )

    return influence_score
