"""Position Failure Templates: Entry/SL/TP execution failure messages.

These templates are used for PR-104 (Position Tracking) integration to alert users when:
1. Entry execution failed (EA cannot open position)
2. Stop loss auto-close failed (SL hit but EA cannot close position)
3. Take profit auto-close failed (TP hit but EA cannot close position)

Each template has 3 channel variants:
- Email: HTML template with subject line
- Telegram: MarkdownV2-formatted message
- Push: PWA push notification with title, body, data

Template variables are defined in docstrings for each template.
"""

# =============================================================================
# ENTRY EXECUTION FAILED TEMPLATES
# =============================================================================

ENTRY_FAILURE_EMAIL = {
    "subject": "⚠️ Manual Trade Entry Required - {instrument}",
    "template_file": "position_failure_entry.html",
    "required_vars": [
        "instrument",
        "side",
        "entry_price",
        "volume",
        "error_reason",
        "approval_id",
    ],
}

ENTRY_FAILURE_TELEGRAM = """⚠️ *Manual Action Required*

Your trade entry failed and requires manual execution:

*Instrument*: {instrument}
*Side*: {side_emoji} {side}
*Entry Price*: {entry_price}
*Volume*: {volume} lots
*Error*: {error_reason}

Please execute this trade manually in your broker platform\\.

Approval ID: `{approval_id}`
"""

ENTRY_FAILURE_PUSH = {
    "title": "⚠️ Manual Trade Entry Required",
    "body": "{instrument} {side} entry failed - manual execution needed",
    "icon": "/icon-192x192.png",
    "badge": "/badge-96x96.png",
    "data": {"url": "/dashboard/approvals/{approval_id}"},
}

# =============================================================================
# STOP LOSS AUTO-CLOSE FAILED TEMPLATES
# =============================================================================

SL_FAILURE_EMAIL = {
    "subject": "🚨 URGENT: Manual Stop Loss Close Required",
    "template_file": "position_failure_sl.html",
    "required_vars": [
        "instrument",
        "side",
        "entry_price",
        "current_price",
        "loss_amount",
        "broker_ticket",
    ],
}

SL_FAILURE_TELEGRAM = """🛑 *URGENT: Stop Loss Hit*

Your position hit stop loss but auto\\-close failed:

*Instrument*: {instrument}
*Side*: {side_emoji} {side}
*Entry*: {entry_price}
*Current*: {current_price}
*Loss*: \\-{loss_amount} {currency}
*Broker Ticket*: {broker_ticket}

*ACTION REQUIRED*: Close this position manually NOW to prevent further losses\\.
"""

SL_FAILURE_PUSH = {
    "title": "🚨 URGENT: Stop Loss Hit",
    "body": "{instrument} SL hit but auto-close failed - close manually NOW",
    "icon": "/icon-192x192.png",
    "badge": "/badge-96x96.png",
    "data": {"url": "/dashboard/positions", "urgency": "high"},
}

# =============================================================================
# TAKE PROFIT AUTO-CLOSE FAILED TEMPLATES
# =============================================================================

TP_FAILURE_EMAIL = {
    "subject": "✅ Manual Take Profit Close Required",
    "template_file": "position_failure_tp.html",
    "required_vars": [
        "instrument",
        "side",
        "entry_price",
        "current_price",
        "profit_amount",
        "broker_ticket",
    ],
}

TP_FAILURE_TELEGRAM = """✅ *Take Profit Hit*

Your position hit take profit but auto\\-close failed:

*Instrument*: {instrument}
*Side*: {side_emoji} {side}
*Entry*: {entry_price}
*Current*: {current_price}
*Profit*: \\+{profit_amount} {currency}
*Broker Ticket*: {broker_ticket}

*ACTION REQUIRED*: Close this position manually to secure your profit\\.
"""

TP_FAILURE_PUSH = {
    "title": "✅ Take Profit Hit",
    "body": "{instrument} TP hit but auto-close failed - close manually to secure profit",
    "icon": "/icon-192x192.png",
    "badge": "/badge-96x96.png",
    "data": {"url": "/dashboard/positions", "urgency": "medium"},
}
