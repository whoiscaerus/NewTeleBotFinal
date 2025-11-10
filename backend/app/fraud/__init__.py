"""Fraud detection module for AI-powered anomaly detection."""

from backend.app.fraud.detectors import (
    detect_latency_spike,
    detect_out_of_band_fill,
    detect_slippage_zscore,
    scan_recent_trades,
)
from backend.app.fraud.models import AnomalyEvent, AnomalySeverity, AnomalyType
from backend.app.fraud.routes import router

__all__ = [
    "AnomalyEvent",
    "AnomalyType",
    "AnomalySeverity",
    "detect_slippage_zscore",
    "detect_latency_spike",
    "detect_out_of_band_fill",
    "scan_recent_trades",
    "router",
]
