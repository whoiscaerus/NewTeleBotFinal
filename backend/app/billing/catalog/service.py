"""Catalog service for product management and access control."""

import logging
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.billing.catalog.models import Product, ProductCategory, ProductTier

logger = logging.getLogger(__name__)


class CatalogService:
    """Service for managing product catalog and user access.

    Handles:
    - Loading products and tiers
    - Filtering by user tier level
    - Checking product availability
    - Managing product metadata
    """

    def __init__(self, db: AsyncSession):
        """Initialize catalog service.

        Args:
            db: Database session
        """
        self.db = db

    async def get_all_categories(self) -> list[ProductCategory]:
        """Get all product categories.

        Returns:
            List of all product categories
        """
        try:
            query = select(ProductCategory).order_by(ProductCategory.name)
            result = await self.db.execute(query)
            categories = list(result.scalars().all())
            logger.info(f"Loaded {len(categories)} product categories")
            return categories
        except Exception as e:
            logger.error(f"Error loading categories: {e}", exc_info=True)
            raise

    async def get_category(self, category_id: str) -> ProductCategory | None:
        """Get specific category by ID.

        Args:
            category_id: Category ID

        Returns:
            ProductCategory or None if not found
        """
        try:
            query = select(ProductCategory).where(ProductCategory.id == category_id)
            result = await self.db.execute(query)
            category = result.scalars().first()
            return category
        except Exception as e:
            logger.error(f"Error loading category {category_id}: {e}", exc_info=True)
            raise

    async def get_all_products(self) -> list[Product]:
        """Get all products with their tiers.

        Returns:
            List of all products
        """
        try:
            query = (
                select(Product)
                .options(selectinload(Product.tiers))
                .order_by(Product.name)
            )
            result = await self.db.execute(query)
            products = list(result.scalars().unique().all())
            logger.info(f"Loaded {len(products)} products")
            return products
        except Exception as e:
            logger.error(f"Error loading products: {e}", exc_info=True)
            raise

    async def get_product(self, product_id: str) -> Product | None:
        """Get specific product by ID.

        Args:
            product_id: Product ID

        Returns:
            Product or None if not found
        """
        try:
            query = (
                select(Product)
                .where(Product.id == product_id)
                .options(selectinload(Product.tiers))
            )
            result = await self.db.execute(query)
            product = result.scalars().first()
            return product
        except Exception as e:
            logger.error(f"Error loading product {product_id}: {e}", exc_info=True)
            raise

    async def get_product_by_slug(self, slug: str) -> Product | None:
        """Get product by slug.

        Args:
            slug: Product slug

        Returns:
            Product or None if not found
        """
        try:
            query = (
                select(Product)
                .where(Product.slug == slug)
                .options(selectinload(Product.tiers))
            )
            result = await self.db.execute(query)
            product = result.scalars().first()
            return product
        except Exception as e:
            logger.error(f"Error loading product by slug {slug}: {e}", exc_info=True)
            raise

    async def get_products_for_tier(self, tier_level: int) -> list[Product]:
        """Get products accessible to user of given tier level.

        User can access products if they have tier >= required tier.

        Args:
            tier_level: User tier level (0=Free, 1=Premium, 2=VIP, 3=Enterprise)

        Returns:
            List of products accessible to this tier
        """
        try:
            query = (
                select(Product)
                .join(ProductTier)
                .where(ProductTier.tier_level <= tier_level)
                .distinct()
                .order_by(Product.name)
            )
            result = await self.db.execute(query)
            products = list(result.scalars().all())
            logger.info(
                f"Loaded {len(products)} products for tier {tier_level}",
                extra={"tier_level": tier_level},
            )
            return products
        except Exception as e:
            logger.error(
                f"Error loading products for tier {tier_level}: {e}",
                exc_info=True,
            )
            raise

    async def get_product_tier(self, tier_id: str) -> ProductTier | None:
        """Get specific product tier by ID.

        Args:
            tier_id: Tier ID

        Returns:
            ProductTier or None if not found
        """
        try:
            query = select(ProductTier).where(ProductTier.id == tier_id)
            result = await self.db.execute(query)
            tier = result.scalars().first()
            return tier
        except Exception as e:
            logger.error(f"Error loading product tier {tier_id}: {e}", exc_info=True)
            raise

    async def create_category(
        self, name: str, slug: str, description: str | None = None
    ) -> ProductCategory:
        """Create new product category.

        Args:
            name: Category name
            slug: URL-safe slug
            description: Optional description

        Returns:
            Created ProductCategory

        Raises:
            ValueError: If slug already exists
        """
        try:
            category = ProductCategory(
                id=str(uuid4()),
                name=name,
                slug=slug,
                description=description,
            )
            self.db.add(category)
            await self.db.commit()
            await self.db.refresh(category)
            logger.info(
                f"Created category: {category.name}", extra={"category_id": category.id}
            )
            return category
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating category: {e}", exc_info=True)
            raise

    async def create_product(
        self,
        category_id: str,
        name: str,
        slug: str,
        description: str | None = None,
        features: str | None = None,
    ) -> Product:
        """Create new product.

        Args:
            category_id: Category ID
            name: Product name
            slug: URL-safe slug
            description: Optional description
            features: Optional JSON array of features

        Returns:
            Created Product
        """
        try:
            product = Product(
                id=str(uuid4()),
                category_id=category_id,
                name=name,
                slug=slug,
                description=description,
                features=features,
            )
            self.db.add(product)
            await self.db.commit()
            await self.db.refresh(product)
            logger.info(
                f"Created product: {product.name}", extra={"product_id": product.id}
            )
            return product
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating product: {e}", exc_info=True)
            raise

    async def create_product_tier(
        self,
        product_id: str,
        tier_level: int,
        tier_name: str,
        base_price: float,
        billing_period: str = "monthly",
    ) -> ProductTier:
        """Create product tier with pricing.

        Args:
            product_id: Product ID
            tier_level: Tier level (0=Free, 1=Premium, 2=VIP, 3=Enterprise)
            tier_name: Display name (e.g., "Premium Monthly")
            base_price: Price in GBP
            billing_period: 'monthly' or 'annual'

        Returns:
            Created ProductTier
        """
        try:
            tier = ProductTier(
                id=str(uuid4()),
                product_id=product_id,
                tier_level=tier_level,
                tier_name=tier_name,
                base_price=base_price,
                billing_period=billing_period,
            )
            self.db.add(tier)
            await self.db.commit()
            await self.db.refresh(tier)
            logger.info(
                f"Created tier: {tier.tier_name} £{tier.base_price}",
                extra={"tier_id": tier.id, "price": base_price},
            )
            return tier
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating product tier: {e}", exc_info=True)
            raise
