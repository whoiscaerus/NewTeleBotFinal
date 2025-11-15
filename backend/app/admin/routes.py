"""
PR-099: Unified Admin Portal Routes

Owner/admin-only endpoints for managing platform operations.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from prometheus_client import Counter
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.admin.middleware import require_admin, require_owner
from backend.app.admin.schemas import (
    AnalyticsDashboardOut,
    ArticleOut,
    DeviceOut,
    DeviceSearchRequest,
    FraudEventOut,
    FraudResolutionRequest,
    RefundOut,
    RefundRequest,
    TicketOut,
    TicketUpdateRequest,
    UserOut,
    UserSearchRequest,
    UserUpdateRequest,
)
from backend.app.admin.service import approve_kyc, process_refund, resolve_fraud_event
from backend.app.audit.service import AuditService
from backend.app.auth.models import User
from backend.app.clients.devices.models import Device
from backend.app.core.db import get_db
from backend.app.fraud.models import AnomalyEvent
from backend.app.kb.models import Article
from backend.app.support.models import Ticket

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

# Metrics
admin_actions_total = Counter(
    "admin_actions_total",
    "Total admin actions performed",
    ["section", "action"],
)


# ===== User Management =====


@router.post("/users/search", response_model=list[UserOut])
async def search_users(
    request: UserSearchRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Search and filter users with pagination.

    Requires: Admin or Owner role

    Args:
        request: Search filters (query, tier, status, limit, offset)
        db: Database session
        admin: Authenticated admin user

    Returns:
        List[UserOut]: Paginated list of users

    Example:
        >>> POST /api/v1/admin/users/search
        >>> {"query": "john@example.com", "tier": "premium", "limit": 50}
    """
    try:
        query = select(User)

        # Apply filters
        if request.query:
            search_term = f"%{request.query}%"
            query = query.where(
                or_(
                    User.email.ilike(search_term),
                    User.telegram_id.ilike(search_term),
                    User.name.ilike(search_term),
                )
            )

        if request.tier:
            query = query.where(User.tier == request.tier)

        if request.status:
            query = query.where(User.status == request.status)

        # Pagination
        query = query.offset(request.offset).limit(request.limit)

        result = await db.execute(query)
        users = result.scalars().all()

        admin_actions_total.labels(section="users", action="search").inc()

        return [
            UserOut(
                id=u.id,
                email=u.email,
                telegram_id=u.telegram_id,
                tier=u.tier,
                status=u.status,
                kyc_status=u.kyc_status or "pending",
                created_at=u.created_at,
                last_active_at=u.last_active_at,
                total_approvals=0,  # TODO: Join with approvals table
                total_devices=0,  # TODO: Join with devices table
            )
            for u in users
        ]

    except Exception as e:
        logger.error(f"User search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User search failed",
        )


@router.get("/users/{user_id}", response_model=UserOut)
async def get_user_details(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Get detailed user information by ID.

    Requires: Admin or Owner role
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    admin_actions_total.labels(section="users", action="get_details").inc()

    return UserOut(
        id=user.id,
        email=user.email,
        telegram_id=user.telegram_id,
        tier=user.tier,
        status=user.status,
        kyc_status=user.kyc_status or "pending",
        created_at=user.created_at,
        last_active_at=user.last_active_at,
        total_approvals=0,
        total_devices=0,
    )


@router.put("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str,
    request: UserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Update user tier, status, or KYC status.

    Requires: Admin or Owner role

    Example:
        >>> PUT /api/v1/admin/users/user_123
        >>> {"tier": "premium", "status": "active"}
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    # Apply updates
    if request.tier:
        user.tier = request.tier
    if request.status:
        user.status = request.status
    if request.kyc_status:
        user.kyc_status = request.kyc_status

    # Audit log
    await AuditService.record(
        db=db,
        actor_id=admin.id,
        action="user_updated",
        target="user",
        target_id=user_id,
        meta={
            "tier": request.tier,
            "status": request.status,
            "kyc_status": request.kyc_status,
            "notes": request.notes,
        },
    )

    await db.commit()
    await db.refresh(user)

    admin_actions_total.labels(section="users", action="update").inc()

    return UserOut(
        id=user.id,
        email=user.email,
        telegram_id=user.telegram_id,
        tier=user.tier,
        status=user.status,
        kyc_status=user.kyc_status or "pending",
        created_at=user.created_at,
        last_active_at=user.last_active_at,
        total_approvals=0,
        total_devices=0,
    )


@router.post("/users/{user_id}/kyc/approve")
async def approve_user_kyc(
    user_id: str,
    notes: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_owner),  # Owner only
):
    """
    Approve KYC for a user.

    Requires: Owner role (not just admin)

    Example:
        >>> POST /api/v1/admin/users/user_123/kyc/approve
        >>> {"notes": "Verified government ID"}
    """
    try:
        user = await approve_kyc(db, user_id, admin, notes)

        admin_actions_total.labels(section="users", action="kyc_approve").inc()

        return {
            "user_id": user.id,
            "kyc_status": user.kyc_status,
            "approved_at": user.kyc_approved_at.isoformat(),
            "approved_by": user.kyc_approved_by,
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"KYC approval failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="KYC approval failed",
        )


# ===== Device Management =====


@router.post("/devices/search", response_model=list[DeviceOut])
async def search_devices(
    request: DeviceSearchRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Search devices with filters and pagination.

    Requires: Admin or Owner role
    """
    try:
        query = select(Device)

        if request.user_id:
            query = query.where(Device.user_id == request.user_id)

        if request.status:
            query = query.where(Device.status == request.status)

        query = query.offset(request.offset).limit(request.limit)

        result = await db.execute(query)
        devices = result.scalars().all()

        admin_actions_total.labels(section="devices", action="search").inc()

        return [
            DeviceOut(
                id=d.id,
                user_id=d.user_id,
                device_name=d.device_name,
                status=d.status,
                created_at=d.created_at,
                last_poll_at=d.last_poll_at,
                total_positions=0,  # TODO: Count positions
            )
            for d in devices
        ]

    except Exception as e:
        logger.error(f"Device search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Device search failed",
        )


@router.post("/devices/{device_id}/revoke")
async def revoke_device(
    device_id: str,
    reason: str = Query(..., min_length=10),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_owner),  # Owner only
):
    """
    Revoke a device (disable access).

    Requires: Owner role

    Example:
        >>> POST /api/v1/admin/devices/device_123/revoke?reason=Security+breach
    """
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device {device_id} not found",
        )

    device.status = "revoked"
    device.revoked_at = datetime.now(UTC)
    device.revoked_by = admin.id
    device.revoke_reason = reason

    # Audit log
    await AuditService.record(
        db=db,
        actor_id=admin.id,
        action="device_revoked",
        target="device",
        target_id=device_id,
        meta={
            "user_id": device.user_id,
            "reason": reason,
        },
    )

    await db.commit()

    admin_actions_total.labels(section="devices", action="revoke").inc()

    return {
        "device_id": device.id,
        "status": "revoked",
        "revoked_at": device.revoked_at.isoformat(),
    }


# ===== Billing & Refunds =====


@router.post("/billing/refund", response_model=RefundOut)
async def create_refund(
    request: RefundRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_owner),  # Owner only
):
    """
    Process a refund for a user with Stripe integration.

    Requires: Owner role

    Example:
        >>> POST /api/v1/admin/billing/refund
        >>> {
        ...     "user_id": "user_123",
        ...     "amount": 50.00,
        ...     "reason": "Service downtime on 2025-11-10",
        ...     "stripe_payment_intent_id": "pi_abc123"
        ... }
    """
    try:
        result = await process_refund(
            db=db,
            user_id=request.user_id,
            amount=request.amount,
            reason=request.reason,
            admin_user=admin,
            stripe_payment_intent_id=request.stripe_payment_intent_id,
        )

        admin_actions_total.labels(section="billing", action="refund").inc()

        return RefundOut(**result)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Refund failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Refund processing failed",
        )


# ===== Analytics Dashboard =====


@router.get("/analytics/dashboard", response_model=AnalyticsDashboardOut)
async def get_analytics_dashboard(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Get real-time analytics dashboard data.

    Requires: Admin or Owner role

    Returns live tiles data: API health, ingestion rates, payment errors, copy-trading stats.
    """
    try:
        # TODO: Replace with actual queries/metrics
        # This is a stub implementation - integrate with real metrics

        # API Health (from Prometheus or health checks)
        api_health_status = "healthy"
        api_error_rate_percent = 0.5
        api_avg_latency_ms = 125.0

        # Signal Ingestion (from signals table)
        signals_ingested_last_hour = 42
        signals_ingested_last_24h = 987
        ingestion_rate_per_minute = 0.7

        # Payment Errors (from billing/payments)
        payment_errors_last_24h = 3
        failed_payment_amount_gbp = 150.00
        retry_success_rate_percent = 66.7

        # Copy Trading (from positions)
        copy_trading_active_users = 45
        copy_trading_positions_open = 12
        copy_trading_pnl_today_gbp = 523.45

        # User Stats
        total_users_result = await db.execute(select(func.count(User.id)))
        total_users = total_users_result.scalar() or 0

        active_threshold = datetime.now(UTC) - timedelta(days=7)
        active_users_result = await db.execute(
            select(func.count(User.id)).where(User.last_active_at >= active_threshold)
        )
        active_users_last_7d = active_users_result.scalar() or 0

        signup_threshold = datetime.now(UTC) - timedelta(hours=24)
        new_signups_result = await db.execute(
            select(func.count(User.id)).where(User.created_at >= signup_threshold)
        )
        new_signups_last_24h = new_signups_result.scalar() or 0

        # System (mocked - integrate with real monitoring)
        db_connections_active = 15
        redis_cache_hit_rate_percent = 92.5
        celery_queue_depth = 3

        admin_actions_total.labels(section="analytics", action="dashboard").inc()

        return AnalyticsDashboardOut(
            api_health_status=api_health_status,
            api_error_rate_percent=api_error_rate_percent,
            api_avg_latency_ms=api_avg_latency_ms,
            signals_ingested_last_hour=signals_ingested_last_hour,
            signals_ingested_last_24h=signals_ingested_last_24h,
            ingestion_rate_per_minute=ingestion_rate_per_minute,
            payment_errors_last_24h=payment_errors_last_24h,
            failed_payment_amount_gbp=failed_payment_amount_gbp,
            retry_success_rate_percent=retry_success_rate_percent,
            copy_trading_active_users=copy_trading_active_users,
            copy_trading_positions_open=copy_trading_positions_open,
            copy_trading_pnl_today_gbp=copy_trading_pnl_today_gbp,
            total_users=total_users,
            active_users_last_7d=active_users_last_7d,
            new_signups_last_24h=new_signups_last_24h,
            db_connections_active=db_connections_active,
            redis_cache_hit_rate_percent=redis_cache_hit_rate_percent,
            celery_queue_depth=celery_queue_depth,
        )

    except Exception as e:
        logger.error(f"Analytics dashboard failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Analytics dashboard failed",
        )


# ===== Fraud Management =====


@router.get("/fraud/events", response_model=list[FraudEventOut])
async def get_fraud_events(
    status: Optional[str] = Query(None, pattern="^(open|resolved)$"),
    severity: Optional[str] = Query(None, pattern="^(low|medium|high|critical)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    List fraud events with filters.

    Requires: Admin or Owner role
    """
    try:
        query = select(AnomalyEvent)

        if status:
            query = query.where(AnomalyEvent.status == status)

        if severity:
            query = query.where(AnomalyEvent.severity == severity)

        query = query.order_by(AnomalyEvent.created_at.desc())
        query = query.offset(offset).limit(limit)

        result = await db.execute(query)
        events = result.scalars().all()

        admin_actions_total.labels(section="fraud", action="list_events").inc()

        return [FraudEventOut.from_orm(e) for e in events]

    except Exception as e:
        logger.error(f"Fraud events query failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fraud events query failed",
        )


@router.post("/fraud/events/resolve")
async def resolve_fraud(
    request: FraudResolutionRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_owner),  # Owner only
):
    """
    Resolve a fraud event with action taken.

    Requires: Owner role

    Example:
        >>> POST /api/v1/admin/fraud/events/resolve
        >>> {
        ...     "event_id": "event_123",
        ...     "resolution": "false_positive",
        ...     "action_taken": "Reviewed logs - user was traveling",
        ...     "notes": "IP changed due to VPN"
        ... }
    """
    try:
        event = await resolve_fraud_event(
            db=db,
            event_id=request.event_id,
            resolution=request.resolution,
            action_taken=request.action_taken,
            admin_user=admin,
            notes=request.notes,
        )

        admin_actions_total.labels(section="fraud", action="resolve").inc()

        return FraudEventOut.from_orm(event)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Fraud resolution failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fraud resolution failed",
        )


# ===== Support Tickets =====


@router.get("/support/tickets", response_model=list[TicketOut])
async def get_tickets(
    status: Optional[str] = Query(None, pattern="^(open|assigned|resolved|closed)$"),
    severity: Optional[str] = Query(None, pattern="^(low|medium|high|critical)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    List support tickets with filters.

    Requires: Admin or Owner role
    """
    try:
        query = select(Ticket)

        if status:
            query = query.where(Ticket.status == status)

        if severity:
            query = query.where(Ticket.severity == severity)

        query = query.order_by(Ticket.created_at.desc())
        query = query.offset(offset).limit(limit)

        result = await db.execute(query)
        tickets = result.scalars().all()

        admin_actions_total.labels(section="support", action="list_tickets").inc()

        return [TicketOut.from_orm(t) for t in tickets]

    except Exception as e:
        logger.error(f"Tickets query failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Tickets query failed",
        )


@router.put("/support/tickets/{ticket_id}", response_model=TicketOut)
async def update_ticket(
    ticket_id: str,
    request: TicketUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Update ticket status, assignment, or add response.

    Requires: Admin or Owner role
    """
    try:
        result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
        ticket = result.scalar_one_or_none()

        if not ticket:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ticket {ticket_id} not found",
            )

        # Apply updates
        if request.status:
            ticket.status = request.status
            if request.status == "resolved":
                ticket.resolved_at = datetime.now(UTC)

        if request.assigned_to:
            ticket.assigned_to = request.assigned_to
            ticket.assigned_at = datetime.now(UTC)

        # Audit log
        await AuditService.record(
            db=db,
            actor_id=admin.id,
            action="ticket_updated",
            target="support",
            target_id=ticket_id,
            meta={
                "status": request.status,
                "assigned_to": request.assigned_to,
                "response": request.response,
            },
        )

        await db.commit()
        await db.refresh(ticket)

        admin_actions_total.labels(section="support", action="update_ticket").inc()

        return TicketOut.from_orm(ticket)

    except Exception as e:
        logger.error(f"Ticket update failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ticket update failed",
        )


# ===== Knowledge Base CMS =====


@router.get("/kb/articles", response_model=list[ArticleOut])
async def get_articles(
    status: Optional[str] = Query(None, pattern="^(draft|published)$"),
    locale: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    List KB articles with filters.

    Requires: Admin or Owner role
    """
    try:
        query = select(Article)

        if status:
            query = query.where(Article.status == status)

        if locale:
            query = query.where(Article.locale == locale)

        query = query.order_by(Article.updated_at.desc())
        query = query.offset(offset).limit(limit)

        result = await db.execute(query)
        articles = result.scalars().all()

        admin_actions_total.labels(section="kb", action="list_articles").inc()

        return [ArticleOut.from_orm(a) for a in articles]

    except Exception as e:
        logger.error(f"Articles query failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Articles query failed",
        )


@router.post("/kb/articles/{article_id}/publish")
async def publish_article(
    article_id: str,
    publish: bool = Query(..., description="True to publish, False to unpublish"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_owner),  # Owner only
):
    """
    Publish or unpublish a KB article.

    Requires: Owner role
    """
    try:
        result = await db.execute(select(Article).where(Article.id == article_id))
        article = result.scalar_one_or_none()

        if not article:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Article {article_id} not found",
            )

        if publish:
            article.status = "published"
            article.published_at = datetime.now(UTC)
        else:
            article.status = "draft"
            article.published_at = None

        # Audit log
        await AuditService.record(
            db=db,
            actor_id=admin.id,
            action="article_publish" if publish else "article_unpublish",
            target="kb",
            target_id=article_id,
            meta={
                "title": article.title,
                "locale": article.locale,
            },
        )

        await db.commit()
        await db.refresh(article)

        admin_actions_total.labels(section="kb", action="publish").inc()

        return ArticleOut.from_orm(article)

    except Exception as e:
        logger.error(f"Article publish failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Article publish failed",
        )
