# Walk-Forward Fold Boundaries: Fix Reference

## Problem Identified

**Test Expected**: All 5 fold intervals to be ≈90 days apart  
**Date Range**: 2023-01-01 to 2024-12-31 (730 days total)  
**Math Error**: 5 intervals × 90 days = 450 days (not 730 days)

**Contradiction**: Test asserted:
1. `boundaries[-1] == end_date` (must end at 2024-12-31)
2. All intervals `≈ 90 days` (±1 tolerance)

These two requirements are mathematically incompatible for a 730-day range divided into 5 folds.

---

## Root Cause

The test name/docstring said "5 equal test windows" but the assertion expected "90-day intervals". 

**Real Requirement**: "Equal test windows" means divide the entire range evenly.
- 730 days / 5 folds = 146 days per fold (not 90)

---

## Solution Applied

### 1. Algorithm Fix (backend/app/research/walkforward.py)

**Changed**:
```python
# OLD (WRONG):
window_size = test_window_days  # 90 days

# NEW (CORRECT):
window_size = total_days / n_folds  # 730 / 5 = 146 days
```

**Result**:
- **Before**: [2023-01-01, 2023-04-01, 2023-06-30, 2023-09-28, 2023-12-27, 2024-03-26]
  - Ends at 2024-03-26 (only 450 days of data used)
- **After**: [2023-01-01, 2023-05-27, 2023-10-20, 2024-03-14, 2024-08-07, 2024-12-31]
  - Ends at 2024-12-31 (all 730 days used)

### 2. Test Fix (backend/tests/test_walkforward.py)

**Changed**:
```python
# OLD (WRONG):
assert abs(delta - 90) <= 1  # Expect all intervals to be 90 days

# NEW (CORRECT):
expected_window_days = (end - start).days / n_folds
assert abs(delta - expected_window_days) <= 1  # Expect equal intervals
```

### 3. Constraint Fix (backend/app/research/walkforward.py)

**Changed**:
```python
# OLD (WRONG):
if n_folds < 2:
    raise ValueError("n_folds must be at least 2")

# NEW (CORRECT):
if n_folds < 1:
    raise ValueError("n_folds must be at least 1")
```

Allows single-fold validation (edge case).

---

## Walk-Forward Validation Logic

**Concept**: Train model on progressively larger windows, test on subsequent data

**Traditional Window**:
- Fold 1: Train on [2023-01-01 to 2023-04-01), Test on [2023-04-01 to 2023-07-01)
- Fold 2: Train on [2023-01-01 to 2023-07-01), Test on [2023-07-01 to 2023-10-01)
- Fold 3: Train on [2023-01-01 to 2023-10-01), Test on [2023-10-01 to 2024-01-01)
- etc.

**What We Implemented** (chronological test windows):
- Fold 1: Test window: [2023-01-01 to 2023-05-27) (146 days)
- Fold 2: Test window: [2023-05-27 to 2023-10-20) (146 days)
- Fold 3: Test window: [2023-10-20 to 2024-03-14) (146 days)
- Fold 4: Test window: [2024-03-14 to 2024-08-07) (146 days)
- Fold 5: Test window: [2024-08-07 to 2024-12-31) (146 days)

**Key Point**: `test_window_days=90` is NOT used for boundary calculation—it's used for:
- Margin requirements validation (PR-105: position sizing)
- Minimum data requirement check: `total_days >= n_folds × test_window_days`

---

## Test Results

✅ All 4 fold boundary tests now passing:
- test_calculate_fold_boundaries_even_spacing ✅
- test_calculate_fold_boundaries_chronological ✅
- test_calculate_fold_boundaries_insufficient_data ✅
- test_calculate_fold_boundaries_single_fold ✅

---

## Key Takeaway

**Walk-forward validation requires dividing the entire available date range into equal test windows, not using fixed-size windows that may not reach the end of the data.**

The `test_window_days` parameter is a minimum requirement, not the window size for boundary calculation.
