"""Async HTTP client for posting HMAC-signed signals to server."""

import json
import logging
import uuid
from datetime import datetime, UTC
from typing import Any, Optional

import httpx

from backend.app.strategy.fib_rsi.schema import SignalCandidate
from backend.app.trading.outbound.config import OutboundConfig
from backend.app.trading.outbound.exceptions import OutboundClientError
from backend.app.trading.outbound.hmac import build_signature
from backend.app.trading.outbound.responses import SignalIngestResponse


class HmacClient:
    """Async HTTP client for posting HMAC-signed signals to server.

    Sends trading signals to the server's `/api/v1/signals/ingest` endpoint
    with HMAC-SHA256 authentication and comprehensive error handling.

    Attributes:
        config: Configuration containing credentials and server URL
        logger: Logger instance for structured logging
        _session: Async httpx.AsyncClient (created on context entry)

    Example:
        >>> async with HmacClient(config, logger) as client:
        ...     signal = SignalCandidate(...)
        ...     response = await client.post_signal(signal)
        ...     print(f"Server signal ID: {response.signal_id}")

    Example (standalone usage):
        >>> client = HmacClient(config, logger)
        >>> await client._ensure_session()
        >>> try:
        ...     response = await client.post_signal(signal)
        ... finally:
        ...     await client.close()
    """

    def __init__(self, config: OutboundConfig, logger: logging.Logger) -> None:
        """Initialize HMAC client.

        Args:
            config: OutboundConfig with credentials and server URL
            logger: Logger instance for structured logging

        Raises:
            ValueError: If config is invalid

        Example:
            >>> config = OutboundConfig.from_env()
            >>> logger = logging.getLogger("outbound")
            >>> client = HmacClient(config, logger)
        """
        self.config = config
        self.logger = logger
        self._session: Optional[httpx.AsyncClient] = None

        # Validate config on initialization
        self.config.validate()

    async def __aenter__(self) -> "HmacClient":
        """Context manager entry - create HTTP session."""
        await self._ensure_session()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Context manager exit - close HTTP session."""
        await self.close()

    async def _ensure_session(self) -> None:
        """Ensure HTTP session is initialized.

        Creates an async httpx.AsyncClient if not already created.

        Example:
            >>> await client._ensure_session()
            >>> client._session is not None
            True
        """
        if self._session is None:
            self._session = httpx.AsyncClient(
                timeout=self.config.timeout_seconds,
                limits=httpx.Limits(
                    max_connections=10,
                    max_keepalive_connections=10,
                ),
            )

    async def close(self) -> None:
        """Close HTTP session gracefully.

        Example:
            >>> await client.close()
        """
        if self._session is not None:
            await self._session.aclose()
            self._session = None

    async def post_signal(
        self,
        signal: SignalCandidate,
        idempotency_key: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> SignalIngestResponse:
        """Post a signal to the server with HMAC authentication.

        Serializes the signal to JSON, generates an HMAC-SHA256 signature,
        POSTs to the server, and handles the response.

        Args:
            signal: SignalCandidate object to send
            idempotency_key: UUID for idempotent retries (generated if None)
            timeout: Request timeout in seconds (overrides config)

        Returns:
            SignalIngestResponse: Server response with signal ID and status

        Raises:
            OutboundClientError: If validation, network, or HTTP error occurs
            TimeoutError: If request timeout exceeded

        Example:
            >>> signal = SignalCandidate(
            ...     instrument="GOLD",
            ...     side="buy",
            ...     entry_price=1950.50,
            ...     stop_loss=1945.00,
            ...     take_profit=1960.00,
            ...     risk_percent=0.02
            ... )
            >>> async with HmacClient(config, logger) as client:
            ...     response = await client.post_signal(signal)
            ...     if response.status == "pending_approval":
            ...         print(f"Signal received: {response.signal_id}")
        """
        await self._ensure_session()

        # Validate signal
        self._validate_signal(signal)

        # Generate idempotency key if not provided
        if not idempotency_key:
            idempotency_key = str(uuid.uuid4())

        # Serialize signal to JSON (canonical order)
        request_body = self._serialize_signal(signal)
        request_body_bytes = json.dumps(request_body, separators=(",", ":")).encode(
            "utf-8"
        )

        # Validate body size
        if len(request_body_bytes) > self.config.max_body_size:
            error_msg = (
                f"Signal body too large: {len(request_body_bytes)} bytes "
                f"(max {self.config.max_body_size})"
            )
            self.logger.error(error_msg)
            raise OutboundClientError(error_msg)

        # Generate timestamp (RFC3339)
        timestamp = _get_rfc3339_timestamp()

        # Generate HMAC signature
        signature = build_signature(
            secret=self.config.producer_secret.encode("utf-8"),
            body=request_body_bytes,
            timestamp=timestamp,
            producer_id=self.config.producer_id,
        )

        # Build headers
        headers = {
            "Content-Type": "application/json",
            "X-Producer-Id": self.config.producer_id,
            "X-Timestamp": timestamp,
            "X-Signature": signature,
            "X-Idempotency-Key": idempotency_key,
            "User-Agent": "TeleBot/1.0 (MT5 Signal Client)",
        }

        # Build endpoint URL
        endpoint_url = f"{self.config.server_base_url}/api/v1/signals/ingest"

        # Log request (redact signature for brevity)
        self.logger.info(
            "Posting signal to server",
            extra={
                "producer_id": self.config.producer_id,
                "signal_instrument": signal.instrument,
                "signal_side": signal.side,
                "idempotency_key": idempotency_key,
                "endpoint": endpoint_url,
            },
        )

        request_timeout = timeout or self.config.timeout_seconds

        try:
            # POST to server
            response = await self._session.post(
                endpoint_url,
                content=request_body_bytes,
                headers=headers,
                timeout=request_timeout,
            )

            # Log response
            self.logger.info(
                "Signal posted",
                extra={
                    "producer_id": self.config.producer_id,
                    "http_status": response.status_code,
                    "idempotency_key": idempotency_key,
                },
            )

            # Handle response
            if response.status_code == 201:
                # Success
                response_data = response.json()
                server_response = SignalIngestResponse(**response_data)

                self.logger.info(
                    "Signal ingested by server",
                    extra={
                        "producer_id": self.config.producer_id,
                        "server_signal_id": server_response.signal_id,
                        "status": server_response.status,
                    },
                )

                return server_response

            elif 400 <= response.status_code < 500:
                # Client error (4xx)
                error_msg = f"Server rejected signal (HTTP {response.status_code})"

                try:
                    error_data = response.json()
                    error_details = error_data.get("errors", [])
                except Exception:
                    error_details = [response.text]

                self.logger.warning(
                    error_msg,
                    extra={
                        "producer_id": self.config.producer_id,
                        "http_status": response.status_code,
                        "errors": error_details,
                    },
                )

                raise OutboundClientError(
                    error_msg,
                    http_code=response.status_code,
                    details={"errors": error_details},
                )

            else:
                # Server error (5xx) or other
                error_msg = f"Server error (HTTP {response.status_code})"

                self.logger.error(
                    error_msg,
                    extra={
                        "producer_id": self.config.producer_id,
                        "http_status": response.status_code,
                        "response_text": response.text[:500],
                    },
                )

                raise OutboundClientError(
                    error_msg,
                    http_code=response.status_code,
                )

        except httpx.TimeoutException as e:
            error_msg = f"Request timeout after {request_timeout}s"
            self.logger.error(
                error_msg,
                extra={
                    "producer_id": self.config.producer_id,
                    "timeout_seconds": request_timeout,
                },
            )
            raise TimeoutError(error_msg) from e

        except httpx.RequestError as e:
            error_msg = f"Network error: {str(e)}"
            self.logger.error(
                error_msg,
                extra={
                    "producer_id": self.config.producer_id,
                    "error_type": type(e).__name__,
                },
            )
            raise OutboundClientError(error_msg) from e

        except OutboundClientError:
            raise

        except Exception as e:
            error_msg = f"Unexpected error posting signal: {str(e)}"
            self.logger.error(
                error_msg,
                extra={
                    "producer_id": self.config.producer_id,
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
            raise OutboundClientError(error_msg) from e

    def _validate_signal(self, signal: SignalCandidate) -> None:
        """Validate signal before posting.

        Args:
            signal: Signal to validate

        Raises:
            OutboundClientError: If signal is invalid

        Example:
            >>> signal = SignalCandidate(instrument="", side="buy", ...)
            >>> client._validate_signal(signal)  # Raises OutboundClientError
        """
        if not signal.instrument or not signal.instrument.strip():
            raise OutboundClientError("Signal must have non-empty instrument")

        if signal.side not in ("buy", "sell"):
            raise OutboundClientError(
                f"Signal side must be 'buy' or 'sell', got {signal.side!r}"
            )

        if signal.entry_price <= 0:
            raise OutboundClientError(
                f"Signal entry_price must be > 0, got {signal.entry_price}"
            )

        if not (0.0 <= signal.confidence <= 1.0):
            raise OutboundClientError(
                f"Signal confidence must be between 0.0 and 1.0, "
                f"got {signal.confidence}"
            )

    def _serialize_signal(self, signal: SignalCandidate) -> dict[str, Any]:
        """Serialize signal to JSON-compatible dictionary.

        Uses canonical key ordering for HMAC signature consistency.

        Args:
            signal: Signal to serialize

        Returns:
            dict: JSON-serializable dictionary

        Example:
            >>> signal = SignalCandidate(
            ...     instrument="GOLD",
            ...     side="buy",
            ...     entry_price=1950.50
            ... )
            >>> data = client._serialize_signal(signal)
            >>> list(data.keys())
            ['comment', 'entry_price', 'instrument', ...]
        """
        body = {
            "confidence": float(signal.confidence),
            "entry_price": float(signal.entry_price),
            "instrument": signal.instrument,
            "payload": signal.payload or {},
            "reason": signal.reason,
            "side": signal.side,
            "stop_loss": float(signal.stop_loss),
            "take_profit": float(signal.take_profit),
            "timestamp": signal.timestamp.isoformat() if signal.timestamp else None,
            "version": signal.version,
        }

        # Return with keys sorted for canonical order
        return dict(sorted(body.items()))

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"HmacClient(producer_id={self.config.producer_id!r}, "
            f"server_base_url={self.config.server_base_url!r}, "
            f"enabled={self.config.enabled})"
        )


def _get_rfc3339_timestamp() -> str:
    """Get current timestamp in RFC3339 format.

    Returns:
        str: Current UTC timestamp in RFC3339 format

    Example:
        >>> timestamp = _get_rfc3339_timestamp()
        >>> len(timestamp) > 0
        True
        >>> "T" in timestamp and "Z" in timestamp
        True
    """
    now = datetime.now(tz=UTC)
    return now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
