"""Product catalog database models."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, Text

from backend.app.core.db import Base


class ProductCategory(Base):
    """Product category for organizing catalog.

    Examples:
        - Trading Signals
        - Copy Trading
        - Advanced Analytics
    """

    __tablename__ = "product_categories"

    id = Column(String(36), primary_key=True)
    name = Column(String(100), nullable=False, index=True)
    slug = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    icon = Column(String(50), nullable=True)  # Emoji or icon name
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (Index("ix_categories_slug", "slug"),)

    def __repr__(self) -> str:
        return f"<ProductCategory {self.name}>"


class Product(Base):
    """Product in catalog.

    Products are organized by category and have multiple tier options.
    """

    __tablename__ = "products"

    id = Column(String(36), primary_key=True)
    category_id = Column(
        String(36), ForeignKey("product_categories.id"), nullable=False
    )
    name = Column(String(100), nullable=False, index=True)
    slug = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    features = Column(Text, nullable=True)  # JSON array of features
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_products_category", "category_id"),
        Index("ix_products_slug", "slug"),
    )

    def __repr__(self) -> str:
        return f"<Product {self.name}>"


class ProductTier(Base):
    """Pricing tier for a product.

    Each product can have multiple tiers:
    - Free tier (tier_level=0)
    - Premium tier (tier_level=1)
    - VIP tier (tier_level=2)
    - Enterprise tier (tier_level=3)
    """

    __tablename__ = "product_tiers"

    id = Column(String(36), primary_key=True)
    product_id = Column(String(36), ForeignKey("products.id"), nullable=False)
    tier_level = Column(
        Integer, nullable=False
    )  # 0=Free, 1=Premium, 2=VIP, 3=Enterprise
    tier_name = Column(String(50), nullable=False)
    base_price = Column(Float, nullable=False)  # In GBP
    billing_period = Column(
        String(20), nullable=False, default="monthly"
    )  # 'monthly', 'annual'
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_product_tiers_product", "product_id"),
        Index("ix_product_tiers_level", "tier_level"),
        Index("ix_product_tier_unique", "product_id", "tier_level", unique=True),
    )

    def __repr__(self) -> str:
        return f"<ProductTier {self.tier_name} £{self.base_price}/mo>"
