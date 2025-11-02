# PR-046: Environment Variables Configuration

## Overview

PR-046 (Copy-Trading Risk & Compliance Controls) requires configuration of risk parameters and control flags. All values use environment variables to support development, testing, and production deployments.

## Required Variables

### Risk Parameters (Copy-Trading Guard Rails)

| Variable | Type | Default | Range | Description |
|----------|------|---------|-------|-------------|
| `COPY_MAX_LEVERAGE` | float | 5.0 | 1.0 - 10.0 | Maximum allowed leverage per trade (1x = no leverage) |
| `COPY_MAX_TRADE_RISK_PCT` | float | 2.0 | 0.1 - 10.0 | Maximum risk per single trade (% of account equity) |
| `COPY_MAX_EXPOSURE_PCT` | float | 50.0 | 20.0 - 100.0 | Maximum total exposure (all positions combined, % of equity) |
| `COPY_DAILY_STOP_PCT` | float | 10.0 | 1.0 - 50.0 | Daily stop-loss (max loss per day, % of equity) |

### Control Flags

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `COPY_TRADING_ENABLED` | bool | true | Global switch to enable/disable copy-trading feature |
| `COPY_AUTO_PAUSE_ON_BREACH` | bool | true | Auto-pause accounts on breach (if false, only alerts) |
| `COPY_AUTO_RESUME_AFTER_24H` | bool | true | Auto-resume after 24-hour pause window |
| `COPY_FORCE_DISCLOSURE_ACCEPTANCE` | bool | true | Force users to accept current disclosure before trading |
| `COPY_TELEGRAM_ALERTS_ENABLED` | bool | true | Send Telegram alerts on breaches/pauses (if available) |

### Service Integrations

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AUDIT_SERVICE_ENABLED` | bool | true | Log all risk events to audit trail (PR-008 integration) |
| `TELEGRAM_SERVICE_ENABLED` | bool | true | Send Telegram alerts on risk events |
| `PROMETHEUS_METRICS_ENABLED` | bool | true | Export Prometheus metrics for monitoring |

## Example Configuration Files

### Development (.env.development)

```bash
# Copy-Trading Feature
COPY_TRADING_ENABLED=true
COPY_AUTO_PAUSE_ON_BREACH=true
COPY_AUTO_RESUME_AFTER_24H=true
COPY_FORCE_DISCLOSURE_ACCEPTANCE=true

# Risk Parameters (Lenient for testing)
COPY_MAX_LEVERAGE=10.0
COPY_MAX_TRADE_RISK_PCT=5.0
COPY_MAX_EXPOSURE_PCT=100.0
COPY_DAILY_STOP_PCT=50.0

# Alerts (Enabled for testing)
COPY_TELEGRAM_ALERTS_ENABLED=true
AUDIT_SERVICE_ENABLED=true
PROMETHEUS_METRICS_ENABLED=true
```

### Testing (.env.test)

```bash
# Copy-Trading Feature
COPY_TRADING_ENABLED=true
COPY_AUTO_PAUSE_ON_BREACH=true
COPY_AUTO_RESUME_AFTER_24H=false  # Disable auto-resume in tests
COPY_FORCE_DISCLOSURE_ACCEPTANCE=true

# Risk Parameters (Strict for comprehensive testing)
COPY_MAX_LEVERAGE=2.0
COPY_MAX_TRADE_RISK_PCT=1.0
COPY_MAX_EXPOSURE_PCT=30.0
COPY_DAILY_STOP_PCT=5.0

# Alerts (Disabled for tests - use mocks)
COPY_TELEGRAM_ALERTS_ENABLED=false
AUDIT_SERVICE_ENABLED=false
PROMETHEUS_METRICS_ENABLED=false
```

### Production (.env.production)

```bash
# Copy-Trading Feature
COPY_TRADING_ENABLED=true
COPY_AUTO_PAUSE_ON_BREACH=true
COPY_AUTO_RESUME_AFTER_24H=true
COPY_FORCE_DISCLOSURE_ACCEPTANCE=true

# Risk Parameters (Strict for production safety)
COPY_MAX_LEVERAGE=5.0
COPY_MAX_TRADE_RISK_PCT=2.0
COPY_MAX_EXPOSURE_PCT=50.0
COPY_DAILY_STOP_PCT=10.0

# Alerts (All enabled for monitoring)
COPY_TELEGRAM_ALERTS_ENABLED=true
AUDIT_SERVICE_ENABLED=true
PROMETHEUS_METRICS_ENABLED=true
```

## Configuration in Code

### Backend (Python/FastAPI)

```python
# backend/app/core/config.py
from pydantic import BaseSettings
from typing import Optional

class CopyTradingSettings(BaseSettings):
    """Copy-trading configuration from environment variables."""

    # Feature flags
    enabled: bool = True
    auto_pause_on_breach: bool = True
    auto_resume_after_24h: bool = True
    force_disclosure_acceptance: bool = True
    telegram_alerts_enabled: bool = True

    # Risk parameters
    max_leverage: float = 5.0
    max_trade_risk_percent: float = 2.0
    max_exposure_percent: float = 50.0
    daily_stop_percent: float = 10.0

    # Service integrations
    audit_service_enabled: bool = True
    prometheus_metrics_enabled: bool = True

    class Config:
        env_prefix = "COPY_"
        case_sensitive = False

# Initialize in main app
from backend.app.core.config import settings

copy_trading_settings = CopyTradingSettings()
```

### Usage in Risk Evaluator

```python
# backend/app/copytrading/risk.py
from backend.app.core.config import CopyTradingSettings

class RiskEvaluator:
    def __init__(self, config: CopyTradingSettings):
        self.max_leverage = config.max_leverage
        self.max_trade_risk_pct = config.max_trade_risk_percent
        self.max_exposure_pct = config.max_exposure_percent
        self.daily_stop_pct = config.daily_stop_percent
        self.auto_pause = config.auto_pause_on_breach

    async def evaluate_risk(self, db, user_id, trade, account_state):
        # Check against configured parameters
        risk_pct = (risk_amount / account_state["equity"]) * 100
        if risk_pct > self.max_trade_risk_pct:
            return False, "Risk exceeds maximum"
        return True, None
```

## Loading Variables at Runtime

### Option 1: Python-dotenv (Recommended)

```bash
pip install python-dotenv
```

```python
# backend/app/core/config.py
from dotenv import load_dotenv
import os

# Load from .env file
load_dotenv()

# Access variables
max_leverage = float(os.getenv("COPY_MAX_LEVERAGE", "5.0"))
max_trade_risk = float(os.getenv("COPY_MAX_TRADE_RISK_PCT", "2.0"))
```

### Option 2: Docker Secrets (Production)

```dockerfile
# Dockerfile
ENV COPY_MAX_LEVERAGE=5.0
ENV COPY_MAX_TRADE_RISK_PCT=2.0
ENV COPY_MAX_EXPOSURE_PCT=50.0
ENV COPY_DAILY_STOP_PCT=10.0
```

Or pass at runtime:

```bash
docker run \
  -e COPY_MAX_LEVERAGE=5.0 \
  -e COPY_MAX_TRADE_RISK_PCT=2.0 \
  ...
  my-app:latest
```

### Option 3: Kubernetes ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: copy-trading-config
data:
  COPY_MAX_LEVERAGE: "5.0"
  COPY_MAX_TRADE_RISK_PCT: "2.0"
  COPY_MAX_EXPOSURE_PCT: "50.0"
  COPY_DAILY_STOP_PCT: "10.0"
  COPY_AUTO_PAUSE_ON_BREACH: "true"
  COPY_FORCE_DISCLOSURE_ACCEPTANCE: "true"
---
apiVersion: v1
kind: Pod
metadata:
  name: app-pod
spec:
  containers:
  - name: app
    image: my-app:latest
    envFrom:
    - configMapRef:
        name: copy-trading-config
```

## Validation

### At Startup

```python
# backend/app/core/config.py
def validate_copy_trading_config():
    """Validate copy-trading configuration on startup."""
    config = CopyTradingSettings()

    # Validate ranges
    if not (1.0 <= config.max_leverage <= 10.0):
        raise ValueError(f"COPY_MAX_LEVERAGE must be 1.0-10.0, got {config.max_leverage}")

    if not (0.1 <= config.max_trade_risk_percent <= 10.0):
        raise ValueError(f"COPY_MAX_TRADE_RISK_PCT must be 0.1-10.0, got {config.max_trade_risk_percent}")

    if not (20.0 <= config.max_exposure_percent <= 100.0):
        raise ValueError(f"COPY_MAX_EXPOSURE_PCT must be 20-100, got {config.max_exposure_percent}")

    if not (1.0 <= config.daily_stop_percent <= 50.0):
        raise ValueError(f"COPY_DAILY_STOP_PCT must be 1-50, got {config.daily_stop_percent}")

    logger.info("Copy-trading configuration validated", extra={
        "max_leverage": config.max_leverage,
        "max_trade_risk_pct": config.max_trade_risk_percent,
        "max_exposure_pct": config.max_exposure_percent,
        "daily_stop_pct": config.daily_stop_percent,
    })

# Call in FastAPI lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    validate_copy_trading_config()
    yield
    # Shutdown

app = FastAPI(lifespan=lifespan)
```

## Monitoring Environment Variables

### Endpoint to Check Configuration (Admin Only)

```python
# backend/app/admin/routes.py
from backend.app.core.config import CopyTradingSettings

@router.get("/api/v1/admin/config/copy-trading", tags=["admin"])
async def get_copy_trading_config(current_user: User = Depends(get_current_user)):
    """Get current copy-trading configuration (admin only)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin required")

    config = CopyTradingSettings()
    return {
        "max_leverage": config.max_leverage,
        "max_trade_risk_pct": config.max_trade_risk_percent,
        "max_exposure_pct": config.max_exposure_percent,
        "daily_stop_pct": config.daily_stop_percent,
        "auto_pause_on_breach": config.auto_pause_on_breach,
        "auto_resume_after_24h": config.auto_resume_after_24h,
        "telegram_alerts_enabled": config.telegram_alerts_enabled,
    }
```

## Testing with Different Configurations

### pytest with custom env vars

```python
# backend/tests/conftest.py
import pytest
import os

@pytest.fixture
def copy_trading_config_strict():
    """Fixture with strict copy-trading config for testing."""
    os.environ["COPY_MAX_LEVERAGE"] = "2.0"
    os.environ["COPY_MAX_TRADE_RISK_PCT"] = "1.0"
    os.environ["COPY_MAX_EXPOSURE_PCT"] = "30.0"
    os.environ["COPY_DAILY_STOP_PCT"] = "5.0"
    yield
    # Cleanup
    del os.environ["COPY_MAX_LEVERAGE"]
    del os.environ["COPY_MAX_TRADE_RISK_PCT"]
    del os.environ["COPY_MAX_EXPOSURE_PCT"]
    del os.environ["COPY_DAILY_STOP_PCT"]

# Usage in tests
async def test_breach_with_strict_config(copy_trading_config_strict):
    risk_evaluator = RiskEvaluator()
    assert risk_evaluator.max_leverage == 2.0
```

## Troubleshooting

### Configuration Not Loading

**Problem**: Variables not updating when .env changes

**Solution**: Restart the app (docker container or local server) - python-dotenv loads once at startup

```bash
# Reload .env
docker restart app-container
# OR locally
# Stop: Ctrl+C
# Modify .env
# Restart: python -m uvicorn backend.main:app
```

### Wrong Values in Production

**Problem**: Strict test config accidentally deployed to production

**Solution**: Use separate .env files per environment

```bash
# Load correct file at startup
export ENV=production  # Set to development, testing, or production
python -m uvicorn backend.main:app --env-file .env.${ENV}
```

### Values Not Validated

**Problem**: Invalid config values not caught until runtime

**Solution**: Call validation at startup (included in lifespan fixture above)

```python
# This catches invalid values on app startup, not at runtime
validate_copy_trading_config()
```

## Reference

- **PR-046 Master Spec**: `/base_files/Final_Master_Prs.md` (search "PR-046:")
- **Implementation**: `backend/app/copytrading/risk.py`, `backend/app/copytrading/disclosures.py`
- **Config Class**: `backend/app/core/config.py`
- **Test Configuration**: `backend/tests/conftest.py`
