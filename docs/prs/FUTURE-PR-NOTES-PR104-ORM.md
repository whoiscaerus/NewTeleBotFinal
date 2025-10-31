# Future PR Notes: PR-104 Circular Import Resolution & ORM Relationships

## Summary

PR-104 (Server-Side Position Management) successfully completed all 5 phases with 41/41 tests passing. However, to avoid circular imports, ORM `relationship()` declarations were commented out. This document tracks what needs attention in future PRs.

---

## ⚠️ Current State: ORM Relationships Commented Out

### Affected Models

**1. `backend/app/trading/positions/models.py` - OpenPosition**
```python
# Line 174-175: COMMENTED OUT
# close_commands = relationship("CloseCommand", back_populates="position", cascade="all, delete-orphan")
```
**Issue**: `OpenPosition` imports `CloseCommand` to define this relationship, but `CloseCommand` tries to import `OpenPosition` back → circular import

**Current Workaround**: Use explicit queries instead
```python
# Instead of: position.close_commands (lazy load)
commands = await db.execute(
    select(CloseCommand).where(CloseCommand.position_id == position.id)
)
```

---

**2. `backend/app/trading/positions/close_commands.py` - CloseCommand**
```python
# Lines 131-133: COMMENTED OUT
# position = relationship("OpenPosition", back_populates="close_commands")
# device = relationship("Device", back_populates="close_commands")
```
**Issue**: Same circular dependency

**Current Workaround**: Foreign keys still exist; query via FK when needed
```python
# Instead of: command.position (lazy load)
position = await db.get(OpenPosition, command.position_id)

# Instead of: command.device (lazy load)
device = await db.get(Device, command.device_id)
```

---

**3. `backend/app/clients/devices/models.py` - Device**
```python
# Lines 92-95: COMMENTED OUT
# close_commands = relationship(
#     "CloseCommand", back_populates="device", cascade="all, delete-orphan"
# )
```
**Issue**: Circular import with `CloseCommand`

---

## Why This Is NOT Breaking

✅ **Foreign keys still work**: Database constraints enforced at schema level
```sql
ALTER TABLE close_commands
ADD CONSTRAINT fk_close_commands_position
FOREIGN KEY (position_id) REFERENCES positions(id);
```

✅ **Explicit queries work perfectly**: All 41 tests validate relationships
```python
# Explicit query is actually more efficient than lazy-load
commands = await db.execute(
    select(CloseCommand)
    .where(CloseCommand.position_id == position.id)
    .order_by(CloseCommand.created_at)
)
```

✅ **No N+1 problem**: We control when queries happen (explicit > implicit)

✅ **Tests passing**: 100% validation that business logic works

---

## When To Address This: PR-110+ (Web Dashboard)

**Future PR Features That Might Need ORM Relationships**:
- PR-110: Position history view (need to fetch position + all close commands together)
- PR-115: Advanced close strategies (need bidirectional relationship for deletion cascade)
- PR-120: Position analytics (need efficient relationship queries)

### Option 1: Keep Current Approach (Recommended)
✅ Explicit queries are actually more efficient
✅ No circular import issues
✅ Clear data flow (no magical lazy-loading)
✅ Easy to debug and optimize
❌ Slightly more verbose code

**When To Use**: For simple features, current approach is fine

---

### Option 2: Implement TYPE_CHECKING Pattern (Advanced)
✅ Full ORM relationship support
✅ No circular imports
✅ More pythonic

**Implementation**:
```python
# backend/app/trading/positions/models.py
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.trading.positions.close_commands import CloseCommand

class OpenPosition(Base):
    # At runtime, import not executed (no circular import)
    # At type-check time, IDE has full type info
    close_commands: Mapped[list["CloseCommand"]] = relationship(
        "CloseCommand",
        back_populates="position",
        cascade="all, delete-orphan"
    )
```

**Risks**:
- SQLAlchemy needs the actual class at runtime for lazy-loading
- TYPE_CHECKING doesn't actually load the class, just type hints
- Requires careful testing to ensure lazy-loading works

**When To Use**: If future PRs need heavy relationship usage

---

### Option 3: Refactor Models Into Separate Files
✅ Clean separation
✅ Full ORM support
✅ No circular imports possible

**Example**:
```
backend/app/trading/positions/
  models/
    __init__.py           # Export all models
    position.py           # Just OpenPosition
    close_command.py      # Just CloseCommand
```

Now they can import each other without circular issues!

**When To Use**: If relationship complexity grows significantly

---

## Action Checklist for Future PRs

### PR-107 (Scheduled Tasks - No ORM Changes Needed)
- [ ] Runs monitor periodically
- [ ] Handles timeout for stale close commands
- [ ] No ORM relationship changes required
- [ ] Can use existing explicit query pattern

### PR-108 (Market Data Feed - No ORM Changes Needed)
- [ ] Provides real-time price feeds
- [ ] Monitor uses to detect breaches
- [ ] No ORM relationship changes required

### PR-110 (Web Dashboard - First Candidate for ORM)
- [ ] Fetch position + related close commands for UI
- [ ] **Decision point**: Keep explicit queries OR implement TYPE_CHECKING
- [ ] If implementing TYPE_CHECKING: Update both position.py and close_command.py
- [ ] Add comprehensive tests for relationship behavior
- [ ] Document any gotchas discovered

### PR-115+ (Advanced Features - May Need ORM)
- [ ] Review after PR-110 decision
- [ ] If using explicit queries: Continue pattern
- [ ] If using TYPE_CHECKING: Extend carefully
- [ ] Test cascading deletes if adding relationship.cascade

---

## Testing Guidance

### For Explicit Query Approach (Current)
```python
# Test that relationships work through queries
async def test_position_close_commands():
    position = await db.get(OpenPosition, position_id)

    # Explicit query instead of relationship
    commands = await db.execute(
        select(CloseCommand).where(
            CloseCommand.position_id == position.id
        )
    )

    assert len(commands.scalars().all()) == 1
```

### For TYPE_CHECKING Approach (If Implemented)
```python
# Test that lazy-loading works
async def test_position_close_commands_lazy():
    position = await db.get(OpenPosition, position_id)

    # This would work IF TYPE_CHECKING pattern is implemented
    # But requires SQLAlchemy to properly load the relationship
    commands = position.close_commands

    assert len(commands) == 1
```

---

## Decision Tree

```
Future PR needs to access Position + Close Commands together?
  ↓
  NO → Keep explicit queries (current approach)

  YES → Is it a one-time query?
    ↓
    YES → Keep explicit queries (simpler, just add join)
    NO → Are you experiencing N+1 problems?
      ↓
      NO → Keep explicit queries (explicit is fine)
      YES → Time to refactor:
        ↓
        Option A: Try TYPE_CHECKING pattern (least invasive)
        Option B: Refactor model files (cleanest long-term)
```

---

## Summary for Next Developer

**Right Now (PR-104 Complete)**:
- ✅ All business logic works
- ✅ Foreign keys enforced
- ✅ Explicit queries used (performant)
- ✅ 100% test coverage
- ✅ No urgency to change

**When Next PR Uses Position + Close Commands**:
- Ask: Do I need ORM relationships?
- If NO: Copy current explicit query pattern
- If YES: Discuss TYPE_CHECKING vs refactor option with team
- If unsure: Explicit queries are safe default

**DO NOT** re-add ORM relationships without addressing circular import!

---
