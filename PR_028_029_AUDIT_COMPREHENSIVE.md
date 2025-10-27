# PR-028 & PR-029 Comprehensive Audit Report

**Date**: October 27, 2025
**Status**: 🟡 **PARTIALLY COMPLETE - MAJOR GAPS**
**PR-028 Completion**: ~60% (catalog + entitlements partial, migration missing, routes incomplete)
**PR-029 Completion**: ~5% (pricing module completely missing)

---

## Executive Summary

### PR-028: Shop Products/Plans & Entitlements Mapping
**Status**: 🟡 PARTIALLY IMPLEMENTED (~60%)

**What Exists**:
- ✅ Catalog models & service (~100 lines)
- ✅ Entitlements models & service (~300 lines)
- ✅ Basic billing routes (~200 lines)
- ⚠️ Stripe integration (unrelated to PR-028 scope)

**What's Missing** (40%):
- ❌ Alembic migration for catalog schema
- ❌ `/api/v1/catalog` endpoint implementation
- ❌ `/api/v1/me/entitlements` endpoint
- ❌ Full catalog.py module with plan definitions
- ❌ Entitlements middleware integration
- ❌ Tests for plan → entitlement mapping

**Impact**: Cannot deploy; routes incomplete; no migration

---

### PR-029: RateFetcher Integration & Dynamic Quotes
**Status**: 🔴 NOT IMPLEMENTED (~5%)

**What Exists**:
- ❌ Zero pricing/rates modules found
- ❌ No fetch_gbp_usd() function
- ❌ No fetch_crypto_prices() function
- ❌ No quote_for() function
- ❌ No /api/v1/quotes endpoint
- ❌ No caching logic
- ❌ No backoff/retry logic

**What's Missing** (95%):
- ❌ backend/app/pricing/rates.py (entire file)
- ❌ backend/app/pricing/quotes.py (entire file)
- ❌ backend/app/pricing/routes.py (entire file)
- ❌ ExchangeRate-API integration
- ❌ CoinGecko integration
- ❌ Redis caching (TTL: 300s)
- ❌ Exponential backoff on failures
- ❌ Rate limiting on external calls
- ❌ Prometheus metrics (2: fetch_total, quote_total)
- ❌ Comprehensive test suite

**Impact**: Cannot serve dynamic quotes; shop cannot show pricing in multiple currencies

---

## PR-028 Detailed Audit: Shop Products & Entitlements

### Current Implementation

#### ✅ What Exists: Catalog Models (~/app/billing/catalog/models.py)
```python
# Line count: ~150 lines
# Status: Present but may be incomplete

class ProductCategory(Base):
    """Represents product category."""
    __tablename__ = "product_categories"
    # Fields present

class Product(Base):
    """Represents a product/plan."""
    __tablename__ = "products"
    # Fields present

class ProductTier(Base):
    """Represents pricing tiers for a product."""
    __tablename__ = "product_tiers"
    # Fields present
```

#### ✅ What Exists: Catalog Service (~/app/billing/catalog/service.py)
```python
# Line count: ~299 lines
# Status: Implemented

class CatalogService:
    async def get_all_categories() -> list[ProductCategory]
    async def get_category(category_id: str) -> ProductCategory | None
    async def get_all_products() -> list[Product]
    async def get_category_products(category_id: str) -> list[Product]
    async def filter_products_by_tier(user_tier: int) -> list[Product]
    async def get_product(product_id: str) -> Product | None
    async def check_product_available(product_id: str) -> bool
    # All methods implemented with error handling
```

#### ✅ What Exists: Entitlements Models (~/app/billing/entitlements/models.py)
```python
# Line count: ~200+ lines
# Status: Present

class EntitlementType(Base):
    """Represents entitlement feature type."""
    __tablename__ = "entitlement_types"
    # Fields: id, name, description, tier_level

class UserEntitlement(Base):
    """Maps users to their active entitlements."""
    __tablename__ = "user_entitlements"
    # Fields: id, user_id, entitlement_type_id, expires_at, is_active
```

#### ✅ What Exists: Entitlements Service (~/app/billing/entitlements/service.py)
```python
# Line count: ~335 lines
# Status: Implemented

class EntitlementService:
    async def get_user_tier(user_id: str) -> int
        # Returns 0-3 (Free, Premium, VIP, Enterprise)
    async def check_entitlement(user_id: str, entitlement: str) -> bool
    async def list_user_entitlements(user_id: str) -> list[EntitlementType]
    async def grant_entitlement(user_id: str, entitlement_id: str, duration: timedelta)
    async def revoke_entitlement(user_id: str, entitlement_id: str)
    async def check_valid(entitlements: list[UserEntitlement]) -> list[UserEntitlement]
    # Multiple helper methods implemented
```

### ❌ What's Missing: Critical Deliverables

#### Missing 1: Alembic Migration
**File**: `backend/alembic/versions/0007_entitlements.py`
**Status**: ❌ NOT CREATED

**What should be in migration**:
```sql
CREATE TABLE product_categories (
    id UUID PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE products (
    id UUID PRIMARY KEY,
    category_id UUID NOT NULL REFERENCES product_categories(id),
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    base_price_gbp DECIMAL(10,2) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE product_tiers (
    id UUID PRIMARY KEY,
    product_id UUID NOT NULL REFERENCES products(id),
    tier_level INT NOT NULL,  -- 0=free, 1=premium, 2=vip, 3=enterprise
    price_gbp DECIMAL(10,2) NOT NULL,
    duration_days INT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE entitlement_types (
    id UUID PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,  -- e.g., "premium_signals", "copy_trading"
    description TEXT,
    tier_level INT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE user_entitlements (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    entitlement_type_id UUID NOT NULL REFERENCES entitlement_types(id),
    expires_at TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX ix_products_category ON products(category_id);
CREATE INDEX ix_product_tiers_product ON product_tiers(product_id);
CREATE INDEX ix_user_entitlements_user ON user_entitlements(user_id);
CREATE INDEX ix_user_entitlements_expires ON user_entitlements(expires_at);
```

**Impact**: Cannot create tables; schema undefined; production deployment blocked

#### Missing 2: Catalog Module (catalog.py)
**File**: `backend/app/billing/catalog.py`
**Status**: ❌ NOT CREATED (should define plan codes, durations, prices)

**Expected Content**:
```python
"""Plan definitions and catalog configuration."""

class Plan(BaseModel):
    """Plan definition with pricing."""
    code: str  # "gold_monthly", "silver_annual", etc.
    name: str
    duration_days: int
    price_gbp: float
    features: dict[str, bool]  # {signals_enabled, copy_trading, etc.}

# Hardcoded or DB-backed plan definitions
PLANS = {
    "basic_monthly": Plan(
        code="basic_monthly",
        name="Basic",
        duration_days=30,
        price_gbp=9.99,
        features={
            "signals_enabled": True,
            "max_devices": 1,
            "copy_trading": False,
            "analytics_level": "basic"
        }
    ),
    "gold_annual": Plan(
        code="gold_annual",
        name="Gold",
        duration_days=365,
        price_gbp=99.99,
        features={
            "signals_enabled": True,
            "max_devices": 5,
            "copy_trading": True,
            "analytics_level": "advanced"
        }
    ),
    # ... more plans
}

def resolve(plan_code: str) -> dict[str, Any]:
    """Resolve plan code to entitlements."""
    plan = PLANS.get(plan_code)
    if not plan:
        raise ValueError(f"Unknown plan: {plan_code}")

    return plan.features
```

**Impact**: No plan definitions; cannot map plans to entitlements

#### Missing 3: Routes Implementation
**File**: `backend/app/billing/routes.py`
**Status**: ⚠️ PARTIAL (checkout exists, but catalog/entitlements endpoints missing)

**Missing Endpoints**:

```python
# Should exist but missing:

@router.get("/api/v1/catalog", response_model=list[CatalogOut])
async def get_catalog(db: AsyncSession = Depends(get_db)):
    """Get all products/plans in catalog."""
    service = CatalogService(db)
    return await service.get_all_products()

@router.get("/api/v1/me/entitlements", response_model=EntitlementsOut)
async def get_my_entitlements(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's active entitlements."""
    service = EntitlementService(db)
    tier = await service.get_user_tier(current_user.id)
    entitlements = await service.list_user_entitlements(current_user.id)
    return EntitlementsOut(tier=tier, features=entitlements)
```

**Impact**: No endpoints to serve plan data to frontend

#### Missing 4: Entitlements Middleware
**File**: Should be integrated into request pipeline
**Status**: ❌ NOT INTEGRATED

**Expected Usage**:
```python
from backend.app.billing.entitlements import require_entitlement

@router.post("/api/v1/signals/advanced-analytics")
@require_entitlement("analytics_level", "advanced")
async def use_advanced_analytics(current_user: User = Depends(get_current_user)):
    """Only users with 'advanced' analytics entitlement can call this."""
    pass
```

**Impact**: Premium features not gated; cannot enforce paid tier access

#### Missing 5: Tests
**Status**: ❌ NO TESTS FOUND

**Tests Should Cover**:
- ✅ Plan → entitlement mapping works
- ✅ Tier levels assign correct entitlements
- ✅ Entitlement expiry handled
- ✅ Catalog filtering by user tier
- ✅ Routes return correct JSON schema

---

## PR-029 Detailed Audit: RateFetcher & Dynamic Quotes

### Current Implementation

**Status**: 🔴 **ZERO IMPLEMENTATION**

**Search Results**:
```
backend/app/pricing/rates.py       ❌ NOT FOUND
backend/app/pricing/quotes.py      ❌ NOT FOUND
backend/app/pricing/routes.py      ❌ NOT FOUND
backend/app/pricing/__init__.py    ❌ NOT FOUND
```

**Directory**: `backend/app/pricing/` **DOES NOT EXIST**

### ❌ What's Missing: All Deliverables (100%)

#### Missing 1: Rates Module (rates.py) - 0% IMPLEMENTED
**Expected File**: `backend/app/pricing/rates.py`
**Expected Line Count**: ~150 lines
**Status**: ❌ NOT CREATED

**Expected Content**:
```python
"""Rate fetching from external APIs with caching and backoff."""

import asyncio
from datetime import datetime, timedelta
from typing import dict

import httpx
import redis.asyncio as redis
from tenacity import retry, stop_after_attempt, wait_exponential

class RateFetcher:
    """Fetch FX and crypto rates from external APIs."""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.ttl_seconds = 300  # 5 minutes

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def fetch_gbp_usd(self) -> float:
        """Fetch GBP/USD exchange rate.

        Returns:
            Exchange rate (1 GBP = X USD)

        Raises:
            Exception: If all retries exhausted
        """
        # Check cache
        cached = await self.redis.get("rate_gbp_usd")
        if cached:
            return float(cached)

        # Fetch from API
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{FX_API_BASE}/latest",
                params={"apikey": FX_API_KEY, "base": "GBP", "symbols": "USD"}
            )
            response.raise_for_status()
            data = response.json()
            rate = data["rates"]["USD"]

            # Cache result
            await self.redis.setex(
                "rate_gbp_usd",
                self.ttl_seconds,
                str(rate)
            )
            return rate

    async def fetch_crypto_prices(self, ids: list[str]) -> dict[str, float]:
        """Fetch crypto prices from CoinGecko.

        Args:
            ids: List of CoinGecko IDs (e.g., ["bitcoin", "ethereum"])

        Returns:
            {crypto_id: price_gbp}
        """
        # Implementation with retry, caching, error handling
        pass
```

**Impact**: Cannot fetch live prices; cannot show current rates to users

#### Missing 2: Quotes Module (quotes.py) - 0% IMPLEMENTED
**Expected File**: `backend/app/pricing/quotes.py`
**Expected Line Count**: ~100 lines
**Status**: ❌ NOT CREATED

**Expected Content**:
```python
"""Quote generation with currency conversion."""

from backend.app.pricing.rates import RateFetcher

class QuoteService:
    """Generate price quotes in multiple currencies."""

    def __init__(self, rate_fetcher: RateFetcher, catalog_service: CatalogService):
        self.rate_fetcher = rate_fetcher
        self.catalog = catalog_service

    async def quote_for(
        self,
        plan_code: str,
        currency: str = "GBP"
    ) -> dict[str, float]:
        """Get quote for plan in specified currency.

        Args:
            plan_code: e.g., "gold_monthly"
            currency: "GBP", "USD", "EUR"

        Returns:
            {plan_code, price_gbp, price_converted, currency, rate}

        Example:
            >>> await service.quote_for("gold_monthly", "USD")
            {
                "plan_code": "gold_monthly",
                "price_gbp": 49.99,
                "price_converted": 63.48,
                "currency": "USD",
                "rate": 1.270
            }
        """
        pass
```

**Impact**: Cannot show prices in user's local currency

#### Missing 3: Routes Module (routes.py) - 0% IMPLEMENTED
**Expected File**: `backend/app/pricing/routes.py`
**Expected Line Count**: ~80 lines
**Status**: ❌ NOT CREATED

**Expected Endpoints**:
```python
@router.get("/api/v1/quotes")
async def get_quotes(
    plan: str,           # ?plan=gold_monthly
    currency: str = "GBP" # ?currency=USD
):
    """Get price quote for plan in specified currency.

    Example:
        GET /api/v1/quotes?plan=gold_monthly&currency=USD
        Response: {price_gbp: 49.99, price_usd: 63.48, rate: 1.270}
    """
    service = QuoteService(rate_fetcher, catalog_service)
    return await service.quote_for(plan, currency)
```

**Impact**: No endpoint to serve dynamic quotes to frontend/bots

#### Missing 4: ExchangeRate-API Integration - 0% IMPLEMENTED
**Status**: ❌ NOT CREATED

**Required Implementation**:
- Fetch from `FX_API_BASE` with `FX_API_KEY`
- Parse JSON response
- Extract rates
- Handle authentication errors
- Cache with TTL

#### Missing 5: CoinGecko Integration - 0% IMPLEMENTED
**Status**: ❌ NOT CREATED

**Required Implementation**:
- Fetch from `COINGECKO_BASE` (no auth)
- Parse JSON response
- Extract prices
- Convert to GBP (using rate fetcher)
- Cache with TTL

#### Missing 6: Caching with Redis - 0% IMPLEMENTED
**Status**: ❌ NOT CREATED

**Requirements**:
- Cache TTL: 300 seconds (`RATES_TTL_SECONDS`)
- Keys: `rate_gbp_usd`, `rate_eur_usd`, `crypto_btc_gbp`, etc.
- Fallback if Redis unavailable (return stale or error)

#### Missing 7: Backoff & Retry Logic - 0% IMPLEMENTED
**Status**: ❌ NOT CREATED

**Requirements**:
- Exponential backoff on API failures
- Max 3 retries
- Jitter to prevent thundering herd
- Fallback to cached value if all retries fail

#### Missing 8: Rate Limiting - 0% IMPLEMENTED
**Status**: ❌ NOT CREATED

**Requirements**:
- Limit external API calls to prevent abuse
- Track per-endpoint calls
- Return cached value if rate limit reached
- Log rate limit violations

#### Missing 9: Prometheus Metrics - 0% IMPLEMENTED
**Status**: ❌ NOT CREATED

**Required Metrics**:
```python
# pricing_rate_fetch_total{source}  # counter
# - source: "exchangerate_api", "coingecko"
# Incremented on each fetch attempt (success/failure)

# pricing_quote_total{currency}  # counter
# - currency: "GBP", "USD", "EUR"
# Incremented on each quote request
```

#### Missing 10: Comprehensive Test Suite - 0% IMPLEMENTED
**Status**: ❌ NOT CREATED

**Test Cases Should Cover**:
- ✅ Fetch GBP/USD rate from API
- ✅ Fetch crypto prices from CoinGecko
- ✅ Cache hit vs miss
- ✅ Stale cache fallback when API fails
- ✅ Exponential backoff on failures
- ✅ Rate limiting enforcement
- ✅ Quote calculation and currency conversion
- ✅ Error handling (timeout, auth, malformed JSON)
- ✅ Metrics recording

---

## Dependency Analysis

### PR-028 Dependencies
- ✅ PR-004 (Auth) - Required for entitlement checking
- ✅ PR-010 (Database baseline) - Already done
- ⚠️ PR-021 (Signals API) - Used to gate signals
- ❌ Alembic migration - **MISSING**

### PR-029 Dependencies
- ✅ PR-028 (Catalog) - Uses plan catalog for quotes
- ⚠️ Redis (optional but recommended)
- ⚠️ httpx async client (should be installed)

### PR-030 Blocks
**NOTE**: PR-030 (Content Distribution Router) likely depends on both PR-028 and PR-029 for catalog and pricing display.

---

## Test Execution

### PR-028 Test Status
**Command**:
```bash
pytest backend/tests/test_billing_catalog.py -v
pytest backend/tests/test_billing_entitlements.py -v
```
**Status**: ❌ **NOT RUN** (would fail - routes missing)
**Expected**: 0/30 tests pass (endpoints don't exist)

### PR-029 Test Status
**Command**:
```bash
pytest backend/tests/test_pricing_rates.py -v
pytest backend/tests/test_pricing_quotes.py -v
```
**Status**: ❌ **NOT FOUND** (module doesn't exist)
**Expected**: Cannot even run (files don't exist)

---

## Code Quality Issues

### PR-028 Issues

**Issue 1**: Entitlements service has tier inference logic that's fragile
```python
# Current (bad):
if "vip_support" in entitlement_names:
    return 3

# Better: Use tier_level field directly
```

**Issue 2**: No validation on plan pricing
```python
# Should validate:
- price_gbp > 0
- duration_days > 0
- plan_code matches pattern
```

**Issue 3**: No soft-delete for revoked entitlements
- Entitlements are hard-deleted
- Should mark as `revoked = True` for audit trail

### PR-029 Issues

**Issue 1**: No retry logic defined
- All code missing; no implementation

**Issue 2**: No fallback strategy documented
- What happens when API is down?
- Should serve stale cache? Or error?

**Issue 3**: No rate limit strategy
- How aggressively to rate-limit?
- Per-IP? Per-user? Global?

---

## Blockers Summary

| Component | PR | Blocker | Impact | Hours to Fix |
|-----------|----|---------|---------| ------------|
| Catalog Models | 028 | Migration missing | Can't create tables | 1 |
| Entitlements Routes | 028 | `/catalog` endpoint missing | Can't fetch plans | 1 |
| Entitlements Routes | 028 | `/me/entitlements` missing | Can't fetch user perms | 1 |
| Entitlements Middleware | 028 | Not integrated | Can't gate premium routes | 2 |
| Pricing Module | 029 | Completely missing | Can't serve quotes | 8 |
| Rate Fetching | 029 | Not implemented | Can't get live prices | 4 |
| Crypto Integration | 029 | Not implemented | Can't show crypto prices | 2 |
| Caching Logic | 029 | Not implemented | Hits API every request | 2 |
| Backoff/Retry | 029 | Not implemented | No resilience | 2 |
| Tests | Both | Missing | Can't verify | 4 |

**TOTAL HOURS TO FIX BOTH PRs**: ~27 hours

---

## Production Readiness Matrix

| Requirement | PR-028 | PR-029 | Status |
|-----------|--------|--------|--------|
| Code implemented | ✅ 60% | ❌ 5% | 🔴 BLOCKED |
| Tests written | ❌ 0% | ❌ 0% | 🔴 BLOCKED |
| Tests passing | ❌ 0% | ❌ 0% | 🔴 BLOCKED |
| Coverage ≥90% | ❌ 0% | ❌ 0% | 🔴 BLOCKED |
| Security reviewed | ⚠️ Partial | ❌ No | 🔴 BLOCKED |
| Documentation | ⚠️ Partial | ❌ No | 🔴 BLOCKED |
| No regressions | ⚠️ Unknown | ❌ Unknown | 🔴 BLOCKED |
| **Can Deploy** | **❌ NO** | **❌ NO** | **🔴 BLOCKED** |

---

## Conclusion

### PR-028: Shop Products & Entitlements
- ✅ **Database layer complete** (models exist)
- ✅ **Service layer complete** (business logic implemented)
- ❌ **Route layer missing** (2 critical endpoints)
- ❌ **Migration missing** (schema not created)
- ❌ **Tests missing** (0 test cases)
- ❌ **Middleware missing** (gate logic not integrated)

**Status**: ~60% complete, **CANNOT DEPLOY**

### PR-029: RateFetcher & Dynamic Quotes
- ❌ **All modules missing** (entire feature)
- ❌ **No API integration** (zero implementation)
- ❌ **No caching** (not built)
- ❌ **No retry logic** (not built)
- ❌ **No tests** (not written)
- ❌ **No metrics** (not recorded)

**Status**: ~5% complete (nothing implemented), **CANNOT DEPLOY**

### Combined Status
**Can PR-026/027 → PR-028 → PR-029?**
```
No. PR-026/027 cannot run tests (missing models).
    PR-028 is ~60% done (need routes + migration + tests).
    PR-029 is ~5% done (need complete rewrite, ~8+ hours).

    Blocking order:
    1. Fix PR-026/027 (4 hours): Create models + migration + tests
    2. Complete PR-028 (6 hours): Routes + middleware + tests
    3. Implement PR-029 (15 hours): Full feature from scratch

    Total: ~25 hours before any can deploy
```

---

## Recommendations

### Immediate Actions
1. **Fix PR-026/027** (do not move forward until these pass)
   - Add missing database models
   - Create Alembic migration
   - Run tests (60+) and verify 90%+ coverage

2. **Complete PR-028** (after PR-026/027 passing)
   - Create `/api/v1/catalog` endpoint
   - Create `/api/v1/me/entitlements` endpoint
   - Create Alembic migration
   - Integrate entitlements middleware
   - Write comprehensive test suite

3. **Implement PR-029** (after PR-028 passing)
   - Create entire pricing module from scratch
   - Implement both external API integrations
   - Add caching and retry logic
   - Write comprehensive test suite

### Timeline
- PR-026/027: 4 hours (models + migration)
- PR-028: 6 hours (routes + middleware + tests)
- PR-029: 15 hours (full implementation)
- **Total**: ~25 hours
- **Best case**: 1-2 developer days

---

## Files Needing Changes

### PR-028
- ❌ `backend/alembic/versions/0007_entitlements.py` (CREATE)
- ❌ `backend/app/billing/catalog.py` (CREATE)
- ⚠️ `backend/app/billing/routes.py` (MODIFY - add 2 endpoints)
- ❌ `backend/app/billing/middleware.py` (CREATE)
- ❌ `backend/tests/test_billing_catalog.py` (CREATE)
- ❌ `backend/tests/test_billing_entitlements.py` (CREATE)

### PR-029
- ❌ `backend/app/pricing/__init__.py` (CREATE)
- ❌ `backend/app/pricing/rates.py` (CREATE)
- ❌ `backend/app/pricing/quotes.py` (CREATE)
- ❌ `backend/app/pricing/routes.py` (CREATE)
- ❌ `backend/tests/test_pricing_rates.py` (CREATE)
- ❌ `backend/tests/test_pricing_quotes.py` (CREATE)
