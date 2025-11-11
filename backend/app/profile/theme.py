"""Theme service for custom client theming.

Provides per-user theme persistence and management:
- Professional (light, corporate)
- Dark Trader (dark, high contrast)
- Gold Minimal (dark, gold accents)
"""

import logging
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.users.models import User

logger = logging.getLogger(__name__)

# Valid theme names
ThemeName = Literal["professional", "darkTrader", "goldMinimal"]
VALID_THEMES: set[str] = {"professional", "darkTrader", "goldMinimal"}
DEFAULT_THEME: ThemeName = "professional"


class ThemeService:
    """Service for managing user theme preferences."""

    def __init__(self, db: AsyncSession):
        """Initialize theme service.

        Args:
            db: Database session
        """
        self.db = db

    async def get_theme(self, user: User) -> ThemeName:
        """Get user's current theme preference.

        Args:
            user: User object

        Returns:
            ThemeName: Current theme name (default: professional)

        Example:
            >>> theme = await service.get_theme(user)
            >>> assert theme in ["professional", "darkTrader", "goldMinimal"]
        """
        theme = user.theme_preference or DEFAULT_THEME

        # Validate theme is still valid (in case of config changes)
        if theme not in VALID_THEMES:
            logger.warning(
                f"User {user.id} has invalid theme '{theme}', falling back to {DEFAULT_THEME}"
            )
            theme = DEFAULT_THEME

        return theme  # type: ignore

    async def set_theme(self, user: User, theme_name: str) -> ThemeName:
        """Set user's theme preference.

        Args:
            user: User object
            theme_name: Theme name to set

        Returns:
            ThemeName: The theme that was set

        Raises:
            ValueError: If theme_name is not valid

        Example:
            >>> theme = await service.set_theme(user, "darkTrader")
            >>> assert theme == "darkTrader"
        """
        # Validate theme name
        if theme_name not in VALID_THEMES:
            raise ValueError(
                f"Invalid theme '{theme_name}'. Valid themes: {', '.join(sorted(VALID_THEMES))}"
            )

        # Update user's theme preference
        old_theme = user.theme_preference
        user.theme_preference = theme_name

        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        logger.info(
            f"Theme updated for user {user.id}: {old_theme} -> {theme_name}",
            extra={
                "user_id": user.id,
                "old_theme": old_theme,
                "new_theme": theme_name,
            },
        )

        return theme_name  # type: ignore

    @staticmethod
    def get_valid_themes() -> list[str]:
        """Get list of valid theme names.

        Returns:
            list[str]: Sorted list of valid theme names
        """
        return sorted(VALID_THEMES)
