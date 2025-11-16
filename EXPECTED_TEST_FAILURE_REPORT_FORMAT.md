# Expected Test Failure Report Format - Examples

This document shows what the detailed test failure reports will look like after the next GitHub Actions run.

---

## Example 1: TEST_FAILURES_DETAILED.md (Markdown Report)

```markdown
# Comprehensive Test Failure Analysis

**Generated**: 2024-01-17 14:32:15 UTC

## Executive Summary

- **Total Tests**: 6424
- **Passed**: 6254 ✅
- **Failed**: 127 ❌
- **Errors**: 43 🔥
- **Skipped**: 0 ⏭️
- **Duration**: 342.45s

**Pass Rate**: 97.3% (6254/6424)

## Failures by File

### backend/tests/test_telegram_bot.py

**Count**: 5 failed

#### test_telegram_command_start_no_user

**Status**: ❌ FAILED

**Error Message**:
```
AssertionError: Message not sent to Telegram API
```

**Stack Trace**:
```
File "backend/tests/test_telegram_bot.py", line 234, in test_telegram_command_start_no_user
  assert mock_telegram.send_message.called
AssertionError: Message not sent to Telegram API
```

---

#### test_telegram_auth_invalid_token

**Status**: ❌ FAILED

**Error Message**:
```
ValueError: Invalid authentication token format
```

**Assertion Failed**:
```
ValueError: Invalid authentication token format
Expected: Valid token format
Received: "invalid-token-xyz"
```

**Stack Trace**:
```
File "backend/app/telegram/auth.py", line 45, in validate_token
  raise ValueError(f"Invalid token format: {token}")
File "backend/tests/test_telegram_bot.py", line 156, in test_telegram_auth_invalid_token
  validate_token("invalid-token-xyz")
```

---

#### test_telegram_rate_limit_exceeded

**Status**: ❌ FAILED

**Error Message**:
```
AssertionError: Rate limit not enforced
Expected: HTTPException(429)
Received: HTTPException(200)
```

**Stack Trace**:
```
File "backend/tests/test_telegram_bot.py", line 301, in test_telegram_rate_limit_exceeded
  assert response.status_code == 429
AssertionError: 200 != 429
```

---

### backend/tests/test_signal_validation.py

**Count**: 3 failed

#### test_signal_price_range_too_high

**Status**: ❌ FAILED

**Error Message**:
```
ValueError: Signal price 999999.99 exceeds maximum allowed: 100000.00
```

**Stack Trace**:
```
File "backend/app/signals/validators.py", line 78, in validate_price
  if price > MAX_SIGNAL_PRICE:
      raise ValueError(f"Signal price {price} exceeds maximum allowed: {MAX_SIGNAL_PRICE}")
File "backend/tests/test_signal_validation.py", line 145, in test_signal_price_range_too_high
  validate_price(999999.99)
```

---

## Errors by File

### backend/tests/test_database_connection.py

**Count**: 2 errors

#### test_postgres_connection_timeout

**Status**: 🔥 ERROR

**Error Message**:
```
psycopg2.OperationalError: could not connect to server: Connection timed out
    Is the server running on host "localhost" (127.0.0.1) and accepting
    TCP/IP connections on port 5432?
```

**Stack Trace**:
```
File "backend/app/core/database.py", line 23, in get_db_connection
  conn = psycopg2.connect(DATABASE_URL)
File "backend/tests/test_database_connection.py", line 89, in test_postgres_connection_timeout
  async with get_db() as db:
ConnectionError: Connection timeout after 30 seconds
```

---

#### test_redis_connection_refused

**Status**: 🔥 ERROR

**Error Message**:
```
redis.exceptions.ConnectionError: Error 111 connecting to localhost:6379. Connection refused.
```

**Stack Trace**:
```
File "backend/app/core/cache.py", line 15, in get_redis_client
  return redis.Redis(host='localhost', port=6379)
File "backend/tests/test_database_connection.py", line 120, in test_redis_connection_refused
  cache = await get_cache_client()
ConnectionError: Connection refused to Redis
```

---

### backend/tests/test_api_integration.py

**Count**: 1 error

#### test_post_signal_missing_fields

**Status**: 🔥 ERROR

**Error Message**:
```
TypeError: __init__() missing 1 required positional argument: 'side'
```

**Stack Trace**:
```
File "backend/app/signals/models.py", line 15, in __init__
  self.side = side  # TypeError: missing 'side' parameter
File "backend/tests/test_api_integration.py", line 203, in test_post_signal_missing_fields
  signal = Signal(instrument="GOLD", price=1950.50)  # Missing 'side'
TypeError: __init__() missing 1 required positional argument: 'side'
```

---

## Skipped Tests by File

### backend/tests/test_advanced_analytics.py

**Count**: 2 skipped

- `test_ml_prediction_accuracy`: Requires TensorFlow (ML model not in test environment)
- `test_deep_neural_network`: ML dependencies not installed

### backend/tests/test_cloud_deployment.py

**Count**: 3 skipped

- `test_aws_lambda_execution`: AWS credentials not configured in test environment
- `test_azure_blob_storage`: Azure account not available in CI
- `test_gcp_cloud_functions`: GCP credentials not provided

---

## Statistics

**Files with Failures**: 4
**Files with Errors**: 3
**Files with Skipped**: 2
**Total Affected Files**: 9 out of 248 test files

---

## Common Error Patterns

- `AssertionError`: 78 occurrences
- `ValueError`: 32 occurrences
- `ConnectionError`: 12 occurrences
- `TypeError`: 8 occurrences
- `TimeoutError`: 6 occurrences
- `KeyError`: 4 occurrences
- `AttributeError`: 2 occurrences
- `ImportError`: 1 occurrence

**Most Common**: AssertionError (61.4% of failures)

---

*Report generated on 2024-01-17T14:32:15.123456*
```

---

## Example 2: TEST_FAILURES.csv (Spreadsheet Format)

```csv
file,test_name,status,error_type,error_message,duration
backend/tests/test_telegram_bot.py,test_telegram_command_start_no_user,failed,AssertionError,Message not sent to Telegram API,0.234
backend/tests/test_telegram_bot.py,test_telegram_auth_invalid_token,failed,ValueError,Invalid authentication token format,0.156
backend/tests/test_telegram_bot.py,test_telegram_rate_limit_exceeded,failed,AssertionError,Rate limit not enforced,0.189
backend/tests/test_signal_validation.py,test_signal_price_range_too_high,failed,ValueError,Signal price exceeds maximum,0.123
backend/tests/test_signal_validation.py,test_signal_missing_instrument,failed,ValueError,Invalid instrument provided,0.145
backend/tests/test_database_connection.py,test_postgres_connection_timeout,error,ConnectionError,Connection timed out after 30 seconds,30.001
backend/tests/test_database_connection.py,test_redis_connection_refused,error,ConnectionError,Connection refused to Redis,2.345
backend/tests/test_api_integration.py,test_post_signal_missing_fields,error,TypeError,Missing required positional argument: side,0.089
```

---

## Example 3: Understanding Report Contents

### How to Read the Markdown Report:

1. **Executive Summary Section**
   - Quick stats at a glance
   - Pass rate percentage
   - Total duration

2. **Failures by File Section**
   - Group 1: All failures in test_telegram_bot.py
   - Group 2: All failures in test_signal_validation.py
   - Each failure shows exact error message and stack trace
   - Click on file/test name to navigate

3. **Errors by File Section**
   - Similar structure but for runtime errors
   - Shows ConnectionError, TypeError, etc.
   - Stack traces help identify root cause

4. **Statistics Section**
   - Count of affected test files
   - Patterns in error types
   - Helps identify systemic issues

### How to Use the CSV Report:

1. **Open in Excel/Google Sheets**
   - One row per failure/error
   - Easy to sort and filter
   - Can add additional columns for tracking

2. **Filter by Error Type**
   - Filter by "error_type" column
   - Group similar issues together
   - Example: All ConnectionErrors together

3. **Sort by Duration**
   - Find slow tests
   - Optimize timing issues
   - Identify timeout problems

4. **Track Progress**
   - Download CSV after each run
   - Compare across runs
   - See if errors are increasing/decreasing

---

## What Each Error Type Means

| Error Type | Means | Action |
|------------|-------|--------|
| **AssertionError** | Test expected one value, got another | Fix business logic to match expected behavior |
| **ValueError** | Invalid input data | Improve input validation or test data |
| **ConnectionError** | Can't connect to external service | Check service availability (DB, Redis, API) |
| **TypeError** | Wrong data type provided | Fix type hints or function calls |
| **TimeoutError** | Operation took too long | Increase timeout or optimize performance |
| **KeyError** | Dictionary key not found | Check data structure or initialization |
| **AttributeError** | Object missing expected attribute | Check object initialization |
| **ImportError** | Module not found | Install missing dependency |

---

## How to Fix Issues Identified in Reports

### Step 1: Read the Report
- Open `TEST_FAILURES_DETAILED.md` in GitHub Actions artifact

### Step 2: Find Your Failure
- Locate file name in "Failures by File" section
- Read exact error message
- Review stack trace

### Step 3: Understand the Issue
- Error message tells you WHAT went wrong
- Stack trace tells you WHERE it went wrong
- Compare with actual code in that file

### Step 4: Fix Locally
```bash
# Example: test_telegram_bot.py has failures

# Run just that test file to debug
.venv/Scripts/python.exe -m pytest backend/tests/test_telegram_bot.py -v

# Run just one test
.venv/Scripts/python.exe -m pytest backend/tests/test_telegram_bot.py::test_telegram_command_start_no_user -v

# Get detailed output
.venv/Scripts/python.exe -m pytest backend/tests/test_telegram_bot.py -vv --tb=long
```

### Step 5: Verify Fix
```bash
# Run same test again
.venv/Scripts/python.exe -m pytest backend/tests/test_telegram_bot.py -v

# When it passes, run full suite
.venv/Scripts/python.exe -m pytest backend/tests/ -q --tb=short
```

### Step 6: Commit and Push
```bash
git add backend/tests/test_telegram_bot.py  # or whichever file you fixed
git commit -m "Fix: telegram bot tests [reason for fix]"
git push whoiscaerus main
```

### Step 7: CI Automatically Re-runs
- GitHub Actions triggers
- Reports generated again
- Verify your fix worked

---

## Expected Outcome

After all fixes are applied, the report should look like:

```markdown
# Comprehensive Test Failure Analysis

## Executive Summary

- **Total Tests**: 6424
- **Passed**: 6424 ✅
- **Failed**: 0 ❌
- **Errors**: 0 🔥
- **Skipped**: 0 ⏭️

**Pass Rate**: 100% 🎉 (6424/6424)

---

*No failures, errors, or skipped tests. All systems nominal!*
```

---

This is what you'll be able to see and work with after the workflow fix is deployed! 🚀
