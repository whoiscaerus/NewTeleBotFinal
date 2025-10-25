"""Outbound signal delivery with HMAC authentication."""

from backend.app.trading.outbound.client import HmacClient
from backend.app.trading.outbound.config import OutboundConfig
from backend.app.trading.outbound.exceptions import (
    OutboundClientError,
    OutboundError,
    OutboundSignatureError,
)
from backend.app.trading.outbound.hmac import build_signature, verify_signature
from backend.app.trading.outbound.responses import SignalIngestResponse

__all__ = [
    "HmacClient",
    "OutboundConfig",
    "OutboundError",
    "OutboundClientError",
    "OutboundSignatureError",
    "build_signature",
    "verify_signature",
    "SignalIngestResponse",
]
