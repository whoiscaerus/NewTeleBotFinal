"""
Copy Registry Pydantic Schemas

Request/response models for copy registry API.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, validator


class CopyVariantCreate(BaseModel):
    """Schema for creating a copy variant."""

    locale: str = Field(
        ..., min_length=2, max_length=10, description="Locale code (en, es, etc.)"
    )
    ab_group: str | None = Field(
        None, max_length=50, description="A/B test group identifier"
    )
    is_control: bool = Field(True, description="Whether this is the control variant")
    text: str = Field(..., min_length=1, description="The actual copy text")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    @validator("locale")
    def validate_locale(cls, v: str) -> str:
        """Validate locale format."""
        if not v.islower():
            raise ValueError("Locale must be lowercase (e.g., 'en', 'es')")
        return v


class CopyVariantResponse(BaseModel):
    """Schema for copy variant response."""

    id: str
    entry_id: str
    locale: str
    ab_group: str | None
    is_control: bool
    text: str
    metadata: dict[str, Any]
    impressions: int
    conversions: int
    conversion_rate: float | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CopyEntryCreate(BaseModel):
    """Schema for creating a copy entry."""

    key: str = Field(
        ...,
        min_length=1,
        max_length=255,
        pattern="^[a-z0-9._-]+$",
        description="Unique key (e.g., 'hero.title', 'cta.signup')",
    )
    type: str = Field(..., description="Copy type (product, legal, marketing, etc.)")
    description: str | None = Field(None, description="Editor notes")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Context, tags, etc."
    )
    variants: list[CopyVariantCreate] = Field(
        default_factory=list, description="Initial locale variants"
    )

    @validator("key")
    def validate_key(cls, v: str) -> str:
        """Validate key format."""
        if not v.islower():
            raise ValueError("Key must be lowercase")
        if "__" in v:
            raise ValueError("Key cannot contain double underscores")
        return v


class CopyEntryUpdate(BaseModel):
    """Schema for updating a copy entry."""

    type: str | None = None
    status: str | None = None
    description: str | None = None
    metadata: dict[str, Any] | None = None


class CopyEntryResponse(BaseModel):
    """Schema for copy entry response."""

    id: str
    key: str
    type: str
    status: str
    description: str | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    created_by: str | None
    updated_by: str | None
    variants: list[CopyVariantResponse]

    class Config:
        from_attributes = True


class CopyResolveRequest(BaseModel):
    """Schema for resolving copy text."""

    keys: list[str] = Field(..., min_items=1, description="Copy keys to resolve")
    locale: str = Field("en", description="Desired locale")
    ab_group: str | None = Field(None, description="A/B test group")
    record_impression: bool = Field(False, description="Whether to record impression")


class CopyResolveResponse(BaseModel):
    """Schema for resolved copy text."""

    locale: str
    ab_group: str | None
    copy: dict[str, str]  # key -> text
    missing: list[str]  # Keys not found


class CopyImpressionRequest(BaseModel):
    """Schema for recording impression."""

    key: str = Field(..., description="Copy key")
    locale: str = Field("en", description="Locale")
    ab_group: str | None = Field(None, description="A/B test group")


class CopyConversionRequest(BaseModel):
    """Schema for recording conversion."""

    key: str = Field(..., description="Copy key")
    locale: str = Field("en", description="Locale")
    ab_group: str | None = Field(None, description="A/B test group")
