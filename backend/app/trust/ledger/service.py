"""Ledger service for trade hash computation and submission.

Handles:
- Hash computation from trade data (deterministic, reproducible)
- PII redaction (no quantities, params, user IDs)
- Blockchain submission via adapters
- Proof storage and retrieval
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.trading.store.models import Trade
from backend.app.trust.ledger.adapters import (
    ArbitrumAdapter,
    BlockchainAdapter,
    BlockchainSubmissionError,
    PolygonAdapter,
)

logger = logging.getLogger(__name__)


def compute_trade_hash(trade: Trade) -> str:
    """Compute deterministic SHA256 hash of trade data.

    Only includes public, non-PII fields for verifiability:
    - trade_id
    - symbol
    - strategy
    - timeframe
    - trade_type (BUY/SELL)
    - entry_time (UTC ISO format)
    - exit_time (UTC ISO format)
    - closed_at (UTC ISO format)
    - status

    REDACTED (not included):
    - user_id (PII)
    - volume (position size - private)
    - profit (P&L - private)
    - entry_price, exit_price (execution prices - private)
    - stop_loss, take_profit (params - private)

    Args:
        trade: Trade model instance (must be CLOSED)

    Returns:
        SHA256 hash as hex string

    Raises:
        ValueError: If trade is not CLOSED
    """
    if trade.status != "CLOSED":
        raise ValueError(f"Cannot hash non-closed trade: {trade.status}")

    # Build canonical JSON (sorted keys for determinism)
    hash_data = {
        "trade_id": trade.trade_id,
        "symbol": trade.symbol,
        "strategy": trade.strategy,
        "timeframe": trade.timeframe,
        "trade_type": trade.trade_type,
        "entry_time": trade.entry_time.isoformat() if trade.entry_time else None,
        "exit_time": trade.exit_time.isoformat() if trade.exit_time else None,
        "status": trade.status,
    }

    # Serialize to JSON with sorted keys (deterministic order)
    canonical_json = json.dumps(hash_data, sort_keys=True, separators=(",", ":"))

    # Compute SHA256
    hash_bytes = hashlib.sha256(canonical_json.encode("utf-8")).digest()
    return hash_bytes.hex()


class LedgerService:
    """Service for submitting trade hashes to blockchain ledger.

    Provides opt-in public verifiability for closed trades.
    """

    def __init__(self, db: AsyncSession):
        """Initialize ledger service.

        Args:
            db: Database session for proof storage
        """
        self.db = db
        self.adapters: dict[str, BlockchainAdapter] = {
            "polygon": PolygonAdapter(),  # Stub mode by default
            "arbitrum": ArbitrumAdapter(),  # Stub mode by default
        }

    async def submit_hash(self, trade: Trade, chain: str = "polygon") -> dict[str, Any]:
        """Submit trade hash to blockchain.

        Args:
            trade: Closed trade to submit
            chain: Blockchain to use (polygon, arbitrum)

        Returns:
            Submission result dict with tx_hash, block_number, timestamp, chain

        Raises:
            ValueError: If trade not CLOSED or chain invalid
            BlockchainSubmissionError: If submission fails after retries
        """
        if trade.status != "CLOSED":
            raise ValueError(f"Cannot submit non-closed trade: {trade.status}")

        if chain not in self.adapters:
            raise ValueError(
                f"Unknown chain: {chain}. Valid: {list(self.adapters.keys())}"
            )

        # Compute hash
        trade_hash = compute_trade_hash(trade)

        logger.info(
            f"Submitting trade hash to {chain}",
            extra={
                "trade_id": trade.trade_id,
                "chain": chain,
                "hash": trade_hash[:16],  # Log first 16 chars
            },
        )

        # Submit via adapter (with retry)
        adapter = self.adapters[chain]
        try:
            result = await adapter.submit_with_retry(
                trade_hash, trade.trade_id, trade.exit_time or datetime.utcnow()
            )

            # Store proof in database (if proof table exists)
            # await self._store_proof(trade.trade_id, trade_hash, result)

            return result

        except BlockchainSubmissionError as e:
            logger.error(
                f"Failed to submit trade to {chain}",
                extra={"trade_id": trade.trade_id, "error": str(e)},
            )
            raise

    async def get_proof(self, trade_id: str) -> dict[str, Any] | None:
        """Retrieve blockchain proof for a trade.

        Args:
            trade_id: Trade identifier

        Returns:
            Proof dict with tx_hash, block_number, chain, timestamp, or None if not found
        """
        # TODO: Query proof table
        # result = await self.db.execute(
        #     select(TradeProof).where(TradeProof.trade_id == trade_id)
        # )
        # proof = result.scalar_one_or_none()
        # if proof:
        #     return {
        #         "trade_id": proof.trade_id,
        #         "trade_hash": proof.trade_hash,
        #         "tx_hash": proof.tx_hash,
        #         "block_number": proof.block_number,
        #         "chain": proof.chain,
        #         "timestamp": proof.timestamp.isoformat(),
        #     }

        logger.warning(f"Proof storage not yet implemented (trade_id={trade_id})")
        return None

    async def verify_hash(self, trade: Trade, expected_hash: str) -> bool:
        """Verify that recomputed hash matches expected hash.

        Args:
            trade: Trade to verify
            expected_hash: Hash to compare against

        Returns:
            True if hash matches, False otherwise
        """
        recomputed_hash = compute_trade_hash(trade)
        return recomputed_hash == expected_hash

    # async def _store_proof(
    #     self, trade_id: str, trade_hash: str, submission_result: dict
    # ) -> None:
    #     """Store blockchain proof in database."""
    #     # TODO: Create TradeProof model and insert proof
    #     pass
