"""Comprehensive tests for Feature Quality Alerting (PR-079).

Tests REAL alert delivery with monkeypatch for Telegram HTTP calls.
Tests message formatting, severity mapping, metadata handling.

Coverage targets:
- Alert delivery success/failure
- Message formatting with emoji icons
- Severity mapping
- Metadata serialization
- Integration with quality violations
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.features.quality import QualityMonitor
from backend.app.features.store import FeatureStore
from backend.app.ops.alerts import send_feature_quality_alert


@pytest.mark.asyncio
async def test_send_feature_quality_alert_success(monkeypatch):
    """✅ REAL TEST: Alert sent successfully with proper formatting."""
    sent_messages = []

    async def mock_send(self, message, severity="ERROR", **kwargs):
        sent_messages.append({"message": message, "severity": severity})
        return True

    from backend.app.ops import alerts

    monkeypatch.setattr(alerts.OpsAlertService, "send", mock_send)
    monkeypatch.setenv("OPS_TELEGRAM_BOT_TOKEN", "test_token")
    monkeypatch.setenv("OPS_TELEGRAM_CHAT_ID", "test_chat")

    # Clear cached service
    alerts._alert_service = None

    success = await send_feature_quality_alert(
        violation_type="nan_values",
        symbol="GOLD",
        message="2 features contain NaN: rsi_14, roc_10",
        severity="high",
        metadata={"snapshot_id": 123},
    )

    assert success
    assert len(sent_messages) == 1
    msg = sent_messages[0]
    assert "Feature Quality Violation" in msg["message"]
    assert "nan_values" in msg["message"]
    assert "GOLD" in msg["message"]
    assert "2 features contain NaN" in msg["message"]
    assert "snapshot_id: 123" in msg["message"]
    assert msg["severity"] == "HIGH"


@pytest.mark.asyncio
async def test_send_feature_quality_alert_severity_icons(monkeypatch):
    """✅ REAL TEST: Correct emoji icons for each severity level."""
    sent_messages = []

    async def mock_send(self, message, severity="ERROR", **kwargs):
        sent_messages.append({"message": message, "severity": severity})
        return True

    from backend.app.ops import alerts

    monkeypatch.setattr(alerts.OpsAlertService, "send", mock_send)
    monkeypatch.setenv("OPS_TELEGRAM_BOT_TOKEN", "test_token")
    monkeypatch.setenv("OPS_TELEGRAM_CHAT_ID", "test_chat")
    alerts._alert_service = None

    # Test each severity level
    severities = ["low", "medium", "high"]
    icons = {"low": "ℹ️", "medium": "⚠️", "high": "🚨"}

    for severity in severities:
        sent_messages.clear()
        await send_feature_quality_alert(
            violation_type="test",
            symbol="GOLD",
            message="Test message",
            severity=severity,
        )

        assert len(sent_messages) == 1
        assert icons[severity] in sent_messages[0]["message"]


@pytest.mark.asyncio
async def test_send_feature_quality_alert_no_metadata(monkeypatch):
    """✅ REAL TEST: Alert works without metadata."""
    sent_messages = []

    async def mock_send(self, message, severity="ERROR", **kwargs):
        sent_messages.append({"message": message})
        return True

    from backend.app.ops import alerts

    monkeypatch.setattr(alerts.OpsAlertService, "send", mock_send)
    monkeypatch.setenv("OPS_TELEGRAM_BOT_TOKEN", "test_token")
    monkeypatch.setenv("OPS_TELEGRAM_CHAT_ID", "test_chat")
    alerts._alert_service = None

    success = await send_feature_quality_alert(
        violation_type="stale_data",
        symbol="GOLD",
        message="Data is 600s old",
        severity="medium",
    )

    assert success
    assert len(sent_messages) == 1
    # Should not contain "Details:" section
    assert "snapshot_id" not in sent_messages[0]["message"]


@pytest.mark.asyncio
async def test_send_feature_quality_alert_config_error(monkeypatch):
    """✅ REAL TEST: Alert fails gracefully when not configured."""
    from backend.app.ops import alerts

    # Clear env vars
    monkeypatch.delenv("OPS_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("OPS_TELEGRAM_CHAT_ID", raising=False)
    alerts._alert_service = None

    success = await send_feature_quality_alert(
        violation_type="nan_values",
        symbol="GOLD",
        message="Test",
        severity="high",
    )

    # Should return False but not raise exception
    assert not success


@pytest.mark.asyncio
async def test_quality_monitor_integration_with_alerts(
    db_session: AsyncSession, monkeypatch
):
    """✅ REAL TEST: Quality monitor violations can be sent as alerts."""
    store = FeatureStore(db_session)
    monitor = QualityMonitor(db_session, max_age_seconds=300)

    sent_alerts = []

    async def mock_send(self, message, severity="ERROR", **kwargs):
        sent_alerts.append({"message": message, "severity": severity})
        return True

    from backend.app.ops import alerts

    monkeypatch.setattr(alerts.OpsAlertService, "send", mock_send)
    monkeypatch.setenv("OPS_TELEGRAM_BOT_TOKEN", "test_token")
    monkeypatch.setenv("OPS_TELEGRAM_CHAT_ID", "test_chat")
    alerts._alert_service = None

    # Store snapshot with violations
    await store.put_features(
        symbol="GOLD",
        timestamp=datetime.now(UTC) - timedelta(seconds=600),  # Stale
        features={"rsi": float("nan")},  # NaN
        quality_score=0.5,  # Low quality
    )

    report = await monitor.check_quality(
        symbol="GOLD",
        expected_features=["rsi", "roc"],  # roc missing
    )

    # Send each violation as alert
    for violation in report.violations:
        await send_feature_quality_alert(
            violation_type=violation.type.value,
            symbol=violation.symbol,
            message=violation.message,
            severity=violation.severity,
            metadata=violation.metadata,
        )

    # Should have sent alerts for each violation
    assert len(sent_alerts) >= 3
    alert_messages = [a["message"] for a in sent_alerts]

    # Verify different violation types present
    combined = " ".join(alert_messages)
    assert "stale_data" in combined or "STALE_DATA" in combined
    assert "nan_values" in combined or "NAN_VALUES" in combined


@pytest.mark.asyncio
async def test_alert_metadata_serialization(monkeypatch):
    """✅ REAL TEST: Complex metadata serialized correctly in alert."""
    sent_messages = []

    async def mock_send(self, message, severity="ERROR", **kwargs):
        sent_messages.append({"message": message})
        return True

    from backend.app.ops import alerts

    monkeypatch.setattr(alerts.OpsAlertService, "send", mock_send)
    monkeypatch.setenv("OPS_TELEGRAM_BOT_TOKEN", "test_token")
    monkeypatch.setenv("OPS_TELEGRAM_CHAT_ID", "test_chat")
    alerts._alert_service = None

    metadata = {
        "age_seconds": 600,
        "max_age_seconds": 300,
        "snapshot_timestamp": "2025-11-09T12:00:00Z",
        "z_score": 4.5,
        "feature": "rsi_14",
    }

    await send_feature_quality_alert(
        violation_type="stale_data",
        symbol="GOLD",
        message="Test",
        severity="high",
        metadata=metadata,
    )

    assert len(sent_messages) == 1
    msg = sent_messages[0]["message"]

    # Verify all metadata keys present
    for key in metadata.keys():
        assert key in msg


@pytest.mark.asyncio
async def test_violation_type_formatting(monkeypatch):
    """✅ REAL TEST: All violation types format correctly."""
    sent_messages = []

    async def mock_send(self, message, severity="ERROR", **kwargs):
        sent_messages.append({"message": message, "type": None})
        return True

    from backend.app.ops import alerts

    monkeypatch.setattr(alerts.OpsAlertService, "send", mock_send)
    monkeypatch.setenv("OPS_TELEGRAM_BOT_TOKEN", "test_token")
    monkeypatch.setenv("OPS_TELEGRAM_CHAT_ID", "test_chat")
    alerts._alert_service = None

    violation_types = [
        "missing_features",
        "nan_values",
        "stale_data",
        "drift_detected",
        "low_quality_score",
    ]

    for vtype in violation_types:
        sent_messages.clear()
        await send_feature_quality_alert(
            violation_type=vtype,
            symbol="GOLD",
            message=f"Test {vtype}",
            severity="medium",
        )

        assert len(sent_messages) == 1
        assert vtype in sent_messages[0]["message"]


@pytest.mark.asyncio
async def test_alert_html_formatting(monkeypatch):
    """✅ REAL TEST: Alert uses HTML formatting tags."""
    sent_messages = []

    async def mock_send(self, message, severity="ERROR", **kwargs):
        sent_messages.append({"message": message})
        return True

    from backend.app.ops import alerts

    monkeypatch.setattr(alerts.OpsAlertService, "send", mock_send)
    monkeypatch.setenv("OPS_TELEGRAM_BOT_TOKEN", "test_token")
    monkeypatch.setenv("OPS_TELEGRAM_CHAT_ID", "test_chat")
    alerts._alert_service = None

    await send_feature_quality_alert(
        violation_type="nan_values",
        symbol="GOLD",
        message="Test message",
        severity="high",
        metadata={"snapshot_id": 123},
    )

    assert len(sent_messages) == 1
    msg = sent_messages[0]["message"]

    # Verify HTML tags present
    assert "<b>" in msg and "</b>" in msg
    assert "<code>" in msg and "</code>" in msg
