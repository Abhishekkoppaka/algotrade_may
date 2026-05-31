"""
3Candle morning setup evaluation for live trading.

The strategy module generates vectorized backtest signals. These helpers keep
the live setup scan aligned with that strategy without making the live engine
own candle-window and pivot-preparation details.
"""

from typing import Optional

import pandas as pd

from strategies.indicators import (
    calculate_floor_pivots_from_ohlc,
    get_sorted_pivot_levels,
)


def evaluate_morning_setup(
    df: pd.DataFrame,
    min_inside_candles: int,
) -> Optional[dict]:
    """
    Return setup data if the 3Candle morning conditions qualify.

    The input must include at least yesterday plus today's intraday candles.
    """
    if df.empty:
        return None

    daily = df.groupby(df.index.date).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    })
    if len(daily) < 2:
        return None

    yesterday = daily.iloc[-2]
    pivot_dict = calculate_floor_pivots_from_ohlc(
        yesterday["high"],
        yesterday["low"],
        yesterday["close"],
    )

    today_date = df.index[-1].date()
    today_df = df[df.index.date == today_date]
    ib = today_df.between_time("09:15", "09:29")
    consolidation = today_df.between_time("09:30", "10:14")
    if ib.empty or consolidation.empty:
        return None

    d15_high = ib["high"].max()
    d15_low = ib["low"].min()

    inside_count = 0
    range_broken = False
    for _, row in consolidation.iterrows():
        if row["high"] < d15_high and row["low"] > d15_low:
            inside_count += 1
        elif row["high"] >= d15_high or row["low"] <= d15_low:
            range_broken = True
            break

    if inside_count < min_inside_candles or range_broken:
        return None

    # Preserve the established 1+3 target set. CPR is calculated centrally for
    # strategies that opt into it, but adding BC/TC must not alter active 1+3
    # live behavior.
    one_plus_three_pivots = {
        name: level
        for name, level in pivot_dict.items()
        if name not in {"BC", "TC"}
    }

    return {
        "d15_high": d15_high,
        "d15_low": d15_low,
        "pivots": get_sorted_pivot_levels(one_plus_three_pivots),
    }


def find_missed_breakout(
    df: pd.DataFrame,
    d15_high: float,
    d15_low: float,
    symbol: str,
) -> Optional[dict]:
    """
    Return the first post-scan breakout already present in today's candles.
    """
    if df.empty:
        return None

    today_date = df.index[-1].date()
    today_df = df[df.index.date == today_date]
    post_scan = today_df.between_time("10:15", "23:59")
    if post_scan.empty:
        return None

    current_ltp = post_scan["close"].iloc[-1]

    long_breaks = post_scan[post_scan["close"] > d15_high]
    if not long_breaks.empty:
        first = long_breaks.iloc[0]
        return {
            "symbol": symbol,
            "direction": "LONG",
            "d15_high": d15_high,
            "d15_low": d15_low,
            "breakout_price": first["close"],
            "breakout_time": first.name.strftime("%H:%M"),
            "current_ltp": current_ltp,
        }

    short_breaks = post_scan[post_scan["close"] < d15_low]
    if not short_breaks.empty:
        first = short_breaks.iloc[0]
        return {
            "symbol": symbol,
            "direction": "SHORT",
            "d15_high": d15_high,
            "d15_low": d15_low,
            "breakout_price": first["close"],
            "breakout_time": first.name.strftime("%H:%M"),
            "current_ltp": current_ltp,
        }

    return None
