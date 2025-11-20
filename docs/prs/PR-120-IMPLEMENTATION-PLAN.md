# PR-120 Implementation Plan: WebSocket Integration

## 1. Overview
Replace polling with WebSockets for real-time updates of signals, orders, and account status on the frontend.

## 2. Technical Specification

### Files to Create/Modify
- `backend/app/main.py`: Add WebSocket endpoint `/ws`.
- `backend/app/core/websockets.py`: Connection manager (handle user auth, channels).
- `frontend/src/hooks/useSocket.ts`: React hook for WS connection.
- `frontend/src/components/dashboard/SignalFeed.tsx`: Update to use WS.

### Logic
1.  **Auth**: Authenticate WS connection using JWT (in query param or header).
2.  **Channels**: Subscribe to `user:{id}` and `signals:public`.
3.  **Broadcasting**: Use Redis Pub/Sub to broadcast messages from backend workers to WS server instances.

### Dependencies
- Redis Pub/Sub.

## 3. Acceptance Criteria
- [ ] Frontend receives "Signal Created" event <500ms after creation.
- [ ] Connection auto-reconnects on drop.
- [ ] Auth enforced (user only receives their own private events).
