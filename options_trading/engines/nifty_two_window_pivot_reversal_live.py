"""
Isolated live options runner for the Nifty two-window pivot reversal strategy.

The existing active Nifty options engine remains unchanged. This engine reuses
its option spread planning and order-confirmation implementation while adding
strategy-specific entry confirmation and underlying-based exits.
"""

import logging
import time
from datetime import datetime, time as dt_time
from typing import Optional

import pandas as pd

from options_trading.config import OptionsTradingSettings
from options_trading.engines.nifty_options_live import NiftyOptionsLiveEngine, IST
from options_trading.models import OptionLeg
from options_trading.strategies.nifty_futures_two_window_pivot_reversal import (
    NiftyFuturesTwoWindowPivotReversalStrategy,
)

logger = logging.getLogger(__name__)


class NiftyTwoWindowPivotReversalOptionsLiveEngine(NiftyOptionsLiveEngine):
    """
    Execute option credit spreads from confirmed Nifty futures reversal signals.

    Entry is attempted after the qualifying one-minute candle has completed.
    Active spreads close immediately when futures reaches target, when a
    completed five-minute futures candle closes beyond stop, or at 14:45 IST.
    """

    def __init__(
        self,
        settings: Optional[OptionsTradingSettings] = None,
        expiry_date: Optional[str] = None,
    ):
        super().__init__(settings=settings, expiry_date=expiry_date)
        self.strategy = NiftyFuturesTwoWindowPivotReversalStrategy()
        self.active_signal: Optional[dict] = None
        self.spread_entry_timestamp: Optional[pd.Timestamp] = None
        self.last_stop_check_timestamp: Optional[pd.Timestamp] = None
        self.exit_failed = False

    def run(self) -> None:
        logger.info("Nifty two-window pivot reversal options engine starting...")
        self.notifier.send("*Nifty Two-Window Pivot Reversal Options Bot Started*")

        missing = self.settings.validate_for_live()
        if missing:
            msg = "Nifty pivot reversal options bot stopped: missing " + ", ".join(missing)
            self.notifier.send(msg)
            logger.error(msg)
            return

        if not self._wait_for_setup_time():
            return
        if not self._prepare_reversal_setup():
            return

        self._monitoring_loop()
        self._close_active_spread("14:45 square-off")
        self.notifier.send("*Nifty pivot reversal options trading day complete.*")

    def _prepare_reversal_setup(self) -> bool:
        now = datetime.now(IST)
        df = self.fetcher.fetch_combined(self.settings.NIFTY_FUTURES_KEY, history_days=3)
        if df.empty:
            self.notifier.send("Nifty pivot reversal setup skipped: no candle data returned.")
            return False

        qualified, missed = self.strategy.prepare_setup(df, as_of=now)
        if missed:
            self.notifier.send(
                "*NIFTY PIVOT REVERSAL SKIPPED*: confirmed signal occurred before startup.\n"
                f"Direction: {missed['direction']}\n"
                f"Signal time: {missed['signal_time'].strftime('%H:%M')}"
            )
            return False
        if not qualified:
            self.notifier.send("Nifty two-window pivot reversal setup did not qualify today.")
            return False

        setup = self.strategy.setup
        self.notifier.send(
            "*Nifty Two-Window Pivot Reversal Setup Qualified*\n"
            f"Direction: {setup.direction}\n"
            f"Trigger: {setup.trigger_price:.2f}\n"
            f"Target: {setup.target_price:.2f}\n"
            f"Stop: {setup.stop_loss_price:.2f}"
        )
        return True

    def _monitoring_loop(self) -> None:
        while datetime.now(IST).time() < dt_time(14, 45):
            if self.exit_failed:
                logger.error("Automated monitoring stopped after an option exit failure")
                return

            now = datetime.now(IST)
            if self.active_spread is not None:
                self._check_underlying_exit()
            elif self.risk.can_trade() and now.time() < dt_time(14, 31):
                self._check_fresh_signal(now)

            time.sleep(self.settings.PIVOT_REVERSAL_MONITOR_INTERVAL)

    def _check_fresh_signal(self, now: datetime) -> None:
        intraday = self.fetcher.fetch_intraday(self.settings.NIFTY_FUTURES_KEY)
        signal = self.strategy.get_signal(intraday, as_of=now)
        if not signal:
            return

        futures_ltp = self.broker.get_ltp(self.settings.NIFTY_FUTURES_KEY)
        if futures_ltp is None:
            logger.warning("Nifty futures LTP unavailable after confirmed signal")
            self.notifier.send(
                "*NIFTY PIVOT REVERSAL ENTRY SKIPPED*: futures LTP unavailable "
                "after confirmed signal."
            )
            return

        if not self._is_entry_price_valid(signal, futures_ltp):
            logger.info(
                "Skipping %s entry: futures LTP %.2f is outside target/stop range %.2f-%.2f",
                signal["direction"],
                futures_ltp,
                signal["stop_loss_price"],
                signal["target_price"],
            )
            self.notifier.send(
                "*NIFTY PIVOT REVERSAL ENTRY SKIPPED*: next-minute futures price "
                "already reached or crossed the planned target/stop.\n"
                f"Direction: {signal['direction']}\n"
                f"Futures LTP: {futures_ltp:.2f}\n"
                f"Target: {signal['target_price']:.2f}\n"
                f"Stop: {signal['stop_loss_price']:.2f}"
            )
            return

        self._enter_spread(signal["direction"], futures_ltp)
        if self.active_spread is not None:
            self.active_signal = signal
            self.spread_entry_timestamp = self._naive_timestamp(datetime.now(IST))
            self.last_stop_check_timestamp = self.spread_entry_timestamp
            self.notifier.send(
                "*NIFTY PIVOT REVERSAL EXIT LEVELS*\n"
                f"Futures target: {signal['target_price']:.2f}\n"
                f"Futures stop: {signal['stop_loss_price']:.2f} "
                "(completed 5-minute close)\n"
                "Forced close: 14:45 IST"
            )

    @staticmethod
    def _is_entry_price_valid(signal: dict, futures_ltp: float) -> bool:
        """Reject a next-minute entry when price already reached target or stop."""
        target = signal["target_price"]
        stop = signal["stop_loss_price"]
        if signal["direction"] == "LONG":
            return stop < futures_ltp < target
        return target < futures_ltp < stop

    def _check_underlying_exit(self, now: Optional[datetime] = None) -> None:
        if self.active_signal is None:
            return

        futures_ltp = self.broker.get_ltp(self.settings.NIFTY_FUTURES_KEY)
        if futures_ltp is None:
            logger.warning("Nifty futures LTP unavailable while monitoring exits")
            return

        direction = self.active_signal["direction"]
        target = self.active_signal["target_price"]
        if direction == "LONG" and futures_ltp >= target:
            self._close_active_spread("Futures target reached")
        elif direction == "SHORT" and futures_ltp <= target:
            self._close_active_spread("Futures target reached")
        else:
            self._check_completed_five_minute_stop(now or datetime.now(IST))

    def _check_completed_five_minute_stop(self, now: datetime) -> None:
        """Close only when a newly completed five-minute candle confirms stop."""
        latest_completed = self._latest_completed_five_minute_timestamp(now)
        after = self.last_stop_check_timestamp or self.spread_entry_timestamp
        if after is not None and latest_completed <= self._naive_timestamp(after):
            return

        intraday = self.fetcher.fetch_intraday(self.settings.NIFTY_FUTURES_KEY)
        if intraday.empty:
            logger.warning("Nifty futures candles unavailable while monitoring stop")
            return

        completed = self._completed_five_minute_candles_after(
            intraday,
            as_of=now,
            after=after,
        )
        if completed.empty:
            return

        self.last_stop_check_timestamp = completed.index.max()
        stop = self.active_signal["stop_loss_price"]
        direction = self.active_signal["direction"]
        for timestamp, row in completed.iterrows():
            close = float(row["close"])
            if direction == "LONG" and close <= stop:
                self._close_active_spread(
                    f"Futures 5-minute close stop reached at {timestamp:%H:%M} "
                    f"(close {close:.2f})"
                )
                return
            if direction == "SHORT" and close >= stop:
                self._close_active_spread(
                    f"Futures 5-minute close stop reached at {timestamp:%H:%M} "
                    f"(close {close:.2f})"
                )
                return

    @classmethod
    def _completed_five_minute_candles_after(
        cls,
        df: pd.DataFrame,
        as_of: datetime,
        after: Optional[pd.Timestamp],
    ) -> pd.DataFrame:
        """Return newly completed session-aligned five-minute closing bars."""
        current_minute = cls._naive_timestamp(as_of).floor("min")
        completed = df[df.index < current_minute]
        if after is not None:
            completed = completed[completed.index > cls._naive_timestamp(after)]
        return completed[completed.index.minute % 5 == 4]

    @staticmethod
    def _naive_timestamp(value) -> pd.Timestamp:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_localize(None)
        return timestamp

    @classmethod
    def _latest_completed_five_minute_timestamp(cls, as_of: datetime) -> pd.Timestamp:
        """Return the latest possible completed session-aligned five-minute bar."""
        timestamp = cls._naive_timestamp(as_of).floor("min") - pd.Timedelta(minutes=1)
        return timestamp - pd.Timedelta(minutes=(timestamp.minute - 4) % 5)

    def _close_active_spread(self, reason: str) -> None:
        if self.active_spread is None or self.exit_failed:
            return

        for leg in (self.active_spread.short_leg, self.active_spread.hedge_leg):
            exit_leg = OptionLeg(
                transaction_type="BUY" if leg.transaction_type == "SELL" else "SELL",
                instrument_key=leg.instrument_key,
                trading_symbol=leg.trading_symbol,
                strike=leg.strike,
                option_type=leg.option_type,
                quantity=leg.quantity,
                role=f"EXIT-{leg.role}",
            )
            if not self._place_and_confirm(exit_leg):
                self.exit_failed = True
                self.notifier.send(
                    f"*NIFTY PIVOT REVERSAL EXIT FAILED*: {leg.trading_symbol}\n"
                    f"Reason: {reason}\n"
                    "Automated exit retries have stopped. Review and close the "
                    "remaining position manually in Upstox."
                )
                return

        self.notifier.send(f"*NIFTY PIVOT REVERSAL SPREAD CLOSED*: {reason}")
        self.active_spread = None
        self.active_signal = None
        self.spread_entry_timestamp = None
        self.last_stop_check_timestamp = None

    def _wait_for_setup_time(self) -> bool:
        now = datetime.now(IST)
        if now.time() >= dt_time(14, 45):
            logger.info("Pivot reversal trading window has closed. Nothing to do.")
            return False

        target_time = now.replace(hour=9, minute=45, second=0, microsecond=0)
        if now < target_time:
            wait_seconds = (target_time - now).total_seconds()
            logger.info("Waiting %.0fs until 09:45 AM IST...", wait_seconds)
            time.sleep(wait_seconds)
        return True
