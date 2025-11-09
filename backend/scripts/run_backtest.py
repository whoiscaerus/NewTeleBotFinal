"""CLI runner for backtesting framework.

Provides command-line interface to run backtests with various configurations.

Usage:
    python -m backend.scripts.run_backtest \
        --strategy fib_rsi \
        --data-source csv \
        --csv-file data/GOLD_15M.csv \
        --symbol GOLD \
        --start 2024-01-01 \
        --end 2024-12-31 \
        --initial-balance 10000 \
        --position-size 0.1 \
        --output-html results/report.html

Example:
    python -m backend.scripts.run_backtest \
        --strategy ppo_gold \
        --data-source parquet \
        --parquet-file data/GOLD.parquet \
        --symbol GOLD \
        --start 2024-01-01 \
        --end 2024-12-31
"""

import argparse
import asyncio
import logging
from datetime import datetime
from pathlib import Path

from backend.app.backtest.adapters import CSVAdapter, ParquetAdapter
from backend.app.backtest.runner import BacktestConfig, BacktestRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    """Run backtest from command-line arguments."""
    parser = argparse.ArgumentParser(description="Run strategy backtest")

    # Strategy and data source
    parser.add_argument(
        "--strategy",
        required=True,
        choices=["fib_rsi", "ppo_gold"],
        help="Strategy to backtest",
    )
    parser.add_argument(
        "--data-source",
        required=True,
        choices=["csv", "parquet", "database"],
        help="Data source type",
    )

    # Data source files
    parser.add_argument("--csv-file", help="Path to CSV file (for csv source)")
    parser.add_argument(
        "--parquet-file", help="Path to Parquet file (for parquet source)"
    )

    # Backtest parameters
    parser.add_argument("--symbol", required=True, help="Trading symbol (e.g., GOLD)")
    parser.add_argument(
        "--start", required=True, help="Start date (YYYY-MM-DD or ISO format)"
    )
    parser.add_argument(
        "--end", required=True, help="End date (YYYY-MM-DD or ISO format)"
    )

    # Trading parameters
    parser.add_argument(
        "--initial-balance",
        type=float,
        default=10000.0,
        help="Initial account balance (default: 10000)",
    )
    parser.add_argument(
        "--position-size",
        type=float,
        default=0.1,
        help="Position size in lots (default: 0.1)",
    )
    parser.add_argument(
        "--slippage-pips",
        type=float,
        default=2.0,
        help="Slippage per trade in pips (default: 2.0)",
    )
    parser.add_argument(
        "--commission-per-lot",
        type=float,
        default=0.0,
        help="Commission per lot (default: 0.0)",
    )

    # Output files
    parser.add_argument(
        "--output-html",
        help="Output HTML report path (default: results/backtest.html)",
    )
    parser.add_argument(
        "--output-csv",
        help="Output CSV trades path (default: results/backtest_trades.csv)",
    )
    parser.add_argument(
        "--output-json",
        help="Output JSON summary path (default: results/backtest_summary.json)",
    )

    args = parser.parse_args()

    # Validate data source arguments
    if args.data_source == "csv" and not args.csv_file:
        parser.error("--csv-file required when --data-source=csv")
    if args.data_source == "parquet" and not args.parquet_file:
        parser.error("--parquet-file required when --data-source=parquet")

    # Parse dates
    try:
        start_date = datetime.fromisoformat(args.start)
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=datetime.now().astimezone().tzinfo)
    except ValueError:
        # Try simple date format
        start_date = datetime.strptime(args.start, "%Y-%m-%d")
        start_date = start_date.replace(tzinfo=datetime.now().astimezone().tzinfo)

    try:
        end_date = datetime.fromisoformat(args.end)
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=datetime.now().astimezone().tzinfo)
    except ValueError:
        # Try simple date format
        end_date = datetime.strptime(args.end, "%Y-%m-%d")
        end_date = end_date.replace(tzinfo=datetime.now().astimezone().tzinfo)

    # Create data adapter
    if args.data_source == "csv":
        adapter = CSVAdapter(args.csv_file, symbol=args.symbol)
    elif args.data_source == "parquet":
        adapter = ParquetAdapter(args.parquet_file, symbol=args.symbol)
    else:  # database
        # Note: Would need async session from app context in real implementation
        raise NotImplementedError("Database adapter requires app context")

    # Validate adapter
    adapter.validate()

    # Create backtest configuration
    config = BacktestConfig(
        initial_balance=args.initial_balance,
        position_size=args.position_size,
        slippage_pips=args.slippage_pips,
        commission_per_lot=args.commission_per_lot,
    )

    # Run backtest
    logger.info(f"Starting backtest: {args.strategy} on {args.symbol}")
    logger.info(f"Period: {start_date} to {end_date}")
    logger.info(f"Initial balance: ${config.initial_balance:,.2f}")

    runner = BacktestRunner(
        strategy=args.strategy,
        data_source=adapter,
        config=config,
    )

    report = await runner.run(
        symbol=args.symbol,
        start=start_date,
        end=end_date,
    )

    # Print summary to console
    print("\n" + "=" * 60)
    print(f"BACKTEST RESULTS: {args.strategy} - {args.symbol}")
    print("=" * 60)
    print(f"Period: {start_date.date()} to {end_date.date()}")
    print(f"Initial Balance: ${report.initial_balance:,.2f}")
    print(f"Final Equity: ${report.final_equity:,.2f}")
    print(
        f"Total PnL: ${report.total_pnl:,.2f} ({report.total_pnl / report.initial_balance * 100:.2f}%)"
    )
    print(
        f"\nTrades: {report.total_trades} ({report.winning_trades}W / {report.losing_trades}L)"
    )
    print(f"Win Rate: {report.win_rate:.2f}%")
    print(f"Profit Factor: {report.profit_factor:.2f}")
    print("\nRisk Metrics:")
    print(
        f"  Max Drawdown: ${report.max_drawdown:,.2f} ({report.max_drawdown_pct:.2f}%)"
    )
    print(f"  Sharpe Ratio: {report.sharpe_ratio:.2f}")
    print(f"  Sortino Ratio: {report.sortino_ratio:.2f}")
    print(f"  Calmar Ratio: {report.calmar_ratio:.2f}")
    print("=" * 60)

    # Export results
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)

    html_path = (
        args.output_html or f"results/backtest_{args.strategy}_{args.symbol}.html"
    )
    csv_path = (
        args.output_csv or f"results/backtest_{args.strategy}_{args.symbol}_trades.csv"
    )
    json_path = (
        args.output_json
        or f"results/backtest_{args.strategy}_{args.symbol}_summary.json"
    )

    report.to_html(html_path)
    report.to_csv(csv_path)
    report.to_json(json_path)

    print("\nResults exported:")
    print(f"  HTML: {html_path}")
    print(f"  CSV: {csv_path}")
    print(f"  JSON: {json_path}")


if __name__ == "__main__":
    asyncio.run(main())
