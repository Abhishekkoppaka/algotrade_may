"""
Configuration for the options trading package.

The package still reads the project root `.env`, but option-specific settings
live here so the Nifty options strategy can evolve independently from the older
stock live bot.
"""

import os

from config.settings import Settings


class OptionsTradingSettings(Settings):
    """Settings required by the Nifty options trading runner."""

    NIFTY_FUTURES_KEY: str = os.getenv("NIFTY_FUTURES_KEY", "")
    NIFTY_OPTION_LOTS: int = int(os.getenv("NIFTY_OPTION_LOTS", "1"))
    NIFTY_OPTION_STRIKE_STEP: int = int(os.getenv("NIFTY_OPTION_STRIKE_STEP", "50"))
    NIFTY_OPTION_SELL_OFFSET: int = int(os.getenv("NIFTY_OPTION_SELL_OFFSET", "500"))
    NIFTY_OPTION_HEDGE_OFFSET: int = int(os.getenv("NIFTY_OPTION_HEDGE_OFFSET", "1000"))
    NIFTY_OPTION_PRODUCT: str = os.getenv("NIFTY_OPTION_PRODUCT", "I")
    PIVOT_REVERSAL_MONITOR_INTERVAL: float = float(
        os.getenv("PIVOT_REVERSAL_MONITOR_INTERVAL", "1")
    )

    def validate_for_live(self) -> list[str]:
        """Return missing settings that block live options trading."""
        missing = []
        if not self.UPSTOX_ACCESS_TOKEN:
            missing.append("UPSTOX_ACCESS_TOKEN")
        if not self.NIFTY_FUTURES_KEY:
            missing.append("NIFTY_FUTURES_KEY")
        return missing
