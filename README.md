# Trading Signal Platform

> Production-ready trading signal platform with Telegram bot integration, MetaTrader 5 support, and real-time approvals.

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- Git

### Setup (5 minutes)

```bash
# 1. Clone repository
git clone https://github.com/who-is-caerus/NewTeleBotFinal.git
cd NewTeleBotFinal

# 2. Copy environment configuration
cp .env.example .env

# 3. Install dependencies and setup
make bootstrap

# 4. Run tests to verify
make test-local

# 5. Start services
make up

# 6. View logs
make logs
```

**API Available at**: http://localhost:8000  
**Health Check**: http://localhost:8000/health

---

## 📋 Architecture

### Tech Stack
- **Backend**: FastAPI + SQLAlchemy 2.0 + Alembic
- **Database**: PostgreSQL 15 + SQLite (testing)
- **Cache**: Redis 7
- **Message Queue**: Redis (Celery ready)
- **API Format**: RESTful JSON, versioned at `/api/v1/`
- **Testing**: pytest (≥90% coverage required)
- **Deployment**: Docker + GitHub Actions

### File Organization

```
backend/
  app/
    core/                  # Settings, logging, auth, DB
    orchestrator/          # FastAPI app factory
    [domains]/             # Features (signals, approvals, trading, etc.)
  tests/                   # Unit & integration tests
  alembic/                 # Database migrations

scripts/
  bootstrap.sh             # Initial setup
  coverage-check.py        # CI/CD coverage validation

docker/
  backend.Dockerfile       # Multi-stage production image

.github/
  workflows/               # GitHub Actions CI/CD
  copilot-instructions.md  # AI coding guidelines
```

---

## 🛠️ Development Workflow

### Common Commands

```bash
make help              # Show all available commands
make setup             # Install dependencies
make fmt               # Format code (black + isort)
make lint              # Run linting (ruff)
make typecheck         # Run type checking (mypy)
make quality           # Run all code checks
make test              # Run all tests
make test-cov          # Tests with coverage report
make test-local        # Full local validation (tests + lint + types)
make up                # Start all services
make down              # Stop all services
make logs              # View service logs
make migrate-up        # Apply database migrations
make clean             # Remove build artifacts
```

### Before Committing

```bash
# Always run local checks
make test-local

# Fix any issues
make fmt               # Auto-format code
make lint              # Shows ruff issues

# Commit when green
git add .
git commit -m "Implement feature"
git push
```

### Git Workflow

1. Create feature branch: `git checkout -b feature/xxx`
2. Make changes following conventions (see [CONTRIBUTING](docs/CONTRIBUTING.md))
3. Run `make test-local` to verify
4. Push to GitHub: `git push origin feature/xxx`
5. Create Pull Request
6. GitHub Actions runs CI/CD automatically
7. Merge when all checks pass ✅

---

## 🗄️ Database

### Initialize Database

```bash
# Create and apply migrations
make migrate-up

# Check migration status
make migrate-status

# Rollback last migration
make migrate-down

# Create new migration
make migrate-new m="add user table"
```

### Connection

- **Local Development**: `postgresql://postgres:postgres@localhost:5432/trading_db`
- **Testing**: `sqlite+aiosqlite:///:memory:` (auto-reset per test)
- **Docker**: See `docker-compose.yml` for all services

---

## 🧪 Testing

### Run Tests

```bash
make test              # All tests
make test-cov          # With coverage report (generates htmlcov/)
make test-fast         # Quick run (no coverage)
make test-unit         # Unit tests only
make test-integration  # Integration tests only
```

### Coverage Requirements

- **Minimum**: 90% for backend code
- **Target**: 95% for critical paths

```bash
# Check coverage
make test-cov
open htmlcov/index.html
```

### Writing Tests

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.mark.asyncio
async def test_create_signal(db: AsyncSession):
    """Test signal creation."""
    signal = await create_signal(db, instrument="GOLD", side="buy")
    assert signal.id is not None
    assert signal.status == "new"

@pytest.mark.asyncio
async def test_create_signal_invalid_instrument(db: AsyncSession):
    """Test signal creation rejects invalid instrument."""
    with pytest.raises(ValueError, match="invalid instrument"):
        await create_signal(db, instrument="INVALID", side="buy")
```

---

## 🔐 Security

### Environment Variables

Never commit `.env` file! Copy `.env.example` instead:

```bash
cp .env.example .env
# Edit .env with your local values
```

### Secrets in Production

Production uses Vault or KMS (not `.env`). See [PR-007](base_files/Final_Master_Prs.md) for details.

### Pre-commit Hooks

Automatically run on every commit:
- Format code (black)
- Sort imports (isort)
- Lint (ruff)
- Type check (mypy)

Install: `pre-commit install` (automatic during `make setup`)

---

## 📦 Docker

### Build Images

```bash
# Development image (with hot reload)
docker-compose build backend

# Production image
docker build -f docker/backend.Dockerfile --target production -t trading-platform:latest .
```

### Services

```yaml
postgres:    localhost:5432
redis:       localhost:6379
backend:     localhost:8000
```

### Logs

```bash
make logs              # All services
make logs-backend      # Backend only
docker-compose logs -f backend --tail=100
```

---

## 📚 Documentation

- **[CONTRIBUTING.md](docs/CONTRIBUTING.md)** — Code style, PR guidelines, commit conventions
- **[Final_Master_Prs.md](base_files/Final_Master_Prs.md)** — Complete PR specification (102+ features)
- **[COMPLETE_BUILD_PLAN_ORDERED.md](base_files/COMPLETE_BUILD_PLAN_ORDERED.md)** — Logical build sequencing
- **[Enterprise_System_Build_Plan.md](base_files/Enterprise_System_Build_Plan.md)** — Architecture & phases
- **[02_UNIVERSAL_PROJECT_TEMPLATE.md](base_files/PROJECT_TEMPLATES/02_UNIVERSAL_PROJECT_TEMPLATE.md)** — Lessons learned & patterns

---

## 🚦 CI/CD Pipeline

GitHub Actions automatically runs on every push:

1. **Lint** — Black formatting, ruff checks, isort imports
2. **Type Check** — mypy strict mode
3. **Tests** — pytest with ≥90% coverage
4. **Security** — Bandit (SAST), Safety (dependencies)
5. **Build** — Docker image build
6. **Summary** — Reports all results

View results: **GitHub Actions** tab in repository

---

## 🎯 Key Principles

1. **Type Safety**: All code has type hints (Python 3.11+)
2. **Test Coverage**: ≥90% for backend, ≥70% for frontend
3. **Code Quality**: Black + ruff + mypy enforced by CI/CD
4. **Security**: No secrets in code, use env vars only
5. **Documentation**: Every module has docstrings + examples
6. **Structured Logging**: JSON logs with request correlation
7. **Error Handling**: RFC7807 problem+json responses

---

## 🤝 Contributing

See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for:
- Code style guidelines
- Pull request process
- Commit message conventions
- Testing requirements
- Documentation standards

---

## 📞 Support

- **Issues**: Create GitHub Issue for bugs/features
- **Discussions**: Use GitHub Discussions for questions
- **Documentation**: Check docs/ for runbooks & guides

---

## 📄 License

MIT License © 2025 Trading Signals Team

---

## 🚀 Next Steps

1. ✅ Setup development environment: `make bootstrap`
2. ✅ Run tests locally: `make test-local`
3. ✅ Read [CONTRIBUTING.md](docs/CONTRIBUTING.md)
4. ✅ Start with PR-001 issues in GitHub
5. ✅ Check [COMPLETE_BUILD_PLAN_ORDERED.md](base_files/COMPLETE_BUILD_PLAN_ORDERED.md) for sequencing

---

**Status**: Production Ready  
**Version**: 0.1.0 (Phase 0 - Foundations)  
**Last Updated**: October 24, 2025
