"""
Notification System

Provides a unified interface for sending alerts to external services.
Currently supports Telegram. Designed to be extended with Discord, email, etc.

All notifications go through this module — no other file should call
the Telegram API directly.
"""

import logging
import requests
from typing import Optional
from config.settings import Settings

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Sends formatted messages to a Telegram chat via Bot API.

    The notifier silently degrades to console-only output if
    Telegram credentials are not configured.

    Attributes:
        bot_token: Telegram bot API token.
        chat_id: Target chat/group ID for messages.
        enabled: Whether Telegram sending is active.
    """

    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize the Telegram notifier.

        Args:
            settings: Configuration object. Creates default if not provided.
        """
        self.settings = settings or Settings()
        self.bot_token = self.settings.TELEGRAM_BOT_TOKEN
        self.chat_id = self.settings.TELEGRAM_CHAT_ID
        # Only enable if both token and chat_id are properly configured
        self.enabled = bool(self.bot_token and self.chat_id)

        if not self.enabled:
            logger.warning("Telegram notifier disabled: missing bot token or chat ID")

    def send(self, message: str, parse_mode: str = "Markdown") -> bool:
        """
        Send a message to the configured Telegram chat.

        Always logs the message to console regardless of Telegram status.
        Escapes underscores for Markdown compatibility.

        Args:
            message: The message text to send.
            parse_mode: Telegram parse mode ("Markdown" or "HTML").

        Returns:
            True if sent successfully (or logging-only mode), False on failure.
        """
        # Always log locally — Telegram is a bonus, not the primary output
        logger.info(f"[ALERT] {message}")

        if not self.enabled:
            return True  # Graceful degradation: logging counts as success

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            # Escape underscores which Markdown interprets as italic markers
            "text": message.replace("_", "\\_"),
            "parse_mode": parse_mode,
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                return True
            else:
                logger.error(f"Telegram API error ({response.status_code}): {response.text}")
                return False
        except requests.Timeout:
            logger.error("Telegram send timed out")
            return False
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    def send_trade_entry(
        self,
        symbol: str,
        direction: str,
        price: float,
        quantity: int,
        target: float,
        stop_loss: float,
    ) -> bool:
        """
        Send a formatted trade entry notification.

        Args:
            symbol: Trading symbol name.
            direction: "LONG" or "SHORT".
            price: Entry price.
            quantity: Position size.
            target: Target price level.
            stop_loss: Stop loss price level.

        Returns:
            True if sent successfully.
        """
        msg = (
            f"*TRADE ENTERED (LIVE)*\n"
            f"Symbol: {symbol}\n"
            f"Direction: {direction}\n"
            f"Price: {price:.2f}\n"
            f"Qty: {quantity}\n"
            f"Target: {target:.2f}\n"
            f"SL: {stop_loss:.2f}"
        )
        return self.send(msg)

    def send_trade_exit(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        exit_price: float,
        pnl: float,
        reason: str,
    ) -> bool:
        """
        Send a formatted trade exit notification.

        Args:
            symbol: Trading symbol name.
            direction: "LONG" or "SHORT".
            entry_price: Original entry price.
            exit_price: Exit price achieved.
            pnl: Profit/Loss in INR.
            reason: Exit reason ("Target", "Stop Loss", "EOD Square-off").

        Returns:
            True if sent successfully.
        """
        emoji = "TARGET HIT" if "Target" in reason else "STOP LOSS" if "Stop" in reason else "EOD EXIT"
        msg = (
            f"*{emoji} (LIVE)*\n"
            f"Symbol: {symbol}\n"
            f"Direction: {direction}\n"
            f"Entry: {entry_price:.2f} | Exit: {exit_price:.2f}\n"
            f"P&L: Rs {pnl:.2f}\n"
            f"Reason: {reason}"
        )
        return self.send(msg)

    def send_watchlist(self, watchlist: dict) -> bool:
        """
        Send the daily qualified watchlist summary.

        Args:
            watchlist: Dictionary of qualified symbols and their setup data.

        Returns:
            True if sent successfully.
        """
        if not watchlist:
            return self.send("No setups qualified today. System idle.")

        msg = f"*Watchlist Qualified ({len(watchlist)} Symbols)*\n"
        for key, data in watchlist.items():
            name = data.get("symbol", key)
            msg += f"- {name} (H: {data.get('d15_high', 0):.2f}, L: {data.get('d15_low', 0):.2f})\n"
        return self.send(msg)

    def send_missed_breakouts(self, missed: list) -> bool:
        """
        Alert stocks skipped because they broke out before the bot started.

        Args:
            missed: List of dicts with keys: symbol, direction, d15_high,
                    d15_low, breakout_price, breakout_time, current_ltp.

        Returns:
            True if sent successfully.
        """
        if not missed:
            return True

        msg = f"*Skipped Pre-Start Breakouts ({len(missed)}) — Bot Started Late*\n"
        for m in missed:
            trigger = m["d15_high"] if m["direction"] == "LONG" else m["d15_low"]
            msg += (
                f"- {m['symbol']} | {m['direction']}\n"
                f"  IB Range: {m['d15_low']:.2f} – {m['d15_high']:.2f}\n"
                f"  Broke {trigger:.2f} at {m['breakout_time']} "
                f"(close: {m['breakout_price']:.2f})\n"
                f"  Current LTP: {m['current_ltp']:.2f}\n"
                f"  Action: skipped for today; waiting only for fresh breakouts.\n"
            )
        return self.send(msg)

    def send_heartbeat(self, monitoring_count: int, elapsed_min: int) -> bool:
        """
        Send a bot-alive ping with current monitoring status.

        Args:
            monitoring_count: Number of stocks still being watched for breakouts.
            elapsed_min: Minutes since the monitoring loop started.

        Returns:
            True if sent successfully.
        """
        msg = (
            f"*Bot Active* — No trade yet\n"
            f"Monitoring: {monitoring_count} stock(s)\n"
            f"Time active: {elapsed_min} min"
        )
        return self.send(msg)

    def send_skipped_summary(self, skipped: list) -> bool:
        """
        Send a summary of stocks that were skipped because price already
        moved past the trigger/target.

        Args:
            skipped: List of dicts with keys: symbol, direction, trigger,
                     ltp, target, time.

        Returns:
            True if sent successfully.
        """
        if not skipped:
            return True

        msg = f"*Skipped Stocks ({len(skipped)})*\n"
        for s in skipped:
            msg += (
                f"- {s['symbol']} | {s['direction']}\n"
                f"  Trigger: {s['trigger']:.2f} | LTP: {s['ltp']:.2f} | "
                f"Target: {s['target']:.2f}\n"
                f"  Time: {s['time']}\n"
            )
        return self.send(msg)
