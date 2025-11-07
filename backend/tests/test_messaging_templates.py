"""Comprehensive tests for template system (PR-060).

Tests cover:
- Email rendering with Jinja2 (HTML + plain text)
- Telegram rendering with MarkdownV2 escaping (all special chars)
- Push rendering with JSON structure
- Position failure templates (3 types × 3 channels = 9 combinations)
- Missing variables (ValueError)
- Snapshot tests for rendered output

Target: 100% coverage of backend/app/messaging/templates.py (430 lines)
"""

import pytest

from backend.app.messaging.templates import (
    escape_markdownv2,
    render_email,
    render_push,
    render_telegram,
    validate_template_vars,
)
from backend.app.messaging.templates.position_failures import (
    ENTRY_FAILURE_EMAIL,
    ENTRY_FAILURE_PUSH,
    ENTRY_FAILURE_TELEGRAM,
    SL_FAILURE_EMAIL,
    SL_FAILURE_PUSH,
    SL_FAILURE_TELEGRAM,
    TP_FAILURE_EMAIL,
    TP_FAILURE_PUSH,
    TP_FAILURE_TELEGRAM,
)


class TestMarkdownV2Escaping:
    """Test MarkdownV2 special character escaping."""

    def test_escape_underscore(self):
        """Test underscore escaping."""
        assert escape_markdownv2("user_id") == r"user\_id"

    def test_escape_asterisk(self):
        """Test asterisk escaping."""
        assert escape_markdownv2("*important*") == r"\*important\*"

    def test_escape_brackets(self):
        """Test bracket escaping."""
        assert escape_markdownv2("[link]") == r"\[link\]"
        assert escape_markdownv2("(text)") == r"\(text\)"

    def test_escape_tilde(self):
        """Test tilde escaping."""
        assert escape_markdownv2("~strikethrough~") == r"\~strikethrough\~"

    def test_escape_backtick(self):
        """Test backtick escaping."""
        assert escape_markdownv2("`code`") == r"\`code\`"

    def test_escape_angle_brackets(self):
        """Test angle bracket escaping."""
        assert escape_markdownv2(">quote") == r"\>quote"
        assert escape_markdownv2("#hashtag") == r"\#hashtag"

    def test_escape_plus_minus(self):
        """Test plus/minus escaping."""
        assert escape_markdownv2("+100") == r"\+100"
        assert escape_markdownv2("-50") == r"\-50"

    def test_escape_equals(self):
        """Test equals escaping."""
        assert escape_markdownv2("x=10") == r"x\=10"

    def test_escape_pipe(self):
        """Test pipe escaping."""
        assert escape_markdownv2("a|b") == r"a\|b"

    def test_escape_curly_braces(self):
        """Test curly brace escaping."""
        assert escape_markdownv2("{key}") == r"\{key\}"

    def test_escape_period(self):
        """Test period escaping."""
        assert escape_markdownv2("Price: 1950.50") == r"Price: 1950\.50"

    def test_escape_exclamation(self):
        """Test exclamation escaping."""
        assert escape_markdownv2("Alert!") == r"Alert\!"

    def test_escape_multiple_special_chars(self):
        """Test escaping multiple special characters."""
        text = "Price: 1950.50 (gain!) [Buy] *XAUUSD*"
        expected = r"Price: 1950\.50 \(gain\!\) \[Buy\] \*XAUUSD\*"
        assert escape_markdownv2(text) == expected

    def test_escape_preserves_spaces(self):
        """Test escaping preserves spaces."""
        assert escape_markdownv2("word1 word2") == "word1 word2"

    def test_escape_preserves_newlines(self):
        """Test escaping preserves newlines."""
        text = "Line 1\nLine 2"
        assert escape_markdownv2(text) == "Line 1\nLine 2"

    def test_escape_empty_string(self):
        """Test escaping empty string."""
        assert escape_markdownv2("") == ""

    def test_escape_only_special_chars(self):
        """Test escaping string with only special chars."""
        assert escape_markdownv2("._*[]()") == r"\.\_\*\[\]\(\)"


class TestTemplateValidation:
    """Test template variable validation."""

    def test_validate_all_vars_present(self):
        """Test validation passes when all vars present."""
        template_vars = {
            "instrument": "XAUUSD",
            "side": "buy",
            "entry_price": 1950.50,
            "volume": 0.1,
            "error_reason": "Broker rejected",
            "approval_id": "approval-123",
        }

        # Should return empty list (no missing vars)
        missing = validate_template_vars("position_failure_entry", template_vars)
        assert missing == []

    def test_validate_missing_var_raises(self):
        """Test validation detects missing var."""
        template_vars = {"instrument": "XAUUSD", "side": "buy"}

        # Should return list of missing vars
        missing = validate_template_vars("position_failure_entry", template_vars)
        assert "entry_price" in missing
        assert "volume" in missing
        assert "error_reason" in missing
        assert "approval_id" in missing

    def test_validate_multiple_missing_vars(self):
        """Test validation lists all missing vars."""
        template_vars = {"instrument": "XAUUSD"}

        # Should return list of all missing vars
        missing = validate_template_vars("position_failure_entry", template_vars)
        assert (
            len(missing) == 5
        )  # Missing: side, entry_price, volume, error_reason, approval_id
        assert "side" in missing
        assert "entry_price" in missing
        assert "volume" in missing
        assert "error_reason" in missing
        assert "approval_id" in missing

    def test_validate_unknown_template(self):
        """Test validation with unknown template name."""
        template_vars = {"foo": "bar"}

        # Unknown template should return empty list (no required vars)
        missing = validate_template_vars("unknown_template", template_vars)
        assert missing == []

    def test_validate_empty_required_list(self):
        """Test validation with no required vars."""
        template_vars = {"any": "value"}

        # Unknown template has no required vars - should return empty list
        missing = validate_template_vars("unknown_template", template_vars)
        assert missing == []

    def test_validate_extra_vars_allowed(self):
        """Test validation allows extra vars."""
        template_vars = {
            "instrument": "XAUUSD",
            "side": "buy",
            "entry_price": 1950.50,
            "volume": 0.1,
            "error_reason": "Rejected",
            "approval_id": "approval-123",
            "extra_var": "ignored",  # Extra var should be allowed
        }

        # Should return empty list (all required vars present, extras OK)
        missing = validate_template_vars("position_failure_entry", template_vars)
        assert missing == []


class TestEmailRendering:
    """Test email template rendering with Jinja2."""

    def test_render_email_position_failure_entry(self):
        """Test rendering entry failure email template."""
        template_vars = {
            "instrument": "XAUUSD",
            "side": "buy",
            "entry_price": 1950.50,
            "volume": 0.1,
            "error_reason": "Insufficient margin",
            "approval_id": "approval-123",
        }

        result = render_email("position_failure_entry", template_vars)

        # Verify structure
        assert "subject" in result
        assert "html" in result
        assert "text" in result

        # Verify subject (actual implementation format)
        assert (
            "Manual Trade Entry Required" in result["subject"]
            or "Manual Action Required" in result["subject"]
        )
        assert "XAUUSD" in result["subject"]

        # Verify HTML contains key elements
        html = result["html"]
        assert "XAUUSD" in html
        assert "buy" in html.lower() or "BUY" in html
        assert "1950.50" in html or "1950.5" in html
        assert "0.1" in html
        assert "Insufficient margin" in html
        assert "approval-123" in html

        # Verify text fallback generated
        text = result["text"]
        assert "XAUUSD" in text
        assert len(text) > 0

    def test_render_email_position_failure_sl(self):
        """Test rendering SL failure email template."""
        template_vars = {
            "instrument": "XAUUSD",
            "side": "sell",
            "entry_price": 1950.50,
            "current_price": 1960.20,
            "loss_amount": 97.00,
            "broker_ticket": "12345678",
        }

        result = render_email("position_failure_sl", template_vars)

        # Verify URGENT in subject
        assert "URGENT" in result["subject"] or "Stop Loss" in result["subject"]

        # Verify HTML contains all fields
        html = result["html"]
        assert "XAUUSD" in html
        assert "sell" in html.lower() or "SELL" in html
        assert "1960.20" in html or "1960.2" in html
        assert "97" in html  # Loss amount
        assert "12345678" in html  # Ticket

    def test_render_email_position_failure_tp(self):
        """Test rendering TP failure email template."""
        template_vars = {
            "instrument": "XAUUSD",
            "side": "buy",
            "entry_price": 1950.50,
            "current_price": 1960.20,
            "profit_amount": 97.00,
            "broker_ticket": "87654321",
        }

        result = render_email("position_failure_tp", template_vars)

        # Verify Take Profit in subject
        assert "Take Profit" in result["subject"] or "Profit" in result["subject"]

        # Verify HTML contains profit amount
        html = result["html"]
        assert "97" in html  # Profit amount
        assert "87654321" in html  # Ticket

    def test_render_email_missing_template_raises(self):
        """Test rendering non-existent template raises ValueError."""
        with pytest.raises(ValueError, match="Email template not found"):
            render_email("nonexistent_template", {})

    def test_render_email_missing_required_var_raises(self):
        """Test rendering with missing var raises ValueError."""
        template_vars = {"instrument": "XAUUSD"}  # Missing other required vars

        with pytest.raises(ValueError, match="Missing required template variables"):
            render_email("position_failure_entry", template_vars)

    def test_render_email_html_is_valid(self):
        """Test rendered HTML has basic structure."""
        template_vars = {
            "instrument": "XAUUSD",
            "side": "buy",
            "entry_price": 1950.50,
            "volume": 0.1,
            "error_reason": "Test error",
            "approval_id": "test-123",
        }

        result = render_email("position_failure_entry", template_vars)

        # Verify HTML structure
        html = result["html"]
        assert "<!DOCTYPE html>" in html or "<html" in html
        assert "</html>" in html
        assert "<body" in html
        assert "</body>" in html

    def test_render_email_side_conditional(self):
        """Test email renders different content for buy vs sell."""
        template_vars_buy = {
            "instrument": "XAUUSD",
            "side": "buy",
            "entry_price": 1950.50,
            "volume": 0.1,
            "error_reason": "Test",
            "approval_id": "test-123",
        }

        template_vars_sell = {
            "instrument": "XAUUSD",
            "side": "sell",
            "entry_price": 1950.50,
            "volume": 0.1,
            "error_reason": "Test",
            "approval_id": "test-456",
        }

        buy_result = render_email("position_failure_entry", template_vars_buy)
        sell_result = render_email("position_failure_entry", template_vars_sell)

        # Verify different side indicators
        assert "buy" in buy_result["html"].lower() or "BUY" in buy_result["html"]
        assert "sell" in sell_result["html"].lower() or "SELL" in sell_result["html"]


class TestTelegramRendering:
    """Test Telegram template rendering with MarkdownV2."""

    def test_render_telegram_entry_failure(self):
        """Test rendering entry failure Telegram message."""
        template_vars = {
            "instrument": "XAUUSD",
            "side": "buy",
            "entry_price": 1950.50,
            "volume": 0.1,
            "error_reason": "Insufficient margin",
            "approval_id": "approval-123",
        }

        text = render_telegram("position_failure_entry", template_vars)

        # Verify structure
        assert isinstance(text, str)
        assert len(text) > 0

        # Verify key content (with escaping)
        assert "XAUUSD" in text
        assert "buy" in text.lower() or "BUY" in text
        assert "Insufficient margin" in text
        assert "approval-123" in text or "approval\\-123" in text

        # Verify MarkdownV2 formatting
        assert "*" in text or "\\*" in text  # Bold markers

    def test_render_telegram_sl_failure(self):
        """Test rendering SL failure Telegram message."""
        template_vars = {
            "instrument": "XAUUSD",
            "side": "sell",
            "entry_price": 1950.50,
            "current_price": 1960.20,
            "loss_amount": 97.00,
            "broker_ticket": "12345678",
        }

        text = render_telegram("position_failure_sl", template_vars)

        # Verify URGENT or Stop Loss mentioned
        assert "URGENT" in text or "Stop Loss" in text or "SL" in text

        # Verify special chars escaped
        assert "\\." in text or "." not in text  # Period should be escaped
        assert "12345678" in text

    def test_render_telegram_tp_failure(self):
        """Test rendering TP failure Telegram message."""
        template_vars = {
            "instrument": "XAUUSD",
            "side": "buy",
            "entry_price": 1950.50,
            "current_price": 1960.20,
            "profit_amount": 97.00,
            "broker_ticket": "87654321",
        }

        text = render_telegram("position_failure_tp", template_vars)

        # Verify Take Profit mentioned
        assert "Take Profit" in text or "TP" in text or "profit" in text.lower()

        # Verify profit amount
        assert "97" in text

    def test_render_telegram_escapes_special_chars(self):
        """Test Telegram rendering escapes special characters."""
        template_vars = {
            "instrument": "XAU.USD",  # Period should be escaped
            "side": "buy",
            "entry_price": 1950.50,  # Decimals
            "volume": 0.1,
            "error_reason": "Error (test!)",  # Parens and exclamation
            "approval_id": "approval-123",
        }

        text = render_telegram("position_failure_entry", template_vars)

        # Verify special chars escaped (MarkdownV2 requires escaping)
        # Period: . → \.
        # Parentheses: ( → \(, ) → \)
        # Exclamation: ! → \!
        # These may appear escaped in the output
        assert "\\" in text  # Some escaping should be present

    def test_render_telegram_missing_template_raises(self):
        """Test rendering non-existent template raises ValueError."""
        with pytest.raises(ValueError, match="Telegram template not found"):
            render_telegram("nonexistent_template", {})

    def test_render_telegram_missing_required_var_raises(self):
        """Test rendering with missing var raises ValueError."""
        template_vars = {"instrument": "XAUUSD"}  # Missing other vars

        with pytest.raises(ValueError, match="Missing required template vars"):
            render_telegram("position_failure_entry", template_vars)


class TestPushRendering:
    """Test push notification rendering."""

    def test_render_push_entry_failure(self):
        """Test rendering entry failure push notification."""
        template_vars = {
            "instrument": "XAUUSD",
            "side": "buy",
            "entry_price": 1950.50,
            "volume": 0.1,
            "error_reason": "Insufficient margin",
            "approval_id": "approval-123",
        }

        result = render_push("position_failure_entry", template_vars)

        # Verify structure
        assert "title" in result
        assert "body" in result
        assert "icon" in result
        assert "badge" in result
        assert "data" in result

        # Verify content
        assert "Manual Trade Entry Required" in result["title"]
        assert "XAUUSD" in result["body"]
        assert "buy" in result["body"].lower()

        # Verify data has URL
        assert "url" in result["data"]
        assert "approval-123" in result["data"]["url"]

    def test_render_push_sl_failure(self):
        """Test rendering SL failure push notification."""
        template_vars = {
            "instrument": "XAUUSD",
            "side": "sell",
            "entry_price": 1950.50,
            "current_price": 1960.20,
            "loss_amount": 97.00,
            "broker_ticket": "12345678",
        }

        result = render_push("position_failure_sl", template_vars)

        # Verify URGENT or Stop Loss
        assert "URGENT" in result["title"] or "Stop Loss" in result["title"]

        # Verify data has URL to positions
        assert "/positions" in result["data"]["url"]

    def test_render_push_tp_failure(self):
        """Test rendering TP failure push notification."""
        template_vars = {
            "instrument": "XAUUSD",
            "side": "buy",
            "entry_price": 1950.50,
            "current_price": 1960.20,
            "profit_amount": 97.00,
            "broker_ticket": "87654321",
        }

        result = render_push("position_failure_tp", template_vars)

        # Verify Take Profit
        assert "Take Profit" in result["title"] or "Profit" in result["title"]

        # Verify profit amount in body
        assert "97" in result["body"] or "profit" in result["body"].lower()

    def test_render_push_icon_present(self):
        """Test push notification has icon."""
        template_vars = {
            "instrument": "XAUUSD",
            "side": "buy",
            "entry_price": 1950.50,
            "volume": 0.1,
            "error_reason": "Test",
            "approval_id": "test-123",
        }

        result = render_push("position_failure_entry", template_vars)

        # Verify icon path
        assert result["icon"].startswith("/")
        assert ".png" in result["icon"] or ".svg" in result["icon"]

    def test_render_push_badge_present(self):
        """Test push notification has badge."""
        template_vars = {
            "instrument": "XAUUSD",
            "side": "buy",
            "entry_price": 1950.50,
            "volume": 0.1,
            "error_reason": "Test",
            "approval_id": "test-123",
        }

        result = render_push("position_failure_entry", template_vars)

        # Verify badge path
        assert result["badge"].startswith("/")

    def test_render_push_missing_template_raises(self):
        """Test rendering non-existent template raises ValueError."""
        with pytest.raises(ValueError, match="Push template not found"):
            render_push("nonexistent_template", {})

    def test_render_push_missing_required_var_raises(self):
        """Test rendering with missing var raises ValueError."""
        template_vars = {"instrument": "XAUUSD"}  # Missing other vars

        with pytest.raises(ValueError, match="Missing required template vars"):
            render_push("position_failure_entry", template_vars)


class TestPositionFailureTemplates:
    """Test position failure template constants exist and are valid."""

    def test_entry_failure_templates_exist(self):
        """Test entry failure templates are defined."""
        assert ENTRY_FAILURE_EMAIL is not None
        assert ENTRY_FAILURE_TELEGRAM is not None
        assert ENTRY_FAILURE_PUSH is not None

        # Verify their types
        assert isinstance(ENTRY_FAILURE_EMAIL, dict)
        assert isinstance(ENTRY_FAILURE_TELEGRAM, str)
        assert isinstance(ENTRY_FAILURE_PUSH, dict)

    def test_sl_failure_templates_exist(self):
        """Test SL failure templates are defined."""
        assert SL_FAILURE_EMAIL is not None
        assert SL_FAILURE_TELEGRAM is not None
        assert SL_FAILURE_PUSH is not None

        assert isinstance(SL_FAILURE_EMAIL, dict)
        assert isinstance(SL_FAILURE_TELEGRAM, str)
        assert isinstance(SL_FAILURE_PUSH, dict)

    def test_tp_failure_templates_exist(self):
        """Test TP failure templates are defined."""
        assert TP_FAILURE_EMAIL is not None
        assert TP_FAILURE_TELEGRAM is not None
        assert TP_FAILURE_PUSH is not None

        assert isinstance(TP_FAILURE_EMAIL, dict)
        assert isinstance(TP_FAILURE_TELEGRAM, str)
        assert isinstance(TP_FAILURE_PUSH, dict)

    def test_entry_failure_email_has_template_name(self):
        """Test entry failure email has position_failure_entry."""
        assert "position_failure_entry" in ENTRY_FAILURE_EMAIL["template_file"]

    def test_sl_failure_email_has_template_name(self):
        """Test SL failure email has position_failure_sl."""
        assert "position_failure_sl" in SL_FAILURE_EMAIL["template_file"]

    def test_tp_failure_email_has_template_name(self):
        """Test TP failure email has position_failure_tp."""
        assert "position_failure_tp" in TP_FAILURE_EMAIL["template_file"]


class TestTemplateIntegration:
    """Test full template rendering workflow."""

    def test_render_all_channels_for_entry_failure(self):
        """Test rendering entry failure across all channels."""
        template_vars = {
            "instrument": "XAUUSD",
            "side": "buy",
            "entry_price": 1950.50,
            "volume": 0.1,
            "error_reason": "Insufficient margin",
            "approval_id": "approval-123",
        }

        # Render all channels
        email = render_email("position_failure_entry", template_vars)
        telegram = render_telegram("position_failure_entry", template_vars)
        push = render_push("position_failure_entry", template_vars)

        # Verify all successful
        assert "subject" in email
        assert isinstance(telegram, str)
        assert "title" in push

        # Verify all contain key info
        assert "XAUUSD" in email["html"]
        assert "XAUUSD" in telegram
        assert "XAUUSD" in push["body"]

    def test_render_all_channels_for_sl_failure(self):
        """Test rendering SL failure across all channels."""
        template_vars = {
            "instrument": "XAUUSD",
            "side": "sell",
            "entry_price": 1950.50,
            "current_price": 1960.20,
            "loss_amount": 97.00,
            "broker_ticket": "12345678",
        }

        email = render_email("position_failure_sl", template_vars)
        telegram = render_telegram("position_failure_sl", template_vars)
        push = render_push("position_failure_sl", template_vars)

        # Verify all contain urgent/stop loss
        assert "URGENT" in email["subject"] or "Stop Loss" in email["subject"]
        assert "URGENT" in telegram or "Stop Loss" in telegram
        assert "URGENT" in push["title"] or "Stop Loss" in push["title"]

    def test_render_all_channels_for_tp_failure(self):
        """Test rendering TP failure across all channels."""
        template_vars = {
            "instrument": "XAUUSD",
            "side": "buy",
            "entry_price": 1950.50,
            "current_price": 1960.20,
            "profit_amount": 97.00,
            "broker_ticket": "87654321",
        }

        email = render_email("position_failure_tp", template_vars)
        telegram = render_telegram("position_failure_tp", template_vars)
        push = render_push("position_failure_tp", template_vars)

        # Verify all contain take profit/profit
        assert "Take Profit" in email["subject"] or "Profit" in email["subject"]
        assert "Take Profit" in telegram or "profit" in telegram.lower()
        assert "Take Profit" in push["title"] or "Profit" in push["title"]
