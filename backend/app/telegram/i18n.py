"""Telegram bot internationalization (i18n) loader.

Provides localization for bot commands, responses, content distribution, and notifications.
Supports locale detection from Telegram profile and user preferences with fallback to English.

Flow:
    1. Detect user locale (Telegram profile → user prefs → fallback to English)
    2. Load translations from content/locales/{locale}/*.json
    3. Support nested keys, pluralization, and variable interpolation
    4. Track telemetry for locale usage

Example:
    >>> from backend.app.telegram.i18n import get_text, detect_user_locale
    >>> locale = detect_user_locale(telegram_user_id="123456", telegram_lang_code="es")
    >>> text = get_text("commands.start.welcome", locale, username="John")
    >>> print(text)  # "¡Bienvenido, John!"
"""

import json
import logging
from pathlib import Path
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import select

from backend.app.observability.metrics import get_metrics

logger = logging.getLogger(__name__)

# Default locale and supported locales
DEFAULT_LOCALE = "en"
SUPPORTED_LOCALES = ["en", "es"]

# Cache for loaded translations
_translations_cache: dict[str, dict[str, Any]] = {}


def _load_translations(locale: str) -> dict[str, Any]:
    """Load translations for a specific locale from JSON files.

    Args:
        locale: Locale code (e.g., "en", "es")

    Returns:
        Dictionary of translations with nested keys

    Example:
        >>> translations = _load_translations("en")
        >>> translations["commands"]["start"]["welcome"]
        "Welcome, {username}!"
    """
    if locale in _translations_cache:
        return _translations_cache[locale]

    translations: dict[str, Any] = {}
    locale_dir = (
        Path(__file__).parent.parent.parent.parent / "content" / "locales" / locale
    )

    if not locale_dir.exists():
        logger.warning(f"Locale directory not found: {locale_dir}")
        return {}

    # Load all JSON files in locale directory
    for json_file in locale_dir.glob("*.json"):
        try:
            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)
                # Use filename without extension as top-level key
                key = json_file.stem
                translations[key] = data
        except Exception as e:
            logger.error(
                f"Failed to load translation file {json_file}: {e}", exc_info=True
            )

    _translations_cache[locale] = translations
    return translations


def _get_nested_value(data: dict[str, Any], key: str) -> str | None:
    """Get nested value from dictionary using dot notation.

    Args:
        data: Dictionary to search
        key: Dot-separated key path (e.g., "commands.start.welcome")

    Returns:
        Value if found, None otherwise

    Example:
        >>> data = {"commands": {"start": {"welcome": "Hello"}}}
        >>> _get_nested_value(data, "commands.start.welcome")
        "Hello"
    """
    keys = key.split(".")
    current = data

    for k in keys:
        if isinstance(current, dict) and k in current:
            current = current[k]
        else:
            return None

    return str(current) if current is not None else None


async def detect_user_locale(
    db: AsyncSession | None = None,
    telegram_user_id: str | None = None,
    telegram_lang_code: str | None = None,
) -> str:
    """Detect user's preferred locale.

    Fallback chain:
        1. User preferences from database (PR-059 integration)
        2. Telegram profile language code
        3. Default to English

    Args:
        db: Database session (optional, for prefs lookup)
        telegram_user_id: Telegram user ID (optional)
        telegram_lang_code: Telegram language code from user profile (optional)

    Returns:
        Locale code (e.g., "en", "es")

    Example:
        >>> locale = await detect_user_locale(
        ...     db=db_session,
        ...     telegram_user_id="123456",
        ...     telegram_lang_code="es"
        ... )
        >>> print(locale)  # "es"
    """
    # Try to get locale from user preferences (PR-059 integration)
    if db is not None and telegram_user_id is not None:
        try:
            from backend.app.prefs.models import UserPreferences

            stmt = select(UserPreferences).where(
                UserPreferences.telegram_user_id == telegram_user_id
            )
            result = await db.execute(stmt)
            prefs = result.scalar_one_or_none()

            if prefs and prefs.locale:
                locale = prefs.locale
                if locale in SUPPORTED_LOCALES:
                    logger.debug(f"Using locale from user prefs: {locale}")
                    return str(locale)
        except Exception as e:
            logger.warning(f"Failed to fetch user preferences: {e}")

    # Try Telegram profile language code
    if telegram_lang_code:
        # Extract base language code (e.g., "es-ES" → "es")
        base_lang = telegram_lang_code.split("-")[0].lower()
        if base_lang in SUPPORTED_LOCALES:
            logger.debug(f"Using locale from Telegram profile: {base_lang}")
            return base_lang

    # Fallback to English
    logger.debug(f"Using default locale: {DEFAULT_LOCALE}")
    return DEFAULT_LOCALE


def get_text(
    key: str,
    locale: str | None = None,
    fallback_to_english: bool = True,
    track_telemetry: bool = True,
    **kwargs: Any,
) -> str:
    """Get localized text for a given key.

    Supports variable interpolation using {variable} syntax.

    Args:
        key: Translation key in dot notation (e.g., "commands.start.welcome")
        locale: Locale code (defaults to DEFAULT_LOCALE)
        fallback_to_english: If True, fallback to English if key not found in locale
        track_telemetry: If True, track locale usage metric
        **kwargs: Variables for interpolation

    Returns:
        Localized text with variables interpolated

    Example:
        >>> text = get_text("commands.start.welcome", locale="es", username="John")
        >>> print(text)  # "¡Bienvenido, John!"

        >>> # Missing key fallback
        >>> text = get_text("missing.key", locale="es", fallback_to_english=True)
        >>> print(text)  # Falls back to English translation
    """
    if locale is None:
        locale = DEFAULT_LOCALE

    # Validate locale
    if locale not in SUPPORTED_LOCALES:
        logger.warning(f"Unsupported locale: {locale}, using default: {DEFAULT_LOCALE}")
        locale = DEFAULT_LOCALE

    # Track telemetry
    if track_telemetry:
        try:
            metrics = get_metrics()
            metrics.telegram_locale_used_total.labels(locale=locale).inc()
        except Exception as e:
            logger.warning(f"Failed to track locale telemetry: {e}")

    # Load translations for requested locale
    translations = _load_translations(locale)
    text = _get_nested_value(translations, key)

    # Fallback to English if not found
    if text is None and fallback_to_english and locale != DEFAULT_LOCALE:
        logger.debug(
            f"Key '{key}' not found in locale '{locale}', trying English fallback"
        )
        translations = _load_translations(DEFAULT_LOCALE)
        text = _get_nested_value(translations, key)

    # Return key itself if still not found (for debugging)
    if text is None:
        logger.warning(f"Translation key not found: {key} (locale: {locale})")
        return f"[MISSING: {key}]"

    # Interpolate variables
    try:
        return text.format(**kwargs)
    except KeyError as e:
        logger.error(
            f"Missing variable in translation: {e} (key: {key}, locale: {locale})"
        )
        return text  # Return without interpolation if variable missing


def get_position_failure_template(
    failure_type: str,
    locale: str | None = None,
    **kwargs: Any,
) -> dict[str, str]:
    """Get localized position failure notification template.

    Integration with PR-104 (Position Tracking) for execution failure notifications.

    Args:
        failure_type: Type of failure ("entry_failure", "exit_sl_hit", "exit_tp_hit")
        locale: Locale code (defaults to DEFAULT_LOCALE)
        **kwargs: Variables for interpolation (instrument, side, price, etc.)

    Returns:
        Dictionary with "title" and "message" keys

    Example:
        >>> template = get_position_failure_template(
        ...     "entry_failure",
        ...     locale="es",
        ...     instrument="GOLD",
        ...     side="buy",
        ...     price=1950.50,
        ...     error="Insufficient margin"
        ... )
        >>> print(template["title"])  # "⚠️ Acción Manual Requerida"
        >>> print(template["message"])  # "Fallo al abrir posición GOLD BUY..."
    """
    if locale is None:
        locale = DEFAULT_LOCALE

    # Load position failures translations
    translations = _load_translations(locale)
    failures = translations.get("position_failures", {})

    # Get template for failure type
    template = failures.get(failure_type)

    # Fallback to English if not found
    if template is None and locale != DEFAULT_LOCALE:
        logger.debug(
            f"Position failure template '{failure_type}' not found in locale '{locale}', "
            f"trying English fallback"
        )
        translations = _load_translations(DEFAULT_LOCALE)
        failures = translations.get("position_failures", {})
        template = failures.get(failure_type)

    # Return missing template if not found
    if template is None:
        logger.error(
            f"Position failure template not found: {failure_type} (locale: {locale})"
        )
        return {
            "title": f"[MISSING TEMPLATE: {failure_type}]",
            "message": f"[MISSING TEMPLATE: {failure_type}]",
        }

    # Interpolate variables
    try:
        return {
            "title": template["title"].format(**kwargs),
            "message": template["message"].format(**kwargs),
        }
    except (KeyError, TypeError) as e:
        logger.error(
            f"Failed to interpolate position failure template: {e} "
            f"(type: {failure_type}, locale: {locale})"
        )
        return cast(dict[str, str], template)


def clear_translations_cache():
    """Clear translations cache (useful for testing and hot-reloading).

    Example:
        >>> clear_translations_cache()
        >>> # Translations will be reloaded from disk on next get_text() call
    """
    global _translations_cache
    _translations_cache = {}
    logger.info("Cleared translations cache")
