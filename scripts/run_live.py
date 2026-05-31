"""
Live Trading Script

Starts the live trading bot with the 3Candle strategy.
Scans Nifty 50 index + all constituent stocks for setups.

Usage:
    python scripts/run_live.py --confirm-live

IMPORTANT: Ensure you have run scripts/authenticate.py first to get a valid token.
This script places real orders. It refuses to start without --confirm-live.
"""

import sys
import argparse
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import Settings
from live.engine import LiveEngine
from live.instruments import build_observer_list

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Run live trading bot")
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="Confirm that this run may place real Upstox orders",
    )
    args = parser.parse_args()

    settings = Settings()

    if not args.confirm_live:
        logger.error("Live trading requires explicit confirmation: add --confirm-live")
        sys.exit(2)

    # Validate token exists
    if not settings.UPSTOX_ACCESS_TOKEN:
        logger.error("No access token found. Run scripts/authenticate.py first.")
        sys.exit(1)

    logger.info("Starting live bot in LIVE mode")
    logger.info(f"Capital: Rs {settings.CAPITAL:,.0f} | Leverage: {settings.LEVERAGE}x")

    # Build instrument list
    observers = build_observer_list(settings)
    logger.info(f"Monitoring {len(observers)} instruments")

    # Start the engine
    engine = LiveEngine(settings)
    engine.run(observers)


if __name__ == "__main__":
    main()
