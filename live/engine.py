"""
Live Trading Engine

The main orchestrator for real-time trading. Implements a state machine
that progresses through the trading day:

    IDLE → SCANNING → WATCHLIST_READY → MONITORING → IN_TRADE → DONE

Responsibilities:
- Build the daily watchlist (scan stocks meeting strategy criteria)
- Monitor for breakout signals
- Execute entries/exits through the broker
- Send notifications at each state transition
- Enforce EOD square-off

This engine is strategy-agnostic: it relies on the strategy to tell it
WHAT to do, and the broker to tell it HOW to execute.
"""

import time
import logging
from datetime import datetime, time as dt_time
from enum import Enum
from typing import Optional, Dict, List

import pytz

from config.settings import Settings
from core.broker import UpstoxBroker
from core.notifier import TelegramNotifier
from core.data_fetcher import DataFetcher
from live.risk import RiskManager
from live.setup import evaluate_morning_setup, find_missed_breakout
from strategies.indicators import (
    get_next_pivot_above,
    get_next_pivot_below,
)

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")


class BotState(Enum):
    """States of the live trading state machine."""
    IDLE = "IDLE"                     # Waiting for market to open
    SCANNING = "SCANNING"             # Running morning scan
    WATCHLIST_READY = "WATCHLIST_READY"  # Watchlist built, monitoring breakouts
    MONITORING = "MONITORING"         # Breakout detected, waiting for trigger
    IN_TRADE = "IN_TRADE"             # Active position open
    DONE = "DONE"                     # Trading day complete


class LiveEngine:
    """
    Orchestrates live intraday trading.

    Runs a continuous loop during market hours, progressing through
    states based on market conditions and strategy signals.

    This is designed for the 3Candle strategy but can be adapted
    for any intraday strategy that follows the pattern:
    morning scan → watchlist → breakout → trigger → exit.

    Attributes:
        broker: Upstox API client for orders and quotes.
        notifier: Telegram notification sender.
        fetcher: Data fetching client.
        risk: Risk management module.
        settings: Configuration parameters.
        state: Current engine state.
        watchlist: Dict of qualified symbols and their setup data.
        active_trade: Currently open trade details (or None).
    """

    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize the live engine with all dependencies.

        Args:
            settings: Configuration object. Creates default if not provided.
        """
        self.settings = settings or Settings()
        self.broker = UpstoxBroker(self.settings)
        self.notifier = TelegramNotifier(self.settings)
        self.fetcher = DataFetcher(self.settings)
        self.risk = RiskManager(self.settings)

        # Engine state
        self.state = BotState.IDLE
        self.watchlist: Dict[str, dict] = {}
        self.active_trade: Optional[dict] = None

    def run(self, observer_list: List[dict]) -> None:
        """
        Main execution loop. Runs until market closes or trade completes.

        Args:
            observer_list: List of instrument dicts with keys:
                - signal_key: Instrument key for signal generation
                - symbol: Human-readable symbol name
                - execution_key: Instrument key for order execution
                - execution_symbol: Symbol name used in execution
        """
        logger.info("Live Engine starting...")
        self.notifier.send("*Live Bot Started*")

        # Wait for 10:15 AM before scanning
        if not self._wait_for_scan_time():
            return

        # Phase 1: Build watchlist
        self.state = BotState.SCANNING
        self.watchlist = self._build_watchlist(observer_list)

        if not self.watchlist:
            self.notifier.send("No setups qualified today. Bot going idle.")
            self.state = BotState.DONE
            return

        self.state = BotState.WATCHLIST_READY
        self.notifier.send_watchlist(self.watchlist)

        # Phase 2: Monitor for breakouts and triggers
        self._monitoring_loop()

        # Phase 3: EOD cleanup
        self._eod_squareoff()
        self.state = BotState.DONE
        self.notifier.send("*Trading day complete.*")

    # -----------------------------------------------------------------------
    # Phase 1: Watchlist Building
    # -----------------------------------------------------------------------

    def _build_watchlist(self, observer_list: List[dict]) -> Dict[str, dict]:
        """
        Scan all instruments and build the qualified watchlist.

        For each instrument, checks:
        1. Whether the IB range is established (09:15-09:29)
        2. Whether 3+ inside candles formed (09:30-10:14)
        3. Whether the range remained unbroken

        Returns:
            Dict keyed by signal_key with setup data for each qualified symbol.
        """
        watchlist = {}
        missed_breakouts = []
        self.notifier.send("*Morning Scan Started* - Checking for 3Candle setups...")

        for item in observer_list:
            sig_key = item["signal_key"]

            # Fetch yesterday + today's data
            df = self.fetcher.fetch_combined(sig_key, history_days=3)
            if df.empty:
                continue

            setup_data = evaluate_morning_setup(
                df,
                min_inside_candles=self.settings.MIN_INSIDE_CANDLES,
            )
            if setup_data:
                missed = find_missed_breakout(
                    df, setup_data["d15_high"], setup_data["d15_low"], item["symbol"]
                )
                if missed:
                    missed_breakouts.append(missed)
                    logger.info(
                        "%s skipped: breakout already happened at %s before bot startup",
                        item["symbol"],
                        missed["breakout_time"],
                    )
                    time.sleep(self.settings.LIVE_SCAN_SLEEP)
                    continue

                watchlist[sig_key] = {
                    "symbol": item["symbol"],
                    "exec_key": item["execution_key"],
                    "exec_symbol": item["execution_symbol"],
                    "d15_high": setup_data["d15_high"],
                    "d15_low": setup_data["d15_low"],
                    "pivots": setup_data["pivots"],
                    "state": "WAITING_BREAKOUT",
                }

            time.sleep(self.settings.LIVE_SCAN_SLEEP)

        logger.info(f"Watchlist built: {len(watchlist)} symbols qualified")

        if missed_breakouts:
            logger.info(f"{len(missed_breakouts)} missed breakout(s) detected")
            self.notifier.send_missed_breakouts(missed_breakouts)

        return watchlist

    # -----------------------------------------------------------------------
    # Phase 2: Monitoring Loop
    # -----------------------------------------------------------------------

    def _monitoring_loop(self) -> None:
        """
        Main monitoring loop. Polls for breakouts and manages trades.

        Runs until 14:30 or until a trade completes.
        Checks every 5 seconds for price updates.
        """
        last_heartbeat = datetime.now(IST)
        monitor_start = datetime.now(IST)
        HEARTBEAT_INTERVAL = 300  # 5 minutes

        while not self.risk.is_eod_squareoff_time(datetime.now(IST).time()):
            now = datetime.now(IST)

            # If no active trade, check for breakouts
            if self.active_trade is None and self.risk.can_trade():
                self._check_breakouts()

            # If in a trade, check for exit conditions
            if self.active_trade is not None:
                self._check_exits()

            # If trade completed, we're done for the day (1 trade limit)
            if not self.risk.can_trade() and self.active_trade is None:
                logger.info("Trade completed. Done for the day.")
                break

            # 5-minute Telegram heartbeat when no active trade
            if self.active_trade is None:
                secs_since = (now - last_heartbeat).total_seconds()
                if secs_since >= HEARTBEAT_INTERVAL:
                    monitoring_count = sum(
                        1 for v in self.watchlist.values()
                        if v["state"] in ("WAITING_BREAKOUT", "WAITING_TRIGGER")
                    )
                    elapsed_min = int((now - monitor_start).total_seconds() / 60)
                    self.notifier.send_heartbeat(monitoring_count, elapsed_min)
                    last_heartbeat = now

            time.sleep(self.settings.LIVE_MONITOR_INTERVAL)

            # Console heartbeat every 2 minutes
            if int(time.time()) % 120 < 6:
                status = "IN TRADE" if self.active_trade else "SCANNING"
                logger.info(f"[{now.strftime('%H:%M:%S')}] Bot alive - {status}")

    def _check_breakouts(self) -> None:
        """
        Check all watchlist items for breakout and trigger conditions.

        For items in WAITING_BREAKOUT:
        - Fetch latest quote
        - If close > d15_high → mark LONG breakout, set trigger at high
        - If close < d15_low → mark SHORT breakout, set trigger at low

        For items in WAITING_TRIGGER:
        - Check if LTP has crossed the trigger price
        - If yes, execute entry order
        """
        now_str = datetime.now(IST).strftime("%H:%M:%S")
        logger.info(f"[{now_str}] Checking {len(self.watchlist)} watchlist items for breakouts...")
        newly_skipped = []
        for sig_key, item in list(self.watchlist.items()):
            # Stop scanning once a trade is active (1-trade-per-day limit)
            if self.active_trade is not None:
                break
            if item["state"] == "WAITING_BREAKOUT":
                self._check_for_breakout(sig_key, item)
                if item["state"] == "SKIPPED":
                    newly_skipped.append(item.get("skip_detail"))
            elif item["state"] == "WAITING_TRIGGER":
                self._check_for_trigger(sig_key, item)
            # SKIPPED / REJECTED / ACTIVE states are ignored

        if newly_skipped:
            self.notifier.send_skipped_summary(newly_skipped)

    def _check_for_breakout(self, sig_key: str, item: dict) -> None:
        """Check if a symbol has broken out of the IB range."""
        ltp = self.broker.get_ltp(sig_key)
        if ltp is None:
            logger.warning(f"{item['symbol']}: LTP fetch returned None — skipping this cycle")
            return

        now_str = datetime.now(IST).strftime("%H:%M:%S")
        name = item["symbol"]

        logger.info(
            f"{name}: LTP={ltp:.2f} | IB High={item['d15_high']:.2f} | IB Low={item['d15_low']:.2f}"
        )

        if ltp > item["d15_high"]:
            trigger = item["d15_high"]
            target = get_next_pivot_above(trigger, item["pivots"])
            sl = get_next_pivot_below(trigger, item["pivots"])

            if ltp >= target:
                item["state"] = "SKIPPED"
                item["skip_detail"] = {
                    "symbol": name, "direction": "LONG",
                    "trigger": trigger, "ltp": ltp,
                    "target": target, "time": now_str,
                }
                logger.info(f"{name}: LONG breakout SKIPPED — LTP {ltp:.2f} already past target {target:.2f}")
                return

            item["state"] = "WAITING_TRIGGER"
            item["direction"] = "LONG"
            item["trigger_price"] = trigger
            item["target"] = target
            item["sl"] = sl
            self.notifier.send(
                f"*BREAKOUT: {name}*\n"
                f"Direction: LONG\n"
                f"Trigger: {trigger:.2f} | LTP: {ltp:.2f}\n"
                f"Target: {target:.2f} | SL: {sl:.2f}"
            )
            # Attempt entry immediately — don't wait 60s for next poll cycle
            self._check_for_trigger(sig_key, item)

        elif ltp < item["d15_low"]:
            trigger = item["d15_low"]
            target = get_next_pivot_below(trigger, item["pivots"])
            sl = get_next_pivot_above(trigger, item["pivots"])

            if ltp <= target:
                item["state"] = "SKIPPED"
                item["skip_detail"] = {
                    "symbol": name, "direction": "SHORT",
                    "trigger": trigger, "ltp": ltp,
                    "target": target, "time": now_str,
                }
                logger.info(f"{name}: SHORT breakout SKIPPED — LTP {ltp:.2f} already past target {target:.2f}")
                return

            item["state"] = "WAITING_TRIGGER"
            item["direction"] = "SHORT"
            item["trigger_price"] = trigger
            item["target"] = target
            item["sl"] = sl
            self.notifier.send(
                f"*BREAKOUT: {name}*\n"
                f"Direction: SHORT\n"
                f"Trigger: {trigger:.2f} | LTP: {ltp:.2f}\n"
                f"Target: {target:.2f} | SL: {sl:.2f}"
            )
            # Attempt entry immediately — don't wait 60s for next poll cycle
            self._check_for_trigger(sig_key, item)

        else:
            logger.debug(f"{name}: LTP {ltp:.2f} within IB range — no breakout yet")

    def _check_for_trigger(self, sig_key: str, item: dict) -> None:
        """Check if the breakout trigger price has been crossed, and enter trade."""
        ltp = self.broker.get_ltp(sig_key)
        if ltp is None:
            return

        triggered = False
        if item["direction"] == "LONG" and ltp >= item["trigger_price"]:
            triggered = True
        elif item["direction"] == "SHORT" and ltp <= item["trigger_price"]:
            triggered = True

        if not triggered:
            logger.info(
                f"{item['symbol']}: trigger not met — "
                f"LTP {ltp:.2f} vs trigger {item['trigger_price']:.2f} ({item['direction']})"
            )
            return

        # Validate risk before entering
        if not self.risk.validate_signal(
            item["trigger_price"], item["target"], item["sl"], item["direction"]
        ):
            direction = item["direction"]
            trigger = item["trigger_price"]
            target = item["target"]
            sl = item["sl"]
            if direction == "LONG" and trigger > sl:
                rr = (target - trigger) / (trigger - sl)
            elif direction == "SHORT" and sl > trigger:
                rr = (trigger - target) / (sl - trigger)
            else:
                rr = 0.0
            self.notifier.send(
                f"*TRADE REJECTED: {item['symbol']}*\n"
                f"Direction: {direction} | R:R: {rr:.2f} "
                f"(min {self.settings.MIN_RISK_REWARD:.2f})\n"
                f"Trigger: {trigger:.2f} | Target: {target:.2f} | SL: {sl:.2f}"
            )
            item["state"] = "REJECTED"
            return

        # Calculate position size
        qty = self.risk.calculate_quantity(ltp)
        if qty == 0:
            self.notifier.send(
                f"*TRADE SKIPPED: {item['symbol']}*\n"
                f"Cannot size position — LTP {ltp:.2f} too high for exposure "
                f"Rs {self.settings.TOTAL_EXPOSURE:.0f}"
            )
            item["state"] = "REJECTED"
            return

        tx_type = "BUY" if item["direction"] == "LONG" else "SELL"
        order_id = self.broker.place_market_order(item["exec_key"], tx_type, qty)

        if not order_id:
            self.notifier.send(f"*ENTRY ORDER FAILED*: {item['symbol']}")
            item["state"] = "REJECTED"
            self.risk.record_trade()
            return

        time.sleep(2)
        status, msg = self.broker.get_order_status(order_id)
        status_norm = (status or "").lower()
        if status_norm not in ("complete", "completed"):
            self.notifier.send(
                f"*ENTRY ORDER NOT CONFIRMED*: {item['symbol']}\n"
                f"Order ID: {order_id}\n"
                f"Status: {status or 'UNKNOWN'}\n"
                f"Reason: {msg or 'Check Upstox manually before continuing.'}"
            )
            item["state"] = "REJECTED"
            self.risk.record_trade()
            return

        # Record the active trade
        self.active_trade = {
            "signal_key": sig_key,
            "exec_key": item["exec_key"],
            "symbol": item["symbol"],
            "exec_symbol": item["exec_symbol"],
            "direction": item["direction"],
            "entry_price": ltp,
            "qty": qty,
            "target": item["target"],
            "sl": item["sl"],
            "order_id": order_id,
            "entry_time": datetime.now(IST),
        }

        item["state"] = "ACTIVE"
        self.risk.record_trade()
        self.state = BotState.IN_TRADE

        self.notifier.send_trade_entry(
            symbol=item["symbol"],
            direction=item["direction"],
            price=ltp,
            quantity=qty,
            target=item["target"],
            stop_loss=item["sl"],
        )

    # -----------------------------------------------------------------------
    # Phase 3: Exit Management
    # -----------------------------------------------------------------------

    def _check_exits(self) -> None:
        """Check if the active trade has hit target or stop loss."""
        if self.active_trade is None:
            return

        trade = self.active_trade
        ltp = self.broker.get_ltp(trade["signal_key"])
        if ltp is None:
            return

        should_exit = False
        reason = ""

        if trade["direction"] == "LONG":
            if ltp >= trade["target"]:
                should_exit = True
                reason = "Target Hit"
            elif ltp <= trade["sl"]:
                should_exit = True
                reason = "Stop Loss Hit"
        else:  # SHORT
            if ltp <= trade["target"]:
                should_exit = True
                reason = "Target Hit"
            elif ltp >= trade["sl"]:
                should_exit = True
                reason = "Stop Loss Hit"

        if should_exit:
            self._exit_trade(ltp, reason)

    def _eod_squareoff(self) -> None:
        """Force-close any open position at EOD."""
        if self.active_trade is None:
            return

        for attempt in range(3):
            trade = self.active_trade
            if trade is None:
                return

            ltp = self.broker.get_ltp(trade["signal_key"])
            exit_price = ltp if ltp else trade["entry_price"]
            self._exit_trade(exit_price, "EOD Square-off")

            if self.active_trade is None:
                return
            if attempt < 2:
                time.sleep(5)

        # If exit still failed after EOD attempt, alert for manual intervention
        trade = self.active_trade
        if self.active_trade is not None:
            self.notifier.send(
                f"*EOD EXIT FAILED: {trade['symbol']}*\n"
                f"Position is STILL OPEN at the broker.\n"
                f"*CLOSE MANUALLY ON UPSTOX IMMEDIATELY.*\n"
                f"Qty: {trade['qty']} | Direction: {trade['direction']}"
            )
            logger.critical(
                f"EOD square-off FAILED for {trade['symbol']}. "
                f"MANUAL close required on Upstox."
            )

    def _exit_trade(self, exit_price: float, reason: str) -> None:
        """
        Close the active trade.

        Args:
            exit_price: Price at which to exit.
            reason: Why we're exiting.
        """
        trade = self.active_trade

        # Place exit order
        tx_type = "SELL" if trade["direction"] == "LONG" else "BUY"
        order_id = self.broker.place_market_order(trade["exec_key"], tx_type, trade["qty"])

        if not order_id:
            # Order failed — keep active_trade intact so the monitoring loop retries.
            # Only send the critical alert on the first failure to avoid spam.
            attempts = trade.get("exit_attempts", 0) + 1
            trade["exit_attempts"] = attempts
            if attempts == 1:
                self.notifier.send(
                    f"*EXIT ORDER FAILED: {trade['symbol']}*\n"
                    f"Trigger: {reason}\n"
                    f"Action: {tx_type} {trade['qty']} units\n"
                    f"*MANUAL CLOSE MAY BE REQUIRED*\n"
                    f"Position remains marked active."
                )
            logger.error(
                f"Exit order failed for {trade['symbol']} (attempt {attempts}) "
                f"— position still open. Retrying next cycle."
            )
            return  # Do NOT clear active_trade

        time.sleep(2)
        status, msg = self.broker.get_order_status(order_id)
        status_norm = (status or "").lower()
        if status_norm not in ("complete", "completed"):
            attempts = trade.get("exit_attempts", 0) + 1
            trade["exit_attempts"] = attempts
            self.notifier.send(
                f"*EXIT ORDER NOT CONFIRMED: {trade['symbol']}*\n"
                f"Order ID: {order_id}\n"
                f"Status: {status or 'UNKNOWN'}\n"
                f"Reason: {msg or 'Check Upstox manually.'}\n"
                f"Bot will keep the position marked active."
            )
            logger.error(
                f"Exit order not confirmed for {trade['symbol']} "
                f"(attempt {attempts}, status={status})."
            )
            return

        # Calculate PnL
        if trade["direction"] == "LONG":
            pnl = (exit_price - trade["entry_price"]) * trade["qty"]
        else:
            pnl = (trade["entry_price"] - exit_price) * trade["qty"]

        # Notify
        self.notifier.send_trade_exit(
            symbol=trade["symbol"],
            direction=trade["direction"],
            entry_price=trade["entry_price"],
            exit_price=exit_price,
            pnl=pnl,
            reason=reason,
        )

        # Clear active trade only after confirmed exit completion.
        self.active_trade = None
        self.state = BotState.DONE

    # -----------------------------------------------------------------------
    # Utilities
    # -----------------------------------------------------------------------

    def _wait_for_scan_time(self) -> bool:
        """
        Wait until 10:15 AM IST before starting the scan.

        Returns:
            True if scan time reached, False if market is already closed.
        """
        now = datetime.now(IST)

        if now.time() >= dt_time(15, 30):
            logger.info("Market closed. Nothing to do.")
            return False

        target_time = now.replace(hour=10, minute=15, second=0, microsecond=0)
        if now < target_time:
            wait_seconds = (target_time - now).total_seconds()
            logger.info(f"Waiting {wait_seconds:.0f}s until 10:15 AM IST...")
            self.notifier.send(f"*Bot waiting* {wait_seconds/60:.0f} min until scan time")
            time.sleep(wait_seconds)

        return True
