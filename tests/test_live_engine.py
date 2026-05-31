"""
Tests for live engine watchlist decisions.
"""

from live.engine import LiveEngine
from config.settings import Settings
from tests.test_strategy import create_synthetic_day


class DummyFetcher:
    def __init__(self, df):
        self.df = df

    def fetch_combined(self, instrument_key, history_days=3):
        return self.df


class DummyNotifier:
    def __init__(self):
        self.missed = []
        self.messages = []

    def send(self, message):
        self.messages.append(message)
        return True

    def send_missed_breakouts(self, missed):
        self.missed.extend(missed)
        return True


def _observer():
    return [{
        "signal_key": "NSE_EQ|TEST",
        "symbol": "TEST",
        "execution_key": "NSE_EQ|TEST",
        "execution_symbol": "TEST",
    }]


def _settings():
    settings = Settings()
    settings.LIVE_SCAN_SLEEP = 0
    return settings


def test_build_watchlist_skips_breakout_that_happened_before_startup():
    df = create_synthetic_day(
        ib_high=100,
        ib_low=90,
        inside_candles=5,
        breakout_direction="LONG",
        breakout_price=101,
    )
    engine = LiveEngine(_settings())
    engine.fetcher = DummyFetcher(df)
    engine.notifier = DummyNotifier()

    watchlist = engine._build_watchlist(_observer())

    assert watchlist == {}
    assert len(engine.notifier.missed) == 1
    assert engine.notifier.missed[0]["symbol"] == "TEST"
    assert engine.notifier.missed[0]["direction"] == "LONG"


def test_build_watchlist_keeps_qualified_setup_without_pre_start_breakout():
    df = create_synthetic_day(
        ib_high=100,
        ib_low=90,
        inside_candles=5,
        breakout_direction="LONG",
        breakout_price=95,
    )
    engine = LiveEngine(_settings())
    engine.fetcher = DummyFetcher(df)
    engine.notifier = DummyNotifier()

    watchlist = engine._build_watchlist(_observer())

    assert list(watchlist) == ["NSE_EQ|TEST"]
    assert watchlist["NSE_EQ|TEST"]["state"] == "WAITING_BREAKOUT"
    assert engine.notifier.missed == []
