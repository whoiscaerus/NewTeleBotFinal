"""Quick test to verify fixtures."""

import asyncio
import os
import sys

os.environ["APP_ENV"] = "development"
os.environ["DB_DSN"] = "postgresql+psycopg://user:pass@localhost:5432/test_app"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["HMAC_PRODUCER_ENABLED"] = "false"
os.environ["OWNER_ONLY_ENCRYPTION_KEY"] = "hzkaI52IRiaoJTcZjtMP5xFR74cpksplPZabHwJ53U4="

sys.path.insert(0, r"c:\Users\FCumm\NewTeleBotFinal\backend")

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.app.clients.devices.models import Device
from backend.app.clients.models import Client
from backend.app.core.db import Base


async def test():
    """Test fixtures."""
    # Create engine
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_factory = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_factory() as db_session:
        # Create client
        client_obj = Client(
            id=str(uuid4()),
            email="test@example.com",
            telegram_id="12345",
        )
        db_session.add(client_obj)
        await db_session.commit()
        print(f"✓ Created client: {client_obj.id}")

        # Create device
        device = Device(
            id=str(uuid4()),
            client_id=client_obj.id,
            name="test_device",
            is_active=True,
        )
        db_session.add(device)
        await db_session.commit()
        print(f"✓ Created device: {device.id} with client_id: {client_obj.id}")

        # Now query it back
        stmt = select(Device).where(Device.id == device.id)
        result = await db_session.execute(stmt)
        loaded_device = result.scalar_one_or_none()

        if loaded_device:
            print(
                f"✓ Loaded device: {loaded_device.id} with client_id: {loaded_device.client_id}"
            )
            print(f"  Client IDs match: {loaded_device.client_id == client_obj.id}")
        else:
            print("✗ Device not found!")


if __name__ == "__main__":
    asyncio.run(test())
