"""User models."""

from sqlalchemy import Column, String
from sqlalchemy.orm import relationship

from backend.app.core.db import Base


class User(Base):
    """User model."""

    __tablename__ = "users"

    id = Column(String, primary_key=True)
    email = Column(String, nullable=False, unique=True)
    username = Column(String)
    status = Column(String, default="active")
    theme_preference = Column(
        String, default="professional"
    )  # professional, darkTrader, goldMinimal

    # Relationships
    preferences = relationship(
        "UserPreferences",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    privacy_requests = relationship(
        "PrivacyRequest",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    paper_account = relationship(
        "PaperAccount",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    reports = relationship(
        "Report",
        back_populates="user",
        cascade="all, delete-orphan",
    )  # PR-101: AI-Generated Reports
