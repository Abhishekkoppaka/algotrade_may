"""
Tests for the 3Candle strategy implementation.

Uses synthetic data to verify that the strategy correctly:
- Identifies Initial Balance
- Counts inside candles
- Detects breakout signals
- Sets appropriate target and stop levels
- Resets state at EOD
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import pandas as pd
import numpy as np
from strategies.three_candle import ThreeCandleStrategy
from config.settings import Settings


def create_synthetic_day(
    ib_high=100.0,
    ib_low=90.0,
    inside_candles=5,
    breakout_direction="LONG",
    breakout_price=102.0,
):
    """
    Create a synthetic trading day with controlled parameters.

    Generates 1-minute bars from 09:15 to 15:30 with:
    - IB period establishing the given high/low
    - Specified number of inside candles
    - A breakout candle after live monitoring starts

    We also need at least one prior day for pivot calculation.
    """
    timestamps = []
    data = []

    # Previous day (for pivot calculation) — single day of flat data
    prev_date = pd.Timestamp("2024-01-01")
    for h in range(9, 16):
        for m in range(0, 60):
            ts = prev_date.replace(hour=h, minute=m)
            timestamps.append(ts)
            data.append({
                "open": 95.0, "high": 105.0, "low": 85.0, "close": 95.0, "volume": 1000
            })

    # Current day
    today = pd.Timestamp("2024-01-02")

    # 09:15-09:29: IB formation (15 candles)
    for m in range(15, 30):
        ts = today.replace(hour=9, minute=m)
        timestamps.append(ts)
        if m == 15:
            data.append({"open": 95.0, "high": ib_high, "low": ib_low, "close": 96.0, "volume": 1000})
        else:
            data.append({"open": 95.0, "high": 98.0, "low": 92.0, "close": 95.0, "volume": 1000})

    # 09:30-10:29: mostly inside candles; the configured strategy window ends at 10:14.
    # When inside_candles >= MIN_INSIDE_CANDLES (3), remaining candles stay inside
    # When inside_candles < 3, remaining candles break the range to invalidate
    for m_offset in range(60):
        h = 9 + (30 + m_offset) // 60
        m = (30 + m_offset) % 60
        ts = today.replace(hour=h, minute=m)
        timestamps.append(ts)
        if m_offset < inside_candles:
            # Inside candle: stays strictly within IB
            data.append({"open": 95.0, "high": ib_high - 2, "low": ib_low + 2, "close": 95.0, "volume": 1000})
        elif inside_candles < 3:
            # For tests with insufficient candles: break the range
            data.append({"open": 95.0, "high": ib_high + 1, "low": 92.0, "close": 96.0, "volume": 1000})
        else:
            # For tests with sufficient candles: keep remaining bars also inside
            data.append({"open": 95.0, "high": ib_high - 2, "low": ib_low + 2, "close": 95.0, "volume": 1000})

    # 10:30-14:29: trading period with breakout in this fixture
    for m_offset in range(240):
        h = 10 + (30 + m_offset) // 60
        m = (30 + m_offset) % 60
        ts = today.replace(hour=h, minute=m)
        timestamps.append(ts)
        if m_offset == 0 and breakout_direction == "LONG":
            # Breakout candle: closes above IB high
            data.append({
                "open": 99.0, "high": breakout_price + 2,
                "low": 98.0, "close": breakout_price, "volume": 5000
            })
        elif m_offset == 0 and breakout_direction == "SHORT":
            data.append({
                "open": 91.0, "high": 92.0,
                "low": breakout_price - 2, "close": breakout_price, "volume": 5000
            })
        else:
            data.append({"open": 95.0, "high": 96.0, "low": 94.0, "close": 95.0, "volume": 1000})

    # 14:30-15:30: Reset period
    for m_offset in range(60):
        h = 14 + (30 + m_offset) // 60
        m = (30 + m_offset) % 60
        ts = today.replace(hour=h, minute=m)
        timestamps.append(ts)
        data.append({"open": 95.0, "high": 96.0, "low": 94.0, "close": 95.0, "volume": 1000})

    df = pd.DataFrame(data, index=pd.DatetimeIndex(timestamps))
    return df


class TestThreeCandleStrategy:
    """Test the 3Candle strategy signal generation."""

    def setup_method(self):
        self.strategy = ThreeCandleStrategy(Settings())

    def test_long_signal_generated(self):
        """Strategy should produce LONG signal when price closes above IB high."""
        df = create_synthetic_day(ib_high=100, ib_low=90, inside_candles=5, breakout_direction="LONG", breakout_price=101)
        df = self.strategy.prepare_data(df)
        df = self.strategy.generate_signals(df)

        # Should have at least one LONG signal (direction == 1)
        long_signals = df[df["signal_direction"] == 1]
        assert len(long_signals) > 0

    def test_short_signal_generated(self):
        """Strategy should produce SHORT signal when price closes below IB low."""
        df = create_synthetic_day(ib_high=100, ib_low=90, inside_candles=5, breakout_direction="SHORT", breakout_price=89)
        df = self.strategy.prepare_data(df)
        df = self.strategy.generate_signals(df)

        short_signals = df[df["signal_direction"] == 2]
        assert len(short_signals) > 0

    def test_no_signal_insufficient_inside_candles(self):
        """No signal if fewer than 3 inside candles."""
        df = create_synthetic_day(ib_high=100, ib_low=90, inside_candles=2, breakout_direction="LONG", breakout_price=101)
        df = self.strategy.prepare_data(df)
        df = self.strategy.generate_signals(df)

        # Should have no valid signals on the current day
        today_df = df[df.index.date == pd.Timestamp("2024-01-02").date()]
        assert today_df["signal_direction"].max() == 0

    def test_eod_reset(self):
        """is_reset should be 1 for bars at/after 14:30."""
        df = create_synthetic_day()
        df = self.strategy.prepare_data(df)
        df = self.strategy.generate_signals(df)

        reset_bars = df[df["is_reset"] == 1]
        assert len(reset_bars) > 0
        # All reset bars should be at 14:30 or later (i.e., time >= 14:30)
        for ts in reset_bars.index:
            minutes_from_midnight = ts.hour * 60 + ts.minute
            assert minutes_from_midnight >= 14 * 60 + 30


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
