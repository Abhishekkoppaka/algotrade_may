"""
Backtest Runner Script

CLI tool to run any strategy's backtest on any historical data file.
Produces trades CSV, metrics summary, and equity curve chart.

Usage:
    python scripts/run_backtest.py --strategy three_candle --data data/output/Data/NIFTY50_INDEX_1min.csv
    python scripts/run_backtest.py --strategy camarilla --data data/output/Data/NIFTY50_INDEX_1min.csv
    python scripts/run_backtest.py --strategy three_candle --data data/output/Data/RELIANCE_1min.csv
"""

import sys
import argparse
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from config.settings import Settings
from strategies.three_candle import ThreeCandleStrategy
from strategies.camarilla import CamarillaStrategy
from strategies.two_window_pivot_reversal import TwoWindowPivotReversalStrategy
from backtesting.engine import BacktestEngine
from backtesting.metrics import calculate_metrics, print_metrics, save_report

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Registry of available strategies
STRATEGIES = {
    "three_candle": ThreeCandleStrategy,
    "camarilla": CamarillaStrategy,
    "two_window_pivot_reversal": TwoWindowPivotReversalStrategy,
}


def main():
    parser = argparse.ArgumentParser(description="Run strategy backtest")
    parser.add_argument(
        "--strategy", "-s",
        required=True,
        choices=list(STRATEGIES.keys()),
        help="Strategy to backtest"
    )
    parser.add_argument(
        "--data", "-d",
        required=True,
        help="Path to historical data CSV file (1-min OHLCV with timestamp index)"
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output directory for results (default: data/output/{strategy}_Backtest)"
    )
    args = parser.parse_args()

    # Load data
    data_path = Path(args.data)
    if not data_path.exists():
        logger.error(f"Data file not found: {data_path}")
        sys.exit(1)

    logger.info(f"Loading data from {data_path}...")
    df = pd.read_csv(data_path, index_col="timestamp", parse_dates=True)

    # Remove timezone if present
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    logger.info(f"Loaded {len(df)} bars ({df.index[0]} to {df.index[-1]})")

    # Initialize strategy
    settings = Settings()
    strategy_class = STRATEGIES[args.strategy]
    strategy = strategy_class(settings) if args.strategy != "camarilla" else strategy_class()

    # Run backtest
    engine = BacktestEngine(strategy, settings)
    trades_df = engine.run(df)

    # Calculate and display metrics
    if trades_df.empty:
        logger.info("No trades generated during the backtest period.")
        return

    metrics = calculate_metrics(trades_df)
    print_metrics(metrics, f"{strategy.name} BACKTEST RESULTS")

    # Save full report
    output_dir = Path(args.output) if args.output else settings.OUTPUT_DIR / f"{args.strategy}_Backtest"
    save_report(trades_df, metrics, output_dir, args.strategy)


if __name__ == "__main__":
    main()
