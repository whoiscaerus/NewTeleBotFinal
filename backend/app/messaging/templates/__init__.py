"""Messaging templates package: Position failure and other message templates."""

# Import template constants from position_failures module
# Import rendering functions from sibling templates.py file
# Note: backend.app.messaging has both templates/ (package) and templates.py (module)
# We need to import from the .py file, not this package
import importlib.util
import sys
from pathlib import Path

from backend.app.messaging.templates.position_failures import (
    ENTRY_FAILURE_EMAIL,
    ENTRY_FAILURE_PUSH,
    ENTRY_FAILURE_TELEGRAM,
    SL_FAILURE_EMAIL,
    SL_FAILURE_PUSH,
    SL_FAILURE_TELEGRAM,
    TP_FAILURE_EMAIL,
    TP_FAILURE_PUSH,
    TP_FAILURE_TELEGRAM,
)

# Get path to templates.py file (sibling to this package)
templates_py_path = Path(__file__).parent.parent / "templates.py"

# Load templates.py as a module
spec = importlib.util.spec_from_file_location(
    "messaging_templates_module", templates_py_path
)
if spec and spec.loader:
    templates_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(templates_module)

    # Extract the functions we need
    escape_markdownv2 = templates_module.escape_markdownv2
    render_email = templates_module.render_email
    render_push = templates_module.render_push
    render_telegram = templates_module.render_telegram
    render_daily_outlook_email = templates_module.render_daily_outlook_email
    render_daily_outlook_telegram = templates_module.render_daily_outlook_telegram
    validate_template_vars = templates_module.validate_template_vars

__all__ = [
    # Constants
    "ENTRY_FAILURE_EMAIL",
    "ENTRY_FAILURE_TELEGRAM",
    "ENTRY_FAILURE_PUSH",
    "SL_FAILURE_EMAIL",
    "SL_FAILURE_TELEGRAM",
    "SL_FAILURE_PUSH",
    "TP_FAILURE_EMAIL",
    "TP_FAILURE_TELEGRAM",
    "TP_FAILURE_PUSH",
    # Functions
    "escape_markdownv2",
    "render_email",
    "render_push",
    "render_telegram",
    "render_daily_outlook_email",
    "render_daily_outlook_telegram",
    "validate_template_vars",
]
