"""
Nifty option spread planner.

Converts a Nifty futures directional signal into a defined-risk Nifty option
credit spread.
"""

from datetime import date
from typing import Optional, List

import pandas as pd

from options_trading.config import OptionsTradingSettings
from options_trading.models import OptionLeg, SpreadPlan


class NiftySpreadPlanner:
    """Builds the option legs for the configured Nifty spread rule."""

    def __init__(self, settings: OptionsTradingSettings):
        self.settings = settings

    def build_plan(
        self,
        signal_direction: str,
        signal_ltp: float,
        contracts: List[dict],
        expiry_date: Optional[str] = None,
    ) -> Optional[SpreadPlan]:
        if not contracts:
            return None

        expiry = expiry_date or self.nearest_expiry(contracts)
        expiry_contracts = [c for c in contracts if c.get("expiry") == expiry]
        if not expiry_contracts:
            return None

        base = self.round_to_strike(signal_ltp)
        if signal_direction == "LONG":
            option_type = "CE"
            short_strike = base + self.settings.NIFTY_OPTION_SELL_OFFSET
            hedge_strike = base + self.settings.NIFTY_OPTION_HEDGE_OFFSET
        else:
            option_type = "PE"
            short_strike = base - self.settings.NIFTY_OPTION_SELL_OFFSET
            hedge_strike = base - self.settings.NIFTY_OPTION_HEDGE_OFFSET

        short_contract = self.find_contract(expiry_contracts, short_strike, option_type)
        hedge_contract = self.find_contract(expiry_contracts, hedge_strike, option_type)
        if not short_contract or not hedge_contract:
            return None

        quantity = int(short_contract.get("lot_size", short_contract.get("minimum_lot", 0)))
        quantity *= self.settings.NIFTY_OPTION_LOTS
        if quantity <= 0:
            return None

        return SpreadPlan(
            signal_direction=signal_direction,
            signal_ltp=signal_ltp,
            base_strike=base,
            expiry=expiry,
            hedge_leg=self.make_leg("BUY", hedge_contract, quantity, "HEDGE"),
            short_leg=self.make_leg("SELL", short_contract, quantity, "SHORT"),
        )

    def round_to_strike(self, price: float) -> int:
        step = self.settings.NIFTY_OPTION_STRIKE_STEP
        return int(round(price / step) * step)

    def nearest_expiry(self, contracts: List[dict]) -> str:
        expiries = sorted({
            c.get("expiry")
            for c in contracts
            if c.get("expiry") and pd.to_datetime(c.get("expiry")).date() >= date.today()
        })
        if not expiries:
            raise ValueError("No current or future Nifty option expiries returned")
        return expiries[0]

    def find_contract(self, contracts: List[dict], strike: int, option_type: str) -> Optional[dict]:
        for contract in contracts:
            if (
                int(float(contract.get("strike_price", -1))) == strike
                and contract.get("instrument_type") == option_type
            ):
                return contract
        return None

    def make_leg(
        self,
        transaction_type: str,
        contract: dict,
        quantity: int,
        role: str,
    ) -> OptionLeg:
        return OptionLeg(
            transaction_type=transaction_type,
            instrument_key=contract["instrument_key"],
            trading_symbol=contract["trading_symbol"],
            strike=float(contract["strike_price"]),
            option_type=contract["instrument_type"],
            quantity=quantity,
            role=role,
        )

