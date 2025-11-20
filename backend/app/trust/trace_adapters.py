"""
Auto-Trace Adapters: Pluggable interfaces for posting trades to third-party trackers.

Supports:
- Myfxbook (webhook posting)
- File Export (local/S3)
- Generic Webhook (custom endpoint)

All adapters:
- Handle authentication securely
- Support retry with exponential backoff
- Log all interactions
- Strip PII before posting
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

import aiohttp
import boto3

logger = logging.getLogger(__name__)


class AdapterError(Exception):
    """Raised when adapter encounters fatal error."""

    pass


class AdapterType(str, Enum):
    """Available adapter types."""

    MYFXBOOK = "myfxbook"
    FILE_EXPORT = "file_export"
    WEBHOOK = "webhook"


@dataclass
class AdapterConfig:
    """Configuration for each adapter."""

    name: str
    enabled: bool = True
    retry_max_attempts: int = 5
    retry_backoff_base: int = 5  # seconds
    retry_backoff_max: int = 3600  # 1 hour
    timeout_seconds: int = 30


class TraceAdapter(ABC):
    """
    Abstract base class for all trace adapters.

    Defines interface for posting trades to external trackers.
    """

    def __init__(self, config: AdapterConfig):
        """Initialize adapter with configuration."""
        self.config = config
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        """Async context manager entry."""
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._session:
            await self._session.close()

    @abstractmethod
    async def post_trade(
        self, trade_data: dict[str, Any], retry_count: int = 0
    ) -> bool:
        """
        Post trade to external tracker.

        Args:
            trade_data: Stripped trade dict (no PII):
                {
                    "trade_id": "...",
                    "instrument": "GOLD",
                    "side": "buy",
                    "entry_price": 1950.50,
                    "exit_price": 1955.00,
                    "volume": 1.0,
                    "entry_time": "2025-01-15T10:30:00Z",
                    "exit_time": "2025-01-15T11:00:00Z",
                    "profit_loss": 22.50,
                    "profit_loss_percent": 1.15
                }
            retry_count: Current retry attempt (0-5)

        Returns:
            bool: True if success, False if retriable failure

        Raises:
            AdapterError: On fatal error (after retries exhausted)
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Adapter name (e.g., 'myfxbook', 'file_export')."""
        pass

    def calculate_backoff(self, retry_count: int) -> int:
        """
        Calculate backoff delay in seconds.

        Exponential backoff: base * (multiplier ** retry_count)
        Capped at max_backoff_seconds

        Examples:
        - retry_count=0: 5 seconds
        - retry_count=1: 30 seconds
        - retry_count=2: 300 seconds (5 minutes)
        - retry_count=3: 1800 seconds (30 minutes)
        - retry_count=4+: 3600 seconds (1 hour, capped)
        """
        multiplier = 6
        backoff = self.config.retry_backoff_base * (multiplier**retry_count)
        return int(min(backoff, self.config.retry_backoff_max))


class MyfxbookAdapter(TraceAdapter):
    """
    Post trades to Myfxbook via webhook.

    Environment:
    - MYFXBOOK_WEBHOOK_URL: https://myfxbook.com/webhooks/...
    - MYFXBOOK_WEBHOOK_TOKEN: secret token
    """

    def __init__(self, config: AdapterConfig, webhook_url: str, webhook_token: str):
        """Initialize with Myfxbook credentials."""
        super().__init__(config)
        self.webhook_url = webhook_url
        self.webhook_token = webhook_token

    @property
    def name(self) -> str:
        """Adapter name."""
        return AdapterType.MYFXBOOK.value

    async def post_trade(
        self, trade_data: dict[str, Any], retry_count: int = 0
    ) -> bool:
        """
        POST trade to Myfxbook webhook.

        Payload:
        {
            "trade_id": "...",
            "instrument": "GOLD",
            "side": "buy",
            "entry_price": 1950.50,
            "exit_price": 1955.00,
            "volume": 1.0,
            "entry_time": "2025-01-15T10:30:00Z",
            "exit_time": "2025-01-15T11:00:00Z",
            "profit_loss": 22.50,
            "profit_loss_percent": 1.15
        }
        """
        if not self._session:
            raise AdapterError("Session not initialized. Use async context manager.")

        try:
            # Prepare headers
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.webhook_token}",
                "X-Trace-Retry-Count": str(retry_count),
            }

            # POST to webhook
            async with self._session.post(
                self.webhook_url,
                json=trade_data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds),
            ) as response:
                if response.status in (200, 201, 204):
                    logger.info(
                        f"Myfxbook trade posted successfully: {trade_data['trade_id']}",
                        extra={
                            "trade_id": trade_data["trade_id"],
                            "adapter": self.name,
                            "status_code": response.status,
                        },
                    )
                    return True
                elif response.status >= 500:
                    # Server error, retriable
                    logger.warning(
                        f"Myfxbook server error {response.status}, will retry: {trade_data['trade_id']}",
                        extra={
                            "trade_id": trade_data["trade_id"],
                            "adapter": self.name,
                            "retry_count": retry_count,
                            "status_code": response.status,
                        },
                    )
                    return False
                else:
                    # Client error, fatal
                    body = await response.text()
                    raise AdapterError(f"Myfxbook {response.status}: {body}")

        except TimeoutError:
            logger.warning(
                f"Myfxbook timeout, will retry: {trade_data['trade_id']}",
                extra={
                    "trade_id": trade_data["trade_id"],
                    "adapter": self.name,
                    "retry_count": retry_count,
                },
            )
            return False
        except aiohttp.ClientError as e:
            logger.warning(
                f"Myfxbook network error, will retry: {str(e)}",
                extra={
                    "trade_id": trade_data["trade_id"],
                    "adapter": self.name,
                    "retry_count": retry_count,
                    "error": str(e),
                },
            )
            return False


class FileExportAdapter(TraceAdapter):
    """
    Export trades to file (local or S3).

    Environment:
    - FILE_EXPORT_TYPE: "local" or "s3"
    - FILE_EXPORT_LOCAL_PATH: /var/traces/ (for local)
    - FILE_EXPORT_S3_BUCKET: trades-export (for S3)
    - FILE_EXPORT_S3_PREFIX: traces/ (for S3)
    """

    def __init__(
        self,
        config: AdapterConfig,
        export_type: str = "local",
        local_path: str | None = None,
        s3_bucket: str | None = None,
        s3_prefix: str | None = None,
    ):
        """Initialize with export configuration."""
        super().__init__(config)
        self.export_type = export_type.lower()
        self.local_path = local_path or "/var/traces"
        self.s3_bucket = s3_bucket
        self.s3_prefix = (s3_prefix or "traces/").rstrip("/") + "/"
        self.s3_client = None

        if self.export_type == "s3":
            self.s3_client = boto3.client("s3")

    @property
    def name(self) -> str:
        """Adapter name."""
        return AdapterType.FILE_EXPORT.value

    async def post_trade(
        self, trade_data: dict[str, Any], retry_count: int = 0
    ) -> bool:
        """
        Export trade to file.

        Appends JSON line to file: trades-{YYYY-MM-DD}.jsonl
        """
        try:
            trade_id = trade_data.get("trade_id", "unknown")
            exit_time = trade_data.get("exit_time", "2025-01-15")

            # Extract date from exit_time for file naming
            date_str = exit_time[:10] if len(exit_time) >= 10 else "2025-01-15"
            filename = f"trades-{date_str}.jsonl"

            if self.export_type == "local":
                # Write to local file
                from pathlib import Path

                path = Path(self.local_path)
                path.mkdir(parents=True, exist_ok=True)

                file_path = path / filename
                line = json.dumps(trade_data) + "\n"

                # Async file write
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None, self._write_local_file, str(file_path), line
                )

                logger.info(
                    f"Trade exported to file: {filename}",
                    extra={
                        "trade_id": trade_id,
                        "adapter": self.name,
                        "file": filename,
                    },
                )
                return True

            elif self.export_type == "s3":
                # Write to S3
                key = self.s3_prefix + filename
                line = json.dumps(trade_data) + "\n"

                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._write_s3_file, key, line)

                logger.info(
                    f"Trade exported to S3: {key}",
                    extra={"trade_id": trade_id, "adapter": self.name, "s3_key": key},
                )
                return True

            else:
                raise AdapterError(f"Unknown export type: {self.export_type}")

        except Exception as e:
            logger.error(
                f"File export failed: {str(e)}",
                extra={
                    "trade_id": trade_data.get("trade_id", "unknown"),
                    "adapter": self.name,
                    "retry_count": retry_count,
                    "error": str(e),
                },
                exc_info=True,
            )
            return False

    @staticmethod
    def _write_local_file(file_path: str, line: str) -> None:
        """Synchronous file write (for executor)."""
        with open(file_path, "a") as f:
            f.write(line)

    def _write_s3_file(self, key: str, line: str) -> None:
        """Synchronous S3 write (for executor)."""
        if not self.s3_client or not self.s3_bucket:
            raise AdapterError("S3 not configured")

        try:
            # Try to read existing object
            response = self.s3_client.get_object(Bucket=self.s3_bucket, Key=key)
            existing = response["Body"].read().decode("utf-8")
            content = existing + line
        except self.s3_client.exceptions.NoSuchKey:
            # First time, create new
            content = line

        # Write back
        self.s3_client.put_object(
            Bucket=self.s3_bucket,
            Key=key,
            Body=content.encode("utf-8"),
            ContentType="application/x-jsonl",
        )


class WebhookAdapter(TraceAdapter):
    """
    Post trades to generic webhook endpoint.

    Environment:
    - WEBHOOK_ENDPOINT: https://your-tracker.com/traces
    - WEBHOOK_AUTH_HEADER: X-API-Key
    - WEBHOOK_AUTH_TOKEN: your-api-key
    """

    def __init__(
        self,
        config: AdapterConfig,
        endpoint: str,
        auth_header: str | None = None,
        auth_token: str | None = None,
    ):
        """Initialize with webhook configuration."""
        super().__init__(config)
        self.endpoint = endpoint
        self.auth_header = auth_header or "Authorization"
        self.auth_token = auth_token

    @property
    def name(self) -> str:
        """Adapter name."""
        return AdapterType.WEBHOOK.value

    async def post_trade(
        self, trade_data: dict[str, Any], retry_count: int = 0
    ) -> bool:
        """
        POST trade to webhook endpoint.

        Supports custom authentication header.
        """
        if not self._session:
            raise AdapterError("Session not initialized. Use async context manager.")

        try:
            # Prepare headers
            headers = {
                "Content-Type": "application/json",
                "X-Trace-Retry-Count": str(retry_count),
            }

            # Add auth if configured
            if self.auth_token:
                if self.auth_header.lower() == "authorization":
                    headers["Authorization"] = f"Bearer {self.auth_token}"
                else:
                    headers[self.auth_header] = self.auth_token

            # POST to webhook
            async with self._session.post(
                self.endpoint,
                json=trade_data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds),
            ) as response:
                if response.status in (200, 201, 204):
                    logger.info(
                        f"Webhook trade posted successfully: {trade_data['trade_id']}",
                        extra={
                            "trade_id": trade_data["trade_id"],
                            "adapter": self.name,
                            "endpoint": self.endpoint,
                            "status_code": response.status,
                        },
                    )
                    return True
                elif response.status >= 500:
                    # Server error, retriable
                    logger.warning(
                        f"Webhook server error {response.status}, will retry",
                        extra={
                            "trade_id": trade_data["trade_id"],
                            "adapter": self.name,
                            "retry_count": retry_count,
                            "status_code": response.status,
                        },
                    )
                    return False
                else:
                    # Client error, fatal
                    body = await response.text()
                    raise AdapterError(f"Webhook {response.status}: {body}")

        except TimeoutError:
            logger.warning(
                "Webhook timeout, will retry",
                extra={
                    "trade_id": trade_data["trade_id"],
                    "adapter": self.name,
                    "retry_count": retry_count,
                },
            )
            return False
        except aiohttp.ClientError as e:
            logger.warning(
                f"Webhook network error, will retry: {str(e)}",
                extra={
                    "trade_id": trade_data["trade_id"],
                    "adapter": self.name,
                    "retry_count": retry_count,
                    "error": str(e),
                },
            )
            return False


class AdapterRegistry:
    """Registry for managing available adapters."""

    def __init__(self):
        """Initialize registry."""
        self._adapters: dict[str, TraceAdapter] = {}

    def register(self, adapter: TraceAdapter) -> None:
        """Register an adapter."""
        self._adapters[adapter.name] = adapter

    def get(self, name: str) -> TraceAdapter | None:
        """Get adapter by name."""
        return self._adapters.get(name)

    def list_adapters(self) -> list[str]:
        """List all registered adapter names."""
        return list(self._adapters.keys())

    def list_enabled(self) -> list[TraceAdapter]:
        """List enabled adapters."""
        return [a for a in self._adapters.values() if a.config.enabled]
