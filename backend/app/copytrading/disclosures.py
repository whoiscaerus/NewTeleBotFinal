"""
PR-046: Copy-Trading Risk & Compliance Controls - Disclosure versioning and consent management

This module manages versioned disclosures and user consent tracking:
- Create/manage disclosure versions
- Track user acceptance with immutable audit trail (PR-008)
- Validate current disclosure acceptance
- Handle consent upgrades

All consent acceptance is logged immutably for compliance.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.app.copytrading.service import Disclosure, UserConsent

try:
    from prometheus_client import Counter

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    Counter = None  # type: ignore

logger = logging.getLogger(__name__)

# Prometheus metrics
copy_consent_counter: Any
if PROMETHEUS_AVAILABLE:
    copy_consent_counter = Counter(
        "copy_consent_signed_total",
        "Total number of consent acceptances recorded",
        ["version", "user_tier"],
    )
else:
    copy_consent_counter = None

# Standard disclosure versions
DISCLOSURE_VERSION_1_0 = "1.0"
CURRENT_DISCLOSURE_VERSION = DISCLOSURE_VERSION_1_0

# Standard disclosure text (can be updated in database)
DEFAULT_DISCLOSURE_TEXT_V1 = """
# Copy-Trading Risk Disclosure v1.0

## Warning: Automated Trading Carries Risk

By enabling copy-trading, you acknowledge that:

### 1. RISK OF LOSS
- Copy-trading automat ically executes trades without your approval
- ALL TRADES INVOLVE SUBSTANTIAL RISK OF LOSS
- You could lose some or all of your investment

### 2. LEVERAGE & MULTIPLIED LOSSES
- Leverage amplifies both gains AND losses
- Leverage up to {max_leverage}x is permitted
- You could lose more than your initial investment

### 3. DAILY LOSS LIMITS
- Trading auto-pauses if you lose more than {daily_stop}% in one day
- This is a safety measure to protect your account

### 4. NO GUARANTEES
- Past performance does not guarantee future results
- Even profitable strategies can lose money
- Market conditions change rapidly

### 5. ACCOUNT REQUIREMENTS
- You must maintain minimum equity of £{min_equity}
- Account must be verified and linked to broker
- Risk parameters are non-negotiable

### 6. AUTOMATIC PAUSE ON BREACH
- Copy-trading pauses if risk parameters violated
- Breaches include: max leverage, max trade risk, daily losses, total exposure
- Paused account auto-resumes after 24 hours or manual override

### 7. NO ADVICE
- Copy-trading is NOT financial advice
- You are responsible for your trading decisions
- Consult a financial advisor before trading

## I ACKNOWLEDGE AND ACCEPT THESE RISKS
By checking "Accept", I confirm that:
- I have read and understood all risks
- I am financially able to lose my investment
- I make my own investment decisions
- I understand leverage and its risks
"""


class DisclosureService:
    """
    Manages versioned disclosures and user consent tracking.
    All consent acceptance is immutable and audited (PR-008).
    """

    def __init__(self, audit_service=None):
        """
        Initialize disclosure service.

        Args:
            audit_service: Service for audit logging (PR-008)
        """
        self.audit_service = audit_service

    async def create_disclosure(
        self,
        db: AsyncSession,
        version: str,
        title: str,
        content: str,
        effective_date: datetime,
        is_active: bool = True,
    ) -> dict:
        """
        Create a new disclosure version.

        Args:
            db: Database session
            version: Version string (e.g., "1.0", "1.1", "2.0")
            title: Human-readable title
            content: Full disclosure text (markdown)
            effective_date: When this disclosure becomes active
            is_active: Whether this is the current version

        Returns:
            Created disclosure details

        Example:
            >>> disclosure = await service.create_disclosure(
            ...     db, "1.0", "Copy-Trading Risk Disclosure v1.0",
            ...     "By enabling copy-trading...", datetime.utcnow()
            ... )
        """
        # If making this active, deactivate others
        if is_active:
            stmt = select(Disclosure).where(Disclosure.is_active == True)
            result = await db.execute(stmt)
            current_disclosures = result.scalars().all()
            for d in current_disclosures:
                d.is_active = False

        disclosure = Disclosure(
            version=version,
            title=title,
            content=content,
            effective_date=effective_date,
            is_active=is_active,
        )

        db.add(disclosure)
        await db.commit()
        await db.refresh(disclosure)

        logger.info(f"Created disclosure version {version}")

        return {
            "id": disclosure.id,
            "version": disclosure.version,
            "title": disclosure.title,
            "is_active": disclosure.is_active,
            "effective_date": disclosure.effective_date.isoformat(),
        }

    async def get_current_disclosure(
        self,
        db: AsyncSession,
    ) -> Optional[dict]:
        """
        Get the current active disclosure.

        Args:
            db: Database session

        Returns:
            Current disclosure dict or None if not found
        """
        stmt = (
            select(Disclosure)
            .where(Disclosure.is_active == True)
            .order_by(Disclosure.created_at.desc())
        )
        result = await db.execute(stmt)
        disclosure = result.scalar_one_or_none()

        if not disclosure:
            return None

        return {
            "id": disclosure.id,
            "version": disclosure.version,
            "title": disclosure.title,
            "content": disclosure.content,
            "effective_date": disclosure.effective_date.isoformat(),
        }

    async def get_disclosure_by_version(
        self,
        db: AsyncSession,
        version: str,
    ) -> Optional[dict]:
        """
        Get specific disclosure version.

        Args:
            db: Database session
            version: Version string (e.g., "1.0")

        Returns:
            Disclosure dict or None
        """
        stmt = select(Disclosure).where(Disclosure.version == version)
        result = await db.execute(stmt)
        disclosure = result.scalar_one_or_none()

        if not disclosure:
            return None

        return {
            "id": disclosure.id,
            "version": disclosure.version,
            "title": disclosure.title,
            "content": disclosure.content,
            "effective_date": disclosure.effective_date.isoformat(),
        }

    async def record_consent(
        self,
        db: AsyncSession,
        user_id: str,
        disclosure_version: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict:
        """
        Record user's acceptance of disclosure (immutable audit trail).

        Args:
            db: Database session
            user_id: User identifier
            disclosure_version: Version accepted (e.g., "1.0")
            ip_address: Client IP address (for audit)
            user_agent: Client user agent (for audit)

        Returns:
            Consent record details

        Example:
            >>> consent = await service.record_consent(
            ...     db, user_id, "1.0",
            ...     ip_address="192.168.1.1",
            ...     user_agent="Mozilla/5.0..."
            ... )
        """
        # Verify disclosure exists
        stmt = select(Disclosure).where(Disclosure.version == disclosure_version)
        result = await db.execute(stmt)
        disclosure = result.scalar_one_or_none()

        if not disclosure:
            raise ValueError(f"Disclosure version {disclosure_version} not found")

        # Create consent record (immutable)
        consent = UserConsent(
            user_id=user_id,
            disclosure_version=disclosure_version,
            accepted_at=datetime.utcnow(),
            ip_address=ip_address,
            user_agent=user_agent,
        )

        db.add(consent)
        await db.commit()
        await db.refresh(consent)

        # Increment consent counter metric
        if copy_consent_counter:
            try:
                user_tier = getattr(
                    consent, "user_tier", "unknown"
                )  # Try to get tier, default to 'unknown'
                copy_consent_counter.labels(
                    version=disclosure_version, user_tier=user_tier
                ).inc()
            except Exception as e:
                logger.error(f"Failed to increment Prometheus metric: {e}")

        logger.info(
            f"User {user_id} accepted disclosure v{disclosure_version}",
            extra={"user_id": user_id, "version": disclosure_version, "ip": ip_address},
        )

        # Log to audit trail
        if self.audit_service:
            try:
                await self.audit_service.log_event(
                    user_id=user_id,
                    action="disclosure_accepted",
                    details={
                        "version": disclosure_version,
                        "ip_address": ip_address,
                        "user_agent": user_agent,
                        "timestamp": consent.accepted_at.isoformat(),
                    },
                )
            except Exception as e:
                logger.error(f"Failed to log audit event: {e}")

        return {
            "id": consent.id,
            "user_id": user_id,
            "disclosure_version": disclosure_version,
            "accepted_at": consent.accepted_at.isoformat(),
            "ip_address": ip_address,
        }

    async def has_accepted_version(
        self,
        db: AsyncSession,
        user_id: str,
        disclosure_version: str,
    ) -> bool:
        """
        Check if user has accepted specific disclosure version.

        Args:
            db: Database session
            user_id: User identifier
            disclosure_version: Version to check (e.g., "1.0")

        Returns:
            True if user accepted this version, False otherwise
        """
        stmt = select(UserConsent).where(
            (UserConsent.user_id == user_id)
            & (UserConsent.disclosure_version == disclosure_version)
        )
        result = await db.execute(stmt)
        consent = result.scalar_one_or_none()

        return consent is not None

    async def has_accepted_current(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> bool:
        """
        Check if user has accepted current disclosure version.

        Args:
            db: Database session
            user_id: User identifier

        Returns:
            True if user accepted current version, False otherwise
        """
        # Get current version
        current = await self.get_current_disclosure(db)
        if not current:
            return False

        return await self.has_accepted_version(db, user_id, current["version"])

    async def get_user_consent_history(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> list:
        """
        Get user's complete consent history (immutable audit trail).

        Args:
            db: Database session
            user_id: User identifier

        Returns:
            List of consent records in order of acceptance
        """
        stmt = (
            select(UserConsent)
            .where(UserConsent.user_id == user_id)
            .order_by(UserConsent.accepted_at.asc())
        )
        result = await db.execute(stmt)
        consents = result.scalars().all()

        return [
            {
                "id": c.id,
                "disclosure_version": c.disclosure_version,
                "accepted_at": c.accepted_at.isoformat(),
                "ip_address": c.ip_address,
            }
            for c in consents
        ]

    async def require_current_consent(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> tuple[bool, Optional[str]]:
        """
        Check if user needs to accept new disclosure version.

        Args:
            db: Database session
            user_id: User identifier

        Returns:
            Tuple of (consent_current: bool, required_version: str or None)
            If consent_current is False, required_version contains new version to accept.
        """
        current_disclosure = await self.get_current_disclosure(db)
        if not current_disclosure:
            return True, None  # No disclosure, no need to accept

        has_accepted = await self.has_accepted_current(db, user_id)
        if has_accepted:
            return True, None

        return False, current_disclosure["version"]
