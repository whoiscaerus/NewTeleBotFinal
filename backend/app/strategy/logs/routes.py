"""Decision logs API routes for search and retrieval.

Provides endpoints for:
- Searching decisions by filters (date, strategy, outcome, symbol)
- Retrieving individual decisions with full context
- Paginated results for large datasets

Supports:
- Complex filtering
- Efficient pagination
- Sorting by timestamp
- Integration with explainability (PR-080)
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import get_db
from backend.app.strategy.logs.models import DecisionLog, DecisionOutcome

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/decisions", tags=["decisions"])


class DecisionSearchParams(BaseModel):
    """Search parameters for decision logs."""

    strategy: str | None = Field(None, description="Filter by strategy name")
    symbol: str | None = Field(None, description="Filter by symbol")
    outcome: DecisionOutcome | None = Field(None, description="Filter by outcome")
    start_date: datetime | None = Field(
        None, description="Filter by start date (inclusive)"
    )
    end_date: datetime | None = Field(
        None, description="Filter by end date (inclusive)"
    )
    page: int = Field(1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(50, ge=1, le=500, description="Results per page")


class DecisionResponse(BaseModel):
    """Single decision log response."""

    id: str
    timestamp: datetime
    strategy: str
    symbol: str
    outcome: str
    features: dict
    note: str | None = None

    class Config:
        from_attributes = True


class DecisionSearchResponse(BaseModel):
    """Paginated decision search results."""

    total: int = Field(description="Total number of results")
    page: int = Field(description="Current page number")
    page_size: int = Field(description="Results per page")
    total_pages: int = Field(description="Total number of pages")
    results: list[DecisionResponse] = Field(description="Decision logs for this page")


@router.get("/search", response_model=DecisionSearchResponse)
async def search_decisions(
    strategy: str | None = Query(None, description="Filter by strategy name"),
    symbol: str | None = Query(None, description="Filter by symbol"),
    outcome: DecisionOutcome | None = Query(None, description="Filter by outcome"),
    start_date: datetime | None = Query(None, description="Start date (inclusive)"),
    end_date: datetime | None = Query(None, description="End date (inclusive)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=500, description="Results per page"),
    session: AsyncSession = Depends(get_db),
) -> DecisionSearchResponse:
    """Search decision logs with filters and pagination.

    Returns paginated results matching the specified criteria.
    Results are ordered by timestamp descending (most recent first).

    Args:
        strategy: Filter by strategy name (exact match)
        symbol: Filter by trading symbol (exact match)
        outcome: Filter by decision outcome enum
        start_date: Filter by timestamp >= start_date
        end_date: Filter by timestamp <= end_date
        page: Page number (1-indexed)
        page_size: Results per page (1-500)
        session: Database session

    Returns:
        DecisionSearchResponse with paginated results

    Example:
        GET /api/v1/decisions/search?strategy=fib_rsi&outcome=entered&page=1&page_size=20
    """
    # Build filter conditions
    filters = []

    if strategy:
        filters.append(DecisionLog.strategy == strategy)
    if symbol:
        filters.append(DecisionLog.symbol == symbol)
    if outcome:
        filters.append(DecisionLog.outcome == outcome)
    if start_date:
        filters.append(DecisionLog.timestamp >= start_date)
    if end_date:
        filters.append(DecisionLog.timestamp <= end_date)

    # Count total results
    count_query = select(func.count(DecisionLog.id))
    if filters:
        count_query = count_query.where(and_(*filters))

    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0

    # Fetch paginated results
    offset = (page - 1) * page_size
    query = (
        select(DecisionLog)
        .order_by(DecisionLog.timestamp.desc())
        .limit(page_size)
        .offset(offset)
    )

    if filters:
        query = query.where(and_(*filters))

    result = await session.execute(query)
    decisions = result.scalars().all()

    # Convert to response models
    decision_responses = [
        DecisionResponse(
            id=d.id,
            timestamp=d.timestamp,
            strategy=d.strategy,
            symbol=d.symbol,
            outcome=d.outcome.value,
            features=d.features or {},
            note=d.note,
        )
        for d in decisions
    ]

    total_pages = (total + page_size - 1) // page_size  # Ceiling division

    logger.info(
        f"Decision search: {len(decisions)} results (page {page}/{total_pages}, total {total})"
    )

    # Increment telemetry
    from backend.app.observability.metrics import metrics_collector

    metrics_collector.decision_search_total.inc()

    return DecisionSearchResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        results=decision_responses,
    )


@router.get("/{decision_id}", response_model=DecisionResponse)
async def get_decision(
    decision_id: str,
    session: AsyncSession = Depends(get_db),
) -> DecisionResponse:
    """Get a single decision log by ID.

    Args:
        decision_id: Decision UUID
        session: Database session

    Returns:
        DecisionResponse with full decision context

    Raises:
        HTTPException: 404 if decision not found

    Example:
        GET /api/v1/decisions/abc-123-def-456
    """
    query = select(DecisionLog).where(DecisionLog.id == decision_id)
    result = await session.execute(query)
    decision = result.scalar_one_or_none()

    if not decision:
        logger.warning(f"Decision not found: {decision_id}")
        raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")

    logger.info(f"Retrieved decision: {decision_id}")

    return DecisionResponse(
        id=decision.id,
        timestamp=decision.timestamp,
        strategy=decision.strategy,
        symbol=decision.symbol,
        outcome=decision.outcome.value,
        features=decision.features or {},
        note=decision.note,
    )
