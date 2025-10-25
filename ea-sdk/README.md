# Caerus MT5 Expert Advisor SDK

Professional MT5 Expert Advisor with approval and copy-trading modes.

## Overview

The Caerus EA SDK provides a complete solution for connecting MetaTrader 5 trading systems to the Caerus platform:

- **Dual-Mode Operation**: Approval mode (manual confirmation) + Copy-Trading mode (automatic)
- **Secure Communication**: HMAC-SHA256 signatures + encrypted signal payloads
- **Risk Management**: Built-in position limits, spread guards, daily trade caps
- **Enterprise Features**: Extensive logging, audit trails, device management

## Architecture

```
┌─────────────────────────────────────────┐
│   MT5 Expert Advisor                    │
│  ┌──────────────┐      ┌──────────────┐ │
│  │ Approval     │      │ Copy-Trading │ │
│  │ Mode         │      │ Mode         │ │
│  └──────────────┘      └──────────────┘ │
└─────────────────────────────────────────┘
           │
        [HMAC-SHA256 Authentication]
           │
┌─────────────────────────────────────────┐
│   Caerus API Backend                    │
│  • Signal polling                       │
│  • AES-256-GCM encryption               │
│  • Execution acknowledgment             │
└─────────────────────────────────────────┘
```

## Modes

### Approval Mode (Default)

```
1. EA polls for pending signals every 10 seconds
2. User reviews signal in Telegram/Mini App
3. User clicks "Approve" in Telegram
4. EA executes when it next polls
5. EA sends ACK back to server
```

**Use Case**: Manual trading, learning, risk-averse traders

### Copy-Trading Mode

```
1. EA polls for signals
2. Signal auto-executes immediately
3. Applies risk multiplier (0.1x to 2.0x)
4. Enforces position caps
5. Sends ACK to server
```

**Use Case**: Hands-off automated trading, passive income

## Installation

### 1. Add to MetaTrader 5

Copy files to MT5 MQL5 directory:

```
C:\Users\<Username>\AppData\Roaming\MetaQuotes\Terminal\<TerminalID>\MQL5\
├── Include\
│   ├── caerus_auth.mqh
│   ├── caerus_http.mqh
│   └── caerus_models.mqh
└── Experts\
    └── ReferenceEA.mq5
```

### 2. Configure EA Inputs

In MetaTrader 5, open ReferenceEA and set inputs:

```
DEVICE_ID              = "ea_device_001"           # Unique device identifier
DEVICE_SECRET          = "device_secret_key_here"  # From registration
API_BASE               = "https://api.caerus.trading"
POLL_INTERVAL_SECONDS  = 10                        # Polling frequency
MAX_SPREAD_POINTS      = 50                        # Max bid-ask spread
AUTO_EXECUTE_COPY_TRADING = false/true             # Mode: false=approval, true=copy
MAX_POSITION_SIZE_LOT  = 1.0                       # Max trade size
```

### 3. Verify Connection

1. EA loads → Should show: "[Caerus EA] Initializing EA - Device: ea_device_001"
2. Wait for first poll → "[Caerus EA] Poll complete. Pending signals: 0"
3. If error → Check logs for auth failures or network issues

## API Reference

### Authentication

All requests include HMAC-SHA256 signature:

```
Authorization: CaerusHMAC <device_id>:<signature>:<nonce>:<timestamp>
```

**Components**:
- `device_id`: Unique device identifier
- `signature`: HMAC-SHA256(payload + nonce)
- `nonce`: Unique request identifier (timestamp + counter)
- `timestamp`: Unix timestamp (prevents replay attacks)

### Polling Endpoint

**Endpoint**: `GET /api/v1/devices/poll`

**Response**:

```json
{
  "signals": [
    {
      "id": "sig_001",
      "instrument": "XAUUSD",
      "side": 0,
      "entry_price": 1950.0,
      "stop_loss": 1930.0,
      "take_profit": 1980.0,
      "volume": 0.5
    }
  ],
  "timestamp": "2025-10-25T15:30:45Z"
}
```

**Payload Encryption**:
- Signals are encrypted with **AES-256-GCM**
- Per-device key derived from KDF
- Nonce prevents replay attacks

### Acknowledgment Endpoint

**Endpoint**: `POST /api/v1/devices/ack`

**Request**:

```json
{
  "signal_id": "sig_001",
  "order_ticket": 1000001,
  "status": 0,
  "error_message": ""
}
```

**Status Codes**:
- `0`: Successfully executed
- `1`: Rejected (user declined)
- `2`: Failed (execution error)

## Risk Management

### Spread Guard

Blocks trades if spread exceeds threshold:

```mql5
MAX_SPREAD_POINTS = 50  // Max 50 points (0.5 pips for XAUUSD)
```

If current spread > threshold → Trade rejected with "Spread too wide"

### Position Size Cap

Enforces maximum trade size:

```mql5
MAX_POSITION_SIZE_LOT = 1.0  // Max 1.0 lot per trade
```

If signal requires > 1.0 lot → Reduced to 1.0 lot

### Daily Trade Limit

Prevents excessive trading in single day:

```mql5
max_daily_trades = 50  // Max 50 trades per 24h
```

Once limit reached → No more trades until next day

### Position Count Limit

Limits concurrent positions per symbol:

```cpp
MAX_POSITIONS_PER_SYMBOL = 5  // Max 5 open trades on XAUUSD
```

## Copy-Trading Details

### Risk Multiplier

Scales all trade sizes:

```
Executed Volume = Signal Volume × Risk Multiplier

Example:
  Signal Volume: 1.0 lot
  Risk Multiplier: 0.8
  Executed Volume: 0.8 lot (20% reduction)
```

### Pricing Markup

Copy-trading tier includes +30% markup:

```
Base Price: $199/month (Pro plan)
Copy Price: $199 × 1.30 = $258.70/month
```

### Consent

Versioned consent text stored:

```
Version: 1.0
Accepted: 2025-10-25T10:00:00Z

User must accept current version before enabling copy-trading.
```

## Security

### HMAC-SHA256 Signatures

Every request signed with device secret:

```
Signature = HMAC-SHA256(payload + nonce, device_secret)
```

Server verifies signature → Prevents tampering

### Nonce-Based Replay Protection

Each request includes unique nonce:

```
Nonce = Timestamp + Counter
```

Server rejects duplicate nonces → Prevents replay attacks

### AES-256-GCM Encryption

Signal payloads encrypted:

```
Plaintext: JSON signal data
Key: Per-device key (PBKDF2 derived)
Nonce: 12-byte random
AAD: Device ID
Ciphertext: Encrypted signal (GCM mode)
```

Ensures confidentiality + integrity

### Key Rotation

Keys automatically rotated every 90 days:

```
1. New key generated with KDF
2. Old key marked for rotation (7-day grace period)
3. During grace period: Both keys accepted
4. After grace period: Old key rejected
5. Request new secret on rotation
```

## Troubleshooting

### "HTTP request failed"

**Cause**: Network connectivity issue  
**Solution**:
1. Check internet connection
2. Verify firewall allows HTTPS (port 443)
3. Check API_BASE URL is correct

### "Auth header mismatch"

**Cause**: Invalid HMAC signature  
**Solution**:
1. Verify DEVICE_SECRET is correct
2. Check device is registered
3. Regenerate secret if needed

### "Spread too wide"

**Cause**: Bid-ask spread > threshold  
**Solution**:
1. Wait for spread to tighten
2. Increase MAX_SPREAD_POINTS if needed
3. Trade during higher liquidity hours

### "Max positions reached"

**Cause**: Already have max trades open on symbol  
**Solution**:
1. Close unprofitable trades
2. Reduce MAX_POSITIONS_PER_SYMBOL if needed

## Performance Metrics

| Operation | Time | Target |
|-----------|------|--------|
| Poll latency | ~200ms | <500ms |
| Order execution | ~80ms | <100ms |
| HMAC signing | ~5ms | <10ms |
| ACK response | ~100ms | <200ms |

## Best Practices

1. **Start in Approval Mode**
   - Test EA in approval mode first
   - Monitor execution quality
   - Verify signals are profitable

2. **Set Conservative Limits**
   - Start with low position sizes
   - Set reasonable stop losses
   - Monitor daily P&L

3. **Monitor Logs**
   - Check EA logs regularly
   - Look for connection errors
   - Verify ACKs are sending

4. **Secure Credentials**
   - Never share DEVICE_SECRET
   - Rotate secret if compromised
   - Use strong passwords

5. **Test on Demo First**
   - Run on demo account first
   - Verify all signals and ACKs
   - Monitor for 24-48 hours

## Support

For issues or questions:

1. Check EA logs: `Experts\Logs\*.log`
2. Verify connection: Test polling manually
3. Contact support: support@caerus.trading
4. GitHub issues: https://github.com/caerus-trading/ea-sdk

## License

Proprietary - Caerus Trading Ltd.

All rights reserved.

## Changelog

### v1.0.0 (2025-10-25)

Initial release:
- ✅ Dual-mode EA (approval + copy-trading)
- ✅ HMAC-SHA256 authentication
- ✅ Signal polling + ACK
- ✅ Risk management (spread, position, daily limits)
- ✅ Comprehensive logging
