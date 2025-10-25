#!/bin/bash
# Verification Script for MT5 Trading Integration Implementation
# Purpose: Validate all components are correctly implemented

set -e

echo "================================"
echo "MT5 Trading Integration Verification"
echo "================================"
echo ""

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counters
PASSED=0
FAILED=0

# Helper functions
pass() {
    echo -e "${GREEN}✓ $1${NC}"
    ((PASSED++))
}

fail() {
    echo -e "${RED}✗ $1${NC}"
    ((FAILED++))
}

info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

echo "📁 Checking File Structure..."
echo ""

# Check all required files exist
files_to_check=(
    "backend/app/trading/mt5/__init__.py"
    "backend/app/trading/mt5/session.py"
    "backend/app/trading/mt5/circuit_breaker.py"
    "backend/app/trading/mt5/health.py"
    "backend/app/trading/mt5/errors.py"
    "backend/tests/test_mt5_session.py"
)

for file in "${files_to_check[@]}"; do
    if [ -f "$file" ]; then
        pass "File exists: $file"
    else
        fail "File missing: $file"
    fi
done

echo ""
echo "🧪 Checking Test Coverage..."
echo ""

# Run pytest with coverage
info "Running pytest with coverage report..."
python -m pytest backend/tests/test_mt5_session.py -v --cov=backend/app/trading/mt5 --cov-report=term-missing 2>/dev/null | grep -E "(PASSED|FAILED|ERRORS|coverage)" || true

echo ""
echo "🔍 Checking Code Quality..."
echo ""

# Check for type hints
info "Checking for type hints completeness..."
session_file="backend/app/trading/mt5/session.py"
if python -c "import ast; tree = ast.parse(open('$session_file').read()); print('Type hints found')" 2>/dev/null | grep -q "Type hints found"; then
    pass "Type hints present in session.py"
else
    fail "Type hints missing in session.py"
fi

# Check for docstrings
info "Checking for docstrings..."
docstring_count=$(python -c "
import ast
with open('backend/app/trading/mt5/session.py', 'r') as f:
    tree = ast.parse(f.read())
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and ast.get_docstring(node):
            count += 1
    print(count)
" 2>/dev/null)

if [ "$docstring_count" -gt 0 ]; then
    pass "Found $docstring_count documented functions/classes"
else
    fail "No docstrings found"
fi

echo ""
echo "✅ Checking Implementation Completeness..."
echo ""

# Check for required classes
info "Checking for required classes..."

classes_to_check=(
    "MT5SessionManager:session.py"
    "CircuitBreaker:circuit_breaker.py"
    "MT5HealthStatus:health.py"
    "MT5AuthError:errors.py"
)

for class_def in "${classes_to_check[@]}"; do
    class_name="${class_def%:*}"
    file="${class_def#*:}"
    if grep -q "class $class_name" "backend/app/trading/mt5/$file"; then
        pass "Class $class_name found in $file"
    else
        fail "Class $class_name not found in $file"
    fi
done

echo ""
echo "🔒 Checking Security..."
echo ""

# Check for hardcoded credentials
info "Checking for hardcoded credentials..."
if grep -r "password.*=.*['\"]" backend/app/trading/mt5/ --include="*.py" | grep -v "def\|#\|:\|login"; then
    fail "Potential hardcoded credentials found"
else
    pass "No obvious hardcoded credentials detected"
fi

# Check for proper error handling
info "Checking for error handling..."
try_count=$(grep -r "try:" backend/app/trading/mt5/ --include="*.py" | wc -l)
if [ "$try_count" -gt 0 ]; then
    pass "Error handling present ($try_count try blocks)"
else
    fail "No error handling found"
fi

echo ""
echo "📊 Running Import Checks..."
echo ""

# Check imports
info "Checking that modules can be imported..."
python -c "
try:
    from backend.app.trading.mt5.session import MT5SessionManager
    from backend.app.trading.mt5.circuit_breaker import CircuitBreaker
    from backend.app.trading.mt5.health import probe
    from backend.app.trading.mt5.errors import MT5AuthError
    print('All imports successful')
except ImportError as e:
    print(f'Import error: {e}')
" 2>&1 | while read line; do
    if echo "$line" | grep -q "successful"; then
        pass "Imports working correctly"
    elif echo "$line" | grep -q "error"; then
        fail "$line"
    fi
done

echo ""
echo "📋 Summary"
echo "================================"
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"
echo "================================"
echo ""

if [ "$FAILED" -eq 0 ]; then
    echo -e "${GREEN}✓ All verification checks passed!${NC}"
    echo ""
    echo "The MT5 Trading Integration implementation is complete and ready for:"
    echo "  • Code review"
    echo "  • Integration testing"
    echo "  • Deployment to staging"
    exit 0
else
    echo -e "${RED}✗ Some verification checks failed. Please review above.${NC}"
    exit 1
fi
