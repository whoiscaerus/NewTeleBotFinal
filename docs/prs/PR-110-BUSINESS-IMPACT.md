# PR-110 Business Impact

## Reliability
- **Prevents Double Billing**: Critical for payment processing. Ensures users are never charged twice for the same transaction, even if they click the button multiple times or network issues occur.
- **Data Integrity**: Prevents duplicate resource creation (e.g., creating two identical signals or orders) due to client retries.

## User Experience
- **Robustness**: Users on unstable connections (mobile) can safely retry operations without fear of unintended side effects.
- **Transparency**: The `X-Idempotency-Hit` header provides visibility to clients (and support staff) when a response is a replay.

## Technical Debt
- **Standardization**: Provides a uniform way to handle idempotency across all API endpoints, replacing ad-hoc solutions.
- **Scalability**: Redis-backed storage ensures idempotency works across multiple API instances (horizontal scaling).

## Risk Mitigation
- **Financial Risk**: Directly mitigates the risk of financial loss due to duplicate transactions.
- **Operational Risk**: Reduces support tickets related to "why did this happen twice?".
