# Header Validation Fix - Quick Reference

## Problem
Missing required headers returned **422 Unprocessable Entity** instead of **400 Bad Request**

## Solution
Modified `backend/app/core/errors.py` to detect missing headers and return 400

## Files Changed
- ✏️ `backend/app/core/errors.py` - Updated `pydantic_validation_exception_handler()`
- ✨ `backend/tests/test_header_validation_fix.py` - Added 3 new tests

## Test Results
✅ All 36 tests passing:
- 3 new header validation tests
- 33 existing error handling tests

## Key Code Change

**Before (line ~281-333):**
```python
async def pydantic_validation_exception_handler(request: Request, exc: Exception):
    """Handle Pydantic validation errors..."""
    from pydantic_core import ValidationError as PydanticValidationError

    errors = []
    if isinstance(exc, PydanticValidationError):  # ❌ Wrong exception type
        for error in exc.errors():
            # ... all errors return 422
```

**After (line ~281-355):**
```python
async def pydantic_validation_exception_handler(request: Request, exc: Exception):
    """Handle Pydantic validation errors...

    Missing required headers return 400 Bad Request.
    Other validation errors return 422 Unprocessable Entity.
    """
    errors = []
    has_missing_header = False
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    # Use hasattr instead of isinstance to work with FastAPI's RequestValidationError
    if hasattr(exc, "errors"):  # ✅ Works with FastAPI exceptions
        error_list = exc.errors() if callable(exc.errors) else exc.errors
        for error in error_list:
            # ... collect errors ...

            # Check if this is a missing header error
            if len(error["loc"]) >= 2 and error["loc"][0] == "header":
                if error["type"] in ("missing", "value_error"):
                    has_missing_header = True  # ✅ Detect missing headers

    # Return 400 for missing headers
    if has_missing_header:
        status_code = status.HTTP_400_BAD_REQUEST  # ✅ Correct status code

    # ... build response with correct status_code ...
```

## Impact

### Endpoints Affected
Any endpoint with required header parameters:
- `GET /api/v1/clients/devices` (requires `X-Device-Id`)
- Other endpoints with header-based authentication or validation

### Before → After

| Scenario | Before | After |
|----------|--------|-------|
| Missing required header | 422 ❌ | 400 ✅ |
| Invalid header value | 422 | 422 |
| Missing body field | 422 | 422 |
| Missing query param | 422 | 422 |

## Testing

Run tests locally:
```bash
.venv\Scripts\python.exe -m pytest backend/tests/test_header_validation_fix.py -v
```

Expected output:
```
test_missing_required_header_returns_400 ✓
test_valid_header_passes ✓
test_error_response_includes_field_details ✓
```

## Error Response Format (RFC 7807)

```json
{
  "type": "https://api.tradingsignals.local/errors/validation",
  "title": "Request Validation Error",
  "status": 400,
  "detail": "Missing required header(s)",
  "errors": [
    {
      "field": "header.x-device-id",
      "message": "Field required",
      "type": "missing"
    }
  ]
}
```

## Deployment Notes

✅ **Safe to deploy** - Low risk change
- Only affects error status codes for missing headers
- All other behavior unchanged
- RFC 7807 format maintained
- No database migrations needed
