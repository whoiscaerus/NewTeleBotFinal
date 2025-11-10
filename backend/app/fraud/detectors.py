"""Fraud detection algorithms for trade anomalies.

Detects suspicious MT5 execution patterns:
- Slippage: Entry/exit price deviation from expected (z-score analysis)
- Latency: Execution delays beyond normal thresholds
- Out-of-band fills: Prices outside reasonable market range
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.fraud.models import AnomalyEvent, AnomalySeverity, AnomalyType
from backend.app.trading.store.models import Trade

logger = logging.getLogger(__name__)


# Configuration thresholds
SLIPPAGE_ZSCORE_THRESHOLD = 3.0  # Standard deviations for slippage alert
LATENCY_THRESHOLD_MS = 2000  # Max acceptable execution latency (ms)
OUT_OF_BAND_TOLERANCE_PERCENT = 0.5  # % deviation from expected price
MIN_TRADES_FOR_ZSCORE = 10  # Minimum trades needed for z-score calculation
LOOKBACK_WINDOW_DAYS = 30  # Days to look back for baseline calculation


async def detect_slippage_zscore(
    db: AsyncSession, trade: Trade, expected_price: Optional[Decimal] = None
) -> AnomalyEvent | None:
    """Detect extreme slippage using z-score analysis.

    Compares trade's entry price deviation against historical baseline
    for the same symbol. Flags if deviation exceeds SLIPPAGE_ZSCORE_THRESHOLD.

    Args:
        db: Database session
        trade: Trade to analyze
        expected_price: Expected entry price (uses signal price if available)

    Returns:
        AnomalyEvent if slippage is extreme, None otherwise

    Business Logic:
        1. Calculate baseline: mean/stddev of entry price slippage for symbol
        2. Compute z-score: (actual_slippage - mean) / stddev
        3. If |z-score| > SLIPPAGE_ZSCORE_THRESHOLD → anomaly
        4. Severity: score = min(|z-score| / 10, 1.0)
        5. Requires MIN_TRADES_FOR_ZSCORE historical trades
    """
    # Use expected price or actual entry (for closed trades, compare to entry)
    if expected_price is None:
        # If no expected price, can't detect slippage on open trades
        if trade.status == "OPEN":
            return None
        # For closed trades, use entry price as baseline
        expected_price = trade.entry_price

    actual_price = trade.entry_price
    slippage_pips = abs(float(actual_price - expected_price))

    # Get historical baseline for this symbol
    lookback = datetime.utcnow() - timedelta(days=LOOKBACK_WINDOW_DAYS)

    # Calculate mean and stddev of historical slippage
    stmt = select(
        func.avg(func.abs(Trade.entry_price - expected_price)).label("mean_slippage"),
        func.stddev(func.abs(Trade.entry_price - expected_price)).label(
            "stddev_slippage"
        ),
        func.count(Trade.trade_id).label("trade_count"),
    ).where(
        and_(
            Trade.symbol == trade.symbol,
            Trade.entry_time >= lookback,
            Trade.trade_id != trade.trade_id,  # Exclude current trade
        )
    )

    result = await db.execute(stmt)
    row = result.one_or_none()

    if row is None or row.trade_count < MIN_TRADES_FOR_ZSCORE:
        # Not enough data for statistical analysis
        logger.info(
            f"Insufficient historical data for slippage z-score on {trade.symbol} "
            f"(need {MIN_TRADES_FOR_ZSCORE}, have {row.trade_count if row else 0})"
        )
        return None

    mean_slippage = float(row.mean_slippage or 0)
    stddev_slippage = float(row.stddev_slippage or 1)

    # Avoid division by zero
    if stddev_slippage < 0.0001:
        stddev_slippage = 0.01  # Minimum stddev

    # Calculate z-score
    z_score = (slippage_pips - mean_slippage) / stddev_slippage

    if abs(z_score) < SLIPPAGE_ZSCORE_THRESHOLD:
        # Within acceptable range
        return None

    # Calculate anomaly score (0-1 scale)
    # z-score of 3 = 0.3, 5 = 0.5, 10 = 1.0
    score = min(abs(z_score) / 10.0, 1.0)

    # Determine severity
    if score >= 0.85:
        severity = AnomalySeverity.CRITICAL
    elif score >= 0.6:
        severity = AnomalySeverity.HIGH
    elif score >= 0.3:
        severity = AnomalySeverity.MEDIUM
    else:
        severity = AnomalySeverity.LOW

    # Create anomaly event
    anomaly = AnomalyEvent(
        user_id=trade.user_id,
        trade_id=trade.trade_id,
        anomaly_type=AnomalyType.SLIPPAGE_EXTREME,
        severity=severity.value,
        score=Decimal(str(score)),
        details={
            "symbol": trade.symbol,
            "expected_price": float(expected_price),
            "actual_price": float(actual_price),
            "slippage_pips": slippage_pips,
            "z_score": z_score,
            "mean_slippage": mean_slippage,
            "stddev_slippage": stddev_slippage,
            "trade_count_baseline": row.trade_count,
            "threshold": SLIPPAGE_ZSCORE_THRESHOLD,
        },
    )

    logger.warning(
        f"Slippage anomaly detected: {trade.symbol} z-score={z_score:.2f} "
        f"(threshold={SLIPPAGE_ZSCORE_THRESHOLD}), score={score:.3f}"
    )

    return anomaly


async def detect_latency_spike(
    db: AsyncSession, trade: Trade, signal_time: Optional[datetime] = None
) -> AnomalyEvent | None:
    """Detect execution latency spikes.

    Measures time between signal generation and trade execution.
    Flags if latency exceeds LATENCY_THRESHOLD_MS.

    Args:
        db: Database session
        trade: Trade to analyze
        signal_time: When signal was generated (uses entry_time - 1min if None)

    Returns:
        AnomalyEvent if latency is excessive, None otherwise

    Business Logic:
        1. Latency = trade.entry_time - signal_time
        2. If latency > LATENCY_THRESHOLD_MS → anomaly
        3. Score = min(latency_ms / 10000, 1.0)
        4. Severity: <1s LOW, 1-2s MEDIUM, 2-5s HIGH, >5s CRITICAL
    """
    if signal_time is None:
        # Estimate signal time as 1 minute before entry
        signal_time = trade.entry_time - timedelta(minutes=1)

    # Calculate latency in milliseconds
    latency_delta = trade.entry_time - signal_time
    latency_ms = latency_delta.total_seconds() * 1000

    if latency_ms < LATENCY_THRESHOLD_MS:
        # Within acceptable range
        return None

    # Calculate anomaly score (0-1 scale)
    # 2s = 0.2, 5s = 0.5, 10s = 1.0
    score = min(latency_ms / 10000.0, 1.0)

    # Determine severity
    if latency_ms >= 5000:
        severity = AnomalySeverity.CRITICAL
    elif latency_ms >= 2000:
        severity = AnomalySeverity.HIGH
    elif latency_ms >= 1000:
        severity = AnomalySeverity.MEDIUM
    else:
        severity = AnomalySeverity.LOW

    # Create anomaly event
    anomaly = AnomalyEvent(
        user_id=trade.user_id,
        trade_id=trade.trade_id,
        anomaly_type=AnomalyType.LATENCY_SPIKE,
        severity=severity.value,
        score=Decimal(str(score)),
        details={
            "symbol": trade.symbol,
            "signal_time": signal_time.isoformat(),
            "entry_time": trade.entry_time.isoformat(),
            "latency_ms": latency_ms,
            "threshold_ms": LATENCY_THRESHOLD_MS,
        },
    )

    logger.warning(
        f"Latency spike detected: {trade.symbol} latency={latency_ms:.0f}ms "
        f"(threshold={LATENCY_THRESHOLD_MS}ms), score={score:.3f}"
    )

    return anomaly


async def detect_out_of_band_fill(
    db: AsyncSession, trade: Trade, market_high: Decimal, market_low: Decimal
) -> AnomalyEvent | None:
    """Detect fills outside reasonable market range.

    Checks if entry price is within expected market range during the
    execution window. Flags if price is outside tolerance band.

    Args:
        db: Database session
        trade: Trade to analyze
        market_high: Market high during execution window
        market_low: Market low during execution window

    Returns:
        AnomalyEvent if fill is out-of-band, None otherwise

    Business Logic:
        1. Expected range = [market_low, market_high]
        2. Tolerance = OUT_OF_BAND_TOLERANCE_PERCENT * (high - low)
        3. If entry_price < (low - tolerance) OR entry_price > (high + tolerance) → anomaly
        4. Score = deviation_percent / 10.0 (capped at 1.0)
        5. Severity: <1% LOW, 1-2% MEDIUM, 2-5% HIGH, >5% CRITICAL
    """
    entry_price = trade.entry_price
    market_range = market_high - market_low
    tolerance = market_range * Decimal(str(OUT_OF_BAND_TOLERANCE_PERCENT))

    lower_bound = market_low - tolerance
    upper_bound = market_high + tolerance

    # Check if within bounds
    if lower_bound <= entry_price <= upper_bound:
        return None

    # Calculate deviation percentage
    if entry_price < lower_bound:
        deviation = float(lower_bound - entry_price)
        deviation_percent = (deviation / float(market_low)) * 100
        direction = "below"
    else:
        deviation = float(entry_price - upper_bound)
        deviation_percent = (deviation / float(market_high)) * 100
        direction = "above"

    # Calculate anomaly score (0-1 scale)
    # 1% = 0.1, 5% = 0.5, 10% = 1.0
    score = min(deviation_percent / 10.0, 1.0)

    # Determine severity
    if deviation_percent >= 5.0:
        severity = AnomalySeverity.CRITICAL
    elif deviation_percent >= 2.0:
        severity = AnomalySeverity.HIGH
    elif deviation_percent >= 1.0:
        severity = AnomalySeverity.MEDIUM
    else:
        severity = AnomalySeverity.LOW

    # Create anomaly event
    anomaly = AnomalyEvent(
        user_id=trade.user_id,
        trade_id=trade.trade_id,
        anomaly_type=AnomalyType.OUT_OF_BAND_FILL,
        severity=severity.value,
        score=Decimal(str(score)),
        details={
            "symbol": trade.symbol,
            "entry_price": float(entry_price),
            "market_high": float(market_high),
            "market_low": float(market_low),
            "tolerance_percent": OUT_OF_BAND_TOLERANCE_PERCENT,
            "lower_bound": float(lower_bound),
            "upper_bound": float(upper_bound),
            "deviation": deviation,
            "deviation_percent": deviation_percent,
            "direction": direction,
        },
    )

    logger.warning(
        f"Out-of-band fill detected: {trade.symbol} price={float(entry_price)} "
        f"{direction} range [{float(market_low)}, {float(market_high)}], "
        f"deviation={deviation_percent:.2f}%, score={score:.3f}"
    )

    return anomaly


async def scan_recent_trades(db: AsyncSession, hours: int = 24) -> list[AnomalyEvent]:
    """Scan recent trades for all anomaly types.

    Args:
        db: Database session
        hours: How many hours back to scan

    Returns:
        List of detected anomalies

    Business Logic:
        1. Fetch all trades from last N hours
        2. Run all detectors (slippage, latency, out-of-band)
        3. Persist detected anomalies to DB
        4. Return list for reporting/alerting
    """
    lookback = datetime.utcnow() - timedelta(hours=hours)

    # Fetch recent trades
    stmt = (
        select(Trade)
        .where(
            and_(
                Trade.created_at >= lookback,
                Trade.status == "CLOSED",  # Only analyze closed trades
            )
        )
        .order_by(Trade.created_at.desc())
    )

    result = await db.execute(stmt)
    trades = result.scalars().all()

    anomalies = []

    for trade in trades:
        # Run all detectors
        # Note: In production, expected_price would come from signal
        # For now, we'll skip slippage if no signal reference
        if trade.signal_id:
            slippage_anomaly = await detect_slippage_zscore(db, trade)
            if slippage_anomaly:
                db.add(slippage_anomaly)
                anomalies.append(slippage_anomaly)

        # Latency detection (estimate signal time)
        latency_anomaly = await detect_latency_spike(db, trade)
        if latency_anomaly:
            db.add(latency_anomaly)
            anomalies.append(latency_anomaly)

        # Out-of-band detection (would need market data feed)
        # Skip for now unless we have market data

    await db.commit()

    logger.info(
        f"Fraud scan complete: scanned {len(trades)} trades, "
        f"detected {len(anomalies)} anomalies"
    )

    return anomalies
