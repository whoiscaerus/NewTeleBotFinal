#!/usr/bin/env python3
"""
Comprehensive Smoke Test Script for NewTeleBotFinal.

This script verifies the core functionality of the system end-to-end:
1. System Health (API reachable)
2. User Registration (Auth)
3. User Login (JWT generation)
4. Signal Creation (Business Logic + DB)
5. Signal Retrieval (Read path)

Usage:
    1. Ensure Docker stack is running: docker-compose up -d
    2. Run this script: python scripts/smoke_test_full.py
"""

import logging
import sys
import time
import uuid

import httpx

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("smoke_test")

BASE_URL = "http://localhost:8000"
API_V1 = f"{BASE_URL}/api/v1"


def wait_for_health(timeout=60):
    """Wait for API to become healthy."""
    logger.info("Waiting for API to be healthy...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = httpx.get(f"{BASE_URL}/health")
            if response.status_code == 200:
                logger.info("✅ API is healthy")
                return True
        except httpx.RequestError:
            pass
        time.sleep(1)

    logger.error("❌ API failed to become healthy")
    return False


def run_smoke_test():
    """Run the full smoke test suite."""

    # 1. Health Check
    if not wait_for_health():
        sys.exit(1)

    client = httpx.Client(base_url=BASE_URL, timeout=10.0)

    # Generate unique user
    unique_id = str(uuid.uuid4())[:8]
    email = f"smoke_{unique_id}@example.com"
    password = "SmokeTestPassword123!"

    # 2. Register
    logger.info(f"Registering user: {email}")
    try:
        reg_resp = client.post(
            f"{API_V1}/auth/register", json={"email": email, "password": password}
        )
        if reg_resp.status_code != 201:
            logger.error(f"❌ Registration failed: {reg_resp.text}")
            sys.exit(1)
        logger.info("✅ User registered successfully")
    except Exception as e:
        logger.error(f"❌ Registration exception: {e}")
        sys.exit(1)

    # 3. Login
    logger.info("Logging in...")
    try:
        login_resp = client.post(
            f"{API_V1}/auth/login", json={"email": email, "password": password}
        )
        if login_resp.status_code != 200:
            logger.error(f"❌ Login failed: {login_resp.text}")
            sys.exit(1)

        token_data = login_resp.json()
        access_token = token_data["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        logger.info("✅ Login successful, token received")
    except Exception as e:
        logger.error(f"❌ Login exception: {e}")
        sys.exit(1)

    # 4. Create Signal
    logger.info("Creating trading signal...")
    signal_payload = {
        "instrument": "XAUUSD",
        "side": "buy",
        "price": 2000.50,
        "payload": {"reason": "Smoke Test"},
    }

    try:
        sig_resp = client.post(
            f"{API_V1}/signals", json=signal_payload, headers=headers
        )
        if sig_resp.status_code != 201:
            logger.error(f"❌ Signal creation failed: {sig_resp.text}")
            sys.exit(1)

        signal_data = sig_resp.json()
        signal_id = signal_data["id"]
        logger.info(f"✅ Signal created: {signal_id}")
    except Exception as e:
        logger.error(f"❌ Signal creation exception: {e}")
        sys.exit(1)

    # 5. Verify Signal (Read)
    logger.info("Verifying signal retrieval...")
    try:
        # Assuming there is a list endpoint or get by ID
        # Based on routes, we might need to check list
        list_resp = client.get(f"{API_V1}/signals", headers=headers)
        if list_resp.status_code != 200:
            logger.error(f"❌ Signal list failed: {list_resp.text}")
            sys.exit(1)

        data = list_resp.json()
        signals = data.get("items", [])
        # Check if our signal is in the list
        found = any(s["id"] == signal_id for s in signals)

        if found:
            logger.info("✅ Signal verified in list")
        else:
            logger.error("❌ Signal NOT found in list")
            sys.exit(1)

    except Exception as e:
        logger.error(f"❌ Signal verification exception: {e}")
        sys.exit(1)

    logger.info("🎉 ALL SMOKE TESTS PASSED! System is production ready.")


if __name__ == "__main__":
    run_smoke_test()
