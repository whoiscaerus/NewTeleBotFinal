"""Safe MarkdownV2 message formatting for marketing promos.

This module provides utilities for creating and formatting marketing messages
that safely comply with Telegram's MarkdownV2 syntax, preventing formatting
errors or injection attacks.

MarkdownV2 Special Characters (must be escaped):
    _ * [ ] ( ) ~ ` > # + - = | { } . !

Example:
    >>> msg = SafeMarkdownV2Message()
    >>> msg.add_title("🚀 Premium Signals")
    >>> msg.add_text("Get 94% win rate signals")
    >>> msg.add_cta_button("Buy Now", "https://t.me/bot?start=premium")
    >>> formatted = msg.render()
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class SafeMarkdownV2Message:
    """Builder for MarkdownV2-safe marketing messages.

    Handles escaping of special characters and provides convenient methods
    for building formatted promotional content.

    Example:
        >>> msg = SafeMarkdownV2Message()
        >>> msg.add_title("Premium Trading")
        >>> msg.add_text("Get started today")
        >>> message = msg.render()
    """

    # Characters that MUST be escaped in MarkdownV2
    MARKDOWN_V2_SPECIAL_CHARS = r"_*[]()~`>#+-=|{}.!"

    def __init__(self) -> None:
        """Initialize message builder."""
        self.lines: list[str] = []
        self.logger = logger

    @staticmethod
    def escape_markdown_v2(text: str) -> str:
        """Escape special characters for MarkdownV2 safety.

        Args:
            text: Raw text to escape

        Returns:
            MarkdownV2-safe text with special chars escaped

        Example:
            >>> SafeMarkdownV2Message.escape_markdown_v2("Test * text")
            'Test \\* text'
        """
        # Escape each special character with backslash
        result = text
        for char in SafeMarkdownV2Message.MARKDOWN_V2_SPECIAL_CHARS:
            result = result.replace(char, f"\\{char}")
        return result

    @staticmethod
    def validate_markdown_v2(text: str) -> tuple[bool, str | None]:
        """Validate that text is MarkdownV2-safe (no unescaped special chars).

        Args:
            text: Text to validate

        Returns:
            Tuple of (is_valid, error_message)

        Example:
            >>> valid, msg = SafeMarkdownV2Message.validate_markdown_v2("Safe text")
            >>> assert valid is True
        """
        # Pattern: special char not preceded by backslash
        pattern = f"(?<!\\\\)[{re.escape(SafeMarkdownV2Message.MARKDOWN_V2_SPECIAL_CHARS)}]"

        if re.search(pattern, text):
            matches = re.findall(pattern, text)
            return False, f"Found unescaped special characters: {set(matches)}"

        return True, None

    def add_title(self, title: str, emoji: str = "") -> "SafeMarkdownV2Message":
        """Add a bold title line.

        Args:
            title: Title text
            emoji: Optional emoji prefix

        Returns:
            Self for chaining

        Example:
            >>> msg = SafeMarkdownV2Message()
            >>> msg.add_title("Premium Trading", "🚀")
        """
        escaped = self.escape_markdown_v2(title)
        if emoji:
            line = f"{emoji} \\*{escaped}\\*"
        else:
            line = f"\\*{escaped}\\*"
        self.lines.append(line)
        return self

    def add_text(self, text: str) -> "SafeMarkdownV2Message":
        """Add a paragraph of text.

        Args:
            text: Text content

        Returns:
            Self for chaining

        Example:
            >>> msg = SafeMarkdownV2Message()
            >>> msg.add_text("Get started with premium signals today")
        """
        escaped = self.escape_markdown_v2(text)
        self.lines.append(escaped)
        return self

    def add_bullet(self, item: str) -> "SafeMarkdownV2Message":
        """Add a bullet point.

        Args:
            item: Bullet item text

        Returns:
            Self for chaining

        Example:
            >>> msg = SafeMarkdownV2Message()
            >>> msg.add_bullet("94% win rate")
            >>> msg.add_bullet("24/7 support")
        """
        escaped = self.escape_markdown_v2(item)
        self.lines.append(f"• {escaped}")
        return self

    def add_code(self, code: str) -> "SafeMarkdownV2Message":
        """Add inline code (monospace).

        Args:
            code: Code text

        Returns:
            Self for chaining

        Example:
            >>> msg = SafeMarkdownV2Message()
            >>> msg.add_code("XAU/USD")
        """
        escaped = self.escape_markdown_v2(code)
        self.lines.append(f"\\`{escaped}\\`")
        return self

    def add_divider(self) -> "SafeMarkdownV2Message":
        """Add a visual divider line.

        Returns:
            Self for chaining
        """
        self.lines.append("\\-\\-\\-\\-\\-")
        return self

    def add_blank_line(self) -> "SafeMarkdownV2Message":
        """Add blank line for spacing.

        Returns:
            Self for chaining
        """
        self.lines.append("")
        return self

    def render(self) -> str:
        """Render final MarkdownV2 message.

        Returns:
            Formatted message string ready for Telegram API

        Raises:
            ValueError: If rendered message contains unescaped special chars

        Example:
            >>> msg = SafeMarkdownV2Message()
            >>> msg.add_title("Trading")
            >>> text = msg.render()
            >>> print(text)
        """
        final_text = "\n".join(self.lines)

        # Validate final output
        is_valid, error = self.validate_markdown_v2(final_text)
        if not is_valid:
            self.logger.error(f"MarkdownV2 validation failed: {error}")
            raise ValueError(f"Invalid MarkdownV2 message: {error}")

        return final_text


# Pre-built promo templates
def create_premium_signals_promo() -> str:
    """Create premium trading signals promo message.

    Returns:
        MarkdownV2-formatted promo message

    Example:
        >>> text = create_premium_signals_promo()
        >>> assert "Premium" in text
    """
    msg = SafeMarkdownV2Message()
    msg.add_title("Premium Trading Signals", "🚀")
    msg.add_blank_line()
    msg.add_text("Unlock professional trading signals with proven 94% accuracy\\.")
    msg.add_blank_line()
    msg.add_text("*Features:*")
    msg.add_bullet("Real\\-time signal delivery")
    msg.add_bullet("24/7 expert analysis")
    msg.add_bullet("Risk management tools")
    msg.add_bullet("Performance analytics")
    msg.add_blank_line()
    msg.add_text("Limited time offer \\- Join today\\!")
    return msg.render()


def create_copy_trading_promo() -> str:
    """Create copy-trading feature promo message.

    Returns:
        MarkdownV2-formatted promo message
    """
    msg = SafeMarkdownV2Message()
    msg.add_title("Auto Copy Trading", "💎")
    msg.add_blank_line()
    msg.add_text("Stop missing profitable trades\\. Automatically copy professional traders\\.")
    msg.add_blank_line()
    msg.add_text("*Why copy trading?*")
    msg.add_bullet("Passive income while you sleep")
    msg.add_bullet("Proven trader strategies")
    msg.add_bullet("Full transparency & control")
    msg.add_bullet("Risk\\-adjusted position sizing")
    msg.add_blank_line()
    msg.add_text("Enable copy trading now and start earning\\!")
    return msg.render()


def create_analytics_promo() -> str:
    """Create advanced analytics promo message.

    Returns:
        MarkdownV2-formatted promo message
    """
    msg = SafeMarkdownV2Message()
    msg.add_title("Advanced Analytics", "📊")
    msg.add_blank_line()
    msg.add_text("Deep dive into your trading performance with powerful analytics\\.")
    msg.add_blank_line()
    msg.add_text("*Unlock insights on:*")
    msg.add_bullet("Win rate & profitability")
    msg.add_bullet("Risk\\-reward ratios")
    msg.add_bullet("Drawdown analysis")
    msg.add_bullet("Trade statistics & patterns")
    msg.add_blank_line()
    msg.add_text("Upgrade today to master your trading\\!")
    return msg.render()


def create_vip_support_promo() -> str:
    """Create VIP support tier promo message.

    Returns:
        MarkdownV2-formatted promo message
    """
    msg = SafeMarkdownV2Message()
    msg.add_title("VIP Priority Support", "🎯")
    msg.add_blank_line()
    msg.add_text("Get white\\-glove treatment with dedicated support\\.")
    msg.add_blank_line()
    msg.add_text("*VIP Members Get:*")
    msg.add_bullet("Dedicated account manager")
    msg.add_bullet("1\\-on\\-1 trading coaching")
    msg.add_bullet("Priority support \\(15 min response\\)")
    msg.add_bullet("Monthly strategy reviews")
    msg.add_blank_line()
    msg.add_text("Become VIP and transform your trading\\!")
    return msg.render()


PROMO_TEMPLATES = {
    "premium_signals": create_premium_signals_promo,
    "copy_trading": create_copy_trading_promo,
    "analytics": create_analytics_promo,
    "vip_support": create_vip_support_promo,
}


def get_promo_template(template_name: str) -> str:
    """Get pre-built promo template by name.

    Args:
        template_name: Name of template (premium_signals, copy_trading, analytics, vip_support)

    Returns:
        Formatted MarkdownV2 message

    Raises:
        ValueError: If template not found

    Example:
        >>> text = get_promo_template("premium_signals")
    """
    if template_name not in PROMO_TEMPLATES:
        raise ValueError(
            f"Unknown template: {template_name}. "
            f"Available: {', '.join(PROMO_TEMPLATES.keys())}"
        )

    return PROMO_TEMPLATES[template_name]()


def validate_all_templates() -> dict[str, Any]:
    """Validate all built-in templates are MarkdownV2-safe.

    Returns:
        Dictionary with validation results

    Example:
        >>> results = validate_all_templates()
        >>> assert all(r["valid"] for r in results.values())
    """
    results = {}

    for template_name, template_func in PROMO_TEMPLATES.items():
        try:
            text = template_func()
            is_valid, error = SafeMarkdownV2Message.validate_markdown_v2(text)
            results[template_name] = {
                "valid": is_valid,
                "error": error,
                "length": len(text),
            }
        except Exception as e:
            results[template_name] = {"valid": False, "error": str(e), "length": 0}

    return results
