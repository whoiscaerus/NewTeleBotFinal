#!/bin/bash

# PR-4 Verification Script - Approvals Domain v1
# Purpose: Verify all PR-4 implementation requirements are met
# Status: AUTOMATED VERIFICATION

set -e

echo "============================================================"
echo "PR-4 VERIFICATION SCRIPT - Approvals Domain v1"
echo "============================================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

PASS_COUNT=0
FAIL_COUNT=0

# Helper functions
pass_check() {
    echo -e "${GREEN}✓${NC} $1"
    ((PASS_COUNT++))
}

fail_check() {
    echo -e "${RED}✗${NC} $1"
    ((FAIL_COUNT++))
}

warn_check() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Check 1: Migration file exists
echo "1. DATABASE MIGRATION"
if [ -f "backend/alembic/versions/0003_approvals.py" ]; then
    pass_check "Migration file exists: backend/alembic/versions/0003_approvals.py"
else
    fail_check "Migration file missing: backend/alembic/versions/0003_approvals.py"
fi

# Check 2: ORM model files exist
echo ""
echo "2. ORM MODELS"
if [ -f "backend/app/approvals/models.py" ]; then
    pass_check "ORM model file exists: backend/app/approvals/models.py"
else
    fail_check "ORM model file missing: backend/app/approvals/models.py"
fi

# Check 3: Schema files exist
echo ""
echo "3. PYDANTIC SCHEMAS"
if [ -f "backend/app/approvals/schemas.py" ]; then
    pass_check "Schema file exists: backend/app/approvals/schemas.py"
else
    fail_check "Schema file missing: backend/app/approvals/schemas.py"
fi

# Check 4: Service layer exists
echo ""
echo "4. BUSINESS LOGIC"
if [ -f "backend/app/approvals/service.py" ]; then
    pass_check "Service file exists: backend/app/approvals/service.py"
else
    fail_check "Service file missing: backend/app/approvals/service.py"
fi

# Check 5: Routes exist
echo ""
echo "5. API ENDPOINTS"
if [ -f "backend/app/approvals/routes.py" ]; then
    pass_check "Routes file exists: backend/app/approvals/routes.py"
else
    fail_check "Routes file missing: backend/app/approvals/routes.py"
fi

# Check 6: Tests exist
echo ""
echo "6. TEST SUITE"
if [ -f "backend/tests/test_approvals.py" ]; then
    pass_check "Test file exists: backend/tests/test_approvals.py"
else
    fail_check "Test file missing: backend/tests/test_approvals.py"
fi

# Check 7: Run approval tests
echo ""
echo "7. TEST EXECUTION"
if python -m pytest backend/tests/test_approvals.py -q --tb=no > /tmp/pytest_output.txt 2>&1; then
    TEST_COUNT=$(grep -o "[0-9]* passed" /tmp/pytest_output.txt | grep -o "[0-9]*" | head -1)
    pass_check "Approval tests passing: $TEST_COUNT/15 tests"
else
    FAILED=$(grep -o "[0-9]* failed" /tmp/pytest_output.txt || echo "unknown")
    fail_check "Approval tests failing: $FAILED"
fi

# Check 8: Full test suite
echo ""
echo "8. REGRESSION TESTING"
if python -m pytest backend/tests/ -q --tb=no > /tmp/pytest_full.txt 2>&1; then
    TOTAL_TESTS=$(grep -o "[0-9]* passed" /tmp/pytest_full.txt | grep -o "[0-9]*" | head -1)
    pass_check "Full test suite passing: $TOTAL_TESTS total tests"
else
    FAILURES=$(grep -o "[0-9]* failed" /tmp/pytest_full.txt || echo "unknown")
    fail_check "Full test suite has failures: $FAILURES"
fi

# Check 9: Documentation exists
echo ""
echo "9. DOCUMENTATION"
DOC_COUNT=0
if [ -f "docs/prs/PR-4-IMPLEMENTATION-PLAN.md" ]; then
    pass_check "Implementation plan exists"
    ((DOC_COUNT++))
else
    fail_check "Implementation plan missing"
fi

if [ -f "docs/prs/PR-4-ACCEPTANCE-CRITERIA.md" ]; then
    pass_check "Acceptance criteria exists"
    ((DOC_COUNT++))
else
    fail_check "Acceptance criteria missing"
fi

if [ -f "docs/prs/PR-4-BUSINESS-IMPACT.md" ]; then
    pass_check "Business impact exists"
    ((DOC_COUNT++))
else
    fail_check "Business impact missing"
fi

if [ -f "docs/prs/PR-4-IMPLEMENTATION-COMPLETE.md" ]; then
    pass_check "Implementation complete exists"
    ((DOC_COUNT++))
else
    fail_check "Implementation complete missing"
fi

# Check 10: Code quality
echo ""
echo "10. CODE QUALITY"
if command -v black &> /dev/null; then
    if python -m black --check backend/app/approvals/ backend/tests/test_approvals.py > /dev/null 2>&1; then
        pass_check "Black formatting compliant"
    else
        warn_check "Black formatting needs fixing (run: python -m black backend/app/approvals/)"
    fi
else
    warn_check "Black not available (skipping)"
fi

if command -v ruff &> /dev/null; then
    if python -m ruff check backend/app/approvals/ > /dev/null 2>&1; then
        pass_check "Ruff linting clean"
    else
        warn_check "Ruff has issues (run: python -m ruff check backend/app/approvals/)"
    fi
else
    warn_check "Ruff not available (skipping)"
fi

# Check 11: API endpoints registered
echo ""
echo "11. API REGISTRATION"
if grep -q "include_router(approvals_routes.router)" backend/app/orchestrator/main.py; then
    pass_check "Approvals router registered in main app"
else
    fail_check "Approvals router NOT registered in main app"
fi

# Check 12: Database relationships
echo ""
echo "12. DATABASE INTEGRITY"
if grep -q "approvals = relationship" backend/app/signals/models.py; then
    pass_check "Signal model has approvals relationship"
else
    fail_check "Signal model missing approvals relationship"
fi

# Check 13: Coverage report
echo ""
echo "13. TEST COVERAGE"
if python -m pytest backend/tests/test_approvals.py --cov=backend/app/approvals --cov-report=term-missing -q > /tmp/coverage.txt 2>&1; then
    COVERAGE=$(grep "TOTAL" /tmp/coverage.txt | awk '{print $NF}' || echo "unknown")
    if [[ "$COVERAGE" =~ [0-9]+% ]]; then
        pass_check "Code coverage: $COVERAGE"
    else
        warn_check "Could not extract coverage percentage"
    fi
else
    warn_check "Coverage report generation failed"
fi

# Summary
echo ""
echo "============================================================"
echo "VERIFICATION SUMMARY"
echo "============================================================"
echo -e "${GREEN}Passed:${NC} $PASS_COUNT"
echo -e "${RED}Failed:${NC} $FAIL_COUNT"

if [ $FAIL_COUNT -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓ ALL CHECKS PASSED - PR-4 READY FOR MERGE${NC}"
    exit 0
else
    echo ""
    echo -e "${RED}✗ SOME CHECKS FAILED - FIX ISSUES BEFORE MERGE${NC}"
    exit 1
fi
