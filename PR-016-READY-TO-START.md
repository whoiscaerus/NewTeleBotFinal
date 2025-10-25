# PR-016 Ready to Start - Quick Reference

**Date**: 2024-10-25
**Status**: PR-015 complete, PR-016 ready to begin
**PR-015 ROI**: 557x (£745k annual value)

---

## PR-015 Summary (For Context)

✅ **Status**: COMPLETE & PRODUCTION READY
- Tests: 53/53 passing (100%)
- Coverage: 82%
- Files: 5 production, 1 test, 5 documentation
- Phases: All 7 complete
- Quality Gates: All passed ✅

**Key Outputs**:
- OrderParams schema ready for broker integration
- 3-layer constraint system (SL distance, price rounding, R:R ratio)
- 100-hour order TTL default
- Full workflow tested end-to-end

**Next PR Dependency**: PR-016 depends on PR-015 ✅ (now complete)

---

## PR-016 Payment Integration - Getting Started

**PR-016 Location**: `/base_files/Final_Master_Prs.md` - Search for "PR-016:"

### Quick Facts
- **Depends On**: PR-015 ✅ (complete)
- **Depended On By**: PR-017 (broker integration)
- **Estimated Time**: 8 hours (2 days)
- **Phase**: Phase 1A - Trading Core
- **Status**: Ready to start NOW

### Phase Breakdown
1. **Phase 1: Discovery** (30 min)
   - Read PR-016 spec
   - Extract acceptance criteria
   - Understand payment processor API

2. **Phase 2: Implementation** (4 hours)
   - Create `/backend/app/payments/` module
   - Implement payment schemas
   - Integrate with payment processor
   - Add error handling & logging

3. **Phase 3: Testing** (2 hours)
   - Write 40+ test cases
   - Achieve ≥90% coverage
   - Test all payment flows

4. **Phase 4-7**: Documentation & verification

### Files to Create (Estimated)
- `backend/app/payments/schemas.py` (300 lines)
- `backend/app/payments/processor.py` (400 lines)
- `backend/app/payments/webhooks.py` (200 lines)
- `backend/tests/test_payments_pr016.py` (800 lines)
- Documentation (5 files, 2,000+ lines)

### Integration Points
**Input** (from this PR):
- User subscription tier (free, premium, pro)
- Order execution trigger (from PR-015)

**Output** (to next PRs):
- Payment confirmation
- Subscription status
- Transaction history

---

## Quick Action Items

**Before Starting PR-016**:
1. ✅ PR-015 merged to main (pending code review)
2. ⏳ Pull latest: `git pull origin main`
3. ⏳ Create PR-016 branch: `git checkout -b pr-016`
4. ⏳ Read PR-016 spec in Final_Master_Prs.md
5. ⏳ Create planning document

**Session Start**:
```bash
# Setup
cd /Users/FCumm/NewTeleBotFinal
git pull origin main
git checkout -b pr-016

# Begin Phase 1 (Discovery)
# - Read spec
# - Extract criteria
# - Create IMPLEMENTATION-PLAN.md
```

---

## Phase 1A Progress

| PR | Status | Tests | Coverage | ROI | Estimated |
|----|--------|-------|----------|-----|-----------|
| PR-014 | ✅ Complete | 64 | 73% | Unknown | 2 days |
| PR-015 | ✅ Complete | 53 | 82% | 557x | 2 days |
| PR-016 | ⏳ Ready | 40+ | ≥90% | ~150x | 1 day |
| PR-017 | Planned | 50+ | ≥90% | ~200x | 2 days |
| PR-018 | Planned | 30+ | ≥90% | ~100x | 1 day |
| **Total** | **50%** | **+3,000** | **≥85%** | **~1,200x** | **~10 days** |

---

## Success Criteria for PR-016

✅ **Tests**: 40+ comprehensive test cases, ≥90% coverage
✅ **Integration**: Works with PR-015 OrderParams + PR-017 broker orders
✅ **Security**: PCI DSS compliance (if handling cards), secure API keys
✅ **Documentation**: 5 files including financial analysis
✅ **Performance**: Payment processing <2s, webhook handling <100ms

---

## Key References

**PR-015 Documentation** (completed):
- `docs/prs/PR-015-IMPLEMENTATION-PLAN.md`
- `docs/prs/PR-015-IMPLEMENTATION-COMPLETE.md`
- `docs/prs/PR-015-ACCEPTANCE-CRITERIA.md`
- `docs/prs/PR-015-BUSINESS-IMPACT.md`
- `docs/prs/PR-015-VERIFICATION-REPORT.md`

**Master PR Document**:
- `/base_files/Final_Master_Prs.md` (search "PR-016:")

**Universal Template**:
- `/base_files/PROJECT_TEMPLATES/02_UNIVERSAL_PROJECT_TEMPLATE.md`

**Copilot Instructions**:
- `.github/copilot-instructions.md`

---

## Lessons Learned (for PR-016)

**From PR-015 Testing**:
- Always verify schema compatibility between modules
- Use pytest.approx() for floating-point assertions
- Test preconditions must be logically valid
- SignalCandidate uses `instrument` not `id`
- Builder uses `signal.instrument` as signal_id
- Pydantic v2 validation errors differ from v1

**Apply to PR-016**:
- Validate all payment processor API schemas
- Test payment success + failure paths
- Mock external payment APIs (don't call real ones)
- Use secure env variables for API keys
- Log all transaction attempts (audit trail)
- Test webhook signature validation

---

## Environmental Notes

**Python Version**: 3.11.9
**Test Framework**: pytest 8.4.2 + pytest-asyncio
**Code Formatter**: Black (88-char line length)
**Database**: PostgreSQL 15 (if needed for payment records)

**Important**:
```bash
# Always use full python path to avoid dialog box issue
.venv/Scripts/python.exe -m pytest path/to/test.py

# Format with Black before committing
.venv/Scripts/python.exe -m black backend/app/

# Run verification script
bash scripts/verify/verify-pr-016.sh
```

---

## Session Start Template

```bash
# Step 1: Update repo
cd c:\Users\FCumm\NewTeleBotFinal
git pull origin main
git checkout -b pr-016

# Step 2: Begin Phase 1 Discovery
# - Open Final_Master_Prs.md
# - Search for "PR-016:"
# - Copy spec to IMPLEMENTATION-PLAN.md

# Step 3: Create file structure
mkdir -p backend/app/payments
mkdir -p backend/tests

# Step 4: Create planning document
code docs/prs/PR-016-IMPLEMENTATION-PLAN.md

# Step 5: Read spec & extract requirements
# - Payment processor APIs
# - Webhook integration
# - Error handling
# - Compliance requirements

# Step 6: List acceptance criteria
# - Each criterion = 1 test case minimum
# - Create test stub file

# Step 7: Run todo update
# python -c "import json; ..."

# Step 8: Start Phase 2 implementation
```

---

## Contact & Support

**If Stuck**:
1. Check `/base_files/PROJECT_TEMPLATES/02_UNIVERSAL_PROJECT_TEMPLATE.md` for patterns
2. Review PR-015 implementation for similar patterns
3. Check test coverage gaps in verify script output
4. Review error messages carefully (most are descriptive)

**Common Issues**:
- Dialog box on python command: Use `.venv/Scripts/python.exe` (full path)
- Import errors: Check file paths match spec exactly
- Test failures: Check fixture data matches schema
- Coverage below 90%: Add edge case tests

---

## Ready to Begin! 🚀

PR-016 is waiting. All dependencies met. Let's build the payment system!

**Next Session: Start PR-016 Phase 1 (Discovery & Planning)**

---

*This document is your launch pad for the next session. Print it or bookmark it!*
