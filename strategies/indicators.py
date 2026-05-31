"""
Shared Technical Indicators

Contains all pivot point calculations and helper functions used across
multiple strategies. This is the SINGLE source of truth for:
- Floor Pivot Points (PP, R1-R3, S1-S3)
- Central Pivot Range (BC, TC)
- Camarilla Pivot Points (H3-H5, L3-L5)
- Pivot-relative price mapping (find next pivot above/below a price)

No strategy should re-implement these calculations.
"""

import pandas as pd
import numpy as np
from typing import List


# ===========================================================================
# Floor Pivot Points (Standard)
# ===========================================================================

def calculate_floor_pivots(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate standard Floor Pivot Points from previous day's OHLC.

    Pivot Point = (High + Low + Close) / 3
    R1 = 2*PP - Low          S1 = 2*PP - High
    R2 = PP + (High - Low)   S2 = PP - (High - Low)
    R3 = High + 2*(PP - Low) S3 = Low - 2*(High - PP)

    Also includes Previous Day High (PDH) and Previous Day Low (PDL)
    as additional support/resistance levels.

    Args:
        df: OHLCV DataFrame with DateTimeIndex.

    Returns:
        DataFrame with pivot columns added:
        PDH, PDL, PDC, vPP, vBC, vTC, vR1, vR2, vR3, vS1, vS2, vS3
    """
    df = df.copy()
    df["date"] = df.index.date

    # Aggregate to daily OHLC
    daily = df.groupby("date").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    })

    # Previous Day values (shifted by 1 day)
    daily["PDH"] = daily["high"].shift(1)
    daily["PDL"] = daily["low"].shift(1)
    daily["PDC"] = daily["close"].shift(1)

    # Floor Pivot calculations
    daily["vPP"] = (daily["PDH"] + daily["PDL"] + daily["PDC"]) / 3
    daily["vR1"] = daily["vPP"] + (daily["vPP"] - daily["PDL"])
    daily["vS1"] = daily["vPP"] - (daily["PDH"] - daily["vPP"])
    daily["vR2"] = daily["vPP"] + (daily["PDH"] - daily["PDL"])
    daily["vS2"] = daily["vPP"] - (daily["PDH"] - daily["PDL"])
    daily["vR3"] = daily["PDH"] + 2 * (daily["vPP"] - daily["PDL"])
    daily["vS3"] = daily["PDL"] - 2 * (daily["PDH"] - daily["vPP"])
    raw_bc = (daily["PDH"] + daily["PDL"]) / 2
    raw_tc = (2 * daily["vPP"]) - raw_bc
    daily["vBC"] = np.minimum(raw_bc, raw_tc)
    daily["vTC"] = np.maximum(raw_bc, raw_tc)

    # Merge daily pivots back to intraday timeframe
    pivot_cols = [
        "PDH", "PDL", "PDC", "vPP", "vBC", "vTC",
        "vR1", "vS1", "vR2", "vS2", "vR3", "vS3",
    ]
    merged = df.merge(daily[pivot_cols], left_on="date", right_index=True)
    merged.drop(columns=["date"], inplace=True)

    return merged


def calculate_floor_pivots_from_ohlc(
    prev_high: float, prev_low: float, prev_close: float
) -> dict:
    """
    Calculate floor pivots from explicit previous day OHLC values.

    Useful in live trading where we already know yesterday's values
    and don't need to compute from a full DataFrame.

    Args:
        prev_high: Previous day's high price.
        prev_low: Previous day's low price.
        prev_close: Previous day's closing price.

    Returns:
        Dictionary with keys: PP, BC, TC, R1, R2, R3, S1, S2, S3, PDH, PDL
    """
    pp = (prev_high + prev_low + prev_close) / 3
    raw_bc = (prev_high + prev_low) / 2
    raw_tc = (2 * pp) - raw_bc
    return {
        "PP": pp,
        "BC": min(raw_bc, raw_tc),
        "TC": max(raw_bc, raw_tc),
        "R1": pp + (pp - prev_low),
        "R2": pp + (prev_high - prev_low),
        "R3": prev_high + 2 * (pp - prev_low),
        "S1": pp - (prev_high - pp),
        "S2": pp - (prev_high - prev_low),
        "S3": prev_low - 2 * (prev_high - pp),
        "PDH": prev_high,
        "PDL": prev_low,
    }


# ===========================================================================
# Camarilla Pivot Points
# ===========================================================================

def calculate_camarilla_pivots(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate Camarilla Pivot Points from previous day's HLC.

    Camarilla levels use a constant multiplier applied to range:
    H3 = Close + Range * 1.1/4     L3 = Close - Range * 1.1/4
    H4 = Close + Range * 1.1/2     L4 = Close - Range * 1.1/2
    H5 = (High/Low) * Close        L5 = Close - (H5 - Close)

    Args:
        df: OHLCV DataFrame with DateTimeIndex.

    Returns:
        DataFrame with Camarilla pivot columns: cL3, cH3, cL4, cH4, cL5, cH5
    """
    df = df.copy()
    df["date"] = df.index.date

    daily = df.groupby("date").agg({
        "high": "max",
        "low": "min",
        "close": "last",
    })

    # Camarilla range
    daily["cRange"] = daily["high"] - daily["low"]

    # Core Camarilla levels
    daily["cL3"] = daily["close"] - daily["cRange"] * (1.1 / 4)
    daily["cH3"] = daily["close"] + daily["cRange"] * (1.1 / 4)
    daily["cL4"] = daily["close"] - daily["cRange"] * (1.1 / 2)
    daily["cH4"] = daily["close"] + daily["cRange"] * (1.1 / 2)

    # H5/L5 — extreme levels based on range ratio
    daily["cH5"] = (daily["high"] / daily["low"]) * daily["close"]
    daily["cL5"] = daily["close"] - (daily["cH5"] - daily["close"])

    # Shift to apply previous day's levels to current day
    pivot_cols = ["cL3", "cH3", "cL4", "cH4", "cL5", "cH5"]
    daily_shifted = daily[pivot_cols].shift(1)

    # Merge back to intraday
    df = df.join(daily_shifted, on="date")
    df.drop(columns=["date"], inplace=True)

    return df


# ===========================================================================
# Pivot Navigation Helpers
# ===========================================================================

def get_sorted_pivot_levels(pivot_dict: dict) -> List[float]:
    """
    Get all pivot levels sorted ascending for binary search.

    Args:
        pivot_dict: Dictionary of pivot name → price (from calculate_floor_pivots_from_ohlc).

    Returns:
        Sorted list of all pivot prices.
    """
    return sorted(pivot_dict.values())


def get_next_pivot_above(price: float, sorted_pivots: List[float]) -> float:
    """
    Find the nearest pivot level ABOVE a given price.

    Used to determine target for LONG trades or stop-loss for SHORT trades.

    Args:
        price: Reference price to search above.
        sorted_pivots: Ascending-sorted list of pivot levels.

    Returns:
        The first pivot above the price, or price + 100 as fallback
        (ensures we always have a target even beyond R3).
    """
    for p in sorted_pivots:
        if p > price:
            return p
    # Fallback: if price is above all pivots, use a fixed offset
    return price + 100.0


def get_next_pivot_below(price: float, sorted_pivots: List[float]) -> float:
    """
    Find the nearest pivot level BELOW a given price.

    Used to determine target for SHORT trades or stop-loss for LONG trades.

    Args:
        price: Reference price to search below.
        sorted_pivots: Ascending-sorted list of pivot levels.

    Returns:
        The first pivot below the price, or price - 100 as fallback
        (ensures we always have a stop even below S3).
    """
    for p in reversed(sorted_pivots):
        if p < price:
            return p
    # Fallback: if price is below all pivots, use a fixed offset
    return price - 100.0
