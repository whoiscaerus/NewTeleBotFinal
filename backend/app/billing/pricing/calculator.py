"""Pricing calculator for dynamic price computation."""

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.billing.catalog.service import CatalogService
from backend.app.billing.pricing.rules import (
    AffiliateDiscountRule,
    PricingRuleEngine,
    RegionalMarkupRule,
    VolumeDiscountRule,
)

logger = logging.getLogger(__name__)

# Regional FX rates (hardcoded for now, in production would fetch from PR-013 market data)
FX_RATES = {
    "GB": 1.0,  # GBP base
    "US": 1.28,  # USD
    "EU": 0.92,  # EUR
    "ASIA": 1.5,  # SGD/HKD average
}


@dataclass
class PriceDetail:
    """Detailed pricing information."""

    product_tier_id: str
    base_price: float  # GBP before markups
    regional_price: float  # After FX markup
    affiliate_discount: float  # Discount amount (if applicable)
    volume_discount: float  # Discount amount (if applicable)
    final_price: float  # Total after all markups/discounts
    currency: str  # 'GBP', 'USD', etc
    region: str  # 'GB', 'US', 'EU', 'ASIA'
    billing_period: str  # 'monthly', 'annual'

    def to_dict(self) -> dict:
        """Convert to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "product_tier_id": self.product_tier_id,
            "base_price": round(self.base_price, 2),
            "regional_price": round(self.regional_price, 2),
            "affiliate_discount": round(self.affiliate_discount, 2),
            "volume_discount": round(self.volume_discount, 2),
            "final_price": round(self.final_price, 2),
            "currency": self.currency,
            "region": self.region,
            "billing_period": self.billing_period,
        }


class PricingCalculator:
    """Calculates dynamic pricing with regional markups and bonuses."""

    def __init__(self, db: AsyncSession):
        """Initialize pricing calculator.

        Args:
            db: Database session
        """
        self.db = db
        self.catalog_service = CatalogService(db)

    async def get_price(
        self,
        product_tier_id: str,
        user_id: str | None = None,
        region: str = "GB",
        months: int = 1,
    ) -> PriceDetail:
        """Calculate final price for product tier.

        Applies rules in order:
        1. Base price (from product tier)
        2. Regional FX markup
        3. Affiliate discount (if user was referred)
        4. Volume discount (if buying multiple months)

        Args:
            product_tier_id: Product tier ID
            user_id: User ID (for checking referrer)
            region: User's region ('GB', 'US', 'EU', 'ASIA')
            months: Number of months buying (1, 3, 6, 12)

        Returns:
            PriceDetail with breakdown

        Raises:
            ValueError: If product tier not found
        """
        try:
            # 1. Get product tier and base price
            tier = await self.catalog_service.get_product_tier(product_tier_id)
            if not tier:
                raise ValueError(f"Product tier not found: {product_tier_id}")

            base_price = float(tier.base_price)
            billing_period = str(tier.billing_period)
            logger.info(
                f"Calculating price for {product_tier_id}: base £{base_price}",
                extra={"tier_id": product_tier_id, "region": region},
            )

            # 2. Initialize rule engine
            engine = PricingRuleEngine()

            # 3. Apply regional FX markup
            fx_rate = FX_RATES.get(region, 1.0)
            if fx_rate != 1.0:
                engine.add_rule(RegionalMarkupRule(region, fx_rate))

            regional_price = engine.calculate(base_price)

            # 4. Check for affiliate discount
            affiliate_discount = 0.0
            referrer_id = await self._get_referrer(user_id)
            if referrer_id:
                engine.add_rule(AffiliateDiscountRule(discount_percent=10.0))
                affiliate_discount = regional_price * 0.10
                logger.info(
                    f"Applied affiliate discount for {user_id} (referrer: {referrer_id})",
                    extra={"user_id": user_id, "referrer_id": referrer_id},
                )

            # 5. Apply volume discount
            volume_discount = 0.0
            if months > 1:
                engine.add_rule(VolumeDiscountRule(months))
                volume_discount_rule = VolumeDiscountRule(months)
                volume_discount = (regional_price - affiliate_discount) * (
                    1 - volume_discount_rule.multiplier
                )
                logger.info(
                    f"Applied volume discount for {months} months",
                    extra={"months": months},
                )

            # 6. Calculate final price
            final_price = engine.calculate(base_price)

            # Determine currency based on region
            currency_map = {"GB": "GBP", "US": "USD", "EU": "EUR", "ASIA": "SGD"}
            currency = currency_map.get(region, "GBP")

            detail = PriceDetail(
                product_tier_id=product_tier_id,
                base_price=base_price,
                regional_price=regional_price,
                affiliate_discount=affiliate_discount,
                volume_discount=volume_discount,
                final_price=final_price,
                currency=currency,
                region=region,
                billing_period=billing_period,
            )

            logger.info(
                f"Price calculated: £{base_price} → {detail.currency} {final_price}",
                extra={
                    "tier_id": product_tier_id,
                    "base": base_price,
                    "final": final_price,
                    "currency": currency,
                },
            )

            return detail

        except Exception as e:
            logger.error(f"Error calculating price: {e}", exc_info=True)
            raise

    async def _get_referrer(self, user_id: str | None) -> str | None:
        """Get referrer ID for user (from PR-024 affiliate system).

        Args:
            user_id: User ID

        Returns:
            Referrer user ID or None
        """
        if not user_id:
            return None

        try:
            # In production, this would query the affiliate system (PR-024)
            # For now, just return None (no referrer)
            return None
        except Exception as e:
            logger.error(f"Error getting referrer: {e}", exc_info=True)
            return None

    async def get_comparison(
        self,
        product_tier_id: str,
        user_id: str | None = None,
    ) -> dict:
        """Get price comparison across regions.

        Args:
            product_tier_id: Product tier ID
            user_id: User ID

        Returns:
            Dictionary with prices for each region
        """
        try:
            comparison = {}
            for region in FX_RATES.keys():
                price_detail = await self.get_price(product_tier_id, user_id, region)
                comparison[region] = price_detail.to_dict()

            return comparison
        except Exception as e:
            logger.error(f"Error getting price comparison: {e}", exc_info=True)
            raise
