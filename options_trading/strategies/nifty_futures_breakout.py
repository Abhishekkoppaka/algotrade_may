"""
Nifty futures breakout signal strategy.

This strategy decides whether the Nifty futures instrument has produced a
fresh 3Candle breakout. It does not know how options are selected or ordered.
"""

from typing import Optional

import pandas as pd

from live.setup import evaluate_morning_setup, find_missed_breakout


class NiftyFuturesBreakoutStrategy:
    """3Candle breakout strategy applied to Nifty futures candles and LTP."""

    name = "nifty_futures_3candle_breakout"

    def __init__(self, min_inside_candles: int):
        self.min_inside_candles = min_inside_candles
        self.setup: Optional[dict] = None

    def prepare_setup(self, df: pd.DataFrame) -> tuple[bool, Optional[dict]]:
        """
        Prepare the daily setup and reject stale pre-start breakouts.

        Returns:
            Tuple of (qualified, missed_breakout). If missed_breakout is not
            None, the setup is stale for the day and should not be traded.
        """
        setup = evaluate_morning_setup(df, self.min_inside_candles)
        if not setup:
            self.setup = None
            return False, None

        missed = find_missed_breakout(
            df,
            setup["d15_high"],
            setup["d15_low"],
            "NIFTY FUT",
        )
        if missed:
            self.setup = None
            return False, missed

        self.setup = setup
        return True, None

    def get_signal(self, ltp: float) -> Optional[str]:
        """Return LONG, SHORT, or None based on the fresh futures LTP."""
        if not self.setup:
            return None
        if ltp > self.setup["d15_high"]:
            return "LONG"
        if ltp < self.setup["d15_low"]:
            return "SHORT"
        return None
