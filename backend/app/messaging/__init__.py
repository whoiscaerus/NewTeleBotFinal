"""Messaging package: Multi-channel notification infrastructure.

This package provides:
- Messaging bus: Redis/Celery queue facade with priority lanes
- Template system: Jinja2 email, MarkdownV2 Telegram, PWA push
- Senders: Email (SMTP), Telegram (Bot API), Push (web-push)
- Position failure templates: Entry/SL/TP execution failure alerts

Integration points:
- PR-059 (User Preferences): Filter notifications by enabled channels/instruments
- PR-104 (Position Tracking): Send position failure alerts
- PR-044 (Price Alerts): Send price alert notifications
"""

import importlib.util

# Import template rendering functions from templates.py file (not templates/ directory)
# Python's import system prioritizes the templates/ directory, so we need explicit file path
import os
import sys

from backend.app.messaging.bus import enqueue_campaign, enqueue_message

templates_file_path = os.path.join(os.path.dirname(__file__), "templates.py")
spec = importlib.util.spec_from_file_location("templates_module", templates_file_path)
if spec is None or spec.loader is None:
    raise ImportError(f"Could not load templates module from {templates_file_path}")
templates_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(templates_module)

render_email = templates_module.render_email
render_telegram = templates_module.render_telegram
render_push = templates_module.render_push

__all__ = [
    "enqueue_message",
    "enqueue_campaign",
    "render_email",
    "render_telegram",
    "render_push",
]
