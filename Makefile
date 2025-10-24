.PHONY: help setup fmt lint typecheck test test-cov test-local up down logs clean bootstrap migrate-up migrate-down migrate-status

.DEFAULT_GOAL := help

help: ## Display this help screen
	@grep -h -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

# ============================================================================
# DEVELOPMENT SETUP
# ============================================================================

setup: ## Initial project setup (run once)
	python -m pip install --upgrade pip setuptools wheel
	python -m pip install -e ".[dev]"
	pre-commit install
	@echo "✅ Project setup complete!"

bootstrap: setup ## Full bootstrap (setup + db init)
	@echo "🚀 Running bootstrap script..."
	bash scripts/bootstrap.sh

# ============================================================================
# CODE QUALITY
# ============================================================================

fmt: ## Format code with black and isort
	python -m black backend/
	python -m isort backend/
	@echo "✅ Code formatted!"

lint: ## Run linting checks (ruff)
	python -m ruff check backend/
	@echo "✅ Linting passed!"

typecheck: ## Run type checks (mypy)
	python -m mypy backend/app --ignore-missing-imports
	@echo "✅ Type checks passed!"

quality: fmt lint typecheck ## Run all code quality checks

# ============================================================================
# TESTING
# ============================================================================

test: ## Run all tests
	python -m pytest backend/tests -v

test-cov: ## Run tests with coverage report
	python -m pytest backend/tests --cov=backend/app --cov-report=html --cov-report=term-missing
	@echo "✅ Coverage report generated (open htmlcov/index.html)"

test-local: test-cov lint typecheck ## Run all local checks (tests + lint + typecheck)
	@echo "✅ All local checks passed!"

test-fast: ## Run tests without coverage (faster)
	python -m pytest backend/tests -v --tb=short

test-unit: ## Run only unit tests
	python -m pytest backend/tests -v -m unit

test-integration: ## Run only integration tests
	python -m pytest backend/tests -v -m integration

# ============================================================================
# DOCKER & SERVICES
# ============================================================================

up: ## Start all services (Docker Compose)
	docker-compose up -d
	@echo "✅ Services started!"
	@echo "   - Backend: http://localhost:8000"
	@echo "   - Postgres: localhost:5432"
	@echo "   - Redis: localhost:6379"

down: ## Stop all services
	docker-compose down
	@echo "✅ Services stopped!"

logs: ## Show logs from all services
	docker-compose logs -f

logs-backend: ## Show only backend logs
	docker-compose logs -f backend

# ============================================================================
# DATABASE MIGRATIONS
# ============================================================================

migrate-up: ## Run pending migrations
	alembic upgrade head
	@echo "✅ Migrations applied!"

migrate-down: ## Rollback last migration
	alembic downgrade -1
	@echo "✅ Migration rolled back!"

migrate-status: ## Show migration status
	alembic current
	alembic history

migrate-new: ## Create new migration (use: make migrate-new m="description")
	alembic revision --autogenerate -m "$(m)"

# ============================================================================
# CLEANUP
# ============================================================================

clean: ## Remove build artifacts and cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .mypy_cache -exec rm -rf {} +
	find . -type d -name *.egg-info -exec rm -rf {} +
	find . -type f -name .coverage -delete
	rm -rf htmlcov/
	@echo "✅ Cleanup complete!"

clean-containers: ## Remove all Docker containers and volumes (⚠️ DESTRUCTIVE)
	docker-compose down -v
	@echo "✅ Containers and volumes removed!"

# ============================================================================
# COMMON WORKFLOWS
# ============================================================================

dev: setup up migrate-up ## Complete dev environment setup
	@echo "✅ Development environment ready!"
	@echo "   Next: make test-local to verify everything works"

rebuild: ## Rebuild all Docker images
	docker-compose build --no-cache
	@echo "✅ Images rebuilt!"

reset: clean clean-containers setup up migrate-up ## Full reset (clean install)
	@echo "✅ Full reset complete!"
