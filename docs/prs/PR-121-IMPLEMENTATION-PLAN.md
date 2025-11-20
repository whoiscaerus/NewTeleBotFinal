# PR-121 Implementation Plan: TradingView Charts

## 1. Overview
Integrate TradingView Lightweight Charts to visualize trading signals on the frontend, replacing raw text data.

## 2. Technical Specification

### Files to Create/Modify
- `frontend/src/components/charts/SignalChart.tsx`: Chart component.
- `frontend/src/app/dashboard/page.tsx`: Integrate chart.
- `frontend/package.json`: Add `lightweight-charts`.

### Logic
1.  **Data**: Fetch OHLC data for the signal's instrument (e.g., XAUUSD).
2.  **Visualization**:
    - Render Candle series.
    - Render "Entry" line (Green).
    - Render "Stop Loss" line (Red).
    - Render "Take Profit" line (Blue).

### Dependencies
- `lightweight-charts` (npm).

## 3. Acceptance Criteria
- [ ] Chart renders correct OHLC data.
- [ ] Entry/SL/TP lines appear at correct price levels.
- [ ] Chart is responsive (mobile friendly).
