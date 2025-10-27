"""
Phase 6 Integration Tests - Database Query Integration

Tests for Phase 6 database queries and caching:
- ReconciliationQueryService tests
- PositionQueryService tests
- GuardQueryService tests
- Cache effectiveness tests
- Error handling tests
- End-to-end API tests with real data

Author: Trading System
Date: 2024-10-26
"""

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.trading.query_service import (
    GuardQueryService,
    PositionQueryService,
    ReconciliationQueryService,
)
from backend.app.trading.reconciliation.models import ReconciliationLog
from backend.app.trading.schemas import AlertType, ConditionType


@pytest.mark.asyncio
class TestReconciliationQueryService:
    """Test ReconciliationQueryService database queries."""

    async def test_get_reconciliation_status_healthy_no_data(
        self,
        db_session: AsyncSession,
        test_user_id: UUID,
    ):
        """Test reconciliation status when no logs exist."""
        # Should return healthy idle status with empty events
        status = await ReconciliationQueryService.get_reconciliation_status(
            db_session,
            test_user_id,
        )

        assert status.user_id == test_user_id
        assert status.status == "idle"  # No positions
        assert status.total_syncs == 0
        assert status.open_positions_count == 0
        assert status.matched_positions == 0
        assert status.divergences_detected == 0
        assert len(status.recent_events) == 0

    async def test_get_reconciliation_status_with_matched_positions(
        self,
        db_session: AsyncSession,
        test_user_id: UUID,
    ):
        """Test reconciliation status with matched positions in database."""
        # Create test reconciliation log
        log = ReconciliationLog(
            user_id=test_user_id,
            mt5_position_id=12345,
            symbol="XAUUSD",
            direction="buy",
            volume=0.1,
            entry_price=1950.50,
            current_price=1955.75,
            take_profit=1960.00,
            stop_loss=1945.00,
            matched=1,  # Matched
            divergence_reason=None,
            close_reason=None,
            event_type="sync",
            status="success",
        )
        db_session.add(log)
        await db_session.commit()

        # Get reconciliation status
        status = await ReconciliationQueryService.get_reconciliation_status(
            db_session,
            test_user_id,
        )

        assert status.status == "healthy"
        assert status.open_positions_count == 1
        assert status.matched_positions == 1
        assert status.divergences_detected == 0
        assert len(status.recent_events) > 0

    async def test_get_reconciliation_status_with_divergences(
        self,
        db_session: AsyncSession,
        test_user_id: UUID,
    ):
        """Test reconciliation status when divergences exist."""
        # Create divergence log
        log = ReconciliationLog(
            user_id=test_user_id,
            mt5_position_id=12346,
            symbol="EURUSD",
            direction="sell",
            volume=0.5,
            entry_price=1.0950,
            current_price=1.0925,
            matched=2,  # Divergence
            divergence_reason="slippage",
            slippage_pips=5.0,
            event_type="warning",
            status="warning",
        )
        db_session.add(log)
        await db_session.commit()

        status = await ReconciliationQueryService.get_reconciliation_status(
            db_session,
            test_user_id,
        )

        assert status.status == "warning"
        assert status.divergences_detected >= 1
        assert status.error_message is not None

    async def test_get_recent_reconciliation_logs(
        self,
        db_session: AsyncSession,
        test_user_id: UUID,
    ):
        """Test fetching recent reconciliation logs."""
        # Create multiple logs
        for i in range(3):
            log = ReconciliationLog(
                user_id=test_user_id,
                mt5_position_id=12345 + i,
                symbol="XAUUSD",
                direction="buy",
                volume=0.1,
                entry_price=1950.50 + i,
                matched=1,
                event_type="sync",
                status="success",
            )
            db_session.add(log)

        await db_session.commit()

        # Fetch recent logs
        logs = await ReconciliationQueryService.get_recent_reconciliation_logs(
            db_session,
            test_user_id,
            limit=10,
            hours=24,
        )

        assert len(logs) >= 3


@pytest.mark.asyncio
class TestPositionQueryService:
    """Test PositionQueryService database queries."""

    async def test_get_open_positions_empty(
        self,
        db_session: AsyncSession,
        test_user_id: UUID,
    ):
        """Test fetching positions when none exist."""
        positions, total_pnl, total_pnl_pct = (
            await PositionQueryService.get_open_positions(
                db_session,
                test_user_id,
            )
        )

        assert len(positions) == 0
        assert total_pnl == 0.0
        assert total_pnl_pct == 0.0

    async def test_get_open_positions_with_data(
        self,
        db_session: AsyncSession,
        test_user_id: UUID,
    ):
        """Test fetching open positions with data."""
        # Create test position
        log = ReconciliationLog(
            user_id=test_user_id,
            mt5_position_id=12345,
            symbol="XAUUSD",
            direction="buy",
            volume=0.1,
            entry_price=1950.50,
            current_price=1955.75,
            take_profit=1960.00,
            stop_loss=1945.00,
            matched=1,
            close_reason=None,  # Open
            event_type="sync",
            status="success",
        )
        db_session.add(log)
        await db_session.commit()

        positions, total_pnl, total_pnl_pct = (
            await PositionQueryService.get_open_positions(
                db_session,
                test_user_id,
            )
        )

        assert len(positions) == 1
        position = positions[0]
        assert position.symbol == "XAUUSD"
        assert position.direction == "buy"
        assert position.volume == 0.1
        assert position.matched_with_bot is True

    async def test_get_open_positions_with_symbol_filter(
        self,
        db_session: AsyncSession,
        test_user_id: UUID,
    ):
        """Test filtering positions by symbol."""
        # Create two positions
        for symbol in ["XAUUSD", "EURUSD"]:
            log = ReconciliationLog(
                user_id=test_user_id,
                mt5_position_id=12345 if symbol == "XAUUSD" else 12346,
                symbol=symbol,
                direction="buy",
                volume=0.1,
                entry_price=1950.50 if symbol == "XAUUSD" else 1.0950,
                current_price=1955.75 if symbol == "XAUUSD" else 1.0925,
                matched=1,
                close_reason=None,
                event_type="sync",
                status="success",
            )
            db_session.add(log)

        await db_session.commit()

        # Filter by XAUUSD
        positions, _, _ = await PositionQueryService.get_open_positions(
            db_session,
            test_user_id,
            symbol="XAUUSD",
        )

        assert len(positions) == 1
        assert positions[0].symbol == "XAUUSD"

    async def test_get_position_by_id(
        self,
        db_session: AsyncSession,
        test_user_id: UUID,
    ):
        """Test fetching a specific position by ID."""
        # Create position
        log = ReconciliationLog(
            user_id=test_user_id,
            mt5_position_id=12345,
            symbol="XAUUSD",
            direction="buy",
            volume=0.1,
            entry_price=1950.50,
            current_price=1955.75,
            matched=1,
            event_type="sync",
            status="success",
        )
        db_session.add(log)
        await db_session.commit()

        position = await PositionQueryService.get_position_by_id(
            db_session,
            test_user_id,
            log.id,
        )

        assert position is not None
        assert position.symbol == "XAUUSD"
        assert str(position.position_id) == str(log.id)


@pytest.mark.asyncio
class TestGuardQueryService:
    """Test GuardQueryService database queries."""

    async def test_get_drawdown_alert_normal(
        self,
        db_session: AsyncSession,
        test_user_id: UUID,
    ):
        """Test drawdown alert when equity is healthy."""
        alert = await GuardQueryService.get_drawdown_alert(
            db_session,
            test_user_id,
            current_equity=9500.0,
            peak_equity=10000.0,
            alert_threshold_pct=20.0,
        )

        assert alert.current_drawdown_pct == 5.0
        assert alert.alert_type == AlertType.NORMAL
        assert alert.should_close_all is False

    async def test_get_drawdown_alert_warning(
        self,
        db_session: AsyncSession,
        test_user_id: UUID,
    ):
        """Test drawdown alert in warning state."""
        alert = await GuardQueryService.get_drawdown_alert(
            db_session,
            test_user_id,
            current_equity=8500.0,
            peak_equity=10000.0,
            alert_threshold_pct=20.0,
        )

        assert alert.current_drawdown_pct == 15.0
        assert alert.alert_type == AlertType.WARNING
        assert alert.should_close_all is False

    async def test_get_drawdown_alert_critical(
        self,
        db_session: AsyncSession,
        test_user_id: UUID,
    ):
        """Test drawdown alert in critical state (should liquidate)."""
        alert = await GuardQueryService.get_drawdown_alert(
            db_session,
            test_user_id,
            current_equity=8000.0,
            peak_equity=10000.0,
            alert_threshold_pct=20.0,
        )

        assert alert.current_drawdown_pct == 20.0
        assert alert.alert_type == AlertType.CRITICAL
        assert alert.should_close_all is True
        assert alert.time_to_liquidation_seconds is not None

    async def test_get_market_condition_alerts_empty(
        self,
        db_session: AsyncSession,
        test_user_id: UUID,
    ):
        """Test market condition alerts when none exist."""
        alerts = await GuardQueryService.get_market_condition_alerts(
            db_session,
            test_user_id,
        )

        assert len(alerts) == 0

    async def test_get_market_condition_alerts_with_data(
        self,
        db_session: AsyncSession,
        test_user_id: UUID,
    ):
        """Test market condition alerts with guard triggers."""
        # Create guard trigger log
        log = ReconciliationLog(
            user_id=test_user_id,
            mt5_position_id=12345,
            symbol="XAUUSD",
            direction="buy",
            volume=0.1,
            entry_price=1950.00,
            divergence_reason="gap",
            slippage_pips=50.0,
            event_type="guard_trigger",
            status="warning",
        )
        db_session.add(log)
        await db_session.commit()

        alerts = await GuardQueryService.get_market_condition_alerts(
            db_session,
            test_user_id,
        )

        assert len(alerts) >= 1
        assert alerts[0].symbol == "XAUUSD"
        assert alerts[0].condition_type == ConditionType.PRICE_GAP


@pytest.mark.asyncio
class TestPhase6Integration:
    """End-to-end integration tests for Phase 6."""

    async def test_full_api_flow_with_database(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user_id: UUID,
    ):
        """Test complete API flow with database integration."""
        # Create test data
        log = ReconciliationLog(
            user_id=test_user_id,
            mt5_position_id=12345,
            symbol="XAUUSD",
            direction="buy",
            volume=0.1,
            entry_price=1950.50,
            current_price=1955.75,
            matched=1,
            event_type="sync",
            status="success",
        )
        db_session.add(log)
        await db_session.commit()

        # Test reconciliation endpoint
        response = await client.get(
            "/api/v1/reconciliation/status",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "idle", "warning"]
        assert "total_syncs" in data

        # Test positions endpoint
        response = await client.get(
            "/api/v1/positions/open",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "positions" in data
        assert isinstance(data["positions"], list)

        # Test guards endpoint
        response = await client.get(
            "/api/v1/guards/status",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "drawdown_guard" in data
        assert "market_guard_alerts" in data

    async def test_authorization_enforcement(
        self,
        client: AsyncClient,
    ):
        """Test that endpoints require authentication."""
        # Try without auth headers
        response = await client.get("/api/v1/reconciliation/status")
        assert response.status_code == 401

        response = await client.get("/api/v1/positions/open")
        assert response.status_code == 401

        response = await client.get("/api/v1/guards/status")
        assert response.status_code == 401

    async def test_health_check_no_auth(self, client: AsyncClient):
        """Test that health check works without authentication."""
        response = await client.get("/api/v1/trading/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "trading-api"
