"""Decentralized trade ledger for public verifiability.

Provides blockchain-based proof-of-execution for closed trades.
Hash submission is opt-in and only occurs post-close.
"""

from backend.app.trust.ledger.adapters import (
    ArbitrumAdapter,
    BlockchainAdapter,
    PolygonAdapter,
)
from backend.app.trust.ledger.service import LedgerService, compute_trade_hash

__all__ = [
    "LedgerService",
    "compute_trade_hash",
    "BlockchainAdapter",
    "PolygonAdapter",
    "ArbitrumAdapter",
]
