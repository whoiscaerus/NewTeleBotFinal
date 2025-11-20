"""Template System: Multi-channel message rendering.

This module provides template rendering for:
- Email: Jinja2 templates with HTML + plain text fallback
- Telegram: MarkdownV2-safe formatting with special char escaping
- Push: PWA push notifications with title, body, icon, data

Templates are loaded from:
- Email: /email/templates/{template_name}.html (Jinja2)
- Telegram: Inline templates with MarkdownV2 escaping
- Push: Inline JSON templates

Example:
    # Render email template
    email = render_email(
        template_name="position_failure_entry",
        template_vars={"instrument": "GOLD", "side": "buy", "entry_price": 1950.50}
    )
    # Returns: {"subject": "...", "html": "...", "text": "..."}

    # Render Telegram message
    telegram_text = render_telegram(
        template_name="position_failure_entry",
        template_vars={"instrument": "GOLD", "side": "buy"}
    )
    # Returns: Telegram MarkdownV2-formatted string

    # Render push notification
    push = render_push(
        template_name="position_failure_entry",
        template_vars={"instrument": "GOLD", "side": "buy"}
    )
    # Returns: {"title": "...", "body": "...", "icon": "...", "data": {...}}
"""

import logging
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

logger = logging.getLogger(__name__)

# Email templates directory
EMAIL_TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent / "email" / "templates"

# Jinja2 environment (lazy-loaded)
_jinja_env: Environment | None = None

# MarkdownV2 special characters that need escaping
# See: https://core.telegram.org/bots/api#markdownv2-style
MARKDOWNV2_SPECIAL_CHARS = r"_*[]()~`>#+-=|{}.!"


def _get_jinja_env() -> Environment:
    """Get or create Jinja2 environment.

    Returns:
        Environment: Jinja2 environment with email templates loaded

    Raises:
        RuntimeError: If email templates directory not found
    """
    global _jinja_env

    if _jinja_env is None:
        if not EMAIL_TEMPLATES_DIR.exists():
            raise RuntimeError(
                f"Email templates directory not found: {EMAIL_TEMPLATES_DIR}"
            )

        _jinja_env = Environment(
            loader=FileSystemLoader(EMAIL_TEMPLATES_DIR),
            autoescape=True,  # Auto-escape HTML (security)
            trim_blocks=True,
            lstrip_blocks=True,
        )

        logger.info(f"Jinja2 environment initialized: {EMAIL_TEMPLATES_DIR}")

    return _jinja_env


def escape_markdownv2(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2.

    MarkdownV2 requires escaping: _ * [ ] ( ) ~ ` > # + - = | { } . !

    Args:
        text: Raw text to escape

    Returns:
        str: Escaped text safe for MarkdownV2

    Example:
        >>> escape_markdownv2("Price: $1,950.50")
        "Price: \\$1,950\\.50"
    """
    # Escape each special char with backslash
    for char in MARKDOWNV2_SPECIAL_CHARS:
        text = text.replace(char, f"\\{char}")
    return text


def render_email(template_name: str, template_vars: dict[str, Any]) -> dict[str, str]:
    """Render email template using Jinja2.

    Args:
        template_name: Template name (without .html extension)
        template_vars: Template variables (e.g., {"instrument": "GOLD"})

    Returns:
        dict: {"subject": "...", "html": "...", "text": "..."}

    Raises:
        ValueError: If required template vars missing
        TemplateNotFound: If template file not found

    Example:
        email = render_email(
            template_name="position_failure_entry",
            template_vars={
                "instrument": "GOLD",
                "side": "buy",
                "entry_price": 1950.50,
                "volume": 1.0,
                "error_reason": "Insufficient margin",
                "approval_id": "abc123"
            }
        )
        # email["subject"] = "⚠️ Manual Trade Entry Required - GOLD"
        # email["html"] = "<html>...</html>"
        # email["text"] = "Your trade entry failed..."
    """
    try:
        # Validate required template variables
        missing_vars = validate_template_vars(template_name, template_vars)
        if missing_vars:
            raise ValueError(
                f"Missing required template variables: {', '.join(missing_vars)}"
            )

        # Get Jinja2 environment
        env = _get_jinja_env()

        # Load template
        template = env.get_template(f"{template_name}.html")

        # Render HTML
        html = template.render(**template_vars)

        # Generate plain text version (strip HTML tags)
        text = re.sub(r"<[^>]+>", "", html)
        text = re.sub(r"\s+", " ", text).strip()

        # Extract subject from template (convention: first <title> tag or h2)
        subject_match = re.search(r"<title>(.*?)</title>", html)
        if not subject_match:
            subject_match = re.search(r"<h2[^>]*>(.*?)</h2>", html)

        subject = (
            subject_match.group(1)
            if subject_match
            else f"Notification - {template_name}"
        )

        logger.debug(
            f"Email rendered: {template_name}",
            extra={"template_name": template_name, "vars_count": len(template_vars)},
        )

        return {"subject": subject, "html": html, "text": text}

    except TemplateNotFound as err:
        logger.error(f"Email template not found: {template_name}")
        raise ValueError(f"Email template not found: {template_name}") from err

    except Exception as e:
        logger.error(
            f"Failed to render email template: {e}",
            exc_info=True,
            extra={"template_name": template_name},
        )
        raise


def render_telegram(template_name: str, template_vars: dict[str, Any]) -> str:
    """Render Telegram message with MarkdownV2 escaping.

    Args:
        template_name: Template name (e.g., "position_failure_entry")
        template_vars: Template variables

    Returns:
        str: Telegram message with MarkdownV2 formatting

    Raises:
        ValueError: If required template vars missing or template not found

    Example:
        text = render_telegram(
            template_name="position_failure_entry",
            template_vars={
                "instrument": "GOLD",
                "side": "buy",
                "entry_price": 1950.50,
                "volume": 1.0,
                "error_reason": "Insufficient margin",
                "approval_id": "abc123"
            }
        )
        # Returns: "⚠️ *Manual Action Required*\n\n..."
    """
    # Import inline templates
    from backend.app.messaging.templates.position_failures import (
        ENTRY_FAILURE_TELEGRAM,
        SL_FAILURE_TELEGRAM,
        TP_FAILURE_TELEGRAM,
    )

    # Template registry
    telegram_templates = {
        "position_failure_entry": ENTRY_FAILURE_TELEGRAM,
        "position_failure_sl": SL_FAILURE_TELEGRAM,
        "position_failure_tp": TP_FAILURE_TELEGRAM,
    }

    # Get template
    template = telegram_templates.get(template_name)
    if not template:
        raise ValueError(f"Telegram template not found: {template_name}")

    # Validate required vars (template-specific)
    if template_name == "position_failure_entry":
        required = [
            "instrument",
            "side",
            "entry_price",
            "volume",
            "error_reason",
            "approval_id",
        ]
    elif template_name in ("position_failure_sl", "position_failure_tp"):
        required = [
            "instrument",
            "side",
            "entry_price",
            "current_price",
            "broker_ticket",
        ]
        if template_name == "position_failure_sl":
            required.append("loss_amount")
        else:
            required.append("profit_amount")
    else:
        required = []

    missing = [var for var in required if var not in template_vars]
    if missing:
        raise ValueError(f"Missing required template vars: {missing}")

    # Add side emoji if not present
    if "side_emoji" not in template_vars and "side" in template_vars:
        template_vars["side_emoji"] = "🟢" if template_vars["side"] == "buy" else "🔴"

    # Add currency if not present
    if "currency" not in template_vars:
        template_vars["currency"] = "USD"

    try:
        # Escape all string values for MarkdownV2
        escaped_vars = {}
        for key, value in template_vars.items():
            if isinstance(value, str):
                # Don't escape emojis or side_emoji
                if key in ("side_emoji",):
                    escaped_vars[key] = value
                else:
                    escaped_vars[key] = escape_markdownv2(value)
            else:
                # Numbers, bools, etc. - convert to string and escape
                escaped_vars[key] = escape_markdownv2(str(value))

        # Format template with escaped values
        text = template.format(**escaped_vars)

        logger.debug(
            f"Telegram message rendered: {template_name}",
            extra={"template_name": template_name, "length": len(text)},
        )

        return text

    except KeyError as err:
        logger.error(
            f"Missing template variable: {err}",
            extra={"template_name": template_name, "missing_var": str(err)},
        )
        raise ValueError(f"Missing template variable: {err}") from err

    except Exception as e:
        logger.error(
            f"Failed to render Telegram template: {e}",
            exc_info=True,
            extra={"template_name": template_name},
        )
        raise


def render_push(template_name: str, template_vars: dict[str, Any]) -> dict[str, Any]:
    """Render PWA push notification.

    Args:
        template_name: Template name (e.g., "position_failure_entry")
        template_vars: Template variables

    Returns:
        dict: {
            "title": "Notification title",
            "body": "Notification body",
            "icon": "/icon-192x192.png",
            "badge": "/badge-96x96.png",
            "data": {"url": "/dashboard/..."}
        }

    Raises:
        ValueError: If required template vars missing or template not found

    Example:
        push = render_push(
            template_name="position_failure_entry",
            template_vars={
                "instrument": "GOLD",
                "side": "buy",
                "approval_id": "abc123"
            }
        )
    """
    # Import inline templates
    from backend.app.messaging.templates.position_failures import (
        ENTRY_FAILURE_PUSH,
        SL_FAILURE_PUSH,
        TP_FAILURE_PUSH,
    )

    # Template registry
    push_templates = {
        "position_failure_entry": ENTRY_FAILURE_PUSH,
        "position_failure_sl": SL_FAILURE_PUSH,
        "position_failure_tp": TP_FAILURE_PUSH,
    }

    # Get template
    template = push_templates.get(template_name)
    if not template:
        raise ValueError(f"Push template not found: {template_name}")

    # Validate required vars (template-specific)
    if template_name == "position_failure_entry":
        required = ["instrument", "side", "approval_id"]
    elif template_name in ("position_failure_sl", "position_failure_tp"):
        required = ["instrument", "side", "broker_ticket"]
    else:
        required = []

    missing = [var for var in required if var not in template_vars]
    if missing:
        raise ValueError(f"Missing required template vars: {missing}")

    try:
        # Format template strings
        title = template["title"].format(**template_vars)
        body = template["body"].format(**template_vars)

        # Format data URL if present
        data = template.get("data", {}).copy()
        if "url" in data:
            data["url"] = data["url"].format(**template_vars)

        # Build push notification
        push_notification = {
            "title": title,
            "body": body,
            "icon": template.get("icon", "/icon-192x192.png"),
            "badge": template.get("badge", "/badge-96x96.png"),
            "data": data,
        }

        logger.debug(
            f"Push notification rendered: {template_name}",
            extra={"template_name": template_name, "title": title},
        )

        return push_notification

    except KeyError as err:
        logger.error(
            f"Missing template variable: {err}",
            extra={"template_name": template_name, "missing_var": str(err)},
        )
        raise ValueError(f"Missing template variable: {err}") from err

    except Exception as e:
        logger.error(
            f"Failed to render push template: {e}",
            exc_info=True,
            extra={"template_name": template_name},
        )
        raise


def validate_template_vars(
    template_name: str, template_vars: dict[str, Any]
) -> list[str]:
    """Validate template variables (returns list of missing vars).

    Args:
        template_name: Template name
        template_vars: Template variables to validate

    Returns:
        list[str]: List of missing required variables (empty if all present)

    Example:
        missing = validate_template_vars("position_failure_entry", {"instrument": "GOLD"})
        # Returns: ["side", "entry_price", "volume", "error_reason", "approval_id"]
    """
    # Define required vars per template
    required_vars = {
        "position_failure_entry": [
            "instrument",
            "side",
            "entry_price",
            "volume",
            "error_reason",
            "approval_id",
        ],
        "position_failure_sl": [
            "instrument",
            "side",
            "entry_price",
            "current_price",
            "loss_amount",
            "broker_ticket",
        ],
        "position_failure_tp": [
            "instrument",
            "side",
            "entry_price",
            "current_price",
            "profit_amount",
            "broker_ticket",
        ],
        # PR-091: Daily Outlook templates
        "daily_outlook_email": ["outlook"],
        "daily_outlook_telegram": ["outlook"],
    }

    required = required_vars.get(template_name, [])
    missing = [var for var in required if var not in template_vars]

    return missing


# ========================================
# PR-091: Daily Market Outlook Templates
# ========================================


def render_daily_outlook_email(outlook) -> dict[str, str]:
    """
    Render Daily Outlook email template.

    Args:
        outlook: OutlookReport object

    Returns:
        dict with keys: subject, html, text
    """
    date_str = outlook.generated_at.strftime("%B %d, %Y")
    subject = f"📊 Daily Market Outlook - {date_str}"

    # HTML version (rich formatting)
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 700px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }}
        .content {{ background: white; padding: 30px; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 8px 8px; }}
        .narrative {{ white-space: pre-wrap; margin-bottom: 30px; }}
        .data-box {{ background: #f5f5f5; padding: 20px; border-left: 4px solid #667eea; margin: 20px 0; }}
        .zone {{ padding: 10px; margin: 5px 0; border-radius: 4px; }}
        .zone.low {{ background: #d4edda; color: #155724; }}
        .zone.medium {{ background: #fff3cd; color: #856404; }}
        .zone.high {{ background: #f8d7da; color: #721c24; }}
        .correlations {{ margin-top: 20px; }}
        .correlation {{ padding: 8px; margin: 5px 0; background: #f9f9f9; border-radius: 4px; }}
        .footer {{ text-align: center; color: #888; font-size: 12px; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e0e0e0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Daily Market Outlook</h1>
            <p>{date_str}</p>
        </div>
        <div class="content">
            <div class="narrative">
{outlook.narrative}
            </div>

            <div class="data-box">
                <h3>Data Citations</h3>
                <ul>
                    <li><strong>Sharpe Ratio:</strong> {outlook.data_citations.get('sharpe_ratio', 'N/A'):.2f}</li>
                    <li><strong>Sortino Ratio:</strong> {outlook.data_citations.get('sortino_ratio', 'N/A'):.2f}</li>
                    <li><strong>Max Drawdown:</strong> {outlook.data_citations.get('max_drawdown_pct', 'N/A'):.1f}%</li>
                    <li><strong>Volatility:</strong> {outlook.data_citations.get('volatility_pct', 'N/A'):.1f}%</li>
                    <li><strong>Win Rate:</strong> {outlook.data_citations.get('win_rate', 'N/A'):.1f}%</li>
                    <li><strong>RSI (14):</strong> {outlook.data_citations.get('rsi', 'N/A'):.1f}</li>
                    <li><strong>ROC (10):</strong> {outlook.data_citations.get('roc', 'N/A'):.2f}%</li>
                </ul>
            </div>

            <h3>Volatility Zones</h3>
            {"".join([f'<div class="zone {zone.level}"><strong>{zone.level.upper()}</strong>: {zone.description}</div>' for zone in outlook.volatility_zones])}

            <div class="correlations">
                <h3>Key Correlations</h3>
                {"".join([f'<div class="correlation">{corr.instrument_b}: {corr.coefficient:+.2f}</div>' for corr in outlook.correlations])}
            </div>
        </div>

        <div class="footer">
            <p><em>This is an AI-generated analysis based on historical data.</em></p>
            <p><em>Past performance does not guarantee future results. Not financial advice.</em></p>
        </div>
    </div>
</body>
</html>
"""

    # Plain text version (fallback)
    text = f"""
Daily Market Outlook - {date_str}

{outlook.narrative}

Data Citations:
- Sharpe Ratio: {outlook.data_citations.get('sharpe_ratio', 'N/A'):.2f}
- Sortino Ratio: {outlook.data_citations.get('sortino_ratio', 'N/A'):.2f}
- Max Drawdown: {outlook.data_citations.get('max_drawdown_pct', 'N/A'):.1f}%
- Volatility: {outlook.data_citations.get('volatility_pct', 'N/A'):.1f}%
- Win Rate: {outlook.data_citations.get('win_rate', 'N/A'):.1f}%
- RSI (14): {outlook.data_citations.get('rsi', 'N/A'):.1f}
- ROC (10): {outlook.data_citations.get('roc', 'N/A'):.2f}%

Volatility Zones:
{chr(10).join([f"{zone.level.upper()}: {zone.description}" for zone in outlook.volatility_zones])}

Key Correlations:
{chr(10).join([f"{corr.instrument_b}: {corr.coefficient:+.2f}" for corr in outlook.correlations])}

---
This is an AI-generated analysis. Past performance does not guarantee future results. Not financial advice.
"""

    return {"subject": subject, "html": html.strip(), "text": text.strip()}


def render_daily_outlook_telegram(outlook) -> str:
    """
    Render Daily Outlook Telegram template (MarkdownV2-safe).

    Args:
        outlook: OutlookReport object

    Returns:
        str: Telegram-formatted message
    """
    date_str = outlook.generated_at.strftime("%B %d, %Y")

    # Build concise narrative (first 500 chars + ellipsis)
    narrative_short = outlook.narrative[:500]
    if len(outlook.narrative) > 500:
        narrative_short += "..."

    # Escape special chars for MarkdownV2
    narrative_escaped = _escape_markdown_v2(narrative_short)

    # Build message
    message = f"""
📊 *Daily Market Outlook*
_{date_str}_

{narrative_escaped}

📈 *Key Metrics*
• Sharpe: {outlook.data_citations.get('sharpe_ratio', 0.0):.2f}
• Sortino: {outlook.data_citations.get('sortino_ratio', 0.0):.2f}
• Drawdown: {outlook.data_citations.get('max_drawdown_pct', 0.0):.1f}%
• Volatility: {outlook.data_citations.get('volatility_pct', 0.0):.1f}%
• Win Rate: {outlook.data_citations.get('win_rate', 0.0):.1f}%

🔍 *Correlations*
{chr(10).join([f"• {corr.instrument_b}: {corr.coefficient:+.2f}" for corr in outlook.correlations[:3]])}

_AI\\-generated analysis\\. Not financial advice\\._
"""

    return message.strip()


def _escape_markdown_v2(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    # Characters that need escaping in MarkdownV2
    special_chars = r"_*[]()~`>#+-=|{}.!"
    for char in special_chars:
        text = text.replace(char, f"\\{char}")
    return text
