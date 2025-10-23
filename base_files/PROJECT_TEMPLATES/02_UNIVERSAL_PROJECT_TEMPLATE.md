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

## 📞 Support

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
