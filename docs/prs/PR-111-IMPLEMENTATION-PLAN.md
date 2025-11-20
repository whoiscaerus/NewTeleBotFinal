# PR-111 Implementation Plan: Circuit Breakers

## 1. Overview
Implement the Circuit Breaker pattern for external API calls (Telegram, Brokers, Stripe) to prevent cascading failures when third-party services are down.

## 2. Technical Specification

### Files to Create/Modify
- `backend/app/core/circuit_breaker.py`: Base circuit breaker implementation (using `pybreaker` or custom).
- `backend/app/telegram/client.py`: Wrap Telegram API calls.
- `backend/app/trading/broker.py`: Wrap Broker API calls.
- `backend/tests/core/test_circuit_breaker.py`: Unit tests.

### Logic
1.  **States**: Closed (Normal), Open (Failing), Half-Open (Testing).
2.  **Config**:
    - Failure Threshold: 5 failures.
    - Recovery Timeout: 60 seconds.
3.  **Storage**: Use Redis to share state across worker processes.

### Dependencies
- `pybreaker` (need to add to `pyproject.toml`) or custom implementation using Redis.

## 3. Acceptance Criteria
- [ ] Circuit opens after N consecutive failures.
- [ ] Fast failure (no external call) when circuit is open.
- [ ] Circuit allows 1 test request after timeout (Half-Open).
- [ ] State is shared across multiple API workers (Redis).
