"""
PR-057: Comprehensive Tests for Export Service

Tests REAL business logic with REAL database operations:
- Export generation (CSV/JSON)
- PII redaction
- Share token creation/validation
- Token expiration
- Access limits
- Public share link access
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.models import User
from backend.app.exports.models import ExportToken
from backend.app.exports.service import ExportService
from backend.app.trading.store.models import Trade


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(id="test_user_id", email="test@example.com", password_hash="hashed")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def sample_trades(db_session: AsyncSession, test_user: User):
    """Create sample trades for testing."""
    trades = [
        Trade(
            user_id=test_user.id,
            symbol="XAUUSD",
            strategy="fib_rsi",
            timeframe="H1",
            trade_type="BUY",
            direction=0,
            volume=Decimal("1.0"),
            entry_price=Decimal("1950.00"),
            exit_price=Decimal("1960.00"),
            stop_loss=Decimal("1945.00"),
            take_profit=Decimal("1965.00"),
            profit=Decimal("100.00"),
            entry_time=datetime(2025, 11, 1, 10, 0, 0),
            exit_time=datetime(2025, 11, 1, 12, 0, 0),
            status="CLOSED",
        ),
        Trade(
            user_id=test_user.id,
            symbol="EURUSD",
            strategy="channel",
            timeframe="H1",
            trade_type="SELL",
            direction=1,
            volume=Decimal("2.0"),
            entry_price=Decimal("1.0850"),
            exit_price=Decimal("1.0830"),
            stop_loss=Decimal("1.0870"),
            take_profit=Decimal("1.0820"),
            profit=Decimal("40.00"),
            entry_time=datetime(2025, 11, 2, 14, 0, 0),
            exit_time=datetime(2025, 11, 2, 16, 0, 0),
            status="CLOSED",
        ),
        Trade(
            user_id=test_user.id,
            symbol="GBPUSD",
            strategy="fib_rsi",
            timeframe="H4",
            trade_type="BUY",
            direction=0,
            volume=Decimal("1.5"),
            entry_price=Decimal("1.2650"),
            exit_price=None,  # still open
            stop_loss=Decimal("1.2600"),
            take_profit=Decimal("1.2700"),
            profit=None,
            entry_time=datetime(2025, 11, 3, 9, 0, 0),
            exit_time=None,
            status="OPEN",
        ),
    ]

    for trade in trades:
        db_session.add(trade)

    await db_session.commit()

    return trades


@pytest.mark.asyncio
class TestExportGeneration:
    """Test export generation with real data."""

    async def test_generate_csv_export_no_redaction(
        self, db_session: AsyncSession, test_user: User, sample_trades
    ):
        """Test CSV export generation without PII redaction."""
        service = ExportService(db_session)

        result = await service.generate_export(
            user_id=test_user.id, format="csv", redact_pii=False
        )

        # Verify export structure
        assert result["format"] == "csv"
        assert result["trade_count"] == 3
        assert result["redacted"] is False
        assert isinstance(result["data"], str)

        # Verify CSV content includes all trades
        csv_lines = result["data"].strip().split("\n")
        assert len(csv_lines) == 4  # header + 3 trades

        # Verify header
        assert "trade_id" in csv_lines[0]
        assert "symbol" in csv_lines[0]
        assert "profit" in csv_lines[0]

        # Verify trade data present (trade_id is UUID, check symbol/profit instead)
        assert "XAUUSD" in result["data"]
        assert "100.0" in result["data"]

    async def test_generate_json_export_no_redaction(
        self, db_session: AsyncSession, test_user: User, sample_trades
    ):
        """Test JSON export generation without PII redaction."""
        service = ExportService(db_session)

        result = await service.generate_export(
            user_id=test_user.id, format="json", redact_pii=False
        )

        # Verify export structure
        assert result["format"] == "json"
        assert result["trade_count"] == 3
        assert result["redacted"] is False
        assert isinstance(result["data"], dict)

        # Verify JSON structure
        data = result["data"]
        assert "export_date" in data
        assert "trade_count" in data
        assert data["trade_count"] == 3
        assert "trades" in data
        assert len(data["trades"]) == 3

        # Verify trade data
        first_trade = data["trades"][0]
        # trade_id is UUID, check it exists
        assert "trade_id" in first_trade
        assert first_trade["symbol"] == "GBPUSD"  # newest trade (desc order)
        assert first_trade["trade_type"] == "BUY"
        assert first_trade["volume"] == 1.5

    async def test_generate_export_with_pii_redaction(
        self, db_session: AsyncSession, test_user: User, sample_trades
    ):
        """Test export with PII redaction."""
        service = ExportService(db_session)

        result = await service.generate_export(
            user_id=test_user.id, format="json", redact_pii=True
        )

        # Verify redaction flag
        assert result["redacted"] is True

        # Verify PII redacted
        data = result["data"]
        trades = data["trades"]

        # Trade IDs should be redacted
        assert trades[0]["trade_id"] == "TRADE_1"
        assert trades[1]["trade_id"] == "TRADE_2"
        assert trades[2]["trade_id"] == "TRADE_3"

        # user_id should not be present
        for trade in trades:
            assert "user_id" not in trade
            # broker_ticket should not be present if it existed
            assert "broker_ticket" not in trade

    async def test_generate_export_invalid_format(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test export generation rejects invalid format."""
        service = ExportService(db_session)

        with pytest.raises(ValueError, match="Invalid format"):
            await service.generate_export(
                user_id=test_user.id, format="xml", redact_pii=False  # invalid
            )

    async def test_generate_export_no_trades(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test export generation with no trades."""
        service = ExportService(db_session)

        with pytest.raises(ValueError, match="No trades found"):
            await service.generate_export(
                user_id=test_user.id, format="csv", redact_pii=False
            )


@pytest.mark.asyncio
class TestShareTokenManagement:
    """Test share token creation and validation."""

    async def test_create_share_token_defaults(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test share token creation with default settings."""
        service = ExportService(db_session)

        token = await service.create_share_token(user_id=test_user.id, format="csv")

        # Verify token structure
        assert token.user_id == test_user.id
        assert token.format == "csv"
        assert len(token.token) > 20  # secure token
        assert token.max_accesses == 1  # single-use default
        assert token.accessed_count == 0
        assert token.revoked is False

        # Verify expiration (24 hours default)
        time_diff = (token.expires_at - datetime.utcnow()).total_seconds()
        assert 23.9 * 3600 < time_diff < 24.1 * 3600  # ~24 hours

    async def test_create_share_token_custom_expiry(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test share token with custom expiration."""
        service = ExportService(db_session)

        token = await service.create_share_token(
            user_id=test_user.id, format="json", expires_in_hours=48
        )

        # Verify 48-hour expiration
        time_diff = (token.expires_at - datetime.utcnow()).total_seconds()
        assert 47.9 * 3600 < time_diff < 48.1 * 3600  # ~48 hours

    async def test_create_share_token_custom_max_accesses(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test share token with multiple access limit."""
        service = ExportService(db_session)

        token = await service.create_share_token(
            user_id=test_user.id, format="csv", max_accesses=5
        )

        assert token.max_accesses == 5
        assert token.accessed_count == 0

    async def test_token_is_valid_fresh_token(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test is_valid() for fresh token."""
        service = ExportService(db_session)

        token = await service.create_share_token(user_id=test_user.id, format="csv")

        assert token.is_valid() is True

    async def test_token_is_valid_revoked(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test is_valid() for revoked token."""
        service = ExportService(db_session)

        token = await service.create_share_token(user_id=test_user.id, format="csv")

        # Revoke token
        token.revoked = True

        assert token.is_valid() is False

    async def test_token_is_valid_expired(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test is_valid() for expired token."""
        token = ExportToken(
            id="test_token_id",
            user_id=test_user.id,
            token="test_token",
            format="csv",
            expires_at=datetime.utcnow() - timedelta(hours=1),  # expired 1 hour ago
            max_accesses=1,
            accessed_count=0,
            revoked=False,
        )

        db_session.add(token)
        await db_session.commit()

        assert token.is_valid() is False

    async def test_token_is_valid_max_accesses_reached(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test is_valid() for token with max accesses reached."""
        token = ExportToken(
            id="test_token_id",
            user_id=test_user.id,
            token="test_token",
            format="csv",
            expires_at=datetime.utcnow() + timedelta(hours=24),
            max_accesses=3,
            accessed_count=3,  # max reached
            revoked=False,
        )

        db_session.add(token)
        await db_session.commit()

        assert token.is_valid() is False


@pytest.mark.asyncio
class TestTokenAccess:
    """Test token access tracking."""

    async def test_mark_token_accessed(self, db_session: AsyncSession, test_user: User):
        """Test marking token as accessed."""
        service = ExportService(db_session)

        token = await service.create_share_token(
            user_id=test_user.id, format="csv", max_accesses=3
        )

        assert token.accessed_count == 0
        assert token.last_accessed_at is None

        # Mark accessed
        await service.mark_token_accessed(token)

        assert token.accessed_count == 1
        assert token.last_accessed_at is not None
        assert token.is_valid() is True  # still valid (1/3)

        # Mark accessed again
        await service.mark_token_accessed(token)

        assert token.accessed_count == 2
        assert token.is_valid() is True  # still valid (2/3)

        # Mark accessed third time
        await service.mark_token_accessed(token)

        assert token.accessed_count == 3
        assert token.is_valid() is False  # max reached (3/3)

    async def test_get_token_by_value(self, db_session: AsyncSession, test_user: User):
        """Test retrieving token by value."""
        service = ExportService(db_session)

        created_token = await service.create_share_token(
            user_id=test_user.id, format="csv"
        )

        # Retrieve by value
        retrieved_token = await service.get_token_by_value(created_token.token)

        assert retrieved_token is not None
        assert retrieved_token.id == created_token.id
        assert retrieved_token.token == created_token.token

    async def test_get_token_by_value_not_found(self, db_session: AsyncSession):
        """Test retrieving non-existent token."""
        service = ExportService(db_session)

        token = await service.get_token_by_value("nonexistent_token")

        assert token is None

    async def test_revoke_token(self, db_session: AsyncSession, test_user: User):
        """Test revoking a token."""
        service = ExportService(db_session)

        token = await service.create_share_token(user_id=test_user.id, format="csv")

        assert token.revoked is False
        assert token.is_valid() is True

        # Revoke token
        await service.revoke_token(token)

        assert token.revoked is True
        assert token.is_valid() is False


@pytest.mark.asyncio
class TestEndToEndShareFlow:
    """Test complete share link workflow."""

    async def test_complete_share_workflow(
        self, db_session: AsyncSession, test_user: User, sample_trades
    ):
        """Test complete workflow: create token → access → validate."""
        service = ExportService(db_session)

        # Step 1: Create share token
        token = await service.create_share_token(
            user_id=test_user.id, format="json", expires_in_hours=24, max_accesses=1
        )

        assert token.is_valid() is True

        # Step 2: Access export via token
        export_data = await service.generate_export(
            user_id=token.user_id, format=token.format, redact_pii=True
        )

        assert export_data["redacted"] is True
        assert export_data["trade_count"] == 3

        # Step 3: Mark token accessed
        await service.mark_token_accessed(token)

        # Step 4: Verify token now invalid (single-use)
        assert token.is_valid() is False
        assert token.accessed_count == 1

    async def test_share_workflow_multiple_accesses(
        self, db_session: AsyncSession, test_user: User, sample_trades
    ):
        """Test share workflow with multiple allowed accesses."""
        service = ExportService(db_session)

        # Create token with 3 allowed accesses
        token = await service.create_share_token(
            user_id=test_user.id, format="csv", max_accesses=3
        )

        # Access 1
        await service.mark_token_accessed(token)
        assert token.is_valid() is True

        # Access 2
        await service.mark_token_accessed(token)
        assert token.is_valid() is True

        # Access 3
        await service.mark_token_accessed(token)
        assert token.is_valid() is False  # max reached
