"""
Alerts Module

Price alerts with Telegram and Mini App notifications.
"""

from backend.app.alerts.service import (
    AlertCreate,
    AlertNotification,
    AlertOut,
    AlertUpdate,
    PriceAlert,
    PriceAlertService,
)

__all__ = [
    "PriceAlert",
    "AlertNotification",
    "PriceAlertService",
    "AlertCreate",
    "AlertUpdate",
    "AlertOut",
]
