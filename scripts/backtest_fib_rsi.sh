#!/bin/bash
# Backtest Fib/RSI strategy with historical data
#
# Usage:
#   ./scripts/backtest_fib_rsi.sh data/GOLD_15M.csv 2024-01-01 2024-12-31
#
# Arguments:
#   $1: Path to CSV data file
#   $2: Start date (YYYY-MM-DD)
#   $3: End date (YYYY-MM-DD)
#
# Example:
#   ./scripts/backtest_fib_rsi.sh data/GOLD_15M.csv 2024-01-01 2024-12-31

set -e

# Check arguments
if [ $# -ne 3 ]; then
    echo "Usage: $0 <csv_file> <start_date> <end_date>"
    echo "Example: $0 data/GOLD_15M.csv 2024-01-01 2024-12-31"
    exit 1
fi

CSV_FILE=$1
START_DATE=$2
END_DATE=$3

# Validate CSV exists
if [ ! -f "$CSV_FILE" ]; then
    echo "Error: CSV file not found: $CSV_FILE"
    exit 1
fi

# Run backtest
echo "Running Fib/RSI backtest..."
echo "Data: $CSV_FILE"
echo "Period: $START_DATE to $END_DATE"
echo ""

python -m backend.scripts.run_backtest \
    --strategy fib_rsi \
    --data-source csv \
    --csv-file "$CSV_FILE" \
    --symbol GOLD \
    --start "$START_DATE" \
    --end "$END_DATE" \
    --initial-balance 10000 \
    --position-size 0.1 \
    --slippage-pips 2.0 \
    --output-html results/backtest_fib_rsi.html \
    --output-csv results/backtest_fib_rsi_trades.csv \
    --output-json results/backtest_fib_rsi_summary.json

echo ""
echo "Backtest complete! Results saved to results/"
echo "  - HTML report: results/backtest_fib_rsi.html"
echo "  - Trades CSV: results/backtest_fib_rsi_trades.csv"
echo "  - Summary JSON: results/backtest_fib_rsi_summary.json"
