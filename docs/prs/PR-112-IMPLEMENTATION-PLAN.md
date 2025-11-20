# PR-112 Implementation Plan: Risk Management Layer

## 1. Overview
Implement a pre-trade risk management layer to enforce account-level safety limits before any order is sent to a broker.

## 2. Technical Specification

### Files to Create/Modify
- `backend/app/trading/risk.py`: Risk engine logic.
- `backend/app/trading/models.py`: Add risk settings to User/Account.
- `backend/app/trading/service.py`: Integrate risk check before order placement.
- `backend/tests/trading/test_risk.py`: Unit tests.

### Logic
1.  **Checks**:
    - **Max Daily Loss**: Stop trading if daily P&L < -X%.
    - **Max Leverage**: Reject order if total exposure > X times equity.
    - **Max Position Size**: Reject if single trade > X% of account.
    - **Kill Switch**: Global or per-user flag to pause trading.
2.  **Data Source**: Redis for real-time P&L tracking (fast access).

## 3. Acceptance Criteria
- [ ] Trade rejected if Daily Loss limit hit.
- [ ] Trade rejected if Leverage limit hit.
- [ ] Admin can toggle Kill Switch to stop all new orders.
- [ ] Risk checks perform in <10ms (Redis).
