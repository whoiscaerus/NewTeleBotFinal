"""
Reports API routes (PR-101).

Endpoints for on-demand report generation and history viewing.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.models import User
from backend.app.core.db import get_db
from backend.app.reports.generator import ReportGenerator
from backend.app.reports.models import Report, ReportPeriod, ReportStatus, ReportType

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


# Pydantic schemas
class ReportGenerateRequest(BaseModel):
    """Request to generate a report on demand."""

    period: ReportPeriod
    type: ReportType


class ReportOut(BaseModel):
    """Report response schema."""

    id: str
    type: ReportType
    period: ReportPeriod
    status: ReportStatus
    period_start: datetime
    period_end: datetime
    html_url: Optional[str]
    pdf_url: Optional[str]
    summary: Optional[str]
    delivered_channels: list[str]
    created_at: datetime
    generated_at: Optional[datetime]

    class Config:
        from_attributes = True


class ReportsListResponse(BaseModel):
    """List of reports with pagination."""

    reports: list[ReportOut]
    total: int
    page: int
    per_page: int


# Routes
@router.post("/generate", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
async def generate_report(
    request: ReportGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a report on demand.

    - **CLIENT reports**: Available to all paid users for their own data
    - **OWNER reports**: Restricted to owner/admin role

    Returns immediately with GENERATING status. Check status with GET /reports/{id}.
    """
    # Authorization
    if request.type == ReportType.OWNER:
        if not current_user.is_owner:  # TODO: Add owner check
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Owner reports restricted to admin users",
            )
        user_id = None
    else:
        if current_user.tier == "free":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Reports require paid subscription",
            )
        user_id = current_user.id

    # Generate report
    generator = ReportGenerator(db)
    report = await generator.build_report(request.period, request.type, user_id)

    return ReportOut.from_orm(report)


@router.get("/", response_model=ReportsListResponse)
async def list_reports(
    type: Optional[ReportType] = Query(None, description="Filter by report type"),
    period: Optional[ReportPeriod] = Query(None, description="Filter by period"),
    status: Optional[ReportStatus] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List reports for current user.

    - **Clients** see only their own reports
    - **Owners** can see all reports including business summaries
    """
    # Build query
    query = select(Report)

    # Scope to user (unless owner viewing all)
    if not current_user.is_owner:  # TODO: Add owner check
        query = query.where(Report.user_id == current_user.id)

    # Filters
    if type:
        query = query.where(Report.type == type)
    if period:
        query = query.where(Report.period == period)
    if status:
        query = query.where(Report.status == status)

    # Count total
    count_result = await db.execute(query)
    total = len(count_result.scalars().all())

    # Pagination
    query = query.order_by(desc(Report.created_at))
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    reports = result.scalars().all()

    return ReportsListResponse(
        reports=[ReportOut.from_orm(r) for r in reports],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get specific report by ID.

    Returns report details including URLs for HTML/PDF viewing.
    """
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Report not found"
        )

    # Authorization: users can only view their own reports
    if report.user_id and report.user_id != current_user.id:
        if not current_user.is_owner:  # TODO: Add owner check
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot access other users' reports",
            )

    return ReportOut.from_orm(report)
