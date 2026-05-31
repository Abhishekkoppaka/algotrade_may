"""
Run the Nifty futures-tracked live options spread bot.

Usage:
    python scripts/run_nifty_options_live.py --confirm-live
    python scripts/run_nifty_options_live.py --confirm-live --expiry 2026-05-28

This script places real Nifty option orders using Nifty futures as the signal.
It is separate from run_live.py.
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from options_trading.config import OptionsTradingSettings
from options_trading.engines import NiftyOptionsLiveEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Nifty options spread bot")
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="Confirm that this run may place real Nifty option orders",
    )
    parser.add_argument(
        "--expiry",
        default=None,
        help="Optional Nifty option expiry in YYYY-MM-DD format. Defaults to nearest expiry.",
    )
    args = parser.parse_args()

    if not args.confirm_live:
        logger.error("Nifty options live trading requires --confirm-live")
        sys.exit(2)

    settings = OptionsTradingSettings()
    missing = settings.validate_for_live()
    if missing:
        logger.error("Missing required setting(s): %s", ", ".join(missing))
        logger.error("Add them to .env. See options_trading/.env.example.")
        sys.exit(1)

    logger.info("Starting Nifty options bot in LIVE mode")
    logger.info(
        "Signal=%s | Lots=%s | Sell offset=%s | Hedge offset=%s",
        settings.NIFTY_FUTURES_KEY,
        settings.NIFTY_OPTION_LOTS,
        settings.NIFTY_OPTION_SELL_OFFSET,
        settings.NIFTY_OPTION_HEDGE_OFFSET,
    )

    engine = NiftyOptionsLiveEngine(settings=settings, expiry_date=args.expiry)
    engine.run()


if __name__ == "__main__":
    main()
