"""Tests for the two-window pivot reversal backtest and live signal logic."""

from datetime import datetime

import pandas as pd
import pytest

from backtesting.engine import BacktestEngine
from config.settings import Settings
from options_trading.engines.nifty_two_window_pivot_reversal_live import (
    NiftyTwoWindowPivotReversalOptionsLiveEngine,
)
from options_trading.models import OptionLeg, SpreadPlan
from options_trading.strategies.nifty_futures_two_window_pivot_reversal import (
    NiftyFuturesTwoWindowPivotReversalStrategy,
)
from strategies.two_window_pivot_reversal import (
    TwoWindowPivotReversalStrategy,
    build_two_window_pivot_setup,
)


def _window_df(
    second_high: float = 110.0,
    second_low: float = 99.0,
) -> pd.DataFrame:
    rows = []
    index = pd.date_range("2026-05-29 09:15", "2026-05-29 09:44", freq="1min")
    for timestamp in index:
        if timestamp.time() < datetime.strptime("09:30", "%H:%M").time():
            rows.append({"open": 105.0, "high": 110.0, "low": 100.0, "close": 105.0})
        else:
            rows.append({
                "open": 105.0,
                "high": second_high,
                "low": second_low,
                "close": 105.0,
            })
    return pd.DataFrame(rows, index=index)


def _historical_and_today(include_signal: bool = True) -> pd.DataFrame:
    previous = pd.DataFrame(
        [{"open": 105.0, "high": 120.0, "low": 90.0, "close": 105.0, "volume": 1000}],
        index=[pd.Timestamp("2026-05-28 15:15")],
    )
    index = pd.date_range("2026-05-29 09:15", "2026-05-29 14:45", freq="1min")
    rows = []
    for timestamp in index:
        if timestamp.time() < datetime.strptime("09:30", "%H:%M").time():
            row = {"open": 107.0, "high": 115.0, "low": 100.0, "close": 107.0, "volume": 1000}
        elif timestamp.time() < datetime.strptime("09:45", "%H:%M").time():
            row = {"open": 105.0, "high": 110.0, "low": 99.0, "close": 105.0, "volume": 1000}
        else:
            row = {"open": 107.0, "high": 109.0, "low": 106.0, "close": 107.0, "volume": 1000}
        rows.append(row)

    today = pd.DataFrame(rows, index=index)
    if include_signal:
        today.loc["2026-05-29 10:00"] = {
            "open": 110.0, "high": 112.0, "low": 109.0, "close": 111.0, "volume": 1000,
        }
        today.loc["2026-05-29 10:01"] = {
            "open": 107.0, "high": 109.0, "low": 106.0, "close": 108.0, "volume": 1000,
        }
        today.loc["2026-05-29 10:02"] = {
            "open": 112.0, "high": 115.0, "low": 111.0, "close": 114.0, "volume": 1000,
        }
    return pd.concat([previous, today])


def test_low_break_only_builds_long_setup_with_nearest_strict_levels():
    setup = build_two_window_pivot_setup(_window_df(), [95.0, 105.0, 109.0, 120.0])
    assert setup is not None
    assert setup.direction == "LONG"
    assert setup.trigger_price == 110.0
    assert setup.target_price == 120.0
    assert setup.stop_loss_price == 109.0


@pytest.mark.parametrize(
    ("second_high", "second_low"),
    [
        (110.0, 100.0),  # Neither side strictly breaks; touching is not enough.
        (111.0, 99.0),   # Both sides strictly break.
    ],
)
def test_setup_rejects_neither_or_both_side_breaks(second_high, second_low):
    assert build_two_window_pivot_setup(
        _window_df(second_high=second_high, second_low=second_low),
        [95.0, 105.0, 120.0],
    ) is None


def test_high_break_only_builds_short_setup():
    setup = build_two_window_pivot_setup(
        _window_df(second_high=111.0, second_low=102.0),
        [95.0, 101.0, 105.0, 120.0],
    )
    assert setup is not None
    assert setup.direction == "SHORT"
    assert setup.trigger_price == 102.0
    assert setup.target_price == 101.0
    assert setup.stop_loss_price == 105.0


def test_backtest_enters_at_next_candle_open_after_confirmed_close():
    engine = BacktestEngine(TwoWindowPivotReversalStrategy(Settings()), Settings())
    trades = engine.run(_historical_and_today())
    assert len(trades) == 1
    trade = trades.iloc[0]
    assert trade["type"] == "Long"
    assert trade["entry_time"] == pd.Timestamp("2026-05-29 10:01")
    assert trade["entry_price"] == 107.0
    assert trade["exit_time"] == pd.Timestamp("2026-05-29 10:02")
    assert trade["exit_price"] == 115.0
    assert trade["reason"] == "Target"


@pytest.mark.parametrize("gap_open", [95.0, 115.0])
def test_backtest_skips_long_entry_when_next_open_reaches_stop_or_target(gap_open):
    df = _historical_and_today()
    df.loc["2026-05-29 10:01", ["open", "high", "low", "close"]] = [
        gap_open, gap_open, gap_open, gap_open,
    ]
    engine = BacktestEngine(TwoWindowPivotReversalStrategy(Settings()), Settings())
    assert engine.run(df).empty


def test_live_strategy_emits_only_after_fresh_completed_signal_candle():
    strategy = NiftyFuturesTwoWindowPivotReversalStrategy()
    df = _historical_and_today(include_signal=False).loc[:"2026-05-29 09:44"]
    qualified, missed = strategy.prepare_setup(df, as_of=datetime(2026, 5, 29, 9, 45))
    assert qualified is True
    assert missed is None

    fresh = pd.concat([
        df,
        pd.DataFrame(
            [{"open": 110.0, "high": 112.0, "low": 109.0, "close": 111.0, "volume": 1000}],
            index=[pd.Timestamp("2026-05-29 09:45")],
        ),
    ])
    assert strategy.get_signal(fresh, as_of=datetime(2026, 5, 29, 9, 45, 30)) is None
    signal = strategy.get_signal(fresh, as_of=datetime(2026, 5, 29, 9, 46))
    assert signal is not None
    assert signal["direction"] == "LONG"
    assert signal["signal_time"] == pd.Timestamp("2026-05-29 09:45")


def test_live_strategy_rejects_signal_that_completed_before_startup():
    strategy = NiftyFuturesTwoWindowPivotReversalStrategy()
    df = _historical_and_today(include_signal=False).loc[:"2026-05-29 09:44"]
    df = pd.concat([
        df,
        pd.DataFrame(
            [{"open": 110.0, "high": 112.0, "low": 109.0, "close": 111.0, "volume": 1000}],
            index=[pd.Timestamp("2026-05-29 09:45")],
        ),
    ])
    qualified, missed = strategy.prepare_setup(df, as_of=datetime(2026, 5, 29, 9, 46))
    assert qualified is False
    assert missed is not None
    assert missed["signal_time"] == pd.Timestamp("2026-05-29 09:45")


def test_live_engine_stops_automatic_retries_after_partial_exit_failure():
    engine = NiftyTwoWindowPivotReversalOptionsLiveEngine.__new__(
        NiftyTwoWindowPivotReversalOptionsLiveEngine
    )
    engine.active_spread = SpreadPlan(
        signal_direction="LONG",
        signal_ltp=110.0,
        base_strike=100,
        expiry="2026-06-04",
        hedge_leg=OptionLeg("BUY", "HEDGE", "HEDGE", 200.0, "CE", 50, "HEDGE"),
        short_leg=OptionLeg("SELL", "SHORT", "SHORT", 150.0, "CE", 50, "SHORT"),
    )
    engine.active_signal = {"direction": "LONG"}
    engine.exit_failed = False
    orders = []

    def place_and_confirm(leg):
        orders.append(leg)
        return "order-id" if len(orders) == 1 else None

    class Notifier:
        def send(self, _message):
            return True

    engine._place_and_confirm = place_and_confirm
    engine.notifier = Notifier()

    engine._close_active_spread("test failure")
    engine._close_active_spread("must not retry")

    assert engine.exit_failed is True
    assert [leg.role for leg in orders] == ["EXIT-SHORT", "EXIT-HEDGE"]


@pytest.mark.parametrize(
    ("direction", "ltp", "expected"),
    [
        ("LONG", 105.0, True),
        ("LONG", 100.0, False),
        ("LONG", 110.0, False),
        ("SHORT", 105.0, True),
        ("SHORT", 100.0, False),
        ("SHORT", 110.0, False),
    ],
)
def test_live_engine_rejects_entry_price_at_or_beyond_target_or_stop(
    direction, ltp, expected
):
    signal = {
        "direction": direction,
        "target_price": 110.0 if direction == "LONG" else 100.0,
        "stop_loss_price": 100.0 if direction == "LONG" else 110.0,
    }
    assert (
        NiftyTwoWindowPivotReversalOptionsLiveEngine._is_entry_price_valid(signal, ltp)
        is expected
    )


def _make_live_exit_engine(ltp, candles=None, direction="LONG"):
    engine = NiftyTwoWindowPivotReversalOptionsLiveEngine.__new__(
        NiftyTwoWindowPivotReversalOptionsLiveEngine
    )
    engine.settings = type("Settings", (), {"NIFTY_FUTURES_KEY": "NIFTY-FUT"})()
    engine.active_signal = {
        "direction": direction,
        "target_price": 110.0 if direction == "LONG" else 100.0,
        "stop_loss_price": 100.0 if direction == "LONG" else 110.0,
    }
    engine.spread_entry_timestamp = pd.Timestamp("2026-05-29 10:03:00")
    engine.last_stop_check_timestamp = engine.spread_entry_timestamp
    engine.broker = type("Broker", (), {"get_ltp": lambda _self, _key: ltp})()

    class Fetcher:
        def __init__(self):
            self.calls = 0

        def fetch_intraday(self, _key):
            self.calls += 1
            return candles if candles is not None else pd.DataFrame()

    engine.fetcher = Fetcher()
    reasons = []
    engine._close_active_spread = reasons.append
    return engine, reasons


def test_live_engine_closes_target_immediately_from_ltp_without_fetching_candles():
    engine, reasons = _make_live_exit_engine(ltp=110.0)
    engine._check_underlying_exit(now=datetime(2026, 5, 29, 10, 3, 30))
    assert reasons == ["Futures target reached"]
    assert engine.fetcher.calls == 0


def test_live_engine_closes_short_target_immediately_from_ltp():
    engine, reasons = _make_live_exit_engine(ltp=100.0, direction="SHORT")
    engine._check_underlying_exit(now=datetime(2026, 5, 29, 10, 3, 30))
    assert reasons == ["Futures target reached"]
    assert engine.fetcher.calls == 0


def test_live_engine_does_not_close_stop_from_ltp_without_completed_five_minute_bar():
    engine, reasons = _make_live_exit_engine(ltp=95.0)
    engine._check_underlying_exit(now=datetime(2026, 5, 29, 10, 4, 30))
    assert reasons == []
    assert engine.fetcher.calls == 0


def test_live_engine_closes_stop_from_completed_five_minute_candle_close():
    candles = pd.DataFrame(
        [{"close": 99.0}],
        index=[pd.Timestamp("2026-05-29 10:04:00")],
    )
    engine, reasons = _make_live_exit_engine(ltp=99.0, candles=candles)
    engine._check_underlying_exit(now=datetime(2026, 5, 29, 10, 5, 0))
    assert reasons == [
        "Futures 5-minute close stop reached at 10:04 (close 99.00)"
    ]
    assert engine.fetcher.calls == 1


def test_live_engine_closes_short_stop_from_completed_five_minute_candle_close():
    candles = pd.DataFrame(
        [{"close": 111.0}],
        index=[pd.Timestamp("2026-05-29 10:04:00")],
    )
    engine, reasons = _make_live_exit_engine(
        ltp=111.0,
        candles=candles,
        direction="SHORT",
    )
    engine._check_underlying_exit(now=datetime(2026, 5, 29, 10, 5, 0))
    assert reasons == [
        "Futures 5-minute close stop reached at 10:04 (close 111.00)"
    ]
    assert engine.fetcher.calls == 1


def test_live_engine_fetches_stop_candles_only_once_per_new_five_minute_boundary():
    candles = pd.DataFrame(
        [{"close": 101.0}],
        index=[pd.Timestamp("2026-05-29 10:04:00")],
    )
    engine, reasons = _make_live_exit_engine(ltp=101.0, candles=candles)
    engine._check_underlying_exit(now=datetime(2026, 5, 29, 10, 5, 0))
    engine._check_underlying_exit(now=datetime(2026, 5, 29, 10, 5, 30))
    assert reasons == []
    assert engine.fetcher.calls == 1
