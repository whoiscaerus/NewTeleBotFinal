"""Dynamic quote generation for shop plans in multiple currencies.

PR-029: RateFetcher Integration & Dynamic Quotes

Provides quote_for(plan_code, currency) to get plan prices in any currency.
Uses rates.py for FX conversions and catalog.py for base plans.
"""

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.billing.catalog.service import CatalogService
from backend.app.billing.pricing.rates import RateFetcher

logger = logging.getLogger(__name__)


class QuoteService:
    """Generates dynamic quotes for plans in various currencies."""

    # Base currency conversions (GBP = 1.0)
    BASE_RATES = {
        "GBP": 1.0,
        "USD": 1.28,
        "EUR": 0.92,
        "JPY": 190.0,
        "AUD": 1.95,
        "CAD": 1.73,
        "CHF": 1.13,
        "CNY": 9.2,
        "INR": 106.0,
        "SGD": 1.72,
    }

    def __init__(self, db: AsyncSession, rate_fetcher: Optional[RateFetcher] = None):
        """Initialize quote service.

        Args:
            db: Database session
            rate_fetcher: Optional RateFetcher (for DI in tests)
        """
        self.db = db
        self.catalog_service = CatalogService(db)
        self.rate_fetcher = rate_fetcher

    async def quote_for(
        self,
        plan_code: str,
        currency: str = "GBP",
    ) -> float:
        """Get plan quote in specified currency.

        Args:
            plan_code: Plan slug (e.g., 'gold_monthly', 'silver_annual')
            currency: Target currency code (GBP, USD, EUR, etc)

        Returns:
            Quote amount in specified currency

        Raises:
            ValueError: If plan not found or currency not supported
        """
        try:
            # 1. Get base plan price (in GBP)
            product = await self.catalog_service.get_product_by_slug(plan_code)
            if not product:
                raise ValueError(f"Plan not found: {plan_code}")

            # Get price from product tier (assume tier 0 for base price)
            if not product.tiers or len(product.tiers) == 0:
                raise ValueError(f"Plan has no pricing tiers: {plan_code}")

            base_tier = product.tiers[0]
            base_price_gbp = base_tier.base_price

            logger.info(
                f"Quote for {plan_code}: base £{base_price_gbp} in {currency}",
                extra={"plan": plan_code, "currency": currency},
            )

            # 2. Convert to target currency
            if currency == "GBP":
                return round(base_price_gbp, 2)

            # Use rate fetcher if available (for live rates)
            if self.rate_fetcher:
                try:
                    if currency == "USD":
                        rate = await self.rate_fetcher.fetch_gbp_usd()
                    elif currency in ["BTC", "ETH", "LTC"]:
                        # Crypto conversion would require crypto price fetch
                        crypto_map = {
                            "BTC": "bitcoin",
                            "ETH": "ethereum",
                            "LTC": "litecoin",
                        }
                        crypto_id = crypto_map.get(currency)
                        if not crypto_id:
                            raise ValueError(f"Unsupported crypto: {currency}")
                        prices = await self.rate_fetcher.fetch_crypto_prices(
                            [crypto_id]
                        )
                        if crypto_id not in prices:
                            raise ValueError(f"Could not fetch {currency} price")
                        rate = prices[crypto_id]
                    else:
                        # Use static rates as fallback
                        rate_tmp = self.BASE_RATES.get(currency)
                        if not rate_tmp:
                            raise ValueError(f"Unsupported currency: {currency}")
                        rate = rate_tmp
                except Exception as e:
                    logger.warning(
                        f"Failed to fetch live rate for {currency}, using static: {e}"
                    )
                    rate_tmp = self.BASE_RATES.get(currency)
                    if not rate_tmp:
                        raise ValueError(f"No fallback rate for {currency}")
                    rate = rate_tmp
            else:
                # Use static rates
                rate_tmp = self.BASE_RATES.get(currency)
                if not rate_tmp:
                    raise ValueError(f"No rate available for {currency}")
                rate = rate_tmp

            if not rate:
                raise ValueError(f"No rate available for {currency}")

            converted_price = base_price_gbp * rate
            logger.info(
                f"Quote calculated: £{base_price_gbp} × {rate:.4f} = {currency} {converted_price:.2f}",
                extra={
                    "plan": plan_code,
                    "base_gbp": base_price_gbp,
                    "rate": rate,
                    "final": converted_price,
                },
            )

            return round(converted_price, 2)

        except ValueError as e:
            logger.error(f"Invalid quote request: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error generating quote: {e}", exc_info=True)
            raise

    async def get_quotes_for_all_plans(
        self,
        currency: str = "GBP",
    ) -> dict[str, float]:
        """Get quotes for all available plans in currency.

        Args:
            currency: Target currency code

        Returns:
            Dict mapping plan slug to quote amount

        Raises:
            ValueError: If currency not supported
        """
        try:
            # Get all products
            products = await self.catalog_service.get_all_products()
            if not products:
                logger.warning("No products found")
                return {}

            quotes = {}
            for product in products:
                try:
                    product_slug = str(product.slug)
                    quote = await self.quote_for(product_slug, currency)
                    quotes[product_slug] = quote
                except Exception as e:
                    logger.error(f"Failed to quote {str(product.slug)}: {e}")
                    # Skip this product, continue with others
                    continue

            logger.info(
                f"Generated {len(quotes)} quotes for {currency}",
                extra={"currency": currency, "count": len(quotes)},
            )

            return quotes

        except Exception as e:
            logger.error(f"Failed to get all quotes: {e}", exc_info=True)
            raise

    async def get_comparison(
        self,
        plan_code: str,
    ) -> dict[str, float]:
        """Get plan quote across multiple currencies.

        Args:
            plan_code: Plan slug

        Returns:
            Dict mapping currency to quote amount
        """
        try:
            comparison = {}
            currencies = list(self.BASE_RATES.keys())

            for currency in currencies:
                try:
                    quote = await self.quote_for(plan_code, currency)
                    comparison[currency] = quote
                except Exception as e:
                    logger.warning(f"Failed to quote in {currency}: {e}")
                    continue

            logger.info(
                f"Generated price comparison for {plan_code} ({len(comparison)} currencies)",
                extra={"plan": plan_code, "count": len(comparison)},
            )

            return comparison

        except Exception as e:
            logger.error(f"Failed to get price comparison: {e}", exc_info=True)
            raise

    async def validate_quote(
        self,
        plan_code: str,
        currency: str,
        expected_amount: float,
        tolerance: float = 0.05,  # ±5% tolerance for rate fluctuations
    ) -> bool:
        """Validate that a quoted amount is still accurate.

        Useful for checkout validations (prevent stale prices).

        Args:
            plan_code: Plan slug
            currency: Currency code
            expected_amount: Expected quote amount
            tolerance: Tolerance percentage (0.05 = 5%)

        Returns:
            True if quote is valid within tolerance
        """
        try:
            actual_quote = await self.quote_for(plan_code, currency)
            diff = abs(actual_quote - expected_amount) / expected_amount

            is_valid = diff <= tolerance
            logger.info(
                f"Quote validation: expected {currency}{expected_amount:.2f}, "
                f"actual {currency}{actual_quote:.2f}, diff {diff*100:.1f}%",
                extra={
                    "plan": plan_code,
                    "expected": expected_amount,
                    "actual": actual_quote,
                    "valid": is_valid,
                },
            )

            return is_valid

        except Exception as e:
            logger.error(f"Failed to validate quote: {e}", exc_info=True)
            return False
