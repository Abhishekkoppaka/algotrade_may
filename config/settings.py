"""
Centralized configuration for the entire trading system.

All constants, environment variables, and tunable parameters live here.
No other module should read from .env directly or define trading constants.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Environment Setup
# ---------------------------------------------------------------------------

# Project root is the parent of the config/ directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

load_dotenv(ENV_PATH)


class Settings:
    """
    Single source of truth for all configuration values.

    Usage:
        from config.settings import Settings
        settings = Settings()
        print(settings.UPSTOX_ACCESS_TOKEN)
    """

    # ------ Upstox API Credentials ------
    UPSTOX_CLIENT_ID: str = os.getenv("UPSTOX_CLIENT_ID", "")
    UPSTOX_CLIENT_SECRET: str = os.getenv("UPSTOX_CLIENT_SECRET", "")
    UPSTOX_REDIRECT_URI: str = os.getenv("UPSTOX_REDIRECT_URI", "http://127.0.0.1:5000/callback")
    UPSTOX_ACCESS_TOKEN: str = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip("'").strip('"')

    # ------ Telegram Notifications ------
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip("'").strip('"')
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "").strip("'").strip('"')

    # ------ Trading Parameters ------
    # Base capital in INR
    CAPITAL: float = 5_000.0
    # Leverage multiplier (5x means total exposure = CAPITAL * 5)
    LEVERAGE: int = 5
    # Maximum position size in INR
    TOTAL_EXPOSURE: float = CAPITAL * LEVERAGE
    # Maximum number of trades allowed per day per strategy
    MAX_TRADES_PER_DAY: int = 1
    # Minimum reward:risk ratio allowed for live entries
    MIN_RISK_REWARD: float = 0.5

    # ------ Time Windows (IST, 24-hour format as HHMM integers) ------
    # Initial Balance formation window
    IB_START: int = 915
    IB_END: int = 929
    # Consolidation check window (candles must stay inside IB)
    CONSOLIDATION_START: int = 930
    CONSOLIDATION_END: int = 1014
    # Active trading window
    TRADE_START: int = 1015
    TRADE_END: int = 1429
    # End-of-day forced square-off time
    EOD_SQUAREOFF: int = 1430
    # Minimum inside candles required for valid setup
    MIN_INSIDE_CANDLES: int = 3

    # ------ Two-Window Pivot Reversal Strategy ------
    # Entry signals are accepted after the two 15-minute windows are complete.
    PIVOT_REVERSAL_ENTRY_START: int = 945
    # A 14:29 close may still create an entry during the following minute.
    PIVOT_REVERSAL_LAST_SIGNAL: int = 1429
    # Open positions are closed at the 14:45 candle open.
    PIVOT_REVERSAL_SQUAREOFF: int = 1445

    # ------ Data Fetching ------
    # Number of days per chunk when fetching historical data (Upstox limit ~30 days)
    FETCH_CHUNK_DAYS: int = 20
    # Default historical lookback in days
    DEFAULT_LOOKBACK_DAYS: int = 730
    # API rate limit sleep between requests (seconds)
    API_RATE_LIMIT_SLEEP: float = 60.0
    # Pause between per-instrument live scan requests (seconds)
    LIVE_SCAN_SLEEP: float = 2.0
    # Default candle interval
    DEFAULT_INTERVAL: str = "1minute"
    # Interval between monitoring checks in the live engine (seconds)
    LIVE_MONITOR_INTERVAL: float = 60.0

    # ------ File Paths ------
    DATA_DIR: Path = PROJECT_ROOT / "data"
    OUTPUT_DIR: Path = DATA_DIR / "output"
    SOURCE_DIR: Path = DATA_DIR / "source"
    STOCK_LIST_PATH: Path = SOURCE_DIR / "ind_nifty50list.csv"

    # ------ Instrument Keys ------
    # Nifty 50 Index (used for signal generation)
    NIFTY50_INDEX_KEY: str = "NSE_INDEX|Nifty 50"
    # NIFTYBEES ETF (used for execution when trading index signal)
    NIFTYBEES_KEY: str = "NSE_EQ|INF204KB14I2"

    # ------ API Base URLs ------
    UPSTOX_BASE_URL: str = "https://api.upstox.com/v2"
    UPSTOX_V3_BASE_URL: str = "https://api.upstox.com/v3"

    @property
    def auth_headers(self) -> dict:
        """Standard authorization headers for all Upstox API calls."""
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.UPSTOX_ACCESS_TOKEN}"
        }

    def __repr__(self) -> str:
        return (
            f"Settings(CAPITAL={self.CAPITAL}, "
            f"LEVERAGE={self.LEVERAGE}x)"
        )
