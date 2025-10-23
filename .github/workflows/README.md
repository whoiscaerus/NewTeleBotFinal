# GitHub Actions CI/CD Pipeline Documentation

## Overview

This project uses GitHub Actions for continuous integration and deployment. All workflows are located in `.github/workflows/`.

## Workflows

### 1. Backend Tests & Code Quality (`tests.yml`)

**Trigger:** Push to main/develop, Pull requests  
**Purpose:** Run all tests and code quality checks

**Jobs:**
- `code-quality`: Black formatting + Ruff linting
- `backend-tests`: pytest with PostgreSQL 16 + Redis 7

**Services:**
- PostgreSQL 16 (port 5432)
- Redis 7 (port 6379)

**Requirements:**
- ✅ Black formatting (88 char line length)
- ✅ Ruff linting (no errors)
- ✅ ≥90% backend test coverage
- ✅ All tests passing

**Status:** ✅ ACTIVE

---

### 2. Pull Request Checks (`pr-checks.yml`)

**Trigger:** Pull request opened/updated  
**Purpose:** Validate PR metadata and format

**Checks:**
- PR title format (must start with `PR-XXX:` or conventional commit type)
- PR size warning (>50 files)
- Changed files count

**Status:** ✅ ACTIVE

---

### 3. Security Scanning (`security.yml`)

**Trigger:** Push to main/develop, Pull requests, Daily at 2 AM UTC  
**Purpose:** Security vulnerability scanning

**Scans:**
- `dependency-scan`: Python package vulnerabilities (safety, pip-audit)
- `secrets-scan`: Git history secrets detection (gitleaks)
- `code-security`: Code security issues (bandit)

**Artifacts:**
- Bandit security report (JSON)

**Status:** ✅ ACTIVE (non-blocking warnings)

---

### 4. Database Migrations (`migrations.yml`)

**Trigger:** Push/PR with migration file changes  
**Purpose:** Validate Alembic migrations

**Tests:**
- Migration syntax validation
- Upgrade test (alembic upgrade head)
- Downgrade test (alembic downgrade -1)
- Database state verification

**Services:**
- PostgreSQL 16

**Status:** ✅ ACTIVE

---

### 5. Docker Build (`docker.yml`)

**Trigger:** Push to main, Tags (v*), Pull requests  
**Purpose:** Build and test Docker images

**Features:**
- Multi-platform build (linux/amd64, linux/arm64)
- GitHub Container Registry integration
- Layer caching for faster builds
- Automatic tagging (branch, PR, semver, SHA)

**Images:**
- `ghcr.io/who-is-caerus/newteleBotfinal/backend:latest`

**Status:** ✅ ACTIVE (build only, not pushing yet)

---

### 6. Deploy to Staging (`deploy-staging.yml`)

**Trigger:** Push to develop, Manual workflow dispatch  
**Purpose:** Deploy to staging environment

**Environment:** `staging`  
**URL:** https://staging.yourdomain.com

**Steps:**
1. Checkout code
2. Deploy backend (placeholder)
3. Run smoke tests (placeholder)
4. Send success notification

**Status:** 🟡 PLACEHOLDER (ready for actual deployment configuration)

---

### 7. Deploy to Production (`deploy-production.yml`)

**Trigger:** Push tags (v*.*.*), Manual workflow dispatch  
**Purpose:** Deploy to production environment

**Environment:** `production`  
**URL:** https://yourdomain.com

**Steps:**
1. Extract version from tag
2. Pre-deployment validation
3. Deploy backend (placeholder)
4. Health check (placeholder)
5. Create GitHub Release

**Status:** 🟡 PLACEHOLDER (ready for actual deployment configuration)

---

## Workflow Dependencies

```
PR Created
  ↓
pr-checks.yml (metadata validation)
  ↓
tests.yml (code quality → backend tests)
  ↓
security.yml (dependency scan, secrets scan, code security)
  ↓
migrations.yml (if migrations changed)
  ↓
docker.yml (build Docker image)
  ↓
[Merge to develop]
  ↓
deploy-staging.yml (staging deployment)
  ↓
[Create tag v*.*.*]
  ↓
deploy-production.yml (production deployment)
```

---

## Environment Variables

### All Workflows
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `ENVIRONMENT`: test/staging/production

### Deployment Workflows
- `REGISTRY`: ghcr.io (GitHub Container Registry)
- `IMAGE_NAME`: Repository name

---

## Secrets Required

### Current (Minimal)
- `GITHUB_TOKEN`: Auto-provided by GitHub Actions

### Future (Production Deployment)
- `DEPLOY_SSH_KEY`: SSH key for deployment server
- `STAGING_HOST`: Staging server hostname
- `PRODUCTION_HOST`: Production server hostname
- `SENTRY_DSN`: Error tracking
- `SLACK_WEBHOOK`: Deployment notifications

---

## Badge Status

Add these to `README.md`:

```markdown
![Tests](https://github.com/who-is-caerus/NewTeleBotFinal/actions/workflows/tests.yml/badge.svg)
![Security](https://github.com/who-is-caerus/NewTeleBotFinal/actions/workflows/security.yml/badge.svg)
![Docker](https://github.com/who-is-caerus/NewTeleBotFinal/actions/workflows/docker.yml/badge.svg)
```

---

## Local Testing

### Run tests locally (same as CI)
```bash
cd backend
python -m pytest tests/ -v --tb=short --cov=app --cov-report=term-missing
```

### Run Black formatting
```bash
python -m black backend/app/ backend/tests/ --line-length=88
```

### Run Ruff linting
```bash
ruff check backend/app/ backend/tests/ --line-length=88
```

### Run security scans locally
```bash
pip install safety bandit
safety check -r backend/requirements.txt
bandit -r backend/app/
```

---

## Troubleshooting

### Tests failing in CI but passing locally
- Ensure PostgreSQL and Redis are running
- Check Python version (must be 3.11)
- Verify environment variables match

### Docker build failing
- Check Dockerfile syntax
- Ensure all dependencies in requirements.txt
- Verify base image is available

### Deployment failing
- Check secrets are configured
- Verify deployment target is reachable
- Review deployment logs in GitHub Actions

---

## Maintenance

### Adding New Workflow
1. Create `.github/workflows/new-workflow.yml`
2. Define trigger, jobs, steps
3. Test in feature branch
4. Update this documentation

### Modifying Existing Workflow
1. Create feature branch
2. Edit workflow file
3. Test via pull request
4. Merge after verification

---

## Support

For workflow issues:
1. Check GitHub Actions logs
2. Review this documentation
3. Check copilot-instructions.md
4. Ask in project chat
