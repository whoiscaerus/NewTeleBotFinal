# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy application code and requirements
COPY pyproject.toml .
COPY backend/ /build/backend/
RUN python -m pip install --user --no-cache-dir .

# Stage 2: Runtime (production)
FROM python:3.11-slim as production

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 appuser

# Copy Python packages from builder
COPY --from=builder /root/.local /home/appuser/.local

# Set environment
ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy application code (backend contains app/, alembic/, alembic.ini)
COPY --chown=appuser:appuser backend/ /app/

USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "backend.app.orchestrator.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Stage 3: Development
FROM production as development

USER root

# Install dev tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    vim \
    && rm -rf /var/lib/apt/lists/*

# Install dev dependencies
COPY pyproject.toml .
RUN pip install -e ".[dev]" --no-cache-dir

USER appuser

CMD ["uvicorn", "backend.app.orchestrator.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
