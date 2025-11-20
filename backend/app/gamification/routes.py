"""Gamification API routes for PR-088.

Endpoints:
- GET /api/v1/gamification/me/badges - Get user's earned badges and current level
- POST /api/v1/gamification/leaderboard/opt-in - Opt into leaderboard
- POST /api/v1/gamification/leaderboard/opt-out - Opt out of leaderboard
- GET /api/v1/gamification/leaderboard - Get leaderboard rankings (public)
- GET /api/v1/gamification/me/xp - Get user's XP breakdown
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.models import User
from backend.app.core.db import get_db
from backend.app.gamification.service import GamificationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/gamification", tags=["gamification"])


# Pydantic schemas
class BadgeOut(BaseModel):
    """Badge output schema."""

    id: str
    name: str
    description: str
    icon: str
    category: str
    xp_reward: int


class EarnedBadgeOut(BaseModel):
    """Earned badge output schema."""

    id: str
    badge: BadgeOut
    earned_at: str


class LevelOut(BaseModel):
    """Level output schema."""

    id: str
    name: str
    min_xp: int
    max_xp: int | None
    icon: str
    color: str
    perks: str | None


class UserBadgesResponse(BaseModel):
    """Response for user badges endpoint."""

    user_id: str
    total_xp: int
    current_level: LevelOut | None
    next_level: LevelOut | None
    xp_to_next_level: int | None
    earned_badges: list[EarnedBadgeOut]
    badges_available: list[BadgeOut]


class XPBreakdownResponse(BaseModel):
    """Response for XP breakdown endpoint."""

    user_id: str
    total_xp: int
    base_xp: int  # From approved trades
    stability_bonus: int  # From PnL stability
    badge_xp: int  # From earned badges
    approved_trades_count: int


class LeaderboardOptInRequest(BaseModel):
    """Request to opt into leaderboard."""

    display_name: str | None = Field(None, max_length=50)


class LeaderboardOptInResponse(BaseModel):
    """Response for leaderboard opt-in."""

    user_id: str
    opted_in: bool
    display_name: str | None
    opted_in_at: str


class LeaderboardEntry(BaseModel):
    """Leaderboard entry schema."""

    rank: int
    display_name: str
    xp: int
    sharpe: float
    return_pct: float


class LeaderboardResponse(BaseModel):
    """Response for leaderboard endpoint."""

    entries: list[LeaderboardEntry]
    total_count: int
    limit: int
    offset: int


@router.get("/me/badges", response_model=UserBadgesResponse)
async def get_my_badges(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's earned badges and level progression.

    Returns:
        User's total XP, current level, earned badges, and available badges

    Example Response:
        {
            "user_id": "abc123",
            "total_xp": 1250,
            "current_level": {"name": "Silver", "min_xp": 1001, ...},
            "next_level": {"name": "Gold", "min_xp": 5001, ...},
            "xp_to_next_level": 3751,
            "earned_badges": [...],
            "badges_available": [...]
        }
    """
    try:
        service = GamificationService(db)

        # Calculate total XP
        total_xp = await service.calculate_user_xp(current_user.id)

        # Get current level
        current_level = await service.get_user_level(current_user.id)

        # Get next level
        next_level = None
        xp_to_next_level = None
        if current_level and current_level.max_xp is not None:
            # Query for next level
            from sqlalchemy import select

            from backend.app.gamification.models import Level

            stmt = (
                select(Level)
                .where(Level.min_xp > current_level.max_xp)
                .order_by(Level.min_xp)
            )
            result = await db.execute(stmt)
            next_level = result.scalar_one_or_none()

            if next_level:
                xp_to_next_level = next_level.min_xp - total_xp

        # Get earned badges
        from sqlalchemy import select

        from backend.app.gamification.models import Badge, EarnedBadge

        stmt = (
            select(EarnedBadge)
            .join(Badge)
            .where(EarnedBadge.user_id == current_user.id)
            .order_by(EarnedBadge.earned_at.desc())
        )
        result = await db.execute(stmt)
        earned_badges_db = result.scalars().all()

        earned_badges = [
            EarnedBadgeOut(
                id=eb.id,
                badge=BadgeOut(
                    id=eb.badge.id,
                    name=eb.badge.name,
                    description=eb.badge.description,
                    icon=eb.badge.icon,
                    category=eb.badge.category,
                    xp_reward=eb.badge.xp_reward,
                ),
                earned_at=eb.earned_at.isoformat(),
            )
            for eb in earned_badges_db
        ]

        # Get all available badges (not yet earned)
        earned_badge_ids = {eb.badge_id for eb in earned_badges_db}
        stmt = select(Badge)
        result = await db.execute(stmt)
        all_badges = result.scalars().all()

        badges_available = [
            BadgeOut(
                id=badge.id,
                name=badge.name,
                description=badge.description,
                icon=badge.icon,
                category=badge.category,
                xp_reward=badge.xp_reward,
            )
            for badge in all_badges
            if badge.id not in earned_badge_ids
        ]

        return UserBadgesResponse(
            user_id=current_user.id,
            total_xp=total_xp,
            current_level=(
                LevelOut(
                    id=current_level.id,
                    name=current_level.name,
                    min_xp=current_level.min_xp,
                    max_xp=current_level.max_xp,
                    icon=current_level.icon,
                    color=current_level.color,
                    perks=current_level.perks,
                )
                if current_level
                else None
            ),
            next_level=(
                LevelOut(
                    id=next_level.id,
                    name=next_level.name,
                    min_xp=next_level.min_xp,
                    max_xp=next_level.max_xp,
                    icon=next_level.icon,
                    color=next_level.color,
                    perks=next_level.perks,
                )
                if next_level
                else None
            ),
            xp_to_next_level=xp_to_next_level,
            earned_badges=earned_badges,
            badges_available=badges_available,
        )

    except Exception as e:
        logger.error(
            f"Failed to get badges for user {current_user.id}: {e}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/me/xp", response_model=XPBreakdownResponse)
async def get_my_xp_breakdown(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed XP breakdown for current user.

    Shows how XP is calculated: base (trades) + stability bonus + badge rewards.

    Returns:
        XP breakdown by source

    Example Response:
        {
            "user_id": "abc123",
            "total_xp": 1250,
            "base_xp": 1000,
            "stability_bonus": 50,
            "badge_xp": 200,
            "approved_trades_count": 100
        }
    """
    try:
        service = GamificationService(db)

        # Get approved trades count
        from sqlalchemy import and_, func, select

        from backend.app.approvals.models import Approval, ApprovalStatus

        stmt = select(func.count(Approval.id)).where(
            and_(
                Approval.user_id == current_user.id,
                Approval.status == ApprovalStatus.APPROVED,
            )
        )
        result = await db.execute(stmt)
        approved_count = result.scalar() or 0

        # Calculate base XP
        base_xp = approved_count * service.XP_PER_TRADE

        # Calculate stability bonus
        stability_bonus = await service._calculate_stability_bonus(current_user.id)

        # Calculate badge XP
        from backend.app.gamification.models import Badge, EarnedBadge

        stmt = (
            select(func.sum(Badge.xp_reward))
            .join(EarnedBadge, EarnedBadge.badge_id == Badge.id)
            .where(EarnedBadge.user_id == current_user.id)
        )
        result = await db.execute(stmt)
        badge_xp = result.scalar() or 0

        total_xp = base_xp + stability_bonus + badge_xp

        return XPBreakdownResponse(
            user_id=current_user.id,
            total_xp=total_xp,
            base_xp=base_xp,
            stability_bonus=stability_bonus,
            badge_xp=badge_xp,
            approved_trades_count=approved_count,
        )

    except Exception as e:
        logger.error(
            f"Failed to get XP breakdown for user {current_user.id}: {e}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/leaderboard/opt-in", response_model=LeaderboardOptInResponse)
async def opt_in_leaderboard(
    request: LeaderboardOptInRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Opt current user into leaderboard.

    Users must opt-in to appear on leaderboard (privacy-safe).

    Args:
        request: Optional display name

    Returns:
        Opt-in confirmation with display name

    Example:
        POST /api/v1/gamification/leaderboard/opt-in
        {"display_name": "TraderPro"}

        Response:
        {
            "user_id": "abc123",
            "opted_in": true,
            "display_name": "TraderPro",
            "opted_in_at": "2024-11-09T12:00:00Z"
        }
    """
    try:
        service = GamificationService(db)

        optin = await service.opt_in_leaderboard(
            user_id=current_user.id,
            display_name=request.display_name,
        )

        return LeaderboardOptInResponse(
            user_id=optin.user_id,
            opted_in=optin.opted_in,
            display_name=optin.display_name,
            opted_in_at=optin.opted_in_at.isoformat(),
        )

    except Exception as e:
        logger.error(
            f"Failed to opt-in user {current_user.id} to leaderboard: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/leaderboard/opt-out", response_model=LeaderboardOptInResponse)
async def opt_out_leaderboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Opt current user out of leaderboard.

    Removes user from public leaderboard rankings.

    Returns:
        Opt-out confirmation

    Example:
        POST /api/v1/gamification/leaderboard/opt-out

        Response:
        {
            "user_id": "abc123",
            "opted_in": false,
            "display_name": null,
            "opted_in_at": "2024-11-09T12:00:00Z"
        }
    """
    try:
        service = GamificationService(db)

        optin = await service.opt_out_leaderboard(user_id=current_user.id)

        return LeaderboardOptInResponse(
            user_id=optin.user_id,
            opted_in=optin.opted_in,
            display_name=optin.display_name,
            opted_in_at=(
                optin.opted_out_at.isoformat()
                if optin.opted_out_at
                else optin.opted_in_at.isoformat()
            ),
        )

    except Exception as e:
        logger.error(
            f"Failed to opt-out user {current_user.id} from leaderboard: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Get leaderboard rankings (public endpoint).

    Only shows users who have opted in. Ranks by risk-adjusted return (Sharpe ratio).

    Args:
        limit: Max entries to return (default: 100, max: 500)
        offset: Pagination offset (default: 0)

    Returns:
        Leaderboard entries with rank, display name, XP, Sharpe, and return %

    Example:
        GET /api/v1/gamification/leaderboard?limit=10&offset=0

        Response:
        {
            "entries": [
                {
                    "rank": 1,
                    "display_name": "TraderPro",
                    "xp": 15000,
                    "sharpe": 2.5,
                    "return_pct": 45.2
                },
                ...
            ],
            "total_count": 42,
            "limit": 10,
            "offset": 0
        }
    """
    # Validate limits
    if limit > 500:
        raise HTTPException(status_code=400, detail="Limit cannot exceed 500")

    if offset < 0:
        raise HTTPException(status_code=400, detail="Offset must be non-negative")

    try:
        service = GamificationService(db)

        entries = await service.get_leaderboard(limit=limit, offset=offset)

        # Count total opted-in users
        from sqlalchemy import func, select

        from backend.app.gamification.models import LeaderboardOptIn

        stmt = select(func.count(LeaderboardOptIn.id)).where(
            LeaderboardOptIn.opted_in
        )
        result = await db.execute(stmt)
        total_count = result.scalar() or 0

        return LeaderboardResponse(
            entries=[LeaderboardEntry(**entry) for entry in entries],
            total_count=total_count,
            limit=limit,
            offset=offset,
        )

    except Exception as e:
        logger.error(f"Failed to get leaderboard: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
