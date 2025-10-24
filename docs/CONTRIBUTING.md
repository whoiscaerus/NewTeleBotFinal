# Contributing Guidelines

## 📋 Code Style & Standards

### Python (Backend)

All backend code follows strict standards enforced by CI/CD:

**Tools**: Black (formatting) + Ruff (linting) + mypy (type checking)

```bash
# Auto-format code
make fmt

# Check code quality
make lint typecheck

# Run all checks
make quality
```

**Rules**:
- ✅ **Line Length**: 88 characters (Black standard)
- ✅ **Type Hints**: Required on all functions (Python 3.11+)
- ✅ **Docstrings**: Required on all modules, classes, functions
- ✅ **Imports**: Sorted with isort, organized by type
- ✅ **Error Handling**: Try/except with logging, no bare `except`
- ✅ **No Globals**: Use dependency injection instead
- ✅ **No Prints**: Use structured logging instead
- ✅ **No TODOs**: Code must be complete, no FIXMEs

### Example: Well-Formatted Code

```python
"""Module for signal processing and approval."""

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.errors import InvalidSignalError
from backend.app.signals.models import Signal

logger = logging.getLogger(__name__)


async def create_signal(
    db: AsyncSession,
    instrument: str,
    side: str,
    price: float,
) -> Signal:
    """
    Create a new trading signal.

    Args:
        db: Database session
        instrument: Trading instrument (e.g., "GOLD")
        side: Trade direction ("buy" or "sell")
        price: Entry price

    Returns:
        Signal: Created signal with ID

    Raises:
        InvalidSignalError: If parameters invalid

    Example:
        >>> signal = await create_signal(db, "GOLD", "buy", 1950.50)
        >>> assert signal.id is not None
    """
    if instrument not in VALID_INSTRUMENTS:
        raise InvalidSignalError(f"Unknown instrument: {instrument}")

    logger.info(
        "Creating signal",
        extra={"instrument": instrument, "side": side, "price": price},
    )

    signal = Signal(
        instrument=instrument,
        side=0 if side == "buy" else 1,
        price=price,
    )

    db.add(signal)
    await db.commit()
    await db.refresh(signal)

    logger.info("Signal created", extra={"signal_id": signal.id})

    return signal
```

---

## ✅ Testing Requirements

### Minimum Coverage
- **Backend**: 90% code coverage (enforced by CI/CD)
- **Frontend**: 70% component coverage
- **Error Paths**: 100% (all exceptions tested)

### Test Structure

```python
@pytest.mark.asyncio
async def test_create_signal_valid(db: AsyncSession):
    """Test signal creation with valid input."""
    signal = await create_signal(db, "GOLD", "buy", 1950.50)
    assert signal.id is not None
    assert signal.status == "new"


@pytest.mark.asyncio
async def test_create_signal_invalid_instrument(db: AsyncSession):
    """Test signal creation rejects invalid instrument."""
    with pytest.raises(InvalidSignalError, match="Unknown instrument"):
        await create_signal(db, "INVALID", "buy", 1950.50)


@pytest.mark.asyncio
async def test_create_signal_db_error(db: AsyncSession, monkeypatch):
    """Test signal creation handles database errors."""
    async def mock_commit(*args, **kwargs):
        raise DatabaseError("Connection failed")

    monkeypatch.setattr(db, "commit", mock_commit)

    with pytest.raises(DatabaseError):
        await create_signal(db, "GOLD", "buy", 1950.50)
```

### Run Tests

```bash
make test           # All tests
make test-cov       # With coverage report
make test-fast      # Quick run
make test-unit      # Unit tests only
```

---

## 📝 Pull Request Process

### Before Creating PR

1. **Update code**: Make your changes
2. **Format & lint**: `make quality`
3. **Run tests**: `make test-local`
4. **Check coverage**: `make test-cov` (must be ≥90%)
5. **Update CHANGELOG.md**: Document your change

### Creating PR

**Title Format**: `[PR-XXX] Brief description`

Example: `[PR-021] Implement signals API with HMAC validation`

**PR Description Template**:

```markdown
## Description
Describe what this PR implements.

## Changes
- List key changes
- Be specific about files modified

## Testing
- [ ] All local tests passing
- [ ] Coverage ≥90%
- [ ] No lint/type check errors

## Checklist
- [ ] Code formatted with Black
- [ ] Type hints added
- [ ] Docstrings complete
- [ ] Tests added for new code
- [ ] No secrets in code
- [ ] CHANGELOG.md updated
- [ ] Related PRs linked (if any)

## Dependencies
- PR-XXX (if this depends on other PRs)
```

### Merge Criteria

✅ All checks must pass:
- GitHub Actions CI/CD green
- Code review approved (1+ reviewer)
- No merge conflicts
- All conversations resolved

---

## 📋 Commit Messages

Use conventional commit format:

```
[module] Brief description

Longer explanation if needed. Explain *why* not just *what*.

Fixes: #123
Related: PR-XXX
```

**Examples**:
```
[signals] Add HMAC signature validation to signals API
[auth] Implement JWT token refresh with rotation
[tests] Add 12 edge cases for signal creation
[docs] Update README with database setup instructions
```

---

## 🔍 Code Review Checklist

**For reviewers**:

- ✅ Code follows style guidelines
- ✅ Type hints present and correct
- ✅ Error handling complete
- ✅ Tests cover happy path + error paths
- ✅ No hardcoded values (use config/env)
- ✅ No secrets in code
- ✅ Docstrings clear and complete
- ✅ No TODOs or FIXMEs
- ✅ Performance implications considered
- ✅ Security implications addressed

---

## 🚀 Release Process

Before merging to `main`:

1. Version update: `X.Y.Z` in `pyproject.toml`
2. Update `CHANGELOG.md` with all changes
3. Create GitHub Release with release notes
4. Tag: `git tag vX.Y.Z`
5. Build Docker image: `docker build -t platform:vX.Y.Z .`

---

## 📚 Documentation Requirements

Every PR needs 4 documentation files:

1. **PR-XXX-IMPLEMENTATION-PLAN.md** — What you're building
2. **PR-XXX-IMPLEMENTATION-COMPLETE.md** — What you built
3. **PR-XXX-ACCEPTANCE-CRITERIA.md** — How to verify it works
4. **PR-XXX-BUSINESS-IMPACT.md** — Why it matters

See `/docs/prs/` directory for examples.

---

## 🧠 Lessons Learned

After completing each PR, document any new patterns or problems:

1. Review all issues encountered
2. Document solution with code examples
3. Add to `/base_files/PROJECT_TEMPLATES/02_UNIVERSAL_PROJECT_TEMPLATE.md`
4. Section: "LESSONS LEARNED - Common Issues & Solutions"

This helps future projects avoid the same mistakes.

---

## 🎯 Common Mistakes to Avoid

❌ **Don't**:
- Leave TODOs/FIXMEs in code
- Skip tests for "quick fixes"
- Mix formatting changes with logic changes
- Commit without running `make test-local`
- Use `print()` instead of logging
- Hardcode configuration values
- Store secrets in code or `.env`

✅ **Do**:
- Run `make quality` before committing
- Write tests first (TDD)
- Keep commits focused (one feature per commit)
- Update documentation
- Run full test suite before pushing
- Use structured logging with context
- Use environment variables for config

---

## 🆘 Need Help?

1. **Read**: [README.md](../README.md), [COMPLETE_BUILD_PLAN_ORDERED.md](../base_files/COMPLETE_BUILD_PLAN_ORDERED.md)
2. **Search**: GitHub Issues and Discussions
3. **Ask**: Create a Discussion or comment on related Issue
4. **Debug**: Check CI/CD logs for specific errors

---

## 📞 Questions?

- **Architecture**: See [Enterprise_System_Build_Plan.md](../base_files/Enterprise_System_Build_Plan.md)
- **Building features**: See [Final_Master_Prs.md](../base_files/Final_Master_Prs.md)
- **Patterns & lessons**: See [02_UNIVERSAL_PROJECT_TEMPLATE.md](../base_files/PROJECT_TEMPLATES/02_UNIVERSAL_PROJECT_TEMPLATE.md)

---

**Status**: Active  
**Last Updated**: October 24, 2025
