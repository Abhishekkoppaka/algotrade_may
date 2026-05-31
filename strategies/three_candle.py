"""
3Candle Breakout Strategy

Original Pine Script: "3Candle" by Krish5060
Converted to Python with identical logic.

Strategy Logic:
1. INITIAL BALANCE (09:15-09:29): Record the high and low of the first 15 minutes.
2. CONSOLIDATION CHECK (09:30-10:14): Count "inside candles" — candles whose entire
   range fits within the Initial Balance. Require at least 3 inside candles AND
   the range must not be broken during this period.
3. BREAKOUT DETECTION (10:15-14:29): After consolidation is confirmed:
   - If a candle CLOSES above the IB high → set LONG trigger at that candle's high
   - If a candle CLOSES below the IB low → set SHORT trigger at that candle's low
4. TARGET & STOP: Mapped to the nearest Floor Pivot above/below the trigger price.
5. EOD RESET (14:30): Force-close any open position.

This strategy is a momentum/breakout play: it identifies a narrow opening range,
waits for compression, then rides the expansion.
"""

import numpy as np
import pandas as pd
from strategies.base import BaseStrategy, TradeDirection
from strategies.indicators import (
    calculate_floor_pivots,
    get_next_pivot_above,
    get_next_pivot_below,
)
from config.settings import Settings


class ThreeCandleStrategy(BaseStrategy):
    """
    Implementation of the 3Candle intraday breakout strategy.

    The strategy operates on 1-minute bars and produces one signal per day
    (the first valid breakout after consolidation is confirmed).

    Parameters (from Settings):
    - IB_START / IB_END: Initial Balance time window
    - CONSOLIDATION_START / CONSOLIDATION_END: Inside-candle check window
    - MIN_INSIDE_CANDLES: Minimum inside candles required (default 3)
    - TRADE_START / TRADE_END: Active trading window
    - EOD_SQUAREOFF: Forced exit time
    """

    def __init__(self, settings: Settings = None):
        """
        Initialize the 3Candle strategy.

        Args:
            settings: Configuration for time windows and parameters.
        """
        super().__init__(name="3Candle Breakout")
        self.settings = settings or Settings()

    def prepare_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add Floor Pivot Points to the raw OHLCV data.

        The 3Candle strategy uses standard floor pivots (PP, R1-R3, S1-S3)
        plus PDH/PDL as support and resistance levels for target/stop mapping.

        Args:
            df: Raw 1-minute OHLCV DataFrame.

        Returns:
            DataFrame with pivot columns added.
        """
        return calculate_floor_pivots(df)

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Bar-by-bar signal generation implementing the 3Candle logic.

        Processes each bar sequentially maintaining state across the day:
        - Tracks the IB high/low during 09:15-09:29
        - Counts inside candles during 09:30-10:14
        - Detects breakout closes and sets trigger/target/SL after 10:15
        - Resets all state at 14:30

        Output columns added to DataFrame:
        - signal_direction: 0=NONE, 1=LONG, 2=SHORT
        - trigger_price: Price level that must be crossed for entry
        - target_price: Take profit level (next pivot in trade direction)
        - stop_loss_price: Stop loss level (next pivot against trade direction)
        - is_reset: 1 if this is the EOD reset bar

        Args:
            df: DataFrame with pivot columns (from prepare_data).

        Returns:
            DataFrame with signal columns.
        """
        df = df.copy()

        # Convert timestamp to integer time for fast comparison (e.g., 915, 1030)
        df["time_int"] = df.index.strftime("%H%M").astype(int)

        # Pre-extract arrays for performance (avoid repeated DataFrame indexing)
        times = df["time_int"].values
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values

        # Pivot arrays
        vR3 = df["vR3"].values
        vR2 = df["vR2"].values
        vR1 = df["vR1"].values
        vPP = df["vPP"].values
        vS1 = df["vS1"].values
        vS2 = df["vS2"].values
        vS3 = df["vS3"].values
        PDH = df["PDH"].values
        PDL = df["PDL"].values

        # Output arrays (pre-allocated for performance)
        n = len(df)
        out_direction = np.zeros(n, dtype=int)
        out_trigger = np.full(n, np.nan)
        out_target = np.full(n, np.nan)
        out_sl = np.full(n, np.nan)
        out_reset = np.zeros(n, dtype=int)

        # Intraday state variables (reset each day at 14:30)
        ib_high = -np.inf       # Initial Balance high
        ib_low = np.inf         # Initial Balance low
        inside_count = 0        # Number of inside candles counted
        is_valid = 0            # 0=no signal, 1=LONG ready, 2=SHORT ready
        is_range_broken = False # Whether IB was breached during consolidation

        # Signal state (persists until reset)
        trigger = np.nan
        target = np.nan
        stop_loss = np.nan

        # Settings references
        ib_start = self.settings.IB_START
        ib_end = self.settings.IB_END
        cons_start = self.settings.CONSOLIDATION_START
        cons_end = self.settings.CONSOLIDATION_END
        trade_start = self.settings.TRADE_START
        eod = self.settings.EOD_SQUAREOFF
        min_candles = self.settings.MIN_INSIDE_CANDLES

        for i in range(n):
            t = times[i]
            H, L, C = highs[i], lows[i], closes[i]

            # --- Phase 1: Initial Balance Formation (09:15-09:29) ---
            if ib_start <= t <= ib_end:
                ib_high = max(ib_high, H)
                ib_low = min(ib_low, L)

            # --- Phase 2: Consolidation Check (09:30-10:14) ---
            elif cons_start <= t <= cons_end:
                if ib_high > -np.inf and ib_low < np.inf:
                    if H < ib_high and L > ib_low:
                        # Candle is fully inside IB range
                        inside_count += 1
                    elif H >= ib_high or L <= ib_low:
                        # Range broken — strategy invalidated for today
                        is_range_broken = True

            # --- Phase 3: Breakout Detection (10:15-14:29) ---
            elif trade_start <= t < eod:
                if not is_range_broken and ib_high > -np.inf and inside_count >= min_candles:
                    # LONG breakout: candle closes above IB high
                    if is_valid == 0 and C > ib_high:
                        # Build sorted pivot list for this bar
                        pivots = sorted([
                            vR3[i], vR2[i], vR1[i], vPP[i],
                            vS1[i], vS2[i], vS3[i], PDH[i], PDL[i]
                        ])
                        trigger = H
                        target = get_next_pivot_above(trigger, pivots)
                        stop_loss = get_next_pivot_below(trigger, pivots)
                        is_valid = 1

                    # SHORT breakout: candle closes below IB low
                    elif is_valid == 0 and C < ib_low:
                        pivots = sorted([
                            vR3[i], vR2[i], vR1[i], vPP[i],
                            vS1[i], vS2[i], vS3[i], PDH[i], PDL[i]
                        ])
                        trigger = L
                        target = get_next_pivot_below(trigger, pivots)
                        stop_loss = get_next_pivot_above(trigger, pivots)
                        is_valid = 2

            # --- Phase 4: EOD Reset (14:30+) ---
            if t >= eod:
                out_reset[i] = 1
                # Reset all state for the next trading day
                ib_high = -np.inf
                ib_low = np.inf
                inside_count = 0
                is_valid = 0
                is_range_broken = False
                trigger = np.nan
                target = np.nan
                stop_loss = np.nan

            # Write current state to output arrays
            out_direction[i] = is_valid
            out_trigger[i] = trigger
            out_target[i] = target
            out_sl[i] = stop_loss

        # Assign output columns
        df["signal_direction"] = out_direction
        df["trigger_price"] = out_trigger
        df["target_price"] = out_target
        df["stop_loss_price"] = out_sl
        df["is_reset"] = out_reset

        # Clean up working column
        df.drop(columns=["time_int"], inplace=True)

        return df
