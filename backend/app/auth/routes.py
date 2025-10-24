"""Authentication endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.models import User
from backend.app.auth.rbac import require_roles
from backend.app.auth.schemas import (
    LoginRequest,
    LoginResponse,
    UserCreate,
    UserResponse,
)
from backend.app.auth.utils import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from backend.app.core.db import get_db
from backend.app.core.decorators import abuse_throttle, rate_limit
from backend.app.core.logging import get_logger

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


async def get_bearer_token(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Extract bearer token from Authorization header.

    Args:
        authorization: Authorization header value

    Returns:
        str: Bearer token

    Raises:
        HTTPException: 403 if header missing or invalid format
    """
    if not authorization:
        raise HTTPException(status_code=403, detail="Missing Authorization header")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=403, detail="Invalid Authorization header format"
        )

    return parts[1]


async def get_current_user(
    token: Annotated[str, Depends(get_bearer_token)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Extract and validate JWT token, return current user.

    Args:
        token: Bearer token from Authorization header
        db: Database session

    Returns:
        User: Current authenticated user

    Raises:
        HTTPException: 401 if token invalid or user not found
    """
    logger = get_logger(__name__)

    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            logger.warning("User not found", extra={"user_id": user_id})
            raise HTTPException(status_code=401, detail="User not found")

        return user

    except ValueError as e:
        logger.warning("Token validation failed", extra={"error": str(e)})
        raise HTTPException(status_code=401, detail="Invalid token")


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
@rate_limit(max_tokens=10, refill_rate=0.17, window_seconds=60)  # 10/min
async def register(
    request: Request,
    user_create: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Register a new user.

    Args:
        request: HTTP request (for rate limiting)
        user_create: User registration request (email, password)
        db: Database session

    Returns:
        UserResponse: Created user details

    Raises:
        HTTPException: 400 if email already exists, 429 if rate limited
    """
    logger = get_logger(__name__)

    # Check if user exists
    stmt = select(User).where(User.email == user_create.email)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        logger.warning(
            "Registration failed: email already exists",
            extra={"email": user_create.email},
        )
        raise HTTPException(status_code=400, detail="Email already registered")

    # Create user
    user = User(
        email=user_create.email, password_hash=hash_password(user_create.password)
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info("User registered", extra={"user_id": user.id, "email": user.email})

    return UserResponse(id=user.id, email=user.email, role=user.role.value)


@router.post("/login", response_model=LoginResponse)
@rate_limit(max_tokens=10, refill_rate=0.17, window_seconds=60)  # 10/min
@abuse_throttle(max_failures=5, lockout_seconds=300)  # 5 failures = 5 min lockout
async def login(
    request: Request,
    login_req: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Login user with email and password.

    Args:
        request: HTTP request (for rate limiting)
        login_req: Login credentials (email, password)
        db: Database session

    Returns:
        LoginResponse: JWT token and user info

    Raises:
        HTTPException: 401 if credentials invalid, 429 if rate limited or throttled
    """
    logger = get_logger(__name__)

    # Find user
    stmt = select(User).where(User.email == login_req.email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(login_req.password, user.password_hash):
        logger.warning(
            "Login failed: invalid credentials", extra={"email": login_req.email}
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Generate token
    token = create_access_token(subject=user.id, role=user.role.value)
    logger.info("User logged in", extra={"user_id": user.id, "email": user.email})

    return LoginResponse(
        access_token=token,
        user=UserResponse(id=user.id, email=user.email, role=user.role.value),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: Annotated[User, Depends(get_current_user)]):
    """Get current user profile.

    Args:
        current_user: Current authenticated user

    Returns:
        UserResponse: Current user details
    """
    return UserResponse(
        id=current_user.id, email=current_user.email, role=current_user.role.value
    )


@router.post("/protected-admin")
@require_roles("ADMIN", "OWNER")
async def admin_only_endpoint(current_user: Annotated[User, Depends(get_current_user)]):
    """Protected endpoint for admins only.

    Args:
        current_user: Current authenticated user (must be admin/owner)

    Returns:
        dict: Success message
    """
    logger = get_logger(__name__)
    logger.info(
        "Admin endpoint accessed",
        extra={"user_id": current_user.id, "role": current_user.role.value},
    )

    return {"message": f"Hello {current_user.role.value}: {current_user.email}"}
