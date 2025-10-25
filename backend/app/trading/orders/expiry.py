"""Order expiry time calculation."""

from datetime import datetime, timedelta


def compute_expiry(now: datetime, expiry_hours: int = 100) -> datetime:
    """
    Calculate order expiry time as now + expiry_hours.

    Args:
        now: Current datetime (typically datetime.utcnow())
        expiry_hours: Number of hours until expiry (default 100)

    Returns:
        Expiry datetime (now + expiry_hours)

    Raises:
        ValueError: If expiry_hours is negative
        TypeError: If now is not a datetime

    Examples:
        >>> from datetime import datetime
        >>> now = datetime(2025, 10, 24, 12, 0, 0)
        >>> expiry = compute_expiry(now, expiry_hours=100)
        >>> expiry
        datetime.datetime(2025, 10, 28, 16, 0, 0)
        >>> (expiry - now).total_seconds() / 3600
        100.0

        >>> # Default 100 hours
        >>> expiry = compute_expiry(now)
        >>> (expiry - now).total_seconds() / 3600
        100.0

        >>> # Zero hours (edge case)
        >>> expiry = compute_expiry(now, 0)
        >>> expiry == now
        True
    """
    # Type validation
    if not isinstance(now, datetime):
        raise TypeError(f"now must be datetime, got {type(now)}")

    # Value validation
    if expiry_hours < 0:
        raise ValueError(f"expiry_hours must be >= 0, got {expiry_hours}")

    # Calculate expiry
    expiry = now + timedelta(hours=expiry_hours)

    return expiry
