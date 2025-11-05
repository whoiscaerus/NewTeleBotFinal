"""Pricing API routes for dynamic FX and crypto quotes.

PR-029: RateFetcher Integration & Dynamic Quotes

Endpoints:
- GET /api/v1/quotes: Get quote for a plan in a specific currency
- GET /api/v1/quotes/comparison: Get quote across multiple currencies
- GET /api/v1/quotes/all: Get quotes for all plans in a currency
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.billing.pricing.quotes import QuoteService
from backend.app.billing.pricing.rates import RateFetcher
from backend.app.core.db import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/quotes", tags=["quotes"])


# ============================================================================
# RESPONSE MODELS
# ============================================================================


class QuoteResponse(BaseModel):
    """Quote for a plan in a specific currency."""

    plan_slug: str = Field(..., description="Plan slug (e.g., 'gold_monthly')")
    currency: str = Field(..., description="Currency code (e.g., 'USD')")
    amount: float = Field(..., description="Quote amount in the currency")
    base_currency: str = Field("GBP", description="Base currency for conversion")
    base_amount: float = Field(..., description="Base amount in GBP")
    rate: float = Field(..., description="FX rate applied")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "plan_slug": "gold_monthly",
                "currency": "USD",
                "amount": 38.39,
                "base_currency": "GBP",
                "base_amount": 29.99,
                "rate": 1.28,
            }
        }


class ComparisonResponse(BaseModel):
    """Quote for a plan across multiple currencies."""

    plan_slug: str = Field(..., description="Plan slug")
    base_amount: float = Field(..., description="Base amount in GBP")
    quotes: dict[str, float] = Field(..., description="Quote in each currency")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "plan_slug": "gold_monthly",
                "base_amount": 29.99,
                "quotes": {
                    "GBP": 29.99,
                    "USD": 38.39,
                    "EUR": 27.59,
                    "JPY": 5690,
                },
            }
        }


class AllQuotesResponse(BaseModel):
    """Quotes for all plans in a specific currency."""

    currency: str = Field(..., description="Currency code")
    quotes: dict[str, float] = Field(
        ..., description="Plan slug -> quote amount mapping"
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "currency": "USD",
                "quotes": {
                    "gold_monthly": 38.39,
                    "silver_monthly": 12.99,
                    "bronze_monthly": 5.99,
                },
            }
        }


class ValidationResponse(BaseModel):
    """Price validation response."""

    plan_slug: str = Field(..., description="Plan slug")
    currency: str = Field(..., description="Currency code")
    expected_amount: float = Field(..., description="Expected amount paid by user")
    current_amount: float = Field(..., description="Current quote amount")
    deviation_percent: float = Field(..., description="Deviation percentage")
    is_valid: bool = Field(..., description="Whether price is within tolerance")
    tolerance_percent: float = Field(
        ..., description="Tolerance threshold used for validation"
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "plan_slug": "gold_monthly",
                "currency": "USD",
                "expected_amount": 38.39,
                "current_amount": 38.50,
                "deviation_percent": 0.29,
                "is_valid": True,
                "tolerance_percent": 5.0,
            }
        }


# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================


async def get_quote_service(db: AsyncSession = Depends(get_db)) -> QuoteService:
    """Provide QuoteService with rate fetcher."""
    # Initialize rate fetcher (would use real aiohttp session in production)
    rate_fetcher = RateFetcher()
    return QuoteService(db, rate_fetcher)


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.get("", response_model=QuoteResponse, status_code=200)
async def get_quote(
    plan: str = Query(..., description="Plan slug (e.g., 'gold_monthly')"),
    currency: str = Query(
        "USD", description="Currency code (e.g., 'USD', 'EUR', 'GBP')"
    ),
    service: QuoteService = Depends(get_quote_service),  # noqa: B008
) -> QuoteResponse:
    """Get quote for a plan in a specific currency.

    Fetches live FX rates (with caching) and returns the plan price converted
    to the requested currency. Falls back to base rates if live rates unavailable.

    Query params:
    - plan: Plan slug (required, e.g., 'gold_monthly')
    - currency: Currency code (optional, default 'USD', e.g., 'EUR', 'GBP', 'JPY')

    Returns:
        QuoteResponse with quote amount and FX rate used

    Raises:
        HTTPException: 400 if plan or currency invalid, 500 on unexpected error

    Example:
        GET /api/v1/quotes?plan=gold_monthly&currency=USD
        Response: {
            "plan_slug": "gold_monthly",
            "currency": "USD",
            "amount": 38.39,
            "base_currency": "GBP",
            "base_amount": 29.99,
            "rate": 1.28
        }
    """
    try:
        logger.info(
            f"Getting quote for plan={plan} currency={currency}",
            extra={"plan": plan, "currency": currency},
        )

        # Get quote
        amount = await service.quote_for(plan, currency)

        # Get base amount (GBP)
        try:
            base_amount = await service.quote_for(plan, "GBP")
        except ValueError:
            logger.error(f"Failed to get base amount for plan {plan}")
            raise HTTPException(
                status_code=500, detail="Failed to calculate base amount"
            )

        # Calculate rate
        rate = amount / base_amount if base_amount > 0 else 1.0

        logger.info(
            f"Quote retrieved: {plan} {currency} {amount}",
            extra={
                "plan": plan,
                "currency": currency,
                "amount": amount,
                "rate": rate,
            },
        )

        return QuoteResponse(
            plan_slug=plan,
            currency=currency,
            amount=amount,
            base_currency="GBP",
            base_amount=base_amount,
            rate=rate,
        )

    except ValueError as e:
        logger.warning(f"Invalid quote request: {e}", extra={"error": str(e)})
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(
            f"Error getting quote: {e}",
            extra={"error": str(e), "plan": plan, "currency": currency},
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/comparison/{plan_slug}", response_model=ComparisonResponse, status_code=200
)
async def get_comparison(
    plan_slug: str,
    service: QuoteService = Depends(get_quote_service),  # noqa: B008
) -> ComparisonResponse:
    """Get quote for a plan across multiple currencies.

    Useful for displaying price comparison or multi-currency options.

    Path params:
    - plan_slug: Plan slug (e.g., 'gold_monthly')

    Returns:
        ComparisonResponse with quotes in all supported currencies

    Raises:
        HTTPException: 400 if plan invalid, 500 on error

    Example:
        GET /api/v1/quotes/comparison/gold_monthly
        Response: {
            "plan_slug": "gold_monthly",
            "base_amount": 29.99,
            "quotes": {
                "GBP": 29.99,
                "USD": 38.39,
                "EUR": 27.59,
                "JPY": 5690
            }
        }
    """
    try:
        logger.info(f"Getting comparison for plan {plan_slug}")

        # Get comparison across currencies
        comparison = await service.get_comparison(plan_slug)

        # Get base amount
        try:
            base_amount = await service.quote_for(plan_slug, "GBP")
        except ValueError:
            logger.error(f"Failed to get base amount for plan {plan_slug}")
            raise HTTPException(
                status_code=500, detail="Failed to calculate base amount"
            )

        logger.info(
            f"Comparison retrieved: {plan_slug}",
            extra={"plan": plan_slug, "currencies": len(comparison)},
        )

        return ComparisonResponse(
            plan_slug=plan_slug, base_amount=base_amount, quotes=comparison
        )

    except ValueError as e:
        logger.warning(f"Invalid comparison request: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(
            f"Error getting comparison: {e}",
            extra={"error": str(e), "plan": plan_slug},
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/all", response_model=AllQuotesResponse, status_code=200)
async def get_all_quotes(
    currency: str = Query(
        "USD", description="Currency code (e.g., 'USD', 'EUR', 'GBP')"
    ),
    service: QuoteService = Depends(get_quote_service),  # noqa: B008
) -> AllQuotesResponse:
    """Get quotes for all plans in a specific currency.

    Useful for pricing page or plan comparison table.

    Query params:
    - currency: Currency code (optional, default 'USD')

    Returns:
        AllQuotesResponse with quotes for all plans

    Raises:
        HTTPException: 400 if currency invalid, 500 on error

    Example:
        GET /api/v1/quotes/all?currency=EUR
        Response: {
            "currency": "EUR",
            "quotes": {
                "gold_monthly": 27.59,
                "silver_monthly": 11.99,
                "bronze_monthly": 5.50
            }
        }
    """
    try:
        logger.info(f"Getting all quotes for currency {currency}")

        # Get quotes for all plans
        quotes = await service.get_quotes_for_all_plans(currency)

        logger.info(
            f"All quotes retrieved for {currency}",
            extra={"currency": currency, "plans": len(quotes)},
        )

        return AllQuotesResponse(currency=currency, quotes=quotes)

    except ValueError as e:
        logger.warning(f"Invalid currency: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(
            f"Error getting all quotes: {e}",
            extra={"error": str(e), "currency": currency},
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/validate", response_model=ValidationResponse, status_code=200)
async def validate_quote(
    plan: str = Query(..., description="Plan slug"),
    currency: str = Query(
        "USD", description="Currency code (e.g., 'USD', 'EUR', 'GBP')"
    ),
    amount: float = Query(..., description="Amount user is paying (for validation)"),
    tolerance: float = Query(
        0.05, description="Tolerance threshold as decimal (default 0.05 = 5%)"
    ),
    service: QuoteService = Depends(get_quote_service),  # noqa: B008
) -> ValidationResponse:
    """Validate quote at checkout (detect stale prices).

    Checks if the user's price matches current rate (within tolerance).
    Used before processing payment to ensure user isn't paying stale price.

    Query params:
    - plan: Plan slug (required)
    - currency: Currency code (optional, default 'USD')
    - amount: Amount user is paying (required)
    - tolerance: Tolerance as decimal (optional, default 0.05 = 5%)

    Returns:
        ValidationResponse with validation result

    Raises:
        HTTPException: 400 if params invalid, 500 on error

    Example:
        POST /api/v1/quotes/validate?plan=gold_monthly&currency=USD&amount=38.50&tolerance=0.05
        Response: {
            "plan_slug": "gold_monthly",
            "currency": "USD",
            "expected_amount": 38.50,
            "current_amount": 38.39,
            "deviation_percent": 0.29,
            "is_valid": true,
            "tolerance_percent": 5.0
        }
    """
    try:
        logger.info(
            f"Validating quote: plan={plan} currency={currency} amount={amount}",
            extra={"plan": plan, "currency": currency, "amount": amount},
        )

        # Validate quote
        is_valid = await service.validate_quote(plan, currency, amount, tolerance)

        # Get current quote for response
        current_amount = await service.quote_for(plan, currency)

        # Calculate deviation
        deviation_percent = (
            abs(amount - current_amount) / current_amount * 100
            if current_amount > 0
            else 0
        )

        logger.info(
            f"Quote validation complete: valid={is_valid} deviation={deviation_percent:.2f}%",
            extra={"is_valid": is_valid, "deviation_percent": deviation_percent},
        )

        return ValidationResponse(
            plan_slug=plan,
            currency=currency,
            expected_amount=amount,
            current_amount=current_amount,
            deviation_percent=deviation_percent,
            is_valid=is_valid,
            tolerance_percent=tolerance * 100,
        )

    except ValueError as e:
        logger.warning(f"Invalid validation request: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(
            f"Error validating quote: {e}",
            extra={"error": str(e), "plan": plan, "currency": currency},
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error")
