"""Pricing rules for calculating final prices.

Rules applied in order:
1. Base price (from product tier)
2. Regional FX markup (based on user location/currency)
3. Affiliate bonus (discount if user was referred)
4. Volume discount (future: buy multiple months)
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PricingRule:
    """Pricing rule applied during calculation."""

    name: str
    multiplier: float = 1.0
    fixed_amount: float = 0.0

    def apply(self, price: float) -> float:
        """Apply rule to price.

        Args:
            price: Current price in GBP

        Returns:
            Adjusted price
        """
        return (price * self.multiplier) + self.fixed_amount


class RegionalMarkupRule(PricingRule):
    """Regional FX markup based on user's region.

    Converts base GBP price to regional currency equivalent.
    """

    def __init__(self, region: str, fx_rate: float):
        """Initialize regional markup.

        Args:
            region: User's region (e.g., 'US', 'EU', 'ASIA')
            fx_rate: FX conversion rate to regional currency
        """
        super().__init__(name=f"regional_markup_{region}", multiplier=fx_rate)
        self.region = region
        self.fx_rate = fx_rate


class AffiliateDiscountRule(PricingRule):
    """Affiliate bonus discount for referred users.

    Applies percentage discount if user was referred.
    """

    def __init__(self, discount_percent: float = 10.0):
        """Initialize affiliate discount.

        Args:
            discount_percent: Discount percentage (default 10%)
        """
        self.discount_percent = discount_percent
        super().__init__(
            name="affiliate_discount",
            multiplier=1.0 - (discount_percent / 100.0),
        )


class VolumeDiscountRule(PricingRule):
    """Volume discount for buying multiple months.

    Applies percentage discount based on subscription length.
    """

    def __init__(self, months: int):
        """Initialize volume discount.

        Args:
            months: Number of months (1, 3, 6, 12)
        """
        self.months = months

        # Discount tiers: 3mo=5%, 6mo=10%, 12mo=20%
        discount_map = {1: 0, 3: 5, 6: 10, 12: 20}
        discount_percent = discount_map.get(months, 0)

        super().__init__(
            name=f"volume_discount_{months}mo",
            multiplier=1.0 - (discount_percent / 100.0),
        )


class PricingRuleEngine:
    """Applies pricing rules in sequence."""

    def __init__(self):
        """Initialize rule engine."""
        self.rules: list[PricingRule] = []

    def add_rule(self, rule: PricingRule) -> None:
        """Add rule to engine.

        Args:
            rule: Rule to apply
        """
        self.rules.append(rule)
        logger.info(f"Added pricing rule: {rule.name}")

    def calculate(self, base_price: float) -> float:
        """Apply all rules to base price.

        Args:
            base_price: Base price in GBP

        Returns:
            Final price after all rules applied
        """
        price = base_price
        for rule in self.rules:
            price = rule.apply(price)
            logger.debug(f"Applied {rule.name}: £{base_price} → £{price}")

        return price

    def get_breakdown(self, base_price: float) -> dict[str, float]:
        """Get detailed breakdown of pricing.

        Args:
            base_price: Base price in GBP

        Returns:
            Dictionary with breakdown of each rule applied
        """
        breakdown = {"base": base_price}
        price = base_price

        for rule in self.rules:
            old_price = price
            price = rule.apply(price)
            breakdown[rule.name] = price - old_price

        breakdown["total"] = price
        return breakdown
