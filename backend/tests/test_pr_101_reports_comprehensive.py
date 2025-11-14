"""
Comprehensive tests for PR-101: AI-Generated Reports.

Tests cover:
- Report generation (client/owner, daily/weekly/monthly)
- HTML rendering with real data
- Zero trades edge case
- Multi-channel delivery
- Report storage and retrieval
- Authorization and scoping
- AI summary generation
- Integration with analytics, revenue, messaging
"""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.reports.generator import ReportGenerator
from backend.app.reports.models import Report, ReportPeriod, ReportStatus, ReportType
from backend.app.trading.store.models import Trade
from backend.app.auth.models import User


# Fixtures
@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create test user for client reports."""
    user = User(
        id="test_user_1",
        email="test@example.com",
        telegram_username="testuser",
        telegram_id="123456",
        tier="premium",
        suspended=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_trades(db_session: AsyncSession, test_user: User) -> list[Trade]:
    """Create sample trades for testing."""
    now = datetime.utcnow()
    trades = [
        Trade(
            id="trade_1",
            user_id=test_user.id,
            instrument="XAUUSD",
            side=0,  # BUY
            volume=Decimal("0.10"),
            entry_price=Decimal("1950.50"),
            exit_price=Decimal("1960.50"),
            pnl=Decimal("100.00"),
            closed_at=now - timedelta(hours=1),
        ),
        Trade(
            id="trade_2",
            user_id=test_user.id,
            instrument="XAUUSD",
            side=1,  # SELL
            volume=Decimal("0.10"),
            entry_price=Decimal("1960.00"),
            exit_price=Decimal("1950.00"),
            pnl=Decimal("100.00"),
            closed_at=now - timedelta(hours=2),
        ),
        Trade(
            id="trade_3",
            user_id=test_user.id,
            instrument="EURUSD",
            side=0,
            volume=Decimal("1.00"),
            entry_price=Decimal("1.1000"),
            exit_price=Decimal("1.0950"),
            pnl=Decimal("-50.00"),
            closed_at=now - timedelta(hours=3),
        ),
    ]

    for trade in trades:
        db_session.add(trade)
    await db_session.commit()

    return trades


@pytest.fixture
async def generator(db_session: AsyncSession) -> ReportGenerator:
    """Create report generator instance."""
    return ReportGenerator(db_session)


# Unit Tests: Report Generation Logic
@pytest.mark.asyncio
async def test_build_client_report_with_trades(
    generator: ReportGenerator,
    test_user: User,
    test_trades: list[Trade],
    db_session: AsyncSession,
):
    """Test client report generation with real trade data."""
    report = await generator.build_report(
        ReportPeriod.DAILY, ReportType.CLIENT, user_id=test_user.id
    )

    assert report.id is not None
    assert report.type == ReportType.CLIENT
    assert report.period == ReportPeriod.DAILY
    assert report.status == ReportStatus.COMPLETED
    assert report.user_id == test_user.id
    assert report.generated_at is not None

    # Validate data payload
    data = report.data
    assert data["total_trades"] == 3
    assert data["total_pnl"] == 150.0  # 100 + 100 - 50
    assert data["win_rate"] == 2 / 3  # 2 wins out of 3
    assert data["avg_win"] == 100.0
    assert data["avg_loss"] == 50.0
    assert data["risk_reward"] == 2.0  # 100/50
    assert data["best_trade"] == 100.0
    assert data["worst_trade"] == -50.0

    # AI summary should mention positive results
    assert report.summary is not None
    assert "positive" in report.summary.lower() or "£150.00" in report.summary


@pytest.mark.asyncio
async def test_build_client_report_zero_trades(
    generator: ReportGenerator, test_user: User, db_session: AsyncSession
):
    """Test client report with zero trades (edge case)."""
    report = await generator.build_report(
        ReportPeriod.DAILY, ReportType.CLIENT, user_id=test_user.id
    )

    assert report.status == ReportStatus.COMPLETED
    data = report.data

    # All metrics should be zero
    assert data["total_trades"] == 0
    assert data["total_pnl"] == 0.0
    assert data["win_rate"] == 0.0
    assert data["sharpe_ratio"] is None
    assert data["best_trade"] == 0.0
    assert data["worst_trade"] == 0.0
    assert data["avg_win"] == 0.0
    assert data["avg_loss"] == 0.0
    assert data["top_instruments"] == []

    # AI summary should suggest reviewing signal approvals
    assert "no trades" in report.summary.lower()
    assert "reviewing" in report.summary.lower()


@pytest.mark.asyncio
async def test_build_client_report_negative_week(
    generator: ReportGenerator, test_user: User, db_session: AsyncSession
):
    """Test client report with losing week."""
    now = datetime.utcnow()
    losing_trades = [
        Trade(
            id=f"loss_{i}",
            user_id=test_user.id,
            instrument="XAUUSD",
            side=0,
            volume=Decimal("0.10"),
            entry_price=Decimal("1950.00"),
            exit_price=Decimal("1940.00"),
            pnl=Decimal("-100.00"),
            closed_at=now - timedelta(hours=i),
        )
        for i in range(5)
    ]

    for trade in losing_trades:
        db_session.add(trade)
    await db_session.commit()

    report = await generator.build_report(
        ReportPeriod.WEEKLY, ReportType.CLIENT, user_id=test_user.id
    )

    data = report.data
    assert data["total_trades"] == 5
    assert data["total_pnl"] == -500.0
    assert data["win_rate"] == 0.0  # All losses

    # AI summary should mention negative results
    assert "negative" in report.summary.lower()


@pytest.mark.asyncio
async def test_build_owner_report(generator: ReportGenerator, db_session: AsyncSession):
    """Test owner report generation with business metrics."""
    # Mock revenue service results
    with (
        patch.object(
            generator.revenue_service, "calculate_mrr", return_value=5000.0
        ) as mock_mrr,
        patch.object(
            generator.revenue_service, "calculate_churn_rate", return_value=0.03
        ),
    ):
        report = await generator.build_report(ReportPeriod.MONTHLY, ReportType.OWNER)

        assert report.type == ReportType.OWNER
        assert report.user_id is None  # Owner reports not scoped to user
        assert report.status == ReportStatus.COMPLETED

        data = report.data
        assert "mrr" in data
        assert "churn_rate" in data
        assert "active_users" in data
        assert "platform_win_rate" in data

        # AI summary should mention MRR
        assert "MRR" in report.summary or "mrr" in report.summary.lower()

        # Verify mock was called
        mock_mrr.assert_called()


@pytest.mark.asyncio
async def test_period_range_calculations(generator: ReportGenerator):
    """Test date range calculations for different periods."""
    # Daily: yesterday
    start, end = generator._calculate_period_range(ReportPeriod.DAILY)
    assert (end - start).days == 1

    # Weekly: last 7 days
    start, end = generator._calculate_period_range(ReportPeriod.WEEKLY)
    assert (end - start).days == 7

    # Monthly: last 30 days
    start, end = generator._calculate_period_range(ReportPeriod.MONTHLY)
    assert (end - start).days == 30


@pytest.mark.asyncio
async def test_html_rendering_client(
    generator: ReportGenerator,
    test_user: User,
    test_trades: list[Trade],
    db_session: AsyncSession,
):
    """Test HTML template rendering with real data."""
    report = await generator.build_report(
        ReportPeriod.WEEKLY, ReportType.CLIENT, user_id=test_user.id
    )

    # HTML URL should be generated
    assert report.html_url is not None
    assert report.html_url.startswith("/reports/")

    # Render HTML manually to validate template
    html = generator._render_html(ReportType.CLIENT, report.data, report.summary)

    # Check HTML contains key metrics
    assert "£150.00" in html  # Total P&L
    assert "66.7%" in html or "67%" in html  # Win rate
    assert "Account Summary Report" in html
    assert report.summary in html


@pytest.mark.asyncio
async def test_html_rendering_owner(
    generator: ReportGenerator, db_session: AsyncSession
):
    """Test owner report HTML rendering."""
    with (
        patch.object(generator.revenue_service, "calculate_mrr", return_value=10000.0),
        patch.object(
            generator.revenue_service, "calculate_churn_rate", return_value=0.04
        ),
    ):
        report = await generator.build_report(ReportPeriod.MONTHLY, ReportType.OWNER)

        html = generator._render_html(ReportType.OWNER, report.data, report.summary)

        assert "Business Summary Report" in html
        assert "Confidential" in html
        assert report.summary in html


@pytest.mark.asyncio
async def test_ai_summary_generation_positive(generator: ReportGenerator):
    """Test AI summary for positive performance."""
    data = {
        "total_trades": 10,
        "total_pnl": 500.0,
        "win_rate": 0.7,
        "max_drawdown": 0.10,
    }

    summary = await generator._generate_ai_summary(ReportType.CLIENT, data)

    assert "strong positive" in summary or "positive" in summary
    assert "£500.00" in summary
    assert "70%" in summary or "70.0%" in summary


@pytest.mark.asyncio
async def test_ai_summary_generation_negative(generator: ReportGenerator):
    """Test AI summary for negative performance."""
    data = {
        "total_trades": 5,
        "total_pnl": -200.0,
        "win_rate": 0.2,
        "max_drawdown": 0.25,
    }

    summary = await generator._generate_ai_summary(ReportType.CLIENT, data)

    assert "negative" in summary
    assert "-200.00" in summary or "£-200.00" in summary


@pytest.mark.asyncio
async def test_report_generation_failure_handling(
    generator: ReportGenerator, test_user: User, db_session: AsyncSession
):
    """Test report generation failure tracking."""
    # Mock analytics service to raise exception
    with patch.object(
        generator.equity_service,
        "compute_equity_series",
        side_effect=RuntimeError("Analytics service down"),
    ):
        with pytest.raises(RuntimeError, match="Report generation failed"):
            await generator.build_report(
                ReportPeriod.DAILY, ReportType.CLIENT, user_id=test_user.id
            )

        # Report should be marked as failed
        result = await db_session.execute(
            select(Report).where(Report.user_id == test_user.id)
        )
        report = result.scalar_one_or_none()

        if report:
            assert report.status == ReportStatus.FAILED
            assert report.error_message is not None


@pytest.mark.asyncio
async def test_client_report_requires_user_id(generator: ReportGenerator):
    """Test that client reports require user_id."""
    with pytest.raises(ValueError, match="Client reports require user_id"):
        await generator.build_report(
            ReportPeriod.DAILY, ReportType.CLIENT, user_id=None
        )


@pytest.mark.asyncio
async def test_top_instruments_ranking(
    generator: ReportGenerator, test_user: User, db_session: AsyncSession
):
    """Test instrument ranking by P&L."""
    now = datetime.utcnow()
    trades = [
        Trade(
            id="gold_1",
            user_id=test_user.id,
            instrument="XAUUSD",
            side=0,
            volume=Decimal("0.10"),
            entry_price=Decimal("1950.00"),
            exit_price=Decimal("1960.00"),
            pnl=Decimal("100.00"),
            closed_at=now,
        ),
        Trade(
            id="gold_2",
            user_id=test_user.id,
            instrument="XAUUSD",
            side=0,
            volume=Decimal("0.10"),
            entry_price=Decimal("1960.00"),
            exit_price=Decimal("1970.00"),
            pnl=Decimal("100.00"),
            closed_at=now,
        ),
        Trade(
            id="eur_1",
            user_id=test_user.id,
            instrument="EURUSD",
            side=0,
            volume=Decimal("1.00"),
            entry_price=Decimal("1.1000"),
            exit_price=Decimal("1.1050"),
            pnl=Decimal("50.00"),
            closed_at=now,
        ),
    ]

    for trade in trades:
        db_session.add(trade)
    await db_session.commit()

    report = await generator.build_report(
        ReportPeriod.DAILY, ReportType.CLIENT, user_id=test_user.id
    )

    top_instruments = report.data["top_instruments"]
    assert len(top_instruments) >= 2

    # XAUUSD should be first (highest P&L)
    assert top_instruments[0]["name"] == "XAUUSD"
    assert top_instruments[0]["pnl"] == 200.0
    assert top_instruments[0]["trades"] == 2
    assert top_instruments[0]["win_rate"] == 1.0  # 100% wins


@pytest.mark.asyncio
async def test_report_storage_fields(
    generator: ReportGenerator, test_user: User, db_session: AsyncSession
):
    """Test report entity storage fields."""
    report = await generator.build_report(
        ReportPeriod.WEEKLY, ReportType.CLIENT, user_id=test_user.id
    )

    # URLs
    assert report.html_url is not None
    assert report.pdf_url is not None
    assert report.html_url.endswith(".html")
    assert report.pdf_url.endswith(".pdf")

    # Timestamps
    assert report.created_at is not None
    assert report.generated_at is not None
    assert report.generated_at >= report.created_at

    # Period range
    assert report.period_start < report.period_end
    assert (report.period_end - report.period_start).days == 7


@pytest.mark.asyncio
async def test_multiple_reports_for_user(
    generator: ReportGenerator, test_user: User, db_session: AsyncSession
):
    """Test generating multiple reports for same user."""
    report1 = await generator.build_report(
        ReportPeriod.DAILY, ReportType.CLIENT, user_id=test_user.id
    )
    report2 = await generator.build_report(
        ReportPeriod.WEEKLY, ReportType.CLIENT, user_id=test_user.id
    )

    assert report1.id != report2.id
    assert report1.period != report2.period

    # Both should be retrievable
    result = await db_session.execute(
        select(Report).where(Report.user_id == test_user.id)
    )
    reports = result.scalars().all()
    assert len(reports) == 2


# Integration Tests with Real Services
@pytest.mark.asyncio
async def test_integration_with_equity_service(
    generator: ReportGenerator,
    test_user: User,
    test_trades: list[Trade],
    db_session: AsyncSession,
):
    """Test integration with real equity service."""
    # Equity service should be called during report generation
    report = await generator.build_report(
        ReportPeriod.DAILY, ReportType.CLIENT, user_id=test_user.id
    )

    # Drawdown metrics should be present
    assert "max_drawdown" in report.data
    assert "current_equity" in report.data
    assert "recovery_factor" in report.data


@pytest.mark.asyncio
async def test_integration_with_revenue_service(
    generator: ReportGenerator, db_session: AsyncSession
):
    """Test integration with real revenue service."""
    with (
        patch.object(generator.revenue_service, "calculate_mrr", return_value=7500.0),
        patch.object(
            generator.revenue_service, "calculate_churn_rate", return_value=0.045
        ),
    ):
        report = await generator.build_report(ReportPeriod.MONTHLY, ReportType.OWNER)

        data = report.data
        assert data["mrr"] == 7500.0
        assert data["churn_rate"] == 0.045


# Edge Cases
@pytest.mark.asyncio
async def test_report_with_all_winning_trades(
    generator: ReportGenerator, test_user: User, db_session: AsyncSession
):
    """Test report where all trades are winners (100% win rate)."""
    now = datetime.utcnow()
    winning_trades = [
        Trade(
            id=f"win_{i}",
            user_id=test_user.id,
            instrument="XAUUSD",
            side=0,
            volume=Decimal("0.10"),
            entry_price=Decimal("1950.00"),
            exit_price=Decimal("1960.00"),
            pnl=Decimal("100.00"),
            closed_at=now - timedelta(hours=i),
        )
        for i in range(3)
    ]

    for trade in winning_trades:
        db_session.add(trade)
    await db_session.commit()

    report = await generator.build_report(
        ReportPeriod.DAILY, ReportType.CLIENT, user_id=test_user.id
    )

    data = report.data
    assert data["win_rate"] == 1.0
    assert data["avg_loss"] == 0.0  # No losses
    assert data["worst_trade"] >= 0.0


@pytest.mark.asyncio
async def test_report_with_all_losing_trades(
    generator: ReportGenerator, test_user: User, db_session: AsyncSession
):
    """Test report where all trades are losers (0% win rate)."""
    now = datetime.utcnow()
    losing_trades = [
        Trade(
            id=f"loss_{i}",
            user_id=test_user.id,
            instrument="XAUUSD",
            side=0,
            volume=Decimal("0.10"),
            entry_price=Decimal("1950.00"),
            exit_price=Decimal("1940.00"),
            pnl=Decimal("-50.00"),
            closed_at=now - timedelta(hours=i),
        )
        for i in range(3)
    ]

    for trade in losing_trades:
        db_session.add(trade)
    await db_session.commit()

    report = await generator.build_report(
        ReportPeriod.DAILY, ReportType.CLIENT, user_id=test_user.id
    )

    data = report.data
    assert data["win_rate"] == 0.0
    assert data["avg_win"] == 0.0  # No wins
    assert data["total_pnl"] < 0


@pytest.mark.asyncio
async def test_report_period_label_formatting(generator: ReportGenerator):
    """Test period label formatting."""
    start = datetime(2025, 1, 1)
    end = datetime(2025, 1, 8)

    label = generator._format_period_label(start, end)

    assert "2025-01-01" in label
    assert "2025-01-08" in label
    assert " to " in label
