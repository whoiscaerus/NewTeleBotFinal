# 🧹 Repository Cleanup Analysis & Plan

## Current State After Initial Deletion

✅ **Already Deleted:**
- backend/app/signals/
- backend/app/approvals/
- backend/app/core/
- backend/app/orchestrator/
- backend/app/main.py
- All test_*.py files
- All alembic migrations

---

## 📋 COMPREHENSIVE CLEANUP CHECKLIST

### ✅ KEEP (Foundation Elements)

**Root Files:**
- [x] `.gitignore` - KEEP (git configuration)
- [x] `CHANGELOG.md` - KEEP (already wiped for fresh start)
- [x] `.env` - DELETE (contains old values)
- [x] `.coverage` - DELETE (test artifact)

**Directories:**
- [x] `.github/` - KEEP (CI/CD workflows + copilot instructions)
- [x] `.github/workflows/` - KEEP (all 8 files: tests.yml, etc.)
- [x] `.github/copilot-instructions.md` - KEEP (already updated to new plan)
- [x] `base_files/` - KEEP (master docs)
- [x] `backend/alembic/` - KEEP (directory structure only)
- [x] `backend/tests/` - KEEP (conftest.py + __init__.py)
- [x] `backend/requirements.txt` - KEEP (dependencies)
- [x] `backend/pytest.ini` - KEEP (test config)
- [x] `backend/conftest.py` - KEEP (root pytest config)

**Keep but Review:**
- [x] `docs/` - REVIEW (contains old PR docs)
- [x] `scripts/` - REVIEW (contains old verification scripts)

---

## 🗑️ ITEMS TO DELETE

### HIGH PRIORITY (Delete Immediately)

1. **Root Files:**
   - [ ] `.env` - Contains old DB connection strings, secrets
   - [ ] `.coverage` - Old test coverage file (will be regenerated)

2. **Old PR Documentation** (docs/):
   - [ ] `/docs/FINAL-SESSION-SUMMARY-PR3-PR4-COMPLETE.md` - Old PR-3/4 summary
   - [ ] `/docs/PR-4-FINAL-SESSION-COMPLETE.md` - Old PR-4 session
   - [ ] `/docs/PR_SESSION_COMPLETE.md` - Old session notes
   - [ ] `/docs/SESSION_COMPLETE_FINAL.md` - Old session notes
   - [ ] `/docs/prs/PR-2-*.md` - Old PR-2 docs (5 files)
   - [ ] `/docs/prs/PR-3-*.md` - Old PR-3 docs (4 files)
   - [ ] `/docs/prs/PR-4-*.md` - Old PR-4 docs (6 files)

3. **Old Verification Scripts** (scripts/verify/):
   - [ ] `/scripts/verify/verify-pr-2.sh` - Old PR-2 verification
   - [ ] `/scripts/verify/verify-pr-4.sh` - Old PR-4 verification

4. **Test Cache:**
   - [ ] `/backend/.pytest_cache/` - Old test cache (will regenerate)
   - [ ] `.pytest_cache/` - Root test cache (will regenerate)

### KEEP (Don't Delete)

1. **docs/PROJECT_CONSOLIDATION_SUMMARY.md**
   - ✅ NEW document explaining the fresh start
   - ✅ Keep for reference

2. **base_files/** (All)
   - ✅ Final_Master_Prs.md (104 PRs - PRIMARY)
   - ✅ Enterprise_System_Build_Plan.md (Phase roadmap)
   - ✅ FULL_BUILD_TASK_BOARD.md (Complete checklist)
   - ✅ PROJECT_TEMPLATES/ (Reusable patterns)

3. **backend/app/__init__.py**
   - ✅ Keep (minimal init file)

4. **backend/tests/conftest.py + __init__.py**
   - ✅ Keep (pytest configuration)

5. **backend/alembic/** structure
   - ✅ Keep env.py, versions/ directory
   - ✅ Migrations will be added in PR-001+

6. **.github/**
   - ✅ Keep all workflows (CI/CD)
   - ✅ Keep copilot-instructions.md (already updated)

---

## 🔄 EXECUTION PLAN

### Step 1: Delete Environment & Cache Files
```powershell
Remove-Item -Force .env
Remove-Item -Force .coverage
```

### Step 2: Clean Test Cache
```powershell
Remove-Item -Recurse -Force .pytest_cache
Remove-Item -Recurse -Force backend/.pytest_cache
```

### Step 3: Delete Old PR Documentation (docs/prs/)
```powershell
# Keep: PROJECT_CONSOLIDATION_SUMMARY.md only
# Delete: All PR-2, PR-3, PR-4 docs
Remove-Item -Force docs/prs/PR-2-*.md
Remove-Item -Force docs/prs/PR-3-*.md
Remove-Item -Force docs/prs/PR-4-*.md
```

### Step 4: Delete Old Session Documentation (docs/)
```powershell
Remove-Item -Force docs/FINAL-SESSION-SUMMARY-PR3-PR4-COMPLETE.md
Remove-Item -Force docs/PR-4-FINAL-SESSION-COMPLETE.md
Remove-Item -Force docs/PR_SESSION_COMPLETE.md
Remove-Item -Force docs/SESSION_COMPLETE_FINAL.md
```

### Step 5: Delete Old Verification Scripts
```powershell
Remove-Item -Force scripts/verify/verify-pr-2.sh
Remove-Item -Force scripts/verify/verify-pr-4.sh
```

### Step 6: Verify Clean State
```powershell
# Should show only:
# - base_files/ (all master docs)
# - docs/PROJECT_CONSOLIDATION_SUMMARY.md
# - docs/prs/ (empty or minimal)
# - scripts/ (empty or minimal)
# - backend/ (only app/__init__.py, tests, alembic structure, config files)
# - .github/ (all workflows + copilot-instructions)
```

### Step 7: Commit to Git
```bash
git add -A
git commit -m "Clean state: Remove old PR docs, cache, env files - Repository ready for PR-001 start"
git push origin main
```

---

## ✅ Final Clean State

### What Should Exist:
```
NewTeleBotFinal/
├── .github/
│   ├── workflows/ (8 files: tests.yml, deploy-*.yml, etc.)
│   └── copilot-instructions.md ✅ (updated)
├── base_files/
│   ├── Final_Master_Prs.md ✅ (104 PRs)
│   ├── Enterprise_System_Build_Plan.md ✅
│   ├── FULL_BUILD_TASK_BOARD.md ✅
│   └── PROJECT_TEMPLATES/
├── backend/
│   ├── app/
│   │   └── __init__.py (empty)
│   ├── tests/
│   │   ├── __init__.py
│   │   └── conftest.py
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/ (empty, ready for migrations)
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── conftest.py
│   └── alembic.ini
├── docs/
│   └── PROJECT_CONSOLIDATION_SUMMARY.md ✅
├── scripts/
│   └── verify/ (empty, ready for PR verification scripts)
├── .gitignore
├── CHANGELOG.md (wiped)
└── README.md (keep if exists)
```

### What Should NOT Exist:
```
❌ .env
❌ .coverage
❌ .pytest_cache/
❌ backend/.pytest_cache/
❌ docs/prs/PR-2-*.md through PR-4-*.md
❌ docs/FINAL-SESSION-SUMMARY-*.md
❌ docs/PR_SESSION_COMPLETE.md
❌ docs/SESSION_COMPLETE_FINAL.md
❌ scripts/verify/verify-pr-2.sh
❌ scripts/verify/verify-pr-4.sh
❌ backend/app/signals/
❌ backend/app/approvals/
❌ backend/app/core/
❌ backend/app/orchestrator/
```

---

## 🎯 Status After Clean

Once cleanup complete:
- ✅ Repository is completely clean
- ✅ No old code artifacts
- ✅ No old test files
- ✅ No old documentation
- ✅ Master documents in place (Final_Master_Prs.md + Enterprise Plan + Task Board)
- ✅ CI/CD workflows ready
- ✅ Ready to start PR-001 implementation

**Next Step:** Start PR-001 (Monorepo Bootstrap)
