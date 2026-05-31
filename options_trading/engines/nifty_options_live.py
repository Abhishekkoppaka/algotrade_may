"""
Nifty futures-tracked options live engine.

This is the main options-trading engine. It is intentionally separate from the
older Nifty+50 stock live bot under `live/`.
"""

import logging
import time
from datetime import datetime, time as dt_time
from typing import Optional

import pytz

from core.broker import UpstoxBroker
from core.data_fetcher import DataFetcher
from core.notifier import TelegramNotifier
from live.risk import RiskManager
from options_trading.config import OptionsTradingSettings
from options_trading.execution import NiftySpreadPlanner
from options_trading.models import OptionLeg, SpreadPlan
from options_trading.strategies import NiftyFuturesBreakoutStrategy

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")


class NiftyOptionsLiveEngine:
    """
    Runs Nifty futures signals and executes Nifty option credit spreads.

    Signal mapping:
    - LONG futures breakout: sell OTM call and buy farther OTM call.
    - SHORT futures breakout: sell OTM put and buy farther OTM put.
    """

    def __init__(
        self,
        settings: Optional[OptionsTradingSettings] = None,
        expiry_date: Optional[str] = None,
    ):
        self.settings = settings or OptionsTradingSettings()
        self.expiry_date = expiry_date
        self.broker = UpstoxBroker(self.settings)
        self.fetcher = DataFetcher(self.settings)
        self.notifier = TelegramNotifier(self.settings)
        self.risk = RiskManager(self.settings)
        self.strategy = NiftyFuturesBreakoutStrategy(self.settings.MIN_INSIDE_CANDLES)
        self.spread_planner = NiftySpreadPlanner(self.settings)
        self.active_spread: Optional[SpreadPlan] = None

    def run(self) -> None:
        logger.info("Nifty Options Engine starting...")
        self.notifier.send("*Nifty Options Bot Started*")

        missing = self.settings.validate_for_live()
        if missing:
            msg = "Nifty options bot stopped: missing " + ", ".join(missing)
            self.notifier.send(msg)
            logger.error(msg)
            return

        if not self._wait_for_scan_time():
            return
        if not self._prepare_setup():
            return

        self._monitoring_loop()
        self._eod_squareoff()
        self.notifier.send("*Nifty options trading day complete.*")

    def _prepare_setup(self) -> bool:
        df = self.fetcher.fetch_combined(self.settings.NIFTY_FUTURES_KEY, history_days=3)
        if df.empty:
            self.notifier.send("Nifty futures setup skipped: no candle data returned.")
            return False

        qualified, missed = self.strategy.prepare_setup(df)
        if missed:
            self.notifier.send_missed_breakouts([missed])
            logger.info(
                "Nifty futures skipped: breakout already happened at %s before bot startup",
                missed["breakout_time"],
            )
            return False
        if not qualified:
            self.notifier.send("Nifty futures setup did not qualify today.")
            return False

        setup = self.strategy.setup
        self.notifier.send(
            "*Nifty Futures Setup Qualified*\n"
            f"IB High: {setup['d15_high']:.2f}\n"
            f"IB Low: {setup['d15_low']:.2f}"
        )
        return True

    def _monitoring_loop(self) -> None:
        active_logged = False
        while not self.risk.is_eod_squareoff_time(datetime.now(IST).time()):
            if self.active_spread is None and self.risk.can_trade():
                self._check_fresh_breakout()
            elif self.active_spread is not None and not active_logged:
                logger.info("Spread entered. Holding until EOD square-off.")
                active_logged = True

            time.sleep(self.settings.LIVE_MONITOR_INTERVAL)

    def _check_fresh_breakout(self) -> None:
        ltp = self.broker.get_ltp(self.settings.NIFTY_FUTURES_KEY)
        if ltp is None:
            logger.warning("Nifty futures LTP unavailable; skipping this cycle")
            return

        signal = self.strategy.get_signal(ltp)
        if signal:
            self._enter_spread(signal, ltp)
        else:
            setup = self.strategy.setup
            logger.info(
                "Nifty futures LTP %.2f inside IB range %.2f-%.2f",
                ltp,
                setup["d15_low"],
                setup["d15_high"],
            )

    def _enter_spread(self, signal_direction: str, futures_ltp: float) -> None:
        contracts = self.broker.get_option_contracts(
            self.settings.NIFTY50_INDEX_KEY,
            self.expiry_date,
        )
        plan = self.spread_planner.build_plan(
            signal_direction,
            futures_ltp,
            contracts,
            expiry_date=self.expiry_date,
        )
        if not plan:
            self.notifier.send("*NIFTY SPREAD SKIPPED*: required option plan unavailable.")
            return

        self.notifier.send(
            f"*NIFTY {signal_direction} BREAKOUT - OPTION SPREAD*\n"
            f"Nifty futures LTP: {futures_ltp:.2f} | Base strike: {plan.base_strike}\n"
            f"Expiry: {plan.expiry}\n"
            f"1) BUY hedge: {plan.hedge_leg.trading_symbol} x {plan.hedge_leg.quantity}\n"
            f"2) SELL short: {plan.short_leg.trading_symbol} x {plan.short_leg.quantity}"
        )

        hedge_order = self._place_and_confirm(plan.hedge_leg)
        if not hedge_order:
            self.notifier.send("*NIFTY SPREAD ABORTED*: hedge leg was not confirmed.")
            self.risk.record_trade()
            return

        short_order = self._place_and_confirm(plan.short_leg)
        if not short_order:
            self.notifier.send(
                "*NIFTY SPREAD INCOMPLETE*: hedge bought but short leg failed.\n"
                "Review Upstox manually and close/adjust the hedge if required."
            )
            self.risk.record_trade()
            return

        self.active_spread = plan
        self.risk.record_trade()
        self.notifier.send(
            "*NIFTY SPREAD ENTERED*\n"
            f"BUY hedge: {plan.hedge_leg.trading_symbol}\n"
            f"SELL short: {plan.short_leg.trading_symbol}"
        )

    def _place_and_confirm(self, leg: OptionLeg) -> Optional[str]:
        tag = f"NIFTYOPT-{leg.role}-{datetime.now(IST).strftime('%Y%m%d%H%M%S')}"
        order_id = self.broker.place_market_order(
            leg.instrument_key,
            leg.transaction_type,
            leg.quantity,
            product=self.settings.NIFTY_OPTION_PRODUCT,
            tag=tag,
        )
        if not order_id:
            return None

        time.sleep(2)
        status, msg = self.broker.get_order_status(order_id)
        if (status or "").lower() not in ("complete", "completed"):
            self.notifier.send(
                f"*OPTION LEG NOT CONFIRMED*: {leg.trading_symbol}\n"
                f"Order ID: {order_id}\n"
                f"Status: {status or 'UNKNOWN'}\n"
                f"Reason: {msg or 'Check Upstox manually.'}"
            )
            return None
        return order_id

    def _eod_squareoff(self) -> None:
        if self.active_spread is None:
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
                self.notifier.send(
                    f"*NIFTY OPTION EXIT FAILED*: {leg.trading_symbol}\n"
                    "Close this leg manually in Upstox."
                )
                return

        self.notifier.send("*NIFTY OPTION SPREAD CLOSED AT EOD*")
        self.active_spread = None

    def _wait_for_scan_time(self) -> bool:
        now = datetime.now(IST)
        if now.time() >= dt_time(15, 30):
            logger.info("Market closed. Nothing to do.")
            return False

        target_time = now.replace(hour=10, minute=15, second=0, microsecond=0)
        if now < target_time:
            wait_seconds = (target_time - now).total_seconds()
            logger.info("Waiting %.0fs until 10:15 AM IST...", wait_seconds)
            time.sleep(wait_seconds)
        return True

