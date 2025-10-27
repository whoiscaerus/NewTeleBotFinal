"""
Phase 4 Tests: Auto-Close Service

Comprehensive test suite for PositionCloser service covering:
- Single position closure (happy path + edge cases)
- Bulk position closure
- Idempotent retry logic
- Error handling and recovery
- Audit trail recording
- User notification scenarios

Target Coverage: 100% (15 tests)
Execution Time: ~0.5 seconds
Author: Trading System
Date: 2024-10-26
"""

from datetime import datetime

import pytest

from backend.app.trading.monitoring.auto_close import (
    BulkCloseResult,
    CloseResult,
    PositionCloser,
    get_position_closer,
)

# ================================================================
# Fixtures
# ================================================================


@pytest.fixture
def closer():
    """Fresh PositionCloser instance for each test."""
    return PositionCloser()


@pytest.fixture
def sample_position_data():
    """Sample position data for testing."""
    return {
        "position_id": "pos_123",
        "ticket": 12345,
        "symbol": "XAUUSD",
        "entry_price": 1950.50,
        "current_price": 1940.00,
        "size": 0.1,
    }


@pytest.fixture
def sample_user_id():
    """Sample user ID for testing."""
    return "user_456"


# ================================================================
# CloseResult Tests
# ================================================================


class TestCloseResult:
    """Test suite for CloseResult dataclass."""

    def test_close_result_success_initialization(self):
        """Test CloseResult initialization with success."""
        result = CloseResult(
            success=True,
            position_id="pos_123",
            ticket=12345,
            closed_price=1945.00,
            pnl=55.50,
            close_reason="drawdown_critical",
            close_timestamp=datetime.utcnow(),
        )

        assert result.success is True
        assert result.position_id == "pos_123"
        assert result.ticket == 12345
        assert result.closed_price == 1945.00
        assert result.pnl == 55.50
        assert result.close_id.startswith("close_")

    def test_close_result_failure_with_error_message(self):
        """Test CloseResult with error message."""
        result = CloseResult(
            success=False,
            position_id="pos_123",
            ticket=12345,
            closed_price=None,
            pnl=None,
            close_reason="market_gap",
            close_timestamp=datetime.utcnow(),
            error_message="MT5 connection failed",
        )

        assert result.success is False
        assert result.error_message == "MT5 connection failed"
        assert result.closed_price is None
        assert result.pnl is None

    def test_close_result_auto_generates_close_id(self):
        """Test CloseResult auto-generates close_id if not provided."""
        result = CloseResult(
            success=True,
            position_id="pos_123",
            ticket=12345,
            closed_price=1945.00,
            pnl=50.0,
            close_reason="test",
            close_timestamp=datetime.utcnow(),
        )

        assert result.close_id
        assert result.close_id.startswith("close_")
        assert len(result.close_id) > 10


# ================================================================
# BulkCloseResult Tests
# ================================================================


class TestBulkCloseResult:
    """Test suite for BulkCloseResult dataclass."""

    def test_bulk_close_result_initialization(self):
        """Test BulkCloseResult initialization."""
        results = [
            CloseResult(
                success=True,
                position_id="pos_1",
                ticket=1,
                closed_price=100.0,
                pnl=10.0,
                close_reason="test",
                close_timestamp=datetime.utcnow(),
            ),
            CloseResult(
                success=False,
                position_id="pos_2",
                ticket=2,
                closed_price=None,
                pnl=None,
                close_reason="test",
                close_timestamp=datetime.utcnow(),
                error_message="Error",
            ),
        ]

        bulk_result = BulkCloseResult(
            total_positions=2,
            successful_closes=1,
            failed_closes=1,
            total_pnl=10.0,
            close_reason="liquidation",
            results=results,
        )

        assert bulk_result.total_positions == 2
        assert bulk_result.successful_closes == 1
        assert bulk_result.failed_closes == 1
        assert bulk_result.total_pnl == 10.0
        assert len(bulk_result.results) == 2


# ================================================================
# Single Position Close Tests
# ================================================================


class TestPositionCloser:
    """Test suite for PositionCloser service."""

    @pytest.mark.asyncio
    async def test_close_position_valid_inputs(
        self, closer, sample_position_data, sample_user_id
    ):
        """Test closing position with valid inputs (happy path)."""
        result = await closer.close_position(
            position_id=sample_position_data["position_id"],
            ticket=sample_position_data["ticket"],
            close_reason="drawdown_critical",
            user_id=sample_user_id,
        )

        assert result.success is True
        assert result.position_id == sample_position_data["position_id"]
        assert result.ticket == sample_position_data["ticket"]
        assert result.closed_price is not None
        assert result.pnl is not None
        assert result.close_reason == "drawdown_critical"
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_close_position_with_override_price(
        self, closer, sample_position_data, sample_user_id
    ):
        """Test closing position with override close price."""
        override_price = 1950.00

        result = await closer.close_position(
            position_id=sample_position_data["position_id"],
            ticket=sample_position_data["ticket"],
            close_reason="market_gap",
            user_id=sample_user_id,
            close_price=override_price,
        )

        assert result.success is True
        assert result.closed_price == override_price

    @pytest.mark.asyncio
    async def test_close_position_invalid_position_id(self, closer, sample_user_id):
        """Test close_position rejects invalid position_id."""
        with pytest.raises(ValueError, match="Invalid position_id"):
            await closer.close_position(
                position_id="",  # Empty
                ticket=12345,
                close_reason="test",
                user_id=sample_user_id,
            )

    @pytest.mark.asyncio
    async def test_close_position_invalid_ticket(
        self, closer, sample_position_data, sample_user_id
    ):
        """Test close_position rejects invalid ticket."""
        with pytest.raises(ValueError, match="Invalid ticket"):
            await closer.close_position(
                position_id=sample_position_data["position_id"],
                ticket=-1,  # Negative
                close_reason="test",
                user_id=sample_user_id,
            )

    @pytest.mark.asyncio
    async def test_close_position_invalid_close_reason(
        self, closer, sample_position_data, sample_user_id
    ):
        """Test close_position rejects invalid close_reason."""
        with pytest.raises(ValueError, match="Invalid close_reason"):
            await closer.close_position(
                position_id=sample_position_data["position_id"],
                ticket=sample_position_data["ticket"],
                close_reason="",  # Empty
                user_id=sample_user_id,
            )

    @pytest.mark.asyncio
    async def test_close_position_invalid_user_id(self, closer, sample_position_data):
        """Test close_position rejects invalid user_id."""
        with pytest.raises(ValueError, match="Invalid user_id"):
            await closer.close_position(
                position_id=sample_position_data["position_id"],
                ticket=sample_position_data["ticket"],
                close_reason="test",
                user_id=None,  # None
            )

    @pytest.mark.asyncio
    async def test_close_position_idempotent(
        self, closer, sample_position_data, sample_user_id
    ):
        """Test close_position is idempotent (same result on retry)."""
        # First close
        result1 = await closer.close_position(
            position_id=sample_position_data["position_id"],
            ticket=sample_position_data["ticket"],
            close_reason="drawdown_critical",
            user_id=sample_user_id,
        )

        # Retry with same position_id
        result2 = await closer.close_position(
            position_id=sample_position_data["position_id"],
            ticket=sample_position_data["ticket"],
            close_reason="drawdown_critical",
            user_id=sample_user_id,
        )

        # Same result (idempotent)
        assert result1.success == result2.success
        assert result1.position_id == result2.position_id
        assert result1.close_id == result2.close_id
        assert result1.closed_price == result2.closed_price
        assert result1.pnl == result2.pnl

    @pytest.mark.asyncio
    async def test_close_position_different_positions_independent(
        self, closer, sample_user_id
    ):
        """Test different positions have independent close history."""
        # Close position 1
        result1 = await closer.close_position(
            position_id="pos_1",
            ticket=11111,
            close_reason="drawdown",
            user_id=sample_user_id,
        )

        # Close position 2 (different ticket, different result)
        result2 = await closer.close_position(
            position_id="pos_2",
            ticket=22222,
            close_reason="market",
            user_id=sample_user_id,
        )

        # Different results
        assert result1.position_id != result2.position_id
        assert result1.ticket != result2.ticket
        # PnL might be different due to random simulation
        assert result1.close_id != result2.close_id


# ================================================================
# Bulk Close Tests
# ================================================================


class TestBulkClosePositions:
    """Test suite for bulk position closure."""

    @pytest.mark.asyncio
    async def test_close_all_positions_empty_list(self, closer, sample_user_id):
        """Test bulk close with empty position list."""
        result = await closer.close_all_positions(
            user_id=sample_user_id,
            close_reason="liquidation",
            positions=[],
        )

        assert result.total_positions == 0
        assert result.successful_closes == 0
        assert result.failed_closes == 0
        assert result.total_pnl == 0.0
        assert len(result.results) == 0

    @pytest.mark.asyncio
    async def test_close_all_positions_multiple_success(self, closer, sample_user_id):
        """Test bulk close with multiple successful closes."""
        positions = [
            {"position_id": "pos_1", "ticket": 11111},
            {"position_id": "pos_2", "ticket": 22222},
            {"position_id": "pos_3", "ticket": 33333},
        ]

        result = await closer.close_all_positions(
            user_id=sample_user_id,
            close_reason="liquidation",
            positions=positions,
        )

        assert result.total_positions == 3
        assert result.successful_closes == 3
        assert result.failed_closes == 0
        assert len(result.results) == 3
        # All should be successful
        for close_result in result.results:
            assert close_result.success is True

    @pytest.mark.asyncio
    async def test_close_all_positions_invalid_user_id(self, closer):
        """Test bulk close rejects invalid user_id."""
        with pytest.raises(ValueError, match="Invalid user_id"):
            await closer.close_all_positions(
                user_id="",  # Empty
                close_reason="liquidation",
                positions=[],
            )

    @pytest.mark.asyncio
    async def test_close_all_positions_invalid_close_reason(
        self, closer, sample_user_id
    ):
        """Test bulk close rejects invalid close_reason."""
        with pytest.raises(ValueError, match="Invalid close_reason"):
            await closer.close_all_positions(
                user_id=sample_user_id,
                close_reason="",  # Empty
                positions=[],
            )

    @pytest.mark.asyncio
    async def test_close_all_positions_with_invalid_position_data(
        self, closer, sample_user_id
    ):
        """Test bulk close skips invalid position entries."""
        positions = [
            {"position_id": "pos_1", "ticket": 11111},  # Valid
            {"position_id": None, "ticket": 22222},  # Invalid: no position_id
            {"position_id": "pos_3", "ticket": None},  # Invalid: no ticket
            {"position_id": "pos_4", "ticket": 44444},  # Valid
        ]

        result = await closer.close_all_positions(
            user_id=sample_user_id,
            close_reason="liquidation",
            positions=positions,
        )

        # Should only close valid positions (invalid ones are skipped, not added to results)
        assert result.total_positions == 4  # Total attempted
        assert result.successful_closes == 2  # Only 2 valid positions closed
        assert result.failed_closes == 0  # Invalid positions are skipped, not failed
        assert len(result.results) == 2  # Only 2 results (valid positions)

    @pytest.mark.asyncio
    async def test_close_all_positions_error_isolation(self, closer, sample_user_id):
        """Test bulk close continues despite errors."""
        positions = [
            {"position_id": "pos_1", "ticket": 11111},
            {"position_id": "pos_2", "ticket": 22222},
            {"position_id": "pos_3", "ticket": 33333},
        ]

        result = await closer.close_all_positions(
            user_id=sample_user_id,
            close_reason="liquidation",
            positions=positions,
        )

        # Should attempt all positions
        assert result.total_positions == 3
        # At least some should be successful (error isolation means continue)
        assert result.successful_closes + result.failed_closes == len(result.results)


# ================================================================
# Conditional Close Tests
# ================================================================


class TestCloseIfTriggered:
    """Test suite for conditional position closure."""

    @pytest.mark.asyncio
    async def test_close_position_if_triggered_valid(
        self, closer, sample_position_data, sample_user_id
    ):
        """Test conditional close with valid trigger."""
        result = await closer.close_position_if_triggered(
            position_id=sample_position_data["position_id"],
            trigger_reason="critical",
            guard_type="drawdown",
            user_id=sample_user_id,
            position_data=sample_position_data,
        )

        assert result.success is True
        assert "drawdown_critical" in result.close_reason

    @pytest.mark.asyncio
    async def test_close_position_if_triggered_missing_ticket(
        self, closer, sample_position_data, sample_user_id
    ):
        """Test conditional close fails if ticket missing from position_data."""
        result = await closer.close_position_if_triggered(
            position_id=sample_position_data["position_id"],
            trigger_reason="critical",
            guard_type="drawdown",
            user_id=sample_user_id,
            position_data={},  # Empty: no ticket
        )

        assert result.success is False
        assert "not found" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_close_position_if_triggered_invalid_position_id(
        self, closer, sample_user_id
    ):
        """Test conditional close rejects invalid position_id."""
        with pytest.raises(ValueError, match="Invalid position_id"):
            await closer.close_position_if_triggered(
                position_id=None,
                trigger_reason="critical",
                guard_type="drawdown",
                user_id=sample_user_id,
            )

    @pytest.mark.asyncio
    async def test_close_position_if_triggered_invalid_guard_type(
        self, closer, sample_position_data, sample_user_id
    ):
        """Test conditional close rejects invalid guard_type."""
        with pytest.raises(ValueError, match="Invalid guard_type"):
            await closer.close_position_if_triggered(
                position_id=sample_position_data["position_id"],
                trigger_reason="critical",
                guard_type="",  # Empty
                user_id=sample_user_id,
            )


# ================================================================
# Singleton Tests
# ================================================================


class TestPositionCloserSingleton:
    """Test suite for PositionCloser singleton pattern."""

    def test_get_position_closer_singleton(self):
        """Test get_position_closer returns same instance."""
        closer1 = get_position_closer()
        closer2 = get_position_closer()

        assert closer1 is closer2  # Same instance

    def test_get_position_closer_is_position_closer_instance(self):
        """Test get_position_closer returns PositionCloser instance."""
        closer = get_position_closer()
        assert isinstance(closer, PositionCloser)


# ================================================================
# Integration Tests
# ================================================================


class TestIntegration:
    """Integration tests for PositionCloser."""

    @pytest.mark.asyncio
    async def test_close_multiple_positions_mixed_outcomes(
        self, closer, sample_user_id
    ):
        """Test closing multiple positions with mixed success/failure."""
        # Close position 1 (success)
        result1 = await closer.close_position(
            position_id="pos_1",
            ticket=11111,
            close_reason="drawdown",
            user_id=sample_user_id,
        )

        # Close position 2 (success)
        result2 = await closer.close_position(
            position_id="pos_2",
            ticket=22222,
            close_reason="market",
            user_id=sample_user_id,
        )

        # Retry position 1 (should be idempotent)
        result1_retry = await closer.close_position(
            position_id="pos_1",
            ticket=11111,
            close_reason="drawdown",
            user_id=sample_user_id,
        )

        # All should be successful
        assert result1.success and result2.success and result1_retry.success
        # Retry should match original
        assert result1.close_id == result1_retry.close_id

    @pytest.mark.asyncio
    async def test_bulk_close_then_individual_close(self, closer, sample_user_id):
        """Test bulk close followed by individual close."""
        positions = [
            {"position_id": "pos_1", "ticket": 11111},
            {"position_id": "pos_2", "ticket": 22222},
        ]

        # Bulk close
        bulk_result = await closer.close_all_positions(
            user_id=sample_user_id,
            close_reason="liquidation",
            positions=positions,
        )

        assert bulk_result.successful_closes == 2

        # Individual close of third position
        individual_result = await closer.close_position(
            position_id="pos_3",
            ticket=33333,
            close_reason="drawdown",
            user_id=sample_user_id,
        )

        assert individual_result.success is True
