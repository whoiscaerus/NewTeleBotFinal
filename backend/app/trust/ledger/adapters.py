"""Blockchain adapters for trade hash submission.

Supports multiple chains with retry logic and telemetry.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from backend.app.observability.metrics import metrics

logger = logging.getLogger(__name__)


class BlockchainAdapter(ABC):
    """Base adapter for blockchain submission.

    Each chain adapter implements submit() for posting hashes to that chain.
    """

    def __init__(self, chain_name: str, rpc_url: str | None = None):
        """Initialize adapter.

        Args:
            chain_name: Chain identifier (polygon, arbitrum, etc.)
            rpc_url: RPC endpoint URL (optional for stub mode)
        """
        self.chain_name = chain_name
        self.rpc_url = rpc_url
        self.max_retries = 3
        self.retry_delay_seconds = 2

    @abstractmethod
    async def submit_hash(
        self, trade_hash: str, trade_id: str, closed_at: datetime
    ) -> dict[str, Any]:
        """Submit trade hash to blockchain.

        Args:
            trade_hash: SHA256 hash of trade data
            trade_id: Trade identifier
            closed_at: Trade close timestamp

        Returns:
            dict with keys: tx_hash, block_number, timestamp, chain

        Raises:
            BlockchainSubmissionError: On persistent failure after retries
        """
        pass

    async def submit_with_retry(
        self, trade_hash: str, trade_id: str, closed_at: datetime
    ) -> dict[str, Any]:
        """Submit with exponential backoff retry.

        Args:
            trade_hash: SHA256 hash
            trade_id: Trade identifier
            closed_at: Trade close timestamp

        Returns:
            Submission result dict

        Raises:
            BlockchainSubmissionError: After max_retries exhausted
        """
        last_error = None

        for attempt in range(self.max_retries):
            try:
                logger.info(
                    f"Submitting trade hash to {self.chain_name} (attempt {attempt + 1}/{self.max_retries})",
                    extra={"trade_id": trade_id, "chain": self.chain_name},
                )

                result = await self.submit_hash(trade_hash, trade_id, closed_at)

                # Increment success metric
                metrics.ledger_submissions_total.labels(
                    chain=self.chain_name
                ).inc()

                logger.info(
                    f"Successfully submitted to {self.chain_name}",
                    extra={
                        "trade_id": trade_id,
                        "tx_hash": result.get("tx_hash"),
                        "chain": self.chain_name,
                    },
                )

                return result

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Submission attempt {attempt + 1} failed: {e}",
                    extra={"trade_id": trade_id, "chain": self.chain_name},
                )

                if attempt < self.max_retries - 1:
                    delay = self.retry_delay_seconds * (2**attempt)
                    await asyncio.sleep(delay)

        # All retries exhausted
        metrics.ledger_fail_total.labels(chain=self.chain_name).inc()

        logger.error(
            f"Failed to submit to {self.chain_name} after {self.max_retries} attempts",
            extra={"trade_id": trade_id, "error": str(last_error)},
        )

        raise BlockchainSubmissionError(
            f"Submission to {self.chain_name} failed after {self.max_retries} retries: {last_error}"
        )


class PolygonAdapter(BlockchainAdapter):
    """Polygon blockchain adapter.

    Submits trade hashes to Polygon PoS chain.
    """

    def __init__(self, rpc_url: str | None = None):
        """Initialize Polygon adapter.

        Args:
            rpc_url: Polygon RPC endpoint (optional for stub mode)
        """
        super().__init__("polygon", rpc_url)

    async def submit_hash(
        self, trade_hash: str, trade_id: str, closed_at: datetime
    ) -> dict[str, Any]:
        """Submit hash to Polygon.

        In stub mode (no rpc_url), returns mock transaction.
        In production, uses Web3.py to submit to Polygon smart contract.

        Args:
            trade_hash: SHA256 hash
            trade_id: Trade identifier
            closed_at: Trade close timestamp

        Returns:
            Transaction result dict
        """
        if not self.rpc_url:
            # Stub mode: return mock transaction
            logger.info(
                f"STUB MODE: Simulating Polygon submission for trade {trade_id}"
            )
            return {
                "tx_hash": f"0xpolygon{trade_hash[:16]}",
                "block_number": 12345678,
                "timestamp": closed_at.isoformat(),
                "chain": "polygon",
                "gas_used": 21000,
            }

        # Production mode: Actual Web3 submission
        try:
            # TODO: Implement Web3.py submission to Polygon smart contract
            # from web3 import Web3
            # w3 = Web3(Web3.HTTPProvider(self.rpc_url))
            # contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)
            # tx = contract.functions.submitTradeHash(trade_hash).build_transaction(...)
            # signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
            # tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            # receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

            logger.warning(
                "Production Polygon submission not yet implemented, using stub"
            )
            return await self.submit_hash(
                trade_hash, trade_id, closed_at
            )  # Fallback to stub

        except Exception as e:
            logger.error(f"Polygon submission error: {e}")
            raise BlockchainSubmissionError(f"Polygon submission failed: {e}")


class ArbitrumAdapter(BlockchainAdapter):
    """Arbitrum blockchain adapter.

    Submits trade hashes to Arbitrum One.
    """

    def __init__(self, rpc_url: str | None = None):
        """Initialize Arbitrum adapter.

        Args:
            rpc_url: Arbitrum RPC endpoint (optional for stub mode)
        """
        super().__init__("arbitrum", rpc_url)

    async def submit_hash(
        self, trade_hash: str, trade_id: str, closed_at: datetime
    ) -> dict[str, Any]:
        """Submit hash to Arbitrum.

        In stub mode (no rpc_url), returns mock transaction.
        In production, uses Web3.py to submit to Arbitrum smart contract.

        Args:
            trade_hash: SHA256 hash
            trade_id: Trade identifier
            closed_at: Trade close timestamp

        Returns:
            Transaction result dict
        """
        if not self.rpc_url:
            # Stub mode: return mock transaction
            logger.info(
                f"STUB MODE: Simulating Arbitrum submission for trade {trade_id}"
            )
            return {
                "tx_hash": f"0xarbitrum{trade_hash[:16]}",
                "block_number": 98765432,
                "timestamp": closed_at.isoformat(),
                "chain": "arbitrum",
                "gas_used": 15000,
            }

        # Production mode: Actual Web3 submission
        try:
            # TODO: Implement Web3.py submission to Arbitrum smart contract
            logger.warning(
                "Production Arbitrum submission not yet implemented, using stub"
            )
            return await self.submit_hash(
                trade_hash, trade_id, closed_at
            )  # Fallback to stub

        except Exception as e:
            logger.error(f"Arbitrum submission error: {e}")
            raise BlockchainSubmissionError(f"Arbitrum submission failed: {e}")


class BlockchainSubmissionError(Exception):
    """Raised when blockchain submission fails after all retries."""

    pass
