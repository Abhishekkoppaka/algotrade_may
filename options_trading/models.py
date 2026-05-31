"""Domain models for options spread planning and execution."""

from dataclasses import dataclass


@dataclass
class OptionLeg:
    transaction_type: str
    instrument_key: str
    trading_symbol: str
    strike: float
    option_type: str
    quantity: int
    role: str


@dataclass
class SpreadPlan:
    signal_direction: str
    signal_ltp: float
    base_strike: int
    expiry: str
    hedge_leg: OptionLeg
    short_leg: OptionLeg

