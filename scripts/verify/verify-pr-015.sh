#!/bin/bash
# PR-015 Order Construction Verification Script
# Purpose: Automated verification that PR-015 meets all requirements
# Run after: git checkout main && git pull

set -e  # Exit on any error

echo "=========================================="
echo "PR-015 Order Construction Verification"
echo "=========================================="

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track results
PASSED=0
FAILED=0

# Test function
verify_test() {
    local test_name=$1
    local command=$2

    echo -n "Testing: $test_name... "

    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ PASS${NC}"
        ((PASSED++))
    else
        echo -e "${RED}✗ FAIL${NC}"
        ((FAILED++))
    fi
}

# File existence tests
echo ""
echo "1. Checking file structure..."
verify_test "schema.py exists" "test -f backend/app/trading/orders/schema.py"
verify_test "builder.py exists" "test -f backend/app/trading/orders/builder.py"
verify_test "constraints.py exists" "test -f backend/app/trading/orders/constraints.py"
verify_test "expiry.py exists" "test -f backend/app/trading/orders/expiry.py"
verify_test "__init__.py exists" "test -f backend/app/trading/orders/__init__.py"
verify_test "test suite exists" "test -f backend/tests/test_order_construction_pr015.py"

# Test execution
echo ""
echo "2. Running test suite..."
if command -v python &> /dev/null; then
    verify_test "All tests passing" "python -m pytest backend/tests/test_order_construction_pr015.py -v --tb=no -q"
else
    verify_test "All tests passing" ".venv/Scripts/python.exe -m pytest backend/tests/test_order_construction_pr015.py -v --tb=no -q"
fi

# Code quality tests
echo ""
echo "3. Checking code quality..."
verify_test "No TODOs in schema.py" "! grep -q 'TODO\\|FIXME' backend/app/trading/orders/schema.py"
verify_test "No TODOs in builder.py" "! grep -q 'TODO\\|FIXME' backend/app/trading/orders/builder.py"
verify_test "No TODOs in constraints.py" "! grep -q 'TODO\\|FIXME' backend/app/trading/orders/constraints.py"
verify_test "No TODOs in expiry.py" "! grep -q 'TODO\\|FIXME' backend/app/trading/orders/expiry.py"

# Import tests
echo ""
echo "4. Checking imports..."
if command -v python &> /dev/null; then
    verify_test "Can import OrderParams" "python -c 'from backend.app.trading.orders import OrderParams; print(\"OK\")' | grep -q OK"
    verify_test "Can import build_order" "python -c 'from backend.app.trading.orders import build_order; print(\"OK\")' | grep -q OK"
    verify_test "Can import constraints" "python -c 'from backend.app.trading.orders import apply_min_stop_distance; print(\"OK\")' | grep -q OK"
else
    verify_test "Can import OrderParams" ".venv/Scripts/python.exe -c 'from backend.app.trading.orders import OrderParams; print(\"OK\")' | grep -q OK"
    verify_test "Can import build_order" ".venv/Scripts/python.exe -c 'from backend.app.trading.orders import build_order; print(\"OK\")' | grep -q OK"
    verify_test "Can import constraints" ".venv/Scripts/python.exe -c 'from backend.app.trading.orders import apply_min_stop_distance; print(\"OK\")' | grep -q OK"
fi

# Documentation tests
echo ""
echo "5. Checking documentation..."
verify_test "IMPLEMENTATION-PLAN exists" "test -f docs/prs/PR-015-IMPLEMENTATION-PLAN.md"
verify_test "IMPLEMENTATION-COMPLETE exists" "test -f docs/prs/PR-015-IMPLEMENTATION-COMPLETE.md"
verify_test "ACCEPTANCE-CRITERIA exists" "test -f docs/prs/PR-015-ACCEPTANCE-CRITERIA.md"
verify_test "BUSINESS-IMPACT exists" "test -f docs/prs/PR-015-BUSINESS-IMPACT.md"

# Line count verification
echo ""
echo "6. Checking code metrics..."

# Count lines in each file
schema_lines=$(wc -l < backend/app/trading/orders/schema.py 2>/dev/null || echo "0")
builder_lines=$(wc -l < backend/app/trading/orders/builder.py 2>/dev/null || echo "0")
constraints_lines=$(wc -l < backend/app/trading/orders/constraints.py 2>/dev/null || echo "0")
expiry_lines=$(wc -l < backend/app/trading/orders/expiry.py 2>/dev/null || echo "0")

if [ "$schema_lines" -gt 300 ]; then
    echo -e "${GREEN}✓${NC} schema.py: $schema_lines lines"
    ((PASSED++))
else
    echo -e "${RED}✗${NC} schema.py: $schema_lines lines (expected >300)"
    ((FAILED++))
fi

if [ "$builder_lines" -gt 150 ]; then
    echo -e "${GREEN}✓${NC} builder.py: $builder_lines lines"
    ((PASSED++))
else
    echo -e "${RED}✗${NC} builder.py: $builder_lines lines (expected >150)"
    ((FAILED++))
fi

if [ "$constraints_lines" -gt 200 ]; then
    echo -e "${GREEN}✓${NC} constraints.py: $constraints_lines lines"
    ((PASSED++))
else
    echo -e "${RED}✗${NC} constraints.py: $constraints_lines lines (expected >200)"
    ((FAILED++))
fi

if [ "$expiry_lines" -gt 50 ]; then
    echo -e "${GREEN}✓${NC} expiry.py: $expiry_lines lines"
    ((PASSED++))
else
    echo -e "${RED}✗${NC} expiry.py: $expiry_lines lines (expected >50)"
    ((FAILED++))
fi

# Summary
echo ""
echo "=========================================="
echo "Verification Summary"
echo "=========================================="
echo -e "${GREEN}Passed: $PASSED${NC}"
if [ $FAILED -gt 0 ]; then
    echo -e "${RED}Failed: $FAILED${NC}"
else
    echo -e "${GREEN}Failed: $FAILED${NC}"
fi

if [ $FAILED -eq 0 ]; then
    echo -e "\n${GREEN}✓ PR-015 VERIFICATION PASSED${NC}"
    echo "All requirements met. Ready for production."
    exit 0
else
    echo -e "\n${RED}✗ PR-015 VERIFICATION FAILED${NC}"
    echo "Fix issues and re-run verification."
    exit 1
fi
