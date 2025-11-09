"""
PR-083: Gateway Migration - Compatibility shims and WebSocket replacement.

This module provides migration tooling for Flask → FastAPI gateway consolidation.
"""

from backend.app.gateway.compat import router as compat_router
from backend.app.gateway.websocket import router as websocket_router

__all__ = ["compat_router", "websocket_router"]
