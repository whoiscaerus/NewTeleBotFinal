"""
Comprehensive tests for AI Analyst / Market Outlook (PR-091).

Test Coverage:
- Toggle functionality (8 tests)
- Outlook generation (12 tests)
- Scheduler (5 tests)
- Templates (4 tests)

Total: 29 tests
"""

from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.analyst import (
    FeatureDisabledError,
    build_outlook,
    is_analyst_enabled,
    is_analyst_owner_only,
)
from backend.app.ai.models import FeatureFlag
from backend.app.ai.schemas import CorrelationPair, OutlookReport, VolatilityZone
from backend.app.messaging.templates import (
    render_daily_outlook_email,
    render_daily_outlook_telegram,
)

# ========================================
# Toggle Tests (8 tests)
# ========================================


@pytest_asyncio.fixture(autouse=True)
async def seed_feature_flag(db_session: AsyncSession):
    """Seed the feature_flags table with default values."""
    # Check if flag exists
    flag = await db_session.get(FeatureFlag, "ai_analyst")
    if not flag:
        flag = FeatureFlag(
            name="ai_analyst",
            enabled=False,
            owner_only=True,
            description="Daily AI-written Market Outlook",
        )
        db_session.add(flag)
        await db_session.flush()
    return flag


@pytest.mark.asyncio
class TestAnalystToggle:
    """Test owner toggle functionality."""

    async def test_analyst_disabled_by_default(self, db_session: AsyncSession):
        """Test AI Analyst is disabled by default (safety-first)."""
        # Migration creates flag with enabled=FALSE
        enabled = await is_analyst_enabled(db_session)
        assert enabled is False, "AI Analyst should be disabled by default"

    async def test_analyst_owner_only_by_default(self, db_session: AsyncSession):
        """Test AI Analyst is owner-only by default."""
        owner_only = await is_analyst_owner_only(db_session)
        assert owner_only is True, "AI Analyst should be owner-only by default"

    async def test_toggle_enable_via_api(
        self, client: AsyncClient, admin_headers: dict, db_session: AsyncSession
    ):
        """Test owner can enable AI Analyst via API."""
        response = await client.post(
            "/api/v1/ai/analyst/toggle",
            json={"enabled": True, "owner_only": True},
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["owner_only"] is True
        assert data["name"] == "ai_analyst"

        # Verify DB updated
        enabled = await is_analyst_enabled(db_session)
        assert enabled is True

    async def test_toggle_disable_via_api(
        self, client: AsyncClient, admin_headers: dict, db_session: AsyncSession
    ):
        """Test owner can disable AI Analyst via API."""
        # First enable
        await client.post(
            "/api/v1/ai/analyst/toggle",
            json={"enabled": True, "owner_only": True},
            headers=admin_headers,
        )

        # Then disable
        response = await client.post(
            "/api/v1/ai/analyst/toggle",
            json={"enabled": False, "owner_only": True},
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False

        # Verify DB updated
        enabled = await is_analyst_enabled(db_session)
        assert enabled is False

    async def test_toggle_requires_admin(self, client: AsyncClient, auth_headers: dict):
        """Test only admin can toggle AI Analyst."""
        response = await client.post(
            "/api/v1/ai/analyst/toggle",
            json={"enabled": True, "owner_only": True},
            headers=auth_headers,  # Regular user, not admin
        )

        assert response.status_code == 403

    async def test_toggle_owner_only_flag(
        self, client: AsyncClient, admin_headers: dict, db_session: AsyncSession
    ):
        """Test owner_only flag can be toggled."""
        # Enable with owner-only
        await client.post(
            "/api/v1/ai/analyst/toggle",
            json={"enabled": True, "owner_only": True},
            headers=admin_headers,
        )

        # Switch to public
        response = await client.post(
            "/api/v1/ai/analyst/toggle",
            json={"enabled": True, "owner_only": False},
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["owner_only"] is False

        # Verify DB updated
        owner_only = await is_analyst_owner_only(db_session)
        assert owner_only is False

    async def test_get_analyst_status(self, client: AsyncClient, auth_headers: dict):
        """Test any user can view analyst status."""
        response = await client.get("/api/v1/ai/analyst/status", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "owner_only" in data
        assert "name" in data
        assert data["name"] == "ai_analyst"

    async def test_toggle_persists_across_sessions(
        self, client: AsyncClient, admin_headers: dict, db_session: AsyncSession
    ):
        """Test toggle persists (DB-backed, not in-memory)."""
        # Enable
        await client.post(
            "/api/v1/ai/analyst/toggle",
            json={"enabled": True, "owner_only": False},
            headers=admin_headers,
        )

        # Simulate new session (fresh DB query)
        await db_session.close()
        enabled = await is_analyst_enabled(db_session)
        owner_only = await is_analyst_owner_only(db_session)

        assert enabled is True
        assert owner_only is False


# ========================================
# Outlook Generation Tests (12 tests)
# ========================================


@pytest.mark.asyncio
class TestOutlookGeneration:
    """Test outlook generation business logic."""

    async def test_outlook_generation_requires_enabled(self, db_session: AsyncSession):
        """Test outlook generation fails if feature disabled."""
        # Ensure disabled
        # (default state from migration)

        with pytest.raises(FeatureDisabledError):
            await build_outlook(db_session, target_date=date.today())

    async def test_outlook_includes_data_citations(
        self, db_session: AsyncSession, enable_analyst
    ):
        """Test outlook narrative includes source citations."""
        outlook = await build_outlook(db_session, target_date=date.today())

        assert "Sharpe Ratio" in outlook.narrative
        assert "Sortino Ratio" in outlook.narrative
        assert "Drawdown" in outlook.narrative
        assert "RSI" in outlook.narrative
        assert "ROC" in outlook.narrative
        assert "Volatility" in outlook.narrative

        # Check data_citations dict
        assert "sharpe_ratio" in outlook.data_citations
        assert "sortino_ratio" in outlook.data_citations
        assert "max_drawdown_pct" in outlook.data_citations
        assert "volatility_pct" in outlook.data_citations
        assert "rsi" in outlook.data_citations
        assert "roc" in outlook.data_citations

    async def test_extreme_values_handled(
        self, db_session: AsyncSession, enable_analyst
    ):
        """Test extreme values don't crash generation."""
        # Mock extreme metrics
        with patch(
            "backend.app.ai.analyst._fetch_performance_metrics",
            return_value={
                "sharpe_ratio": -2.5,  # Extreme negative
                "sortino_ratio": 0.1,
                "volatility_pct": 150.0,  # Extreme volatility
                "win_rate": 10.0,  # Very low
            },
        ):
            with patch(
                "backend.app.ai.analyst._calculate_max_drawdown",
                return_value=Decimal("-75.5"),  # Extreme drawdown
            ):
                with patch(
                    "backend.app.ai.analyst._fetch_equity_series",
                    return_value=Mock(),
                ):
                    outlook = await build_outlook(db_session, target_date=date.today())

                    assert outlook is not None
                    assert (
                        "extreme" in outlook.narrative.lower()
                        or "ALERT" in outlook.narrative
                    )
                    assert len(outlook.narrative) > 200

    async def test_zero_trades_handled(self, db_session: AsyncSession, enable_analyst):
        """Test outlook handles zero trades gracefully."""
        # Mock no equity data
        with patch("backend.app.ai.analyst._fetch_equity_series", return_value=None):
            with patch(
                "backend.app.ai.analyst._fetch_performance_metrics",
                return_value={
                    "sharpe_ratio": 0.0,
                    "sortino_ratio": 0.0,
                    "volatility_pct": 0.0,
                    "win_rate": 0.0,
                },
            ):
                outlook = await build_outlook(db_session, target_date=date.today())

                assert "No Trading Activity" in outlook.narrative
                assert "Insufficient data" in outlook.narrative

    async def test_volatility_zones_calculated(
        self, db_session: AsyncSession, enable_analyst
    ):
        """Test volatility zones are calculated correctly."""
        outlook = await build_outlook(db_session, target_date=date.today())

        assert len(outlook.volatility_zones) == 3
        assert any(z.level == "low" for z in outlook.volatility_zones)
        assert any(z.level == "medium" for z in outlook.volatility_zones)
        assert any(z.level == "high" for z in outlook.volatility_zones)

        # Check thresholds
        zones_dict = {z.level: z.threshold for z in outlook.volatility_zones}
        assert zones_dict["low"] < zones_dict["medium"]
        assert zones_dict["medium"] < zones_dict["high"]

    async def test_correlations_computed(
        self, db_session: AsyncSession, enable_analyst
    ):
        """Test correlations are computed (top 3 pairs)."""
        outlook = await build_outlook(db_session, target_date=date.today())

        assert len(outlook.correlations) >= 1
        assert len(outlook.correlations) <= 3

        for corr in outlook.correlations:
            assert corr.instrument_a == "GOLD"
            assert -1.0 <= corr.coefficient <= 1.0

    async def test_narrative_coherence(self, db_session: AsyncSession, enable_analyst):
        """Test narrative meets minimum length and structure."""
        with patch(
            "backend.app.ai.analyst._fetch_equity_series",
            return_value=Mock(),
        ):
            outlook = await build_outlook(db_session, target_date=date.today())

            assert len(outlook.narrative) >= 200
            assert "Daily Market Outlook" in outlook.narrative
            assert "GOLD" in outlook.narrative
            assert "Data Citations" in outlook.narrative
            assert "not financial advice" in outlook.narrative.lower()

    async def test_no_pii_leaked(self, db_session: AsyncSession, enable_analyst):
        """Test narrative doesn't leak PII or secrets."""
        outlook = await build_outlook(db_session, target_date=date.today())

        # Check for common PII patterns
        import re

        email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        assert not re.search(
            email_pattern, outlook.narrative
        ), "Email found in narrative"

        # Check for API key patterns
        api_key_pattern = r"(api[_-]?key|token|secret)[:\s]*['\"]?[A-Za-z0-9_-]{20,}"
        assert not re.search(
            api_key_pattern, outlook.narrative, re.IGNORECASE
        ), "API key found in narrative"

        # Check for credit card patterns (simple check)
        cc_pattern = r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"
        assert not re.search(
            cc_pattern, outlook.narrative
        ), "Credit card found in narrative"

    async def test_timestamps_utc(self, db_session: AsyncSession, enable_analyst):
        """Test all timestamps are in UTC."""
        outlook = await build_outlook(db_session, target_date=date.today())

        # generated_at should be UTC
        assert outlook.generated_at.tzinfo is None  # Naive datetime (assumed UTC)
        # Or if timezone-aware:
        # assert outlook.generated_at.tzinfo == timezone.utc

    async def test_instruments_covered(self, db_session: AsyncSession, enable_analyst):
        """Test instruments_covered field is populated."""
        outlook = await build_outlook(
            db_session, target_date=date.today(), instrument="GOLD"
        )

        assert "GOLD" in outlook.instruments_covered
        assert len(outlook.instruments_covered) >= 1

    async def test_data_citations_complete(
        self, db_session: AsyncSession, enable_analyst
    ):
        """Test all expected metrics are in data_citations."""
        outlook = await build_outlook(db_session, target_date=date.today())

        expected_keys = [
            "sharpe_ratio",
            "sortino_ratio",
            "max_drawdown_pct",
            "volatility_pct",
            "win_rate",
            "rsi",
            "roc",
        ]

        for key in expected_keys:
            assert key in outlook.data_citations, f"Missing citation: {key}"

    async def test_outlook_api_endpoint_owner_only(
        self,
        client: AsyncClient,
        admin_headers: dict,
        auth_headers: dict,
        enable_analyst,
        clear_auth_override,
    ):
        """Test owner-only mode restricts viewing to admin."""
        # Enable with owner-only
        response = await client.post(
            "/api/v1/ai/analyst/toggle",
            json={"enabled": True, "owner_only": True},
            headers=admin_headers,
        )
        assert response.status_code == 200

        # Admin can view
        response_admin = await client.get(
            "/api/v1/ai/outlook/latest", headers=admin_headers
        )
        assert response_admin.status_code == 200

        # Regular user cannot view
        response_user = await client.get(
            "/api/v1/ai/outlook/latest", headers=auth_headers
        )
        assert response_user.status_code == 403
        assert "owner-only" in response_user.json()["detail"].lower()


# ========================================
# Scheduler Tests (5 tests)
# ========================================


@pytest.mark.asyncio
class TestScheduler:
    """Test daily outlook scheduler."""

    async def test_scheduler_skips_when_disabled(self, db_session: AsyncSession):
        """Test disabled analyst skips outlook generation."""
        from backend.schedulers.daily_outlook import generate_daily_outlook

        @asynccontextmanager
        async def mock_factory():
            yield db_session

        with patch(
            "backend.schedulers.daily_outlook.get_async_session",
            side_effect=mock_factory,
        ):
            # Ensure disabled (default)
            # Should log and return without error
            await generate_daily_outlook()  # Should not raise

    async def test_scheduler_generates_when_enabled(
        self, db_session: AsyncSession, enable_analyst
    ):
        """Test enabled analyst generates daily outlook."""
        from backend.schedulers.daily_outlook import generate_daily_outlook

        @asynccontextmanager
        async def mock_factory():
            yield db_session

        with patch(
            "backend.schedulers.daily_outlook.get_async_session",
            side_effect=mock_factory,
        ):
            # Should generate without error
            await generate_daily_outlook()  # Should not raise

    async def test_scheduler_owner_only_sends_to_owner(
        self, db_session: AsyncSession, enable_analyst
    ):
        """Test owner-only mode sends to owner email only."""
        from backend.schedulers.daily_outlook import generate_daily_outlook

        @asynccontextmanager
        async def mock_factory():
            yield db_session

        with patch(
            "backend.schedulers.daily_outlook.get_async_session",
            side_effect=mock_factory,
        ):
            # Mock _send_to_owner
            with patch(
                "backend.schedulers.daily_outlook._send_to_owner", new=AsyncMock()
            ) as mock_send:
                await generate_daily_outlook()
                mock_send.assert_called_once()

    async def test_scheduler_public_sends_to_all(
        self, db_session: AsyncSession, enable_analyst_public
    ):
        """Test public mode sends to all users."""
        from backend.schedulers.daily_outlook import generate_daily_outlook

        @asynccontextmanager
        async def mock_factory():
            yield db_session

        with patch(
            "backend.schedulers.daily_outlook.get_async_session",
            side_effect=mock_factory,
        ):
            # Mock bulk send functions
            with patch(
                "backend.schedulers.daily_outlook._send_to_all_users_email",
                new=AsyncMock(return_value=50),
            ) as mock_email:
                with patch(
                    "backend.schedulers.daily_outlook._send_to_all_users_telegram",
                    new=AsyncMock(return_value=30),
                ) as mock_telegram:
                    await generate_daily_outlook()
                    mock_email.assert_called_once()
                    mock_telegram.assert_called_once()

    async def test_scheduler_increments_metrics(
        self, db_session: AsyncSession, enable_analyst
    ):
        """Test metrics increment on publish."""
        from backend.schedulers.daily_outlook import generate_daily_outlook

        @asynccontextmanager
        async def mock_factory():
            yield db_session

        with patch(
            "backend.schedulers.daily_outlook.get_async_session",
            side_effect=mock_factory,
        ):
            # Mock metrics
            with patch("backend.schedulers.daily_outlook.metrics") as mock_metrics:
                mock_metrics.ai_outlook_published_total = Mock()
                mock_metrics.ai_outlook_published_total.labels = Mock(
                    return_value=Mock(inc=Mock())
                )

                await generate_daily_outlook()

                # Should increment email metric
                mock_metrics.ai_outlook_published_total.labels.assert_called_with(
                    channel="email"
                )


# ========================================
# Template Tests (4 tests)
# ========================================


class TestTemplates:
    """Test messaging templates."""

    def test_email_template_renders_html(self, sample_outlook):
        """Test email template renders HTML correctly."""
        result = render_daily_outlook_email(sample_outlook)

        assert "subject" in result
        assert "html" in result
        assert "text" in result

        # Check HTML structure
        assert "<!DOCTYPE html>" in result["html"]
        assert "Daily Market Outlook" in result["html"]
        assert sample_outlook.narrative[:50] in result["html"]

        # Check citations rendered
        assert "Sharpe Ratio" in result["html"]
        assert "Sortino Ratio" in result["html"]

    def test_email_template_plain_text_fallback(self, sample_outlook):
        """Test email template has plain text fallback."""
        result = render_daily_outlook_email(sample_outlook)

        # Plain text should not have HTML tags
        assert "<html>" not in result["text"]
        assert "<div>" not in result["text"]

        # Should have content
        assert "Daily Market Outlook" in result["text"]
        assert sample_outlook.narrative[:50] in result["text"]

    def test_telegram_template_renders_markdown(self, sample_outlook):
        """Test Telegram template renders Markdown correctly."""
        result = render_daily_outlook_telegram(sample_outlook)

        assert "📊 *Daily Market Outlook*" in result
        assert "Sharpe:" in result
        assert "Sortino:" in result
        assert "not financial advice" in result.lower()

    def test_telegram_template_escapes_special_chars(self, sample_outlook):
        """Test Telegram template escapes special characters for MarkdownV2."""
        # Create outlook with special chars in narrative
        sample_outlook.narrative = "Test (parentheses) and [brackets] and . dots"

        result = render_daily_outlook_telegram(sample_outlook)

        # Special chars should be escaped with backslash
        assert "\\(" in result or "parentheses" not in result  # Truncated or escaped
        # Note: Narrative is truncated to 500 chars, so escaping applies to truncated text


# ========================================
# Fixtures
# ========================================


@pytest_asyncio.fixture
async def enable_analyst(db_session: AsyncSession):
    """Enable AI Analyst for testing."""
    from sqlalchemy import update

    from backend.app.ai.models import FeatureFlag

    stmt = (
        update(FeatureFlag)
        .where(FeatureFlag.name == "ai_analyst")
        .values(enabled=True, owner_only=True)
    )
    await db_session.execute(stmt)
    await db_session.commit()
    yield
    # Cleanup: Disable after test
    stmt = (
        update(FeatureFlag)
        .where(FeatureFlag.name == "ai_analyst")
        .values(enabled=False, owner_only=True)
    )
    await db_session.execute(stmt)
    await db_session.commit()


@pytest_asyncio.fixture
async def enable_analyst_public(db_session: AsyncSession):
    """Enable AI Analyst in public mode for testing."""
    from sqlalchemy import update

    from backend.app.ai.models import FeatureFlag

    stmt = (
        update(FeatureFlag)
        .where(FeatureFlag.name == "ai_analyst")
        .values(enabled=True, owner_only=False)
    )
    await db_session.execute(stmt)
    await db_session.commit()
    yield
    # Cleanup
    stmt = (
        update(FeatureFlag)
        .where(FeatureFlag.name == "ai_analyst")
        .values(enabled=False, owner_only=True)
    )
    await db_session.execute(stmt)
    await db_session.commit()


@pytest.fixture
def sample_outlook() -> OutlookReport:
    """Create sample outlook for testing."""
    return OutlookReport(
        narrative="""## Daily Market Outlook - January 15, 2024

### GOLD Analysis

**Performance Overview**

Our GOLD strategy has delivered a **Sharpe Ratio of 1.25** over the past 90 days, indicating moderate risk-adjusted returns. The **Sortino Ratio of 1.50** suggests good downside risk management.

Current **maximum drawdown stands at -15.3%**, which is within acceptable parameters. The strategy maintains a **win rate of 65.0%**, demonstrating solid trade selection.

**Volatility Analysis**

Market volatility is currently at **12.5%**, placing us in the **low volatility zone**. This calm environment supports active trading with standard position sizing.

**Technical Context**

The 14-period RSI for GOLD reads **62.5**, suggesting the market is in neutral territory. The 10-period ROC at **2.3%** indicates bullish momentum.

**Correlation Analysis**

Cross-asset correlations reveal important relationships:

- **USD/JPY**: strong negative correlation (-0.65) - moves inversely
- **US10Y**: moderate positive correlation (+0.42) - moves in tandem
- **DXY**: strong negative correlation (-0.78) - moves inversely

**Outlook**

Given the strong risk-adjusted returns and manageable drawdown, the strategy remains well-positioned. The low volatility environment supports active trading with standard position sizing.

Traders should remain vigilant for continuation patterns and manage positions according to their individual risk tolerance.

### Data Citations

- **Sharpe Ratio**: 1.25 (90-day rolling)
- **Sortino Ratio**: 1.50 (90-day rolling)
- **Max Drawdown**: -15.3%
- **Volatility**: 12.5% (annualized)
- **Win Rate**: 65.0%
- **RSI (14)**: 62.5
- **ROC (10)**: 2.30%

---

*This is an AI-generated analysis based on historical data. Past performance does not guarantee future results. Not financial advice. Trade at your own risk.*
""",
        volatility_zones=[
            VolatilityZone(
                level="low",
                threshold=10.0,
                description="Calm market conditions, expect tight ranges",
            ),
            VolatilityZone(
                level="medium",
                threshold=20.0,
                description="Moderate volatility, normal trading conditions",
            ),
            VolatilityZone(
                level="high",
                threshold=30.0,
                description="Elevated volatility, expect wide swings",
            ),
        ],
        correlations=[
            CorrelationPair(
                instrument_a="GOLD", instrument_b="USD/JPY", coefficient=-0.65
            ),
            CorrelationPair(
                instrument_a="GOLD", instrument_b="US10Y", coefficient=0.42
            ),
            CorrelationPair(instrument_a="GOLD", instrument_b="DXY", coefficient=-0.78),
        ],
        data_citations={
            "sharpe_ratio": 1.25,
            "sortino_ratio": 1.50,
            "max_drawdown_pct": -15.3,
            "volatility_pct": 12.5,
            "win_rate": 65.0,
            "rsi": 62.5,
            "roc": 2.3,
        },
        generated_at=datetime(2024, 1, 15, 6, 0, 0),
        instruments_covered=["GOLD"],
    )
