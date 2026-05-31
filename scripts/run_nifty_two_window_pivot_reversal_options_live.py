"""
Run the isolated Nifty two-window pivot reversal options bot.

Usage:
    python scripts/run_nifty_two_window_pivot_reversal_options_live.py --confirm-live
    python scripts/run_nifty_two_window_pivot_reversal_options_live.py --confirm-live --expiry 2026-06-04

This script places real Nifty option orders. It is intentionally separate from
the active 1+3 options runner until the strategies are ready to be combined.
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from options_trading.config import OptionsTradingSettings
from options_trading.engines.nifty_two_window_pivot_reversal_live import (
    NiftyTwoWindowPivotReversalOptionsLiveEngine,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run isolated Nifty two-window pivot reversal options bot"
    )
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

    logger.info("Starting isolated Nifty two-window pivot reversal bot in LIVE mode")
    engine = NiftyTwoWindowPivotReversalOptionsLiveEngine(
        settings=settings,
        expiry_date=args.expiry,
    )
    engine.run()


if __name__ == "__main__":
    main()
