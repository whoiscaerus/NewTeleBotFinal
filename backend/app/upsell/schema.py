"""
Upsell API schemas.
"""

from datetime import datetime

from pydantic import BaseModel, Field, validator


class RecommendationOut(BaseModel):
    """Recommendation response."""

    id: str
    recommendation_type: str
    score: float = Field(ge=0.0, le=1.0)
    headline: str
    copy_text: str = Field(..., alias="copy")
    discount_percent: int | None = Field(None, ge=0, le=100)
    expires_at: datetime | None
    shown: bool
    clicked: bool
    converted: bool
    created_at: datetime

    class Config:
        orm_mode = True


class ExposureCreate(BaseModel):
    """Create exposure record."""

    experiment_id: str
    variant_id: str
    recommendation_id: str | None = None
    channel: str | None = Field(
        default=None, pattern="^(telegram|miniapp|web|email)$"
    )


class ExposureOut(BaseModel):
    """Exposure response."""

    id: str
    user_id: str
    experiment_id: str
    variant_id: str
    recommendation_id: str | None
    converted: bool
    converted_at: datetime | None
    channel: str | None
    created_at: datetime

    class Config:
        orm_mode = True


class ConversionEvent(BaseModel):
    """Conversion webhook event."""

    exposure_id: str
    plan_id: str | None = None
    revenue_amount: float | None = None


class ExperimentOut(BaseModel):
    """Experiment response."""

    id: str
    name: str
    description: str | None
    recommendation_type: str
    traffic_split_percent: int = Field(ge=0, le=100)
    status: str
    control_exposures: int
    control_conversions: int
    variant_exposures: int
    variant_conversions: int
    control_ctr: float
    variant_ctr: float
    uplift: float | None
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None

    class Config:
        orm_mode = True

    @validator("control_ctr", "variant_ctr", pre=True, always=True)
    def compute_ctr(cls, v, values):
        """Compute CTR if not provided."""
        if v is None:
            return 0.0
        return v


class ExperimentCreate(BaseModel):
    """Create experiment."""

    name: str = Field(..., min_length=3, max_length=200)
    description: str | None = None
    recommendation_type: str
    traffic_split_percent: int = Field(50, ge=0, le=100)
    min_sample_size: int = Field(100, ge=10)
    min_ctr: float | None = Field(None, ge=0.0, le=1.0)
    max_duration_days: int | None = Field(None, ge=1, le=365)


class VariantCreate(BaseModel):
    """Create variant."""

    experiment_id: str
    name: str = Field(..., min_length=1, max_length=200)
    headline: str = Field(..., min_length=5, max_length=200)
    copy_text: str = Field(..., min_length=10, alias="copy")
    cta_text: str = Field("Upgrade Now", min_length=1, max_length=100)
    discount_percent: int | None = Field(None, ge=0, le=100)
    is_control: bool = False


class VariantOut(BaseModel):
    """Variant response."""

    id: str
    experiment_id: str
    name: str
    headline: str
    copy_text: str = Field(..., alias="copy")
    cta_text: str
    discount_percent: int | None
    is_control: bool
    created_at: datetime

    class Config:
        orm_mode = True
