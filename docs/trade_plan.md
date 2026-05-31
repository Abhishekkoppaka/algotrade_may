# 3Candle Strategy Trade Plan

This document serves as the master blueprint for your automated trading system. It outlines the logical rules, risk management parameters, and operational details of the `live_bot.py` engine.

---

## 1. Core Philosophy
The "3Candle" strategy is an intraday momentum and breakout system designed to capitalize on range expansion. It identifies periods of consolidation following the market open and enters trades when price breaks out of the established morning range.

---

## 2. Setup Conditions (The "Watchlist")

The engine scans all 50 constituent stocks of the Nifty 50 Index. For a stock to be added to the Daily Watchlist, it must meet **all** of the following criteria between 09:15 and 10:14 AM:

1. **Initial Balance (IB) Formation:**
   - The bot records the Absolute High (`d15_high`) and Absolute Low (`d15_low`) of the first 15 minutes of trading (09:15 to 09:29).
2. **Inside Candle Generation:**
   - Between 09:30 and 10:14, the bot counts "Inside Candles". 
   - An Inside Candle is defined as a 1-minute candle whose High is strictly less than `d15_high` AND whose Low is strictly greater than `d15_low`.
   - **Requirement:** At least 3 Inside Candles must form during this 60-minute window.
3. **Range Integrity:**
   - The IB range must remain completely unbroken between 09:30 and 10:14.
   - If *any* 1-minute candle touches or exceeds `d15_high` or `d15_low` during this window, the stock is immediately invalidated for the day.

---

## 3. Entry Execution (10:15 AM to 14:30 PM)

If a stock survives the morning scan and is added to the Watchlist, the bot begins active monitoring at 10:15 AM.

### Trigger Logic
- **LONG Entry:** A 1-minute candle must **close** above the `d15_high`. 
  - Once this happens, the absolute High of that specific breakout candle becomes the `Buy Trigger`.
  - The bot then waits for the live price to cross the `Buy Trigger`.
- **SHORT Entry:** A 1-minute candle must **close** below the `d15_low`.
  - Once this happens, the absolute Low of that specific breakout candle becomes the `Sell Trigger`.
  - The bot then waits for the live price to cross the `Sell Trigger`.

### Risk & Capital Rules
- **Base Capital:** Rs 10,000.
- **Leverage:** 5x Margin (Total Exposure = Rs 50,000).
- **Position Sizing:** `Quantity = 50,000 / Current Price`.
- **Trade Limit:** Strictly **1 Trade Per Day**. 
  - If multiple stocks are on the Watchlist, the bot will take the *first* stock that hits its trigger. All other stocks are instantly ignored to prevent overtrading.

---

## 4. Exit Rules (Targets & Stops)

The strategy uses Daily Floor Pivots, CPR levels, and previous-day high/low
(calculated using the previous day's High, Low, and Close) to map out exact
Take Profit and Stop Loss levels.

- **LONG Trade Exits:**
  - **Target:** The next immediate Pivot, CPR (`BC` or `TC`), or previous-day
    high/low level *above* the Entry Price.
  - **Stop Loss:** The next immediate Pivot or previous-day high/low level
    *below* the Entry Price. CPR levels are ignored.
- **SHORT Trade Exits:**
  - **Target:** The next immediate Pivot, CPR (`BC` or `TC`), or previous-day
    high/low level *below* the Entry Price.
  - **Stop Loss:** The next immediate Pivot or previous-day high/low level
    *above* the Entry Price. CPR levels are ignored.

### Time-Based Square Off
If neither the Target nor the Stop Loss is hit by **14:30 (2:30 PM) IST**, the bot will execute a hard square-off at the current market price (LTP) and cease operations for the day.

---

## 5. System Operations (Live Bot)

The `live_bot.py` script is a completely autonomous daemon.

- **10:15 AM:** Wakes up, pulls historical data, calculates pivots, and identifies Watchlist stocks.
- **Alert System:** Fully integrated with Telegram. You will receive notifications for:
  - The Morning Watchlist
  - Breakout Detected (Trigger Setting)
  - Trade Entered (with qty, target, and stop loss)
  - Trade Closed (Target Hit / Stop Loss Hit / 14:30 Square-Off) with calculated P&L.
- **Execution Mode:** The local bot is live-only and must be started with
  `python scripts/run_live.py --confirm-live`.
  - The bot calls the Upstox `v2/order/place` API for entry and exit MARKET
    orders.
  - Backtesting remains available through `scripts/run_backtest.py`; there is
    no simulated execution branch in the live runner.

The separate two-window pivot reversal options strategy is documented in
`docs/two_window_pivot_reversal_trade_plan.md`.
