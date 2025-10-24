"""Shared validators for Pydantic schemas."""

import re

from pydantic import ConfigDict


class UUIDValidator:
    """Validator for UUID strings."""

    @staticmethod
    def validate_uuid(value: str) -> str:
        """Validate UUID format (v4).

        Args:
            value: UUID string

        Returns:
            str: Validated UUID

        Raises:
            ValueError: If not valid UUID format
        """
        uuid_pattern = (
            r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
        )
        if not re.match(uuid_pattern, value.lower()):
            raise ValueError("Invalid UUID format (must be v4)")
        return value


class EmailValidator:
    """Validator for email addresses."""

    @staticmethod
    def validate_email(value: str) -> str:
        """Validate email format.

        Args:
            value: Email address

        Returns:
            str: Validated email (lowercased)

        Raises:
            ValueError: If not valid email format
        """
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_pattern, value):
            raise ValueError("Invalid email format")
        return value.lower()


class InstrumentValidator:
    """Validator for trading instruments (symbols)."""

    # Valid instruments (extended in later PRs)
    VALID_INSTRUMENTS = {
        "EURUSD",
        "GBPUSD",
        "USDJPY",
        "XAUUSD",
        "XAGUSD",
        "CRUDE",
        "NATGAS",
    }

    @staticmethod
    def validate_instrument(value: str) -> str:
        """Validate trading instrument symbol.

        Args:
            value: Instrument symbol (e.g., 'EURUSD')

        Returns:
            str: Validated instrument (uppercase)

        Raises:
            ValueError: If not a known instrument
        """
        upper_value = value.upper()
        if upper_value not in InstrumentValidator.VALID_INSTRUMENTS:
            allowed = ", ".join(sorted(InstrumentValidator.VALID_INSTRUMENTS))
            raise ValueError(f"Unknown instrument. Allowed: {allowed}")
        return upper_value


class PriceValidator:
    """Validator for price values."""

    @staticmethod
    def validate_price(value: float) -> float:
        """Validate price is positive and reasonable.

        Args:
            value: Price value

        Returns:
            float: Validated price

        Raises:
            ValueError: If price invalid
        """
        if value <= 0:
            raise ValueError("Price must be positive")
        if value > 1_000_000:
            raise ValueError("Price exceeds maximum (1,000,000)")
        return value


class RoleValidator:
    """Validator for user roles."""

    VALID_ROLES = {"OWNER", "ADMIN", "USER"}

    @staticmethod
    def validate_role(value: str) -> str:
        """Validate user role.

        Args:
            value: Role name

        Returns:
            str: Validated role (uppercase)

        Raises:
            ValueError: If not a known role
        """
        upper_value = value.upper()
        if upper_value not in RoleValidator.VALID_ROLES:
            allowed = ", ".join(sorted(RoleValidator.VALID_ROLES))
            raise ValueError(f"Invalid role. Allowed: {allowed}")
        return upper_value


class SideValidator:
    """Validator for trade side (buy/sell)."""

    VALID_SIDES = {"BUY", "SELL"}

    @staticmethod
    def validate_side(value: str) -> str:
        """Validate trade side.

        Args:
            value: Side value ('BUY' or 'SELL')

        Returns:
            str: Validated side (uppercase)

        Raises:
            ValueError: If not valid side
        """
        upper_value = value.upper()
        if upper_value not in SideValidator.VALID_SIDES:
            raise ValueError("Invalid side. Must be BUY or SELL")
        return upper_value


# Pydantic v2 configuration for strict mode
STRICT_CONFIG = ConfigDict(
    validate_assignment=True,
    validate_default=True,
    str_strip_whitespace=True,
    extra="forbid",  # Don't allow extra fields
)
