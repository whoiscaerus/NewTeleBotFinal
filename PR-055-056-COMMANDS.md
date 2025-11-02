# 🚀 PR-055 & PR-056: Quick Start Commands

## Installation & Setup

```bash
# Navigate to project
cd c:\Users\FCumm\NewTeleBotFinal

# Activate virtual environment (if not already active)
.venv\Scripts\Activate.ps1

# Install any missing dependencies (if needed)
pip install pytest pytest-asyncio pytest-cov

# Verify Python environment
.venv\Scripts\python.exe --version  # Should show 3.11.x
```

---

## Running Tests

### Option 1: Run All Tests (Recommended)
```bash
# Run both test suites with coverage reporting
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_055_exports.py backend/tests/test_pr_056_revenue.py -v --tb=short 2>&1 | tee test_results.txt
```

### Option 2: Run PR-055 Tests Only
```bash
# Test only analytics export functionality
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_055_exports.py -v
```

### Option 3: Run PR-056 Tests Only
```bash
# Test only revenue functionality
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_056_revenue.py -v
```

### Option 4: Run with Coverage Report
```bash
# Run tests and generate coverage report
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_055_exports.py backend/tests/test_pr_056_revenue.py --cov=backend/app/analytics --cov=backend/app/revenue --cov-report=html --cov-report=term-missing
```

---

## Database Setup

### Apply Migration
```bash
# Navigate to backend directory
cd backend

# Apply the migration
alembic upgrade head

# Verify tables were created
# (From PostgreSQL client)
\dt revenue_snapshots
\dt subscription_cohorts
```

### Verify Tables Exist
```bash
# Using psql directly
psql -U postgres -d <database_name> -c "SELECT * FROM revenue_snapshots LIMIT 1;"
psql -U postgres -d <database_name> -c "SELECT * FROM subscription_cohorts LIMIT 1;"
```

---

## Code Quality Checks

### Format Code with Black
```bash
# Format all Python files
.venv/Scripts/python.exe -m black backend/app/analytics backend/app/revenue

# Check formatting without modifying
.venv/Scripts/python.exe -m black --check backend/app/analytics backend/app/revenue
```

### Lint with Ruff
```bash
# Check for lint errors
.venv/Scripts/python.exe -m ruff check backend/app/analytics backend/app/revenue

# Fix automatically fixable issues
.venv/Scripts/python.exe -m ruff check --fix backend/app/analytics backend/app/revenue
```

### Security Scan with Bandit
```bash
# Scan for security issues
.venv/Scripts/python.exe -m bandit -r backend/app/analytics backend/app/revenue
```

---

## API Testing (Manual)

### Test CSV Export Endpoint
```bash
# Get JWT token first (or use existing test token)
TOKEN="your_jwt_token_here"

# Request CSV export
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/analytics/export/csv" \
  -o export.csv

# View CSV
cat export.csv
```

### Test JSON Export Endpoint
```bash
# Request JSON export with metrics
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/analytics/export/json?include_metrics=true" \
  -o export.json

# View JSON
cat export.json
```

### Test Revenue Summary Endpoint (Admin Only)
```bash
# Get admin JWT token
ADMIN_TOKEN="your_admin_jwt_token_here"

# Request revenue summary
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:8000/api/v1/revenue/summary" | jq
```

### Test Revenue Cohorts Endpoint
```bash
# Get 12-month cohort analysis
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:8000/api/v1/revenue/cohorts?months_back=12" | jq

# Get 24-month analysis
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:8000/api/v1/revenue/cohorts?months_back=24" | jq
```

### Test Revenue Snapshots Endpoint
```bash
# Get 90-day historical data
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:8000/api/v1/revenue/snapshots?days_back=90" | jq

# Get full year of data
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:8000/api/v1/revenue/snapshots?days_back=365" | jq
```

---

## Full Local Development Workflow

```bash
# 1. Setup
cd c:\Users\FCumm\NewTeleBotFinal
.venv\Scripts\Activate.ps1

# 2. Apply database changes
cd backend
alembic upgrade head
cd ..

# 3. Run tests
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_055_exports.py backend/tests/test_pr_056_revenue.py -v --cov --cov-report=html

# 4. Check coverage (should be 95%+)
# Open htmlcov/index.html in browser

# 5. Run code quality checks
.venv/Scripts/python.exe -m black backend/app/analytics backend/app/revenue
.venv/Scripts/python.exe -m ruff check --fix backend/app/analytics backend/app/revenue
.venv/Scripts/python.exe -m bandit -r backend/app/analytics backend/app/revenue

# 6. Commit changes
git add backend/app/analytics backend/app/revenue backend/tests/test_pr_055_exports.py backend/tests/test_pr_056_revenue.py backend/alembic/versions/0011_revenue_snapshots.py

git commit -m "feat(PR-055,056): Analytics export + Revenue dashboard"

# 7. Push to GitHub
git push origin <branch-name>

# 8. Monitor CI/CD (should all pass on GitHub Actions)
```

---

## Verification Checklist

### Post-Deployment Verification
```bash
# 1. Verify database migration applied
psql -c "SELECT COUNT(*) FROM revenue_snapshots;"
psql -c "SELECT COUNT(*) FROM subscription_cohorts;"

# 2. Verify API endpoints respond
curl -s "http://staging/api/v1/revenue/summary" -H "Authorization: Bearer <token>" | jq

# 3. Verify frontend dashboard loads
# Navigate to: http://staging/admin/revenue

# 4. Verify telemetry is being collected
# Check observability system for analytics_exports_total{type=csv|json}

# 5. Check logs for any errors
tail -f /var/log/app/backend.log | grep -i "revenue\|export"
```

---

## Environment Variables (if needed)

```bash
# .env file
ANALYTICS_EXPORT_TIMEOUT_SECONDS=30
REVENUE_SNAPSHOT_RETENTION_DAYS=365
REVENUE_CALCULATION_CACHE_TTL=300

# Application startup should load these
export $(cat .env | xargs)
```

---

## Troubleshooting

### Tests Fail with "ModuleNotFoundError"
```bash
# Solution: Use full Python path
# WRONG: python -m pytest ...
# CORRECT:
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_055_exports.py -v
```

### Database Migration Fails
```bash
# Check PostgreSQL is running
psql -c "SELECT 1;"

# Rollback previous migration if needed
alembic downgrade -1

# Re-apply migration
alembic upgrade head
```

### Async Test Failures
```bash
# Add pytest markers if tests are skipped
pytest backend/tests/test_pr_055_exports.py -v -m asyncio

# Check Python version (should be 3.11+)
python --version
```

### Coverage Below 95%
```bash
# Generate detailed coverage report
.venv/Scripts/python.exe -m pytest --cov=backend/app/analytics --cov=backend/app/revenue --cov-report=term-missing

# Find uncovered lines (marked with *)
# Add tests to cover those lines
```

---

## Performance Testing

### Load Test Export Endpoints
```bash
# Using Apache Bench (install: apt-get install apache2-utils)
ab -n 100 -c 10 -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/v1/analytics/export/csv"

ab -n 100 -c 10 -H "Authorization: Bearer <admin_token>" \
  "http://localhost:8000/api/v1/revenue/summary"
```

### Load Test with Concurrent Requests
```bash
# Using wrk (install: apt-get install wrk)
wrk -t4 -c100 -d30s -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/v1/analytics/export/csv"
```

---

## Documentation Files

All documentation files are located in the project root:

```bash
# View implementation status
cat PR-055-056-IMPLEMENTATION-COMPLETE.md

# Quick reference guide
cat PR-055-056-QUICK-REFERENCE.md

# Test documentation
cat PR-055-056-TEST-SUMMARY.md

# Files inventory
cat PR-055-056-FILES-INDEX.md

# Deployment checklist
cat PR-055-056-FINAL-CHECKLIST.md
```

---

## CI/CD Pipeline

### GitHub Actions (Automatic)

The pipeline runs automatically when you push:

```yaml
# .github/workflows/tests.yml
1. test-backend (pytest with coverage)
2. test-frontend (if applicable)
3. lint-python (black, ruff)
4. lint-frontend (eslint)
5. security-scan (bandit)
6. database-migrations (alembic check)
```

View results on GitHub: https://github.com/your-repo/actions

---

## Rollback Procedure

### If Deployment Fails

```bash
# Rollback database migration
cd backend
alembic downgrade -1
cd ..

# Revert code changes
git revert HEAD

# Push to GitHub
git push origin main
```

---

## Support & Debugging

### Enable Verbose Logging
```bash
# Run tests with verbose output
.venv/Scripts/python.exe -m pytest backend/tests/ -vv --log-cli-level=DEBUG

# Run with print-to-stderr
pytest -s backend/tests/test_pr_055_exports.py
```

### Check Test Execution Details
```bash
# Show test collection phase
.venv/Scripts/python.exe -m pytest backend/tests/ --collect-only

# Show fixtures
.venv/Scripts/python.exe -m pytest backend/tests/ --fixtures
```

---

## Summary

**All commands assume you're in**: `c:\Users\FCumm\NewTeleBotFinal`

**Key commands to remember**:
- Test: `.venv/Scripts/python.exe -m pytest backend/tests/test_pr_055_exports.py backend/tests/test_pr_056_revenue.py -v`
- Migrate: `alembic upgrade head` (from backend dir)
- Format: `.venv/Scripts/python.exe -m black backend/app/analytics backend/app/revenue`
- Verify: Check coverage is 95%+ and all tests pass

---

**Status**: ✅ Ready to run any command above

Generated: 2025-11-01
