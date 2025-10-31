"""Debug test - direct endpoint test without pytest."""

import asyncio
import logging
import os
import sys

# Set up environment
os.environ["APP_ENV"] = "development"
os.environ["DB_DSN"] = "postgresql+psycopg://user:pass@localhost:5432/test_app"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["HMAC_PRODUCER_ENABLED"] = "false"
os.environ["OWNER_ONLY_ENCRYPTION_KEY"] = "hzkaI52IRiaoJTcZjtMP5xFR74cpksplPZabHwJ53U4="

# Set up path
sys.path.insert(0, r"c:\Users\FCumm\NewTeleBotFinal\backend")

# Configure logging
logging.basicConfig(level=logging.DEBUG)

from datetime import datetime
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.app.approvals.models import Approval, ApprovalDecision
from backend.app.auth.models import User
from backend.app.clients.devices.models import Device

# Import models
from backend.app.core.db import Base
from backend.app.main import app
from backend.app.signals.encryption import encrypt_owner_only
from backend.app.signals.models import Signal


async def test():
    """Run direct test."""
    # Create engine
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_factory = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    # Override dependency
    async def override_get_db():
        async with async_session_factory() as session:
            yield session

    from backend.app.core.db import get_db
    from backend.app.ea.auth import get_device_auth

    # Override device auth to mock it
    async def mock_device_auth(x_device_id: str = None, **kwargs):
        class MockDeviceAuth:
            def __init__(self, device_id, client_id):
                self.device_id = device_id
                self.client_id = client_id

        async with async_session_factory() as session:

            device = await session.get(Device, x_device_id)
            if device:
                return MockDeviceAuth(device.id, device.client_id)
        return None

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_device_auth] = mock_device_auth

    # Create test data
    async with async_session_factory() as db:
        # Create client
        from backend.app.clients.models import Client

        client_obj = Client(
            id=str(uuid4()),
            email="test@example.com",
            telegram_id="12345",
        )
        db.add(client_obj)
        await db.commit()
        print(f"✓ Created client: {client_obj.id}")

        # Create user
        user = User(
            id=str(uuid4()),
            username="testuser",
            email="user@example.com",
            telegram_chat_id=123456,
            telegram_user_id=987654,
            password_hash="hashed",
            is_active=True,
        )
        db.add(user)
        await db.commit()
        print(f"✓ Created user: {user.id}")

        # Create device
        device = Device(
            id=str(uuid4()),
            client_id=client_obj.id,
            name="test_device",
            is_active=True,
        )
        db.add(device)
        await db.commit()
        print(f"✓ Created device: {device.id} with client_id: {client_obj.id}")

        # Create signal
        owner_data = {
            "stop_loss": 2645.50,
            "take_profit": 2670.00,
            "strategy": "breakout",
        }
        encrypted_owner_only = encrypt_owner_only(owner_data)

        signal = Signal(
            id=str(uuid4()),
            user_id=user.id,
            instrument="XAUUSD",
            side=0,
            price=2655.50,
            status=0,
            payload={
                "instrument": "XAUUSD",
                "entry_price": 2655.50,
                "volume": 0.1,
            },
            owner_only=encrypted_owner_only,
        )
        db.add(signal)
        await db.commit()
        print(f"✓ Created signal: {signal.id}")

        # Create approval
        approval = Approval(
            id=str(uuid4()),
            signal_id=signal.id,
            user_id=user.id,
            decision=ApprovalDecision.APPROVED.value,
            client_id=client_obj.id,
        )
        db.add(approval)
        await db.commit()
        print(f"✓ Created approval: {approval.id} with client_id: {client_obj.id}")

    # Make request
    async with AsyncClient(app=app, base_url="http://test") as client:
        ack_payload = {
            "approval_id": approval.id,
            "status": "placed",
            "broker_ticket": "MT5_987654321",
            "error": None,
        }

        response = await client.post(
            "/api/v1/client/ack",
            json=ack_payload,
            headers={
                "X-Device-Id": device.id,
                "X-Nonce": "test_nonce_" + str(uuid4()),
                "X-Timestamp": datetime.utcnow().isoformat() + "Z",
                "X-Signature": "mock_signature",
            },
        )

        print(f"\nResponse status: {response.status_code}")
        print(f"Response headers: {dict(response.headers)}")
        print(f"Response body: {response.text}")

        if response.status_code == 201:
            print("✓ Test passed!")
        else:
            print(f"✗ Test failed with status {response.status_code}")


if __name__ == "__main__":
    asyncio.run(test())
