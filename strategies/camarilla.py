"""
Camarilla Pivot Strategy

Original Pine Script: "Camarilla_L3toH3" by Krish5060
Converted to Python with identical logic.

Strategy Logic (two sub-setups):

SETUP 1 — H4/L4 Breakout:
    Entry: 15-minute candle CLOSES past H4 (but not H5) with momentum color
    Direction: Same as breakout direction
    Target: H5 (for longs) or L5 (for shorts)
    StopLoss: H3 (for longs) or L3 (for shorts)

SETUP 2 — L3/H3 Mean Reversion:
    Entry: 15-minute candle wicks past L3/H3 but closes back inside the range
    Direction: Reversal (wick below L3 + green close → LONG)
    Target: H3 (for longs) or L3 (for shorts)
    StopLoss: L4 (for longs) or H4 (for shorts)

EXECUTION:
- Triggers are set on a 15-minute timeframe (candle close basis)
- Entries fire on the next 1-minute bar that crosses the trigger price
- Stop Loss checked on 15-minute candle CLOSE (not intraday breach)
- Target checked on 1-minute bar (first touch exits)
- EOD square-off at 14:30
- Maximum 1 trade per day
"""

import numpy as np
import pandas as pd
from strategies.base import BaseStrategy, TradeDirection
from strategies.indicators import calculate_camarilla_pivots


class CamarillaStrategy(BaseStrategy):
    """
    Multi-timeframe Camarilla pivot strategy.

    Operates on 1-minute bars but internally builds 15-minute candles
    to detect setup conditions. Entry/exit execution is on 1-minute bars.
    """

    def __init__(self):
        super().__init__(name="Camarilla Pivots")

    def prepare_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add Camarilla Pivot Points to the DataFrame.

        Args:
            df: Raw 1-minute OHLCV DataFrame.

        Returns:
            DataFrame with cL3, cH3, cL4, cH4, cL5, cH5 columns.
        """
        return calculate_camarilla_pivots(df)

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Multi-timeframe signal generation.

        Internally constructs 15-minute candles from 1-minute data,
        evaluates setup conditions at 15-minute boundaries, and
        sets trigger/target/SL for 1-minute execution.

        Output columns:
        - signal_direction: 0=NONE, 1=LONG, 2=SHORT
        - trigger_price: Entry trigger
        - target_price: Take profit
        - stop_loss_price: Stop loss
        - is_reset: EOD flag
        - setup_type: "H4_L4_Breakout" or "L3_H3_Reversal"

        Args:
            df: DataFrame with Camarilla pivot columns.

        Returns:
            DataFrame with signal columns.
        """
        df = df.copy()
        n = len(df)

        # Output arrays
        out_direction = np.zeros(n, dtype=int)
        out_trigger = np.full(n, np.nan)
        out_target = np.full(n, np.nan)
        out_sl = np.full(n, np.nan)
        out_reset = np.zeros(n, dtype=int)
        out_setup = [""] * n

        # Process day by day
        df["date"] = df.index.date

        for date, day_df in df.groupby("date"):
            # Per-day state
            trigger_direction = 0  # 0=none, 1=long, -1=short
            trigger_price = np.nan
            target = np.nan
            sl = np.nan
            setup_type = ""
            trades_today = 0

            # 15-minute chunk tracking
            chunk_open = 0.0
            chunk_high = -np.inf
            chunk_low = np.inf
            chunk_start_idx = None

            for idx, row in day_df.iterrows():
                # Get position in original DataFrame
                pos = df.index.get_loc(idx)
                current_time = idx.time()

                # EOD at 14:30
                if current_time >= pd.Timestamp("14:30").time():
                    out_reset[pos] = 1
                    continue

                # --- 1-MINUTE EXECUTION: Check if trigger is hit ---
                if trades_today == 0 and not np.isnan(trigger_price):
                    if trigger_direction == 1 and row["high"] >= trigger_price:
                        out_direction[pos] = 1
                        out_trigger[pos] = trigger_price
                        out_target[pos] = target
                        out_sl[pos] = sl
                        out_setup[pos] = setup_type
                        trades_today += 1
                    elif trigger_direction == -1 and row["low"] <= trigger_price:
                        out_direction[pos] = 2
                        out_trigger[pos] = trigger_price
                        out_target[pos] = target
                        out_sl[pos] = sl
                        out_setup[pos] = setup_type
                        trades_today += 1

                # --- 15-MINUTE CANDLE BUILDING ---
                if chunk_start_idx is None:
                    chunk_start_idx = pos
                    chunk_open = row["open"]
                    chunk_high = row["high"]
                    chunk_low = row["low"]
                else:
                    chunk_high = max(chunk_high, row["high"])
                    chunk_low = min(chunk_low, row["low"])

                # Check if this bar is the end of a 15-minute window
                if self._is_15min_boundary(current_time):
                    chunk_close = row["close"]

                    # --- 15-MIN CLOSE-BASED STOP LOSS CHECK ---
                    # (SL is only evaluated on 15-min close, not intraday)
                    if trigger_direction == 1 and trades_today > 0 and chunk_close < sl:
                        pass  # Backtester handles exit, not signal generator
                    elif trigger_direction == -1 and trades_today > 0 and chunk_close > sl:
                        pass

                    # --- SETUP CONDITION EVALUATION (only if no trade today) ---
                    if trades_today == 0:
                        cL3 = row.get("cL3", np.nan)
                        cH3 = row.get("cH3", np.nan)
                        cL4 = row.get("cL4", np.nan)
                        cH4 = row.get("cH4", np.nan)
                        cL5 = row.get("cL5", np.nan)
                        cH5 = row.get("cH5", np.nan)

                        if not np.isnan(cL3):
                            is_green = chunk_close > chunk_open
                            is_red = chunk_close < chunk_open

                            # SETUP 1: H4/L4 Breakout
                            # Close past H4 but not H5, with matching color
                            if chunk_close > cH4 and chunk_close < cH5 and is_green:
                                trigger_price = chunk_high
                                trigger_direction = 1
                                target = cH5
                                sl = cH3
                                setup_type = "H4_L4_Breakout"

                            elif chunk_close < cL4 and chunk_close > cL5 and is_red:
                                trigger_price = chunk_low
                                trigger_direction = -1
                                target = cL5
                                sl = cL3
                                setup_type = "H4_L4_Breakout"

                            # SETUP 2: L3/H3 Mean Reversion
                            # Wick past level but close back inside
                            elif chunk_low <= cL3 and chunk_close > cL3 and chunk_close < cH3 and is_green:
                                trigger_price = chunk_high
                                trigger_direction = 1
                                target = cH3
                                sl = cL4
                                setup_type = "L3_H3_Reversal"

                            elif chunk_high >= cH3 and chunk_close < cH3 and chunk_close > cL3 and is_red:
                                trigger_price = chunk_low
                                trigger_direction = -1
                                target = cL3
                                sl = cH4
                                setup_type = "L3_H3_Reversal"

                    # Reset 15-min chunk
                    chunk_start_idx = None
                    chunk_high = -np.inf
                    chunk_low = np.inf

        # Assign output columns
        df["signal_direction"] = out_direction
        df["trigger_price"] = out_trigger
        df["target_price"] = out_target
        df["stop_loss_price"] = out_sl
        df["is_reset"] = out_reset
        df["setup_type"] = out_setup
        df.drop(columns=["date"], inplace=True)

        return df

    @staticmethod
    def _is_15min_boundary(t) -> bool:
        """
        Check if a time falls on a 15-minute candle boundary.

        Market opens at 09:15, so 15-min candles end at:
        09:29, 09:44, 09:59, 10:14, 10:29, ... , 14:29

        Args:
            t: datetime.time object.

        Returns:
            True if this time is the last minute of a 15-min candle.
        """
        h, m = t.hour, t.minute

        # First candle of the day ends at 09:29
        if h == 9 and m == 29:
            return True

        # Subsequent candles: every 15 minutes from 09:30 onwards
        # 09:44, 09:59, 10:14, 10:29, ...
        if h >= 9 and m in (14, 29, 44, 59):
            if h == 9 and m == 14:
                return False  # 09:14 is before market open
            return True

        return False
