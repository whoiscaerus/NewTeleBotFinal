"""
Copy Registry Models

Professional copy management system for product, legal, and marketing text
with A/B testing support and locale management.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from backend.app.core.db import Base, JSONBType


class CopyType(str, Enum):
    """Copy entry type categories."""

    PRODUCT = "product"  # Product UI copy (buttons, labels, tooltips)
    LEGAL = "legal"  # Legal disclaimers, terms, policies
    MARKETING = "marketing"  # Marketing campaigns, CTAs, emails
    NOTIFICATION = "notification"  # System notifications, alerts
    ERROR = "error"  # Error messages


class CopyStatus(str, Enum):
    """Copy entry lifecycle status."""

    DRAFT = "draft"  # Being authored
    REVIEW = "review"  # Pending approval
    APPROVED = "approved"  # Ready for use
    PUBLISHED = "published"  # Live in production
    ARCHIVED = "archived"  # No longer active


class CopyEntry(Base):
    """
    Copy registry entry.

    Represents a single piece of copy (text) that can have multiple
    locale variants and A/B test versions.
    """

    __tablename__ = "copy_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    key = Column(String(255), nullable=False, unique=True, index=True)
    type = Column(String(20), nullable=False, index=True)  # CopyType enum
    status = Column(String(20), nullable=False, default=CopyStatus.DRAFT)
    description = Column(Text, nullable=True)  # Editor notes
    entry_metadata = Column(
        "metadata", JSONBType, nullable=False, default=dict
    )  # Context, tags, etc.

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    created_by = Column(String(36), nullable=True)  # User ID
    updated_by = Column(String(36), nullable=True)  # User ID

    # Relationships
    variants = relationship(
        "CopyVariant", back_populates="entry", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("ix_copy_entries_type_status", "type", "status"),
        Index("ix_copy_entries_key", "key"),
    )

    def __repr__(self) -> str:
        return f"<CopyEntry {self.key} ({self.type})>"

    @property
    def default_variant(self) -> Optional["CopyVariant"]:
        """Get default (control) variant for this entry."""
        for variant in self.variants:
            if variant.is_control and variant.locale == "en":
                return variant
        # Fallback to first en variant
        for variant in self.variants:
            if variant.locale == "en":
                return variant
        return None

    def get_variant(
        self, locale: str = "en", ab_group: str | None = None
    ) -> Optional["CopyVariant"]:
        """
        Get variant for specific locale and A/B test group.

        Args:
            locale: Locale code (en, es, etc.)
            ab_group: A/B test group identifier (None for control)

        Returns:
            CopyVariant or None if not found
        """
        # If A/B group specified, try to find that variant
        if ab_group:
            for variant in self.variants:
                if variant.locale == locale and variant.ab_group == ab_group:
                    return variant

        # Fall back to control variant for locale
        for variant in self.variants:
            if variant.locale == locale and variant.is_control:
                return variant

        # Final fallback to English control
        return self.default_variant


class CopyVariant(Base):
    """
    Locale/A/B variant of a copy entry.

    Each entry can have multiple variants:
    - Different locales (en, es, etc.)
    - A/B test versions (control, variant_a, variant_b)
    """

    __tablename__ = "copy_variants"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    entry_id = Column(
        String(36), ForeignKey("copy_entries.id", ondelete="CASCADE"), nullable=False
    )
    locale = Column(String(10), nullable=False, index=True)
    ab_group = Column(String(50), nullable=True, index=True)  # A/B test group
    is_control = Column(Boolean, nullable=False, default=True)  # Control variant

    text = Column(Text, nullable=False)  # The actual copy
    variant_metadata = Column(
        "metadata", JSONBType, nullable=False, default=dict
    )  # Rich text, variables, etc.

    # A/B testing metrics
    impressions = Column(Integer, nullable=False, default=0)
    conversions = Column(Integer, nullable=False, default=0)
    conversion_rate = Column(Float, nullable=True)  # Computed

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    entry = relationship("CopyEntry", back_populates="variants")

    # Indexes
    __table_args__ = (
        Index("ix_copy_variants_entry_locale", "entry_id", "locale"),
        Index("ix_copy_variants_entry_ab", "entry_id", "ab_group"),
        Index("ix_copy_variants_locale", "locale"),
    )

    def __repr__(self) -> str:
        return f"<CopyVariant {self.entry_id}:{self.locale} ({self.ab_group or 'control'})>"

    def record_impression(self) -> None:
        """Record that this variant was shown."""
        self.impressions += 1
        self._update_conversion_rate()

    def record_conversion(self) -> None:
        """Record that this variant led to conversion."""
        self.conversions += 1
        self._update_conversion_rate()

    def _update_conversion_rate(self) -> None:
        """Recompute conversion rate."""
        if self.impressions > 0:
            self.conversion_rate = self.conversions / self.impressions
        else:
            self.conversion_rate = 0.0
