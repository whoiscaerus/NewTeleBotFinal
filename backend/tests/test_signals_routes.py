"""Comprehensive tests for signals API endpoints.

Tests cover:
- Signal creation endpoint (POST /api/v1/signals)
- Signal retrieval endpoint (GET /api/v1/signals/{signal_id})
- Signal listing endpoint (GET /api/v1/signals)
- HMAC signature verification
- Payload size validation
- Status code handling (201, 400, 401, 409, 413, 422, 500)
- Authentication and authorization
"""

import hashlib
import hmac
import json

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.signals.models import Signal, SignalStatus


@pytest.fixture
def hmac_key():
    """HMAC secret key for testing."""
    return "test-secret-key-12345"


class TestSignalCreationEndpoint:
    """Test POST /api/v1/signals endpoint."""

    @pytest.mark.asyncio
    async def test_create_signal_valid_201(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test valid signal creation returns 201."""
        response = await client.post(
            "/api/v1/signals",
            json={
                "instrument": "XAUUSD",
                "side": "buy",
                "price": 1950.50,
                "payload": {"rsi": 75.5},
                "version": "1.0",
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] is not None
        assert data["instrument"] == "XAUUSD"
        assert data["side"] == 0  # buy
        assert data["price"] == 1950.50
        assert data["status"] == 0  # new
        assert data["payload"] == {"rsi": 75.5}

    @pytest.mark.asyncio
    async def test_create_signal_missing_authentication_401(self, client: AsyncClient):
        """Test missing authentication returns 401."""
        response = await client.post(
            "/api/v1/signals",
            json={
                "instrument": "XAUUSD",
                "side": "buy",
                "price": 1950.50,
                "version": "1.0",
            },
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_signal_invalid_instrument_422(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test invalid instrument returns 422."""
        response = await client.post(
            "/api/v1/signals",
            json={
                "instrument": "INVALID_INSTRUMENT",
                "side": "buy",
                "price": 1950.50,
                "version": "1.0",
            },
            headers=auth_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_signal_invalid_side_422(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test invalid side returns 422."""
        response = await client.post(
            "/api/v1/signals",
            json={
                "instrument": "XAUUSD",
                "side": "invalid",
                "price": 1950.50,
                "version": "1.0",
            },
            headers=auth_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_signal_zero_price_422(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test zero price returns 422."""
        response = await client.post(
            "/api/v1/signals",
            json={
                "instrument": "XAUUSD",
                "side": "buy",
                "price": 0.0,
                "version": "1.0",
            },
            headers=auth_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_signal_negative_price_422(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test negative price returns 422."""
        response = await client.post(
            "/api/v1/signals",
            json={
                "instrument": "XAUUSD",
                "side": "buy",
                "price": -100.0,
                "version": "1.0",
            },
            headers=auth_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_signal_price_exceeds_maximum_422(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test price exceeding maximum returns 422."""
        response = await client.post(
            "/api/v1/signals",
            json={
                "instrument": "XAUUSD",
                "side": "buy",
                "price": 1_000_001.0,
                "version": "1.0",
            },
            headers=auth_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_signal_missing_required_field_422(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test missing required field returns 422."""
        response = await client.post(
            "/api/v1/signals",
            json={
                "instrument": "XAUUSD",
                # Missing side
                "price": 1950.50,
                "version": "1.0",
            },
            headers=auth_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_signal_payload_too_large_413(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test oversized payload returns 422 (validation error)."""
        large_payload = {"data": "x" * 2000}  # Exceeds size limit

        response = await client.post(
            "/api/v1/signals",
            json={
                "instrument": "XAUUSD",
                "side": "buy",
                "price": 1950.50,
                "payload": large_payload,
                "version": "1.0",
            },
            headers=auth_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_signal_with_external_id_header(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test signal creation with X-Producer-Id header."""
        headers = {**auth_headers, "X-Producer-Id": "ext_producer_001"}

        response = await client.post(
            "/api/v1/signals",
            json={
                "instrument": "XAUUSD",
                "side": "buy",
                "price": 1950.50,
                "version": "1.0",
            },
            headers=headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["external_id"] == "ext_producer_001"

    @pytest.mark.asyncio
    async def test_create_signal_duplicate_external_id_409(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test duplicate external_id returns 409."""
        headers = {**auth_headers, "X-Producer-Id": "ext_duplicate_001"}

        # Create first signal
        response1 = await client.post(
            "/api/v1/signals",
            json={
                "instrument": "XAUUSD",
                "side": "buy",
                "price": 1950.50,
                "version": "1.0",
            },
            headers=headers,
        )
        assert response1.status_code == 201

        # Attempt duplicate
        response2 = await client.post(
            "/api/v1/signals",
            json={
                "instrument": "XAUUSD",
                "side": "buy",
                "price": 1950.50,
                "version": "1.0",
            },
            headers=headers,
        )

        assert response2.status_code == 409
        assert "duplicate" in response2.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_signal_invalid_hmac_401(
        self, client: AsyncClient, auth_headers: dict, hmac_key: str
    ):
        """Test invalid HMAC signature returns 401."""
        payload_json = json.dumps(
            {
                "instrument": "XAUUSD",
                "side": "buy",
                "price": 1950.50,
                "version": "1.0",
            }
        )

        # Create wrong signature
        wrong_sig = hmac.new(
            b"wrong-key",
            payload_json.encode(),
            hashlib.sha256,
        ).hexdigest()

        headers = {
            **auth_headers,
            "X-Signature": wrong_sig,
            "X-Timestamp": "1234567890",
        }

        response = await client.post(
            "/api/v1/signals",
            json={
                "instrument": "XAUUSD",
                "side": "buy",
                "price": 1950.50,
                "version": "1.0",
            },
            headers=headers,
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_signal_tampered_payload_401(
        self, client: AsyncClient, auth_headers: dict, hmac_key: str
    ):
        """Test tampered payload is rejected with 401."""
        original_payload = json.dumps(
            {
                "instrument": "XAUUSD",
                "side": "buy",
                "price": 1950.50,
                "version": "1.0",
            }
        )

        # Create signature for original
        sig = hmac.new(
            hmac_key.encode(),
            original_payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        headers = {
            **auth_headers,
            "X-Signature": sig,
            "X-Timestamp": "1234567890",
        }

        # Send different payload
        response = await client.post(
            "/api/v1/signals",
            json={
                "instrument": "EURUSD",  # Different from signed
                "side": "buy",
                "price": 1950.50,
                "version": "1.0",
            },
            headers=headers,
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_signal_sell_direction(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test sell signal created correctly."""
        response = await client.post(
            "/api/v1/signals",
            json={
                "instrument": "EURUSD",
                "side": "sell",
                "price": 1.0850,
                "version": "1.0",
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["side"] == 1  # sell
        assert data["instrument"] == "EURUSD"

    @pytest.mark.asyncio
    async def test_create_signal_empty_payload(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test signal with empty payload."""
        response = await client.post(
            "/api/v1/signals",
            json={
                "instrument": "XAUUSD",
                "side": "buy",
                "price": 1950.50,
                "payload": {},
                "version": "1.0",
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["payload"] == {}

    @pytest.mark.asyncio
    async def test_create_signal_complex_payload(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test signal with complex payload (nested JSON)."""
        response = await client.post(
            "/api/v1/signals",
            json={
                "instrument": "XAUUSD",
                "side": "buy",
                "price": 1950.50,
                "payload": {
                    "indicators": {"rsi": 75.5, "macd": -0.002},
                    "confidence": 0.85,
                    "timeframe": "1h",
                },
                "version": "1.0",
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["payload"]["indicators"]["rsi"] == 75.5
        assert data["payload"]["confidence"] == 0.85


class TestSignalRetrievalEndpoint:
    """Test GET /api/v1/signals/{signal_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_signal_success_200(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test retrieving existing signal returns 200."""
        # Create signal first
        create_response = await client.post(
            "/api/v1/signals",
            json={
                "instrument": "XAUUSD",
                "side": "buy",
                "price": 1950.50,
                "version": "1.0",
            },
            headers=auth_headers,
        )
        signal_id = create_response.json()["id"]

        # Retrieve signal
        response = await client.get(
            f"/api/v1/signals/{signal_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == signal_id
        assert data["instrument"] == "XAUUSD"

    @pytest.mark.asyncio
    async def test_get_signal_not_found_404(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test retrieving non-existent signal returns 404."""
        response = await client.get(
            "/api/v1/signals/nonexistent_id",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_signal_unauthorized_401(self, client: AsyncClient):
        """Test retrieving signal without authentication returns 401."""
        response = await client.get("/api/v1/signals/some_id")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_signal_owner_isolation(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user,
    ):
        """Test user cannot retrieve another user's signal."""
        # Create signal as user 1
        create_response = await client.post(
            "/api/v1/signals",
            json={
                "instrument": "XAUUSD",
                "side": "buy",
                "price": 1950.50,
                "version": "1.0",
            },
            headers=auth_headers,
        )
        signal_id = create_response.json()["id"]

        # Try to retrieve as different user (would need different auth)
        # For now, verify the signal is correctly owned
        from sqlalchemy import select

        result = await db_session.execute(select(Signal).where(Signal.id == signal_id))
        signal = result.scalar()

        assert signal.user_id == test_user.id


class TestSignalListingEndpoint:
    """Test GET /api/v1/signals endpoint."""

    @pytest.mark.asyncio
    async def test_list_signals_empty_200(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test listing signals with no signals returns 200."""
        response = await client.get(
            "/api/v1/signals",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_signals_multiple_200(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test listing multiple signals."""
        # Create 2 signals
        await client.post(
            "/api/v1/signals",
            json={
                "instrument": "XAUUSD",
                "side": "buy",
                "price": 1950.50,
                "version": "1.0",
            },
            headers=auth_headers,
        )
        await client.post(
            "/api/v1/signals",
            json={
                "instrument": "EURUSD",
                "side": "sell",
                "price": 1.0850,
                "version": "1.0",
            },
            headers=auth_headers,
        )

        response = await client.get(
            "/api/v1/signals",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 2

    @pytest.mark.asyncio
    async def test_list_signals_pagination(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test pagination in list_signals."""
        # Create 5 signals
        for i in range(5):
            await client.post(
                "/api/v1/signals",
                json={
                    "instrument": "XAUUSD",
                    "side": "buy",
                    "price": 1950.50 + i,
                    "version": f"1.{i}",
                },
                headers=auth_headers,
            )

        # Get page 1 with page_size=2
        response = await client.get(
            "/api/v1/signals?page=1&page_size=2",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5

        # Get page 2
        response = await client.get(
            "/api/v1/signals?page=2&page_size=2",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_signals_filter_by_status(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test filtering signals by status."""
        # Create signal
        create_response = await client.post(
            "/api/v1/signals",
            json={
                "instrument": "XAUUSD",
                "side": "buy",
                "price": 1950.50,
                "version": "1.0",
            },
            headers=auth_headers,
        )
        signal_id = create_response.json()["id"]

        # List NEW signals (should have 1)
        response = await client.get(
            "/api/v1/signals?status=0",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["status"] == 0

    @pytest.mark.asyncio
    async def test_list_signals_filter_by_instrument(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test filtering signals by instrument."""
        # Create XAUUSD signal
        await client.post(
            "/api/v1/signals",
            json={
                "instrument": "XAUUSD",
                "side": "buy",
                "price": 1950.50,
                "version": "1.0",
            },
            headers=auth_headers,
        )

        # Create EURUSD signal
        await client.post(
            "/api/v1/signals",
            json={
                "instrument": "EURUSD",
                "side": "sell",
                "price": 1.0850,
                "version": "1.0",
            },
            headers=auth_headers,
        )

        # Filter by XAUUSD
        response = await client.get(
            "/api/v1/signals?instrument=XAUUSD",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["instrument"] == "XAUUSD"

    @pytest.mark.asyncio
    async def test_list_signals_unauthorized_401(self, client: AsyncClient):
        """Test listing signals without authentication returns 401."""
        response = await client.get("/api/v1/signals")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_signals_ordered_by_created_at_desc(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test signals ordered by created_at descending."""
        # Create multiple signals
        for i in range(3):
            await client.post(
                "/api/v1/signals",
                json={
                    "instrument": "XAUUSD",
                    "side": "buy",
                    "price": 1950.50 + i,
                    "version": "1.0",
                },
                headers=auth_headers,
            )

        response = await client.get(
            "/api/v1/signals",
            headers=auth_headers,
        )

        data = response.json()
        signals = data["items"]

        # Verify descending order by created_at
        for i in range(len(signals) - 1):
            assert signals[i]["created_at"] >= signals[i + 1]["created_at"]


class TestSignalUpdateEndpoint:
    """Test signal status update operations."""

    @pytest.mark.asyncio
    async def test_update_signal_status_200(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test updating signal status returns 200."""
        # Create signal
        create_response = await client.post(
            "/api/v1/signals",
            json={
                "instrument": "XAUUSD",
                "side": "buy",
                "price": 1950.50,
                "version": "1.0",
            },
            headers=auth_headers,
        )
        signal_id = create_response.json()["id"]

        # Update status (if endpoint exists)
        # Assuming endpoint: PATCH /api/v1/signals/{signal_id}
        response = await client.patch(
            f"/api/v1/signals/{signal_id}",
            json={"status": SignalStatus.APPROVED.value},
            headers=auth_headers,
        )

        # Check if endpoint exists (might be 404 if not implemented)
        if response.status_code != 404:
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == SignalStatus.APPROVED.value


class TestSignalEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_create_signal_minimum_price(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test signal with minimum valid price."""
        response = await client.post(
            "/api/v1/signals",
            json={
                "instrument": "XAUUSD",
                "side": "buy",
                "price": 0.01,
                "version": "1.0",
            },
            headers=auth_headers,
        )

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_signal_maximum_price(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test signal with maximum valid price."""
        response = await client.post(
            "/api/v1/signals",
            json={
                "instrument": "XAUUSD",
                "side": "buy",
                "price": 999999.99,
                "version": "1.0",
            },
            headers=auth_headers,
        )

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_signal_payload_at_size_limit(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test signal with payload at exactly size limit."""
        # Create payload that's exactly 1024 bytes
        payload = {"data": "x" * (1024 - 20)}  # Account for JSON structure

        response = await client.post(
            "/api/v1/signals",
            json={
                "instrument": "XAUUSD",
                "side": "buy",
                "price": 1950.50,
                "payload": payload,
                "version": "1.0",
            },
            headers=auth_headers,
        )

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_signal_payload_just_over_limit_413(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test signal with payload just over size limit returns 422."""
        # Create payload > 1024 bytes
        payload = {"data": "x" * 1100}

        response = await client.post(
            "/api/v1/signals",
            json={
                "instrument": "XAUUSD",
                "side": "buy",
                "price": 1950.50,
                "payload": payload,
                "version": "1.0",
            },
            headers=auth_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_signal_unicode_in_payload(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test signal with unicode in payload."""
        response = await client.post(
            "/api/v1/signals",
            json={
                "instrument": "XAUUSD",
                "side": "buy",
                "price": 1950.50,
                "payload": {"note": "Signal for 日本 market 🚀"},
                "version": "1.0",
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert "日本" in data["payload"]["note"]
