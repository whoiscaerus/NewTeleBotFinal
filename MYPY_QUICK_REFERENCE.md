# MYPY Type Checking Fixes - Quick Reference

## Problem Solved
- **Issue**: 53 mypy type checking errors blocking GitHub Actions CI/CD
- **Root Cause**: Type annotation mismatches, missing casts, optional type guards
- **Solution**: Complete type annotation overhaul across 21 files
- **Result**: 100% error resolution, type checking stage unblocked

## Common Patterns Fixed

### 1. SQLAlchemy Sequence → List
```python
# WRONG
result = db.execute(select(...)).scalars().all()
return result  # Type: Sequence[T], but function expects list[T]

# CORRECT
result = db.execute(select(...)).scalars().all()
return list(result)
```
**Files**: trading/query_service.py, trading/reconciliation/*.py, telegram/handlers/*.py

### 2. Redis Cache Returns
```python
# WRONG
cached = self.redis.get(key)
return json.loads(cached)  # Type error: Any not compatible with str

# CORRECT
cached = self.redis.get(key)
cached_str = cast(str | bytes | bytearray, cached)
return cast(dict[str, Any], json.loads(cached_str))
```
**Files**: billing/security.py, core/idempotency.py

### 3. Service Method Returns (Any type)
```python
# WRONG
result = await self.stripe_handler.handle_checkout(event)
return result  # Type error: no-any-return

# CORRECT
result = await self.stripe_handler.handle_checkout(event)
return cast(dict[str, Any], result)
```
**Files**: billing/webhooks.py, billing/routes.py, billing/gates.py

### 4. Optional Type Guards
```python
# WRONG
if self.db_session:
    self.db_session.add(obj)  # Type error: db_session could be None

# CORRECT
if self.db_session is not None:
    self.db_session.add(obj)
    await self.db_session.commit()
```
**Files**: telegram/scheduler.py, marketing/scheduler.py

### 5. Dict Literal Type Consistency
```python
# WRONG
result_entry = {
    "chat_id": chat_id,      # int
    "message_id": msg.id,    # int
    "success": True          # bool
}  # Infers mixed types, conflicts with dict[str, Any]

# CORRECT
result_entry = {
    "chat_id": str(chat_id),  # Force string
    "message_id": msg.id,     # int is OK
    "success": True
}
```
**Files**: telegram/handlers/distribution.py

### 6. Union Type Syntax (Python 3.10+)
```python
# OLD (still works)
from typing import Optional, Union
value: Optional[str] = None  # Union[str, None]

# NEW (Python 3.10+ preferred, ruff UP038)
value: str | None = None
isinstance(x, (str, int))  # becomes
isinstance(x, str | int)
```
**Files**: media/render.py, core/redis_cache.py

### 7. Import Naming Conflicts
```python
# WRONG
from PIL import Image
Image = None  # Type error: can't assign None to Module type

# CORRECT
from PIL import Image as PILImage
PILImage = None  # type: ignore (or use actual Optional pattern)

# Then use PILImage.new(), PILImage.open(), etc.
```
**Files**: media/render.py

### 8. Function Return Type Casts
```python
# WRONG
async def process(fn):
    response = await fn()
    return response  # Type error: Any not dict[str, Any]

# CORRECT
async def process(fn):
    response = await fn()
    return cast(dict[str, Any], response)
```
**Files**: core/idempotency.py

## How to Apply These Fixes

### Step 1: Identify mypy errors
```bash
.venv/Scripts/python.exe -m mypy app --config-file=../mypy.ini
```

### Step 2: Categorize by type
- **Sequence vs list**: Use `list(result.scalars().all())`
- **Any type**: Use `cast(ExpectedType, value)`
- **Optional checks**: Use `if x is not None:`
- **Union syntax**: Use `T | None` not `Optional[T]`

### Step 3: Fix and validate
```bash
.venv/Scripts/python.exe -m black backend/app/
.venv/Scripts/python.exe -m ruff check backend/app/ --fix
.venv/Scripts/python.exe -m mypy app --config-file=../mypy.ini
```

### Step 4: Pre-commit verification
```bash
cd <repo> && git add . && git commit -m "message"
# Pre-commit hooks will validate: black, ruff, mypy
```

## Key Type Imports

```python
from typing import cast, Any, Optional, Union
# Python 3.10+: prefer X | Y over Union[X, Y]
# Python 3.10+: prefer T | None over Optional[T]
```

## Common mypy Error Messages

| Error | Cause | Fix |
|-------|-------|-----|
| `Sequence vs list` | SQLAlchemy return type | `list(result)` |
| `no-any-return` | Returning Any type | `cast(ExpectedType, value)` |
| `Argument X has incompatible type` | Type mismatch in function call | `cast()` or type annotation |
| `Union-attr` | Accessing attribute on Optional | `if x is not None:` |
| `Dict entry has incompatible type` | Dict value type mismatch | `str(value)` or consistent types |

## Pre-commit Hooks Used

1. **Black**: Python formatter (88 char lines)
2. **Ruff**: Python linter
   - UP038: Modern type hints (X | Y syntax)
   - Other style checks
3. **mypy**: Type checker (strict mode)

## Verification Checklist

- [ ] All mypy errors resolved (0 errors)
- [ ] Black formatting applied
- [ ] Ruff linting passed
- [ ] Pre-commit hooks pass
- [ ] Commit message comprehensive
- [ ] Pushed to GitHub main
- [ ] GitHub Actions type checking stage passes

## Files Most Likely to Have Type Issues

1. **Telegram module**: async/await, Telegram API returns
2. **Trading module**: SQLAlchemy queries, MT5 integration
3. **Billing module**: Stripe API, payment flows
4. **Core module**: Redis cache, idempotency
5. **Media module**: PIL/Pillow operations, image processing

## Prevention Tips

- Add type hints immediately when writing functions
- Use `mypy: disable-error-code=no-any-return` carefully (only last resort)
- Test with `mypy app --config-file=../mypy.ini` before committing
- Cast external API returns explicitly (never assume type)
- Use `assert isinstance(x, Type)` for runtime narrowing when needed

---

**Last Updated**: October 28, 2025 (Session: MYPY_FIXES_COMPLETE)
**Reference**: Commit b53beca
**Status**: ✅ All 53 errors resolved
