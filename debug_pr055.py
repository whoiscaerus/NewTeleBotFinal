"""Quick debug test for PR-055"""

import asyncio
from datetime import date
from decimal import Decimal

from backend.app.analytics.equity import EquitySeries


async def test_debug():
    """Debug the export endpoint."""
    mock_series = EquitySeries(
        dates=[date(2025, 1, 20), date(2025, 1, 21), date(2025, 1, 22)],
        equity=[Decimal("10000"), Decimal("10500"), Decimal("10200")],
        peak_equity=[Decimal("10000"), Decimal("10500"), Decimal("10500")],
        cumulative_pnl=[Decimal("0"), Decimal("500"), Decimal("200")],
    )

    print("Points:", mock_series.points)
    print("Initial equity:", mock_series.initial_equity)
    print("Final equity:", mock_series.final_equity)
    print("Total return %:", mock_series.total_return_percent)
    print("Max drawdown %:", mock_series.max_drawdown_percent)
    print("Days in period:", mock_series.days_in_period)


if __name__ == "__main__":
    asyncio.run(test_debug())
