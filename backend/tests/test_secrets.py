"""Secrets management tests."""

import os
from unittest.mock import patch

import pytest

from backend.app.core.secrets import (
    DotenvProvider,
    EnvProvider,
    SecretManager,
    VaultProvider,
    get_secret_manager,
)


class TestDotenvProvider:
    """Test .env file based secret provider."""

    @pytest.mark.asyncio
    async def test_dotenv_get_secret(self, tmp_path):
        """Test reading secret from .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_SECRET=secret_value\n")

        # Patch at SOURCE (dotenv module), not the re-export
        # DotenvProvider does local import: from dotenv import dotenv_values
        # So we must patch 'dotenv.dotenv_values', not 'backend.app.core.secrets.dotenv_values'
        with patch("dotenv.dotenv_values") as mock_dotenv:
            mock_dotenv.return_value = {"TEST_SECRET": "secret_value"}

            # Create provider INSIDE patch context
            provider = DotenvProvider()
            result = await provider.get_secret("TEST_SECRET")

            assert result == "secret_value"
            mock_dotenv.assert_called_once()

    @pytest.mark.asyncio
    async def test_dotenv_get_secret_not_found(self):
        """Test getting non-existent secret raises error."""
        with patch("dotenv.dotenv_values") as mock_dotenv:
            mock_dotenv.return_value = {}

            provider = DotenvProvider()

            with pytest.raises(ValueError, match="Secret not found"):
                await provider.get_secret("NONEXISTENT")

    @pytest.mark.asyncio
    async def test_dotenv_get_secret_with_default(self):
        """Test getting secret with default value."""
        with patch("backend.app.core.secrets.dotenv_values") as mock_dotenv:
            mock_dotenv.return_value = {}

            provider = DotenvProvider()
            result = await provider.get_secret("NONEXISTENT", default="default_value")

            assert result == "default_value"

    @pytest.mark.asyncio
    async def test_dotenv_set_secret(self):
        """Test setting secret in memory."""
        with patch("backend.app.core.secrets.dotenv_values") as mock_dotenv:
            mock_dotenv.return_value = {}

            provider = DotenvProvider()
            await provider.set_secret("NEW_SECRET", "new_value")

            result = await provider.get_secret("NEW_SECRET")
            assert result == "new_value"


class TestEnvProvider:
    """Test environment variable based secret provider."""

    @pytest.mark.asyncio
    async def test_env_get_secret(self):
        """Test reading secret from environment."""
        os.environ["TEST_ENV_SECRET"] = "env_secret_value"

        try:
            provider = EnvProvider()
            result = await provider.get_secret("TEST_ENV_SECRET")

            assert result == "env_secret_value"
        finally:
            del os.environ["TEST_ENV_SECRET"]

    @pytest.mark.asyncio
    async def test_env_get_secret_not_found(self):
        """Test getting non-existent env var raises error."""
        provider = EnvProvider()

        with pytest.raises(ValueError, match="Secret not found"):
            await provider.get_secret("DEFINITELY_NOT_SET_12345")

    @pytest.mark.asyncio
    async def test_env_get_secret_with_default(self):
        """Test getting secret with default."""
        provider = EnvProvider()
        result = await provider.get_secret("NOT_SET", default="default")

        assert result == "default"

    @pytest.mark.asyncio
    async def test_env_set_secret(self):
        """Test setting secret in environment."""
        provider = EnvProvider()
        await provider.set_secret("TEMP_SECRET", "temp_value")

        assert os.environ.get("TEMP_SECRET") == "temp_value"

        # Cleanup
        del os.environ["TEMP_SECRET"]


class TestVaultProvider:
    """Test HashiCorp Vault based secret provider."""

    def test_vault_initialization_missing_config(self):
        """Test Vault provider fails without config."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="VAULT_ADDR and VAULT_TOKEN"):
                VaultProvider()

    @pytest.mark.asyncio
    async def test_vault_get_secret_hvac_not_installed(self):
        """Test Vault provider fails gracefully if hvac not installed."""
        os.environ["VAULT_ADDR"] = "http://vault:8200"
        os.environ["VAULT_TOKEN"] = "test-token"

        try:
            provider = VaultProvider()

            with patch.dict("sys.modules", {"hvac": None}):
                with pytest.raises(ImportError):
                    await provider.get_secret("test_secret")
        finally:
            del os.environ["VAULT_ADDR"]
            del os.environ["VAULT_TOKEN"]


class TestSecretManager:
    """Test unified secret manager."""

    @pytest.mark.asyncio
    async def test_secret_manager_get_from_env_provider(self):
        """Test manager retrieves from env provider."""
        os.environ["SECRETS_PROVIDER"] = "env"
        os.environ["TEST_KEY"] = "test_value"

        try:
            manager = SecretManager()
            result = await manager.get_secret("TEST_KEY")

            assert result == "test_value"
        finally:
            del os.environ["SECRETS_PROVIDER"]
            del os.environ["TEST_KEY"]

    @pytest.mark.asyncio
    async def test_secret_manager_caching(self):
        """Test manager caches secrets."""
        os.environ["SECRETS_PROVIDER"] = "env"
        os.environ["CACHED_KEY"] = "cached_value"

        try:
            manager = SecretManager()

            # First call - from provider
            result1 = await manager.get_secret("CACHED_KEY")
            assert result1 == "cached_value"

            # Modify environment
            os.environ["CACHED_KEY"] = "modified_value"

            # Second call - from cache (returns old value)
            result2 = await manager.get_secret("CACHED_KEY")
            assert result2 == "cached_value"  # Still cached value

        finally:
            del os.environ["SECRETS_PROVIDER"]
            del os.environ["CACHED_KEY"]

    @pytest.mark.asyncio
    async def test_secret_manager_cache_invalidation(self):
        """Test cache invalidation."""
        os.environ["SECRETS_PROVIDER"] = "env"
        os.environ["INVALID_KEY"] = "value1"

        try:
            manager = SecretManager()

            # Cache the secret
            await manager.get_secret("INVALID_KEY")

            # Modify and invalidate
            os.environ["INVALID_KEY"] = "value2"
            manager.invalidate_cache("INVALID_KEY")

            # Should get new value
            result = await manager.get_secret("INVALID_KEY")
            assert result == "value2"

        finally:
            del os.environ["SECRETS_PROVIDER"]
            del os.environ["INVALID_KEY"]

    @pytest.mark.asyncio
    async def test_secret_manager_get_with_default(self):
        """Test manager returns default for missing secret."""
        os.environ["SECRETS_PROVIDER"] = "env"

        try:
            manager = SecretManager()
            result = await manager.get_secret("MISSING_KEY", default="default_val")

            assert result == "default_val"
        finally:
            del os.environ["SECRETS_PROVIDER"]

    @pytest.mark.asyncio
    async def test_get_secret_manager_singleton(self):
        """Test get_secret_manager returns same instance."""
        os.environ["SECRETS_PROVIDER"] = "env"

        try:
            manager1 = await get_secret_manager()
            manager2 = await get_secret_manager()

            assert manager1 is manager2
        finally:
            del os.environ["SECRETS_PROVIDER"]


class TestSecretProviderSwitching:
    """Test switching between different providers."""

    @pytest.mark.asyncio
    async def test_provider_switching(self):
        """Test switching from env to dotenv provider."""
        # Create manager with env provider
        os.environ["SECRETS_PROVIDER"] = "env"
        os.environ["KEY1"] = "env_value"

        try:
            manager1 = SecretManager()
            result1 = await manager1.get_secret("KEY1")
            assert result1 == "env_value"

        finally:
            del os.environ["KEY1"]
            del os.environ["SECRETS_PROVIDER"]

        # Now create with dotenv (patch at SOURCE before creating manager)
        os.environ["SECRETS_PROVIDER"] = "dotenv"

        try:
            with patch("dotenv.dotenv_values") as mock_dotenv:
                mock_dotenv.return_value = {"KEY2": "dotenv_value"}

                # Create manager INSIDE patch context
                manager2 = SecretManager()
                result2 = await manager2.get_secret("KEY2")
                assert result2 == "dotenv_value"

        finally:
            del os.environ["SECRETS_PROVIDER"]
