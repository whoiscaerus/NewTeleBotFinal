"""
Time-bucketed analytics service.

Provides aggregations of trade performance by:
- Hour of day (0-23)
- Day of week (0-6, Monday-Sunday)
- Month (1-12)
- Calendar month (YYYY-MM)

Used for heatmaps, pattern identification, and performance timing analysis.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.logging import get_logger
from backend.app.trading.store.models import Trade

logger = get_logger(__name__)

try:
    from prometheus_client import Histogram

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

if PROMETHEUS_AVAILABLE:
    bucket_compute_histogram = Histogram(
        "bucket_compute_seconds",
        "Bucket computation duration in seconds",
        labelnames=["bucket_type"],
    )


class HourBucket:
    """Aggregated metrics for a specific hour of day (0-23)."""

    def __init__(self, hour: int):
        self.hour = hour  # 0-23
        self.num_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_pnl = Decimal(0)
        self.avg_pnl = Decimal(0)
        self.win_rate_percent = Decimal(0)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON response."""
        return {
            "hour": self.hour,
            "num_trades": self.num_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "total_pnl": float(self.total_pnl),
            "avg_pnl": float(self.avg_pnl),
            "win_rate_percent": float(self.win_rate_percent),
        }


class DayOfWeekBucket:
    """Aggregated metrics for a specific day of week (Monday=0, Sunday=6)."""

    DAYS = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]

    def __init__(self, day_of_week: int):
        self.day_of_week = day_of_week  # 0-6
        self.day_name = self.DAYS[day_of_week]
        self.num_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_pnl = Decimal(0)
        self.avg_pnl = Decimal(0)
        self.win_rate_percent = Decimal(0)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON response."""
        return {
            "day_of_week": self.day_of_week,
            "day_name": self.day_name,
            "num_trades": self.num_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "total_pnl": float(self.total_pnl),
            "avg_pnl": float(self.avg_pnl),
            "win_rate_percent": float(self.win_rate_percent),
        }


class MonthBucket:
    """Aggregated metrics for a specific calendar month (1-12)."""

    MONTHS = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]

    def __init__(self, month: int):
        self.month = month  # 1-12
        self.month_name = self.MONTHS[month - 1]
        self.num_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_pnl = Decimal(0)
        self.avg_pnl = Decimal(0)
        self.win_rate_percent = Decimal(0)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON response."""
        return {
            "month": self.month,
            "month_name": self.month_name,
            "num_trades": self.num_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "total_pnl": float(self.total_pnl),
            "avg_pnl": float(self.avg_pnl),
            "win_rate_percent": float(self.win_rate_percent),
        }


class CalendarMonthBucket:
    """Aggregated metrics for a specific calendar month (YYYY-MM)."""

    def __init__(self, year: int, month: int):
        self.year = year
        self.month = month
        self.calendar_month = f"{year}-{month:02d}"
        self.num_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_pnl = Decimal(0)
        self.avg_pnl = Decimal(0)
        self.win_rate_percent = Decimal(0)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON response."""
        return {
            "calendar_month": self.calendar_month,
            "num_trades": self.num_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "total_pnl": float(self.total_pnl),
            "avg_pnl": float(self.avg_pnl),
            "win_rate_percent": float(self.win_rate_percent),
        }


class TimeBucketService:
    """Service for time-based trade aggregations.

    Provides methods to group trades by:
    - Hour of day (0-23)
    - Day of week (Monday-Sunday)
    - Calendar month (1-12)
    - Year-month (YYYY-MM)

    All bucket types return 0 values for empty buckets (no null values).
    """

    def __init__(self, db_session: AsyncSession):
        """Initialize bucket service.

        Args:
            db_session: Async database session
        """
        self.db = db_session
        self.logger = logger

    async def group_by_hour(
        self,
        user_id: str,
        start_date: date,
        end_date: date,
    ) -> list[HourBucket]:
        """Group trades by hour of day (0-23).

        Returns aggregated metrics for each hour:
        - num_trades: Total trades in that hour
        - winning_trades: Trades with positive PnL
        - losing_trades: Trades with negative PnL
        - total_pnl: Sum of all PnL in that hour
        - avg_pnl: Average PnL per trade
        - win_rate_percent: (winning_trades / num_trades) * 100

        Empty hours return 0 values (not null).

        Args:
            user_id: User ID
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            List[HourBucket]: Buckets for hours 0-23, sorted by hour

        Example:
            >>> buckets = await service.group_by_hour(user_id, date(2025, 1, 1), date(2025, 1, 31))
            >>> # buckets[0] = hour 0 metrics, buckets[23] = hour 23 metrics
            >>> assert len(buckets) == 24
            >>> assert all(b.num_trades >= 0 for b in buckets)  # No nulls, all >= 0
        """
        # Initialize all 24 hour buckets
        hour_buckets = {i: HourBucket(i) for i in range(24)}

        # Query trades in date range
        query = select(Trade).where(
            and_(
                Trade.user_id == user_id,
                Trade.exit_time >= datetime.combine(start_date, datetime.min.time()),
                Trade.exit_time <= datetime.combine(end_date, datetime.max.time()),
            )
        )

        result = await self.db.execute(query)
        trades = result.scalars().all()

        # Aggregate into hour buckets
        for trade in trades:
            if not trade.exit_time:
                continue

            hour = trade.exit_time.hour
            pnl = Decimal(str(trade.profit)) if trade.profit else Decimal(0)

            bucket = hour_buckets[hour]
            bucket.num_trades += 1
            bucket.total_pnl += pnl

            if pnl > 0:
                bucket.winning_trades += 1
            elif pnl < 0:
                bucket.losing_trades += 1

        # Calculate averages and win rates
        for bucket in hour_buckets.values():
            if bucket.num_trades > 0:
                bucket.avg_pnl = bucket.total_pnl / Decimal(bucket.num_trades)
                bucket.win_rate_percent = (
                    Decimal(bucket.winning_trades)
                    / Decimal(bucket.num_trades)
                    * Decimal(100)
                )

        # Return sorted by hour
        return [hour_buckets[i] for i in range(24)]

    async def group_by_dow(
        self,
        user_id: str,
        start_date: date,
        end_date: date,
    ) -> list[DayOfWeekBucket]:
        """Group trades by day of week (Monday=0 through Sunday=6).

        Returns aggregated metrics for each day of week:
        - num_trades: Total trades on that day
        - winning_trades: Trades with positive PnL
        - losing_trades: Trades with negative PnL
        - total_pnl: Sum of all PnL on that day
        - avg_pnl: Average PnL per trade
        - win_rate_percent: (winning_trades / num_trades) * 100

        Empty days return 0 values (not null).

        Args:
            user_id: User ID
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            List[DayOfWeekBucket]: Buckets for Mon-Sun, sorted by day (0-6)

        Example:
            >>> buckets = await service.group_by_dow(user_id, date(2025, 1, 1), date(2025, 1, 31))
            >>> # buckets[0] = Monday metrics, buckets[6] = Sunday metrics
            >>> assert len(buckets) == 7
            >>> assert all(b.num_trades >= 0 for b in buckets)  # No nulls, all >= 0
        """
        # Initialize all 7 day-of-week buckets
        dow_buckets = {i: DayOfWeekBucket(i) for i in range(7)}

        # Query trades in date range
        query = select(Trade).where(
            and_(
                Trade.user_id == user_id,
                Trade.exit_time >= datetime.combine(start_date, datetime.min.time()),
                Trade.exit_time <= datetime.combine(end_date, datetime.max.time()),
            )
        )

        result = await self.db.execute(query)
        trades = result.scalars().all()

        # Aggregate into day-of-week buckets
        # Python weekday: 0=Monday, 6=Sunday (matches our bucket indexing)
        for trade in trades:
            if not trade.exit_time:
                continue

            dow = trade.exit_time.weekday()  # 0=Monday, 6=Sunday
            pnl = Decimal(str(trade.profit)) if trade.profit else Decimal(0)

            bucket = dow_buckets[dow]
            bucket.num_trades += 1
            bucket.total_pnl += pnl

            if pnl > 0:
                bucket.winning_trades += 1
            elif pnl < 0:
                bucket.losing_trades += 1

        # Calculate averages and win rates
        for bucket in dow_buckets.values():
            if bucket.num_trades > 0:
                bucket.avg_pnl = bucket.total_pnl / Decimal(bucket.num_trades)
                bucket.win_rate_percent = (
                    Decimal(bucket.winning_trades)
                    / Decimal(bucket.num_trades)
                    * Decimal(100)
                )

        # Return sorted by day (0=Monday, 6=Sunday)
        return [dow_buckets[i] for i in range(7)]

    async def group_by_month(
        self,
        user_id: str,
        start_date: date,
        end_date: date,
    ) -> list[MonthBucket]:
        """Group trades by calendar month (1-12).

        Returns aggregated metrics for each month (regardless of year):
        - num_trades: Total trades in that month (across all years)
        - winning_trades: Trades with positive PnL
        - losing_trades: Trades with negative PnL
        - total_pnl: Sum of all PnL in that month
        - avg_pnl: Average PnL per trade
        - win_rate_percent: (winning_trades / num_trades) * 100

        Empty months return 0 values (not null).

        Args:
            user_id: User ID
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            List[MonthBucket]: Buckets for months 1-12, sorted by month

        Example:
            >>> buckets = await service.group_by_month(user_id, date(2024, 1, 1), date(2025, 12, 31))
            >>> # buckets[0] = January metrics (all years), buckets[11] = December metrics (all years)
            >>> assert len(buckets) == 12
            >>> assert all(b.num_trades >= 0 for b in buckets)  # No nulls, all >= 0
        """
        # Initialize all 12 month buckets
        month_buckets = {i: MonthBucket(i) for i in range(1, 13)}

        # Query trades in date range
        query = select(Trade).where(
            and_(
                Trade.user_id == user_id,
                Trade.exit_time >= datetime.combine(start_date, datetime.min.time()),
                Trade.exit_time <= datetime.combine(end_date, datetime.max.time()),
            )
        )

        result = await self.db.execute(query)
        trades = result.scalars().all()

        # Aggregate into month buckets (by month number, ignoring year)
        for trade in trades:
            if not trade.exit_time:
                continue

            month = trade.exit_time.month  # 1-12
            pnl = Decimal(str(trade.profit)) if trade.profit else Decimal(0)

            bucket = month_buckets[month]
            bucket.num_trades += 1
            bucket.total_pnl += pnl

            if pnl > 0:
                bucket.winning_trades += 1
            elif pnl < 0:
                bucket.losing_trades += 1

        # Calculate averages and win rates
        for bucket in month_buckets.values():
            if bucket.num_trades > 0:
                bucket.avg_pnl = bucket.total_pnl / Decimal(bucket.num_trades)
                bucket.win_rate_percent = (
                    Decimal(bucket.winning_trades)
                    / Decimal(bucket.num_trades)
                    * Decimal(100)
                )

        # Return sorted by month (1-12)
        return [month_buckets[i] for i in range(1, 13)]

    async def group_by_calendar_month(
        self,
        user_id: str,
        start_date: date,
        end_date: date,
    ) -> list[CalendarMonthBucket]:
        """Group trades by specific calendar month (YYYY-MM).

        Returns aggregated metrics for each unique year-month in the range:
        - num_trades: Total trades in that month
        - winning_trades: Trades with positive PnL
        - losing_trades: Trades with negative PnL
        - total_pnl: Sum of all PnL in that month
        - avg_pnl: Average PnL per trade
        - win_rate_percent: (winning_trades / num_trades) * 100

        Empty months return 0 values (not null).

        Args:
            user_id: User ID
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            List[CalendarMonthBucket]: Buckets for each year-month, sorted chronologically

        Example:
            >>> buckets = await service.group_by_calendar_month(user_id, date(2025, 1, 1), date(2025, 3, 31))
            >>> # buckets[0] = 2025-01 metrics, buckets[1] = 2025-02 metrics, etc.
            >>> assert all(b.num_trades >= 0 for b in buckets)  # No nulls, all >= 0
        """
        # Query trades in date range
        query = select(Trade).where(
            and_(
                Trade.user_id == user_id,
                Trade.exit_time >= datetime.combine(start_date, datetime.min.time()),
                Trade.exit_time <= datetime.combine(end_date, datetime.max.time()),
            )
        )

        result = await self.db.execute(query)
        trades = result.scalars().all()

        # Build set of calendar months in range
        calendar_buckets: dict[tuple[int, int], CalendarMonthBucket] = {}
        current_date = start_date
        while current_date <= end_date:
            year = current_date.year
            month = current_date.month
            key = (year, month)
            if key not in calendar_buckets:
                calendar_buckets[key] = CalendarMonthBucket(year, month)
            # Move to first day of next month
            if month == 12:
                current_date = date(year + 1, 1, 1)
            else:
                current_date = date(year, month + 1, 1)

        # Aggregate trades into calendar month buckets
        for trade in trades:
            if not trade.exit_time:
                continue

            year = trade.exit_time.year
            month = trade.exit_time.month
            key = (year, month)

            if key not in calendar_buckets:
                calendar_buckets[key] = CalendarMonthBucket(year, month)

            bucket = calendar_buckets[key]
            pnl = Decimal(str(trade.profit)) if trade.profit else Decimal(0)

            bucket.num_trades += 1
            bucket.total_pnl += pnl

            if pnl > 0:
                bucket.winning_trades += 1
            elif pnl < 0:
                bucket.losing_trades += 1

        # Calculate averages and win rates
        for bucket in calendar_buckets.values():
            if bucket.num_trades > 0:
                bucket.avg_pnl = bucket.total_pnl / Decimal(bucket.num_trades)
                bucket.win_rate_percent = (
                    Decimal(bucket.winning_trades)
                    / Decimal(bucket.num_trades)
                    * Decimal(100)
                )

        # Return sorted chronologically
        sorted_buckets = sorted(
            calendar_buckets.items(), key=lambda x: (x[0][0], x[0][1])
        )
        return [bucket for _, bucket in sorted_buckets]
