# PR IMPLEMENTATION FRAMEWORK v1.0
## Master Rules for PR-1 through PR-224 Sequential Implementation

**Effective Date**: October 21, 2025  
**Status**: ACTIVE - All 224 PRs must follow these rules  
**Purpose**: Prevent confusion, track implementations, enable error recovery  
**Specification**: New_Master_Prs.md (224 focused PRs: hybrid best-of-both approach)  
**Timeline**: 26 weeks to production-ready MVP

---

## 📋 CORE PRINCIPLES

### Principle 1: Sequential Implementation
- **Rule**: Implement PRs in order: PR-1 → PR-2 → PR-3 ... → PR-224
- **Why**: Dependencies are linear; each PR builds on previous
- **Enforcement**: Cannot start PR-N until PR-(N-1) is COMPLETE and VERIFIED

### Principle 2: Clear File Location Patterns
- **Rule**: Every file created must follow strict location pattern
- **Why**: Enables rapid discovery, prevents duplication, supports error recovery
- **Pattern**: See "File Naming & Location Standards" section below

### Principle 3: Mandatory Tracking & Indexing
- **Rule**: Every PR must have status document and verification script
- **Why**: Enables "find any implementation" in <1 minute
- **Artifacts**: PR-specific documentation + verification script

### Principle 4: Production Quality from Day One
- **Rule**: No PR is "complete" until it passes ALL verification gates
- **Why**: Prevents accumulating technical debt
- **Gates**: Code quality, tests, documentation, rollback capability

### Principle 5: Error Recovery Capability
- **Rule**: Every PR must be rollback-able without data loss
- **Why**: Enables fixing mistakes quickly
- **Method**: Git commits + migration rollbacks + state documentation

---

## 🗂️ PROJECT STRUCTURE

```
TelebotFinal/
├── ARCHIVE_V0_LEGACY/          ← All legacy code/docs (do not touch)
│   ├── backend/
│   ├── frontend/
│   ├── docs/
│   ├── scripts/
│   └── (all existing code)
│
├── PROJECT_TRACKER.md          ← Master tracking document (CRITICAL!)
├── PR_IMPLEMENTATION_RULES.md  ← These rules (this file)
│
├── backend/                    ← Fresh backend for PR-1-77
│   ├── app/
│   │   ├── orchestrator/       (PR-1)
│   │   ├── core/               (PR-2)
│   │   ├── signals/            (PR-3)
│   │   ├── approvals/          (PR-4)
│   │   └── ...
│   ├── alembic/
│   │   ├── versions/           (migrations only!)
│   │   └── env.py
│   ├── tests/
│   │   ├── test_pr_1.py
│   │   ├── test_pr_2.py
│   │   └── ...
│   ├── requirements.txt
│   ├── pyproject.toml
│   └── pytest.ini
│
├── frontend/                   ← Fresh frontend for PR-32+
│   ├── src/
│   └── ...
│
├── docs/
│   ├── prs/                    ← PR DOCUMENTATION (CRITICAL!)
│   │   ├── PR-1-SPEC.md
│   │   ├── PR-1-IMPLEMENTATION.md
│   │   ├── PR-1-COMPLETE.md
│   │   ├── PR-2-SPEC.md
│   │   └── ...
│   ├── New_Master_Prs.md       (the spec - reference only)
│   └── PROJECT_STRUCTURE.md
│
├── scripts/
│   ├── verify/                 ← Verification scripts (CRITICAL!)
│   │   ├── verify-pr-1.sh
│   │   ├── verify-pr-2.sh
│   │   └── ...
│   ├── verify_all.sh           (master verification)
│   └── pr_status_check.sh      (quick status)
│
├── .github/
│   └── workflows/              (CI/CD)
│
├── README.md                   (project overview)
└── .gitignore
```

---

## 📝 FILE NAMING & LOCATION STANDARDS

### Backend Files

**Orchestrator Pattern (PR-1)**:
```
backend/app/orchestrator/
├── __init__.py
├── main.py
├── routes.py
└── settings.py
```

**Domain Pattern (PR-3 Signals)**:
```
backend/app/signals/
├── __init__.py
├── models.py          (SQLAlchemy ORM models)
├── schemas.py         (Pydantic request/response)
├── routes.py          (FastAPI endpoints)
├── service.py         (business logic)
├── repository.py      (data access layer)
└── dependencies.py    (FastAPI dependencies)
```

**Database Migrations**:
```
backend/alembic/versions/
├── 0001_pr_1_orchestrator.py
├── 0002_pr_2_postgresql_setup.py
├── 0003_pr_3_signals.py
└── (one per PR, named descriptively)
```

**Tests**:
```
backend/tests/
├── test_pr_1_orchestrator.py
├── test_pr_2_database.py
├── test_pr_3_signals.py
└── conftest.py          (pytest fixtures shared)
```

### Documentation Files

**PR Documentation Pattern**:
```
docs/prs/
├── PR-1-SPEC.md                      (spec excerpt from New_Master_Prs.md)
├── PR-1-IMPLEMENTATION.md             (what was built)
├── PR-1-VERIFICATION.md               (how to verify it works)
├── PR-1-ROLLBACK.md                   (how to rollback if needed)
├── PR-1-COMPLETE.md                   (final sign-off)
└── PR-1-DEPENDENCIES.md               (what it depends on)
```

**Verification Scripts**:
```
scripts/verify/
├── verify-pr-1.sh                     (tests PR-1 only)
├── verify-pr-2.sh                     (tests PR-2 only)
├── verify-pr-all.sh                   (tests ALL PRs)
└── quick-status.sh                    (quick health check)
```

---

## ✅ VERIFICATION GATES (CRITICAL!)

### Before a PR is "COMPLETE", it MUST pass:

#### Gate 1: Code Quality
```bash
# Run linter
ruff check backend/app/[pr_domain]/

# Run formatter
black backend/app/[pr_domain]/ --check

# Run type checker
mypy backend/app/[pr_domain]/
```

**Standard**: Zero errors, warnings OK (log them)

#### Gate 2: Unit Tests
```bash
# Run PR-specific tests
pytest backend/tests/test_pr_[N]_*.py -v --cov

# Requirement: >90% code coverage for new code
```

**Standard**: All tests pass, coverage >90%

#### Gate 3: Integration Tests
```bash
# Test database migrations
alembic upgrade head

# Test API endpoints work
pytest backend/tests/test_pr_[N]_integration.py -v
```

**Standard**: Migrations are reversible, endpoints work

#### Gate 4: Documentation Complete
- [ ] PR-N-SPEC.md exists (spec excerpt)
- [ ] PR-N-IMPLEMENTATION.md explains what was built
- [ ] PR-N-VERIFICATION.md shows how to verify
- [ ] PR-N-ROLLBACK.md shows how to rollback
- [ ] Code has docstrings (functions, classes, modules)
- [ ] Docstrings explain intent, not obvious code

#### Gate 5: Rollback Tested
```bash
# Test backward migration works
alembic downgrade -1

# Test code still works in previous state
pytest backend/tests/ -v

# Test forward migration works again
alembic upgrade head
```

**Standard**: Rollback is tested and documented

#### Gate 6: Git Commits Proper
- [ ] One PR = one commit (or series of squashed commits)
- [ ] Commit message: `feat(pr-N): [Title from spec]`
- [ ] Commit message body explains why, not what
- [ ] Commit is signed with GPG (if company policy)

---

## 📊 PROJECT TRACKER (CRITICAL!)

**Location**: `/PROJECT_TRACKER.md`

**Maintains**:
```
| PR | Status | Files | Tests | Docs | Verified | Rollback Tested | Last Update |
|----|--------|-------|-------|------|----------|-----------------|-------------|
| 1  | ✅ COMPLETE | 4 | ✅ | ✅ | ✅ | ✅ | 2025-10-21 |
| 2  | 🔄 IN-PROGRESS | 3 | ⏳ | ⏳ | ❌ | ❌ | 2025-10-21 |
| 3  | ⏳ BLOCKED | - | - | - | - | - | 2025-10-21 |
```

**Updated**: After every PR completion

**Used For**: Quick "where are we" status check

---

## 🚀 PR IMPLEMENTATION WORKFLOW

### Step 1: Read Spec
```
File: /docs/New_Master_Prs.md
Section: PR-N — FULL DETAILED SPECIFICATION
Time: 30-60 minutes
Output: Understand exact requirements
```

### Step 2: Create Documentation
```
Create files:
- /docs/prs/PR-N-SPEC.md (excerpt from spec)
- /docs/prs/PR-N-IMPLEMENTATION.md (skeleton)
- /docs/prs/PR-N-VERIFICATION.md (skeleton)
- /docs/prs/PR-N-ROLLBACK.md (skeleton)

Reason: Clarifies thinking before building
Time: 15-30 minutes
```

### Step 3: Build Code
```
Create files per "File Naming Standards" section
Implement exactly as spec says
Follow code standards:
- Type hints on all functions
- Docstrings on all public functions
- Tests for all business logic
- Error handling for all failures

Time: Varies by PR complexity
```

### Step 4: Write Tests
```
Create: /backend/tests/test_pr_N_*.py
Coverage: >90% of new code
Types:
- Unit tests (isolated functions)
- Integration tests (with database/API)
- Error case tests

Standard: All tests pass before considering complete
```

### Step 5: Database Migration
```
If PR touches database:
- Create: /backend/alembic/versions/000N_pr_N_*.py
- Test: alembic upgrade head (works)
- Test: alembic downgrade -1 (works)
- Test: alembic upgrade head (works)

Standard: Migrations are reversible and tested
```

### Step 6: Verify All Gates
```
Run: scripts/verify/verify-pr-N.sh

Checks:
- Code passes linter (ruff)
- Code passes formatter (black)
- Tests pass (pytest)
- Coverage >90%
- Migrations work (both ways)
- Documentation complete
- Git history clean

Standard: All checks pass, zero critical warnings
```

### Step 7: Update Tracker
```
File: /PROJECT_TRACKER.md

Update:
- PR status → ✅ COMPLETE
- File count
- Test count
- Docs status
- Verified date
- Rollback tested date

Time: 5 minutes
```

### Step 8: Commit to Git
```
git add .
git commit -m "feat(pr-N): [Title from spec]

[Detailed explanation of changes]

Verification:
- All tests pass
- Code coverage >90%
- Migration tested (up/down/up)
- Documentation complete
"
```

### Step 9: Ready for Next PR
```
Confirm:
- PR-N is complete ✅
- All tests pass ✅
- Tracker updated ✅
- Ready to start PR-(N+1)

Time: 5 minutes to transition
```

---

## 🔄 ERROR RECOVERY PROCEDURES

### Scenario 1: Tests Failing on PR-N

**Step 1**: Identify which tests fail
```bash
pytest backend/tests/test_pr_N_*.py -v
```

**Step 2**: Check what changed
```bash
git diff HEAD~1..HEAD
```

**Step 3**: Fix code

**Step 4**: Re-run tests
```bash
pytest backend/tests/test_pr_N_*.py -v
```

**Step 5**: If still failing after investigation, rollback:
```bash
git reset --hard HEAD~1
git revert HEAD
```

### Scenario 2: Migration Fails on PR-N

**Step 1**: Check what went wrong
```bash
alembic current
alembic branches
```

**Step 2**: Rollback migration
```bash
alembic downgrade -1
```

**Step 3**: Fix migration file and re-apply
```bash
alembic upgrade head
```

**Step 4**: Test rollback works
```bash
alembic downgrade -1
alembic upgrade head
```

### Scenario 3: Need to Restart PR-N from Scratch

**Step 1**: Rollback code
```bash
git reset --hard HEAD~1
```

**Step 2**: Rollback database
```bash
alembic downgrade -1
```

**Step 3**: Delete incomplete PR files
```bash
rm -rf backend/app/[domain]/
rm backend/tests/test_pr_N_*.py
```

**Step 4**: Delete documentation
```bash
rm docs/prs/PR-N-*.md
```

**Step 5**: Update tracker (PR status → ⏳ NOT STARTED)

**Step 6**: Re-start PR from Step 1 of workflow

---

## 📋 TRACKING & LOOKUP

### Find Implementation of Feature X

**Step 1**: Look in tracker
```bash
grep -i "feature x" PROJECT_TRACKER.md
```

**Step 2**: Note which PR(s) it's in
```
Feature X is in PR-23, PR-45
```

**Step 3**: Look at implementation doc
```bash
cat docs/prs/PR-23-IMPLEMENTATION.md
```

**Step 4**: Check code
```bash
ls -la backend/app/[domain_from_pr_23]/
```

**Step 5**: Find specific file in tests
```bash
grep -r "feature x" backend/tests/test_pr_23*.py
```

**Result**: Located in <2 minutes max

### Find Error in PR-N

**Step 1**: Check verification script
```bash
scripts/verify/verify-pr-N.sh
```

**Step 2**: Check test output
```bash
pytest backend/tests/test_pr_N_*.py -v --tb=short
```

**Step 3**: Check implementation doc for context
```bash
cat docs/prs/PR-N-IMPLEMENTATION.md
```

**Step 4**: Check git history
```bash
git log --oneline | grep "pr-N"
git show [commit_hash]
```

**Result**: Error located and understood in <5 minutes

### Find Which PR Implements Feature X

**Example**: Find which PR implements "subscription management"

**Method 1**: Use tracker
```bash
grep -i "subscription" PROJECT_TRACKER.md
```

**Method 2**: Search documentation
```bash
grep -r "subscription" docs/prs/*.md
```

**Method 3**: Search code
```bash
grep -r "subscription" backend/app/
```

**Result**: PR-31 (Subscription Management) implements this

---

## 🎯 QUALITY STANDARDS

### Code Style
- **Formatter**: Black (configured in pyproject.toml)
- **Linter**: Ruff (zero errors, warnings OK)
- **Type Checker**: Mypy (strict mode)
- **Pre-commit hooks**: Enforce formatter/linter before commit

### Testing
- **Framework**: Pytest
- **Minimum coverage**: 90% for new code
- **Test organization**: By PR (test_pr_N_*.py)
- **Fixtures**: Shared in conftest.py per test directory

### Documentation
- **API docs**: Docstrings + OpenAPI (auto-generated by FastAPI)
- **Implementation docs**: Markdown files in docs/prs/
- **Code comments**: Only for WHY, not WHAT (code should be obvious)

### Git
- **Commits**: One feature = one atomic commit (or squash related commits)
- **Messages**: Conventional commits (feat, fix, docs, refactor, etc.)
- **Branch**: main only (no feature branches during sequential build)
- **History**: Clean, linear, easy to bisect

---

## 🚨 CRITICAL RULES (MUST FOLLOW)

1. **NO SKIPPING**: Cannot skip PR-N to do PR-(N+10)
   - Reason: Dependencies are linear
   - Exception: Only if explicit dependency graph allows it (rare)

2. **NO PARTIAL COMPLETION**: PR is either COMPLETE or NOT STARTED
   - Reason: Prevents ambiguity
   - Standard: PR-N-COMPLETE.md exists = PR is done

3. **NO CODE WITHOUT TESTS**: Every function must have tests
   - Reason: Enables refactoring safely later
   - Standard: >90% coverage enforced

4. **NO INCOMPLETE MIGRATIONS**: Migrations must be tested both ways
   - Reason: Enables safe rollback
   - Standard: alembic upgrade/downgrade cycle verified

5. **NO LOST IMPLEMENTATIONS**: Every file follows location standard
   - Reason: Enables finding anything in <2 minutes
   - Standard: `tree backend/` matches expected structure

6. **NO MYSTERY CHANGES**: Every commit must be documented
   - Reason: Enables understanding history
   - Standard: Clear commit messages + PR-N-*.md files

---

## 📞 WHAT TO DO IF CONFUSED

**Flowchart**:

```
Am I confused?
├─ YES
│  ├─ Check PROJECT_TRACKER.md (quick status)
│  ├─ Read PR-N-SPEC.md (what should be built)
│  ├─ Read PR-N-IMPLEMENTATION.md (what was built)
│  ├─ Run verify-pr-N.sh (what's working)
│  └─ If still confused → rollback to last known good state
│
└─ NO
   └─ Continue implementation
```

---

## ✅ FINAL CHECKLIST FOR PR COMPLETION

Before marking PR-N as ✅ COMPLETE, verify:

- [ ] All code files created per File Naming Standards
- [ ] All code passes ruff (linter)
- [ ] All code passes black (formatter)
- [ ] All code passes mypy (type checker)
- [ ] All tests pass: `pytest backend/tests/test_pr_N_*.py`
- [ ] Test coverage >90%: `pytest --cov backend/app/[domain]`
- [ ] All database migrations created (if applicable)
- [ ] Migrations test forward: `alembic upgrade head`
- [ ] Migrations test backward: `alembic downgrade -1`
- [ ] Migrations test forward again: `alembic upgrade head`
- [ ] PR-N-SPEC.md written (excerpted from New_Master_Prs.md)
- [ ] PR-N-IMPLEMENTATION.md written (what was built)
- [ ] PR-N-VERIFICATION.md written (how to verify)
- [ ] PR-N-ROLLBACK.md written (how to rollback)
- [ ] PR-N-COMPLETE.md written (sign-off)
- [ ] PROJECT_TRACKER.md updated
- [ ] Git commit created with proper message
- [ ] Verification script passes: `scripts/verify/verify-pr-N.sh`
- [ ] All documentation is clear and complete
- [ ] Code is production-ready

---

## 🎉 SUMMARY

**This framework ensures**:
- ✅ No confusion about what's implemented
- ✅ No loss of code due to poor organization
- ✅ No difficulty finding implementations
- ✅ No broken tests sneaking through
- ✅ No untracked changes
- ✅ Easy error recovery
- ✅ Clear rollback procedures
- ✅ Production-ready quality from day 1

**Use this framework religiously. It prevents all problems.**

---

**Version**: 1.0  
**Effective**: October 21, 2025  
**Last Updated**: October 21, 2025  
**Next Review**: After PR-5 completion

