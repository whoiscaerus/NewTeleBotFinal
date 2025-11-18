#!/usr/bin/env python3
"""Diagnose why database table isn't being created in tests."""

import asyncio

from sqlalchemy.ext.asyncio import create_async_engine


async def test_table_creation():
    """Test that all tables are created properly."""
    from backend.app.core.db import Base

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Check what tables were created
    from sqlalchemy import text

    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        )
        tables = result.fetchall()

    print(f"Tables created in SQLite: {len(tables)}")
    user_table = any("user" in t[0].lower() for t in tables)
    print(f"'users' table found: {user_table}")

    if not user_table:
        print("ERROR: users table not created!")
        print(f"Available tables: {[t[0] for t in tables]}")
    else:
        print("SUCCESS: users table exists")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(test_table_creation())
