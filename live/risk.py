"""
Risk Management Module

Centralized risk controls for live trading:
- Position sizing (how many shares to buy)
- Max trades per day enforcement
- EOD square-off timing
- Trade validation (reject trades with bad R:R)

All risk decisions are routed through this module.
The live engine asks RiskManager before taking any action.
"""

import logging
from datetime import datetime, time
from typing import Optional
from config.settings import Settings

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Enforces risk rules and calculates position sizes.

    The RiskManager is stateful within a trading day — it tracks
    how many trades have been taken and prevents over-trading.

    Attributes:
        settings: Configuration for capital, leverage, and limits.
        trades_today: Counter of trades executed today.
    """

    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize the risk manager.

        Args:
            settings: Configuration object with risk parameters.
        """
        self.settings = settings or Settings()
        self.trades_today = 0

    def calculate_quantity(self, price: float) -> int:
        """
        Calculate position size based on total exposure and current price.

        Formula: Quantity = Total Exposure / Price
        Total Exposure = Capital * Leverage

        Args:
            price: Current price of the instrument.

        Returns:
            Integer quantity (floored). Returns 0 if price is invalid.
        """
        if price <= 0:
            logger.warning(f"Invalid price for position sizing: {price}")
            return 0

        qty = int(self.settings.TOTAL_EXPOSURE / price)
        logger.info(
            f"Position size: {qty} units "
            f"(exposure={self.settings.TOTAL_EXPOSURE}, price={price:.2f})"
        )
        return qty

    def can_trade(self) -> bool:
        """
        Check if we're allowed to take another trade today.

        Returns:
            True if trades_today < MAX_TRADES_PER_DAY.
        """
        allowed = self.trades_today < self.settings.MAX_TRADES_PER_DAY
        if not allowed:
            logger.info(
                f"Max trades reached: {self.trades_today}/{self.settings.MAX_TRADES_PER_DAY}"
            )
        return allowed

    def record_trade(self) -> None:
        """Increment the daily trade counter."""
        self.trades_today += 1
        logger.info(f"Trade recorded. Total today: {self.trades_today}")

    def reset_daily(self) -> None:
        """Reset daily counters. Called at start of each trading day."""
        self.trades_today = 0
        logger.info("Daily risk counters reset")

    def is_eod_squareoff_time(self, current_time: time) -> bool:
        """
        Check if we've reached the end-of-day forced exit time.

        Args:
            current_time: Current time as datetime.time object.

        Returns:
            True if current time >= EOD_SQUAREOFF setting.
        """
        eod_hour = self.settings.EOD_SQUAREOFF // 100
        eod_minute = self.settings.EOD_SQUAREOFF % 100
        eod_time = time(eod_hour, eod_minute)
        return current_time >= eod_time

    def is_market_open(self, current_time: time) -> bool:
        """
        Check if current time is within market hours.

        Indian market hours: 09:15 to 15:30

        Args:
            current_time: Current time as datetime.time object.

        Returns:
            True if within market hours.
        """
        market_open = time(9, 15)
        market_close = time(15, 30)
        return market_open <= current_time <= market_close

    def validate_signal(
        self, trigger: float, target: float, stop_loss: float, direction: str
    ) -> bool:
        """
        Validate that a trade signal has acceptable risk:reward.

        Rejects signals where:
        - Target is on the wrong side of trigger
        - Stop loss is on the wrong side of trigger
        - Risk:Reward ratio is less than Settings.MIN_RISK_REWARD

        Args:
            trigger: Entry trigger price.
            target: Take profit price.
            stop_loss: Stop loss price.
            direction: "LONG" or "SHORT".

        Returns:
            True if the signal passes all validation checks.
        """
        if direction == "LONG":
            if target <= trigger or stop_loss >= trigger:
                logger.warning(f"Invalid LONG levels: trigger={trigger}, target={target}, sl={stop_loss}")
                return False
            risk = trigger - stop_loss
            reward = target - trigger
        elif direction == "SHORT":
            if target >= trigger or stop_loss <= trigger:
                logger.warning(f"Invalid SHORT levels: trigger={trigger}, target={target}, sl={stop_loss}")
                return False
            risk = stop_loss - trigger
            reward = trigger - target
        else:
            return False

        if risk <= 0:
            return False

        rr_ratio = reward / risk
        if rr_ratio < self.settings.MIN_RISK_REWARD:
            logger.info(
                "Signal rejected: R:R ratio %.2f < %.2f",
                rr_ratio,
                self.settings.MIN_RISK_REWARD,
            )
            return False

        return True
