# 🚀 UNIVERSAL PROJECT TEMPLATE - PRODUCTION-READY STARTER KIT

## 📖 Table of Contents

1. [Quick Start](#quick-start)
2. [Project Structure](#project-structure)
3. [File Templates](#file-templates)
4. [GitHub Actions Workflows](#github-actions-workflows)
5. [PR Master System](#pr-master-system)
6. [Development Workflow](#development-workflow)
7. [Quality Gates](#quality-gates)
8. [Deployment Pipeline](#deployment-pipeline)

---

## 🎯 Quick Start

### For New Projects (Copy-Paste Setup)

```bash
# 1. Create new repository on GitHub
# 2. Clone it locally
git clone https://github.com/your-org/your-project.git
cd your-project

# 3. Copy ALL template files from this directory
cp -r /path/to/PROJECT_TEMPLATES/* .

# 4. Update project-specific values
#    - Replace "YOUR_PROJECT_NAME" in all files
#    - Replace "YOUR_ORG" with your GitHub org
#    - Update Python/Node versions if needed

# 5. Initialize git
git add .
git commit -m "Initial commit: Add production-ready project structure"
git push origin main

# 6. GitHub Actions will run automatically
#    - Go to Actions tab to verify
#    - All workflows should pass ✅
```

---

## 📁 Project Structure

### Complete Directory Layout

```
your-project/
├── .github/
│   ├── workflows/                    # CI/CD pipelines
│   │   ├── tests.yml                 # Core testing
│   │   ├── pr-checks.yml             # PR validation
│   │   ├── security.yml              # Security scans
│   │   ├── migrations.yml            # Database validation
│   │   ├── docker.yml                # Container builds
│   │   ├── deploy-staging.yml        # Staging deploy
│   │   ├── deploy-production.yml     # Production deploy
│   │   └── README.md                 # Workflow documentation
│   ├── PULL_REQUEST_TEMPLATE.md      # PR template
│   ├── ISSUE_TEMPLATE/               # Issue templates
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   └── copilot-instructions.md       # Copilot AI configuration
│
├── backend/                          # Backend application
│   ├── app/
│   │   ├── core/                     # Core utilities
│   │   │   ├── __init__.py
│   │   │   ├── settings.py           # Pydantic settings
│   │   │   ├── logging.py            # Structured logging
│   │   │   └── middleware.py         # Request ID middleware
│   │   ├── orchestrator/             # Main app module
│   │   │   ├── __init__.py
│   │   │   ├── main.py               # FastAPI app factory
│   │   │   └── routes.py             # Health/version endpoints
│   │   └── main.py                   # ASGI entry point
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py               # Shared fixtures
│   │   └── test_health.py            # Example tests
│   ├── alembic/
│   │   ├── env.py                    # Migration environment
│   │   └── versions/                 # Migration files
│   ├── alembic.ini                   # Alembic config
│   ├── conftest.py                   # Root pytest config
│   ├── pytest.ini                    # pytest settings
│   ├── requirements.txt              # Python dependencies
│   ├── Dockerfile                    # Docker image definition
│   └── .env.example                  # Environment variables template
│
├── frontend/                         # Frontend application (optional)
│   ├── src/
│   ├── tests/
│   ├── package.json
│   └── Dockerfile
│
├── docs/                             # Documentation
│   ├── prs/                          # PR implementation docs
│   │   ├── INDEX.md                  # PR index
│   │   └── templates/                # PR doc templates
│   ├── api/                          # API documentation
│   └── architecture/                 # Architecture diagrams
│
├── scripts/                          # Automation scripts
│   ├── verify/                       # PR verification scripts
│   │   └── verify-pr-template.sh
│   ├── deploy/                       # Deployment scripts
│   └── setup/                        # Setup scripts
│
├── base_files/                       # Project management
│   ├── Master_PRs.md                 # Complete PR roadmap
│   ├── QUICK_REFERENCE.md            # Quick lookup guide
│   └── PROJECT_TEMPLATES/            # This directory
│
├── .gitignore                        # Git ignore rules
├── .env.example                      # Environment template
├── README.md                         # Project documentation
├── LICENSE                           # License file
├── CHANGELOG.md                      # Version history
└── CONTRIBUTING.md                   # Contribution guide
```

---

## 📄 File Templates

### 1. Root `.gitignore`

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST

# Virtual environments
venv/
ENV/
env/
.venv

# Environment variables
.env
.env.local
.env.*.local

# Testing
.pytest_cache/
.coverage
htmlcov/
.tox/
coverage.xml
*.cover

# IDEs
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Logs
*.log
logs/

# Database
*.db
*.sqlite
*.sqlite3

# Docker
docker-compose.override.yml

# Node
node_modules/
npm-debug.log
yarn-error.log

# Build artifacts
*.tar.gz
*.zip
```

---

### 2. `.env.example`

```env
# Application
APP_NAME=your-project-name
APP_ENV=development
APP_VERSION=1.0.0
APP_BUILD=local
APP_LOG_LEVEL=INFO

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/dbname
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10
DATABASE_POOL_PRE_PING=true

# Redis
REDIS_URL=redis://localhost:6379/0

# Security
SECRET_KEY=your-secret-key-here-change-in-production
ALLOWED_HOSTS=localhost,127.0.0.1

# External APIs
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
OPENAI_API_KEY=your-openai-api-key

# Monitoring
SENTRY_DSN=https://your-sentry-dsn
```

---

### 3. Root `README.md`

```markdown
# YOUR_PROJECT_NAME

[![Tests](https://github.com/YOUR_ORG/YOUR_PROJECT_NAME/actions/workflows/tests.yml/badge.svg)](https://github.com/YOUR_ORG/YOUR_PROJECT_NAME/actions/workflows/tests.yml)
[![Security](https://github.com/YOUR_ORG/YOUR_PROJECT_NAME/actions/workflows/security.yml/badge.svg)](https://github.com/YOUR_ORG/YOUR_PROJECT_NAME/actions/workflows/security.yml)
[![Docker](https://github.com/YOUR_ORG/YOUR_PROJECT_NAME/actions/workflows/docker.yml/badge.svg)](https://github.com/YOUR_ORG/YOUR_PROJECT_NAME/actions/workflows/docker.yml)

## 📖 Overview

[Brief description of your project]

## 🚀 Features

- Feature 1
- Feature 2
- Feature 3

## 🛠️ Tech Stack

- **Backend**: Python 3.11, FastAPI, SQLAlchemy, PostgreSQL
- **Frontend**: Next.js 14, TypeScript, Tailwind CSS
- **Infrastructure**: Docker, GitHub Actions, AWS/Vercel

## 📋 Prerequisites

- Python 3.11+
- PostgreSQL 16+
- Redis 7+
- Node.js 18+ (for frontend)
- Docker (optional)

## ⚡ Quick Start

### 1. Clone Repository

\`\`\`bash
git clone https://github.com/YOUR_ORG/YOUR_PROJECT_NAME.git
cd YOUR_PROJECT_NAME
\`\`\`

### 2. Setup Backend

\`\`\`bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your values
\`\`\`

### 3. Setup Database

\`\`\`bash
# Start PostgreSQL and Redis (Docker)
docker-compose up -d postgres redis

# Run migrations
alembic upgrade head
\`\`\`

### 4. Run Backend

\`\`\`bash
uvicorn app.main:app --reload --port 8000
# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
\`\`\`

### 5. Run Tests

\`\`\`bash
python -m pytest tests/ -v --cov=app
\`\`\`

## 📚 Documentation

- [API Documentation](docs/api/README.md)
- [Architecture](docs/architecture/README.md)
- [Contributing Guide](CONTRIBUTING.md)
- [PR Implementation Guide](docs/prs/INDEX.md)

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)

## 📄 License

[Your License] - see [LICENSE](LICENSE)

## 🙏 Acknowledgments

- [Any credits or acknowledgments]
```

---

### 4. `CONTRIBUTING.md`

```markdown
# Contributing Guide

## Development Workflow

### 1. Create Feature Branch

\`\`\`bash
git checkout -b feat/your-feature-name
# or
git checkout -b fix/your-bug-fix
\`\`\`

### 2. Make Changes

- Write code
- Add tests (≥90% coverage)
- Update documentation

### 3. Run Quality Checks

\`\`\`bash
# Format code
python -m black backend/app/ backend/tests/

# Lint code
ruff check backend/app/ backend/tests/

# Run tests
python -m pytest backend/tests/ -v --cov=app --cov-report=term-missing

# All must pass before committing
\`\`\`

### 4. Commit Changes

\`\`\`bash
git add .
git commit -m "PR-XXX: Your descriptive commit message"
\`\`\`

**Commit Message Format:**
- `PR-XXX: Description` (for PR implementation)
- `feat: Description` (new feature)
- `fix: Description` (bug fix)
- `docs: Description` (documentation)
- `refactor: Description` (code refactoring)
- `test: Description` (add/update tests)
- `chore: Description` (maintenance)

### 5. Push and Create PR

\`\`\`bash
git push origin feat/your-feature-name
\`\`\`

Then create Pull Request on GitHub with template.

## Pull Request Requirements

✅ All tests passing
✅ Coverage ≥90% (backend), ≥70% (frontend)
✅ Black formatting applied
✅ Ruff linting clean
✅ Documentation updated
✅ PR template filled out completely

## Code Review Process

1. Create PR
2. GitHub Actions runs automatically
3. Wait for all checks to pass ✅
4. Request review from team
5. Address review comments
6. Get approval (minimum 1 reviewer)
7. Merge to develop
8. Delete feature branch

## Branch Strategy

- `main` - Production code (protected)
- `develop` - Development branch (protected)
- `feat/*` - Feature branches
- `fix/*` - Bug fix branches
- `chore/*` - Maintenance branches

## Questions?

Ask in project chat or create discussion on GitHub.
```

---

## 🔄 GitHub Actions Workflows

### Complete Workflow Set (Copy to `.github/workflows/`)

**All 7 workflow files are included in this template directory:**

1. `tests.yml` - Core testing
2. `pr-checks.yml` - PR validation
3. `security.yml` - Security scanning
4. `migrations.yml` - Database validation
5. `docker.yml` - Docker build
6. `deploy-staging.yml` - Staging deployment
7. `deploy-production.yml` - Production deployment

**After copying:**
1. Replace `YOUR_ORG/YOUR_PROJECT_NAME` with actual values
2. Update Python/Node versions if needed
3. Verify all environment variables match your `.env.example`

---

## 📋 PR Master System

### PR Master Document Structure

Create `base_files/Master_PRs.md`:

```markdown
# Master PR Roadmap

## PR-1: Project Foundation

**Priority:** CRITICAL
**Dependencies:** None
**Estimated Effort:** 1 day

### Goal
Set up core project structure with FastAPI, PostgreSQL, Redis, and testing framework.

### Files to Create
- `backend/app/core/settings.py`
- `backend/app/core/logging.py`
- `backend/app/core/middleware.py`
- `backend/app/orchestrator/main.py`
- `backend/app/orchestrator/routes.py`
- `backend/app/main.py`
- `backend/tests/test_health.py`
- `backend/tests/conftest.py`

### Database Schema
None (infrastructure only)

### API Endpoints
- `GET /api/v1/health` - Health check
- `GET /api/v1/ready` - Readiness check
- `GET /api/v1/version` - Version info

### Acceptance Criteria
- [ ] FastAPI app starts without errors
- [ ] All 3 endpoints return 200 OK
- [ ] Request ID middleware working
- [ ] Structured JSON logging configured
- [ ] Settings loaded from environment
- [ ] 12 tests passing
- [ ] ≥90% code coverage

**Status:** 🔲 NOT STARTED

---

## PR-2: Database & Alembic Setup

**Priority:** HIGH
**Dependencies:** PR-1
**Estimated Effort:** 2 days

[Continue with detailed PR specs...]
```

### PR Documentation Templates

For each PR, create 4 documents in `docs/prs/`:

1. **PR-XXX-IMPLEMENTATION-PLAN.md**
2. **PR-XXX-ACCEPTANCE-CRITERIA.md**
3. **PR-XXX-BUSINESS-IMPACT.md**
4. **PR-XXX-IMPLEMENTATION-COMPLETE.md**

---

## 🔄 Development Workflow (Complete Process)

### Phase 1: Planning

```bash
# 1. Read PR spec from Master_PRs.md
# 2. Create implementation plan document
# 3. Identify all dependencies
# 4. Create feature branch
git checkout -b feat/pr-XXX-description
```

### Phase 2: Implementation

```bash
# 1. Create all files as specified in PR
# 2. Write production-ready code (no TODOs)
# 3. Apply Black formatting from start
python -m black backend/app/ backend/tests/ --line-length=88

# 4. Run linting
ruff check backend/app/ backend/tests/
```

### Phase 3: Testing

```bash
# 1. Write comprehensive tests (≥90% coverage)
# 2. Run tests locally
python -m pytest backend/tests/ -v --tb=short

# 3. Check coverage
python -m pytest backend/tests/ --cov=app --cov-report=term-missing --cov-report=html

# 4. Verify all acceptance criteria met
```

### Phase 4: Documentation

```bash
# Create 4 required docs in docs/prs/:
# 1. PR-XXX-IMPLEMENTATION-PLAN.md
# 2. PR-XXX-ACCEPTANCE-CRITERIA.md
# 3. PR-XXX-BUSINESS-IMPACT.md
# 4. PR-XXX-IMPLEMENTATION-COMPLETE.md
```

### Phase 5: Commit & Push

```bash
# 1. Stage all files
git add .

# 2. Commit with clear message
git commit -m "PR-XXX: [Description] - All tests passing (X/X)"

# 3. Push to GitHub
git push origin feat/pr-XXX-description
```

### Phase 6: CI/CD Verification

```bash
# 1. GitHub Actions runs automatically
# 2. Monitor Actions tab
# 3. All checks must pass:
#    ✅ code-quality (Black + Ruff)
#    ✅ backend-tests (pytest)
#    ✅ security (non-blocking warnings OK)
#    ✅ migrations (if applicable)
#    ✅ docker (build succeeds)
```

### Phase 7: Pull Request

```bash
# 1. Create PR on GitHub
# 2. Fill out PR template completely
# 3. Link to PR docs
# 4. Request review
# 5. Address feedback
# 6. Get approval
# 7. Merge to develop
```

---

## ✅ Quality Gates (ALL Must Pass)

### Code Quality Gate

- ✅ Black formatting: All files compliant (88-char line)
- ✅ Ruff linting: Zero errors, zero warnings
- ✅ No TODOs or FIXMEs in code
- ✅ No hardcoded values (use settings/env)
- ✅ No print() statements (use logging)
- ✅ All functions have docstrings
- ✅ All functions have type hints

### Testing Gate

- ✅ Backend coverage ≥90%
- ✅ Frontend coverage ≥70%
- ✅ All tests passing (100%)
- ✅ Each acceptance criterion has test
- ✅ Edge cases tested
- ✅ Error scenarios tested
- ✅ Integration tests included

### Documentation Gate

- ✅ Implementation plan created
- ✅ Acceptance criteria documented
- ✅ Business impact explained
- ✅ Implementation complete checklist
- ✅ All 4 docs have no placeholders
- ✅ Code comments for complex logic
- ✅ README updated if needed

### Security Gate

- ✅ No secrets in code
- ✅ All inputs validated
- ✅ All errors handled gracefully
- ✅ SQL injection prevented (use ORM)
- ✅ XSS prevented (escape output)
- ✅ CSRF tokens used (state-changing requests)
- ✅ Security scan passing (or warnings documented)

### Integration Gate

- ✅ GitHub Actions all passing
- ✅ No merge conflicts
- ✅ CHANGELOG.md updated
- ✅ Version bumped (if applicable)
- ✅ Migration tested (up + down)
- ✅ Docker build succeeds

---

## 🚀 Deployment Pipeline

### Staging Deployment

**Trigger:** Merge to `develop` branch

**Process:**
1. GitHub Actions runs tests
2. Builds Docker image
3. Pushes to staging environment
4. Runs smoke tests
5. Sends notification

**URL:** https://staging.yourdomain.com

### Production Deployment

**Trigger:** Create git tag `v*.*.*`

**Process:**
1. Manual approval required
2. GitHub Actions runs full test suite
3. Builds production Docker image
4. Deploys to production
5. Runs health checks
6. Creates GitHub Release
7. Sends notification

**URL:** https://yourdomain.com

### Rollback Process

```bash
# If deployment fails:
# 1. Identify previous working tag
git tag -l

# 2. Create rollback tag
git tag v1.0.1-rollback v1.0.0
git push origin v1.0.1-rollback

# 3. Deployment pipeline runs with old code
# 4. Investigate issue offline
```

---

## 🎓 Best Practices

### 1. Branch Naming

- ✅ `feat/pr-123-user-authentication`
- ✅ `fix/login-bug`
- ✅ `chore/update-dependencies`
- ❌ `my-branch`
- ❌ `test`
- ❌ `asdf`

### 2. Commit Messages

- ✅ `PR-123: Add user authentication with JWT`
- ✅ `fix: Resolve login redirect bug`
- ✅ `docs: Update API documentation`
- ❌ `wip`
- ❌ `fix stuff`
- ❌ `asdf`

### 3. Code Organization

- ✅ One class per file
- ✅ Functions ≤30 lines
- ✅ Files ≤300 lines
- ✅ Clear separation of concerns
- ❌ God classes (1000+ lines)
- ❌ Circular imports
- ❌ Magic numbers

### 4. Testing

- ✅ Test file name: `test_module_name.py`
- ✅ Test function name: `test_function_does_what()`
- ✅ Arrange-Act-Assert pattern
- ✅ One assertion per test
- ❌ Test implementation details
- ❌ Test external APIs directly
- ❌ Flaky tests

---

## 🔧 Copilot Instructions Integration

This template includes `.github/copilot-instructions.md` that tells GitHub Copilot:

- ✅ Project structure and conventions
- ✅ PR implementation workflow
- ✅ Testing requirements
- ✅ Documentation standards
- ✅ Quality gates
- ✅ Deployment process

**Copilot will automatically:**
- Suggest code that follows Black formatting
- Add type hints to all functions
- Include docstrings with examples
- Create comprehensive tests
- Handle errors gracefully
- Use structured logging

---

## 🎯 Success Checklist

### Project Initialization ✅

- [ ] All template files copied to new repo
- [ ] Project-specific values updated in all files
- [ ] `.env` created from `.env.example`
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Database initialized (`alembic upgrade head`)
- [ ] Tests passing locally (`pytest`)
- [ ] GitHub Actions passing (all workflows green ✅)
- [ ] README badges showing passing status

### First PR Complete ✅

- [ ] Feature branch created from `develop`
- [ ] Code implemented per PR spec
- [ ] Tests written (≥90% coverage)
- [ ] All quality gates passed
- [ ] 4 PR docs created
- [ ] GitHub Actions passing
- [ ] Code reviewed and approved
- [ ] Merged to `develop`
- [ ] Staging deployment successful

### Production Ready ✅

- [ ] 10+ PRs implemented successfully
- [ ] All critical features complete
- [ ] Security scans clean
- [ ] Performance tested
- [ ] Documentation complete
- [ ] Staging environment stable
- [ ] Tagged for production (v1.0.0)
- [ ] Production deployment successful

---

## � LESSONS LEARNED - Common Issues & Solutions

### Learned from Real PR Implementation (PR-1 & PR-2)

This section documents actual problems encountered during production implementation and their solutions. **Apply these patterns from day 1 to avoid costly refactoring.**

---

### 1. Database Connection Issues

#### Problem
- **Symptom:** `sessionmaker.__call__() takes 1 positional argument but 2 were given`
- **Root Cause:** Incorrectly passing engine to sessionmaker factory
- **Why It Happens:** SQLAlchemy 2.0 async pattern is different from 1.4

#### Solution
```python
# ❌ WRONG (creates factory then tries to call it with engine)
SessionLocal = SessionLocal(test_engine)

# ✅ CORRECT (sessionmaker already bound to engine)
SessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)
async with SessionLocal() as session:
    # Use session
```

#### Prevention
- Always test async database code locally before pushing
- Use pytest fixtures to inject engine, not sessionmaker
- Document sessionmaker usage in code comments

---

### 2. SQLite vs PostgreSQL Pool Configuration

#### Problem
- **Symptom:** `TypeError: Invalid argument(s) 'pool_size','max_overflow' sent to create_engine()`
- **Root Cause:** SQLite uses StaticPool and doesn't support pool_size/max_overflow
- **Why It Happens:** Config applies same settings to all database backends

#### Solution
```python
# ❌ WRONG (SQLite doesn't support pool configuration)
engine = create_async_engine(
    url,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
)

# ✅ CORRECT (only apply pool settings to PostgreSQL)
engine_kwargs = {"echo": False}

if url.startswith("postgresql"):
    engine_kwargs.update({
        "pool_size": 20,
        "max_overflow": 10,
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    })

engine = create_async_engine(url, **engine_kwargs)
```

#### Prevention
- Always differentiate between test (SQLite) and production (PostgreSQL) configs
- Document database-specific parameters
- Test with both SQLite and PostgreSQL locally

---

### 3. Async/Await Syntax Errors

#### Problem
- **Symptom:** `TypeError: object NoneType can't be used in 'await' expression`
- **Root Cause:** Result object doesn't have `.close()` method in SQLAlchemy 2.0
- **Why It Happens:** API changed between versions; documentation outdated

#### Solution
```python
# ❌ WRONG (result.close() doesn't exist in 2.0)
result = await conn.execute(text("SELECT 1"))
await result.close()

# ✅ CORRECT (just execute, context manager handles cleanup)
from sqlalchemy import text
async with engine.connect() as conn:
    await conn.execute(text("SELECT 1"))
    # Connection closes automatically
```

#### Prevention
- Pin SQLAlchemy version in requirements.txt: `sqlalchemy==2.0.23`
- Test all async database operations locally
- Check SQLAlchemy 2.0 migration guide for API changes

---

### 4. Environment Variables in Tests

#### Problem
- **Symptom:** Tests pass locally, fail on CI/CD (connection errors)
- **Root Cause:** Test environment doesn't have DATABASE_URL set
- **Why It Happens:** Tests inherit parent environment; app tries real DB connection

#### Solution
```python
# In backend/tests/conftest.py (root pytest config)
import os

# Set test environment BEFORE any imports
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["APP_LOG_LEVEL"] = "INFO"

# Now safe to import app modules
import pytest
from backend.app.main import create_app
```

#### Prevention
- Always set environment in conftest.py BEFORE imports
- Use in-memory SQLite for tests: `sqlite+aiosqlite:///:memory:`
- Document required environment variables in README

---

### 5. Test Fixtures Scope Issues

#### Problem
- **Symptom:** `RuntimeWarning: coroutine was never awaited`
- **Root Cause:** Fixture needs to be async but pytest runs it as sync
- **Why It Happens:** Mock functions aren't properly awaited in tests

#### Solution
```python
# ❌ WRONG (async function, not awaited)
async def mock_engine():
    """This won't be awaited by pytest"""
    raise Exception("Connection failed")

# ✅ CORRECT (monkeypatch synchronously)
monkeypatch.setattr("app.db._engine", test_engine)
# Now await verify_db_connection() naturally awaits the mocked engine
```

#### Prevention
- Use `pytest.mark.asyncio` decorator on async tests
- Use monkeypatch for mocking async functions
- Avoid creating async mock functions - use sync mocks instead

---

### 6. Database URL Validation

#### Problem
- **Symptom:** Valid SQLite URLs rejected during testing
- **Root Cause:** URL validation too strict; only allows PostgreSQL
- **Why It Happens:** Production code assumes PostgreSQL-only

#### Solution
```python
# ❌ WRONG (doesn't allow test databases)
if not db_url.startswith(("postgresql", "postgresql+psycopg")):
    raise ValueError(f"Invalid DATABASE_URL: {db_url}")

# ✅ CORRECT (allows both production and test databases)
if not db_url.startswith(("postgresql", "postgresql+psycopg", "postgresql+asyncpg", "sqlite")):
    raise ValueError(f"Invalid DATABASE_URL: {db_url}")
```

#### Prevention
- Document supported database URLs
- Support SQLite for testing from day 1
- Add comments explaining why each URL type is needed

---

### 7. Lifespan Event Error Handling

#### Problem
- **Symptom:** Application crashes on startup if database unavailable
- **Root Cause:** Unhandled exception in lifespan startup
- **Why It Happens:** No try/except around database initialization

#### Solution
```python
# ❌ WRONG (crashes if DB init fails)
@asynccontextmanager
async def lifespan(app):
    await init_db()
    await verify_db_connection()
    yield
    await close_db()

# ✅ CORRECT (graceful degradation)
@asynccontextmanager
async def lifespan(app):
    try:
        await init_db()
        if await verify_db_connection():
            logger.info("Database connected")
        else:
            logger.warning("Database unavailable - running in degraded mode")
    except Exception as e:
        logger.error(f"Database init failed: {e}")
        # Continue - app still starts, just without DB

    yield

    try:
        await close_db()
    except Exception as e:
        logger.error(f"Error closing database: {e}")
```

#### Prevention
- Always wrap startup operations in try/except
- Log startup failures clearly (ERROR level)
- Design app to work in degraded mode (no DB)
- Add health checks that report actual status

---

### 8. Black Formatting in CI/CD

#### Problem
- **Symptom:** `ruff check` fails with "unused imports" on CI but passes locally
- **Root Cause:** Code not formatted with Black before commit
- **Why It Happens:** Developer environment has different Black version

#### Solution
```bash
# In CI/CD workflow BEFORE running tests:
python -m black --check backend/ frontend/  # Verify formatting
python -m ruff check backend/ frontend/     # Lint check

# If fails: run locally and commit changes
python -m black backend/ frontend/          # Auto-format
git add .
git commit -m "Format code with Black (88-char lines)"
```

#### Prevention
- Run Black formatting BEFORE every commit: `python -m black .`
- Add pre-commit hook (see template in `.git/hooks/pre-commit`)
- Use VS Code Black extension for auto-format on save
- Pin Black version: `black==23.12.1`

---

### 9. Test Coverage Measurement

#### Problem
- **Symptom:** Coverage shows 86% locally, but test report incomplete
- **Root Cause:** Not all code paths tested; error handling paths uncovered
- **Why It Happens:** Happy path tests don't cover exceptions

#### Solution
```python
# ❌ WRONG (only happy path)
@pytest.mark.asyncio
async def test_verify_db_connection_success():
    result = await verify_db_connection()
    assert result is True

# ✅ CORRECT (happy path + error path)
@pytest.mark.asyncio
async def test_verify_db_connection_success(test_engine, monkeypatch):
    """Database connection succeeds"""
    monkeypatch.setattr("app.db.get_engine", lambda: test_engine)
    result = await verify_db_connection()
    assert result is True

@pytest.mark.asyncio
async def test_verify_db_connection_failure(monkeypatch):
    """Database connection fails gracefully"""
    def mock_engine():
        raise ConnectionError("Connection refused")
    
    monkeypatch.setattr("app.db.get_engine", mock_engine)
    result = await verify_db_connection()
    assert result is False  # Returns False, doesn't crash
```

#### Prevention
- For every try/except, write a test for the except path
- Use coverage reports: `pytest --cov=app --cov-report=html`
- Target ≥90% coverage; document why uncovered lines can't be tested
- Review coverage report after each PR

---

### 10. Backward Compatibility with Existing Code

#### Problem
- **Symptom:** PR-1 tests fail after PR-2 changes to lifespan
- **Root Cause:** New database initialization in lifespan breaks old tests
- **Why It Happens:** Tests weren't updated to match new startup behavior

#### Solution
```python
# In conftest.py - set up test environment ONCE
import os
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

# Then all tests automatically use test database
# Both old tests (PR-1) and new tests (PR-2) pass
```

#### Prevention
- Always run ALL tests after making infrastructure changes
- Update conftest.py before updating application code
- Add backward compatibility tests: `test_pr1_still_works()`
- Document breaking changes clearly

---

### 11. Import Order and Timing

#### Problem
- **Symptom:** `ModuleNotFoundError: No module named 'backend'`
- **Root Cause:** Running pytest from wrong directory; PYTHONPATH incorrect
- **Why It Happens:** Relative imports fail when working directory changes

#### Solution
```bash
# ❌ WRONG (changes directory, breaks PYTHONPATH)
cd backend && pytest tests/

# ✅ CORRECT (run from project root)
python -m pytest backend/tests/

# In pytest.ini (ensures proper path handling)
[pytest]
pythonpath = .
testpaths = backend/tests
```

#### Prevention
- Always run pytest from project root: `python -m pytest`
- Create pytest.ini in root with `pythonpath = .`
- Document in README: "Always run tests from project root"
- Add CI/CD check: fail if tests run from wrong directory

---

### 12. Type Hints and SQLAlchemy 2.0

#### Problem
- **Symptom:** Type checker complains about AsyncSession usage
- **Root Cause:** Missing type hints on async session functions
- **Why It Happens:** SQLAlchemy 2.0 types are strict

#### Solution
```python
# ❌ WRONG (no type hints)
async def get_db():
    async with SessionLocal() as session:
        yield session

# ✅ CORRECT (full type hints)
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            raise
        finally:
            await session.close()
```

#### Prevention
- Use type hints everywhere (Python 3.11+)
- Enable strict type checking: `mypy --strict`
- Add type hints to all FastAPI dependencies
- Document complex types with comments

---

### 13. Raw Request Body Size Validation BEFORE Library Parsing

#### Problem (Discovered PR-3)
- **Symptom:** Oversized payloads return 422 (Unprocessable Entity) instead of 413 (Payload Too Large)
- **Root Cause:** Pydantic library parses request before route-level size check
- **Why It Happens:** Size validation happens AFTER framework libraries, wrong response code

#### Solution
```python
# ❌ WRONG (Pydantic parses first, then size check)
@router.post("/signals")
async def create_signal(request: SignalCreate):
    body = await request.body()
    if len(body) > MAX_SIZE:  # Too late - Pydantic already threw 422
        raise HTTPException(413, "Too large")

# ✅ CORRECT (size check FIRST, before any library parsing)
@router.post("/signals")
async def create_signal(request: Request):
    # 1. Check raw body size FIRST
    body = await request.body()
    MAX_PAYLOAD_SIZE = 32 * 1024
    if len(body) > MAX_PAYLOAD_SIZE:
        raise HTTPException(status_code=413, detail="Request body too large")
    
    # 2. THEN parse with Pydantic
    try:
        body_dict = json.loads(body)
        signal = SignalCreate(**body_dict)
    except ValidationError as e:
        # This WILL return 422 (correct for validation errors)
        raise HTTPException(status_code=422, detail=str(e))
```

#### Prevention
- Always validate request size at route entry point, BEFORE library parsing
- Check raw `await request.body()` length
- Return 413 for size, 422 for validation, 400 for format errors
- Add comment explaining why this order matters

---

### 14. Distinguish Between Missing (None) vs Invalid (Empty) Values

#### Problem (Discovered PR-3)
- **Symptom:** Empty X-Producer-Id header returns 401 (Unauthorized) instead of 400 (Bad Request)
- **Root Cause:** Using falsy check (`if not x_producer_id`) treats None and empty string the same
- **Why It Happens:** Business logic conflates different error types

#### Solution
```python
# ❌ WRONG (conflates None with empty string)
x_producer_id = request.headers.get("X-Producer-Id")
if not x_producer_id:  # True for BOTH None and ""
    raise HTTPException(status_code=401, detail="Missing header")

# ✅ CORRECT (distinguish between missing and invalid)
x_producer_id = request.headers.get("X-Producer-Id")

if x_producer_id is None:  # Header completely missing
    raise HTTPException(status_code=401, detail="X-Producer-Id header missing")

if not x_producer_id.strip():  # Header present but empty
    raise HTTPException(status_code=400, detail="X-Producer-Id cannot be empty")

# 401 = Authentication issue (credential missing)
# 400 = Bad request (credential invalid/malformed)
```

#### Prevention
- Use `is None` to check for presence (missing header)
- Use falsy checks for value validation (empty string, 0, False)
- Document HTTP status meanings in comments
- Test both missing AND empty cases separately

---

### 15. Explicit Exception Conversion to HTTP Status Codes

#### Problem (Discovered PR-3)
- **Symptom:** Pydantic ValidationError converts to 500 (Internal Server Error) instead of 422
- **Root Cause:** FastAPI auto-converts exceptions, but ValidationError without explicit HTTPException handling becomes generic 500
- **Why It Happens:** Framework auto-conversion assumes all exceptions are server errors

#### Solution
```python
# ❌ WRONG (ValidationError not converted to HTTPException)
from pydantic import ValidationError

@router.post("/signals")
async def create_signal(request: Request):
    body_dict = json.loads(await request.body())
    signal = SignalCreate(**body_dict)  # If validation fails, becomes 500

# ✅ CORRECT (explicitly catch and convert to HTTPException)
from pydantic import ValidationError

@router.post("/signals")
async def create_signal(request: Request):
    try:
        body_dict = json.loads(await request.body())
        signal = SignalCreate(**body_dict)
    except ValidationError as e:
        logger.warning(f"Pydantic validation error: {e}")
        # Convert to proper HTTP response
        details = []
        for error in e.errors():
            details.append({
                "loc": error.get("loc", ()),
                "msg": error.get("msg", "Validation error"),
                "type": error.get("type", "unknown"),
            })
        raise HTTPException(status_code=422, detail=details)
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON format")
```

#### Prevention
- Catch third-party exceptions explicitly (ValidationError, JSONDecodeError, etc.)
- Convert to HTTPException with correct status code
- Log the original error for debugging
- Don't rely on framework auto-conversion for library exceptions
- Test each exception type separately

---

### 16. Timezone-Aware DateTime Handling in Comparisons

#### Problem (Discovered PR-3)
- **Symptom:** `TypeError: can't subtract offset-naive and offset-aware datetimes`
- **Root Cause:** Response timestamp parsing creates naive datetime, comparison with UTC-aware datetime fails
- **Why It Happens:** JSON serialization loses timezone info without explicit handling

#### Solution
```python
# ❌ WRONG (mixes naive and aware datetimes)
created_at_str = data["created_at"]  # Example: "2025-10-24T10:30:45.123456"
created_at = datetime.fromisoformat(created_at_str)  # Naive (no timezone)
now = datetime.now(timezone.utc)  # Aware (has timezone)
diff_seconds = (now - created_at).total_seconds()  # TypeError!

# ✅ CORRECT (both datetimes timezone-aware)
from datetime import datetime, timezone

created_at_str = data["created_at"]  # Example: "2025-10-24T10:30:45.123456Z"

# Ensure timezone info present
if created_at_str.endswith("Z"):
    # ISO 8601 format with "Z" suffix
    created_at_str = created_at_str.replace("Z", "+00:00")
elif not ("+" in created_at_str or "-" in created_at_str[10:]):
    # No timezone info, assume UTC
    created_at_str = created_at_str + "+00:00"

# Both now have timezone info
created_at = datetime.fromisoformat(created_at_str)  # Aware
now = datetime.now(timezone.utc)  # Aware
diff_seconds = abs((now - created_at).total_seconds())  # Works!
```

#### Prevention
- Always use `datetime.now(timezone.utc)` for current time (not `datetime.utcnow()`)
- Always parse ISO strings ensuring timezone info is present
- Compare aware with aware, naive with naive
- Add comment documenting timezone assumptions
- Test with both "Z" suffix and "+00:00" format

---

### 17. JSON Serialization Order Variance in Test HMAC Validation

#### Problem (Discovered PR-3)
- **Symptom:** Manual HMAC calculation in test doesn't match request HMAC from httpx
- **Root Cause:** httpx and json.dumps() serialize dictionary keys in different orders
- **Why It Happens:** Dictionary ordering varies across JSON libraries and Python versions

#### Solution
```python
# ❌ WRONG (assumes predictable JSON serialization)
import json
import hmac

body_dict = {"instrument": "GOLD", "side": "buy", "price": 1950.50}
body_str = json.dumps(body_dict)  # May serialize as {"instrument": ..., "side": ..., "price": ...}
signature = hmac.new(secret.encode(), body_str.encode(), hashlib.sha256).hexdigest()

# But httpx might serialize as {"price": ..., "instrument": ..., "side": ...}
# Signatures won't match!

# ✅ CORRECT (separate concerns: HMAC test vs timing test)
# Lesson: Don't mix two types of validation in one test!

# Test 1: HMAC validation (dedicated test)
@pytest.mark.asyncio
async def test_create_signal_valid_hmac_signature(client, valid_signal_data, hmac_secret):
    """Test HMAC signature validation works"""
    # This test validates HMAC logic comprehensively
    # Include all edge cases here

# Test 2: Timing/clock-skew validation (separate test)
@pytest.mark.asyncio
async def test_create_signal_clock_skew_boundary(client, valid_signal_data):
    """Test clock skew validation at 5-minute boundary"""
    # This test validates ONLY timing logic
    # Don't include HMAC complications here
    # Skip HMAC header or use pre-calculated valid signature
```

#### Prevention
- Separate unit concerns: one test per validation type
- Don't test HMAC + timing in same test
- Use pytest fixtures for pre-calculated valid signatures
- Document why certain validations are skipped in specific tests
- All validations are tested elsewhere in dedicated tests

---

## ✅ Comprehensive Checklist for New Projects

Apply these lessons from Day 1:

- [ ] Set `DATABASE_URL` in conftest.py BEFORE any imports
- [ ] Support both SQLite (testing) and PostgreSQL (production)
- [ ] Only apply pool config to PostgreSQL databases
- [ ] Wrap all startup operations in try/except
- [ ] Run Black formatter before every commit
- [ ] Test both happy path AND error paths (≥90% coverage)
- [ ] Run all tests before committing: `python -m pytest backend/`
- [ ] Document all environment variables in .env.example
- [ ] Use monkeypatch for async mocks (not async mock functions)
- [ ] Run tests from project root (not subdirectories)
- [ ] Add complete type hints to all async functions
- [ ] Test backward compatibility with existing code
- [ ] **NEW (PR-3):** Validate request body size BEFORE library parsing (return 413, not 422)
- [ ] **NEW (PR-3):** Use `is None` for presence checks, falsy for value validation
- [ ] **NEW (PR-3):** Explicitly catch third-party exceptions (ValidationError, etc.) and convert to HTTPException
- [ ] **NEW (PR-3):** Always use `datetime.now(timezone.utc)` for timezone-aware comparisons
- [ ] **NEW (PR-3):** Separate test concerns (HMAC + timing = 2 tests, not 1)

---

## �📞 Support

### Resources

- **GitHub Actions Docs:** https://docs.github.com/en/actions
- **FastAPI Docs:** https://fastapi.tiangolo.com/
- **pytest Docs:** https://docs.pytest.org/
- **Black Docs:** https://black.readthedocs.io/
- **Ruff Docs:** https://docs.astral.sh/ruff/

### Getting Help

1. Check this template documentation
2. Review CI/CD implementation guide
3. Search GitHub Issues
4. Ask in project chat
5. Create GitHub Discussion

---

## 🚀 You're Ready!

This template gives you everything needed to build a production-ready project from day 1:

- ✅ CI/CD pipeline that prevents bugs
- ✅ Testing framework that ensures quality
- ✅ Security scanning that protects users
- ✅ Documentation system that scales
- ✅ Deployment pipeline that's stress-free

**Copy these templates, follow the workflow, and build with confidence!**

---

**Last Updated:** October 23, 2025  
**Version:** 1.0.0  
**Maintained By:** Your Team
