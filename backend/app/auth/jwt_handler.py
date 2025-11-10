"""JWT token handler for authentication."""

from datetime import UTC, datetime, timedelta
from typing import Any, cast

import jwt

from backend.app.core.settings import settings


class JWTHandler:
    """Handle JWT token creation and validation."""

    def __init__(self) -> None:
        """Initialize JWT handler with settings."""
        self.secret_key = settings.security.jwt_secret_key
        self.algorithm = settings.security.jwt_algorithm
        self.expiration_hours = settings.security.jwt_expiration_hours

    def create_token(
        self,
        user_id: str,
        role: str = "user",
        telegram_user_id: str | None = None,
        audience: str | None = None,
        expires_at: datetime | None = None,
        expires_delta: timedelta | None = None,
        jti: str | None = None,
        theme: str | None = None,
    ) -> str:
        """
        Create JWT access token.

        Args:
            user_id: User ID to encode in token
            role: User role (default: "user")
            telegram_user_id: Optional Telegram user ID
            audience: Optional audience claim
            expires_at: Optional explicit expiration time
            expires_delta: Optional expiration delta (takes precedence over expires_at)
            jti: Optional JWT ID (unique identifier for token)
            theme: Optional user theme preference (PR-090)

        Returns:
            Encoded JWT token string

        Example:
            >>> handler = JWTHandler()
            >>> token = handler.create_token(user_id="123", role="admin", theme="darkTrader")
            >>> isinstance(token, str)
            True
        """
        # Determine expiration time
        if expires_delta is not None:
            expire = datetime.now(UTC) + expires_delta
        elif expires_at is not None:
            expire = expires_at
        else:
            expire = datetime.now(UTC) + timedelta(hours=self.expiration_hours)

        # Build payload
        payload = {
            "sub": user_id,
            "role": role,
            "exp": expire,
            "iat": datetime.now(UTC),
        }

        # Add optional claims
        if telegram_user_id:
            payload["telegram_user_id"] = telegram_user_id
        if audience:
            payload["aud"] = audience
        if jti:
            payload["jti"] = jti
        if theme:
            payload["theme"] = theme  # PR-090: Include theme in JWT for SSR/CSR consistency

        # Encode token
        token = jwt.encode(
            payload,
            self.secret_key,
            algorithm=self.algorithm,
        )
        return token

    def decode_token(self, token: str) -> dict[str, Any]:
        """
        Decode and validate JWT token.

        Args:
            token: JWT token string

        Returns:
            Decoded token payload

        Raises:
            ValueError: If token is expired or invalid

        Example:
            >>> handler = JWTHandler()
            >>> token = handler.create_token(user_id="123")
            >>> payload = handler.decode_token(token)
            >>> payload["sub"]
            '123'
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
            )
            return cast(dict[str, Any], payload)
        except jwt.ExpiredSignatureError as err:
            raise ValueError("Token expired") from err
        except jwt.InvalidTokenError as err:
            raise ValueError("Invalid token") from err

    def get_user_id(self, token: str) -> str:
        """
        Extract user ID from token.

        Args:
            token: JWT token string

        Returns:
            User ID from token subject claim

        Raises:
            ValueError: If token is invalid or expired
        """
        payload = self.decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("Token missing user ID (sub claim)")
        return cast(str, user_id)

    def get_role(self, token: str) -> str:
        """
        Extract role from token.

        Args:
            token: JWT token string

        Returns:
            User role from token

        Raises:
            ValueError: If token is invalid or expired
        """
        payload = self.decode_token(token)
        role = payload.get("role", "user")
        return cast(str, role)
