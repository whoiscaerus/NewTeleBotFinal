# PR-060 QUICK REFERENCE - TEST FIX NEEDED ⚠️

## STATUS: 100% Implementation ✅ | Tests Need API Alignment ⚠️

### WHAT'S DONE ✅
- All 3 senders: email (350+ lines), telegram (320+ lines), push (380+ lines)
- API routes: POST /messaging/test (260+ lines)
- Settings: PushSettings added
- Router: messaging_router registered in main.py
- Tests: 4 files, 79 tests, 3,380+ lines created

### WHAT'S NEEDED ⚠️ (30-45 minutes)
**Problem**: Tests import functions that don't exist
- Tests expect: `dequeue_message()`, `retry_message()`, `get_bus()` (module-level)
- Actual API: `MessagingBus` class + `get_messaging_bus()` singleton

### FIX CHECKLIST (4 test files)

#### 1. backend/tests/test_messaging_bus.py (850 lines)
```python
# WRONG (current line 22):
from backend.app.messaging.bus import (
    dequeue_message,  # ❌ Doesn't exist
    enqueue_campaign,  # ✅ Exists
    enqueue_message,  # ✅ Exists
    get_bus,  # ❌ Doesn't exist
    retry_message,  # ❌ Doesn't exist
    MessagingBus,  # ✅ Exists
    ...
)

# CORRECT (needed):
from backend.app.messaging.bus import (
    CAMPAIGN_QUEUE,
    DEAD_LETTER_QUEUE,
    MAX_RETRIES,
    RETRY_DELAYS,
    TRANSACTIONAL_QUEUE,
    MessagingBus,
    enqueue_campaign,
    enqueue_message,
    get_messaging_bus,  # ✅ Correct function name
)

# Add fixture:
@pytest.fixture
async def messaging_bus():
    bus = await get_messaging_bus()
    yield bus
    await bus.close()

# Update all tests to use bus fixture:
async def test_enqueue_dequeue_transactional(messaging_bus):
    # WRONG:
    message_id = await enqueue_message(...)
    message = await dequeue_message(priority="transactional")

    # CORRECT:
    message_id = await messaging_bus.enqueue_message(...)
    message = await messaging_bus.dequeue_message(priority="transactional")
```

#### 2. backend/tests/test_messaging_templates.py (650 lines)
**Status**: ✅ Already correct (imports render functions, not bus methods)
- Imports: `render_email`, `render_telegram`, `render_push`, `validate_template_vars`, `escape_markdownv2`
- No changes needed

#### 3. backend/tests/test_messaging_senders.py (1,200 lines)
**Status**: ✅ Already correct (imports send functions)
- Imports: `send_email`, `send_telegram`, `send_push`
- No changes needed

#### 4. backend/tests/test_messaging_routes.py (680 lines)
**Status**: ⚠️ May need fixture updates
- Check if imports are correct
- Verify fixtures use correct user model

### ACTUAL BUS.PY API

**Module-Level Functions** (convenience wrappers):
```python
async def get_messaging_bus() -> MessagingBus
async def enqueue_message(user_id, channel, template_name, template_vars, priority="transactional") -> str
async def enqueue_campaign(user_ids, channel, template_name, template_vars_fn, batch_size=100) -> dict
```

**MessagingBus Class Methods**:
```python
class MessagingBus:
    async def initialize() -> None
    async def close() -> None
    async def enqueue_message(...) -> str
    async def enqueue_campaign(...) -> dict
    async def dequeue_message(priority="transactional") -> dict | None
    async def retry_message(message: dict) -> None
    async def get_queue_size(priority="transactional") -> int
    async def get_dlq_size() -> int
    # Private:
    async def _move_to_dlq(message: dict, reason: str) -> None
```

**Constants**:
```python
TRANSACTIONAL_QUEUE = "messaging:queue:transactional"
CAMPAIGN_QUEUE = "messaging:queue:campaign"
DEAD_LETTER_QUEUE = "messaging:queue:dlq"
MAX_RETRIES = 5
RETRY_DELAYS = [1, 2, 4, 8, 16]
```

### AFTER FIX: RUN TESTS
```powershell
# Run all messaging tests with coverage
.venv/Scripts/python.exe -m pytest backend/tests/test_messaging_bus.py backend/tests/test_messaging_templates.py backend/tests/test_messaging_senders.py backend/tests/test_messaging_routes.py -v --cov=backend/app/messaging --cov-report=term --cov-report=html

# Expected result:
# 79 tests passing
# Coverage ≥90% for all messaging/* files
```

### THEN: DEPLOY
```powershell
# Stage all files
git add backend/app/messaging backend/tests/test_messaging_*.py docs/prs/PR_060_*.md PR_060_*.md

# Commit
git commit -m "PR-060: Messaging Bus & Templates - Complete with 3 senders + API routes + 79 tests"

# Push
git push origin main
```

---

**📌 MAIN ISSUE**: Test file `test_messaging_bus.py` imports functions that don't exist as module-level (they're class methods)

**🔧 FIX TIME**: 30-45 minutes (update 1 test file + verify other 3)

**✅ THEN**: Tests pass → Coverage ≥90% → Deploy → Done!
