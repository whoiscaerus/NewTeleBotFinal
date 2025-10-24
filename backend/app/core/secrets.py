"""Secrets management with provider abstraction."""

import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

from backend.app.core.settings import get_settings

logger = logging.getLogger(__name__)


class SecretProvider(ABC):
    """Abstract base class for secret providers."""

    @abstractmethod
    async def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Retrieve a secret by key.
        
        Args:
            key: Secret key/name
            default: Default value if secret not found
        
        Returns:
            str: Secret value or default
        
        Raises:
            ValueError: If secret not found and no default provided
        """
        pass

    @abstractmethod
    async def set_secret(self, key: str, value: str) -> None:
        """Set a secret (for testing or rotation).
        
        Args:
            key: Secret key/name
            value: Secret value
        """
        pass


class DotenvProvider(SecretProvider):
    """Read secrets from .env file via python-dotenv.
    
    Use only for development. Not recommended for production.
    """

    def __init__(self):
        """Initialize dotenv provider."""
        from dotenv import dotenv_values

        self.env_file = ".env"
        self.secrets = dotenv_values(self.env_file)
        logger.warning("Using DotenvProvider - not suitable for production")

    async def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get secret from .env file.
        
        Args:
            key: Environment variable name
            default: Default value if not found
        
        Returns:
            Secret value
        """
        value = self.secrets.get(key, default)
        if value is None:
            raise ValueError(f"Secret not found: {key}")
        return value

    async def set_secret(self, key: str, value: str) -> None:
        """Set secret in memory (not written to file).
        
        Args:
            key: Secret key
            value: Secret value
        """
        self.secrets[key] = value


class EnvProvider(SecretProvider):
    """Read secrets from environment variables.
    
    Suitable for containerized environments where secrets are injected
    via environment variables (K8s secrets, ECS task definitions, etc.).
    """

    def __init__(self):
        """Initialize environment variable provider."""
        logger.info("Using EnvProvider (environment variables)")

    async def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get secret from environment.
        
        Args:
            key: Environment variable name
            default: Default value if not set
        
        Returns:
            Secret value
        
        Raises:
            ValueError: If secret not found and no default provided
        """
        value = os.environ.get(key, default)
        if value is None:
            raise ValueError(f"Secret not found in environment: {key}")
        return value

    async def set_secret(self, key: str, value: str) -> None:
        """Set secret in environment.
        
        Args:
            key: Environment variable name
            value: Secret value
        """
        os.environ[key] = value


class VaultProvider(SecretProvider):
    """Read secrets from HashiCorp Vault.
    
    For production use with secret rotation and audit logging.
    Requires VAULT_ADDR, VAULT_TOKEN environment variables.
    """

    def __init__(self):
        """Initialize Vault provider."""
        self.vault_addr = os.environ.get("VAULT_ADDR")
        self.vault_token = os.environ.get("VAULT_TOKEN")
        self.vault_path = os.environ.get("VAULT_PATH", "secret/data")

        if not self.vault_addr or not self.vault_token:
            raise ValueError("VAULT_ADDR and VAULT_TOKEN required for VaultProvider")

        logger.info(f"Using VaultProvider at {self.vault_addr}")

    async def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get secret from Vault.
        
        Args:
            key: Secret key in format 'secret_name' or 'path/secret_name'
            default: Default value if not found
        
        Returns:
            Secret value
        
        Raises:
            ValueError: If secret not found and no default provided
        """
        try:
            import hvac

            client = hvac.Client(url=self.vault_addr, token=self.vault_token)

            # Build secret path
            path = f"{self.vault_path}/{key}"

            # Read from Vault
            response = client.secrets.kv.v2.read_secret_version(path=key)
            value = response["data"]["data"].get(key)

            if value is None and default is None:
                raise ValueError(f"Secret not found in Vault: {key}")

            return value or default

        except ImportError:
            logger.error("hvac library not installed - install with: pip install hvac")
            raise
        except Exception as e:
            logger.error(f"Failed to retrieve secret from Vault: {e}")
            if default is not None:
                logger.warning(f"Using default value for secret: {key}")
                return default
            raise ValueError(f"Secret retrieval failed: {key}") from e

    async def set_secret(self, key: str, value: str) -> None:
        """Set secret in Vault.
        
        Args:
            key: Secret key
            value: Secret value
        """
        try:
            import hvac

            client = hvac.Client(url=self.vault_addr, token=self.vault_token)
            client.secrets.kv.v2.create_or_update_secret(
                path=key,
                secret_dict={key: value},
            )
            logger.info(f"Secret updated in Vault: {key}")

        except Exception as e:
            logger.error(f"Failed to set secret in Vault: {e}")
            raise


class SecretManager:
    """Unified secret management interface.
    
    Routes to appropriate provider based on configuration.
    Caches secrets in memory with optional TTL.
    
    Example:
        manager = SecretManager()
        jwt_key = await manager.get_secret("JWT_SECRET_KEY")
        db_password = await manager.get_secret("DB_PASSWORD")
    """

    def __init__(self):
        """Initialize secret manager with configured provider."""
        self.provider = self._get_provider()
        self.cache: dict[str, tuple[str, float]] = {}  # {key: (value, expiry_time)}
        self.cache_ttl = 3600  # 1 hour default

    def _get_provider(self) -> SecretProvider:
        """Get configured secret provider.
        
        Returns:
            SecretProvider: Initialized provider instance
        
        Raises:
            ValueError: If invalid provider or missing config
        """
        settings = get_settings()
        provider_name = os.environ.get("SECRETS_PROVIDER", "dotenv").lower()

        logger.info(f"Loading SecretProvider: {provider_name}")

        if provider_name == "dotenv":
            return DotenvProvider()
        elif provider_name == "env":
            return EnvProvider()
        elif provider_name == "vault":
            return VaultProvider()
        else:
            raise ValueError(
                f"Unknown SECRETS_PROVIDER: {provider_name}. "
                "Must be: dotenv, env, or vault"
            )

    async def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get secret, checking cache first.
        
        Args:
            key: Secret key
            default: Default value if not found
        
        Returns:
            Secret value
        
        Raises:
            ValueError: If secret not found and no default provided
        """
        # Check cache
        if key in self.cache:
            value, expiry = self.cache[key]
            import time

            if time.time() < expiry:
                logger.debug(f"Cache hit for secret: {key}")
                return value
            else:
                # Expired
                del self.cache[key]

        # Fetch from provider
        logger.debug(f"Fetching secret from provider: {key}")
        value = await self.provider.get_secret(key, default)

        # Cache result
        import time

        self.cache[key] = (value, time.time() + self.cache_ttl)

        return value

    async def set_secret(self, key: str, value: str) -> None:
        """Set secret and invalidate cache.
        
        Args:
            key: Secret key
            value: Secret value
        """
        await self.provider.set_secret(key, value)
        # Invalidate cache
        if key in self.cache:
            del self.cache[key]

    def invalidate_cache(self, key: Optional[str] = None) -> None:
        """Invalidate cache for specific key or all keys.
        
        Args:
            key: Secret key to invalidate, or None to clear all
        """
        if key:
            self.cache.pop(key, None)
            logger.info(f"Cache invalidated for secret: {key}")
        else:
            self.cache.clear()
            logger.info("All secret cache invalidated")


# Global secret manager instance
_manager: Optional[SecretManager] = None


async def get_secret_manager() -> SecretManager:
    """Get or initialize global secret manager.
    
    Returns:
        SecretManager: Initialized manager instance
    """
    global _manager
    if _manager is None:
        _manager = SecretManager()
    return _manager
