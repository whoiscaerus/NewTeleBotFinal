# PR-027-030 Implementation Plan: Telegram Monetization Layer

**Session**: Continuation from PR-024-026
**Phase**: TIER 1D2 — Telegram Webhook & Commands
**Goal**: Build complete Telegram bot monetization flow (webhook → catalog → pricing → shop)
**Total Estimated Time**: 7 hours
**Status**: Ready to implement

---

## 📋 Overview: PR-027-030 Chain

```
PR-027: Telegram Webhook Router
    ↓ (creates webhook entry point)
PR-028: Telegram Catalog & Entitlements
    ↓ (defines what users can buy)
PR-029: Dynamic Pricing
    ↓ (calculates prices with markups/bonuses)
PR-030: Telegram Shop & Checkout
    ↓ (creates checkout flow, orders)
PR-031: Stripe Webhook [BLOCKER - not in scope this session]
```

---

## ✅ Dependency Verification

All dependencies complete:
- ✅ PR-001 (CI/CD) - GitHub Actions
- ✅ PR-002 (Settings) - Config system
- ✅ PR-004 (Auth) - JWT/RBAC
- ✅ PR-007 (Secrets) - Telegram token stored
- ✅ PR-010 (Database) - PostgreSQL ready
- ✅ PR-013 (Data) - Market data fetch available
- ✅ PR-024-026 (Affiliate/Device/Exec) - Already done

**NOTE**: PR-031 (Stripe webhook) is a blocker for PR-030 to be *fully complete*, but we can implement the structure and mock payment handling.

---

## 🏗️ Architecture Overview

```
User sends /shop command to Telegram bot
    ↓
Telegram Servers send webhook POST to backend
    ↓
POST /api/v1/telegram/webhook
    ↓
PR-027: Webhook Signature Verification
    ↓ (verify HMAC-SHA256 signature)
PR-027: Command Router
    ↓ (detect /shop command)
PR-030: Shop Handler (list products)
    ↓
PR-028: Catalog Service (load products, check permissions)
    ↓ (is user premium? what can they buy?)
PR-029: Pricing Calculator (fetch prices with markups)
    ↓ (what does this tier cost? affiliate bonus? regional markup?)
PR-030: Send inline buttons (Choose product)
    ↓
User clicks button → callback_query
    ↓
PR-030: Checkout Handler
    ↓ (verify order, create order record)
PR-031: Payment Handler [BLOCKED - depends on PR-031]
    ↓ (would send to Stripe)
```

---

## 📁 File Structure (PR-027-030)

### PR-027: Telegram Webhook Router (1.5 hours)

**New files**:
```
backend/app/telegram/
├── __init__.py                  # Module exports
├── models.py                    # Webhook events, commands tables
├── schema.py                    # Pydantic schemas (Update, Message, etc)
├── webhook.py                   # POST /api/v1/telegram/webhook endpoint
└── router.py                    # Command routing logic
```

**Key components**:
- Webhook signature verification (HMAC-SHA256)
- Idempotent message handling (via message_id)
- Command routing registry
- Rate limiting per user
- Webhook event logging

---

### PR-028: Telegram Catalog & Entitlements (2 hours)

**New files**:
```
backend/app/billing/catalog/
├── __init__.py                  # Module exports
├── models.py                    # Product, ProductTier, ProductCategory tables
└── service.py                   # CatalogService (load products, check access)

backend/app/billing/entitlements/
├── __init__.py                  # Module exports
├── models.py                    # UserEntitlement, EntitlementType tables
└── service.py                   # EntitlementService (check tier, grant access)
```

**Key components**:
- Product catalog (name, price tier, description, category)
- User tiers (Free, Premium, VIP, Enterprise)
- Entitlements (what each tier can access)
- Permission checks (is_user_premium, can_access_feature)
- Product-tier mapping (which products for which tiers)

---

### PR-029: Dynamic Pricing (1.5 hours)

**New files**:
```
backend/app/billing/pricing/
├── __init__.py                  # Module exports
├── calculator.py                # PricingCalculator (fetch base price, apply rules)
└── rules.py                     # Pricing rules (regional markup, affiliate bonus, volume discount)
```

**Key components**:
- Base pricing per tier
- Regional markup (fetch current FX rates from PR-013)
- Affiliate bonus (if user referred, apply discount)
- Volume discounts (future: buy 3 months → 10% off)
- Dynamic currency conversion

---

### PR-030: Telegram Shop & Checkout (2 hours)

**New files**:
```
backend/app/telegram/handlers/
├── __init__.py                  # Module exports
├── shop.py                      # Shop command handler (list products, show buttons)
└── checkout.py                  # Checkout handler (process button clicks, create orders)

backend/app/orders/
├── __init__.py                  # Module exports
├── models.py                    # Order, OrderItem tables
└── service.py                   # OrderService (create order, track status)
```

**Key components**:
- `/shop` command → show product list with inline buttons
- Button clicks → callback_query handler
- Order creation (item, quantity, price, user)
- Order status tracking (pending, completed, failed)
- Integration with PR-031 payment handler

---

### Database Migrations (1 hour)

```
backend/alembic/versions/
├── 007_add_catalog_tables.py       # Products, ProductTiers, Categories
├── 008_add_entitlements.py         # UserEntitlements, EntitlementTypes
└── 009_add_orders.py               # Orders, OrderItems
```

---

## 📊 Database Schema

### PR-027: Webhook Events

```sql
CREATE TABLE telegram_webhooks (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36),
    message_id INT NOT NULL,
    chat_id INT NOT NULL,
    command VARCHAR(32),           -- /shop, /help, etc
    text TEXT,
    status INT,                    -- 0=received, 1=processing, 2=success, 3=error
    error_message VARCHAR(255),
    created_at DATETIME DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES users(id),
    INDEX ix_webhooks_user_created (user_id, created_at),
    UNIQUE INDEX ix_webhooks_message_id (message_id)
);

CREATE TABLE telegram_commands (
    id VARCHAR(36) PRIMARY KEY,
    command VARCHAR(32) NOT NULL UNIQUE,
    category VARCHAR(32),          -- 'billing', 'help', 'affiliate'
    description VARCHAR(255),
    requires_auth INT,
    requires_premium INT,
    created_at DATETIME DEFAULT NOW()
);
```

### PR-028: Catalog & Entitlements

```sql
CREATE TABLE product_categories (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    icon VARCHAR(50),
    created_at DATETIME DEFAULT NOW()
);

CREATE TABLE products (
    id VARCHAR(36) PRIMARY KEY,
    category_id VARCHAR(36) NOT NULL,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    features TEXT,                 -- JSON array
    created_at DATETIME DEFAULT NOW(),
    FOREIGN KEY (category_id) REFERENCES product_categories(id)
);

CREATE TABLE product_tiers (
    id VARCHAR(36) PRIMARY KEY,
    product_id VARCHAR(36) NOT NULL,
    tier_level INT,                -- 0=Free, 1=Premium, 2=VIP, 3=Enterprise
    tier_name VARCHAR(50),
    base_price FLOAT NOT NULL,     -- GBP
    billing_period VARCHAR(20),    -- 'monthly', 'annual'
    created_at DATETIME DEFAULT NOW(),
    FOREIGN KEY (product_id) REFERENCES products(id),
    UNIQUE INDEX ix_product_tier (product_id, tier_level)
);

CREATE TABLE entitlement_types (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,  -- 'premium_signals', 'copy_trading'
    description VARCHAR(255),
    created_at DATETIME DEFAULT NOW()
);

CREATE TABLE user_entitlements (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    entitlement_type_id VARCHAR(36) NOT NULL,
    granted_at DATETIME DEFAULT NOW(),
    expires_at DATETIME,
    is_active INT DEFAULT 1,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (entitlement_type_id) REFERENCES entitlement_types(id),
    INDEX ix_entitlements_user_active (user_id, is_active)
);
```

### PR-029: Pricing Rules (no new tables, computed)

Pricing stored as configuration/settings, not DB tables. Rules apply at runtime.

### PR-030: Orders

```sql
CREATE TABLE orders (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    product_tier_id VARCHAR(36) NOT NULL,
    quantity INT DEFAULT 1,
    base_price FLOAT NOT NULL,     -- Price before markups
    final_price FLOAT NOT NULL,    -- Price after regional, affiliate, etc
    currency VARCHAR(3),           -- 'GBP', 'USD', etc
    status INT,                    -- 0=pending, 1=completed, 2=failed, 3=cancelled
    payment_method VARCHAR(20),    -- 'stripe', 'telegram_stars'
    transaction_id VARCHAR(255),   -- Stripe transaction ID / TG payment ID
    notes TEXT,
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (product_tier_id) REFERENCES product_tiers(id),
    INDEX ix_orders_user_created (user_id, created_at),
    INDEX ix_orders_status (status)
);

CREATE TABLE order_items (
    id VARCHAR(36) PRIMARY KEY,
    order_id VARCHAR(36) NOT NULL,
    product_tier_id VARCHAR(36) NOT NULL,
    quantity INT,
    unit_price FLOAT,
    total_price FLOAT,
    FOREIGN KEY (order_id) REFERENCES orders(id),
    FOREIGN KEY (product_tier_id) REFERENCES product_tiers(id)
);
```

---

## 🔌 API Endpoints Summary

### PR-027 (Webhook Router)
```
POST /api/v1/telegram/webhook          (no auth needed, signature verification)
  → Routes to command handler based on message type
```

### PR-028 (Catalog & Entitlements)
```
GET /api/v1/billing/catalog            (auth required)
  → Returns all products with user's accessible tiers

GET /api/v1/billing/catalog/{product_id}
  → Returns specific product details

GET /api/v1/billing/entitlements       (auth required)
  → Returns user's current entitlements

POST /api/v1/billing/entitlements      (internal only - PR-031 will call this)
  → Grant entitlement to user
```

### PR-029 (Pricing)
```
GET /api/v1/billing/pricing/{product_tier_id}   (auth required)
  → Returns calculated price with all markups applied
  → Includes: base price, regional markup, affiliate bonus, total
```

### PR-030 (Shop & Checkout)
```
POST /api/v1/telegram/shop             (Telegram webhook handler)
  → Responds with /shop command (inline buttons)

POST /api/v1/telegram/checkout/{product_tier_id}   (Telegram webhook handler)
  → Creates order, starts payment flow
```

---

## 🔑 Implementation Sequence

### Step 1: PR-027 (Telegram Webhook) - 1.5 hours

**Models** (`telegram/models.py`):
- TelegramWebhook (id, user_id, message_id, command, status, created_at)
- TelegramCommand (id, command, category, description, requires_auth)

**Schema** (`telegram/schema.py`):
- TelegramUpdate (message, callback_query)
- TelegramMessage (from, text, message_id, chat)
- TelegramCallback (from, data, message_id)
- Pydantic models for validation

**Webhook** (`telegram/webhook.py`):
```python
@router.post("/api/v1/telegram/webhook", status_code=200)
async def telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    # 1. Verify signature
    body = await request.body()
    signature = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not verify_signature(body, signature):
        raise HTTPException(401, "Invalid signature")

    # 2. Parse update
    data = await request.json()
    update = TelegramUpdate.model_validate(data)

    # 3. Route to handler
    if update.message and update.message.text:
        result = await route_command(update, db)
    elif update.callback_query:
        result = await route_callback(update, db)

    return {"ok": True}
```

**Router** (`telegram/router.py`):
```python
COMMAND_HANDLERS = {
    'start': handle_start,
    'help': handle_help,
    'shop': handle_shop,  # PR-030
    'affiliate': handle_affiliate,  # existing
    ...
}

async def route_command(update: TelegramUpdate, db: AsyncSession):
    command = extract_command(update.message.text)  # /shop → shop
    handler = COMMAND_HANDLERS.get(command)
    if handler:
        return await handler(update, db)
    else:
        return send_unknown_command_error(update)
```

---

### Step 2: PR-028 (Catalog & Entitlements) - 2 hours

**Models** (`billing/catalog/models.py`):
- ProductCategory (id, name, slug, description)
- Product (id, category_id, name, slug, description)
- ProductTier (id, product_id, tier_level, tier_name, base_price)

**Service** (`billing/catalog/service.py`):
```python
class CatalogService:
    async def get_all_products(self) -> list[ProductOut]:
        # Return all products with their tiers

    async def get_product(self, product_id: str) -> ProductOut:
        # Return specific product

    async def get_products_for_tier(self, user_tier: int) -> list[ProductOut]:
        # Return only products accessible to this tier level
```

**Models** (`billing/entitlements/models.py`):
- EntitlementType (id, name, description)
- UserEntitlement (id, user_id, entitlement_type_id, granted_at, expires_at)

**Service** (`billing/entitlements/service.py`):
```python
class EntitlementService:
    async def is_user_premium(self, user_id: str) -> bool:
        # Check if user has 'premium' entitlement

    async def has_entitlement(self, user_id: str, entitlement: str) -> bool:
        # Check if user has specific entitlement

    async def grant_entitlement(self, user_id: str, entitlement: str, duration_days: int):
        # Grant entitlement to user (called by PR-031 payment handler)

    async def get_user_tier(self, user_id: str) -> int:
        # Return highest tier user has access to
```

---

### Step 3: PR-029 (Dynamic Pricing) - 1.5 hours

**Calculator** (`billing/pricing/calculator.py`):
```python
class PricingCalculator:
    async def get_price(
        self,
        product_tier_id: str,
        user_id: str,
        region: str = "GB"
    ) -> PriceDetail:
        # 1. Get base price from DB
        tier = await get_product_tier(product_tier_id)
        base_price = tier.base_price

        # 2. Apply regional FX markup (from PR-013)
        fx_rate = await get_fx_rate(region)
        regional_price = base_price * fx_rate

        # 3. Apply affiliate bonus (if user referred, 10% discount)
        affiliate_bonus = 0
        referrer = await get_referrer(user_id)
        if referrer:
            affiliate_bonus = regional_price * 0.10

        # 4. Return breakdown
        return PriceDetail(
            base_price=base_price,
            regional_price=regional_price,
            affiliate_discount=affiliate_bonus,
            final_price=regional_price - affiliate_bonus,
            currency="GBP"
        )
```

---

### Step 4: PR-030 (Shop & Checkout) - 2 hours

**Shop Handler** (`telegram/handlers/shop.py`):
```python
async def handle_shop(update: TelegramUpdate, db: AsyncSession):
    """
    /shop command
    1. Get user's tier
    2. Load products they can access
    3. Show product list with inline buttons
    """
    user_id = extract_user_id(update)

    # Get user's tier
    ent_service = EntitlementService(db)
    user_tier = await ent_service.get_user_tier(user_id)

    # Get products accessible to this tier
    catalog_service = CatalogService(db)
    products = await catalog_service.get_products_for_tier(user_tier)

    # Build inline buttons
    buttons = [
        InlineKeyboardButton(
            text=f"{p.name} - {p.price} GBP/mo",
            callback_data=f"checkout:{p.id}"
        )
        for p in products
    ]

    # Send to Telegram
    text = "📦 **Premium Plans Available**\n\nChoose your upgrade:"
    await send_telegram_message(
        chat_id=update.message.chat.id,
        text=text,
        reply_markup=InlineKeyboardMarkup([buttons])
    )
```

**Checkout Handler** (`telegram/handlers/checkout.py`):
```python
async def handle_checkout_callback(update: TelegramUpdate, db: AsyncSession):
    """
    User clicks a product button
    1. Parse product_tier_id from callback_data
    2. Calculate final price (PR-029)
    3. Create order record
    4. Show payment options (Stripe, Telegram Stars)
    """
    callback_data = update.callback_query.data  # "checkout:product_id"
    product_tier_id = callback_data.split(":")[1]
    user_id = extract_user_id(update)

    # Get pricing
    pricing_calc = PricingCalculator(db)
    price_detail = await pricing_calc.get_price(product_tier_id, user_id)

    # Create order (pending payment)
    order_service = OrderService(db)
    order = await order_service.create_order(
        user_id=user_id,
        product_tier_id=product_tier_id,
        base_price=price_detail.base_price,
        final_price=price_detail.final_price,
        status=OrderStatus.PENDING
    )

    # Show payment options
    buttons = [
        InlineKeyboardButton("💳 Pay with Stripe", callback_data=f"pay_stripe:{order.id}"),
        InlineKeyboardButton("⭐ Pay with Telegram Stars", callback_data=f"pay_stars:{order.id}"),
    ]

    text = f"""
💰 **Checkout Summary**
Product: {product_name}
Price: {price_detail.final_price} GBP

Choose payment method:
"""

    await send_telegram_message(
        chat_id=update.callback_query.message.chat.id,
        text=text,
        reply_markup=InlineKeyboardMarkup([buttons])
    )
```

---

## 🧪 Testing Strategy

### Unit Tests (PR-027)
- Webhook signature verification (valid/invalid)
- Command extraction from text (/shop, /help)
- Idempotency (same message_id processed twice)
- Rate limiting per user

### Unit Tests (PR-028)
- Catalog loading (products, tiers, access control)
- Entitlement checks (is_user_premium, has_access)
- Tier level logic

### Unit Tests (PR-029)
- Price calculation (base + regional + affiliate)
- FX rate fetching (mock PR-013)
- Discount application

### Unit Tests (PR-030)
- Order creation
- Checkout flow (button click → order)
- Payment option display

---

## ⚠️ Important Notes

1. **PR-031 Dependency**: Stripe webhook integration is NOT in scope for this session. We'll mock payment processing. PR-031 will be next session's first task.

2. **Telegram Bot Setup**: Assumes Telegram bot already exists and webhook URL configured. If not, will need to do that separately (outside these PRs).

3. **Signature Verification**: HMAC-SHA256 signature must match exactly. Will use `settings.TELEGRAM_BOT_API_SECRET_TOKEN` from PR-007 secrets.

4. **Idempotency**: Use message_id as unique key to prevent processing same message twice (network retries).

5. **Rate Limiting**: Use Redis to track commands per user (10 commands/min).

---

## 📌 Session Timeline

| Phase | Duration | Files | Status |
|-------|----------|-------|--------|
| Plan + Study | 15 min | PR-027-030 specs | In progress |
| PR-027 Implementation | 1.5h | 5 files | Next |
| PR-028 Implementation | 2h | 6 files | After PR-027 |
| PR-029 Implementation | 1.5h | 2 files | After PR-028 |
| PR-030 Implementation | 2h | 3 files | After PR-029 |
| Database Migrations | 1h | 3 files | Throughout |
| Main App Integration | 15 min | 1 file | End |
| Linting + Commit | 30 min | All | Final |
| **Total** | **~8 hours** | **20 files** | Estimated |

---

## 🚀 Ready to Begin PR-027?

All dependencies verified ✅. Starting with PR-027 (Telegram Webhook Router).

**Next**: Create `backend/app/telegram/` module with webhook endpoint and routing infrastructure.
