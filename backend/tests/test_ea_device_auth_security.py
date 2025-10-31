"""
Security tests for EA device authentication (PR-041).

Tests cover:
- Timestamp freshness validation (stale/future timestamps)
- Nonce replay detection and prevention
- HMAC signature validation
- Tampering detection (header modifications)
- Error handling and edge cases

Target Coverage: ≥15 test cases for 90%+ backend coverage on auth module
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.devices.models import Device
from backend.app.clients.models import Client
from backend.app.ea.hmac import HMACBuilder


class TestTimestampFreshness:
    """Test timestamp freshness validation (±5 min window)."""

    @pytest.mark.asyncio
    async def test_poll_accepts_fresh_timestamp(
        self, real_auth_client: AsyncClient, device: Device, db_session: AsyncSession
    ):
        """Fresh timestamp (now) should be accepted."""
        now = datetime.utcnow().isoformat() + "Z"
        nonce = "nonce_fresh_001"
        canonical = HMACBuilder.build_canonical_string(
            "GET", "/api/v1/client/poll", "", device.id, nonce, now
        )
        signature = HMACBuilder.sign(canonical, device.hmac_key_hash.encode())

        response = await real_auth_client.get(
            "/api/v1/client/poll",
            headers={
                "X-Device-Id": device.id,
                "X-Nonce": nonce,
                "X-Timestamp": now,
                "X-Signature": signature,
            },
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_poll_rejects_stale_timestamp(
        self, real_auth_client: AsyncClient, device: Device, db_session: AsyncSession
    ):
        """Timestamp older than 5 minutes should be rejected (400)."""
        stale_time = (datetime.utcnow() - timedelta(minutes=6)).isoformat() + "Z"
        nonce = "nonce_stale_001"
        canonical = HMACBuilder.build_canonical_string(
            "GET", "/api/v1/client/poll", "", device.id, nonce, stale_time
        )
        signature = HMACBuilder.sign(canonical, device.hmac_key_hash.encode())

        response = await real_auth_client.get(
            "/api/v1/client/poll",
            headers={
                "X-Device-Id": device.id,
                "X-Nonce": nonce,
                "X-Timestamp": stale_time,
                "X-Signature": signature,
            },
        )

        assert response.status_code == 400
        assert "timestamp" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_poll_rejects_future_timestamp(
        self, real_auth_client: AsyncClient, device: Device, db_session: AsyncSession
    ):
        """Timestamp in future (>5 min ahead) should be rejected (400)."""
        future_time = (datetime.utcnow() + timedelta(minutes=6)).isoformat() + "Z"
        nonce = "nonce_future_001"
        canonical = HMACBuilder.build_canonical_string(
            "GET", "/api/v1/client/poll", "", device.id, nonce, future_time
        )
        signature = HMACBuilder.sign(canonical, device.hmac_key_hash.encode())

        response = await real_auth_client.get(
            "/api/v1/client/poll",
            headers={
                "X-Device-Id": device.id,
                "X-Nonce": nonce,
                "X-Timestamp": future_time,
                "X-Signature": signature,
            },
        )

        assert response.status_code == 400
        assert "timestamp" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_poll_rejects_malformed_timestamp(
        self, real_auth_client: AsyncClient, device: Device, db_session: AsyncSession
    ):
        """Malformed timestamp should be rejected (400)."""
        bad_timestamp = "not-a-timestamp"
        nonce = "nonce_malformed_001"
        signature = "fake_signature"

        response = await real_auth_client.get(
            "/api/v1/client/poll",
            headers={
                "X-Device-Id": device.id,
                "X-Nonce": nonce,
                "X-Timestamp": bad_timestamp,
                "X-Signature": signature,
            },
        )

        assert response.status_code == 400
        assert "timestamp" in response.json()["detail"].lower()


class TestNonceReplayDetection:
    """Test nonce replay prevention (Redis tracking)."""

    @pytest.mark.asyncio
    async def test_poll_accepts_unique_nonce(self, client: AsyncClient, device: Device):
        """Unique nonce should be accepted."""
        now = datetime.utcnow().isoformat() + "Z"
        unique_nonce = f"nonce_unique_{uuid4().hex[:8]}"
        canonical = HMACBuilder.build_canonical_string(
            "GET", "/api/v1/client/poll", "", device.id, unique_nonce, now
        )
        signature = HMACBuilder.sign(canonical, device.hmac_key_hash.encode())

        response = await client.get(
            "/api/v1/client/poll",
            headers={
                "X-Device-Id": device.id,
                "X-Nonce": unique_nonce,
                "X-Timestamp": now,
                "X-Signature": signature,
            },
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_poll_rejects_replayed_nonce(
        self, client: AsyncClient, device: Device
    ):
        """Reused nonce should be rejected (401)."""
        now = datetime.utcnow().isoformat() + "Z"
        replay_nonce = "nonce_replay_test_001"
        canonical = HMACBuilder.build_canonical_string(
            "GET", "/api/v1/client/poll", "", device.id, replay_nonce, now
        )
        signature = HMACBuilder.sign(canonical, device.hmac_key_hash.encode())

        headers = {
            "X-Device-Id": device.id,
            "X-Nonce": replay_nonce,
            "X-Timestamp": now,
            "X-Signature": signature,
        }

        # First request succeeds
        response1 = await client.get("/api/v1/client/poll", headers=headers)
        assert response1.status_code == 200

        # Second request with same nonce fails
        response2 = await client.get("/api/v1/client/poll", headers=headers)
        assert response2.status_code == 401
        assert "replay" in response2.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_poll_rejects_empty_nonce(self, client: AsyncClient, device: Device):
        """Empty nonce should be rejected (400)."""
        now = datetime.utcnow().isoformat() + "Z"
        signature = "fake_signature"

        response = await client.get(
            "/api/v1/client/poll",
            headers={
                "X-Device-Id": device.id,
                "X-Nonce": "",
                "X-Timestamp": now,
                "X-Signature": signature,
            },
        )

        assert response.status_code == 400


class TestSignatureValidation:
    """Test HMAC signature validation."""

    @pytest.mark.asyncio
    async def test_poll_accepts_valid_signature(
        self, client: AsyncClient, device: Device
    ):
        """Valid HMAC signature should be accepted."""
        now = datetime.utcnow().isoformat() + "Z"
        nonce = f"nonce_valid_{uuid4().hex[:8]}"
        canonical = HMACBuilder.build_canonical_string(
            "GET", "/api/v1/client/poll", "", device.id, nonce, now
        )
        signature = HMACBuilder.sign(canonical, device.hmac_key_hash.encode())

        response = await client.get(
            "/api/v1/client/poll",
            headers={
                "X-Device-Id": device.id,
                "X-Nonce": nonce,
                "X-Timestamp": now,
                "X-Signature": signature,
            },
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_poll_rejects_invalid_signature(
        self, client: AsyncClient, device: Device
    ):
        """Invalid signature should be rejected (401)."""
        now = datetime.utcnow().isoformat() + "Z"
        nonce = f"nonce_invalid_{uuid4().hex[:8]}"

        response = await client.get(
            "/api/v1/client/poll",
            headers={
                "X-Device-Id": device.id,
                "X-Nonce": nonce,
                "X-Timestamp": now,
                "X-Signature": "invalid_base64_signature_1234567890",
            },
        )

        assert response.status_code == 401
        assert "signature" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_poll_rejects_tampered_signature(
        self, client: AsyncClient, device: Device
    ):
        """Tampered signature (modified by 1 char) should be rejected (401)."""
        now = datetime.utcnow().isoformat() + "Z"
        nonce = f"nonce_tampered_{uuid4().hex[:8]}"
        canonical = HMACBuilder.build_canonical_string(
            "GET", "/api/v1/client/poll", "", device.id, nonce, now
        )
        signature = HMACBuilder.sign(canonical, device.hmac_key_hash.encode())

        # Tamper with signature: change first character
        tampered = (
            ("X" if signature[0] != "X" else "Y") + signature[1:]
            if len(signature) > 0
            else "tampered"
        )

        response = await client.get(
            "/api/v1/client/poll",
            headers={
                "X-Device-Id": device.id,
                "X-Nonce": nonce,
                "X-Timestamp": now,
                "X-Signature": tampered,
            },
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_poll_rejects_signature_for_wrong_method(
        self, client: AsyncClient, device: Device
    ):
        """Signature generated for POST should fail for GET (401)."""
        now = datetime.utcnow().isoformat() + "Z"
        nonce = f"nonce_method_{uuid4().hex[:8]}"

        # Sign for POST
        canonical = HMACBuilder.build_canonical_string(
            "POST", "/api/v1/client/poll", "", device.id, nonce, now
        )
        signature = HMACBuilder.sign(canonical, device.hmac_key_hash.encode())

        # Use for GET (wrong method)
        response = await client.get(
            "/api/v1/client/poll",
            headers={
                "X-Device-Id": device.id,
                "X-Nonce": nonce,
                "X-Timestamp": now,
                "X-Signature": signature,
            },
        )

        assert response.status_code == 401


class TestCanonicalStringConstruction:
    """Test canonical string format and format validation."""

    def test_canonical_format_correct(self):
        """Canonical string should be METHOD|PATH|BODY|DEVICE_ID|NONCE|TIMESTAMP."""
        canonical = HMACBuilder.build_canonical_string(
            method="GET",
            path="/api/v1/client/poll",
            body="",
            device_id="dev_123",
            nonce="nonce_abc",
            timestamp="2025-10-26T10:30:45Z",
        )

        expected = "GET|/api/v1/client/poll||dev_123|nonce_abc|2025-10-26T10:30:45Z"
        assert canonical == expected

    def test_canonical_format_with_body(self):
        """Canonical string with body should include body content."""
        body = (
            '{"approval_id":"550e8400-e29b-41d4-a716-446655440000","status":"placed"}'
        )
        canonical = HMACBuilder.build_canonical_string(
            method="POST",
            path="/api/v1/client/ack",
            body=body,
            device_id="dev_123",
            nonce="nonce_abc",
            timestamp="2025-10-26T10:30:45Z",
        )

        expected = (
            f"POST|/api/v1/client/ack|{body}|dev_123|nonce_abc|2025-10-26T10:30:45Z"
        )
        assert canonical == expected

    def test_canonical_order_matters(self):
        """Different order should produce different canonical strings."""
        canonical1 = HMACBuilder.build_canonical_string(
            "GET", "/path", "body", "dev", "nonce", "time"
        )
        canonical2 = HMACBuilder.build_canonical_string(
            "GET", "/path", "body", "dev", "time", "nonce"  # nonce/time swapped
        )

        assert canonical1 != canonical2


class TestDeviceNotFound:
    """Test handling of non-existent devices."""

    @pytest.mark.asyncio
    async def test_poll_rejects_unknown_device(self, client: AsyncClient):
        """Unknown device ID should be rejected (404)."""
        unknown_id = uuid4().hex
        now = datetime.utcnow().isoformat() + "Z"
        nonce = f"nonce_unknown_{uuid4().hex[:8]}"
        signature = "fake_signature"

        response = await client.get(
            "/api/v1/client/poll",
            headers={
                "X-Device-Id": unknown_id,
                "X-Nonce": nonce,
                "X-Timestamp": now,
                "X-Signature": signature,
            },
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_poll_rejects_revoked_device(
        self, client: AsyncClient, device: Device, db_session: AsyncSession
    ):
        """Revoked device should be rejected (401)."""
        # Revoke the device
        device.revoked = True
        await db_session.commit()

        now = datetime.utcnow().isoformat() + "Z"
        nonce = f"nonce_revoked_{uuid4().hex[:8]}"
        canonical = HMACBuilder.build_canonical_string(
            "GET", "/api/v1/client/poll", "", device.id, nonce, now
        )
        signature = HMACBuilder.sign(canonical, device.hmac_key_hash.encode())

        response = await client.get(
            "/api/v1/client/poll",
            headers={
                "X-Device-Id": device.id,
                "X-Nonce": nonce,
                "X-Timestamp": now,
                "X-Signature": signature,
            },
        )

        assert response.status_code == 401


class TestMissingHeaders:
    """Test missing required headers."""

    @pytest.mark.asyncio
    async def test_poll_rejects_missing_device_id(self, client: AsyncClient):
        """Missing X-Device-Id should be rejected (400)."""
        now = datetime.utcnow().isoformat() + "Z"

        response = await client.get(
            "/api/v1/client/poll",
            headers={
                # X-Device-Id: MISSING
                "X-Nonce": "nonce",
                "X-Timestamp": now,
                "X-Signature": "sig",
            },
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_poll_rejects_missing_signature(
        self, client: AsyncClient, device: Device
    ):
        """Missing X-Signature should be rejected (400)."""
        now = datetime.utcnow().isoformat() + "Z"

        response = await client.get(
            "/api/v1/client/poll",
            headers={
                "X-Device-Id": device.id,
                "X-Nonce": "nonce",
                "X-Timestamp": now,
                # X-Signature: MISSING
            },
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_ack_rejects_missing_headers(self, client: AsyncClient):
        """POST /ack also requires all headers."""
        response = await client.post(
            "/api/v1/client/ack",
            json={"approval_id": str(uuid4()), "status": "placed"},
            # No headers
        )

        assert response.status_code == 400


class TestAckSpecificSecurity:
    """Test security for ACK endpoint (POST requests with body)."""

    @pytest.mark.asyncio
    async def test_ack_signature_includes_body(
        self, client: AsyncClient, device: Device, approval, db_session
    ):
        """ACK signature should include request body in canonical string."""
        now = datetime.utcnow().isoformat() + "Z"
        nonce = f"nonce_ack_{uuid4().hex[:8]}"
        body = f'{{"approval_id":"{approval.id}","status":"placed"}}'

        canonical = HMACBuilder.build_canonical_string(
            "POST", "/api/v1/client/ack", body, device.id, nonce, now
        )
        signature = HMACBuilder.sign(canonical, device.hmac_key_hash.encode())

        response = await client.post(
            "/api/v1/client/ack",
            json={"approval_id": str(approval.id), "status": "placed"},
            headers={
                "X-Device-Id": device.id,
                "X-Nonce": nonce,
                "X-Timestamp": now,
                "X-Signature": signature,
            },
        )

        assert response.status_code in (201, 200, 404)  # Depends on approval ownership

    @pytest.mark.asyncio
    async def test_ack_rejects_body_tampering(
        self, client: AsyncClient, device: Device, approval
    ):
        """Modifying body after signature should fail (401)."""
        now = datetime.utcnow().isoformat() + "Z"
        nonce = f"nonce_tamper_{uuid4().hex[:8]}"
        body = f'{{"approval_id":"{approval.id}","status":"placed"}}'

        canonical = HMACBuilder.build_canonical_string(
            "POST", "/api/v1/client/ack", body, device.id, nonce, now
        )
        signature = HMACBuilder.sign(canonical, device.hmac_key_hash.encode())

        # Use different body than what was signed

        response = await client.post(
            "/api/v1/client/ack",
            json={"approval_id": str(approval.id), "status": "failed"},
            headers={
                "X-Device-Id": device.id,
                "X-Nonce": nonce,
                "X-Timestamp": now,
                "X-Signature": signature,
            },
        )

        assert response.status_code == 401


# Fixtures for security tests


@pytest_asyncio.fixture
async def client_obj(db_session: AsyncSession) -> Client:
    """Create a test client."""
    client = Client(
        email="test_device_auth@example.com",
        telegram_id="12345",
    )
    db_session.add(client)
    await db_session.commit()
    await db_session.refresh(client)
    return client


@pytest_asyncio.fixture
async def device(client_obj: Client, db_session: AsyncSession) -> Device:
    """Create a test device for security tests."""
    from backend.app.clients.devices.models import Device

    device = Device(
        client_id=client_obj.id,
        device_name="test_device_security",
        hmac_key_hash="test_secret_key_32_bytes_long!!!",
        is_active=True,
    )
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)
    return device


@pytest_asyncio.fixture
async def approval(client_obj: Client, db_session: AsyncSession):
    """Create a test approval for ACK endpoint tests."""
    from backend.app.approvals.models import Approval, ApprovalDecision
    from backend.app.signals.models import Signal

    signal = Signal(
        user_id=client_obj.id,
        instrument="XAUUSD",
        side=0,  # BUY
        price=1950.50,
        status=0,
    )
    db_session.add(signal)
    await db_session.flush()

    approval = Approval(
        signal_id=signal.id,
        client_id=client_obj.id,
        user_id=client_obj.id,
        decision=ApprovalDecision.APPROVED.value,
    )
    db_session.add(approval)
    await db_session.commit()
    await db_session.refresh(approval)
    return approval
