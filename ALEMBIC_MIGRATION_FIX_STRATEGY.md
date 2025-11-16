# Alembic Migration Chain Repair Strategy

## Problem Analysis

The CI alembic migration is failing with:
```
KeyError: '0001_initial_schema'
KeyError: '0003'
```

### Root Causes Identified

1. **Migration naming inconsistency**: Mix of old-style (`003_*`) and new-style (`0003b_*`) naming
2. **Revision ID mismatches**: Files reference revision IDs that don't exist or use different formats
3. **Broken dependency chain**: `0003b` references `0003` but file is named `003_`
4. **Multiple 0002 files**: Both `0002_add_telegram_user_id.py` and `0002_create_trading_store.py`

### Files Affected

**New Style (0001, 0002b, 0002, etc.):**
- `0001_initial_schema.py` → revision="0001" ✅
- `0002_create_trading_store.py` → revision="0002_create_trading_store" (FIXED: down_revision="0001")
- `0002_add_telegram_user_id.py` → revision="0002b_add_telegram_user_id" (FIXED: down_revision="0001")
- `0003b_signal_owner_only.py` → revision="0003b", down_revision="0003" ❌ (should reference "003")

**Old Style (003, 004, 005, etc.):**
- `003_add_signals_approvals.py` → revision="003", down_revision="002"
- `004_add_affiliates.py` → revision="004", down_revision="003"
- (many more...)

**Problem**: New migrations reference old-style revision IDs and vice versa

## Solution

Convert all old-style migrations to new-style naming:

### Step 1: Update Old-Style Revisions to Reference Correctly

1. Change `0003b_signal_owner_only.py`:
   - down_revision: "0003" → "003" (match the old-style file)

2. Rename old-style files to numeric format:
   - `003_add_signals_approvals.py` → rename to use new format
   - But keep the revision IDs as-is in the migration files

Actually, the cleanest solution is to **rebuild the chain** by:

1. Keeping `0001_initial_schema.py` as the head
2. Fixing `0002_create_trading_store.py` to depend on "0001" (DONE)
3. Converting old `003_*` → `0003_*` naming and updating revision IDs
4. Fixing `0003b_signal_owner_only.py` to reference the correct predecessor

## Recommended Path

**Option A (Simple Fix - Current Approach):**
- Fix `0003b_signal_owner_only.py`: change down_revision from "0003" to "003"
- This keeps the old-style chain intact

**Option B (Complete Migration Rewrite - More Robust):**
- Create a single unified migration that applies all schema changes
- Delete all broken migrations
- This is safer but riskier if we don't have correct schema definitions

## Will Proceed With Option A

This maintains backward compatibility with existing DB state while fixing the immediate CI blocker.
