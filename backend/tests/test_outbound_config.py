"""Tests for PR-017: OutboundConfig validation and environment loading.

Validates all configuration rules for HMAC client setup.
"""

import pytest

from backend.app.trading.outbound.config import OutboundConfig


class TestOutboundConfigValidation:
    """Test OutboundConfig.validate() method for all validation rules."""

    def test_validate_success_with_valid_config(self):
        """Test validation passes with all valid values."""
        config = OutboundConfig(
            enabled=True,
            producer_id="mt5-trader-1",
            producer_secret="super-secret-key-1234567890",
            server_base_url="https://api.example.com",
            timeout_seconds=30.0,
            max_body_size=65536,
        )
        # Should not raise
        config.validate()

    def test_validate_raises_on_empty_producer_id(self):
        """Test validation rejects empty producer_id."""
        with pytest.raises(ValueError, match="producer_id must be non-empty"):
            config = OutboundConfig(
                enabled=True,
                producer_id="",
                producer_secret="super-secret-key-1234567890",
                server_base_url="https://api.example.com",
                timeout_seconds=30.0,
                max_body_size=65536,
            )

    def test_validate_raises_on_whitespace_producer_id(self):
        """Test validation rejects whitespace-only producer_id."""
        with pytest.raises(ValueError, match="producer_id must be non-empty"):
            config = OutboundConfig(
                enabled=True,
                producer_id="   ",
                producer_secret="super-secret-key-1234567890",
                server_base_url="https://api.example.com",
                timeout_seconds=30.0,
                max_body_size=65536,
            )

    def test_validate_raises_on_empty_producer_secret(self):
        """Test validation rejects empty producer_secret."""
        with pytest.raises(ValueError, match="producer_secret must be non-empty"):
            config = OutboundConfig(
                enabled=True,
                producer_id="mt5-trader-1",
                producer_secret="",
                server_base_url="https://api.example.com",
                timeout_seconds=30.0,
                max_body_size=65536,
            )

    def test_validate_raises_on_short_producer_secret(self):
        """Test validation rejects producer_secret less than 16 bytes."""
        with pytest.raises(
            ValueError, match="producer_secret must be at least 16 bytes"
        ):
            config = OutboundConfig(
                enabled=True,
                producer_id="mt5-trader-1",
                producer_secret="short",  # Only 5 bytes
                server_base_url="https://api.example.com",
                timeout_seconds=30.0,
                max_body_size=65536,
            )

    def test_validate_accepts_16_byte_secret(self):
        """Test validation accepts exactly 16-byte producer_secret."""
        config = OutboundConfig(
            enabled=True,
            producer_id="mt5-trader-1",
            producer_secret="exactly16bytes!!",  # Exactly 16 bytes
            server_base_url="https://api.example.com",
            timeout_seconds=30.0,
            max_body_size=65536,
        )
        # Should not raise during construction
        assert config is not None

    def test_validate_raises_on_empty_server_url(self):
        """Test validation rejects empty server_base_url."""
        with pytest.raises(ValueError, match="server_base_url must be non-empty"):
            config = OutboundConfig(
                enabled=True,
                producer_id="mt5-trader-1",
                producer_secret="super-secret-key-1234567890",
                server_base_url="",
                timeout_seconds=30.0,
                max_body_size=65536,
            )

    def test_validate_raises_on_timeout_too_small(self):
        """Test validation rejects timeout_seconds < 5.0."""
        with pytest.raises(ValueError, match="timeout_seconds must be >= 5.0"):
            config = OutboundConfig(
                enabled=True,
                producer_id="mt5-trader-1",
                producer_secret="super-secret-key-1234567890",
                server_base_url="https://api.example.com",
                timeout_seconds=4.9,  # Less than 5.0
                max_body_size=65536,
            )

    def test_validate_accepts_5_second_timeout(self):
        """Test validation accepts timeout_seconds >= 5.0."""
        config = OutboundConfig(
            enabled=True,
            producer_id="mt5-trader-1",
            producer_secret="super-secret-key-1234567890",
            server_base_url="https://api.example.com",
            timeout_seconds=5.0,
            max_body_size=65536,
        )
        # Should not raise during construction
        assert config is not None

    def test_validate_raises_on_timeout_too_large(self):
        """Test validation rejects timeout_seconds > 300.0."""
        with pytest.raises(ValueError, match="timeout_seconds must be <= 300.0"):
            config = OutboundConfig(
                enabled=True,
                producer_id="mt5-trader-1",
                producer_secret="super-secret-key-1234567890",
                server_base_url="https://api.example.com",
                timeout_seconds=300.1,  # Greater than 300.0
                max_body_size=65536,
            )

    def test_validate_accepts_300_second_timeout(self):
        """Test validation accepts timeout_seconds <= 300.0."""
        config = OutboundConfig(
            enabled=True,
            producer_id="mt5-trader-1",
            producer_secret="super-secret-key-1234567890",
            server_base_url="https://api.example.com",
            timeout_seconds=300.0,
            max_body_size=65536,
        )
        # Should not raise during construction
        assert config is not None

    def test_validate_raises_on_body_size_too_small(self):
        """Test validation rejects max_body_size < 1024."""
        with pytest.raises(ValueError, match="max_body_size must be >= 1024 bytes"):
            config = OutboundConfig(
                enabled=True,
                producer_id="mt5-trader-1",
                producer_secret="super-secret-key-1234567890",
                server_base_url="https://api.example.com",
                timeout_seconds=30.0,
                max_body_size=1023,  # Less than 1024
            )

    def test_validate_accepts_1024_body_size(self):
        """Test validation accepts max_body_size >= 1024."""
        config = OutboundConfig(
            enabled=True,
            producer_id="mt5-trader-1",
            producer_secret="super-secret-key-1234567890",
            server_base_url="https://api.example.com",
            timeout_seconds=30.0,
            max_body_size=1024,
        )
        # Should not raise during construction
        assert config is not None

    def test_validate_raises_on_body_size_too_large(self):
        """Test validation rejects max_body_size > 10 MB."""
        with pytest.raises(ValueError, match="max_body_size must be <= 10 MB"):
            config = OutboundConfig(
                enabled=True,
                producer_id="mt5-trader-1",
                producer_secret="super-secret-key-1234567890",
                server_base_url="https://api.example.com",
                timeout_seconds=30.0,
                max_body_size=10_485_761,  # Greater than 10 MB
            )

    def test_validate_accepts_10mb_body_size(self):
        """Test validation accepts max_body_size <= 10 MB."""
        config = OutboundConfig(
            enabled=True,
            producer_id="mt5-trader-1",
            producer_secret="super-secret-key-1234567890",
            server_base_url="https://api.example.com",
            timeout_seconds=30.0,
            max_body_size=10_485_760,  # Exactly 10 MB
        )
        # Should not raise during construction
        assert config is not None


class TestOutboundConfigFromEnv:
    """Test OutboundConfig.from_env() method for environment variable loading."""

    def test_from_env_loads_with_all_variables_set(self, monkeypatch):
        """Test from_env() loads config when all env vars are present."""
        monkeypatch.setenv("HMAC_PRODUCER_ENABLED", "true")
        monkeypatch.setenv("HMAC_PRODUCER_SECRET", "my-super-secret-key-1234567890")
        monkeypatch.setenv("PRODUCER_ID", "mt5-trader-1")
        monkeypatch.setenv("OUTBOUND_SERVER_URL", "https://api.example.com")
        monkeypatch.setenv("OUTBOUND_TIMEOUT_SECONDS", "30")
        monkeypatch.setenv("OUTBOUND_MAX_BODY_SIZE", "65536")

        config = OutboundConfig.from_env()

        assert config.enabled is True
        assert config.producer_id == "mt5-trader-1"
        assert config.producer_secret == "my-super-secret-key-1234567890"
        assert config.server_base_url == "https://api.example.com"
        assert config.timeout_seconds == 30.0
        assert config.max_body_size == 65536

    def test_from_env_raises_on_missing_enabled_var(self, monkeypatch):
        """Test from_env() uses default when HMAC_PRODUCER_ENABLED is missing."""
        # Clear the variable if it exists
        monkeypatch.delenv("HMAC_PRODUCER_ENABLED", raising=False)
        monkeypatch.setenv("HMAC_PRODUCER_SECRET", "my-super-secret-key-1234567890")
        monkeypatch.setenv("PRODUCER_ID", "mt5-trader-1")
        monkeypatch.setenv("OUTBOUND_SERVER_URL", "https://api.example.com")

        config = OutboundConfig.from_env()
        # Default should be "true"
        assert config.enabled is True

    def test_from_env_raises_on_missing_secret(self, monkeypatch):
        """Test from_env() raises when HMAC_PRODUCER_SECRET is missing."""
        monkeypatch.setenv("HMAC_PRODUCER_ENABLED", "true")
        monkeypatch.delenv("HMAC_PRODUCER_SECRET", raising=False)
        monkeypatch.setenv("PRODUCER_ID", "mt5-trader-1")
        monkeypatch.setenv("OUTBOUND_SERVER_URL", "https://api.example.com")

        with pytest.raises(ValueError, match="HMAC_PRODUCER_SECRET"):
            OutboundConfig.from_env()

    def test_from_env_raises_on_missing_server_url(self, monkeypatch):
        """Test from_env() raises when OUTBOUND_SERVER_URL is missing."""
        monkeypatch.setenv("HMAC_PRODUCER_ENABLED", "true")
        monkeypatch.setenv("HMAC_PRODUCER_SECRET", "my-super-secret-key-1234567890")
        monkeypatch.setenv("PRODUCER_ID", "mt5-trader-1")
        monkeypatch.delenv("OUTBOUND_SERVER_URL", raising=False)

        with pytest.raises(ValueError, match="OUTBOUND_SERVER_URL"):
            OutboundConfig.from_env()

    def test_from_env_uses_hostname_as_default_producer_id(self, monkeypatch):
        """Test from_env() uses hostname when PRODUCER_ID is not set."""
        monkeypatch.setenv("HMAC_PRODUCER_ENABLED", "true")
        monkeypatch.setenv("HMAC_PRODUCER_SECRET", "my-super-secret-key-1234567890")
        monkeypatch.delenv("PRODUCER_ID", raising=False)
        monkeypatch.setenv("OUTBOUND_SERVER_URL", "https://api.example.com")

        config = OutboundConfig.from_env()

        # Should use hostname
        assert config.producer_id is not None
        assert len(config.producer_id) > 0

    def test_from_env_parses_timeout_as_float(self, monkeypatch):
        """Test from_env() correctly parses OUTBOUND_TIMEOUT_SECONDS."""
        monkeypatch.setenv("HMAC_PRODUCER_ENABLED", "true")
        monkeypatch.setenv("HMAC_PRODUCER_SECRET", "my-super-secret-key-1234567890")
        monkeypatch.setenv("PRODUCER_ID", "mt5-trader-1")
        monkeypatch.setenv("OUTBOUND_SERVER_URL", "https://api.example.com")
        monkeypatch.setenv("OUTBOUND_TIMEOUT_SECONDS", "15.5")

        config = OutboundConfig.from_env()

        assert config.timeout_seconds == 15.5

    def test_from_env_parses_body_size_as_int(self, monkeypatch):
        """Test from_env() correctly parses OUTBOUND_MAX_BODY_SIZE."""
        monkeypatch.setenv("HMAC_PRODUCER_ENABLED", "true")
        monkeypatch.setenv("HMAC_PRODUCER_SECRET", "my-super-secret-key-1234567890")
        monkeypatch.setenv("PRODUCER_ID", "mt5-trader-1")
        monkeypatch.setenv("OUTBOUND_SERVER_URL", "https://api.example.com")
        monkeypatch.setenv("OUTBOUND_MAX_BODY_SIZE", "131072")

        config = OutboundConfig.from_env()

        assert config.max_body_size == 131072

    def test_from_env_disabled_config_ignores_env_values(self, monkeypatch):
        """Test from_env() disabled config uses dummy values, not env vars."""
        monkeypatch.setenv("HMAC_PRODUCER_ENABLED", "false")
        monkeypatch.delenv("HMAC_PRODUCER_SECRET", raising=False)
        monkeypatch.setenv("PRODUCER_ID", "mt5-trader-1")
        monkeypatch.setenv("OUTBOUND_SERVER_URL", "https://api.example.com")

        # Disabled config ignores env vars and uses built-in dummy values
        config = OutboundConfig.from_env()
        assert config.enabled is False
        assert config.producer_id == "disabled-producer-id"
        assert config.producer_secret == "disabled-secret-1234"

    def test_from_env_disabled_config_with_valid_params(self, monkeypatch):
        """Test from_env() disabled config with all valid parameters."""
        monkeypatch.setenv("HMAC_PRODUCER_ENABLED", "false")
        monkeypatch.setenv("HMAC_PRODUCER_SECRET", "super-secret-key-1234567890")
        monkeypatch.setenv("PRODUCER_ID", "mt5-trader-1")
        monkeypatch.setenv("OUTBOUND_SERVER_URL", "https://api.example.com")

        config = OutboundConfig.from_env()

        assert config.enabled is False

    def test_from_env_raises_on_invalid_timeout_format(self, monkeypatch):
        """Test from_env() raises when OUTBOUND_TIMEOUT_SECONDS is not a float."""
        monkeypatch.setenv("HMAC_PRODUCER_ENABLED", "true")
        monkeypatch.setenv("HMAC_PRODUCER_SECRET", "my-super-secret-key-1234567890")
        monkeypatch.setenv("PRODUCER_ID", "mt5-trader-1")
        monkeypatch.setenv("OUTBOUND_SERVER_URL", "https://api.example.com")
        monkeypatch.setenv("OUTBOUND_TIMEOUT_SECONDS", "not-a-number")

        with pytest.raises(
            ValueError, match="OUTBOUND_TIMEOUT_SECONDS must be a float"
        ):
            OutboundConfig.from_env()

    def test_from_env_raises_on_invalid_body_size_format(self, monkeypatch):
        """Test from_env() raises when OUTBOUND_MAX_BODY_SIZE is not an integer."""
        monkeypatch.setenv("HMAC_PRODUCER_ENABLED", "true")
        monkeypatch.setenv("HMAC_PRODUCER_SECRET", "my-super-secret-key-1234567890")
        monkeypatch.setenv("PRODUCER_ID", "mt5-trader-1")
        monkeypatch.setenv("OUTBOUND_SERVER_URL", "https://api.example.com")
        monkeypatch.setenv("OUTBOUND_MAX_BODY_SIZE", "not-an-integer")

        with pytest.raises(
            ValueError, match="OUTBOUND_MAX_BODY_SIZE must be an integer"
        ):
            OutboundConfig.from_env()


class TestOutboundConfigEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_config_with_very_long_producer_id(self):
        """Test config accepts very long producer_id."""
        long_id = "x" * 10000
        config = OutboundConfig(
            enabled=True,
            producer_id=long_id,
            producer_secret="super-secret-key-1234567890",
            server_base_url="https://api.example.com",
            timeout_seconds=30.0,
            max_body_size=65536,
        )
        assert config is not None

    def test_config_with_special_chars_in_secret(self):
        """Test config accepts special characters in producer_secret."""
        secret = "!@#$%^&*()-_=+[]{};:'\"<>?,./super-secret"
        config = OutboundConfig(
            enabled=True,
            producer_id="mt5-trader-1",
            producer_secret=secret,
            server_base_url="https://api.example.com",
            timeout_seconds=30.0,
            max_body_size=65536,
        )
        assert config is not None

    def test_config_with_https_and_http_urls(self):
        """Test config accepts both HTTPS and HTTP server URLs."""
        for url in ["https://api.example.com", "http://localhost:8000"]:
            config = OutboundConfig(
                enabled=True,
                producer_id="mt5-trader-1",
                producer_secret="super-secret-key-1234567890",
                server_base_url=url,
                timeout_seconds=30.0,
                max_body_size=65536,
            )
            assert config is not None

    def test_config_repr_shows_relevant_fields(self):
        """Test __repr__ shows config details."""
        config = OutboundConfig(
            enabled=True,
            producer_id="mt5-trader-1",
            producer_secret="super-secret-key-1234567890",
            server_base_url="https://api.example.com",
            timeout_seconds=30.0,
            max_body_size=65536,
        )
        repr_str = repr(config)
        assert "OutboundConfig" in repr_str
        assert "mt5-trader-1" in repr_str
