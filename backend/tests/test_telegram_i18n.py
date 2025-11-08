"""Comprehensive tests for PR-070: Telegram Bot Localization & Content Localization.

Tests cover:
- Locale detection (Telegram profile → prefs → fallback)
- Translation loading and caching
- Nested key resolution
- Variable interpolation
- Fallback to English for missing keys
- Position failure notification templates
- Content distribution localization
- Guide localization
- Telemetry tracking
- Edge cases and error handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.telegram.i18n import (
    DEFAULT_LOCALE,
    _get_nested_value,
    _load_translations,
    clear_translations_cache,
    detect_user_locale,
    get_position_failure_template,
    get_text,
)


class TestTranslationLoading:
    """Test translation file loading and caching."""

    def test_load_english_translations(self):
        """Test loading English translations from JSON files."""
        clear_translations_cache()
        translations = _load_translations("en")

        # Verify structure
        assert isinstance(translations, dict)
        assert "commands" in translations
        assert "guides" in translations
        assert "notifications" in translations
        assert "position_failures" in translations

        # Verify commands content
        assert "start" in translations["commands"]
        assert "welcome" in translations["commands"]["start"]
        assert "Welcome" in translations["commands"]["start"]["welcome"]

    def test_load_spanish_translations(self):
        """Test loading Spanish translations from JSON files."""
        clear_translations_cache()
        translations = _load_translations("es")

        # Verify structure
        assert isinstance(translations, dict)
        assert "commands" in translations
        assert "guides" in translations
        assert "notifications" in translations
        assert "position_failures" in translations

        # Verify commands content (Spanish)
        assert "start" in translations["commands"]
        assert "welcome" in translations["commands"]["start"]
        assert "Bienvenido" in translations["commands"]["start"]["welcome"]

    def test_translations_cached(self):
        """Test that translations are cached after first load."""
        clear_translations_cache()

        # First load
        trans1 = _load_translations("en")

        # Second load (should use cache)
        trans2 = _load_translations("en")

        # Should be same object (cached)
        assert trans1 is trans2

    def test_load_invalid_locale_returns_empty(self):
        """Test loading unsupported locale returns empty dict."""
        clear_translations_cache()
        translations = _load_translations("invalid_locale")

        assert translations == {}

    def test_clear_cache(self):
        """Test clearing translations cache."""
        clear_translations_cache()

        # Load translations
        trans1 = _load_translations("en")

        # Clear cache
        clear_translations_cache()

        # Load again (should reload from disk)
        trans2 = _load_translations("en")

        # Should be different objects (cache cleared)
        assert trans1 is not trans2


class TestNestedKeyResolution:
    """Test nested key resolution with dot notation."""

    def test_get_nested_value_single_level(self):
        """Test getting value from single-level dict."""
        data = {"key": "value"}
        result = _get_nested_value(data, "key")
        assert result == "value"

    def test_get_nested_value_nested(self):
        """Test getting value from nested dict."""
        data = {"level1": {"level2": {"level3": "value"}}}
        result = _get_nested_value(data, "level1.level2.level3")
        assert result == "value"

    def test_get_nested_value_missing_key(self):
        """Test getting value for missing key returns None."""
        data = {"key": "value"}
        result = _get_nested_value(data, "missing")
        assert result is None

    def test_get_nested_value_missing_nested_key(self):
        """Test getting value for missing nested key returns None."""
        data = {"level1": {"level2": "value"}}
        result = _get_nested_value(data, "level1.missing.key")
        assert result is None

    def test_get_nested_value_non_dict(self):
        """Test getting value when intermediate key is not a dict."""
        data = {"level1": "string"}
        result = _get_nested_value(data, "level1.level2")
        assert result is None


class TestLocaleDetection:
    """Test user locale detection with fallback chain."""

    @pytest.mark.asyncio
    async def test_detect_locale_from_user_prefs(self):
        """Test locale detection from user preferences (highest priority)."""
        # Mock database session
        db = AsyncMock(spec=AsyncSession)

        # Mock user preferences
        mock_prefs = MagicMock()
        mock_prefs.locale = "es"
        mock_prefs.telegram_user_id = "123456"

        # Mock query result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_prefs
        db.execute.return_value = mock_result

        # Detect locale
        locale = await detect_user_locale(
            db=db,
            telegram_user_id="123456",
            telegram_lang_code="en",
        )

        assert locale == "es"

    @pytest.mark.asyncio
    async def test_detect_locale_from_telegram_profile(self):
        """Test locale detection from Telegram language code (second priority)."""
        # Mock database session (no prefs found)
        db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        # Detect locale
        locale = await detect_user_locale(
            db=db,
            telegram_user_id="123456",
            telegram_lang_code="es",
        )

        assert locale == "es"

    @pytest.mark.asyncio
    async def test_detect_locale_fallback_to_english(self):
        """Test locale detection fallback to English."""
        # No database, no Telegram lang code
        locale = await detect_user_locale(
            db=None,
            telegram_user_id=None,
            telegram_lang_code=None,
        )

        assert locale == DEFAULT_LOCALE

    @pytest.mark.asyncio
    async def test_detect_locale_telegram_code_with_region(self):
        """Test extracting base language from Telegram code with region."""
        locale = await detect_user_locale(
            db=None,
            telegram_user_id=None,
            telegram_lang_code="es-ES",  # Spanish (Spain)
        )

        assert locale == "es"

    @pytest.mark.asyncio
    async def test_detect_locale_unsupported_telegram_code(self):
        """Test unsupported Telegram language code fallback to English."""
        locale = await detect_user_locale(
            db=None,
            telegram_user_id=None,
            telegram_lang_code="fr",  # French (not supported)
        )

        assert locale == DEFAULT_LOCALE

    @pytest.mark.asyncio
    async def test_detect_locale_db_error_fallback_to_telegram(self):
        """Test fallback to Telegram code when database query fails."""
        # Mock database that raises exception
        db = AsyncMock(spec=AsyncSession)
        db.execute.side_effect = Exception("Database error")

        locale = await detect_user_locale(
            db=db,
            telegram_user_id="123456",
            telegram_lang_code="es",
        )

        # Should fallback to Telegram code
        assert locale == "es"


class TestGetText:
    """Test localized text retrieval with variable interpolation."""

    def test_get_text_english(self):
        """Test getting English text."""
        clear_translations_cache()
        text = get_text("commands.start.welcome", locale="en", username="John")

        assert "Welcome" in text
        assert "John" in text

    def test_get_text_spanish(self):
        """Test getting Spanish text."""
        clear_translations_cache()
        text = get_text("commands.start.welcome", locale="es", username="Juan")

        assert "Bienvenido" in text
        assert "Juan" in text

    def test_get_text_fallback_to_english(self):
        """Test fallback to English when key not found in locale."""
        clear_translations_cache()

        # Create temporary Spanish translations without a key
        with patch("backend.app.telegram.i18n._load_translations") as mock_load:
            # Spanish translations missing the key
            mock_load.side_effect = lambda locale: (
                {"commands": {"start": {}}}
                if locale == "es"
                else {"commands": {"start": {"welcome": "Welcome, {username}!"}}}
            )

            text = get_text(
                "commands.start.welcome",
                locale="es",
                username="John",
                fallback_to_english=True,
            )

            assert "Welcome" in text

    def test_get_text_missing_key_no_fallback(self):
        """Test missing key without fallback returns debug string."""
        clear_translations_cache()
        text = get_text("commands.missing.key", locale="en", fallback_to_english=False)

        assert "[MISSING:" in text

    def test_get_text_variable_interpolation(self):
        """Test variable interpolation in translated text."""
        clear_translations_cache()
        text = get_text("commands.start.welcome", locale="en", username="Alice")

        assert "Alice" in text

    def test_get_text_missing_variable(self):
        """Test missing variable in interpolation returns text without interpolation."""
        clear_translations_cache()
        # Get text without providing required variable
        text = get_text("commands.start.welcome", locale="en")

        # Should return text with placeholder (not interpolated)
        assert "{username}" in text

    def test_get_text_unsupported_locale(self):
        """Test unsupported locale uses default locale."""
        clear_translations_cache()
        text = get_text("commands.start.button_open_app", locale="invalid_locale")

        # Should use default English
        assert "Open Mini App" in text

    def test_get_text_default_locale(self):
        """Test default locale when none specified."""
        clear_translations_cache()
        text = get_text("commands.start.button_open_app")

        # Should use default English
        assert "Open Mini App" in text


class TestPositionFailureTemplates:
    """Test position failure notification templates (PR-104 integration)."""

    def test_entry_failure_template_english(self):
        """Test entry failure template in English."""
        clear_translations_cache()
        template = get_position_failure_template(
            "entry_failure",
            locale="en",
            instrument="GOLD",
            side="buy",
            price=1950.50,
            volume=0.1,
            sl=1940.00,
            tp=1970.00,
            error="Insufficient margin",
            approval_id="AP-12345",
        )

        assert "title" in template
        assert "message" in template
        assert "Manual Action Required" in template["title"]
        assert "GOLD" in template["message"]
        assert "buy" in template["message"]
        assert "1950.5" in template["message"]
        assert "Insufficient margin" in template["message"]
        assert "AP-12345" in template["message"]

    def test_exit_sl_hit_template_spanish(self):
        """Test exit SL hit template in Spanish."""
        clear_translations_cache()
        template = get_position_failure_template(
            "exit_sl_hit",
            locale="es",
            instrument="GOLD",
            side="sell",
            ticket="12345",
            entry_price=1950.00,
            current_price=1955.00,
            sl_price=1960.00,
            loss_amount=50.00,
            loss_percent=2.5,
            error="Connection timeout",
            position_id="POS-67890",
        )

        assert "title" in template
        assert "message" in template
        assert "URGENTE" in template["title"]
        assert "GOLD" in template["message"]
        assert "sell" in template["message"]
        assert "12345" in template["message"]
        assert "POS-67890" in template["message"]

    def test_exit_tp_hit_template_english(self):
        """Test exit TP hit template in English."""
        clear_translations_cache()
        template = get_position_failure_template(
            "exit_tp_hit",
            locale="en",
            instrument="SP500",
            side="buy",
            ticket="98765",
            entry_price=4500.00,
            current_price=4550.00,
            tp_price=4550.00,
            profit_amount=500.00,
            profit_percent=10.0,
            error="Order rejected by broker",
            position_id="POS-11111",
        )

        assert "title" in template
        assert "message" in template
        assert "Take Profit" in template["title"]
        assert "SP500" in template["message"]
        assert "500.0" in template["message"]
        assert "10.0" in template["message"]

    def test_position_failure_template_missing_type(self):
        """Test missing template type returns debug string."""
        clear_translations_cache()
        template = get_position_failure_template(
            "invalid_type",
            locale="en",
        )

        assert "[MISSING TEMPLATE:" in template["title"]

    def test_position_failure_template_fallback_to_english(self):
        """Test fallback to English when template not found in locale."""
        clear_translations_cache()

        # Mock Spanish translations without position_failures
        with patch("backend.app.telegram.i18n._load_translations") as mock_load:

            def side_effect(locale):
                if locale == "es":
                    return {}  # Spanish missing position_failures
                else:
                    return {
                        "position_failures": {
                            "entry_failure": {
                                "title": "Manual Action Required",
                                "message": "Failed to open position",
                            }
                        }
                    }

            mock_load.side_effect = side_effect

            template = get_position_failure_template(
                "entry_failure",
                locale="es",
            )

            # Should fallback to English
            assert "Manual Action Required" in template["title"]


class TestContentDistributionLocalization:
    """Test content distribution with localization (integration)."""

    def test_distribution_message_localized_english(self):
        """Test distribution message uses English locale."""
        clear_translations_cache()

        # Get localized header/footer
        header = get_text("notifications.distribution.header", locale="en")
        footer = get_text("notifications.distribution.footer", locale="en")

        assert "New Content" in header
        assert "Questions?" in footer

    def test_distribution_message_localized_spanish(self):
        """Test distribution message uses Spanish locale."""
        clear_translations_cache()

        # Get localized header/footer
        header = get_text("notifications.distribution.header", locale="es")
        footer = get_text("notifications.distribution.footer", locale="es")

        assert "Nuevo Contenido" in header
        assert "Preguntas?" in footer

    def test_distribution_tags_localized(self):
        """Test distribution tags are localized."""
        clear_translations_cache()

        # English tags
        gold_tag_en = get_text("notifications.distribution.gold_tag", locale="en")
        crypto_tag_en = get_text("notifications.distribution.crypto_tag", locale="en")

        assert "GOLD" in gold_tag_en
        assert "CRYPTO" in crypto_tag_en

        # Spanish tags
        gold_tag_es = get_text("notifications.distribution.gold_tag", locale="es")
        crypto_tag_es = get_text("notifications.distribution.crypto_tag", locale="es")

        assert "ORO" in gold_tag_es
        assert "CRIPTO" in crypto_tag_es


class TestGuideLocalization:
    """Test guide/tutorial content localization."""

    def test_guide_categories_localized(self):
        """Test guide categories are localized."""
        clear_translations_cache()

        # English categories
        trading_en = get_text("guides.categories.trading", locale="en")
        risk_en = get_text("guides.categories.risk", locale="en")

        assert "Trading Basics" in trading_en
        assert "Risk Management" in risk_en

        # Spanish categories
        trading_es = get_text("guides.categories.trading", locale="es")
        risk_es = get_text("guides.categories.risk", locale="es")

        assert "Trading" in trading_es  # Spanish has different wording
        assert "Riesgo" in risk_es

    def test_guide_getting_started_localized(self):
        """Test getting started guide is localized."""
        clear_translations_cache()

        # English
        title_en = get_text("guides.getting_started.title", locale="en")
        intro_en = get_text("guides.getting_started.intro", locale="en")

        assert "Getting Started" in title_en
        assert "Welcome" in intro_en

        # Spanish
        title_es = get_text("guides.getting_started.title", locale="es")
        intro_es = get_text("guides.getting_started.intro", locale="es")

        assert "Comenzando" in title_es
        assert "Bienvenido" in intro_es


class TestCommandsLocalization:
    """Test Telegram commands localization."""

    def test_start_command_localized(self):
        """Test /start command is localized."""
        clear_translations_cache()

        # English
        welcome_en = get_text("commands.start.welcome", locale="en", username="John")
        desc_en = get_text("commands.start.description", locale="en")

        assert "Welcome" in welcome_en
        assert "John" in welcome_en
        assert "real-time" in desc_en

        # Spanish
        welcome_es = get_text("commands.start.welcome", locale="es", username="Juan")
        desc_es = get_text("commands.start.description", locale="es")

        assert "Bienvenido" in welcome_es
        assert "Juan" in welcome_es
        assert "tiempo real" in desc_es

    def test_help_command_localized(self):
        """Test /help command is localized."""
        clear_translations_cache()

        # English
        title_en = get_text("commands.help.title", locale="en")
        get_text("commands.help.description", locale="en")

        assert "Help" in title_en
        assert "Commands" in title_en

        # Spanish
        title_es = get_text("commands.help.title", locale="es")
        get_text("commands.help.description", locale="es")

        assert "Ayuda" in title_es
        assert "Comandos" in title_es

    def test_shop_command_localized(self):
        """Test /shop command is localized."""
        clear_translations_cache()

        # English
        title_en = get_text("commands.shop.title", locale="en")
        premium_en = get_text("commands.shop.premium_plan", locale="en", price="49.99")

        assert "Subscription Plans" in title_en
        assert "Premium Plan" in premium_en
        assert "49.99" in premium_en

        # Spanish
        title_es = get_text("commands.shop.title", locale="es")
        premium_es = get_text("commands.shop.premium_plan", locale="es", price="49.99")

        assert "Planes de Suscripción" in title_es
        assert "Plan Premium" in premium_es
        assert "49.99" in premium_es


class TestNotificationsLocalization:
    """Test notification messages localization."""

    def test_signal_notification_localized(self):
        """Test trading signal notification is localized."""
        clear_translations_cache()

        # English
        new_signal_en = get_text("notifications.signal.new_signal", locale="en")
        instrument_en = get_text(
            "notifications.signal.instrument", locale="en", instrument="GOLD"
        )

        assert "New Trading Signal" in new_signal_en
        assert "Instrument:" in instrument_en
        assert "GOLD" in instrument_en

        # Spanish
        new_signal_es = get_text("notifications.signal.new_signal", locale="es")
        instrument_es = get_text(
            "notifications.signal.instrument", locale="es", instrument="ORO"
        )

        assert "Nueva Señal" in new_signal_es
        assert "Instrumento:" in instrument_es
        assert "ORO" in instrument_es

    def test_approval_notification_localized(self):
        """Test approval notification is localized."""
        clear_translations_cache()

        # English
        approved_en = get_text("notifications.approval.approved", locale="en")
        rejected_en = get_text("notifications.approval.rejected", locale="en")

        assert "approved" in approved_en
        assert "rejected" in rejected_en

        # Spanish
        approved_es = get_text("notifications.approval.approved", locale="es")
        rejected_es = get_text("notifications.approval.rejected", locale="es")

        assert "aprobada" in approved_es
        assert "rechazada" in rejected_es


class TestTelemetryTracking:
    """Test telemetry metrics tracking for locale usage."""

    @patch("backend.app.telegram.i18n.get_metrics")
    def test_get_text_tracks_telemetry(self, mock_get_metrics):
        """Test get_text() tracks locale usage metric."""
        clear_translations_cache()

        # Mock metrics
        mock_metrics = MagicMock()
        mock_counter = MagicMock()
        mock_metrics.telegram_locale_used_total = mock_counter
        mock_get_metrics.return_value = mock_metrics

        # Get text (should track metric)
        get_text("commands.start.welcome", locale="es", track_telemetry=True)

        # Verify metric tracked
        mock_counter.labels.assert_called_once_with(locale="es")
        mock_counter.labels().inc.assert_called_once()

    @patch("backend.app.telegram.i18n.get_metrics")
    def test_get_text_skips_telemetry_when_disabled(self, mock_get_metrics):
        """Test get_text() skips telemetry when disabled."""
        clear_translations_cache()

        # Mock metrics
        mock_metrics = MagicMock()
        mock_get_metrics.return_value = mock_metrics

        # Get text with telemetry disabled
        get_text("commands.start.welcome", locale="en", track_telemetry=False)

        # Verify metric NOT tracked
        mock_metrics.telegram_locale_used_total.assert_not_called()


class TestEdgeCasesAndErrors:
    """Test edge cases and error handling."""

    def test_get_text_empty_key(self):
        """Test get_text with empty key."""
        clear_translations_cache()
        text = get_text("", locale="en")

        assert "[MISSING:" in text

    def test_get_text_none_locale(self):
        """Test get_text with None locale uses default."""
        clear_translations_cache()
        text = get_text("commands.start.button_open_app", locale=None)

        assert "Open Mini App" in text

    def test_get_text_with_numeric_values(self):
        """Test variable interpolation with numeric values."""
        clear_translations_cache()
        text = get_text("commands.errors.rate_limit", locale="en", seconds=30)

        assert "30" in text

    def test_multiple_locales_cached_independently(self):
        """Test multiple locales are cached independently."""
        clear_translations_cache()

        # Load English
        text_en = get_text("commands.start.welcome", locale="en", username="John")

        # Load Spanish
        text_es = get_text("commands.start.welcome", locale="es", username="Juan")

        # Verify different translations
        assert "Welcome" in text_en
        assert "Bienvenido" in text_es

    def test_special_characters_in_variables(self):
        """Test variable interpolation with special characters."""
        clear_translations_cache()
        text = get_text("commands.start.welcome", locale="en", username="José García")

        assert "José García" in text

    def test_position_failure_template_missing_variable(self):
        """Test position failure template with missing variable."""
        clear_translations_cache()

        # Get template without required variables
        template = get_position_failure_template(
            "entry_failure",
            locale="en",
        )

        # Should return template with placeholders
        assert "{instrument}" in template["message"]
        assert "{side}" in template["message"]
