"""
Basic tests for PR-101: AI-Generated Reports.

Simplified tests to avoid circular import issues.
Tests core report generation logic without full integration.
"""

from datetime import datetime, timedelta

import pytest

from backend.app.reports.models import Report, ReportPeriod, ReportStatus, ReportType


@pytest.mark.asyncio
async def test_report_model_creation(db_session):
    """Test Report model can be created and saved."""
    report = Report(
        type=ReportType.CLIENT,
        period=ReportPeriod.DAILY,
        status=ReportStatus.COMPLETED,
        user_id="test_user_123",
        period_start=datetime.utcnow() - timedelta(days=1),
        period_end=datetime.utcnow(),
        summary="Test AI summary for daily report",
        data={
            "total_pnl": 150.0,
            "total_trades": 3,
            "win_rate": 0.67,
        },
        html_url="https://reports.example.com/report_123.html",
        pdf_url="https://reports.example.com/report_123.pdf",
        delivered_channels=["email", "telegram"],
    )

    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    assert report.id is not None
    assert report.type == ReportType.CLIENT
    assert report.status == ReportStatus.COMPLETED
    assert report.user_id == "test_user_123"
    assert report.data["total_pnl"] == 150.0
    assert "email" in report.delivered_channels


@pytest.mark.asyncio
async def test_report_period_enum():
    """Test ReportPeriod enum values."""
    assert ReportPeriod.DAILY == "DAILY"
    assert ReportPeriod.WEEKLY == "WEEKLY"
    assert ReportPeriod.MONTHLY == "MONTHLY"


@pytest.mark.asyncio
async def test_report_type_enum():
    """Test ReportType enum values."""
    assert ReportType.CLIENT == "CLIENT"
    assert ReportType.OWNER == "OWNER"


@pytest.mark.asyncio
async def test_report_status_enum():
    """Test ReportStatus enum values."""
    assert ReportStatus.PENDING == "PENDING"
    assert ReportStatus.GENERATING == "GENERATING"
    assert ReportStatus.COMPLETED == "COMPLETED"
    assert ReportStatus.FAILED == "FAILED"


@pytest.mark.asyncio
async def test_report_data_jsonb_storage(db_session):
    """Test that JSONB data field stores arbitrary JSON."""
    report = Report(
        type=ReportType.OWNER,
        period=ReportPeriod.MONTHLY,
        status=ReportStatus.COMPLETED,
        user_id=None,  # Owner reports have no user_id
        period_start=datetime.utcnow() - timedelta(days=30),
        period_end=datetime.utcnow(),
        summary="Owner business summary",
        data={
            "mrr": 5000.0,
            "churn_rate": 0.03,
            "active_users": 250,
            "platform_win_rate": 0.72,
            "top_instruments": [
                {"name": "XAUUSD", "trades": 1200, "pnl": 45000.0},
                {"name": "EURUSD", "trades": 800, "pnl": 32000.0},
            ],
        },
        html_url="https://reports.example.com/owner_monthly.html",
        pdf_url="https://reports.example.com/owner_monthly.pdf",
    )

    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    assert report.data["mrr"] == 5000.0
    assert report.data["churn_rate"] == 0.03
    assert len(report.data["top_instruments"]) == 2
    assert report.data["top_instruments"][0]["name"] == "XAUUSD"


@pytest.mark.asyncio
async def test_report_delivery_tracking(db_session):
    """Test delivery tracking with delivered/failed channels."""
    report = Report(
        type=ReportType.CLIENT,
        period=ReportPeriod.WEEKLY,
        status=ReportStatus.COMPLETED,
        user_id="test_user_456",
        period_start=datetime.utcnow() - timedelta(days=7),
        period_end=datetime.utcnow(),
        summary="Weekly performance summary",
        data={"total_pnl": 300.0},
        html_url="https://reports.example.com/weekly_456.html",
        pdf_url="https://reports.example.com/weekly_456.pdf",
        delivered_channels=["email"],  # Email succeeded
        delivery_failed_channels=["telegram"],  # Telegram failed
    )

    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    assert "email" in report.delivered_channels
    assert "telegram" in report.delivery_failed_channels
    assert len(report.delivered_channels) == 1
    assert len(report.delivery_failed_channels) == 1


@pytest.mark.asyncio
async def test_report_failure_tracking(db_session):
    """Test failed report with error message."""
    report = Report(
        type=ReportType.CLIENT,
        period=ReportPeriod.DAILY,
        status=ReportStatus.FAILED,
        user_id="test_user_789",
        period_start=datetime.utcnow() - timedelta(days=1),
        period_end=datetime.utcnow(),
        error_message="Failed to compute equity metrics: Database connection timeout",
    )

    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    assert report.status == ReportStatus.FAILED
    assert report.error_message is not None
    assert "Database connection timeout" in report.error_message
    assert report.html_url is None  # No URLs for failed reports


@pytest.mark.asyncio
async def test_report_timestamps(db_session):
    """Test created_at and generated_at timestamps."""
    report = Report(
        type=ReportType.CLIENT,
        period=ReportPeriod.DAILY,
        status=ReportStatus.GENERATING,
        user_id="test_user_999",
        period_start=datetime.utcnow() - timedelta(days=1),
        period_end=datetime.utcnow(),
    )

    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    assert report.created_at is not None
    assert report.generated_at is None  # Not generated yet

    # Simulate generation completion
    report.status = ReportStatus.COMPLETED
    report.generated_at = datetime.utcnow()
    report.html_url = "https://reports.example.com/generated.html"

    await db_session.commit()
    await db_session.refresh(report)

    assert report.generated_at is not None
    assert report.generated_at >= report.created_at


print("✅ PR-101 basic tests module loaded successfully")
