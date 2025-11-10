"""
CLI Tool for AI Analyst Management (PR-091).

Commands:
- toggle-analyst: Enable/disable AI Analyst Mode
- analyst-status: Show current status

Usage:
    python -m backend.cli.ai toggle-analyst --enable --owner-only
    python -m backend.cli.ai toggle-analyst --disable
    python -m backend.cli.ai toggle-analyst --enable --no-owner-only  (public release)
    python -m backend.cli.ai analyst-status
"""

import asyncio
import sys
from argparse import ArgumentParser

from sqlalchemy import select, update

from backend.app.ai.models import FeatureFlag
from backend.app.core.db import get_db_context


async def toggle_analyst(enabled: bool, owner_only: bool):
    """
    Toggle AI Analyst Mode on/off.

    Args:
        enabled: True to enable, False to disable
        owner_only: True for owner-only, False for public
    """
    async with get_db_context() as db:
        stmt = (
            update(FeatureFlag)
            .where(FeatureFlag.name == "ai_analyst")
            .values(enabled=enabled, owner_only=owner_only)
            .returning(FeatureFlag)
        )

        result = await db.execute(stmt)
        await db.commit()
        flag = result.scalar_one()

        print("✅ AI Analyst Mode Updated:")
        print(f"   Enabled: {flag.enabled}")
        print(f"   Owner-Only: {flag.owner_only}")
        print(f"   Updated At: {flag.updated_at}")

        if flag.enabled and flag.owner_only:
            print("\n📧 Mode: OWNER TESTING (outlooks sent to owner email only)")
        elif flag.enabled:
            print("\n🌍 Mode: PUBLIC (outlooks sent to all users)")
        else:
            print("\n🔴 Mode: DISABLED (no outlooks generated)")


async def analyst_status():
    """Show current AI Analyst status."""
    async with get_db_context() as db:
        stmt = select(FeatureFlag).where(FeatureFlag.name == "ai_analyst")
        result = await db.execute(stmt)
        flag = result.scalar_one_or_none()

        if flag is None:
            print("❌ AI Analyst feature flag not found in database")
            print("   Run migration: alembic upgrade head")
            sys.exit(1)

        print("📊 AI Analyst Status:")
        print(f"   Enabled: {flag.enabled}")
        print(f"   Owner-Only: {flag.owner_only}")
        print(f"   Updated At: {flag.updated_at}")
        print(f"   Updated By: {flag.updated_by or 'N/A'}")
        print(f"   Description: {flag.description or 'N/A'}")

        if flag.enabled and flag.owner_only:
            print("\n📧 Mode: OWNER TESTING")
            print("   Daily outlooks sent to owner email only")
            print("   Use --no-owner-only to release to all users")
        elif flag.enabled:
            print("\n🌍 Mode: PUBLIC")
            print("   Daily outlooks sent to all users via email + Telegram")
        else:
            print("\n🔴 Mode: DISABLED")
            print("   No outlooks are being generated")


def main():
    """CLI entry point."""
    parser = ArgumentParser(description="AI Analyst Management CLI (PR-091)")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # toggle-analyst command
    toggle_parser = subparsers.add_parser(
        "toggle-analyst", help="Enable/disable AI Analyst Mode"
    )
    toggle_parser.add_argument(
        "--enable", action="store_true", help="Enable AI Analyst"
    )
    toggle_parser.add_argument(
        "--disable", action="store_true", help="Disable AI Analyst"
    )
    toggle_parser.add_argument(
        "--owner-only",
        action="store_true",
        default=True,
        help="Owner-only mode (default: True)",
    )
    toggle_parser.add_argument(
        "--no-owner-only",
        action="store_true",
        help="Public mode (send to all users)",
    )

    # analyst-status command
    subparsers.add_parser("analyst-status", help="Show current AI Analyst status")

    args = parser.parse_args()

    if args.command == "toggle-analyst":
        if args.enable and args.disable:
            print("❌ Error: Cannot use --enable and --disable together")
            sys.exit(1)

        if not args.enable and not args.disable:
            print("❌ Error: Must specify --enable or --disable")
            sys.exit(1)

        enabled = args.enable
        owner_only = not args.no_owner_only  # Default True unless --no-owner-only

        asyncio.run(toggle_analyst(enabled, owner_only))

    elif args.command == "analyst-status":
        asyncio.run(analyst_status())

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
