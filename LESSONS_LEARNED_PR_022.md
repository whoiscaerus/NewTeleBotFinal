# Lessons Learned - PR-022 Approvals API

## AuditService Integration Pattern

### Problem
Routes were calling `audit_service.record_event()` but AuditService class only has `record()` method, causing HTTP 500 errors.

### Wrong Way ❌
```python
# Instance creation when method is static
audit_service = AuditService(db)

# Calling non-existent method
await audit_service.record_event(
    actor_id=...,
    action=...,
    ip=client_ip,  # Wrong parameter name
)
```

### Right Way ✅
```python
# Call static method directly
await AuditService.record(
    db=db,  # Pass db explicitly for static method
    action="approval.approved",
    target="approval",
    actor_id=str(current_user.id),
    actor_role=current_user.role,
    target_id=str(approval.id),
    meta={...},
    ip_address=client_ip,  # Correct parameter name
    user_agent=user_agent,  # Correct parameter name
    status="success",
)
```

### Why It Works
- `AuditService.record()` is a @staticmethod (doesn't need instance)
- Parameters must match exact method signature: `ip_address`, not `ip`
- Always pass `status="success"` or `status="failure"`
- Pass all metadata (no PII/secrets) in `meta` dict

### Prevention
1. Always check if service method is @staticmethod or instance method
2. Read full method signature before calling
3. Use IDE autocomplete to see parameter names
4. Test audit logging with simple unit test first

---

## FastAPI Request Parameter Injection

### Problem
When extracting HTTP request context (headers, IP, etc.) in FastAPI routes, incorrect parameter handling causes type errors.

### Wrong Way ❌
```python
# Unnecessarily using Depends() for Request
def get_client_ip(request: Request = Depends()) -> str:
    return request.headers.get("x-forwarded-for")

# Making function async when no I/O occurs
async def get_client_ip(request: Request) -> str:
    return request.headers.get("x-forwarded-for")

# Then calling it with await
client_ip = await get_client_ip(request)
```

### Right Way ✅
```python
# FastAPI auto-injects Request - no Depends() needed
def get_client_ip(request: Request) -> str:
    # Only check forwarded header if present
    if forwarded := request.headers.get("x-forwarded-for"):
        return forwarded.split(",")[0].strip()
    # Fallback to client connection
    return request.client.host if request.client else "unknown"

# In route handler
@router.post("/approvals")
async def create_approval(
    request_data: ApprovalCreate,
    request: Request,  # FastAPI auto-injects
    db: AsyncSession = Depends(get_db),
):
    client_ip = get_client_ip(request)  # No await needed
```

### Why It Works
- FastAPI automatically injects Request objects
- `Depends()` is only needed for registered dependency functions
- Header reading is synchronous (no I/O), so function shouldn't be async
- Await is only needed for actual I/O operations (db.query, http calls, etc.)

### Prevention
1. Request extraction functions should be sync (not async)
2. Header reading functions don't need Depends()
3. Keep I/O and non-I/O operations separate
4. Use IDE hints - if there's no async operation, remove async

---

## SQLAlchemy Session Management - Modified Objects

### Problem
When modifying a related object (e.g., updating Signal status in approval service), changes weren't persisting to database even though db.commit() was called.

### Wrong Way ❌
```python
# Modify related object but don't add to session
signal = await db.get(Signal, signal_id)
signal.status = 1  # Mark as APPROVED

approval = Approval(...)
db.add(approval)  # Only add new approval
await db.commit()  # Signal changes lost!
```

### Right Way ✅
```python
# Add ALL modified objects to session
signal = await db.get(Signal, signal_id)
signal.status = 1  # Mark as APPROVED

approval = Approval(...)

# Add BOTH to session
db.add(approval)  # New object
db.add(signal)    # Modified object - CRITICAL!

await db.commit()  # Both changes persist
```

### Why It Works
- SQLAlchemy tracks new objects (via db.add())
- SQLAlchemy auto-tracks modified objects retrieved via db.get() or db.query()
- But for async sessions, be explicit and add() all changed objects
- db.commit() persists all objects in the session

### Prevention
1. Always add modified objects to session explicitly in async code
2. If object won't persist, add "db.add(object)" after modification
3. Test database state after operations (verify rows in DB)
4. Use db.refresh() after commit to reload fresh data

---

## Test Data Schema Validation

### Problem
Tests failed because test data didn't match Pydantic schema validators (e.g., instrument not in whitelist, side should be string not integer).

### Wrong Way ❌
```python
# Using invalid instrument (not in whitelist)
signal_data = {
    "instrument": "GOLD",  # Invalid - must be XAUUSD, EURUSD, etc.
    "side": 0,  # Wrong type - should be "buy" or "sell" string
    "price": 1950.50,
}

# Schema validation fails
response = await client.post("/api/v1/signals", json=signal_data)
# Result: 400 Bad Request before reaching route handler
```

### Right Way ✅
```python
# Use instruments from whitelist defined in schema
signal_data = {
    "instrument": "XAUUSD",  # Valid (in whitelist)
    "side": "buy",  # Correct type (string, valid enum)
    "price": 1950.50,
    "version": "1.0",  # For deduplication
}

response = await client.post("/api/v1/signals", json=signal_data)
# Result: 201 Created
```

### Valid Instruments (from whitelist)
- XAUUSD (Gold)
- EURUSD (EUR/USD)
- GBPUSD (GBP/USD)
- USDJPY (USD/JPY)
- AUDUSD (AUD/USD)
- NZDUSD (NZD/USD)
- USDCAD (USD/CAD)
- USDCHF (USD/CHF)
- EURGBP (EUR/GBP)
- EURJPY (EUR/JPY)

### Valid Decisions (Approvals)
- "approved"
- "rejected"

### Prevention
1. Always check model definition for validators
2. Read the @validator decorators in schema.py
3. Check Pydantic config for any constraints
4. In tests, create fixtures with valid data
5. Use model.model_dump() to see what's expected

---

## UUID to String Conversion Pattern

### Problem
FastAPI/Pydantic expects string UUIDs in JSON, but user.id might be UUID object. Type mismatch causes validation errors or strange behavior.

### Wrong Way ❌
```python
# Passing UUID object when string expected
user_id = current_user.id  # UUID object
approval = Approval(
    user_id=user_id  # Fails if schema expects string
)

# Or in audit logging
await AuditService.record(
    actor_id=current_user.id,  # UUID not converted
)
```

### Right Way ✅
```python
# Always convert UUID to string for API/schema layer
user_id = str(current_user.id)
approval = Approval(
    user_id=user_id  # Now string
)

# In audit logging
await AuditService.record(
    actor_id=str(current_user.id),  # Convert to string
    target_id=str(approval.id),
)
```

### Why It Works
- Pydantic schemas in FastAPI expect JSON-serializable types (strings)
- UUID objects aren't JSON serializable
- str(uuid) converts to standard UUID string format (e.g., "550e8400-e29b-41d4-a716-446655440000")
- Both SQLAlchemy and database drivers handle UUID↔string conversion
- Be consistent: convert at API boundary, not in core logic

### Prevention
1. Always convert UUIDs to strings when passing to external services
2. In route handlers, use str(current_user.id) for any external calls
3. In responses, Pydantic handles conversion (if field type is str)
4. Check ORM model - if it's UUID type, SQLAlchemy handles conversion
5. Use type hints to catch these: actor_id: str (not UUID)

---

## Error Investigation: HTTP 500 Debugging

### Symptoms → Root Cause Checklist

| Symptom | Check First | Second | Third |
|---------|------------|--------|-------|
| 500 on valid POST | Check audit service | Check metrics service | Check DB constraints |
| 400 on valid input | Check schema validators | Check @validator decorators | Check Pydantic config |
| 403 instead of 401 | Check get_current_user dependency | Check JWT header name | Check CORS preflight |
| Database constraint error | Check UNIQUE constraints | Check foreign keys | Check NOT NULL fields |
| Async/await TypeError | Check function is async | Check called with await | Check await on sync function |

### Debug Pattern for 500 Errors

1. **Enable detailed logging** - Add print() in each major step
2. **Wrap sections in try/except** - Find which step fails
3. **Check external service calls** - AuditService, metrics, DB
4. **Verify parameters match signature** - Method names, param names
5. **Test with curl or Postman** - Exclude test framework issues
6. **Check method vs function** - @staticmethod vs instance method
7. **Read error message** - Often includes which parameter is wrong

### Prevention
1. Always use try/except around external service calls
2. Log at start and end of each service call
3. Use type hints for all function parameters
4. Use IDE autocomplete to verify method signatures
5. Write unit tests for each service method separately

---

## Summary

**Three Critical Patterns for PR-022 Success**:

1. **AuditService**: Use static method `AuditService.record()` with exact parameter names (`ip_address`, `user_agent`)
2. **FastAPI Requests**: No Depends() needed, functions can be sync for header extraction
3. **SQLAlchemy Async**: Add all modified objects to session before commit

**Test Data Validation**: Always check schema validators before writing test data

**UUID Handling**: Always convert to string when passing to external services/APIs

---

**Apply these patterns to all future PRs for faster, more reliable implementation.** ✅
