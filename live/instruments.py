"""
Instrument universe construction for live trading.

This module owns the mapping between signal instruments and execution
instruments. The live engine consumes the resulting observer dictionaries and
does not need to know where the universe came from.
"""

import logging
from typing import List, Dict

import pandas as pd

from config.settings import Settings

logger = logging.getLogger(__name__)


def build_observer_list(settings: Settings) -> List[Dict[str, str]]:
    """
    Build the list of instruments monitored by the live bot.

    Each observer contains:
    - signal_key: Upstox key used to detect signals
    - symbol: display symbol for the signal instrument
    - execution_key: Upstox key used to place orders
    - execution_symbol: display symbol for the traded instrument
    """
    observers = [_build_index_observer(settings)]
    observers.extend(_load_stock_observers(settings))
    return observers


def _build_index_observer(settings: Settings) -> Dict[str, str]:
    """Use Nifty 50 index for signals and NIFTYBEES for execution."""
    return {
        "signal_key": settings.NIFTY50_INDEX_KEY,
        "symbol": "NIFTY 50",
        "execution_key": settings.NIFTYBEES_KEY,
        "execution_symbol": "NIFTYBEES",
    }


def _load_stock_observers(settings: Settings) -> List[Dict[str, str]]:
    """Load Nifty 50 stock observers from the configured source CSV."""
    if not settings.STOCK_LIST_PATH.exists():
        logger.warning("Stock list not found: %s", settings.STOCK_LIST_PATH)
        logger.warning("Running with Nifty 50 Index only")
        return []

    stock_df = pd.read_csv(settings.STOCK_LIST_PATH)
    observers = []
    for _, row in stock_df.iterrows():
        key = f"NSE_EQ|{row['ISIN Code']}"
        observers.append({
            "signal_key": key,
            "symbol": row["Symbol"],
            "execution_key": key,
            "execution_symbol": row["Symbol"],
        })

    logger.info("Loaded %s stocks from watchlist", len(stock_df))
    return observers
