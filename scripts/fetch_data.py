"""
Data Download Script

Downloads historical 1-minute candle data from Upstox for one or more instruments.
Supports fetching:
- Nifty 50 Index
- NIFTYBEES ETF
- All Nifty 50 constituent stocks
- Continuous futures (stitched monthly contracts)

Usage:
    python scripts/fetch_data.py --instrument nifty50
    python scripts/fetch_data.py --instrument niftybees
    python scripts/fetch_data.py --instrument all_stocks
    python scripts/fetch_data.py --instrument NSE_EQ|INE467B01029 --days 365
"""

import sys
import argparse
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from config.settings import Settings
from core.data_fetcher import DataFetcher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def fetch_single(fetcher: DataFetcher, instrument_key: str, symbol: str, output_dir: Path, days: int):
    """Fetch and save data for a single instrument."""
    output_file = output_dir / f"{symbol}_1min.csv"

    if output_file.exists():
        logger.info(f"Data for {symbol} already exists at {output_file}. Skipping.")
        return

    logger.info(f"Fetching {symbol} ({instrument_key})...")
    from datetime import datetime, timedelta
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    df = fetcher.fetch_historical(instrument_key, start_date, end_date)
    if df.empty:
        logger.warning(f"No data returned for {symbol}!")
        return

    df.to_csv(output_file)
    logger.info(f"Saved {len(df)} candles → {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Download historical market data")
    parser.add_argument(
        "--instrument", "-i",
        default="nifty50",
        help="Instrument to fetch: nifty50, niftybees, all_stocks, or a specific key"
    )
    parser.add_argument(
        "--days", "-d",
        type=int,
        default=730,
        help="Number of days of history to fetch (default: 730)"
    )
    args = parser.parse_args()

    settings = Settings()
    fetcher = DataFetcher(settings)
    output_dir = settings.OUTPUT_DIR / "Data"
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.instrument == "nifty50":
        fetch_single(fetcher, settings.NIFTY50_INDEX_KEY, "NIFTY50_INDEX", output_dir, args.days)

    elif args.instrument == "niftybees":
        fetch_single(fetcher, settings.NIFTYBEES_KEY, "NIFTYBEES", output_dir, args.days)

    elif args.instrument == "all_stocks":
        if not settings.STOCK_LIST_PATH.exists():
            logger.error(f"Stock list not found: {settings.STOCK_LIST_PATH}")
            sys.exit(1)

        stock_df = pd.read_csv(settings.STOCK_LIST_PATH)
        total = len(stock_df)

        for idx, row in stock_df.iterrows():
            symbol = row["Symbol"]
            isin = row["ISIN Code"]
            key = f"NSE_EQ|{isin}"
            logger.info(f"[{idx+1}/{total}] Processing {symbol}")
            fetch_single(fetcher, key, symbol, output_dir, args.days)

    else:
        # Treat as a specific instrument key
        symbol = args.instrument.split("|")[-1] if "|" in args.instrument else args.instrument
        fetch_single(fetcher, args.instrument, symbol, output_dir, args.days)

    logger.info("Data download complete!")


if __name__ == "__main__":
    main()
