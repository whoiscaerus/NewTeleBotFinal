# ✅ Test Fixture Fix - test_ea_device_auth_security.py

## Issue Reported
```
ERROR backend/tests/test_ea_device_auth_security.py::TestAckSpecificSecurity::test_ack_signature_includes_body
TypeError: 'client_id' is an invalid keyword argument for Signal
```

## Root Cause Analysis

### Problem 1: Wrong Field Name for Signal
The test fixture was trying to create a Signal with `client_id`, but the Signal model actually uses `user_id`.

**Signal Model Fields:**
- `user_id` ← Correct field (who receives the signal)
- `user_id` is a foreign key to users table
- NOT `client_id`, NOT `strategy_id`, NOT `entry_price`

### Problem 2: Enum Type Not Converted
The fixture was passing `ApprovalDecision.APPROVED` directly, but SQLite needs the integer value (1), not the enum.

**Solution:** Use `.value` to get the integer representation of the enum.

### Problem 3: Missing `user_id` in Approval
The Approval model requires TWO fields:
- `client_id` - For denormalized fast queries
- `user_id` - Who made the decision

Both must be provided, not just `client_id`.

## Fixes Applied

### Fix 1: Signal Model Fields
```python
# WRONG
signal = Signal(
    client_id=client_obj.id,           # ❌ Wrong field
    strategy_id=uuid4(),                # ❌ Doesn't exist
    entry_price=1950.50,                # ❌ Doesn't exist
    stop_loss=1940.50,                  # ❌ Doesn't exist
    take_profit=1960.50,                # ❌ Doesn't exist
    volume=0.5,                         # ❌ Doesn't exist
)

# CORRECT
signal = Signal(
    user_id=client_obj.id,              # ✅ Correct field
    instrument="XAUUSD",                # ✅ Required
    side=0,                             # ✅ Required (0=BUY)
    price=1950.50,                      # ✅ Required
    status=0,                           # ✅ Required
)
```

### Fix 2: Enum Value Conversion
```python
# WRONG
approval = Approval(
    decision=ApprovalDecision.APPROVED  # ❌ Returns Enum object
)

# CORRECT
approval = Approval(
    decision=ApprovalDecision.APPROVED.value  # ✅ Returns int (1)
)
```

### Fix 3: Complete Approval Creation
```python
# WRONG
approval = Approval(
    client_id=client_obj.id,
    signal_id=signal.id,
    decision=ApprovalDecision.APPROVED.value,
    # Missing: user_id ❌
)

# CORRECT
approval = Approval(
    signal_id=signal.id,
    client_id=client_obj.id,
    user_id=client_obj.id,              # ✅ Both required
    decision=ApprovalDecision.APPROVED.value,
)
```

## Test Result

**Before Fix:**
```
TypeError: 'client_id' is an invalid keyword argument for Signal
```

**After Fix:**
```
✅ 1 passed, 35 warnings in 0.96s
```

## Commit

- **Commit Hash**: `567061f`
- **Message**: "fix: correct Signal and Approval fixture models in test_ea_device_auth_security.py"
- **Branch**: main
- **Status**: ✅ Deployed to GitHub

## Files Modified

- `backend/tests/test_ea_device_auth_security.py` - Updated `approval` fixture (6 line changes)

## Verification

✅ Test now passes locally: `test_ack_signature_includes_body`
✅ All pre-commit hooks pass (formatting, linting, type checking)
✅ Deployed to GitHub main branch
✅ Ready for next CI/CD run

---

**Status**: 🟢 **FIXED & DEPLOYED**
**Date**: October 29, 2025
