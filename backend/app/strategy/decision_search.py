"""Decision search API endpoints (PR-080).

Provides searchable interface for historical trading decisions with filtering,
pagination, and individual decision retrieval.

Endpoints:
    GET /api/v1/decisions/search - Search decisions with filters
    GET /api/v1/decisions/{decision_id} - Get single decision by ID
"""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import get_db
from backend.app.observability.metrics import metrics
from backend.app.strategy.logs.models import DecisionLog, DecisionOutcome

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/decisions", tags=["decisions"])


class DecisionSearchResult(BaseModel):
    """Single decision search result."""

    id: str
    timestamp: datetime
    strategy: str
    symbol: str
    outcome: str
    features: dict[str, Any] | None = None
    note: str | None = None

    class Config:
        from_attributes = True


class DecisionSearchResponse(BaseModel):
    """Paginated decision search response."""

    results: list[DecisionSearchResult]
    total: int
    page: int
    page_size: int
    total_pages: int


@router.get("/search", response_model=DecisionSearchResponse)
async def search_decisions(
    strategy: str | None = Query(
        None, description="Filter by strategy name"
    ),  # noqa: B008
    symbol: str | None = Query(
        None, description="Filter by trading symbol"
    ),  # noqa: B008
    outcome: str | None = Query(None, description="Filter by outcome"),  # noqa: B008
    start_date: datetime | None = Query(  # noqa: B008
        None, description="Filter by start date"
    ),
    end_date: datetime | None = Query(  # noqa: B008
        None, description="Filter by end date"
    ),
    page: int = Query(1, ge=1, description="Page number"),  # noqa: B008
    page_size: int = Query(
        20, ge=1, le=100, description="Items per page"
    ),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> DecisionSearchResponse:
    """Search decisions with filters and pagination.

    Returns decisions ordered by timestamp (most recent first).
    Supports filtering by strategy, symbol, outcome, and date range.

    Args:
        strategy: Filter by strategy name (e.g., "fib_rsi", "ppo_gold")
        symbol: Filter by trading symbol (e.g., "GOLD", "EURUSD")
        outcome: Filter by outcome (e.g., "entered", "rejected")
        start_date: Filter decisions after this date (inclusive)
        end_date: Filter decisions before this date (inclusive)
        page: Page number (1-indexed)
        page_size: Number of results per page (max 100)
        db: Database session

    Returns:
        Paginated search results with total count and page info

    Example:
        GET /api/v1/decisions/search?strategy=fib_rsi&symbol=GOLD&page=1
    """
    # Track search telemetry
    metrics.decision_search_total.inc()

    # Build query with filters
    query = select(DecisionLog)

    if strategy:
        query = query.where(DecisionLog.strategy == strategy)

    if symbol:
        query = query.where(DecisionLog.symbol == symbol)

    if outcome:
        try:
            outcome_enum = DecisionOutcome(outcome)
            query = query.where(DecisionLog.outcome == outcome_enum)
        except KeyError:
            raise HTTPException(
                status_code=400, detail=f"Invalid outcome: {outcome}"
            ) from None

    if start_date:
        query = query.where(DecisionLog.timestamp >= start_date)

    if end_date:
        query = query.where(DecisionLog.timestamp <= end_date)

    # Count total results
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Calculate pagination
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    offset = (page - 1) * page_size

    # Fetch paginated results (ordered by timestamp DESC - most recent first)
    query = query.order_by(DecisionLog.timestamp.desc()).limit(page_size).offset(offset)

    result = await db.execute(query)
    decisions = result.scalars().all()

    # Convert to response model
    results = [
        DecisionSearchResult(
            id=d.id,
            timestamp=d.timestamp,
            strategy=d.strategy,
            symbol=d.symbol,
            outcome=d.outcome.name.lower(),
            features=d.features,
            note=d.note,
        )
        for d in decisions
    ]

    logger.info(
        f"Decision search: {total} results, page {page}/{total_pages}",
        extra={
            "total": total,
            "page": page,
            "filters": {
                "strategy": strategy,
                "symbol": symbol,
                "outcome": outcome,
            },
        },
    )

    return DecisionSearchResponse(
        results=results,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{decision_id}", response_model=DecisionSearchResult)
async def get_decision(
    decision_id: str,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> DecisionSearchResult:
    """Get a single decision by ID.

    Args:
        decision_id: Decision UUID
        db: Database session

    Returns:
        Decision details

    Raises:
        HTTPException: 404 if decision not found

    Example:
        GET /api/v1/decisions/abc-123-def-456
    """
    query = select(DecisionLog).where(DecisionLog.id == decision_id)
    result = await db.execute(query)
    decision = result.scalar_one_or_none()

    if not decision:
        raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")

    return DecisionSearchResult(
        id=decision.id,
        timestamp=decision.timestamp,
        strategy=decision.strategy,
        symbol=decision.symbol,
        outcome=decision.outcome.name.lower(),
        features=decision.features,
        note=decision.note,
    )
