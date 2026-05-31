"""Tests for Nifty options spread planning."""

from options_trading.config import OptionsTradingSettings
from options_trading.execution import NiftySpreadPlanner


class DummyBroker:
    def __init__(self, contracts):
        self.contracts = contracts

    def get_option_contracts(self, underlying_key, expiry_date=None):
        return self.contracts


def _contract(strike, option_type, expiry="2026-05-28", lot_size=50):
    return {
        "expiry": expiry,
        "instrument_key": f"NSE_FO|{strike}{option_type}",
        "trading_symbol": f"NIFTY {strike} {option_type}",
        "strike_price": strike,
        "instrument_type": option_type,
        "lot_size": lot_size,
        "minimum_lot": lot_size,
    }


def _planner(contracts):
    settings = OptionsTradingSettings()
    settings.NIFTY_OPTION_LOTS = 1
    settings.NIFTY_OPTION_STRIKE_STEP = 50
    settings.NIFTY_OPTION_SELL_OFFSET = 500
    settings.NIFTY_OPTION_HEDGE_OFFSET = 1000
    settings.NIFTY_FUTURES_KEY = "NSE_FO|NIFTY_FUT"
    return NiftySpreadPlanner(settings), DummyBroker(contracts)


def test_long_signal_builds_bear_call_spread():
    planner, broker = _planner([
        _contract(24500, "CE"),
        _contract(25000, "CE"),
    ])

    plan = planner.build_plan("LONG", 24000, broker.contracts, expiry_date="2026-05-28")

    assert plan.short_leg.transaction_type == "SELL"
    assert plan.short_leg.strike == 24500
    assert plan.short_leg.option_type == "CE"
    assert plan.hedge_leg.transaction_type == "BUY"
    assert plan.hedge_leg.strike == 25000
    assert plan.hedge_leg.option_type == "CE"


def test_short_signal_builds_bull_put_spread():
    planner, broker = _planner([
        _contract(22500, "PE"),
        _contract(22000, "PE"),
    ])

    plan = planner.build_plan("SHORT", 23000, broker.contracts, expiry_date="2026-05-28")

    assert plan.short_leg.transaction_type == "SELL"
    assert plan.short_leg.strike == 22500
    assert plan.short_leg.option_type == "PE"
    assert plan.hedge_leg.transaction_type == "BUY"
    assert plan.hedge_leg.strike == 22000
    assert plan.hedge_leg.option_type == "PE"
