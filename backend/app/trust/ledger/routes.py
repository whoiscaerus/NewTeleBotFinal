"""Public API routes for blockchain proof verification.

Provides read-only access to on-chain trade proofs.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import get_db
from backend.app.core.logging import get_logger
from backend.app.trading.store.models import Trade
from backend.app.trust.ledger.service import LedgerService, compute_trade_hash
from sqlalchemy import select

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/public", tags=["public", "ledger"])


class TradeProofResponse(BaseModel):
    """Response schema for trade proof."""

    trade_id: str
    trade_hash: str
    tx_hash: str | None = None
    block_number: int | None = None
    chain: str | None = None
    timestamp: str | None = None
    verifiable_data: dict[str, Any]

    class Config:
        from_attributes = True


@router.get("/proof/{trade_id}", response_model=TradeProofResponse)
async def get_trade_proof(
    trade_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get blockchain proof for a closed trade.

    Returns:
        - trade_id: Trade identifier
        - trade_hash: SHA256 hash of trade data
        - tx_hash: Blockchain transaction hash (if submitted)
        - block_number: Block number (if submitted)
        - chain: Blockchain name (polygon, arbitrum)
        - timestamp: Submission timestamp
        - verifiable_data: Public trade data used for hashing

    Access:
        - Public (no authentication required)
        - Only shows non-PII data (symbol, strategy, timeframe, timestamps)

    Raises:
        404: If trade not found or not closed
    """
    # Fetch trade
    result = await db.execute(select(Trade).where(Trade.trade_id == trade_id))
    trade = result.scalar_one_or_none()

    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    if trade.status != "CLOSED":
        raise HTTPException(status_code=400, detail="Trade not closed yet")

    # Compute hash
    try:
        trade_hash = compute_trade_hash(trade)
    except ValueError as e:
        logger.error(f"Failed to compute hash for trade {trade_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute trade hash")

    # Retrieve blockchain proof (if available)
    ledger_service = LedgerService(db)
    proof = await ledger_service.get_proof(trade_id)

    # Build verifiable data (same fields used for hashing)
    verifiable_data = {
        "trade_id": trade.trade_id,
        "symbol": trade.symbol,
        "strategy": trade.strategy,
        "timeframe": trade.timeframe,
        "trade_type": trade.trade_type,
        "entry_time": trade.entry_time.isoformat() if trade.entry_time else None,
        "exit_time": trade.exit_time.isoformat() if trade.exit_time else None,
        "status": trade.status,
    }

    return TradeProofResponse(
        trade_id=trade.trade_id,
        trade_hash=trade_hash,
        tx_hash=proof["tx_hash"] if proof else None,
        block_number=proof["block_number"] if proof else None,
        chain=proof["chain"] if proof else None,
        timestamp=proof["timestamp"] if proof else None,
        verifiable_data=verifiable_data,
    )


@router.get("/proof/{trade_id}/verify")
async def verify_trade_hash(
    trade_id: str,
    expected_hash: str,
    db: AsyncSession = Depends(get_db),
):
    """Verify that a trade hash matches the recomputed hash.

    Args:
        trade_id: Trade identifier
        expected_hash: Hash to verify

    Returns:
        {"verified": true/false, "recomputed_hash": "...", "expected_hash": "..."}

    Access:
        - Public (no authentication required)
    """
    # Fetch trade
    result = await db.execute(select(Trade).where(Trade.trade_id == trade_id))
    trade = result.scalar_one_or_none()

    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    if trade.status != "CLOSED":
        raise HTTPException(status_code=400, detail="Trade not closed yet")

    # Compute hash
    try:
        ledger_service = LedgerService(db)
        verified = await ledger_service.verify_hash(trade, expected_hash)
        recomputed_hash = compute_trade_hash(trade)

        return {
            "verified": verified,
            "recomputed_hash": recomputed_hash,
            "expected_hash": expected_hash,
            "trade_id": trade_id,
        }

    except ValueError as e:
        logger.error(f"Failed to verify hash for trade {trade_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to verify trade hash")
