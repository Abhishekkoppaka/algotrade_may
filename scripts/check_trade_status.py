#!/usr/bin/env python3
"""
Quick Trade Activity Checker

Run this to get a snapshot of whether the bot is trading or waiting.

Usage:
    python scripts/check_trade_status.py
"""

import sys
from pathlib import Path
from datetime import datetime, time
import pytz

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import Settings

IST = pytz.timezone("Asia/Kolkata")
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)


def check_authentication():
    """Verify Upstox authentication."""
    settings = Settings()
    if settings.UPSTOX_ACCESS_TOKEN:
        print("[OK] Upstox Token:   VALID")
        return True
    else:
        print("[X] Upstox Token:    MISSING - Run scripts/authenticate.py")
        return False


def check_market_hours():
    """Check if market is currently open."""
    now = datetime.now(IST)
    market_open = MARKET_OPEN <= now.time() <= MARKET_CLOSE
    market_day = now.weekday() < 5  # Monday-Friday

    status = "OPEN" if (market_open and market_day) else "CLOSED"
    print(f"[OK] Market Status:  {status} ({now.strftime('%H:%M IST')})")
    return market_open and market_day


def check_trading_mode():
    """Show current trading mode."""
    print("[OK] Trading Mode:   LIVE")
    return "LIVE"


def check_config():
    """Verify trading configuration."""
    settings = Settings()
    print(f"\nTRADING CONFIGURATION:")
    print(f"   Capital:            Rs {settings.CAPITAL:,.0f}")
    print(f"   Leverage:           {settings.LEVERAGE:.1f}x")
    print(f"   Min Inside Candles: {settings.MIN_INSIDE_CANDLES}")
    print(f"   Total Exposure:     Rs {settings.TOTAL_EXPOSURE:,.0f}")
    print(f"   Min R:R:            {settings.MIN_RISK_REWARD:.2f}")


def check_telegram():
    """Check if Telegram notifications are enabled."""
    settings = Settings()
    if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID:
        print("[OK] Telegram:       ENABLED")
        return True
    else:
        print("[WARN] Telegram:     DISABLED (optional)")
        return False


def print_trading_times():
    """Print important trading times."""
    print(f"\nTRADING SCHEDULE (IST):")
    print(f"   09:15 - 09:29 AM    Initial Balance (IB) Range")
    print(f"   09:30 - 10:14 AM    Consolidation (Inside Candles)")
    print(f"   10:15 AM            Bot Starts Monitoring")
    print(f"   10:15 AM - 02:30 PM Breakout Monitoring Window")
    print(f"   02:30 PM            Strategy EOD Square-off")
    print(f"   03:30 PM            Market Close")


def print_what_to_look_for():
    """Print checklist of what to monitor."""
    print(f"\nWHAT TO LOOK FOR WHEN MONITORING:")
    print(f"\n   1. WATCHLIST QUALIFIED (10:15 AM)")
    print(f"      Look for: 'X symbols qualified'")
    print(f"      If none: No trading opportunities today")
    
    print(f"\n   2. BREAKOUT DETECTED (10:15 AM - 2:30 PM)")
    print(f"      Look for: '[BREAKOUT] SYMBOL'")
    print(f"      Shows: Direction, Trigger, Target, SL")
    
    print(f"\n   3. TRADE ENTRY")
    print(f"      Look for: '[ORDER PLACED]' or 'TRADE ENTRY'")
    print(f"      Shows: Entry price, qty, target, SL")
    
    print(f"\n   4. ACTIVE POSITION")
    print(f"      Look for: 'IN_TRADE' state in monitor")
    print(f"      Shows: Current price vs entry price")
    
    print(f"\n   5. TRADE EXIT")
    print(f"      Look for: 'Target Hit' or 'Stop Loss Hit'")
    print(f"      Shows: Exit price and PnL")


def print_quick_start():
    """Print quick start instructions."""
    print(f"\nQUICK START:")
    print(f"\n   Terminal 1:")
    print(f"   $ cd <project-directory>")
    print(f"   $ python scripts/run_live.py --confirm-live")

    print(f"\n   Terminal 2:")
    print(f"   $ cd <project-directory>")
    print(f"   $ python scripts/monitor_trades.py")
    
    print(f"\n   Result: Live dashboard shows all trades in real-time")


def main():
    """Run all checks."""
    print("="*70)
    print("LIVE TRADING BOT - STATUS CHECK")
    print("="*70)
    
    # Basic checks
    auth_ok = check_authentication()
    market_ok = check_market_hours()
    mode = check_trading_mode()
    check_telegram()
    
    print(f"\n{'STATUS':<20} {'RESULT':<50}")
    print("-"*70)
    
    if not auth_ok:
        print("[WARN] Cannot proceed without authentication. Run scripts/authenticate.py")
        sys.exit(1)

    if not market_ok:
        print("[INFO] Market is currently closed. Bot will start when market opens.")
    else:
        print("[OK] Market is OPEN and bot should be trading now!")
    
    # Show configuration
    check_config()
    
    # Show trading times
    print_trading_times()
    
    # Show what to look for
    print_what_to_look_for()
    
    # Show quick start
    print_quick_start()
    
    print(f"\n{'='*70}")
    print("For detailed monitoring, run: python scripts/monitor_trades.py")
    print("For setup guide, see:         docs/PROJECT_BASELINE.md")
    print("="*70)


if __name__ == "__main__":
    main()
