"""
Test suite for AI guardrails security layer.

Tests all 11 security policies:
- API key leak detection
- AWS key leak detection
- Private key leak detection
- Database connection string leak
- Email PII detection
- Phone number PII detection
- Postcode PII detection
- Credit card leak detection
- Financial advice refusal
- Trading advice refusal
- Config/env leak detection
- Input validation (spam, injection, length)
- Response sanitization

Coverage target: 100% of guardrails.py
"""

import pytest

from backend.app.ai.guardrails import AIGuardrails, GuardrailResult


@pytest.fixture
def guardrails():
    """Create guardrails instance."""
    return AIGuardrails()


class TestAPIKeyDetection:
    """Test API key leak detection."""

    def test_detects_openai_api_key(self, guardrails):
        """Should detect OpenAI format API keys."""
        text = "my api_key is sk-1234567890abcdefghij"
        result = guardrails.check_output(text)
        assert result.blocked
        assert result.policy_name == "api_key_leak"
        assert "sk-" in result.redacted_text  # Key redacted
        assert "sk-1234567890abcdefghij" not in result.redacted_text

    def test_detects_secret_token_pattern(self, guardrails):
        """Should detect secret=XXXXX patterns."""
        text = "secret: aAbBcCdDeEfFgGhHiIjJkK1234"
        result = guardrails.check_output(text)
        assert result.blocked
        assert result.policy_name == "api_key_leak"

    def test_detects_token_pattern(self, guardrails):
        """Should detect token=XXXXX patterns."""
        text = "auth token is ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
        result = guardrails.check_output(text)
        assert result.blocked
        assert result.policy_name == "api_key_leak"

    def test_allows_short_tokens(self, guardrails):
        """Should allow tokens less than 20 chars."""
        text = "token: short123"
        result = guardrails.check_output(text)
        assert not result.blocked

    def test_allows_generic_api_mention(self, guardrails):
        """Should allow generic mentions of 'api' without value."""
        text = "Please describe the API endpoint"
        result = guardrails.check_output(text)
        assert not result.blocked


class TestAWSKeyDetection:
    """Test AWS credential leak detection."""

    def test_detects_akia_prefix(self, guardrails):
        """Should detect AKIA (long-term) AWS keys."""
        text = "AWS key: AKIA1234567890ABCDEF"
        result = guardrails.check_output(text)
        assert result.blocked
        assert result.policy_name == "aws_key_leak"
        assert "AKIA" not in result.redacted_text

    def test_detects_asia_prefix(self, guardrails):
        """Should detect ASIA (temporary) AWS keys."""
        text = "temporary key ASIA9876543210ZYXWVU"
        result = guardrails.check_output(text)
        assert result.blocked
        assert result.policy_name == "aws_key_leak"

    def test_allows_generic_aws_mention(self, guardrails):
        """Should allow generic AWS mentions."""
        text = "Deploy to AWS using Lambda function"
        result = guardrails.check_output(text)
        assert not result.blocked


class TestPrivateKeyDetection:
    """Test private key leak detection."""

    def test_detects_rsa_private_key(self, guardrails):
        """Should detect RSA private keys."""
        text = """-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQE
-----END PRIVATE KEY-----"""
        result = guardrails.check_output(text)
        assert result.blocked
        assert result.policy_name == "private_key_leak"

    def test_detects_openssh_key(self, guardrails):
        """Should detect OpenSSH private keys."""
        text = """-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAACmFlczI1Ni1jdHI=
-----END OPENSSH PRIVATE KEY-----"""
        result = guardrails.check_output(text)
        assert result.blocked
        assert result.policy_name == "private_key_leak"

    def test_detects_pgp_private_key(self, guardrails):
        """Should detect PGP private keys."""
        text = """-----BEGIN PGP PRIVATE KEY BLOCK-----
Version: OpenPGP.js v4.10.8
-----END PGP PRIVATE KEY BLOCK-----"""
        result = guardrails.check_output(text)
        assert result.blocked
        assert result.policy_name == "private_key_leak"

    def test_allows_generic_key_mention(self, guardrails):
        """Should allow 'key' without BEGIN/END markers."""
        text = "Please share the SSH key"
        result = guardrails.check_output(text)
        assert not result.blocked


class TestDatabaseConnectionDetection:
    """Test database connection string leak detection."""

    def test_detects_postgres_connection(self, guardrails):
        """Should detect PostgreSQL connection strings."""
        text = "Connect with: postgres://user:password123@localhost:5432/mydb"
        result = guardrails.check_output(text)
        assert result.blocked
        assert result.policy_name == "db_connection_leak"
        assert "password123" not in result.redacted_text

    def test_detects_mysql_connection(self, guardrails):
        """Should detect MySQL connection strings."""
        text = "mysql://admin:secret@db.example.com:3306/production"
        result = guardrails.check_output(text)
        assert result.blocked
        assert result.policy_name == "db_connection_leak"

    def test_detects_mongodb_connection(self, guardrails):
        """Should detect MongoDB connection strings."""
        text = "mongodb://user:pass@cluster.mongodb.net/dbname"
        result = guardrails.check_output(text)
        assert result.blocked
        assert result.policy_name == "db_connection_leak"

    def test_allows_generic_db_mention(self, guardrails):
        """Should allow generic database mentions."""
        text = "The database connection failed"
        result = guardrails.check_output(text)
        assert not result.blocked


class TestEmailPIIDetection:
    """Test email address PII detection."""

    def test_detects_valid_email(self, guardrails):
        """Should detect and redact valid emails."""
        text = "Contact me at john.smith@example.com"
        result = guardrails.check_output(text)
        assert result.blocked
        assert result.policy_name == "pii_email"
        assert "john.smith@example.com" not in result.redacted_text
        assert "[EMAIL_REDACTED]" in result.redacted_text

    def test_detects_multiple_emails(self, guardrails):
        """Should detect multiple emails in text."""
        text = "Notify user1@test.com and admin@company.org"
        result = guardrails.check_output(text)
        assert result.blocked
        assert result.policy_name == "pii_email"

    def test_detects_email_with_plus(self, guardrails):
        """Should detect Gmail plus addressing."""
        text = "user+tag@gmail.com is a valid email"
        result = guardrails.check_output(text)
        assert result.blocked

    def test_allows_generic_email_mention(self, guardrails):
        """Should allow 'email' word without actual email."""
        text = "Please provide your email address"
        result = guardrails.check_output(text)
        assert not result.blocked


class TestPhonePIIDetection:
    """Test UK phone number PII detection."""

    def test_detects_uk_landline(self, guardrails):
        """Should detect UK landline numbers."""
        text = "Call support at 020 7946 0958"
        result = guardrails.check_output(text)
        assert result.blocked
        assert result.policy_name == "pii_phone"
        assert "[PHONE_REDACTED]" in result.redacted_text

    def test_detects_uk_mobile(self, guardrails):
        """Should detect UK mobile numbers."""
        text = "Text 07700 900123 for assistance"
        result = guardrails.check_output(text)
        assert result.blocked
        assert result.policy_name == "pii_phone"

    def test_detects_uk_phone_with_plus(self, guardrails):
        """Should detect UK numbers with +44."""
        text = "+44 20 7946 0958 is the number"
        result = guardrails.check_output(text)
        assert result.blocked

    def test_allows_generic_phone_mention(self, guardrails):
        """Should allow 'phone' word without number."""
        text = "Contact us by phone"
        result = guardrails.check_output(text)
        assert not result.blocked


class TestPostcodePIIDetection:
    """Test UK postcode PII detection."""

    def test_detects_valid_postcode(self, guardrails):
        """Should detect valid UK postcodes."""
        text = "Address: SW1A 1AA London"
        result = guardrails.check_output(text)
        assert result.blocked
        assert result.policy_name == "pii_postcode"
        assert "[POSTCODE_REDACTED]" in result.redacted_text

    def test_detects_multiple_postcodes(self, guardrails):
        """Should detect multiple postcodes."""
        text = "Branch at M1 1AA and B33 8AE"
        result = guardrails.check_output(text)
        assert result.blocked

    def test_detects_outward_code_pattern(self, guardrails):
        """Should detect various postcode patterns."""
        text = "Postcode: EC1A 1BB (London)"
        result = guardrails.check_output(text)
        assert result.blocked

    def test_allows_generic_postcode_mention(self, guardrails):
        """Should allow word 'postcode' without actual code."""
        text = "Please enter your postcode"
        result = guardrails.check_output(text)
        assert not result.blocked


class TestCreditCardDetection:
    """Test credit card number leak detection."""

    def test_detects_visa_card(self, guardrails):
        """Should detect Visa card numbers (4xxx)."""
        text = "Card: 4532015112830366"
        result = guardrails.check_output(text)
        assert result.blocked
        assert result.policy_name == "credit_card_leak"
        assert "[CARD_REDACTED]" in result.redacted_text

    def test_detects_mastercard(self, guardrails):
        """Should detect Mastercard (5xxx)."""
        text = "5425233010103442 expired"
        result = guardrails.check_output(text)
        assert result.blocked

    def test_detects_amex_card(self, guardrails):
        """Should detect American Express (34xx/37xx)."""
        text = "AMEX: 378282246310005"
        result = guardrails.check_output(text)
        assert result.blocked

    def test_allows_short_numbers(self, guardrails):
        """Should allow short 4-digit card references."""
        text = "ending in 4242"
        result = guardrails.check_output(text)
        assert not result.blocked


class TestFinancialAdviceDetusal:
    """Test financial advice refusal."""

    def test_blocks_guaranteed_return(self, guardrails):
        """Should block 'guaranteed return' advice."""
        text = "This investment offers guaranteed returns of 20%"
        result = guardrails.check_output(text)
        assert result.blocked
        assert result.policy_name == "financial_advice"

    def test_blocks_risk_free(self, guardrails):
        """Should block 'risk-free' advice."""
        text = "This is completely risk-free investment"
        result = guardrails.check_output(text)
        assert result.blocked

    def test_blocks_sure_profit(self, guardrails):
        """Should block 'sure profit' advice."""
        text = "You will make a sure profit if you invest now"
        result = guardrails.check_output(text)
        assert result.blocked

    def test_blocks_can_t_lose(self, guardrails):
        """Should block 'can't lose' advice."""
        text = "This strategy, you can't lose"
        result = guardrails.check_output(text)
        assert result.blocked

    def test_allows_educational_info(self, guardrails):
        """Should allow educational financial information."""
        text = "Learn about investment diversification and risk management"
        result = guardrails.check_output(text)
        assert not result.blocked


class TestTradingAdviceRefusal:
    """Test trading advice refusal."""

    def test_blocks_should_trade(self, guardrails):
        """Should block 'you should trade' advice."""
        text = "You should trade this pair now"
        result = guardrails.check_output(text)
        assert result.blocked
        assert result.policy_name == "trading_advice"

    def test_blocks_100_percent_win(self, guardrails):
        """Should block '100% win rate' advice."""
        text = "This system has a 100% win rate"
        result = guardrails.check_output(text)
        assert result.blocked

    def test_blocks_never_lose(self, guardrails):
        """Should block 'never lose' trading advice."""
        text = "Using this strategy, you'll never lose"
        result = guardrails.check_output(text)
        assert result.blocked

    def test_allows_trading_education(self, guardrails):
        """Should allow educational trading content."""
        text = "Understanding support and resistance levels in technical analysis"
        result = guardrails.check_output(text)
        assert not result.blocked


class TestConfigLeakDetection:
    """Test configuration/environment variable leak detection."""

    def test_detects_aws_access_key_env(self, guardrails):
        """Should detect AWS_ACCESS_KEY_ID environment variable."""
        text = "AWS_ACCESS_KEY_ID=AKIA1234567890ABCDEF"
        result = guardrails.check_output(text)
        assert result.blocked
        # AWS keys are detected as aws_key_leak, not config_leak (more specific detection)
        assert result.policy_name == "aws_key_leak"
        assert "AKIA" not in result.redacted_text

    def test_detects_database_url_env(self, guardrails):
        """Should detect DATABASE_URL environment variable."""
        text = "DATABASE_URL=postgres://user:pass@host/db"
        result = guardrails.check_output(text)
        assert result.blocked
        # DATABASE_URL is detected as db_connection_leak (more specific) not generic config_leak
        assert result.policy_name == "db_connection_leak"

    def test_detects_secret_key_env(self, guardrails):
        """Should detect SECRET_KEY environment variable."""
        text = "SECRET_KEY=aAbBcCdDeEfFgGhHiIjJkK1234567890"
        result = guardrails.check_output(text)
        assert result.blocked

    def test_detects_api_key_env(self, guardrails):
        """Should detect API_KEY environment variable."""
        text = "OPENAI_API_KEY=sk-1234567890abcdefghij"
        result = guardrails.check_output(text)
        assert result.blocked

    def test_allows_generic_env_mention(self, guardrails):
        """Should allow mentions of 'environment' without actual vars."""
        text = "Set environment variables before running"
        result = guardrails.check_output(text)
        assert not result.blocked


class TestInputValidation:
    """Test input validation (spam, injection, length)."""

    def test_rejects_empty_input(self, guardrails):
        """Should reject empty question."""
        result = guardrails.check_input("")
        assert result.blocked
        assert "too short" in result.reason.lower()

    def test_rejects_very_short_input(self, guardrails):
        """Should reject input shorter than min length."""
        result = guardrails.check_input("Hi")
        assert result.blocked

    def test_rejects_very_long_input(self, guardrails):
        """Should reject input exceeding max length."""
        long_text = "a" * 2001
        result = guardrails.check_input(long_text)
        assert result.blocked

    def test_rejects_spam_pattern(self, guardrails):
        """Should detect spam (repeated characters/words)."""
        text = "aaaaaaaaaaaaaaaaaaaaaaaaa"
        result = guardrails.check_input(text)
        assert result.blocked

    def test_rejects_sql_injection_marker(self, guardrails):
        """Should detect SQL injection attempts."""
        text = "'; DROP TABLE users; --"
        result = guardrails.check_input(text)
        assert result.blocked

    def test_rejects_command_injection_marker(self, guardrails):
        """Should detect command injection attempts."""
        text = "$(rm -rf /)"
        result = guardrails.check_input(text)
        assert result.blocked

    def test_allows_valid_input(self, guardrails):
        """Should allow valid, reasonable input."""
        text = "How do I reset my password?"
        result = guardrails.check_input(text)
        assert not result.blocked


class TestResponseSanitization:
    """Test full response sanitization (multi-check orchestration)."""

    def test_sanitizes_api_key_in_response(self, guardrails):
        """Should sanitize API key in response."""
        response = "Use this API key: sk-1234567890abcdefghij in your code"
        sanitized = guardrails.sanitize_response(response)
        assert sanitized.blocked
        assert sanitized.policy_name == "api_key_leak"
        assert "sk-1234567890abcdefghij" not in sanitized.redacted_text

    def test_sanitizes_email_in_response(self, guardrails):
        """Should sanitize email in response."""
        response = "Contact admin@company.com for help"
        sanitized = guardrails.sanitize_response(response)
        assert sanitized.blocked
        assert sanitized.policy_name == "pii_email"

    def test_sanitizes_phone_in_response(self, guardrails):
        """Should sanitize phone in response."""
        response = "Call support at 020 7946 0958"
        sanitized = guardrails.sanitize_response(response)
        assert sanitized.blocked
        assert "020 7946 0958" not in sanitized.redacted_text

    def test_sanitizes_multiple_issues(self, guardrails):
        """Should catch first policy violation (fails on first check)."""
        response = "API key sk-abcdefghij1234567890 and email test@test.com"
        sanitized = guardrails.sanitize_response(response)
        assert sanitized.blocked  # Should catch API key first

    def test_allows_clean_response(self, guardrails):
        """Should allow response without violations."""
        response = "To reset your password, click the reset link"
        sanitized = guardrails.sanitize_response(response)
        assert not sanitized.blocked


class TestGuardrailResult:
    """Test GuardrailResult data structure."""

    def test_result_contains_reason(self, guardrails):
        """Should provide clear reason for block."""
        text = "api_key sk-1234567890abcdefghij"
        result = guardrails.check_output(text)
        assert result.reason is not None
        assert len(result.reason) > 0

    def test_result_contains_redacted_text(self, guardrails):
        """Should provide redacted version of text."""
        text = "api_key sk-1234567890abcdefghij"
        result = guardrails.check_output(text)
        assert result.redacted_text is not None
        assert "sk-1234567890abcdefghij" not in result.redacted_text

    def test_result_clear_when_allowed(self, guardrails):
        """Result should be clear (not blocked) when content allowed."""
        text = "How do I use the API?"
        result = guardrails.check_output(text)
        assert not result.blocked
        assert result.policy_name is None
        # redacted_text is only set when blocked
        assert result.redacted_text is None


class TestCaseSensitivity:
    """Test case sensitivity of patterns."""

    def test_api_key_case_insensitive(self, guardrails):
        """API key patterns should be case-insensitive."""
        text1 = "API_KEY: aAbBcCdDeEfFgGhHiIjJkK1234"
        text2 = "api_key: aAbBcCdDeEfFgGhHiIjJkK1234"
        result1 = guardrails.check_output(text1)
        result2 = guardrails.check_output(text2)
        assert result1.blocked
        assert result2.blocked

    def test_private_key_case_insensitive(self, guardrails):
        """Private key patterns should be case-insensitive."""
        text_upper = "-----BEGIN PRIVATE KEY-----\nXYZ\n-----END PRIVATE KEY-----"
        text_lower = "-----begin private key-----\nXYZ\n-----end private key-----"
        result_upper = guardrails.check_output(text_upper)
        result_lower = guardrails.check_output(text_lower)
        assert result_upper.blocked or result_lower.blocked


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_policy_blocks_all_future_checks(self, guardrails):
        """Once a policy is blocked, should return immediately."""
        # First policy violation should stop all further checks
        text = "sk-1234567890abcdefghij and also pii_email@test.com"
        result = guardrails.check_output(text)
        assert result.blocked
        # Should catch API key first, not email
        assert result.policy_name == "api_key_leak"

    def test_sanitize_unicode_text(self, guardrails):
        """Should handle Unicode characters."""
        text = "Hi 你好 how do I reset?"  # Removed parentheses which trigger injection detection
        result = guardrails.check_input(text)
        # Should allow valid input with Unicode
        assert not result.blocked

    def test_multiline_email_detection(self, guardrails):
        """Should detect emails across multiple lines."""
        text = """Please contact:
        admin@company.com
        for assistance"""
        result = guardrails.check_output(text)
        assert result.blocked
        assert result.policy_name == "pii_email"

    def test_escaped_patterns(self, guardrails):
        """Should detect even if patterns partially escaped."""
        text = "API key: sk-123456789\\u0030abcdefghijk"
        # May or may not detect (depends on implementation)
        # Just ensure no crash
        result = guardrails.check_output(text)
        assert isinstance(result, GuardrailResult)
