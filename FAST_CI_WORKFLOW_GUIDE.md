# Fast CI/CD Workflow Guide

## 🎯 Problem
Running full CI/CD (6424 tests) takes 45-90 minutes, which is too slow when fixing specific test failures.

## ✅ Solutions

### Option 1: Skip CI During Development (EASIEST)
**When to use:** You're fixing tests locally and don't need CI validation yet.

**How:**
```bash
# Commit with [skip-ci] marker
git commit -m "FIX: Updated SignalCandidate tests [skip-ci]"
git push

# OR use the helper script
python quick_test.py test_outbound_client_errors.py
# (script will offer to commit with [skip-ci] if tests pass)
```

**Result:** CI will not run at all - saves time during iterative development.

---

### Option 2: Run Only Changed Tests (AUTOMATIC)
**When to use:** You want CI to run, but only on files you modified.

**How:**
```bash
# Commit with [test-changed] marker
git commit -m "FIX: Updated SignalCandidate tests [test-changed]"
git push
```

**Result:**
- Workflow `test-changed-only.yml` detects changed test files
- Runs ONLY those files on CI (5-10 minutes instead of 60 minutes)
- Full CI workflow is skipped

---

### Option 3: Manual Trigger for Specific Tests (MOST CONTROL)
**When to use:** You want to test specific files on CI without pushing code.

**How:**
1. Go to GitHub Actions tab
2. Select "Test Specific Files" workflow
3. Click "Run workflow"
4. Enter test paths (e.g., `backend/tests/test_outbound_client_errors.py`)
5. Choose verbose mode if needed
6. Click "Run workflow"

**Result:** Runs ONLY the tests you specify (2-5 minutes)

---

### Option 4: Full CI Run (DEFAULT)
**When to use:** Ready to validate all tests before merge.

**How:**
```bash
# Normal commit (no special markers)
git commit -m "FIX: All test fixes complete - ready for review"
git push
```

**Result:** Full CI runs all 6424 tests (45-90 minutes)

---

## 🔄 Recommended Workflow

### During Development (Iterative Fixes)
```bash
# 1. Fix tests locally
python quick_test.py test_outbound_client_errors.py

# 2. If tests pass, commit with [skip-ci]
git commit -m "FIX: SignalCandidate missing fields [skip-ci]"
git push

# 3. Repeat for each test file
```

### Before Final Review
```bash
# Run full CI once everything passes locally
git commit -m "FIX: All test failures resolved"
git push  # Full CI runs
```

---

## 📊 Time Comparison

| Method | Time | When to Use |
|--------|------|-------------|
| **[skip-ci]** | 0 min (no CI) | Iterative development |
| **[test-changed]** | 5-10 min | Changed files only |
| **Manual trigger** | 2-5 min | Specific test validation |
| **Full CI** | 45-90 min | Final validation before merge |

---

## 🚀 Quick Reference Commands

### Using Helper Script
```bash
# Test single file
python quick_test.py test_outbound_client_errors.py

# Test multiple files
python quick_test.py test_outbound_client_errors.py test_data_pipeline.py

# Test pattern
python quick_test.py "test_pr_0*"
```

### Manual Commits
```bash
# Skip CI entirely
git commit -m "Your message [skip-ci]"

# Run changed tests only
git commit -m "Your message [test-changed]"

# Run full CI
git commit -m "Your message"  # No marker
```

---

## 🔍 Checking CI Status

All three workflows appear in GitHub Actions:
- **CI/CD Tests** - Full suite (skipped if [skip-ci] present)
- **Test Changed Files Only** - Runs if [test-changed] present
- **Test Specific Files** - Manual trigger only

---

## 💡 Pro Tips

1. **Batch your fixes:** Fix multiple test files, test locally, then commit all at once with [skip-ci]

2. **Use [test-changed] for validation:** When you've fixed 5-10 files, commit with [test-changed] to verify on CI

3. **Save full CI for end:** Only run full CI when all fixes are complete

4. **Check artifacts:** Even with [test-changed], test results are uploaded as artifacts (30-day retention)

---

## 🐛 Troubleshooting

**Q: [skip-ci] not working?**
- Check commit message syntax: `[skip-ci]`, `[ci-skip]`, `[skip ci]`, or `[ci skip]`
- Must be in commit message, not PR title

**Q: [test-changed] not detecting files?**
- Only detects files in `backend/tests/` directory
- Must have `.py` extension
- Check workflow run logs for "Changed test files: ..."

**Q: Manual trigger not showing up?**
- Workflows must be pushed to `main` branch first
- Go to Actions → "Test Specific Files" → "Run workflow" button

---

## 📝 Example Session

```bash
# Fix test file 1
vim backend/tests/test_outbound_client_errors.py
python quick_test.py test_outbound_client_errors.py
# Tests pass ✅

# Fix test file 2
vim backend/tests/test_data_pipeline.py
python quick_test.py test_data_pipeline.py
# Tests pass ✅

# Commit both with skip-ci
git add .
git commit -m "FIX: SignalCandidate and SymbolPrice tests [skip-ci]"
git push  # CI skipped, instant push

# Fix 5 more files...
# Tests all pass locally ✅

# Now validate on CI with changed files only
git add .
git commit -m "FIX: Batch test fixes for PR-017/018 [test-changed]"
git push  # Only changed files run on CI (10 min)

# Everything passes on CI ✅
# Final commit without markers for full validation
git commit --allow-empty -m "VERIFY: All tests fixed - run full CI suite"
git push  # Full CI runs (60 min)
```
