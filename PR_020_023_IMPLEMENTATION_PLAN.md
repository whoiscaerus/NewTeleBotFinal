# PR-020-023 Implementation Plan

## Overview
Implementing 4 critical PRs that bridge from trading core (P1A) to API layer (P1B):
- **PR-020**: Charting/Exports (matplotlib backend, caching)
- **PR-021**: Signals API (ingest, schema, dedupe, payload limits)
- **PR-022**: Approvals API (approve/reject, consent versioning, audit)
- **PR-023**: Reconciliation & Trade Monitoring (MT5 sync, auto-close, drawdown guard)

## Phase Transition
These PRs represent the **P1A → P1B transition**:
- P1A complete: MT5 connection, data fetching, strategy engine, order building, signal posting
- P1B begins: API-based ingestion, user approvals, trade reconciliation

## Dependencies Verification

### PR-020 Dependencies
- ✅ PR-001: Monorepo bootstrap
- ✅ PR-002: Settings/config
- (Standalone, can start immediately)

### PR-021 Dependencies
- ✅ PR-010: Database models baseline
- ✅ PR-006: Error handling/validation
- ✅ PR-004: Auth/RBAC

### PR-022 Dependencies
- ✅ PR-010: Database
- ✅ PR-021: Signals (must ingest before approving)
- ✅ PR-004: Auth
- ✅ PR-008: Audit logging

### PR-023 Dependencies
- ✅ PR-011: MT5 connection
- ✅ PR-016: Trade store
- ✅ PR-021: Signals API
- ✅ PR-022: Approvals
- ✅ PR-018: Alerts/retries

## Implementation Sequence

**Step 1: PR-020 (Charting)**
- Create backend/app/media/{render,storage}.py
- Implement matplotlib caching
- Test with mock chart data

**Step 2: PR-021 (Signals API)**
- Create signals models, service, routes
- Database migration (signals table)
- HMAC validation
- Deduplication logic

**Step 3: PR-022 (Approvals API)**
- Create approvals models, service, routes
- Database migration (approvals table)
- Consent versioning
- Audit integration

**Step 4: PR-023 (Reconciliation)**
- Create reconciliation service
- Create monitoring service (drawdown guard)
- Database migrations
- Real-time position sync

## Time Estimate: ~9 hours total
- PR-020: 2 hours
- PR-021: 2 hours
- PR-022: 2 hours
- PR-023: 3 hours

## Validation Checkpoints
After each PR:
1. Run local tests: pytest backend/tests -v
2. Check pre-commit: All hooks passing
3. Verify migrations: alembic upgrade head
4. Manual endpoint testing
5. Commit with comprehensive message
