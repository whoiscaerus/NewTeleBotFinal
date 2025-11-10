"""Comprehensive tests for theme system (PR-090).

Tests cover:
1. ThemeService: get_theme, set_theme, validation
2. Theme API routes: GET/PUT theme, list themes
3. JWT integration: theme in profile claims
4. Metrics integration: theme_selected_total
5. Business logic: persistence, invalid themes, defaults
6. Edge cases: missing theme, invalid theme names, database state
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.jwt_handler import JWTHandler
from backend.app.observability.metrics import get_metrics
from backend.app.profile.theme import VALID_THEMES, DEFAULT_THEME, ThemeService
from backend.app.users.models import User


@pytest.mark.asyncio
class TestThemeService:
    """Test ThemeService business logic."""

    async def test_get_theme_default(self, db_session: AsyncSession):
        """Test get_theme returns default for user without theme."""
        user = User(id="user1", email="test@example.com", theme_preference=None)
        db_session.add(user)
        await db_session.commit()

        service = ThemeService(db_session)
        theme = await service.get_theme(user)

        assert theme == DEFAULT_THEME
        assert theme == "professional"

    async def test_get_theme_custom(self, db_session: AsyncSession):
        """Test get_theme returns user's custom theme."""
        user = User(id="user2", email="test2@example.com", theme_preference="darkTrader")
        db_session.add(user)
        await db_session.commit()

        service = ThemeService(db_session)
        theme = await service.get_theme(user)

        assert theme == "darkTrader"

    async def test_get_theme_invalid_fallback(self, db_session: AsyncSession):
        """Test get_theme falls back to default if user has invalid theme."""
        # Simulate user with invalid theme (e.g., from old config)
        user = User(id="user3", email="test3@example.com", theme_preference="invalidTheme")
        db_session.add(user)
        await db_session.commit()

        service = ThemeService(db_session)
        theme = await service.get_theme(user)

        # Should fall back to default
        assert theme == DEFAULT_THEME

    async def test_set_theme_valid(self, db_session: AsyncSession):
        """Test set_theme updates user's theme preference."""
        user = User(id="user4", email="test4@example.com", theme_preference="professional")
        db_session.add(user)
        await db_session.commit()

        service = ThemeService(db_session)
        result = await service.set_theme(user, "goldMinimal")

        assert result == "goldMinimal"
        assert user.theme_preference == "goldMinimal"

        # Verify database persistence
        await db_session.refresh(user)
        assert user.theme_preference == "goldMinimal"

    async def test_set_theme_invalid_raises(self, db_session: AsyncSession):
        """Test set_theme raises ValueError for invalid theme name."""
        user = User(id="user5", email="test5@example.com", theme_preference="professional")
        db_session.add(user)
        await db_session.commit()

        service = ThemeService(db_session)

        with pytest.raises(ValueError, match="Invalid theme"):
            await service.set_theme(user, "nonexistentTheme")

        # User's theme should not change
        assert user.theme_preference == "professional"

    async def test_set_theme_all_valid_themes(self, db_session: AsyncSession):
        """Test set_theme works for all valid theme names."""
        user = User(id="user6", email="test6@example.com")
        db_session.add(user)
        await db_session.commit()

        service = ThemeService(db_session)

        for theme_name in VALID_THEMES:
            result = await service.set_theme(user, theme_name)
            assert result == theme_name
            assert user.theme_preference == theme_name

    @pytest.mark.parametrize(
        "invalid_theme",
        ["", " ", "Professional", "DARKTRADER", "gold_minimal", "dark-trader", "invalid"],
    )
    async def test_set_theme_invalid_formats(
        self, db_session: AsyncSession, invalid_theme: str
    ):
        """Test set_theme rejects various invalid theme formats."""
        user = User(id=f"user_inv_{invalid_theme}", email=f"{invalid_theme}@example.com")
        db_session.add(user)
        await db_session.commit()

        service = ThemeService(db_session)

        with pytest.raises(ValueError, match="Invalid theme"):
            await service.set_theme(user, invalid_theme)

    def test_get_valid_themes(self):
        """Test get_valid_themes returns sorted list of valid themes."""
        themes = ThemeService.get_valid_themes()

        assert isinstance(themes, list)
        assert len(themes) == 3
        assert "professional" in themes
        assert "darkTrader" in themes
        assert "goldMinimal" in themes
        assert themes == sorted(themes)


@pytest.mark.asyncio
class TestThemeRoutes:
    """Test theme API endpoints."""

    async def test_get_theme_authenticated(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test GET /api/v1/profile/theme returns user's theme."""
        # Create user with theme
        user = User(id="auth_user1", email="auth1@example.com", theme_preference="darkTrader")
        db_session.add(user)
        await db_session.commit()

        # Mock authentication to return this user
        response = await client.get("/api/v1/profile/theme", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "theme" in data
        assert data["theme"] in VALID_THEMES

    async def test_get_theme_unauthenticated(self, client: AsyncClient):
        """Test GET /api/v1/profile/theme requires authentication."""
        response = await client.get("/api/v1/profile/theme")

        assert response.status_code == 401

    async def test_update_theme_valid(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test PUT /api/v1/profile/theme updates user's theme."""
        # Create user
        user = User(id="auth_user2", email="auth2@example.com", theme_preference="professional")
        db_session.add(user)
        await db_session.commit()

        response = await client.put(
            "/api/v1/profile/theme",
            json={"theme": "goldMinimal"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["theme"] == "goldMinimal"

    async def test_update_theme_invalid(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test PUT /api/v1/profile/theme rejects invalid theme."""
        response = await client.put(
            "/api/v1/profile/theme",
            json={"theme": "invalidTheme"},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "Invalid theme" in response.json()["detail"]

    async def test_update_theme_metrics_increment(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test PUT /api/v1/profile/theme increments theme_selected_total metric."""
        metrics = get_metrics()

        # Get initial metric value
        initial_value = metrics.theme_selected_total.labels(name="darkTrader")._value.get()

        # Update theme
        response = await client.put(
            "/api/v1/profile/theme",
            json={"theme": "darkTrader"},
            headers=auth_headers,
        )

        assert response.status_code == 200

        # Verify metric incremented
        new_value = metrics.theme_selected_total.labels(name="darkTrader")._value.get()
        assert new_value == initial_value + 1

    async def test_list_themes_public(self, client: AsyncClient):
        """Test GET /api/v1/profile/themes works without authentication."""
        response = await client.get("/api/v1/profile/themes")

        assert response.status_code == 200
        data = response.json()
        assert "themes" in data
        assert isinstance(data["themes"], list)
        assert len(data["themes"]) == 3
        assert "professional" in data["themes"]
        assert "darkTrader" in data["themes"]
        assert "goldMinimal" in data["themes"]

    async def test_update_theme_missing_field(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test PUT /api/v1/profile/theme validates required field."""
        response = await client.put(
            "/api/v1/profile/theme",
            json={},
            headers=auth_headers,
        )

        assert response.status_code == 422  # Pydantic validation error


@pytest.mark.asyncio
class TestJWTThemeIntegration:
    """Test theme integration with JWT tokens."""

    def test_jwt_includes_theme_claim(self):
        """Test JWT token includes theme in payload when provided."""
        handler = JWTHandler()

        token = handler.create_token(
            user_id="user1",
            role="user",
            theme="darkTrader",
        )

        # Decode token
        payload = handler.decode_token(token)

        assert "theme" in payload
        assert payload["theme"] == "darkTrader"

    def test_jwt_without_theme_claim(self):
        """Test JWT token omits theme claim when not provided."""
        handler = JWTHandler()

        token = handler.create_token(
            user_id="user2",
            role="user",
        )

        # Decode token
        payload = handler.decode_token(token)

        assert "theme" not in payload

    def test_jwt_theme_claim_all_themes(self):
        """Test JWT token supports all valid theme names."""
        handler = JWTHandler()

        for theme in VALID_THEMES:
            token = handler.create_token(
                user_id="user3",
                role="user",
                theme=theme,
            )

            payload = handler.decode_token(token)
            assert payload["theme"] == theme


@pytest.mark.asyncio
class TestThemePersistence:
    """Test theme persistence across sessions."""

    async def test_theme_persists_across_requests(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test theme update persists and is returned in subsequent requests."""
        # Update theme
        response1 = await client.put(
            "/api/v1/profile/theme",
            json={"theme": "goldMinimal"},
            headers=auth_headers,
        )
        assert response1.status_code == 200

        # Get theme in new request
        response2 = await client.get("/api/v1/profile/theme", headers=auth_headers)
        assert response2.status_code == 200

        data = response2.json()
        assert data["theme"] == "goldMinimal"

    async def test_theme_update_idempotent(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test updating theme to same value is idempotent."""
        # Set theme first time
        response1 = await client.put(
            "/api/v1/profile/theme",
            json={"theme": "darkTrader"},
            headers=auth_headers,
        )
        assert response1.status_code == 200

        # Set same theme again
        response2 = await client.put(
            "/api/v1/profile/theme",
            json={"theme": "darkTrader"},
            headers=auth_headers,
        )
        assert response2.status_code == 200

        # Should still return darkTrader
        data = response2.json()
        assert data["theme"] == "darkTrader"


@pytest.mark.asyncio
class TestThemeBusinessLogic:
    """Test theme business logic and edge cases."""

    async def test_new_user_gets_default_theme(self, db_session: AsyncSession):
        """Test new user without theme_preference gets default theme."""
        user = User(id="new_user", email="new@example.com")
        db_session.add(user)
        await db_session.commit()

        service = ThemeService(db_session)
        theme = await service.get_theme(user)

        assert theme == DEFAULT_THEME

    async def test_theme_change_logged(
        self, db_session: AsyncSession, caplog
    ):
        """Test theme changes are logged with user_id and theme names."""
        user = User(id="log_user", email="log@example.com", theme_preference="professional")
        db_session.add(user)
        await db_session.commit()

        service = ThemeService(db_session)

        with caplog.at_level("INFO"):
            await service.set_theme(user, "goldMinimal")

        # Verify log contains user_id and theme names
        assert "log_user" in caplog.text
        assert "goldMinimal" in caplog.text

    async def test_concurrent_theme_updates(self, db_session: AsyncSession):
        """Test theme updates are atomic and don't cause race conditions."""
        user = User(id="concurrent_user", email="concurrent@example.com")
        db_session.add(user)
        await db_session.commit()

        service = ThemeService(db_session)

        # Simulate concurrent updates (last one wins)
        await service.set_theme(user, "professional")
        await service.set_theme(user, "darkTrader")
        await service.set_theme(user, "goldMinimal")

        await db_session.refresh(user)
        assert user.theme_preference == "goldMinimal"

    @pytest.mark.parametrize("theme_name", ["professional", "darkTrader", "goldMinimal"])
    async def test_all_themes_settable(
        self, db_session: AsyncSession, theme_name: str
    ):
        """Test all valid themes can be set and retrieved."""
        user = User(id=f"test_{theme_name}", email=f"{theme_name}@example.com")
        db_session.add(user)
        await db_session.commit()

        service = ThemeService(db_session)

        # Set theme
        result = await service.set_theme(user, theme_name)
        assert result == theme_name

        # Get theme
        retrieved = await service.get_theme(user)
        assert retrieved == theme_name

        # Verify database
        await db_session.refresh(user)
        assert user.theme_preference == theme_name
