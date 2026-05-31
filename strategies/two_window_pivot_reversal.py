"""
Two-window pivot reversal strategy.

The strategy compares the first two 15-minute ranges of the trading day:
- 09:15-09:29: initial range
- 09:30-09:44: qualification range

A strict break of only one side of the initial range creates a reversal setup.
Entry is confirmed by a later one-minute candle close beyond the second range,
then executed at the next one-minute candle open.
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from config.settings import Settings
from strategies.base import BaseStrategy
from strategies.indicators import calculate_floor_pivots


@dataclass(frozen=True)
class TwoWindowPivotSetup:
    """Qualified two-window reversal setup and its fixed trade levels."""

    direction: str
    trigger_price: float
    target_price: float
    stop_loss_price: float
    first_high: float
    first_low: float
    second_high: float
    second_low: float


def _nearest_above(price: float, levels: list[float]) -> Optional[float]:
    candidates = [level for level in levels if pd.notna(level) and level > price]
    return min(candidates) if candidates else None


def _nearest_below(price: float, levels: list[float]) -> Optional[float]:
    candidates = [level for level in levels if pd.notna(level) and level < price]
    return max(candidates) if candidates else None


def build_two_window_pivot_setup(
    today_df: pd.DataFrame,
    pivot_levels: list[float],
) -> Optional[TwoWindowPivotSetup]:
    """
    Build a setup from today's first two 15-minute windows.

    A setup is rejected when both initial-range sides break, neither side
    breaks, or a strict target/stop level cannot be selected.
    """
    first_window = today_df.between_time("09:15", "09:29")
    second_window = today_df.between_time("09:30", "09:44")
    if len(first_window) < 15 or len(second_window) < 15:
        return None

    first_high = float(first_window["high"].max())
    first_low = float(first_window["low"].min())
    second_high = float(second_window["high"].max())
    second_low = float(second_window["low"].min())

    low_broken = second_low < first_low
    high_broken = second_high > first_high
    if low_broken == high_broken:
        return None

    if low_broken:
        trigger = second_high
        target = _nearest_above(trigger, [*pivot_levels, first_high])
        stop = _nearest_below(trigger, [*pivot_levels, second_low])
        direction = "LONG"
    else:
        trigger = second_low
        target = _nearest_below(trigger, [*pivot_levels, first_low])
        stop = _nearest_above(trigger, [*pivot_levels, second_high])
        direction = "SHORT"

    if target is None or stop is None:
        return None

    return TwoWindowPivotSetup(
        direction=direction,
        trigger_price=float(trigger),
        target_price=float(target),
        stop_loss_price=float(stop),
        first_high=first_high,
        first_low=first_low,
        second_high=second_high,
        second_low=second_low,
    )


class TwoWindowPivotReversalStrategy(BaseStrategy):
    """Backtest strategy for the two-window pivot reversal rule."""

    def __init__(self, settings: Optional[Settings] = None):
        super().__init__(name="Two-Window Pivot Reversal")
        self.settings = settings or Settings()

    def prepare_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add shared previous-day floor pivot and CPR levels."""
        return calculate_floor_pivots(df)

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate one confirmed signal per qualified day."""
        df = df.copy()
        n = len(df)
        out_direction = np.zeros(n, dtype=int)
        out_trigger = np.full(n, np.nan)
        out_target = np.full(n, np.nan)
        out_sl = np.full(n, np.nan)
        out_reset = np.zeros(n, dtype=int)
        out_next_open = np.zeros(n, dtype=int)

        pivot_columns = [
            "vPP", "vBC", "vTC", "vR1", "vR2", "vR3",
            "vS1", "vS2", "vS3", "PDH", "PDL",
        ]

        for _, positions in df.groupby(df.index.date).indices.items():
            day_positions = np.asarray(positions)
            day_df = df.iloc[day_positions]
            first_row = day_df.iloc[0]
            pivot_levels = [first_row[column] for column in pivot_columns]
            setup = build_two_window_pivot_setup(day_df, pivot_levels)
            signal_emitted = False

            for position in day_positions:
                timestamp = df.index[position]
                time_int = timestamp.hour * 100 + timestamp.minute

                if time_int >= self.settings.PIVOT_REVERSAL_SQUAREOFF:
                    out_reset[position] = 1
                    continue

                if (
                    setup is None
                    or signal_emitted
                    or time_int < self.settings.PIVOT_REVERSAL_ENTRY_START
                    or time_int > self.settings.PIVOT_REVERSAL_LAST_SIGNAL
                ):
                    continue

                close = float(df.iloc[position]["close"])
                if setup.direction == "LONG" and close > setup.trigger_price:
                    out_direction[position] = 1
                elif setup.direction == "SHORT" and close < setup.trigger_price:
                    out_direction[position] = 2
                else:
                    continue

                out_trigger[position] = setup.trigger_price
                out_target[position] = setup.target_price
                out_sl[position] = setup.stop_loss_price
                out_next_open[position] = 1
                signal_emitted = True

        df["signal_direction"] = out_direction
        df["trigger_price"] = out_trigger
        df["target_price"] = out_target
        df["stop_loss_price"] = out_sl
        df["is_reset"] = out_reset
        df["entry_on_next_open"] = out_next_open
        return df
