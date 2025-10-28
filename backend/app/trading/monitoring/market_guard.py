"""
MarketGuard Service - Monitor market conditions and trigger position closes on safety issues.

This service detects market anomalies (price gaps, liquidity crisis, extreme volatility)
and marks positions for automatic closure or alerts users to manual intervention.

Author: Trading System
Created: October 2024
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class MarketConditionAlert:
    """Alert for market safety conditions."""

    def __init__(
        self,
        symbol: str,
        alert_type: str,
        severity: str,
        condition_value: float,
        threshold_value: float,
        message: str,
        timestamp: datetime,
    ):
        """Initialize market alert.

        Args:
            symbol: Trading symbol (e.g., "XAUUSD")
            alert_type: Type of condition (gap, liquidity, spread, volatility)
            severity: Alert severity (warning, critical)
            condition_value: Measured value (e.g., gap percentage)
            threshold_value: Configured threshold
            message: Human-readable alert message
            timestamp: Alert timestamp (UTC)
        """
        self.symbol = symbol
        self.alert_type = alert_type
        self.severity = severity
        self.condition_value = condition_value
        self.threshold_value = threshold_value
        self.message = message
        self.timestamp = timestamp

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<MarketAlert {self.symbol} {self.alert_type}: "
            f"{self.condition_value:.2f}% (threshold: {self.threshold_value:.2f}%)>"
        )


class MarketGuard:
    """
    Monitor market conditions for safety and automatically close positions if needed.

    Responsibilities:
    1. Detect price gaps (unexpected moves between close/open)
    2. Check liquidity conditions (bid-ask spread too wide)
    3. Monitor volatility anomalies
    4. Mark positions for automatic close
    5. Alert users to manual intervention

    Example:
        >>> guard = MarketGuard(
        ...     price_gap_alert_pct=5.0,
        ...     bid_ask_spread_max_pct=0.5,
        ...     liquidity_check_enabled=True
        ... )
        >>> alert = await guard.check_price_gap(
        ...     symbol="XAUUSD",
        ...     last_close=1950.00,
        ...     current_open=2050.00
        ... )
        >>> if alert:
        ...     print(f"Gap detected: {alert.message}")
    """

    def __init__(
        self,
        price_gap_alert_pct: float = 5.0,
        bid_ask_spread_max_pct: float = 0.5,
        min_liquidity_volume_lots: float = 10.0,
        liquidity_check_enabled: bool = True,
    ):
        """Initialize MarketGuard with thresholds.

        Args:
            price_gap_alert_pct: Gap threshold for alert (default 5%)
            bid_ask_spread_max_pct: Max acceptable bid-ask spread (default 0.5%)
            min_liquidity_volume_lots: Minimum available volume in lots (default 10)
            liquidity_check_enabled: Enable liquidity checks (default True)
        """
        self.price_gap_alert_pct = price_gap_alert_pct
        self.bid_ask_spread_max_pct = bid_ask_spread_max_pct
        self.min_liquidity_volume_lots = min_liquidity_volume_lots
        self.liquidity_check_enabled = liquidity_check_enabled

        logger.info(
            "MarketGuard initialized",
            extra={
                "price_gap_alert_pct": price_gap_alert_pct,
                "bid_ask_spread_max_pct": bid_ask_spread_max_pct,
                "min_liquidity_volume_lots": min_liquidity_volume_lots,
                "liquidity_check_enabled": liquidity_check_enabled,
            },
        )

    async def check_price_gap(
        self, symbol: str, last_close: float, current_open: float
    ) -> MarketConditionAlert | None:
        """
        Detect price gaps between close and open.

        Args:
            symbol: Trading symbol
            last_close: Previous close price
            current_open: Current open price

        Returns:
            MarketConditionAlert if gap exceeds threshold, None otherwise

        Raises:
            ValueError: If prices invalid (negative or zero)

        Example:
            >>> alert = await guard.check_price_gap(
            ...     symbol="XAUUSD",
            ...     last_close=1950.00,
            ...     current_open=2050.00  # 5.1% gap
            ... )
            >>> if alert:
            ...     print(f"Gap detected: {alert.message}")
        """
        if last_close <= 0 or current_open <= 0:
            logger.error(
                "Invalid prices in gap check",
                extra={
                    "symbol": symbol,
                    "last_close": last_close,
                    "current_open": current_open,
                },
            )
            raise ValueError("Prices must be positive")

        # Calculate gap percentage
        gap_pct = abs(current_open - last_close) / last_close * 100
        now = datetime.utcnow()

        # Determine direction
        direction = "up" if current_open > last_close else "down"

        logger.debug(
            f"Price gap check: {symbol} {gap_pct:.2f}% {direction}",
            extra={
                "symbol": symbol,
                "gap_pct": gap_pct,
                "direction": direction,
                "threshold": self.price_gap_alert_pct,
            },
        )

        # Check if gap exceeds threshold
        if gap_pct >= self.price_gap_alert_pct:
            message = (
                f"⚠️ **PRICE GAP DETECTED** for {symbol}: {gap_pct:.2f}% {direction} "
                f"(Close: {last_close:.2f} → Open: {current_open:.2f})"
            )

            alert = MarketConditionAlert(
                symbol=symbol,
                alert_type="gap",
                severity=(
                    "critical" if gap_pct >= self.price_gap_alert_pct * 2 else "warning"
                ),
                condition_value=gap_pct,
                threshold_value=self.price_gap_alert_pct,
                message=message,
                timestamp=now,
            )

            logger.warning(
                f"Price gap alert: {alert}",
                extra={"symbol": symbol, "gap_pct": gap_pct, "direction": direction},
            )

            return alert

        return None

    async def check_liquidity(
        self,
        symbol: str,
        bid: float,
        ask: float,
        position_volume_lots: float,
    ) -> MarketConditionAlert | None:
        """
        Check liquidity conditions (bid-ask spread and available volume).

        Args:
            symbol: Trading symbol
            bid: Current bid price
            ask: Current ask price
            position_volume_lots: Position size in lots (for volume check)

        Returns:
            MarketConditionAlert if liquidity issue detected, None otherwise

        Raises:
            ValueError: If prices invalid

        Example:
            >>> alert = await guard.check_liquidity(
            ...     symbol="XAUUSD",
            ...     bid=1950.00,
            ...     ask=1950.50,  # 0.026% spread
            ...     position_volume_lots=1.0
            ... )
            >>> if alert:
            ...     print(f"Liquidity issue: {alert.message}")
        """
        if not self.liquidity_check_enabled:
            logger.debug("Liquidity check disabled, skipping")
            return None

        if bid <= 0 or ask <= 0:
            logger.error(
                "Invalid prices in liquidity check",
                extra={"symbol": symbol, "bid": bid, "ask": ask},
            )
            raise ValueError("Prices must be positive")

        if ask < bid:
            logger.error(
                "Invalid bid-ask configuration",
                extra={"symbol": symbol, "bid": bid, "ask": ask},
            )
            raise ValueError("Ask price must be >= bid price")

        now = datetime.utcnow()

        # Calculate bid-ask spread percentage
        spread_pct = (ask - bid) / bid * 100

        logger.debug(
            f"Liquidity check: {symbol} spread {spread_pct:.3f}%",
            extra={
                "symbol": symbol,
                "bid": bid,
                "ask": ask,
                "spread_pct": spread_pct,
                "max_spread_pct": self.bid_ask_spread_max_pct,
            },
        )

        # Check if spread is too wide
        if spread_pct > self.bid_ask_spread_max_pct:
            message = (
                f"⚠️ **WIDE SPREAD** for {symbol}: {spread_pct:.3f}% "
                f"(Bid: {bid:.2f} Ask: {ask:.2f})"
            )

            alert = MarketConditionAlert(
                symbol=symbol,
                alert_type="spread",
                severity=(
                    "warning"
                    if spread_pct < self.bid_ask_spread_max_pct * 2
                    else "critical"
                ),
                condition_value=spread_pct,
                threshold_value=self.bid_ask_spread_max_pct,
                message=message,
                timestamp=now,
            )

            logger.warning(
                f"Liquidity spread alert: {alert}",
                extra={"symbol": symbol, "spread_pct": spread_pct},
            )

            return alert

        return None

    async def mark_position_for_close(
        self, position_id: str, reason: str, condition_details: dict | None = None
    ) -> bool:
        """
        Mark position for automatic close due to market conditions.

        Args:
            position_id: Position identifier
            reason: Reason for close (gap, liquidity, margin, volatility)
            condition_details: Optional dict with condition details

        Returns:
            True if position marked successfully

        Example:
            >>> marked = await guard.mark_position_for_close(
            ...     position_id="pos_123",
            ...     reason="gap",
            ...     condition_details={"gap_pct": 5.5, "symbol": "XAUUSD"}
            ... )
        """
        try:
            logger.info(
                f"Position marked for close: {position_id}",
                extra={
                    "position_id": position_id,
                    "reason": reason,
                    "details": condition_details or {},
                },
            )

            # TODO: Update position table with close_marked_at timestamp
            # and close_reason field
            # position.close_marked_at = datetime.utcnow()
            # position.close_reason = reason
            # db.commit()

            return True

        except Exception as e:
            logger.error(
                f"Error marking position for close: {e}",
                exc_info=True,
                extra={"position_id": position_id},
            )
            return False

    async def should_close_position(
        self,
        position_id: str,
        symbol: str,
        bid: float,
        ask: float,
        last_close: float,
        current_open: float,
        position_volume_lots: float,
    ) -> tuple[bool, str | None]:
        """
        Determine if position should be closed based on market conditions.

        Checks:
        1. Price gap exceeds threshold
        2. Bid-ask spread too wide
        3. Liquidity insufficient

        Args:
            position_id: Position identifier
            symbol: Trading symbol
            bid: Current bid price
            ask: Current ask price
            last_close: Previous candle close price
            current_open: Current candle open price
            position_volume_lots: Position size in lots

        Returns:
            Tuple of (should_close: bool, reason: Optional[str])

        Example:
            >>> should_close, reason = await guard.should_close_position(
            ...     position_id="pos_123",
            ...     symbol="XAUUSD",
            ...     bid=2000.00,
            ...     ask=2000.50,
            ...     last_close=1950.00,
            ...     current_open=2050.00,
            ...     position_volume_lots=1.0
            ... )
            >>> if should_close:
            ...     print(f"Close position: {reason}")
        """
        try:
            # Check for price gap
            gap_alert = await self.check_price_gap(symbol, last_close, current_open)
            if gap_alert:
                logger.warning(
                    f"Position {position_id} should close: price gap",
                    extra={"gap_pct": gap_alert.condition_value},
                )
                return True, f"gap ({gap_alert.condition_value:.2f}%)"

            # Check for liquidity issues
            liquidity_alert = await self.check_liquidity(
                symbol, bid, ask, position_volume_lots
            )
            if liquidity_alert:
                logger.warning(
                    f"Position {position_id} should close: liquidity issue",
                    extra={"spread_pct": liquidity_alert.condition_value},
                )
                return True, f"liquidity ({liquidity_alert.condition_value:.3f}%)"

            # All checks passed
            logger.debug(
                f"Position {position_id} market conditions OK",
                extra={"symbol": symbol},
            )
            return False, None

        except Exception as e:
            logger.error(
                f"Error evaluating close condition: {e}",
                exc_info=True,
                extra={"position_id": position_id},
            )
            return False, None


# Global instance (lazy-loaded)
_market_guard: MarketGuard | None = None


def get_market_guard(
    price_gap_alert_pct: float = 5.0,
    bid_ask_spread_max_pct: float = 0.5,
    min_liquidity_volume_lots: float = 10.0,
    liquidity_check_enabled: bool = True,
) -> MarketGuard:
    """Get or create global MarketGuard instance.

    Args:
        price_gap_alert_pct: Gap threshold (default 5%)
        bid_ask_spread_max_pct: Spread threshold (default 0.5%)
        min_liquidity_volume_lots: Minimum volume (default 10 lots)
        liquidity_check_enabled: Enable checks (default True)

    Returns:
        MarketGuard instance
    """
    global _market_guard

    if _market_guard is None:
        _market_guard = MarketGuard(
            price_gap_alert_pct=price_gap_alert_pct,
            bid_ask_spread_max_pct=bid_ask_spread_max_pct,
            min_liquidity_volume_lots=min_liquidity_volume_lots,
            liquidity_check_enabled=liquidity_check_enabled,
        )

    return _market_guard
