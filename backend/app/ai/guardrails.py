"""
AI Guardrails - Safety layer for blocking unsafe responses.

Implements:
- PII/secrets redaction
- Financial advice refusal
- Policy enforcement
- Prompt injection prevention
"""

import re
from typing import NamedTuple


class GuardrailResult(NamedTuple):
    """Result of guardrail evaluation."""

    blocked: bool
    policy_name: str | None = None
    reason: str | None = None
    redacted_text: str | None = None


class AIGuardrails:
    """Safety layer for AI responses."""

    def __init__(self):
        """Initialize patterns."""
        # Secrets patterns
        self.api_key_patterns = [
            re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),
            re.compile(
                r"(?:api|auth)[\s_-]?key[:\s=]+['\"]?([a-zA-Z0-9\-_]{20,})['\"]?",
                re.IGNORECASE,
            ),
            re.compile(
                r"secret[:\s=]+['\"]?([a-zA-Z0-9\-_]{20,})['\"]?", re.IGNORECASE
            ),
            re.compile(r"token[:\s]+([a-zA-Z0-9]{20,})", re.IGNORECASE),
            re.compile(
                r"(?:auth|bearer)\s+(?:token\s+)?([a-zA-Z0-9\-_.]{20,})", re.IGNORECASE
            ),
            re.compile(
                r"\bis\s+([A-Z]{10,}[a-z]{10,})", re.IGNORECASE
            ),  # "is LONGTOKEN" pattern
        ]

        self.aws_patterns = [
            re.compile(r"(?:AKIA|ASIA|A3T)[A-Z0-9]{16}"),
        ]

        self.private_key_patterns = [
            re.compile(r"-----BEGIN.*?PRIVATE KEY", re.IGNORECASE | re.DOTALL),
        ]

        self.db_conn_patterns = [
            re.compile(r"(?:postgres|mysql|mongodb|redis)[+]?[a-z]*://[^\s]+"),
        ]

        # PII patterns
        self.email_pattern = re.compile(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
        )
        self.uk_phone_pattern = re.compile(
            r"(?:(?:\+44|0)(?:\s)?(?:20|7[0-9]{3})\s?[0-9\s]{6,}|\b020\s?\d{4}\s?\d{4}\b|07\d{3}\s?\d{3}\s?\d{3,4}\b)"
        )
        self.uk_postcode_pattern = re.compile(
            r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}\b", re.IGNORECASE
        )
        self.credit_card_pattern = re.compile(
            r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11}|6(?:011|5[0-9]{2})[0-9]{12}|(?:2131|1800|35\d{3})\d{11})\b"
        )

        # Environment variables
        self.env_var_pattern = re.compile(
            r"(AWS_ACCESS_KEY_ID|DATABASE_URL|SECRET_KEY|OPENAI_API_KEY|STRIPE_SECRET_KEY|PRIVATE_KEY)[=:\s]+['\"]?([a-zA-Z0-9\-_/.@:]{10,})['\"]?",
            re.IGNORECASE,
        )

        # Financial advice keywords
        self.financial_keywords = [
            "guaranteed return",
            "definitely profitable",
            "will make money",
            "certain profit",
            "risk-free",
            "invest in",
            "buy now",
            "sell now",
            "sure bet",
            "always wins",
            "sure profit",
            "guaranteed profit",
            "can't lose",
            "no risk",
            "guaranteed gains",
            "guaranteed gains",
            "guaranteed returns",
            "definite profit",
        ]

        # Trading advice phrases
        self.trading_phrases = [
            "you should trade",
            "guaranteed signals",
            "100% win rate",
            "risk-free trading",
            "certain price movement",
            "this will definitely",
            "never lose",
            "always profitable",
        ]

    def check_input(self, user_message: str) -> GuardrailResult:
        """Check user input for abuse/injection."""
        # Block if too short
        if len(user_message.strip()) < 3:
            return GuardrailResult(
                blocked=True, policy_name="input_length", reason="Message too short"
            )

        # Block if ALL CAPS (spam)
        if len(user_message) > 10 and user_message.isupper():
            return GuardrailResult(
                blocked=True, policy_name="spam_detection", reason="All caps detected"
            )

        # Block if repeated characters
        if re.search(r"(.)\1{20,}", user_message):
            return GuardrailResult(
                blocked=True,
                policy_name="spam_detection",
                reason="Repeated characters detected",
            )

        # Block prompt injection markers
        injection_markers = [
            "system:",
            "ignore",
            "forget",
            "override",
            "bypass",
            "admin",
            "root",
        ]
        if any(marker in user_message.lower() for marker in injection_markers):
            return GuardrailResult(
                blocked=True,
                policy_name="prompt_injection",
                reason="Suspicious pattern detected",
            )

        # Block SQL injection
        if re.search(
            r"(DROP|DELETE|INSERT|UPDATE|UNION|SELECT).*?(FROM|WHERE|TABLE)",
            user_message,
            re.IGNORECASE,
        ):
            return GuardrailResult(
                blocked=True,
                policy_name="prompt_injection",
                reason="SQL injection attempt",
            )

        # Block command injection
        if re.search(r"[$`(){};\|&]", user_message):
            return GuardrailResult(
                blocked=True,
                policy_name="prompt_injection",
                reason="Command injection attempt",
            )

        return GuardrailResult(blocked=False)

    def check_output(self, response_text: str) -> GuardrailResult:
        """Check AI response for secrets/PII leakage."""
        # Check for API keys
        for pattern in self.api_key_patterns:
            if pattern.search(response_text):
                redacted = pattern.sub(
                    lambda m: (
                        m.group(0)[:3] + "[REDACTED]"
                        if len(m.group(0)) > 3
                        else "[REDACTED]"
                    ),
                    response_text,
                )
                return GuardrailResult(
                    blocked=True,
                    policy_name="api_key_leak",
                    reason="API key detected",
                    redacted_text=redacted,
                )

        # Check for AWS keys
        for pattern in self.aws_patterns:
            if pattern.search(response_text):
                redacted = pattern.sub("[AWS_KEY_REDACTED]", response_text)
                return GuardrailResult(
                    blocked=True,
                    policy_name="aws_key_leak",
                    reason="AWS credentials detected",
                    redacted_text=redacted,
                )

        # Check for private keys
        for pattern in self.private_key_patterns:
            if pattern.search(response_text):
                redacted = pattern.sub("[PRIVATE_KEY_REDACTED]", response_text)
                return GuardrailResult(
                    blocked=True,
                    policy_name="private_key_leak",
                    reason="Private key detected",
                    redacted_text=redacted,
                )

        # Check for DB connections
        for pattern in self.db_conn_patterns:
            if pattern.search(response_text):
                redacted = pattern.sub("[DATABASE_URL_REDACTED]", response_text)
                return GuardrailResult(
                    blocked=True,
                    policy_name="db_connection_leak",
                    reason="Database connection string detected",
                    redacted_text=redacted,
                )

        # Check for emails
        if self.email_pattern.search(response_text):
            redacted = self.email_pattern.sub("[EMAIL_REDACTED]", response_text)
            return GuardrailResult(
                blocked=True,
                policy_name="pii_email",
                reason="Email address detected",
                redacted_text=redacted,
            )

        # Check for UK phones
        if self.uk_phone_pattern.search(response_text):
            redacted = self.uk_phone_pattern.sub("[PHONE_REDACTED]", response_text)
            return GuardrailResult(
                blocked=True,
                policy_name="pii_phone",
                reason="Phone number detected",
                redacted_text=redacted,
            )

        # Check for UK postcodes
        if self.uk_postcode_pattern.search(response_text):
            redacted = self.uk_postcode_pattern.sub(
                "[POSTCODE_REDACTED]", response_text
            )
            return GuardrailResult(
                blocked=True,
                policy_name="pii_postcode",
                reason="Postcode detected",
                redacted_text=redacted,
            )

        # Check for credit cards
        if self.credit_card_pattern.search(response_text):
            redacted = self.credit_card_pattern.sub("[CARD_REDACTED]", response_text)
            return GuardrailResult(
                blocked=True,
                policy_name="credit_card_leak",
                reason="Credit card detected",
                redacted_text=redacted,
            )

        # Check for financial/trading advice
        financial_result = self.check_financial_advice(response_text)
        if financial_result.blocked:
            return financial_result

        # Check for config/env leaks
        config_result = self.check_config_leak(response_text)
        if config_result.blocked:
            return config_result

        return GuardrailResult(blocked=False)

    def check_financial_advice(self, response_text: str) -> GuardrailResult:
        """Check for prohibited financial advice."""
        lower_text = response_text.lower()

        for keyword in self.financial_keywords:
            if keyword in lower_text:
                return GuardrailResult(
                    blocked=True,
                    policy_name="financial_advice",
                    reason=f"Financial advice detected: {keyword}",
                )

        for phrase in self.trading_phrases:
            if phrase in lower_text:
                return GuardrailResult(
                    blocked=True,
                    policy_name="trading_advice",
                    reason=f"Trading advice detected: {phrase}",
                )

        return GuardrailResult(blocked=False)

    def check_config_leak(self, response_text: str) -> GuardrailResult:
        """Check for environment variable leaks."""
        if self.env_var_pattern.search(response_text):
            redacted = self.env_var_pattern.sub(r"\1=[REDACTED]", response_text)
            return GuardrailResult(
                blocked=True,
                policy_name="config_leak",
                reason="Environment variable detected",
                redacted_text=redacted,
            )

        return GuardrailResult(blocked=False)

    def sanitize_response(self, response_text: str) -> GuardrailResult:
        """Run all guardrails and return result."""
        # Check output (secrets/PII)
        result = self.check_output(response_text)
        if result.blocked:
            return result

        # Check financial advice
        result = self.check_financial_advice(response_text)
        if result.blocked:
            return result

        # Check config leak
        result = self.check_config_leak(response_text)
        if result.blocked:
            return result

        return GuardrailResult(blocked=False, redacted_text=response_text)
