"""
Comprehensive API route tests for PR-052 (Equity & Drawdown Engine).

Tests all API endpoints:
- GET /analytics/equity
- GET /analytics/drawdown

Validates:
- Authentication requirements
- Input validation
- Response schemas
- Error handling (404, 500)
- Date range filtering
- Business logic correctness
"""

import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.analytics.models import DimSymbol, DimDay, TradesFact
from backend.app.auth.models import User


pytestmark = pytest.mark.asyncio


class TestEquityRoutes:
    """Test GET /analytics/equity endpoint."""

    async def test_equity_endpoint_requires_auth(self, client: AsyncClient):
        """Test equity endpoint requires JWT authentication."""
        response = await client.get("/api/v1/analytics/equity")
        
        assert response.status_code == 401
        assert "detail" in response.json()

    async def test_equity_endpoint_returns_curve(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Test equity endpoint returns equity curve with proper structure."""
        # Create test data
        symbol = DimSymbol(symbol="GOLD", created_at=datetime.utcnow())
        db_session.add(symbol)
        await db_session.flush()

        # Create 5 days
        days = []
        for i in range(1, 6):
            dim_day = DimDay(
                date=date(2025, 1, i),
                day_of_week=i % 7,
                week_of_year=1,
                month=1,
                year=2025,
                is_trading_day=1,
                created_at=datetime.utcnow(),
            )
            db_session.add(dim_day)
            await db_session.flush()
            days.append(dim_day)

        # Create profitable trades
        trade1 = TradesFact(
            user_id=test_user.id,
            symbol_id=symbol.id,
            date_id=days[0].id,
            side=0,
            entry_price=Decimal("1950"),
            exit_price=Decimal("1960"),
            volume=Decimal("1.0"),
            entry_time=datetime(2025, 1, 1, 10, 0),
            exit_time=datetime(2025, 1, 1, 14, 0),
            gross_pnl=Decimal("10"),
            fees=Decimal("1"),
            net_pnl=Decimal("9"),
            created_at=datetime.utcnow(),
        )
        trade2 = TradesFact(
            user_id=test_user.id,
            symbol_id=symbol.id,
            date_id=days[2].id,
            side=1,
            entry_price=Decimal("1970"),
            exit_price=Decimal("1965"),
            volume=Decimal("1.0"),
            entry_time=datetime(2025, 1, 3, 10, 0),
            exit_time=datetime(2025, 1, 3, 14, 0),
            gross_pnl=Decimal("5"),
            fees=Decimal("0.5"),
            net_pnl=Decimal("4.5"),
            created_at=datetime.utcnow(),
        )
        db_session.add_all([trade1, trade2])
        await db_session.commit()

        # Call endpoint
        response = await client.get("/api/v1/analytics/equity", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        # Validate structure
        assert "points" in data
        assert "initial_equity" in data
        assert "final_equity" in data
        assert "total_return_percent" in data
        assert "max_drawdown_percent" in data
        assert "days_in_period" in data

        # Validate points
        points = data["points"]
        assert len(points) == 5  # 5 days (including gaps)
        
        # Each point should have required fields
        for point in points:
            assert "date" in point
            assert "equity" in point
            assert "cumulative_pnl" in point
            assert "drawdown_percent" in point

        # Business logic validation
        assert data["initial_equity"] == 10000  # Default initial balance
        assert data["final_equity"] > 10000  # Made profit
        assert data["total_return_percent"] > 0  # Positive return

    async def test_equity_endpoint_respects_date_range(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Test equity endpoint filters by start_date and end_date."""
        # Create test data spanning 10 days
        symbol = DimSymbol(symbol="GOLD", created_at=datetime.utcnow())
        db_session.add(symbol)
        await db_session.flush()

        days = []
        for i in range(1, 11):
            dim_day = DimDay(
                date=date(2025, 1, i),
                day_of_week=i % 7,
                week_of_year=1,
                month=1,
                year=2025,
                is_trading_day=1,
                created_at=datetime.utcnow(),
            )
            db_session.add(dim_day)
            await db_session.flush()
            days.append(dim_day)

        # Create trades on days 1, 5, and 10
        for day_idx in [0, 4, 9]:
            trade = TradesFact(
                user_id=test_user.id,
                symbol_id=symbol.id,
                date_id=days[day_idx].id,
                side=0,
                entry_price=Decimal("1950"),
                exit_price=Decimal("1960"),
                volume=Decimal("1.0"),
                entry_time=datetime(2025, 1, day_idx + 1, 10, 0),
                exit_time=datetime(2025, 1, day_idx + 1, 14, 0),
                gross_pnl=Decimal("10"),
                fees=Decimal("1"),
                net_pnl=Decimal("9"),
                created_at=datetime.utcnow(),
            )
            db_session.add(trade)
        await db_session.commit()

        # Filter to days 3-7
        response = await client.get(
            "/api/v1/analytics/equity",
            params={"start_date": "2025-01-03", "end_date": "2025-01-07"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        
        # Should only include days 3-7 (5 days)
        assert data["days_in_period"] == 5
        assert len(data["points"]) == 5
        
        # First point should be 2025-01-03
        assert data["points"][0]["date"] == "2025-01-03"
        # Last point should be 2025-01-07
        assert data["points"][-1]["date"] == "2025-01-07"

    async def test_equity_endpoint_handles_no_trades(
        self,
        client: AsyncClient,
        test_user: User,
        auth_headers: dict,
    ):
        """Test equity endpoint returns 404 when user has no trades."""
        response = await client.get("/api/v1/analytics/equity", headers=auth_headers)

        assert response.status_code == 404
        assert "detail" in response.json()
        assert "no trades" in response.json()["detail"].lower()

    async def test_equity_endpoint_validates_initial_balance(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Test equity endpoint accepts custom initial_balance."""
        # Create minimal test data
        symbol = DimSymbol(symbol="GOLD", created_at=datetime.utcnow())
        db_session.add(symbol)
        await db_session.flush()

        dim_day = DimDay(
            date=date(2025, 1, 1),
            day_of_week=1,
            week_of_year=1,
            month=1,
            year=2025,
            is_trading_day=1,
            created_at=datetime.utcnow(),
        )
        db_session.add(dim_day)
        await db_session.flush()

        trade = TradesFact(
            user_id=test_user.id,
            symbol_id=symbol.id,
            date_id=dim_day.id,
            side=0,
            entry_price=Decimal("1950"),
            exit_price=Decimal("1960"),
            volume=Decimal("1.0"),
            entry_time=datetime(2025, 1, 1, 10, 0),
            exit_time=datetime(2025, 1, 1, 14, 0),
            gross_pnl=Decimal("10"),
            fees=Decimal("1"),
            net_pnl=Decimal("9"),
            created_at=datetime.utcnow(),
        )
        db_session.add(trade)
        await db_session.commit()

        # Call with custom initial balance
        response = await client.get(
            "/api/v1/analytics/equity",
            params={"initial_balance": 50000},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        
        # Initial equity should match custom balance
        assert data["initial_equity"] == 50000
        # Final equity should be initial + net_pnl
        assert data["final_equity"] == 50009


class TestDrawdownRoutes:
    """Test GET /analytics/drawdown endpoint."""

    async def test_drawdown_endpoint_requires_auth(self, client: AsyncClient):
        """Test drawdown endpoint requires JWT authentication."""
        response = await client.get("/api/v1/analytics/drawdown")
        
        assert response.status_code == 401
        assert "detail" in response.json()

    async def test_drawdown_endpoint_returns_stats(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Test drawdown endpoint returns complete drawdown statistics."""
        # Create test data with drawdown scenario
        symbol = DimSymbol(symbol="GOLD", created_at=datetime.utcnow())
        db_session.add(symbol)
        await db_session.flush()

        days = []
        for i in range(1, 6):
            dim_day = DimDay(
                date=date(2025, 1, i),
                day_of_week=i % 7,
                week_of_year=1,
                month=1,
                year=2025,
                is_trading_day=1,
                created_at=datetime.utcnow(),
            )
            db_session.add(dim_day)
            await db_session.flush()
            days.append(dim_day)

        # Create trades: +100, +50, -80, -20, +150 (creates drawdown)
        pnls = [Decimal("100"), Decimal("50"), Decimal("-80"), Decimal("-20"), Decimal("150")]
        
        for i, pnl in enumerate(pnls):
            trade = TradesFact(
                user_id=test_user.id,
                symbol_id=symbol.id,
                date_id=days[i].id,
                side=0 if pnl > 0 else 1,
                entry_price=Decimal("1950"),
                exit_price=Decimal("1960") if pnl > 0 else Decimal("1940"),
                volume=Decimal("1.0"),
                entry_time=datetime(2025, 1, i + 1, 10, 0),
                exit_time=datetime(2025, 1, i + 1, 14, 0),
                gross_pnl=pnl + Decimal("1"),
                fees=Decimal("1"),
                net_pnl=pnl,
                created_at=datetime.utcnow(),
            )
            db_session.add(trade)
        await db_session.commit()

        # Call endpoint
        response = await client.get("/api/v1/analytics/drawdown", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        # Validate structure
        assert "max_drawdown_percent" in data
        assert "current_drawdown_percent" in data
        assert "peak_equity" in data
        assert "trough_equity" in data
        assert "drawdown_duration_days" in data
        assert "recovery_time_days" in data
        assert "average_drawdown_percent" in data

        # Business logic validation
        # After +100, +50 → peak at 10150
        # After -80, -20 → trough at 10050
        # Drawdown = (10150 - 10050) / 10150 * 100 ≈ 0.985%
        assert data["max_drawdown_percent"] > 0
        assert data["peak_equity"] == 10150
        assert data["trough_equity"] == 10050

    async def test_drawdown_endpoint_handles_no_drawdown(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Test drawdown endpoint handles scenario with no drawdown (all wins)."""
        # Create test data with only winning trades
        symbol = DimSymbol(symbol="GOLD", created_at=datetime.utcnow())
        db_session.add(symbol)
        await db_session.flush()

        days = []
        for i in range(1, 4):
            dim_day = DimDay(
                date=date(2025, 1, i),
                day_of_week=i % 7,
                week_of_year=1,
                month=1,
                year=2025,
                is_trading_day=1,
                created_at=datetime.utcnow(),
            )
            db_session.add(dim_day)
            await db_session.flush()
            days.append(dim_day)

        # Create only profitable trades
        for i in range(3):
            trade = TradesFact(
                user_id=test_user.id,
                symbol_id=symbol.id,
                date_id=days[i].id,
                side=0,
                entry_price=Decimal("1950"),
                exit_price=Decimal("1960"),
                volume=Decimal("1.0"),
                entry_time=datetime(2025, 1, i + 1, 10, 0),
                exit_time=datetime(2025, 1, i + 1, 14, 0),
                gross_pnl=Decimal("10"),
                fees=Decimal("1"),
                net_pnl=Decimal("9"),
                created_at=datetime.utcnow(),
            )
            db_session.add(trade)
        await db_session.commit()

        # Call endpoint
        response = await client.get("/api/v1/analytics/drawdown", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        # No drawdown scenario
        assert data["max_drawdown_percent"] == 0
        assert data["current_drawdown_percent"] == 0
        assert data["average_drawdown_percent"] == 0

    async def test_drawdown_endpoint_respects_date_range(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Test drawdown endpoint filters by date range."""
        # Create test data spanning 10 days
        symbol = DimSymbol(symbol="GOLD", created_at=datetime.utcnow())
        db_session.add(symbol)
        await db_session.flush()

        days = []
        for i in range(1, 11):
            dim_day = DimDay(
                date=date(2025, 1, i),
                day_of_week=i % 7,
                week_of_year=1,
                month=1,
                year=2025,
                is_trading_day=1,
                created_at=datetime.utcnow(),
            )
            db_session.add(dim_day)
            await db_session.flush()
            days.append(dim_day)

        # Create trades with drawdown in middle
        pnls = [Decimal("100")] * 10
        pnls[4] = Decimal("-50")  # Drawdown on day 5
        pnls[5] = Decimal("-30")  # Continues drawdown
        
        for i, pnl in enumerate(pnls):
            trade = TradesFact(
                user_id=test_user.id,
                symbol_id=symbol.id,
                date_id=days[i].id,
                side=0 if pnl > 0 else 1,
                entry_price=Decimal("1950"),
                exit_price=Decimal("1960") if pnl > 0 else Decimal("1940"),
                volume=Decimal("1.0"),
                entry_time=datetime(2025, 1, i + 1, 10, 0),
                exit_time=datetime(2025, 1, i + 1, 14, 0),
                gross_pnl=pnl + Decimal("1"),
                fees=Decimal("1"),
                net_pnl=pnl,
                created_at=datetime.utcnow(),
            )
            db_session.add(trade)
        await db_session.commit()

        # Filter to days 1-4 (before drawdown)
        response = await client.get(
            "/api/v1/analytics/drawdown",
            params={"start_date": "2025-01-01", "end_date": "2025-01-04"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        # Should have no drawdown (all wins)
        assert data["max_drawdown_percent"] == 0

    async def test_drawdown_endpoint_handles_no_trades(
        self,
        client: AsyncClient,
        test_user: User,
        auth_headers: dict,
    ):
        """Test drawdown endpoint returns 404 when user has no trades."""
        response = await client.get("/api/v1/analytics/drawdown", headers=auth_headers)

        assert response.status_code == 404
        assert "detail" in response.json()
        assert "no trades" in response.json()["detail"].lower()


class TestEdgeCases:
    """Test edge cases and error handling."""

    async def test_equity_invalid_date_range(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Test equity endpoint handles invalid date range (start > end)."""
        # Create minimal test data
        symbol = DimSymbol(symbol="GOLD", created_at=datetime.utcnow())
        db_session.add(symbol)
        await db_session.flush()

        dim_day = DimDay(
            date=date(2025, 1, 1),
            day_of_week=1,
            week_of_year=1,
            month=1,
            year=2025,
            is_trading_day=1,
            created_at=datetime.utcnow(),
        )
        db_session.add(dim_day)
        await db_session.flush()

        trade = TradesFact(
            user_id=test_user.id,
            symbol_id=symbol.id,
            date_id=dim_day.id,
            side=0,
            entry_price=Decimal("1950"),
            exit_price=Decimal("1960"),
            volume=Decimal("1.0"),
            entry_time=datetime(2025, 1, 1, 10, 0),
            exit_time=datetime(2025, 1, 1, 14, 0),
            gross_pnl=Decimal("10"),
            fees=Decimal("1"),
            net_pnl=Decimal("9"),
            created_at=datetime.utcnow(),
        )
        db_session.add(trade)
        await db_session.commit()

        # Call with invalid range (start after end)
        response = await client.get(
            "/api/v1/analytics/equity",
            params={"start_date": "2025-01-31", "end_date": "2025-01-01"},
            headers=auth_headers,
        )

        # Should return error
        assert response.status_code in [400, 404, 500]

    async def test_concurrent_requests_same_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Test concurrent requests to equity endpoint don't interfere."""
        # Create test data
        symbol = DimSymbol(symbol="GOLD", created_at=datetime.utcnow())
        db_session.add(symbol)
        await db_session.flush()

        dim_day = DimDay(
            date=date(2025, 1, 1),
            day_of_week=1,
            week_of_year=1,
            month=1,
            year=2025,
            is_trading_day=1,
            created_at=datetime.utcnow(),
        )
        db_session.add(dim_day)
        await db_session.flush()

        trade = TradesFact(
            user_id=test_user.id,
            symbol_id=symbol.id,
            date_id=dim_day.id,
            side=0,
            entry_price=Decimal("1950"),
            exit_price=Decimal("1960"),
            volume=Decimal("1.0"),
            entry_time=datetime(2025, 1, 1, 10, 0),
            exit_time=datetime(2025, 1, 1, 14, 0),
            gross_pnl=Decimal("10"),
            fees=Decimal("1"),
            net_pnl=Decimal("9"),
            created_at=datetime.utcnow(),
        )
        db_session.add(trade)
        await db_session.commit()

        # Make multiple concurrent requests
        import asyncio
        tasks = [
            client.get("/api/v1/analytics/equity", headers=auth_headers)
            for _ in range(5)
        ]
        responses = await asyncio.gather(*tasks)

        # All should succeed with same data
        for response in responses:
            assert response.status_code == 200
            data = response.json()
            assert data["final_equity"] == 10009
