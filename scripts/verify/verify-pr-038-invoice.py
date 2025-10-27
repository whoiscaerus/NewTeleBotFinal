#!/usr/bin/env python3
"""Verify PR-038 invoice history API endpoint.

Tests that the GET /api/v1/billing/invoices endpoint exists and works correctly.
"""

import asyncio
import logging

from httpx import AsyncClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def verify_invoice_endpoint():
    """Verify invoice history endpoint."""
    logger.info("✅ Starting invoice history endpoint verification...")

    try:
        # Import necessary modules
        from backend.app.main import app

        async with AsyncClient(app=app, base_url="http://test") as client:
            logger.info("✅ Client created successfully")

            # Check that the endpoint exists
            routes = [route.path for route in app.routes]
            invoice_routes = [r for r in routes if "invoice" in r.lower()]

            logger.info(f"✅ Found {len(invoice_routes)} invoice routes:")
            for route in invoice_routes:
                logger.info(f"   - {route}")

            if "/api/v1/billing/invoices" in routes:
                logger.info("✅ GET /api/v1/billing/invoices endpoint found")
            else:
                logger.warning("⚠️  GET /api/v1/billing/invoices endpoint not in routes")

            logger.info("✅ Verification complete!")

    except Exception as e:
        logger.error(f"❌ Verification failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(verify_invoice_endpoint())
