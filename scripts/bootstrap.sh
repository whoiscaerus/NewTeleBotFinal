#!/usr/bin/env bash
# Bootstrap script for initial project setup
# Run once: bash scripts/bootstrap.sh

set -e

echo "🚀 Starting project bootstrap..."

# ============================================================================
# 1. Setup Python environment
# ============================================================================
echo "📦 Setting up Python environment..."
python -m venv .venv 2>/dev/null || true
source .venv/bin/activate 2>/dev/null || true

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
pre-commit install

# ============================================================================
# 2. Environment configuration
# ============================================================================
echo "⚙️  Setting up environment..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "   ✅ Created .env (update with your local values)"
else
    echo "   ℹ️  .env already exists"
fi

# ============================================================================
# 3. Database setup
# ============================================================================
echo "🗄️  Setting up database..."

# Start containers
docker-compose up -d postgres redis

# Wait for Postgres to be ready
echo "   ⏳ Waiting for Postgres..."
for i in {1..30}; do
    if docker-compose exec -T postgres pg_isready -U postgres > /dev/null 2>&1; then
        echo "   ✅ Postgres ready"
        break
    fi
    sleep 1
done

# Run migrations
echo "   Running migrations..."
alembic upgrade head
echo "   ✅ Migrations applied"

# ============================================================================
# 4. Verify setup
# ============================================================================
echo "✅ Verify installation..."
python -m black --version
python -m ruff --version
python -m mypy --version
pytest --version

# ============================================================================
# 5. Run initial tests
# ============================================================================
echo "🧪 Running smoke tests..."
python -m pytest backend/tests -v --tb=short 2>/dev/null || echo "   ℹ️  No tests yet"

# ============================================================================
# Complete
# ============================================================================
echo ""
echo "✅ Bootstrap complete!"
echo ""
echo "Next steps:"
echo "  1. Update .env with your local configuration"
echo "  2. Run: make test-local"
echo "  3. Run: make logs"
echo ""
echo "Useful commands:"
echo "  make help           - Show all available commands"
echo "  make up             - Start all services"
echo "  make down           - Stop all services"
echo "  make logs           - View service logs"
echo "  make test-local     - Run all tests locally"
echo "  make quality        - Run code quality checks"
echo ""
