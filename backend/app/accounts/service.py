"""
Account Linking Service - Link Telegram Users to MT5 Accounts

Implements:
- Account linking with verification
- Multi-account support per user
- Primary account selection
- Account info caching
- MT5 connection verification
"""

import logging
from datetime import datetime, timedelta
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.accounts.models import AccountInfo, AccountLink
from backend.app.core.errors import NotFoundError, ValidationError
from backend.app.trading.mt5.session import MT5SessionManager

logger = logging.getLogger(__name__)


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================


class AccountLinkCreate(BaseModel):
    """Request to link new MT5 account."""

    mt5_account_id: str = Field(
        ..., min_length=1, max_length=255, description="MT5 account number"
    )
    mt5_login: str = Field(
        ..., min_length=1, max_length=255, description="MT5 login for connection"
    )


class AccountLinkUpdate(BaseModel):
    """Request to update account link."""

    is_primary: bool = Field(default=False, description="Set as primary account")


class AccountLinkOut(BaseModel):
    """Response with account link details."""

    id: str
    mt5_account_id: str
    broker_name: str
    is_primary: bool
    verified_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class AccountInfoOut(BaseModel):
    """Current account info snapshot."""

    balance: float | None
    equity: float | None
    free_margin: float | None
    margin_used: float | None
    margin_level: float | None
    drawdown_percent: float | None
    open_positions_count: int
    last_updated: datetime

    class Config:
        from_attributes = True


# ============================================================================
# SERVICE
# ============================================================================


class AccountLinkingService:
    """
    Manages account linking and verification.

    Handles:
    - Linking new accounts with MT5 verification
    - Multi-account management per user
    - Account info caching and refresh
    - Primary account selection
    """

    def __init__(self, db_session: AsyncSession, mt5_manager: MT5SessionManager):
        """
        Initialize service.

        Args:
            db_session: AsyncSession for database operations
            mt5_manager: MT5SessionManager for connection verification
        """
        self.db = db_session
        self.mt5 = mt5_manager
        self.cache_ttl = timedelta(seconds=30)

    async def link_account(
        self,
        user_id: str,
        mt5_account_id: str,
        mt5_login: str,
    ) -> AccountLink:
        """
        Link a new MT5 account to user.

        Verifies account exists and is accessible before creating link.

        Args:
            user_id: Telegram user ID
            mt5_account_id: MT5 account number
            mt5_login: MT5 login for connection

        Returns:
            Created AccountLink model

        Raises:
            ValidationError: If account invalid or not accessible
            NotFoundError: If user not found
        """
        try:
            # Verify user exists
            from backend.app.auth.models import User

            user = await self.db.get(User, user_id)
            if not user:
                raise NotFoundError(f"User not found: {user_id}")

            # Check account doesn't already exist for this user
            existing = await self.db.execute(
                select(AccountLink).where(
                    (AccountLink.user_id == user_id)
                    & (AccountLink.mt5_account_id == mt5_account_id)
                )
            )
            if existing.scalar():
                raise ValidationError(f"Account already linked: {mt5_account_id}")

            # Verify MT5 account is accessible
            logger.info(
                f"Verifying MT5 account: {mt5_account_id}", extra={"user_id": user_id}
            )
            is_valid = await self._verify_mt5_account(mt5_login, mt5_account_id)
            if not is_valid:
                raise ValidationError(f"MT5 account not accessible: {mt5_account_id}")

            # Create link
            link = AccountLink(
                id=str(uuid4()),
                user_id=user_id,
                mt5_account_id=mt5_account_id,
                mt5_login=mt5_login,
                broker_name="MetaTrader5",
                verified_at=datetime.utcnow(),
            )

            # If first account, make it primary
            count = await self.db.execute(
                select(AccountLink).where(AccountLink.user_id == user_id)
            )
            if len(count.scalars().all()) == 0:
                link.is_primary = True

            self.db.add(link)
            await self.db.commit()
            await self.db.refresh(link)

            logger.info(
                f"Account linked: {mt5_account_id}",
                extra={
                    "user_id": user_id,
                    "account_id": link.id,
                    "is_primary": link.is_primary,
                },
            )

            return link

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error linking account: {e}", exc_info=True)
            raise

    async def get_account(self, account_link_id: str) -> AccountLink:
        """Get account link by ID."""
        link = await self.db.get(AccountLink, account_link_id)
        if not link:
            raise NotFoundError(f"Account link not found: {account_link_id}")
        return link

    async def get_user_accounts(self, user_id: str) -> list[AccountLink]:
        """Get all linked accounts for user."""
        result = await self.db.execute(
            select(AccountLink)
            .where(AccountLink.user_id == user_id)
            .order_by(AccountLink.is_primary.desc(), AccountLink.created_at)
        )
        return result.scalars().all()

    async def get_primary_account(self, user_id: str) -> AccountLink | None:
        """Get user's primary account."""
        result = await self.db.execute(
            select(AccountLink).where(
                (AccountLink.user_id == user_id) & (AccountLink.is_primary is True)
            )
        )
        return result.scalar()

    async def set_primary_account(
        self, user_id: str, account_link_id: str
    ) -> AccountLink:
        """
        Set account as primary for user.

        Unsets previous primary.

        Args:
            user_id: User ID
            account_link_id: Account to make primary

        Returns:
            Updated AccountLink

        Raises:
            NotFoundError: If account not found or doesn't belong to user
        """
        try:
            link = await self.get_account(account_link_id)
            if link.user_id != user_id:
                raise ValidationError("Account does not belong to user")

            # Unset previous primary
            await self.db.execute(
                select(AccountLink).where(
                    (AccountLink.user_id == user_id) & (AccountLink.is_primary is True)
                )
            )
            for row in (
                await self.db.execute(
                    select(AccountLink).where(AccountLink.user_id == user_id)
                )
            ).scalars():
                row.is_primary = False

            # Set new primary
            link.is_primary = True
            self.db.add(link)
            await self.db.commit()
            await self.db.refresh(link)

            logger.info(
                "Primary account updated",
                extra={"user_id": user_id, "account_id": account_link_id},
            )

            return link

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error setting primary account: {e}", exc_info=True)
            raise

    async def unlink_account(self, user_id: str, account_link_id: str) -> bool:
        """
        Unlink account from user.

        Args:
            user_id: User ID
            account_link_id: Account to unlink

        Returns:
            True if unlinked successfully

        Raises:
            NotFoundError: If account not found
            ValidationError: If trying to unlink only account
        """
        try:
            link = await self.get_account(account_link_id)
            if link.user_id != user_id:
                raise ValidationError("Account does not belong to user")

            # Check if only account (can't remove all)
            accounts = await self.get_user_accounts(user_id)
            if len(accounts) == 1:
                raise ValidationError("Cannot unlink only account")

            await self.db.delete(link)
            await self.db.commit()

            logger.info(
                "Account unlinked",
                extra={"user_id": user_id, "account_id": account_link_id},
            )

            return True

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error unlinking account: {e}", exc_info=True)
            raise

    async def get_account_info(
        self, account_link_id: str, force_refresh: bool = False
    ) -> AccountInfo:
        """
        Get account info snapshot.

        Uses cached info if available (30s TTL), otherwise fetches fresh.

        Args:
            account_link_id: Account link ID
            force_refresh: Skip cache and fetch fresh

        Returns:
            AccountInfo model

        Raises:
            NotFoundError: If account not found
        """
        link = await self.get_account(account_link_id)

        # Check cache
        if not force_refresh:
            result = await self.db.execute(
                select(AccountInfo).where(
                    AccountInfo.account_link_id == account_link_id
                )
            )
            info = result.scalar()
            if info:
                age = datetime.utcnow() - info.last_updated
                if age < self.cache_ttl:
                    logger.info(
                        f"Account info from cache (age: {age.total_seconds():.1f}s)"
                    )
                    return info

        # Fetch fresh from MT5
        try:
            logger.info(f"Fetching fresh account info for {link.mt5_account_id}")
            account_data = await self.mt5.get_account_info(link.mt5_login)

            if not account_data:
                raise ValidationError("MT5 account info not available")

            # Update or create AccountInfo
            info = await self.db.execute(
                select(AccountInfo).where(
                    AccountInfo.account_link_id == account_link_id
                )
            )
            info_obj = info.scalar()

            if not info_obj:
                info_obj = AccountInfo(
                    id=str(uuid4()),
                    account_link_id=account_link_id,
                )
                self.db.add(info_obj)

            # Update fields from MT5
            info_obj.balance = account_data.get("balance")
            info_obj.equity = account_data.get("equity")
            info_obj.free_margin = account_data.get("free_margin")
            info_obj.margin_used = account_data.get("margin_used")
            info_obj.margin_level = account_data.get("margin_level")
            info_obj.open_positions_count = account_data.get("open_positions", 0)

            # Calculate drawdown
            if info_obj.equity and info_obj.balance:
                drawdown = (info_obj.balance - info_obj.equity) / info_obj.balance * 100
                info_obj.drawdown_percent = drawdown

            info_obj.last_updated = datetime.utcnow()

            self.db.add(info_obj)
            await self.db.commit()
            await self.db.refresh(info_obj)

            logger.info(
                "Account info updated",
                extra={
                    "account_id": account_link_id,
                    "equity": info_obj.equity,
                    "drawdown": info_obj.drawdown_percent,
                },
            )

            return info_obj

        except Exception as e:
            logger.error(f"Error fetching account info: {e}", exc_info=True)
            raise

    async def _verify_mt5_account(self, mt5_login: str, mt5_account_id: str) -> bool:
        """
        Verify MT5 account is accessible.

        Attempts connection and checks account number matches.

        Args:
            mt5_login: MT5 login
            mt5_account_id: Expected account number

        Returns:
            True if account verified and accessible
        """
        try:
            account_info = await self.mt5.get_account_info(mt5_login)
            if not account_info:
                logger.warning(f"MT5 account not accessible: {mt5_login}")
                return False

            # Verify account number matches
            if str(account_info.get("account")) != mt5_account_id:
                logger.warning(
                    f"MT5 account number mismatch: expected={mt5_account_id}, got={account_info.get('account')}"
                )
                return False

            logger.info(f"MT5 account verified: {mt5_account_id}")
            return True

        except Exception as e:
            logger.warning(f"Error verifying MT5 account: {e}")
            return False
