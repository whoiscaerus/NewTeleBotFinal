"""Trading positions module.

This module handles server-side position tracking with hidden owner SL/TP levels.
Critical for anti-reselling protection - clients never see exit levels.

Key Components:
    - OpenPosition: Position tracking model with hidden owner_sl/owner_tp
    - PositionStatus: Position lifecycle states

Security:
    The owner_sl and owner_tp fields are NEVER exposed to client APIs.
    This prevents clients from seeing complete trading strategy and reselling signals.
"""

from .models import OpenPosition, PositionStatus

__all__ = [
    "OpenPosition",
    "PositionStatus",
]
