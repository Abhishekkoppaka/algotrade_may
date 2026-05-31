"""
Nifty futures two-window pivot reversal signal strategy.

This module only decides whether a fresh Nifty futures signal exists. Option
contract selection and order placement remain outside the strategy.
"""

from datetime import datetime
from typing import Optional

import pandas as pd

from strategies.indicators import calculate_floor_pivots_from_ohlc
from strategies.two_window_pivot_reversal import (
    TwoWindowPivotSetup,
    build_two_window_pivot_setup,
)


class NiftyFuturesTwoWindowPivotReversalStrategy:
    """Live Nifty futures signal source for the two-window reversal rule."""

    name = "nifty_futures_two_window_pivot_reversal"

    def __init__(self):
        self.setup: Optional[TwoWindowPivotSetup] = None
        self.last_checked_timestamp: Optional[pd.Timestamp] = None
        self.signal_emitted = False

    def prepare_setup(
        self,
        df: pd.DataFrame,
        as_of: Optional[datetime] = None,
    ) -> tuple[bool, Optional[dict]]:
        """
        Prepare today's setup and reject a signal that occurred before startup.
        """
        if df.empty:
            return False, None

        completed = self._completed_candles(df, as_of)
        if completed.empty:
            return False, None

        today = completed.index[-1].date()
        previous_days = df[df.index.date < today]
        daily = previous_days.groupby(previous_days.index.date).agg({
            "high": "max",
            "low": "min",
            "close": "last",
        })
        if daily.empty:
            return False, None

        yesterday = daily.iloc[-1]
        pivot_dict = calculate_floor_pivots_from_ohlc(
            yesterday["high"],
            yesterday["low"],
            yesterday["close"],
        )
        today_df = completed[completed.index.date == today]
        setup = build_two_window_pivot_setup(today_df, list(pivot_dict.values()))
        if setup is None:
            return False, None

        self.setup = setup
        self.last_checked_timestamp = today_df.index.max()
        missed = self._first_signal(today_df.between_time("09:45", "14:29"))
        if missed:
            self.setup = None
            return False, missed

        return True, None

    def get_signal(
        self,
        df: pd.DataFrame,
        as_of: Optional[datetime] = None,
    ) -> Optional[dict]:
        """Return the first fresh confirmed one-minute-close signal."""
        if self.setup is None or self.signal_emitted or df.empty:
            return None

        completed = self._completed_candles(df, as_of)
        if self.last_checked_timestamp is not None:
            completed = completed[completed.index > self.last_checked_timestamp]
        if completed.empty:
            return None

        self.last_checked_timestamp = completed.index.max()
        signal = self._first_signal(completed.between_time("09:45", "14:29"))
        if signal:
            self.signal_emitted = True
        return signal

    def _first_signal(self, candles: pd.DataFrame) -> Optional[dict]:
        if self.setup is None or candles.empty:
            return None

        if self.setup.direction == "LONG":
            matches = candles[candles["close"] > self.setup.trigger_price]
        else:
            matches = candles[candles["close"] < self.setup.trigger_price]
        if matches.empty:
            return None

        signal_bar = matches.iloc[0]
        return {
            "direction": self.setup.direction,
            "signal_time": signal_bar.name,
            "signal_close": float(signal_bar["close"]),
            "trigger_price": self.setup.trigger_price,
            "target_price": self.setup.target_price,
            "stop_loss_price": self.setup.stop_loss_price,
        }

    @staticmethod
    def _completed_candles(
        df: pd.DataFrame,
        as_of: Optional[datetime],
    ) -> pd.DataFrame:
        """
        Exclude the current in-progress one-minute candle.

        Upstox intraday responses may include the candle for the current minute.
        """
        timestamp = pd.Timestamp(as_of or datetime.now())
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_localize(None)
        current_minute = timestamp.floor("min")
        return df[df.index < current_minute]
