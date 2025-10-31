"""Debug the 500 error."""

import asyncio
import os
import sys
from uuid import uuid4

# Set up path
sys.path.insert(0, r"c:\Users\FCumm\NewTeleBotFinal\backend")

# Set encryption key
os.environ["OWNER_ONLY_ENCRYPTION_KEY"] = "hzkaI52IRiaoJTcZjtMP5xFR74cpksplPZabHwJ53U4="

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.app.approvals.models import Approval, ApprovalDecision
from backend.app.auth.models import User
from backend.app.clients.devices.models import Device
from backend.app.core.db import Base
from backend.app.ea.models import Execution, ExecutionStatus
from backend.app.signals.encryption import encrypt_owner_only
from backend.app.signals.models import Signal


async def debug_test():
    """Create test data and verify everything."""
    # Create in-memory database
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Create test user
        user = User(
            id=str(uuid4()),
            username="testuser",
            email="test@example.com",
            telegram_chat_id=123456,
            telegram_user_id=987654,
            password_hash="hashed",
            is_active=True,
        )
        session.add(user)
        await session.commit()
        print(f"✓ Created user: {user.id}")

        # Create test device
        device = Device(
            id=str(uuid4()),
            client_id=str(uuid4()),
            name="test_device",
            is_active=True,
        )
        session.add(device)
        await session.commit()
        print(f"✓ Created device: {device.id}")

        # Create signal with owner_only
        owner_data = {
            "stop_loss": 2645.50,
            "take_profit": 2670.00,
            "strategy": "breakout",
        }
        encrypted_owner_only = encrypt_owner_only(owner_data)
        print(f"✓ Encrypted owner_only: {encrypted_owner_only[:50]}...")

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
        session.add(signal)
        await session.commit()
        print(f"✓ Created signal: {signal.id}")

        # Create approval
        approval = Approval(
            id=str(uuid4()),
            signal_id=signal.id,
            user_id=user.id,
            decision=ApprovalDecision.APPROVED.value,
        )
        session.add(approval)
        await session.commit()
        print(f"✓ Created approval: {approval.id}")

        # Try to create execution
        execution = Execution(
            id=str(uuid4()),
            device_id=device.id,
            approval_id=approval.id,
            status=ExecutionStatus.ACKNOWLEDGED.value,
            broker_ticket="MT5_987654321",
        )
        session.add(execution)
        await session.commit()
        print(f"✓ Created execution: {execution.id}")

        print("\n✓ All objects created successfully!")


if __name__ == "__main__":
    asyncio.run(debug_test())
