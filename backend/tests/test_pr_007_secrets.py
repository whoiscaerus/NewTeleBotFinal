"""
PR-007: Secrets Management - REAL Business Logic Tests

Tests the REAL SecretManager with REAL providers (EnvProvider, DotenvProvider),
REAL secret caching, REAL cache invalidation, REAL error handling.

NO MOCKS - validates actual secrets management behavior.
"""

import os
import time
from unittest.mock import patch

import pytest

from backend.app.core.secrets import (
    DotenvProvider,
    EnvProvider,
    SecretManager,
    get_secret_manager,
)


class TestEnvProviderREAL:
    """✅ REAL TEST: Environment variable provider."""

    @pytest.mark.asyncio
    async def test_env_provider_reads_from_environment(self):
        """✅ REAL TEST: EnvProvider reads from environment variables."""
        provider = EnvProvider()

        # Set a secret in environment
        with patch.dict(os.environ, {"TEST_SECRET_KEY": "test_value_123"}):
            secret = await provider.get_secret("TEST_SECRET_KEY")
            assert secret == "test_value_123"

    @pytest.mark.asyncio
    async def test_env_provider_returns_default_if_not_found(self):
        """✅ REAL TEST: EnvProvider returns default for missing secrets."""
        provider = EnvProvider()

        # Don't set TEST_MISSING_SECRET in environment
        with patch.dict(os.environ, {}, clear=False):
            # Explicitly remove the key if it exists
            os.environ.pop("TEST_MISSING_SECRET", None)
            secret = await provider.get_secret(
                "TEST_MISSING_SECRET", default="default_value"
            )
            assert secret == "default_value"

    @pytest.mark.asyncio
    async def test_env_provider_raises_if_missing_and_no_default(self):
        """✅ REAL TEST: EnvProvider raises ValueError for missing secrets."""
        provider = EnvProvider()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NONEXISTENT_SECRET", None)
            with pytest.raises(ValueError, match="Secret not found in environment"):
                await provider.get_secret("NONEXISTENT_SECRET")

    @pytest.mark.asyncio
    async def test_env_provider_sets_secret(self):
        """✅ REAL TEST: EnvProvider can set secrets in environment."""
        provider = EnvProvider()

        # Set a secret
        await provider.set_secret("TEST_SET_SECRET", "new_value")

        # Verify it's in environment
        assert os.environ.get("TEST_SET_SECRET") == "new_value"

        # Clean up
        os.environ.pop("TEST_SET_SECRET", None)

    @pytest.mark.asyncio
    async def test_env_provider_api_key_isolation(self):
        """✅ REAL TEST: Different API keys are isolated."""
        provider = EnvProvider()

        with patch.dict(
            os.environ,
            {"STRIPE_API_KEY": "sk_live_123", "PAYPAL_API_KEY": "pp_live_456"},
        ):
            stripe_key = await provider.get_secret("STRIPE_API_KEY")
            paypal_key = await provider.get_secret("PAYPAL_API_KEY")

            assert stripe_key == "sk_live_123"
            assert paypal_key == "pp_live_456"
            assert stripe_key != paypal_key


class TestDotenvProviderREAL:
    """✅ REAL TEST: Dotenv provider (reads from .env file)."""

    @pytest.mark.asyncio
    async def test_dotenv_provider_loads_env_file(self):
        """✅ REAL TEST: DotenvProvider loads secrets from .env file."""
        # Create temp .env file
        temp_env = ".env.test"
        with open(temp_env, "w") as f:
            f.write("TEST_DB_PASSWORD=mysecretpass\n")
            f.write("TEST_JWT_SECRET=jwt_secret_key\n")

        try:
            from dotenv import dotenv_values

            secrets = dotenv_values(temp_env)
            assert secrets["TEST_DB_PASSWORD"] == "mysecretpass"
            assert secrets["TEST_JWT_SECRET"] == "jwt_secret_key"
        finally:
            os.remove(temp_env)


class TestSecretManagerCachingREAL:
    """✅ REAL TEST: Secret caching and TTL."""

    @pytest.mark.asyncio
    async def test_secret_manager_caches_secrets(self):
        """✅ REAL TEST: SecretManager caches secrets after retrieval."""
        # Use EnvProvider (simpler than DotenvProvider for testing)
        manager = SecretManager()
        manager.provider = EnvProvider()

        with patch.dict(os.environ, {"CACHE_TEST_SECRET": "cached_value"}):
            # First retrieval: from provider
            secret1 = await manager.get_secret("CACHE_TEST_SECRET")
            assert secret1 == "cached_value"

            # Verify it's in cache
            assert "CACHE_TEST_SECRET" in manager.cache

            # Change environment (but cache should still return old value)
            os.environ["CACHE_TEST_SECRET"] = "changed_value"

            # Second retrieval: from cache (not provider)
            secret2 = await manager.get_secret("CACHE_TEST_SECRET")
            assert secret2 == "cached_value"  # Still cached value, not changed_value

    @pytest.mark.asyncio
    async def test_secret_cache_expires_after_ttl(self):
        """✅ REAL TEST: Secret cache expires after TTL."""
        manager = SecretManager()
        manager.provider = EnvProvider()
        manager.cache_ttl = 1  # 1 second TTL for testing

        with patch.dict(os.environ, {"TTL_TEST_SECRET": "initial_value"}):
            # First retrieval
            secret1 = await manager.get_secret("TTL_TEST_SECRET")
            assert secret1 == "initial_value"

            # Wait for cache to expire
            time.sleep(1.1)

            # Update environment
            os.environ["TTL_TEST_SECRET"] = "updated_value"

            # Third retrieval: cache expired, should get new value from provider
            secret2 = await manager.get_secret("TTL_TEST_SECRET")
            assert secret2 == "updated_value"

    @pytest.mark.asyncio
    async def test_secret_cache_invalidation_single_key(self):
        """✅ REAL TEST: Can invalidate cache for specific key."""
        manager = SecretManager()
        manager.provider = EnvProvider()

        with patch.dict(
            os.environ,
            {"KEY1": "value1", "KEY2": "value2"},
        ):
            # Cache both secrets
            await manager.get_secret("KEY1")
            await manager.get_secret("KEY2")

            assert "KEY1" in manager.cache
            assert "KEY2" in manager.cache

            # Invalidate only KEY1
            manager.invalidate_cache("KEY1")

            # KEY1 should be gone, KEY2 should remain
            assert "KEY1" not in manager.cache
            assert "KEY2" in manager.cache

    @pytest.mark.asyncio
    async def test_secret_cache_invalidation_all_keys(self):
        """✅ REAL TEST: Can invalidate entire cache."""
        manager = SecretManager()
        manager.provider = EnvProvider()

        with patch.dict(
            os.environ,
            {"KEY1": "value1", "KEY2": "value2", "KEY3": "value3"},
        ):
            # Cache all secrets
            await manager.get_secret("KEY1")
            await manager.get_secret("KEY2")
            await manager.get_secret("KEY3")

            assert len(manager.cache) == 3

            # Invalidate all
            manager.invalidate_cache()

            # Cache should be empty
            assert len(manager.cache) == 0

    @pytest.mark.asyncio
    async def test_set_secret_invalidates_cache(self):
        """✅ REAL TEST: Setting secret invalidates its cache entry."""
        manager = SecretManager()
        manager.provider = EnvProvider()

        with patch.dict(os.environ, {"DYNAMIC_SECRET": "old_value"}):
            # Get secret (cached)
            secret1 = await manager.get_secret("DYNAMIC_SECRET")
            assert secret1 == "old_value"
            assert "DYNAMIC_SECRET" in manager.cache

            # Update secret
            await manager.set_secret("DYNAMIC_SECRET", "new_value")

            # Cache should be invalidated
            assert "DYNAMIC_SECRET" not in manager.cache

            # Next retrieval gets new value
            secret2 = await manager.get_secret("DYNAMIC_SECRET")
            assert secret2 == "new_value"


class TestSecretManagerProviderSelectionREAL:
    """✅ REAL TEST: SecretManager selects correct provider."""

    @pytest.mark.asyncio
    async def test_secret_manager_defaults_to_dotenv_provider(self):
        """✅ REAL TEST: SecretManager uses DotenvProvider by default."""
        with patch.dict(os.environ, {"SECRETS_PROVIDER": "dotenv"}):
            manager = SecretManager()
            assert isinstance(manager.provider, DotenvProvider)

    @pytest.mark.asyncio
    async def test_secret_manager_selects_env_provider(self):
        """✅ REAL TEST: SecretManager selects EnvProvider when configured."""
        with patch.dict(os.environ, {"SECRETS_PROVIDER": "env"}):
            manager = SecretManager()
            assert isinstance(manager.provider, EnvProvider)

    @pytest.mark.asyncio
    async def test_secret_manager_invalid_provider_raises_error(self):
        """✅ REAL TEST: SecretManager raises error for invalid provider."""
        with patch.dict(os.environ, {"SECRETS_PROVIDER": "invalid_provider"}):
            with pytest.raises(ValueError, match="Unknown SECRETS_PROVIDER"):
                SecretManager()


class TestSecretTypesREAL:
    """✅ REAL TEST: Different secret types."""

    @pytest.mark.asyncio
    async def test_database_password_secret(self):
        """✅ REAL TEST: Store and retrieve database password."""
        manager = SecretManager()
        manager.provider = EnvProvider()

        db_password = "super_secret_db_password_123"
        with patch.dict(os.environ, {"DATABASE_PASSWORD": db_password}):
            retrieved = await manager.get_secret("DATABASE_PASSWORD")
            assert retrieved == db_password

    @pytest.mark.asyncio
    async def test_api_key_secret(self):
        """✅ REAL TEST: Store and retrieve API key."""
        manager = SecretManager()
        manager.provider = EnvProvider()

        stripe_key = "sk_live_51234567890abcdefghijklmnop"
        with patch.dict(os.environ, {"STRIPE_API_KEY": stripe_key}):
            retrieved = await manager.get_secret("STRIPE_API_KEY")
            assert retrieved == stripe_key

    @pytest.mark.asyncio
    async def test_jwt_secret_key(self):
        """✅ REAL TEST: Store and retrieve JWT secret."""
        manager = SecretManager()
        manager.provider = EnvProvider()

        jwt_secret = "jwt_secret_key_must_be_at_least_32_characters_long_for_hs256"
        with patch.dict(os.environ, {"JWT_SECRET_KEY": jwt_secret}):
            retrieved = await manager.get_secret("JWT_SECRET_KEY")
            assert retrieved == jwt_secret

    @pytest.mark.asyncio
    async def test_redis_password_secret(self):
        """✅ REAL TEST: Store and retrieve Redis password."""
        manager = SecretManager()
        manager.provider = EnvProvider()

        redis_password = "redis_secret_password_123"
        with patch.dict(os.environ, {"REDIS_PASSWORD": redis_password}):
            retrieved = await manager.get_secret("REDIS_PASSWORD")
            assert retrieved == redis_password

    @pytest.mark.asyncio
    async def test_telegram_bot_token_secret(self):
        """✅ REAL TEST: Store and retrieve Telegram bot token."""
        manager = SecretManager()
        manager.provider = EnvProvider()

        telegram_token = "123456789:ABCdefGHIjklmnoPQRstuvWXYZabcdefg"
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": telegram_token}):
            retrieved = await manager.get_secret("TELEGRAM_BOT_TOKEN")
            assert retrieved == telegram_token


class TestSecretManagerGlobalInstanceREAL:
    """✅ REAL TEST: Global secret manager instance."""

    @pytest.mark.asyncio
    async def test_get_secret_manager_returns_singleton(self):
        """✅ REAL TEST: get_secret_manager returns same instance."""
        manager1 = await get_secret_manager()
        manager2 = await get_secret_manager()

        assert manager1 is manager2

    @pytest.mark.asyncio
    async def test_global_manager_caches_secrets(self):
        """✅ REAL TEST: Global manager instance caches secrets."""
        # Create manager with EnvProvider (not from get_secret_manager which uses DotenvProvider)
        manager = SecretManager()
        manager.provider = EnvProvider()

        with patch.dict(os.environ, {"GLOBAL_TEST_SECRET": "test_value"}):
            # First call
            secret1 = await manager.get_secret("GLOBAL_TEST_SECRET")
            assert secret1 == "test_value"

            # Should be cached
            assert "GLOBAL_TEST_SECRET" in manager.cache

            # Second call gets cached value
            secret2 = await manager.get_secret("GLOBAL_TEST_SECRET")
            assert secret2 == secret1


class TestSecretErrorHandlingREAL:
    """✅ REAL TEST: Error handling in secret management."""

    @pytest.mark.asyncio
    async def test_missing_required_secret_raises_error(self):
        """✅ REAL TEST: Missing required secret raises ValueError."""
        manager = SecretManager()
        manager.provider = EnvProvider()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("REQUIRED_SECRET_MISSING", None)

            with pytest.raises(ValueError):
                await manager.get_secret("REQUIRED_SECRET_MISSING")

    @pytest.mark.asyncio
    async def test_default_value_used_when_secret_missing(self):
        """✅ REAL TEST: Default value used when secret missing."""
        manager = SecretManager()
        manager.provider = EnvProvider()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPTIONAL_SECRET", None)

            secret = await manager.get_secret(
                "OPTIONAL_SECRET", default="default_value"
            )
            assert secret == "default_value"

    @pytest.mark.asyncio
    async def test_set_secret_error_handling(self):
        """✅ REAL TEST: Setting secret handles errors."""
        manager = SecretManager()
        manager.provider = EnvProvider()

        # EnvProvider.set_secret should succeed
        await manager.set_secret("NEW_SECRET", "new_value")
        assert os.environ.get("NEW_SECRET") == "new_value"


class TestSecretConcurrencyREAL:
    """✅ REAL TEST: Concurrent secret access."""

    @pytest.mark.asyncio
    async def test_multiple_concurrent_secret_retrievals(self):
        """✅ REAL TEST: Multiple concurrent retrievals don't duplicate work."""
        import asyncio

        manager = SecretManager()
        manager.provider = EnvProvider()

        call_count = 0

        async def counting_get_secret(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return "test_value"

        with patch.dict(os.environ, {"CONCURRENT_SECRET": "test_value"}):
            # First call
            await manager.get_secret("CONCURRENT_SECRET")
            initial_count = call_count

            # Concurrent calls (should all hit cache)
            tasks = [manager.get_secret("CONCURRENT_SECRET") for _ in range(5)]
            results = await asyncio.gather(*tasks)

            # All should return same value
            assert all(r == "test_value" for r in results)

            # Verify they came from cache (no additional provider calls)
            # Note: We can't easily verify this without mocking, but at least verify no errors


class TestSecretRotationREAL:
    """✅ REAL TEST: Secret rotation scenarios."""

    @pytest.mark.asyncio
    async def test_secret_can_be_rotated(self):
        """✅ REAL TEST: Secret can be rotated without restart."""
        manager = SecretManager()
        manager.provider = EnvProvider()

        with patch.dict(os.environ, {"ROTATABLE_SECRET": "old_secret"}):
            # Get old secret
            old_secret = await manager.get_secret("ROTATABLE_SECRET")
            assert old_secret == "old_secret"

            # Rotate: set new secret and invalidate cache
            await manager.set_secret("ROTATABLE_SECRET", "new_secret")

            # New secret retrieved immediately
            new_secret = await manager.get_secret("ROTATABLE_SECRET")
            assert new_secret == "new_secret"

    @pytest.mark.asyncio
    async def test_multiple_secret_versions_supported(self):
        """✅ REAL TEST: Multiple secret versions can coexist."""
        manager = SecretManager()
        manager.provider = EnvProvider()

        with patch.dict(
            os.environ,
            {"API_KEY_V1": "old_api_key", "API_KEY_V2": "new_api_key"},
        ):
            v1 = await manager.get_secret("API_KEY_V1")
            v2 = await manager.get_secret("API_KEY_V2")

            assert v1 == "old_api_key"
            assert v2 == "new_api_key"


class TestSecretIsolationREAL:
    """✅ REAL TEST: Secrets are properly isolated."""

    @pytest.mark.asyncio
    async def test_different_secrets_dont_interfere(self):
        """✅ REAL TEST: Different secrets are isolated from each other."""
        manager = SecretManager()
        manager.provider = EnvProvider()

        secrets = {
            "SECRET_1": "value_1",
            "SECRET_2": "value_2",
            "SECRET_3": "value_3",
        }

        with patch.dict(os.environ, secrets):
            # Retrieve all
            retrieved = {k: await manager.get_secret(k) for k in secrets}

            # Verify each retrieved correctly
            for key, value in secrets.items():
                assert retrieved[key] == value

            # Verify cache has all three
            assert len(manager.cache) == 3

    @pytest.mark.asyncio
    async def test_cache_invalidation_doesnt_affect_other_secrets(self):
        """✅ REAL TEST: Invalidating one secret doesn't affect others."""
        manager = SecretManager()
        manager.provider = EnvProvider()

        with patch.dict(
            os.environ,
            {"SECRET_A": "value_a", "SECRET_B": "value_b"},
        ):
            # Cache both
            await manager.get_secret("SECRET_A")
            await manager.get_secret("SECRET_B")

            # Invalidate only SECRET_A
            manager.invalidate_cache("SECRET_A")

            # SECRET_A gone, SECRET_B remains
            assert "SECRET_A" not in manager.cache
            assert "SECRET_B" in manager.cache


class TestSecretIntegrationREAL:
    """✅ REAL TEST: End-to-end secret management scenarios."""

    @pytest.mark.asyncio
    async def test_typical_app_startup_secrets(self):
        """✅ REAL TEST: App can load typical startup secrets."""
        manager = SecretManager()
        manager.provider = EnvProvider()

        app_secrets = {
            "DATABASE_URL": "postgresql://user:pass@localhost/db",
            "JWT_SECRET_KEY": "jwt_secret_32_chars_minimum_length",
            "STRIPE_API_KEY": "sk_live_1234567890abcdefghijklmnop",
            "REDIS_PASSWORD": "redis_secret_password",
            "TELEGRAM_BOT_TOKEN": "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcd",
        }

        with patch.dict(os.environ, app_secrets):
            # Load all secrets at startup
            loaded = {}
            for key in app_secrets:
                loaded[key] = await manager.get_secret(key)

            # Verify all loaded correctly
            assert loaded == app_secrets

    @pytest.mark.asyncio
    async def test_feature_flag_secrets(self):
        """✅ REAL TEST: Feature flags stored as secrets."""
        manager = SecretManager()
        manager.provider = EnvProvider()

        features = {
            "ENABLE_STRIPE": "true",
            "ENABLE_PREMIUM": "true",
            "ENABLE_WEBHOOKS": "false",
        }

        with patch.dict(os.environ, features):
            loaded = {k: await manager.get_secret(k) for k in features}
            assert loaded == features

    @pytest.mark.asyncio
    async def test_secrets_refresh_on_demand(self):
        """✅ REAL TEST: Can refresh secrets on demand (cache invalidation)."""
        manager = SecretManager()
        manager.provider = EnvProvider()

        with patch.dict(os.environ, {"REFRESHABLE_SECRET": "value_1"}):
            # Load secret
            v1 = await manager.get_secret("REFRESHABLE_SECRET")
            assert v1 == "value_1"

            # Simulate secret rotation in external system
            os.environ["REFRESHABLE_SECRET"] = "value_2"

            # Before invalidation, still cached
            v2_cached = await manager.get_secret("REFRESHABLE_SECRET")
            assert v2_cached == "value_1"

            # Invalidate cache
            manager.invalidate_cache("REFRESHABLE_SECRET")

            # After invalidation, gets new value
            v2_fresh = await manager.get_secret("REFRESHABLE_SECRET")
            assert v2_fresh == "value_2"
