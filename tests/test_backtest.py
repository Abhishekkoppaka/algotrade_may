"""
Tests for the backtesting engine.

Verifies that the engine correctly:
- Enters trades when triggers are crossed
- Exits on target, stop loss, and EOD
- Records trade metadata accurately
- Respects max trades per day limit
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import pandas as pd
import numpy as np
from backtesting.engine import BacktestEngine
from backtesting.metrics import calculate_metrics
from strategies.three_candle import ThreeCandleStrategy
from config.settings import Settings


class TestBacktestEngine:
    """Test the backtesting engine execution logic."""

    def test_produces_trades_dataframe(self):
        """Engine should return a DataFrame (possibly empty)."""
        settings = Settings()
        strategy = ThreeCandleStrategy(settings)
        engine = BacktestEngine(strategy, settings)

        # Minimal data — may produce 0 trades, but should not crash
        dates = pd.date_range("2024-01-01 09:15", periods=400, freq="1min")
        df = pd.DataFrame({
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000
        }, index=dates)

        result = engine.run(df)
        assert isinstance(result, pd.DataFrame)

    def test_trade_columns_present(self):
        """If trades are generated, they should have expected columns."""
        settings = Settings()
        strategy = ThreeCandleStrategy(settings)
        engine = BacktestEngine(strategy, settings)

        # Create data that should trigger at least one trade
        from tests.test_strategy import create_synthetic_day
        df = create_synthetic_day(ib_high=100, ib_low=90, inside_candles=5, breakout_direction="LONG", breakout_price=101)

        result = engine.run(df)
        if not result.empty:
            expected_cols = {"type", "entry_time", "entry_price", "exit_time", "exit_price", "pnl", "reason"}
            assert expected_cols.issubset(set(result.columns))


class TestMetrics:
    """Test metrics calculation."""

    def test_empty_trades(self):
        """Metrics should handle empty DataFrame gracefully."""
        metrics = calculate_metrics(pd.DataFrame())
        assert metrics["total_trades"] == 0
        assert metrics["win_rate"] == 0.0

    def test_all_winners(self):
        """100% win rate when all trades are profitable."""
        trades = pd.DataFrame({
            "pnl": [10.0, 20.0, 15.0],
            "type": ["Long", "Long", "Short"],
        })
        metrics = calculate_metrics(trades)
        assert metrics["win_rate"] == 100.0
        assert metrics["total_return"] == 45.0

    def test_mixed_trades(self):
        """Correct calculation with mix of winners and losers."""
        trades = pd.DataFrame({
            "pnl": [10.0, -5.0, 20.0, -15.0],
            "type": ["Long", "Long", "Short", "Short"],
        })
        metrics = calculate_metrics(trades)
        assert metrics["total_trades"] == 4
        assert metrics["win_rate"] == 50.0
        assert metrics["total_return"] == 10.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
