"""Test if fakeredis works."""

import asyncio
import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

try:
    import fakeredis.aioredis

    print("✅ fakeredis installed")
    redis_inst = fakeredis.aioredis.FakeRedis()
    print(f"✅ Created fakeredis instance: {type(redis_inst)}")

    async def test_set():
        result = await redis_inst.set("test_key", "1", nx=True, ex=300)
        print(f"✅ Redis set() works: {result}")

    asyncio.run(test_set())

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback

    traceback.print_exc()
