"""
Generic Backtesting Engine

Strategy-agnostic backtester that takes ANY strategy implementing BaseStrategy
and simulates bar-by-bar execution on historical data.

The engine's responsibilities:
- Manage position state (flat, long, short)
- Execute entries when trigger prices are crossed
- Execute exits on target, stop loss, or EOD reset
- Track all trades with full metadata
- Enforce risk rules (max trades per day)

The engine does NOT:
- Generate signals (that's the strategy's job)
- Place real orders (that's the live engine's job)
- Calculate metrics (that's the metrics module's job)
"""

import pandas as pd
import numpy as np
import logging
from typing import Optional, List
from strategies.base import BaseStrategy, TradeDirection
from config.settings import Settings

logger = logging.getLogger(__name__)


class BacktestEngine:
    """
    Simulates strategy execution on historical data.

    Takes a prepared DataFrame (with signal columns from a strategy)
    and walks through bar-by-bar simulating entries, exits, and position
    management.

    Attributes:
        strategy: The strategy instance to test.
        settings: Configuration for risk parameters.
        trades: List of completed trade dictionaries.
    """

    def __init__(self, strategy: BaseStrategy, settings: Optional[Settings] = None):
        """
        Initialize the backtest engine.

        Args:
            strategy: Strategy instance to test. Must implement BaseStrategy.
            settings: Configuration object for risk parameters.
        """
        self.strategy = strategy
        self.settings = settings or Settings()
        self.trades: List[dict] = []

    def run(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Execute a full backtest on the given data.

        Workflow:
        1. strategy.prepare_data() → add indicators
        2. strategy.generate_signals() → add signal columns
        3. Simulate bar-by-bar execution

        Args:
            df: Raw OHLCV DataFrame with DateTimeIndex.

        Returns:
            DataFrame of all executed trades with columns:
            type, entry_time, entry_price, exit_time, exit_price, pnl, reason
        """
        logger.info(f"Running backtest: {self.strategy.name}")
        logger.info(f"Data range: {df.index[0]} to {df.index[-1]} ({len(df)} bars)")

        # Step 1 & 2: Prepare data and generate signals
        df = self.strategy.prepare_data(df)
        df = self.strategy.generate_signals(df)

        # Step 3: Simulate execution
        self.trades = []
        self._simulate(df)

        trades_df = pd.DataFrame(self.trades)
        logger.info(f"Backtest complete: {len(trades_df)} trades generated")
        return trades_df

    def _simulate(self, df: pd.DataFrame) -> None:
        """
        Core simulation loop — processes each bar sequentially.

        State machine:
        - FLAT: Looking for entry trigger to be crossed
        - LONG: Monitoring for target (high >= target) or SL (low <= SL)
        - SHORT: Monitoring for target (low <= target) or SL (high >= SL)

        Entry logic uses the PREVIOUS bar's signal to determine the current
        bar's trigger (simulating real-time: signal detected, then next bar
        attempts entry).

        Args:
            df: DataFrame with signal columns from the strategy.
        """
        # Position state
        position = 0        # 0=flat, 1=long, -1=short
        entry_price = 0.0
        entry_time = None
        target_price = 0.0
        stop_price = 0.0
        trades_today = 0

        # Previous bar's signal state (for trigger detection on next bar)
        prev_direction = 0
        prev_trigger = np.nan
        prev_target = np.nan
        prev_sl = np.nan
        prev_entry_on_next_open = False

        for idx, row in df.iterrows():
            # --- EOD RESET: Force-close any open position ---
            if row.get("is_reset", 0) == 1:
                if position == 1:
                    pnl = row["open"] - entry_price
                    self._record_trade(
                        "Long", entry_time, entry_price,
                        idx, row["open"], pnl, "EOD Square-off"
                    )
                    position = 0
                elif position == -1:
                    pnl = entry_price - row["open"]
                    self._record_trade(
                        "Short", entry_time, entry_price,
                        idx, row["open"], pnl, "EOD Square-off"
                    )
                    position = 0
                trades_today = 0

            # --- EXIT LOGIC: Check target and stop loss ---
            if position == 1:
                # Stop loss hit (checked first — conservative assumption on same-bar)
                if row["low"] <= stop_price:
                    pnl = stop_price - entry_price
                    self._record_trade(
                        "Long", entry_time, entry_price,
                        idx, stop_price, pnl, "Stop Loss"
                    )
                    position = 0
                # Target hit
                elif row["high"] >= target_price:
                    pnl = target_price - entry_price
                    self._record_trade(
                        "Long", entry_time, entry_price,
                        idx, target_price, pnl, "Target"
                    )
                    position = 0

            elif position == -1:
                # Stop loss hit
                if row["high"] >= stop_price:
                    pnl = entry_price - stop_price
                    self._record_trade(
                        "Short", entry_time, entry_price,
                        idx, stop_price, pnl, "Stop Loss"
                    )
                    position = 0
                # Target hit
                elif row["low"] <= target_price:
                    pnl = entry_price - target_price
                    self._record_trade(
                        "Short", entry_time, entry_price,
                        idx, target_price, pnl, "Target"
                    )
                    position = 0

            # --- ENTRY LOGIC: Only if flat and haven't traded today ---
            if position == 0 and row.get("is_reset", 0) == 0 and trades_today < self.settings.MAX_TRADES_PER_DAY:

                # LONG entry: previous bar signaled LONG and current bar crosses trigger
                if prev_direction == 1 and not np.isnan(prev_trigger):
                    if prev_entry_on_next_open or row["high"] >= prev_trigger:
                        if prev_entry_on_next_open and (
                            row["open"] >= prev_target or row["open"] <= prev_sl
                        ):
                            logger.info(
                                "Skipping LONG next-open entry at %s: open %.2f "
                                "is outside target/stop range %.2f-%.2f",
                                idx, row["open"], prev_sl, prev_target,
                            )
                            prev_direction = 0
                            prev_trigger = np.nan
                            prev_target = np.nan
                            prev_sl = np.nan
                            prev_entry_on_next_open = False
                            continue

                        position = 1
                        trades_today += 1
                        entry_price = (
                            row["open"]
                            if prev_entry_on_next_open
                            else max(row["open"], prev_trigger)
                        )
                        entry_time = idx
                        target_price = prev_target
                        stop_price = prev_sl

                        # Check if target/SL hit on same candle as entry
                        if row["low"] <= stop_price:
                            pnl = stop_price - entry_price
                            self._record_trade(
                                "Long", entry_time, entry_price,
                                idx, stop_price, pnl, "Immediate Stop Loss"
                            )
                            position = 0
                        elif row["high"] >= target_price:
                            pnl = target_price - entry_price
                            self._record_trade(
                                "Long", entry_time, entry_price,
                                idx, target_price, pnl, "Immediate Target"
                            )
                            position = 0

                # SHORT entry: previous bar signaled SHORT and current bar crosses trigger
                elif prev_direction == 2 and not np.isnan(prev_trigger):
                    if prev_entry_on_next_open or row["low"] <= prev_trigger:
                        if prev_entry_on_next_open and (
                            row["open"] <= prev_target or row["open"] >= prev_sl
                        ):
                            logger.info(
                                "Skipping SHORT next-open entry at %s: open %.2f "
                                "is outside target/stop range %.2f-%.2f",
                                idx, row["open"], prev_target, prev_sl,
                            )
                            prev_direction = 0
                            prev_trigger = np.nan
                            prev_target = np.nan
                            prev_sl = np.nan
                            prev_entry_on_next_open = False
                            continue

                        position = -1
                        trades_today += 1
                        entry_price = (
                            row["open"]
                            if prev_entry_on_next_open
                            else min(row["open"], prev_trigger)
                        )
                        entry_time = idx
                        target_price = prev_target
                        stop_price = prev_sl

                        # Check if target/SL hit on same candle as entry
                        if row["high"] >= stop_price:
                            pnl = entry_price - stop_price
                            self._record_trade(
                                "Short", entry_time, entry_price,
                                idx, stop_price, pnl, "Immediate Stop Loss"
                            )
                            position = 0
                        elif row["low"] <= target_price:
                            pnl = entry_price - target_price
                            self._record_trade(
                                "Short", entry_time, entry_price,
                                idx, target_price, pnl, "Immediate Target"
                            )
                            position = 0

            # Update previous bar state for next iteration
            prev_direction = row.get("signal_direction", 0)
            prev_trigger = row.get("trigger_price", np.nan)
            prev_target = row.get("target_price", np.nan)
            prev_sl = row.get("stop_loss_price", np.nan)
            prev_entry_on_next_open = bool(row.get("entry_on_next_open", 0))

    def _record_trade(
        self,
        trade_type: str,
        entry_time,
        entry_price: float,
        exit_time,
        exit_price: float,
        pnl: float,
        reason: str,
    ) -> None:
        """
        Record a completed trade to the trades list.

        Args:
            trade_type: "Long" or "Short".
            entry_time: Timestamp of entry.
            entry_price: Price at entry.
            exit_time: Timestamp of exit.
            exit_price: Price at exit.
            pnl: Profit/loss in points.
            reason: Why the trade was closed.
        """
        self.trades.append({
            "type": trade_type,
            "entry_time": entry_time,
            "entry_price": entry_price,
            "exit_time": exit_time,
            "exit_price": exit_price,
            "pnl": pnl,
            "reason": reason,
        })
