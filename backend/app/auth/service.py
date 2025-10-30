"""Authentication service for user management and JWT operations.

Implements PR-004: AuthN/AuthZ Core
- User creation with password hashing
- Password verification
- JWT token minting
- User authentication
"""

from datetime import datetime

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.jwt_handler import JWTHandler
from backend.app.auth.models import User
from backend.app.core.logging import get_logger

logger = get_logger(__name__)

# Argon2id password context (PR-004 spec: memory/time cost from env)
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


class AuthService:
    """Service for authentication operations."""

    def __init__(self, db: AsyncSession):
        """
        Initialize auth service.

        Args:
            db: Database session
        """
        self.db = db
        self.jwt_handler = JWTHandler()

    async def create_user(
        self,
        email: str,
        password: str,
        role: str = "user",
        telegram_user_id: str | None = None,
    ) -> User:
        """
        Create a new user with hashed password.

        Args:
            email: User email (must be unique)
            password: Plain text password (will be hashed)
            role: User role (default: "user")
            telegram_user_id: Optional Telegram user ID for bot/Mini App integration

        Returns:
            User: Created user object

        Raises:
            ValueError: If email already exists
            ValueError: If telegram_user_id already exists
            ValueError: If password too weak

        Example:
            >>> service = AuthService(db_session)
            >>> user = await service.create_user("test@example.com", "secure_password123")
            >>> assert user.email == "test@example.com"
            >>> assert user.role == "user"
        """
        # Check if email already exists
        stmt = select(User).where(User.email == email)
        result = await self.db.execute(stmt)
        existing_user = result.scalars().first()

        if existing_user:
            logger.warning(f"Attempted to create user with existing email: {email}")
            raise ValueError(f"User with email {email} already exists")

        # Check if telegram_user_id already exists (if provided)
        if telegram_user_id:
            stmt = select(User).where(User.telegram_user_id == telegram_user_id)
            result = await self.db.execute(stmt)
            existing_telegram_user = result.scalars().first()

            if existing_telegram_user:
                logger.warning(
                    f"Attempted to create user with existing Telegram ID: {telegram_user_id}"
                )
                raise ValueError(
                    f"User with Telegram ID {telegram_user_id} already exists"
                )

        # Validate password strength (basic check)
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters")

        # Hash password using Argon2id
        password_hash = pwd_context.hash(password)

        # Create user
        user = User(
            email=email,
            password_hash=password_hash,
            role=role,
            telegram_user_id=telegram_user_id,
            created_at=datetime.utcnow(),
        )

        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        logger.info(
            f"User created: {user.id}",
            extra={"user_id": user.id, "email": email, "role": role},
        )

        return user

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """
        Verify a password against its hash.

        Args:
            plain_password: Plain text password
            hashed_password: Argon2id hashed password

        Returns:
            bool: True if password matches, False otherwise

        Example:
            >>> service = AuthService(db_session)
            >>> hashed = pwd_context.hash("mypassword")
            >>> service.verify_password("mypassword", hashed)
            True
            >>> service.verify_password("wrongpassword", hashed)
            False
        """
        try:
            return bool(pwd_context.verify(plain_password, hashed_password))
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False

    async def authenticate_user(self, email: str, password: str) -> User | None:
        """
        Authenticate user by email and password.

        Args:
            email: User email
            password: Plain text password

        Returns:
            User | None: User object if authenticated, None otherwise

        Example:
            >>> service = AuthService(db_session)
            >>> user = await service.authenticate_user("test@example.com", "password123")
            >>> if user:
            ...     print(f"Authenticated: {user.email}")
        """
        # Find user by email
        stmt = select(User).where(User.email == email)
        result = await self.db.execute(stmt)
        user = result.scalars().first()

        if not user:
            logger.warning(f"Authentication failed: user not found for email {email}")
            return None

        # Verify password
        if not self.verify_password(password, user.password_hash):
            logger.warning(f"Authentication failed: invalid password for {email}")
            return None

        # Update last login timestamp
        user.last_login_at = datetime.utcnow()
        await self.db.commit()

        logger.info(
            f"User authenticated: {user.id}", extra={"user_id": user.id, "email": email}
        )

        return user

    def mint_jwt(self, user: User) -> str:
        """
        Create JWT access token for authenticated user.

        Args:
            user: User object

        Returns:
            str: JWT access token

        Example:
            >>> service = AuthService(db_session)
            >>> user = await service.authenticate_user("test@example.com", "password")
            >>> token = service.mint_jwt(user)
            >>> isinstance(token, str)
            True
        """
        token = self.jwt_handler.create_token(
            user_id=user.id,
            role=user.role,
            telegram_user_id=user.telegram_user_id if user.telegram_user_id else None,
        )

        logger.info(f"JWT token minted for user: {user.id}", extra={"user_id": user.id})

        return str(token)

    async def get_user_by_id(self, user_id: str) -> User | None:
        """
        Retrieve user by ID.

        Args:
            user_id: User ID

        Returns:
            User | None: User object if found, None otherwise

        Example:
            >>> service = AuthService(db_session)
            >>> user = await service.get_user_by_id("user_123")
            >>> if user:
            ...     print(user.email)
        """
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()


# Convenience functions for backward compatibility
def hash_password(password: str) -> str:
    """Hash password using Argon2id.

    Args:
        password: Plain text password

    Returns:
        str: Hashed password

    Example:
        >>> hashed = hash_password("mypassword")
        >>> len(hashed) > 50
        True
    """
    return str(pwd_context.hash(password))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash.

    Args:
        plain_password: Plain text password
        hashed_password: Argon2id hash

    Returns:
        bool: True if matches, False otherwise

    Example:
        >>> hashed = hash_password("test123")
        >>> verify_password("test123", hashed)
        True
        >>> verify_password("wrong", hashed)
        False
    """
    try:
        return bool(pwd_context.verify(plain_password, hashed_password))
    except Exception:
        return False
