# Strategies package
# Contains the abstract base class and all strategy implementations
from strategies.base import BaseStrategy, Signal, TradeDirection
from strategies.three_candle import ThreeCandleStrategy
from strategies.camarilla import CamarillaStrategy
from strategies.two_window_pivot_reversal import TwoWindowPivotReversalStrategy
