# PR-102: NFT Access Feature Flag

**Status**: Disabled by default (staging only)

## Overview

Prototype tokenized access to mirrored strategies using NFT/token-based licensing.

**⚠️ IMPORTANT**: This feature is **NOT for production release**. It is a proof-of-concept behind a feature flag.

## Feature Flag

```bash
NFT_ACCESS_ENABLED=false  # MUST be false in production
```

## Environment Variables

```bash
# Feature toggle (default: false)
NFT_ACCESS_ENABLED=false

# Blockchain configuration (staging only)
WEB3_CHAIN_ID=1                        # Ethereum mainnet
WEB3_RPC_URL=https://eth.llamarpc.com  # Public RPC
NFT_CONTRACT_ADDRESS=0x...             # NFT contract address (staging)
```

## Security Constraints

### ✅ Allowed in Staging

- Internal testing with allowlisted wallets
- Minting NFTs for beta testers
- Verifying signature workflows
- Testing access checks

### ❌ Never in Production

- Public mint UI
- Critical feature gating (NFT access is **additive only**)
- Unauthenticated access checks without rate limiting
- On-chain minting without gas management

## How It Works

### 1. Wallet Linking (SIWE-Compatible)

User signs a message with their Web3 wallet to prove ownership:

```
Sign this message to link your wallet to your trading account.

User ID: 123e4567-e89b-12d3-a456-426614174000
Nonce: a1b2c3d4e5f6g7h8
Timestamp: 2025-11-11T10:30:00Z

This request will not trigger any blockchain transaction or cost any gas fees.
```

Backend verifies ECDSA signature using `eth-account` library.

### 2. NFT Minting (Owner/Admin Only)

Owner/admin can mint NFT access tokens via API:

```bash
POST /api/v1/web3/nft/mint
{
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "wallet_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
  "entitlement_key": "copy.mirror",
  "expires_at": "2026-01-01T00:00:00Z",  # Optional: time-locked
  "token_id": null,  # Optional: on-chain token ID
  "contract_address": null,  # Optional: NFT contract
  "chain_id": 1
}
```

### 3. Access Check

Services can check NFT access:

```bash
GET /api/v1/web3/access/{wallet_address}/{entitlement_key}
```

Returns:
```json
{
  "has_access": true,
  "nft": {
    "id": "nft_abc123",
    "entitlement_key": "copy.mirror",
    "expires_at": "2026-01-01T00:00:00Z",
    "is_active": true
  }
}
```

### 4. Revocation (Owner/Admin Only)

Owner/admin can revoke NFT access:

```bash
POST /api/v1/web3/nft/revoke
{
  "nft_id": "nft_abc123",
  "reason": "User violated terms of service"
}
```

## Database Schema

### `wallet_links` Table

Links Web3 wallets to user accounts.

| Column | Type | Description |
|--------|------|-------------|
| id | String(36) | Primary key |
| user_id | String(36) | Foreign key to users |
| wallet_address | String(42) | Ethereum address (0x...) |
| chain_id | Integer | Blockchain ID (1=Ethereum) |
| signature | String(132) | ECDSA signature |
| message | String(255) | Signed message |
| verified_at | DateTime | Verification timestamp |
| is_active | Integer | 0=revoked, 1=active |
| created_at | DateTime | Creation timestamp |
| revoked_at | DateTime | Revocation timestamp (nullable) |

**Indexes**: user_id, wallet_address (unique), is_active

### `nft_access` Table

NFT tokens representing feature access.

| Column | Type | Description |
|--------|------|-------------|
| id | String(36) | Primary key |
| user_id | String(36) | Foreign key to users |
| wallet_address | String(42) | Foreign key to wallet_links |
| entitlement_key | String(50) | Feature key (e.g., "copy.mirror") |
| token_id | String(100) | On-chain token ID (nullable) |
| contract_address | String(42) | NFT contract address (nullable) |
| chain_id | Integer | Blockchain ID |
| is_active | Integer | 0=revoked/expired, 1=active |
| minted_at | DateTime | Mint timestamp |
| expires_at | DateTime | Expiration timestamp (nullable = permanent) |
| revoked_at | DateTime | Revocation timestamp (nullable) |
| revoke_reason | String(255) | Reason for revocation (nullable) |
| meta | JSON | Additional metadata |

**Indexes**: user_id, wallet_address, entitlement_key, (is_active, expires_at)

## Entitlements

### Standard Entitlements (Tier-Based)

- `basic_access` (Free tier)
- `premium_signals` (Premium tier)
- `copy_trading` (VIP tier)
- `vip_support` (Enterprise tier)

### Web3 NFT-Based Entitlements (PR-102)

- `copy.mirror` - NFT-gated copy trading access
- `strategy.premium` - NFT-gated premium strategy access

**Naming Convention**: Web3 entitlements use dot notation (e.g., `copy.mirror`)

## Audit Trail

All NFT operations are logged to `audit_logs`:

| Action | Description |
|--------|-------------|
| `web3.wallet_link` | Wallet linked to user |
| `web3.wallet_revoke` | Wallet unlinked |
| `web3.nft_mint` | NFT access token minted |
| `web3.nft_revoke` | NFT access token revoked |
| `web3.nft_extend` | NFT expiry extended |

**Actor Role**: OWNER, ADMIN, USER, SYSTEM

## Telemetry

Prometheus metrics (when feature enabled):

```
# Access checks
nft_access_checks_total{result="granted|denied"}

# Minting
nft_mints_total

# Revocations
nft_revokes_total
```

## Testing in Staging

### 1. Enable Feature Flag

```bash
export NFT_ACCESS_ENABLED=true
export WEB3_CHAIN_ID=1
export WEB3_RPC_URL=https://eth.llamarpc.com
```

### 2. Allowlist Staging Wallets

Only specific wallets should be allowed in staging:

```
0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb  # Test wallet 1
0x5aEda56215b167893e80B4fE645BA6d5Bab767DE  # Test wallet 2
```

### 3. Test Workflow

1. Link wallet (sign message with MetaMask/WalletConnect)
2. Owner mints NFT for test user
3. Verify access check returns `has_access: true`
4. Owner revokes NFT
5. Verify access check returns `has_access: false`

## Production Rollout Plan (Future)

**DO NOT roll out without**:

1. Legal review of tokenized licensing terms
2. Gas management strategy for on-chain minting
3. Rate limiting on public access checks
4. Multi-chain support (Polygon, Arbitrum)
5. Smart contract audit for NFT contract
6. User education materials
7. KYC/AML compliance review

**Keep feature flag OFF** until all requirements met.

## Dependencies

- **PR-045/046** (copy-trading): NFT access can gate copy trading features
- **PR-093** (ledger): Optional blockchain proof integration
- **PR-008** (audit log): All mint/revoke operations logged

## See Also

- `backend/app/web3/nft_access.py` - Minting service
- `backend/app/web3/wallet_link.py` - Wallet linking service
- `backend/app/web3/routes.py` - API endpoints
- `backend/app/billing/entitlements/service.py` - Entitlements integration
- `backend/tests/test_pr_102_web3_comprehensive.py` - Test suite
