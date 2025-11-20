"""JWT and password utilities."""

from datetime import UTC, datetime, timedelta
from typing import Any, cast

import jwt
from passlib.context import CryptContext

from backend.app.core.settings import settings

# Password hashing
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash password using Argon2."""
    # passlib's hash may be typed as Any in stubs — cast to str for mypy
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify password against hash."""
    # cast to bool to satisfy static typing if stubs are imprecise
    return pwd_context.verify(plain, hashed)


def create_access_token(
    subject: str, role: str, expires_delta: timedelta | None = None
) -> str:
    """Create JWT access token."""
    if expires_delta is None:
        expires_delta = timedelta(hours=settings.security.jwt_expiration_hours)

    expire = datetime.now(UTC) + expires_delta
    payload = {
        "sub": subject,
        "role": role,
        "exp": expire,
        "iat": datetime.now(UTC),
    }

    token = jwt.encode(
        payload,
        settings.security.jwt_secret_key,
        algorithm=settings.security.jwt_algorithm,
    )
    return token


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate JWT token."""
    try:
        payload = jwt.decode(
            token,
            settings.security.jwt_secret_key,
            algorithms=[settings.security.jwt_algorithm],
        )
        # jwt.decode has imprecise return typing in some stubs; cast to dict
        return cast(dict[str, Any], payload)
    except jwt.ExpiredSignatureError as err:
        raise ValueError("Token expired") from err
    except jwt.InvalidTokenError as err:
        raise ValueError("Invalid token") from err
