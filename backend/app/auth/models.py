"""Authentication and authorization models."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.db import Base

if TYPE_CHECKING:
    pass


class UserRole(str, Enum):
    """User roles for RBAC."""

    OWNER = "owner"
    ADMIN = "admin"
    USER = "user"


class User(Base):
    """User model."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole), nullable=False, default=UserRole.USER, index=True
    )
    telegram_user_id: Mapped[str | None] = mapped_column(
        String(50), unique=True, nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    # NOTE: AccountLink (PR-043), Endorsement (PR-024), and UserTrustScore (PR-024) are implemented

    account_links: Mapped[list] = relationship(
        "AccountLink",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select",
    )
    endorsements_given: Mapped[list] = relationship(
        "Endorsement",
        foreign_keys="[Endorsement.endorser_id]",
        back_populates="endorser",
        lazy="select",
        viewonly=False,
    )
    endorsements_received: Mapped[list] = relationship(
        "Endorsement",
        foreign_keys="[Endorsement.endorsee_id]",
        back_populates="endorsee",
        lazy="select",
        viewonly=False,
    )
    trust_score: Mapped[object] = relationship(
        "UserTrustScore", back_populates="user", uselist=False, lazy="select"
    )

    def __init__(self, **kwargs):
        """Initialize User with default role."""
        if "role" not in kwargs:
            kwargs["role"] = UserRole.USER
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role})>"
