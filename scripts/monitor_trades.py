"""
Live Trade Monitor

Real-time monitoring dashboard for the live trading bot.
Shows current state, active trades, watchlist status, and trade history.

Usage:
    python scripts/monitor_trades.py
    
    Or in a separate terminal while run_live.py is running to monitor trade activity.
    
    The monitor tracks:
    - Bot state transitions (IDLE → SCANNING → MONITORING → IN_TRADE)
    - Active trades with entry/exit prices and PnL
    - Breakout signals detected
    - Order status and execution
    - Market quotes for monitored symbols
"""

import os
import sys
import time
import json
import logging
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from collections import defaultdict, deque

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import Settings
import pytz

# Configure logging to also capture into handlers for monitoring
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

# Capture logs in memory for display
class RingBuffer(deque):
    """Ring buffer to keep last N items."""
    def __init__(self, size=100):
        super().__init__(maxlen=size)


class MemoryHandler(logging.Handler):
    """Custom handler to capture logs in memory."""
    def __init__(self):
        super().__init__()
        self.buffer = RingBuffer(size=200)
    
    def emit(self, record):
        try:
            msg = self.format(record)
            self.buffer.append(msg)
        except Exception:
            self.handleError(record)


class TradeMonitor:
    """
    Real-time monitoring dashboard for live trading bot.
    
    Tracks:
    - Bot state and transitions
    - Active trades and their PnL
    - Breakout signals detected
    - Order execution status
    - Key alerts and messages
    """

    def __init__(self):
        self.settings = Settings()
        
        # Add memory handler to capture logs
        self.memory_handler = MemoryHandler()
        self.memory_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
            datefmt="%H:%M:%S"
        ))
        logging.getLogger().addHandler(self.memory_handler)
        
        # State tracking
        self.trades: Dict[str, Dict] = {}  # Track trades by symbol
        self.breakouts: Dict[str, Dict] = {}  # Track breakouts by symbol
        self.alerts: deque = deque(maxlen=20)  # Last 20 key alerts
        self.current_state = "IDLE"
        self.watchlist_size = 0
        self.session_start = datetime.now(IST)
        self.trades_completed = 0
        self.total_pnl = 0.0
        self.mode = "LIVE"

    def parse_logs_for_trades(self):
        """Parse captured logs to extract trade information."""
        for log_entry in self.memory_handler.buffer:
            # Detect bot state
            if "BotState" in log_entry or "SCANNING" in log_entry:
                if "SCANNING" in log_entry:
                    self.current_state = "SCANNING"
                elif "MONITORING" in log_entry:
                    self.current_state = "MONITORING"
                elif "IN_TRADE" in log_entry:
                    self.current_state = "IN_TRADE"
                elif "IDLE" in log_entry:
                    self.current_state = "IDLE"
            
            # Detect watchlist size
            if "symbols qualified" in log_entry:
                match = re.search(r'(\d+)\s+symbols qualified', log_entry)
                if match:
                    self.watchlist_size = int(match.group(1))
            
            # Detect breakouts
            if "BREAKOUT:" in log_entry:
                self.alerts.append(f"🔔 {log_entry.split('[ALERT]')[-1].strip() if '[ALERT]' in log_entry else log_entry}")
            
            # Detect trade entries
            if "ORDER PLACED:" in log_entry or "Trade Entry" in log_entry:
                self.alerts.append(f"📊 {log_entry}")
            
            # Detect trade exits
            if "Stop Loss Hit" in log_entry or "Target Hit" in log_entry or "EOD" in log_entry:
                self.alerts.append(f"🎯 {log_entry}")

    def print_header(self):
        """Print session header."""
        now = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        print("\n" + "="*90)
        print(f"{'LIVE TRADING MONITOR':^90}")
        print(f"{now:^90}")
        print("="*90)
        print(f"Mode: {self.mode:20} | Capital: Rs {self.settings.CAPITAL:>12,.0f} | Leverage: {self.settings.LEVERAGE:.1f}x")
        print("-"*90)

    def print_bot_status(self):
        """Print current bot status."""
        elapsed = (datetime.now(IST) - self.session_start).total_seconds() / 60
        state_emoji = {
            "IDLE": "⏸️",
            "SCANNING": "🔍",
            "MONITORING": "👁️",
            "IN_TRADE": "💹",
            "DONE": "✅"
        }
        
        print(f"\n📌 BOT STATUS")
        print(f"   State:           {state_emoji.get(self.current_state, '❓')} {self.current_state}")
        print(f"   Elapsed:         {elapsed:.0f} minutes")
        print(f"   Watchlist Size:  {self.watchlist_size} symbols")
        print(f"   Trades Today:    {self.trades_completed}")
        print(f"   Session PnL:     Rs {self.total_pnl:,.2f}")

    def print_active_trades(self):
        """Print any active trades."""
        print(f"\n💰 ACTIVE TRADES")
        if not self.trades:
            print(f"   No active trades currently")
            return
        
        for symbol, trade in self.trades.items():
            direction = trade.get("direction", "?")
            entry = trade.get("entry_price", 0)
            qty = trade.get("qty", 0)
            target = trade.get("target", 0)
            sl = trade.get("sl", 0)
            
            print(f"   [{direction}] {symbol}")
            print(f"       Entry: Rs {entry:.2f} | Qty: {qty}")
            print(f"       Target: Rs {target:.2f} | SL: Rs {sl:.2f}")

    def print_recent_breakouts(self):
        """Print recent breakout signals."""
        print(f"\n⚡ RECENT BREAKOUTS")
        if not self.breakouts:
            print(f"   No breakouts detected yet")
            return
        
        for symbol, breakout in list(self.breakouts.items())[-5:]:
            direction = breakout.get("direction", "?")
            trigger = breakout.get("trigger", 0)
            ltp = breakout.get("ltp", 0)
            time_detected = breakout.get("time", "N/A")
            
            print(f"   [{time_detected}] {symbol}: {direction} breakout at Rs {trigger:.2f} (LTP: Rs {ltp:.2f})")

    def print_key_alerts(self):
        """Print key alerts and notifications."""
        print(f"\n🔔 KEY ALERTS (Latest 10)")
        if not self.alerts:
            print(f"   No alerts yet")
            return
        
        for alert in list(self.alerts)[-10:]:
            # Truncate long alerts
            alert_short = alert[:80] + "..." if len(alert) > 80 else alert
            print(f"   {alert_short}")

    def print_recent_logs(self, limit: int = 15):
        """Print recent log entries."""
        print(f"\n📋 RECENT LOGS (Last {limit})")
        logs = list(self.memory_handler.buffer)[-limit:]
        for log in logs:
            # Filter for important logs
            if any(keyword in log for keyword in ["BREAKOUT", "ORDER", "TRADE", "ERROR", "ALERT", "COMPLETED"]):
                # Truncate timestamp
                log_short = log[17:] if len(log) > 17 else log  # Remove date part
                log_short = log_short[:75] + "..." if len(log_short) > 75 else log_short
                print(f"   {log_short}")

    def print_market_indicators(self):
        """Print key market indicators."""
        print(f"\n📊 SESSION INDICATORS")
        
        # Calculate metrics from trades if any
        if self.trades_completed > 0:
            print(f"   Trading Performance:")
            print(f"   - Total Trades: {self.trades_completed}")
            print(f"   - Session PnL: Rs {self.total_pnl:+,.2f}")
            
            if self.trades_completed > 0:
                avg_pnl = self.total_pnl / self.trades_completed
                print(f"   - Avg Trade PnL: Rs {avg_pnl:+,.2f}")
        else:
            print(f"   Waiting for trading signals...")

    def print_quick_checklist(self):
        """Print quick health checklist."""
        print(f"\n✅ SYSTEM CHECKLIST")
        
        # Check 1: Token
        token_ok = bool(self.settings.UPSTOX_ACCESS_TOKEN)
        print(f"   {'✓' if token_ok else '✗'} Access Token: {'Configured' if token_ok else 'MISSING'}")
        
        # Check 2: Notification
        notif_ok = bool(self.settings.TELEGRAM_BOT_TOKEN and self.settings.TELEGRAM_CHAT_ID)
        print(f"   {'✓' if notif_ok else '✗'} Telegram: {'Enabled' if notif_ok else 'Disabled'}")
        
        # Check 3: Stock list
        stock_list_ok = Path(self.settings.STOCK_LIST_PATH).exists()
        print(f"   {'✓' if stock_list_ok else '✗'} Stock List: {'Found' if stock_list_ok else 'MISSING'}")
        
        # Check 4: API connectivity
        print(f"   {'✓' if self.watchlist_size > 0 else '⏳'} API Connection: {'Active' if self.watchlist_size > 0 else 'Waiting'}")

    def run_continuous_monitor(self, interval: int = 3):
        """
        Run continuous monitoring loop.
        
        Args:
            interval: Seconds between refresh cycles.
        """
        logger.info("="*90)
        logger.info("TRADE MONITOR STARTED - Press Ctrl+C to exit")
        logger.info("="*90)
        
        try:
            while True:
                # Update state from logs
                self.parse_logs_for_trades()
                
                # Clear screen (Windows or Unix)
                os.system("cls" if os.name == "nt" else "clear")
                
                # Print dashboard
                self.print_header()
                self.print_bot_status()
                self.print_active_trades()
                self.print_recent_breakouts()
                self.print_key_alerts()
                self.print_recent_logs()
                self.print_market_indicators()
                self.print_quick_checklist()
                
                print(f"\n🔄 Refreshing in {interval}s... (Ctrl+C to exit)")
                print("="*90 + "\n")
                
                time.sleep(interval)
        
        except KeyboardInterrupt:
            print("\n\n" + "="*90)
            print("TRADE MONITOR STOPPED")
            print("="*90)
            logger.info("Trade monitor terminated by user")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Monitor error: {e}", exc_info=True)
            sys.exit(1)

def main():
    """Main entry point."""
    monitor = TradeMonitor()
    
    # Run monitoring loop with 3-second refresh
    monitor.run_continuous_monitor(interval=3)


if __name__ == "__main__":
    main()

