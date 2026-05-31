"""
Tests for live 3Candle setup evaluation helpers.
"""

import pandas as pd

from live.setup import evaluate_morning_setup, find_missed_breakout
from tests.test_strategy import create_synthetic_day


def test_evaluate_morning_setup_qualifies_valid_day():
    df = create_synthetic_day(
        ib_high=100,
        ib_low=90,
        inside_candles=5,
        breakout_direction="LONG",
        breakout_price=101,
    )

    setup = evaluate_morning_setup(df, min_inside_candles=3)

    assert setup is not None
    assert setup["d15_high"] == 100
    assert setup["d15_low"] == 90
    assert setup["pivots"] == sorted(setup["pivots"])
    assert len(setup["pivots"]) == 9


def test_evaluate_morning_setup_rejects_range_break():
    df = create_synthetic_day(
        ib_high=100,
        ib_low=90,
        inside_candles=2,
        breakout_direction="LONG",
        breakout_price=101,
    )

    assert evaluate_morning_setup(df, min_inside_candles=3) is None


def test_find_missed_breakout_detects_first_post_scan_break():
    index = pd.to_datetime([
        "2024-01-01 09:15",
        "2024-01-01 15:29",
        "2024-01-02 10:15",
        "2024-01-02 10:16",
    ])
    df = pd.DataFrame({
        "open": [95, 95, 99, 102],
        "high": [100, 100, 103, 104],
        "low": [90, 90, 98, 101],
        "close": [95, 95, 101, 103],
        "volume": [1000, 1000, 5000, 5000],
    }, index=index)

    missed = find_missed_breakout(df, d15_high=100, d15_low=90, symbol="TEST")

    assert missed is not None
    assert missed["symbol"] == "TEST"
    assert missed["direction"] == "LONG"
    assert missed["breakout_time"] == "10:15"
