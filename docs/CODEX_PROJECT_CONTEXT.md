# Codex Project Context

Generated: 2026-05-30

This document is a compact reference for Codex and future maintainers. It is
based on reading the project source, tests, docs, config templates, and source
data schema. It intentionally does not copy secrets from `.env`, generated
Python cache files, or bulky generated market data under `data/output/`.

## Project Summary

This is a Python algorithmic trading project for Indian markets using Upstox.
It supports:

- Upstox OAuth authentication and token storage in `.env`.
- Historical and intraday candle download.
- 1-minute backtesting for strategy modules, including the two-window pivot
  reversal strategy.
- Live 3Candle scanning and real Upstox order execution.
- Separate Nifty futures driven options spread execution for the 1+3 and
  two-window pivot reversal strategies.
- Telegram operational alerts.
- Basic live risk controls: one trade per day, exposure-based sizing, minimum
  reward:risk, and end-of-day square-off.

The repo is not currently initialized as a Git repository.

## Runtime Dependencies

Declared in `requirements.txt`:

- `requests`
- `pandas`
- `numpy`
- `python-dotenv`
- `flask`
- `matplotlib`
- `pytz`
- `pytest`

## Important Commands

Authentication:

```powershell
python scripts/authenticate.py
```

Live stock/Nifty 3Candle bot:

```powershell
python scripts/run_live.py --confirm-live
```

Nifty 1+3 options live bot:

```powershell
python scripts/run_nifty_options_live.py --confirm-live
python scripts/run_nifty_options_live.py --confirm-live --expiry 2026-05-28
```

Separate Nifty two-window pivot reversal options live bot:

```powershell
python scripts/run_nifty_two_window_pivot_reversal_options_live.py --confirm-live
```

Backtest:

```powershell
python scripts/run_backtest.py --strategy three_candle --data data/output/Data/NIFTYBEES_1min_2yr.csv
python scripts/run_backtest.py --strategy camarilla --data data/output/Data/NIFTYBEES_1min_2yr.csv
python scripts/run_backtest.py --strategy two_window_pivot_reversal --data data/output/Data/NIFTYBEES_1min_2yr.csv
```

Fetch data:

```powershell
python scripts/fetch_data.py --instrument nifty50
python scripts/fetch_data.py --instrument niftybees
python scripts/fetch_data.py --instrument all_stocks
```

Status/monitoring helpers:

```powershell
python scripts/check_trade_status.py
python scripts/monitor_trades.py
pytest
```

## Directory Map

- `backtesting/`: strategy-agnostic historical execution and metrics.
- `config/`: central settings and project paths.
- `core/`: broker, market data, and notifier integrations.
- `data/source/`: required source data, especially Nifty 50 constituents.
- `data/output/`: generated CSVs, charts, logs, and backtest outputs.
- `docs/`: baseline planning docs, trade plan, improvement plan, and this file.
- `live/`: direct stock/Nifty live trading engine and helpers.
- `options_trading/`: Nifty options package.
- `scripts/`: CLI entrypoints and operational helpers.
- `strategies/`: reusable backtest strategy implementations and indicators.
- `tests/`: pytest coverage for indicators, strategies, backtest, live setup,
  live watchlist behavior, options spread planning, and the two-window live
  adapter.

## Configuration

`config/settings.py` defines class-level settings. It loads `.env` at import
time using `python-dotenv`.

Core environment variables from `.env.example`:

- `UPSTOX_CLIENT_ID`
- `UPSTOX_CLIENT_SECRET`
- `UPSTOX_REDIRECT_URI`
- `UPSTOX_ACCESS_TOKEN`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Important hard-coded/default trading settings:

- `CAPITAL = 5000.0`
- `LEVERAGE = 5`
- `TOTAL_EXPOSURE = CAPITAL * LEVERAGE`
- `MAX_TRADES_PER_DAY = 1`
- `MIN_RISK_REWARD = 0.5`
- IB window: `09:15` to `09:29`
- Consolidation window: `09:30` to `10:14`
- Trade start: `10:15`
- Strategy square-off: `14:30`
- Market close guard in engines: `15:30`
- `MIN_INSIDE_CANDLES = 3`
- `LIVE_MONITOR_INTERVAL = 60.0`
- `LIVE_SCAN_SLEEP = 2.0`
- Two-window pivot reversal signal window: `09:45` to `14:29`
- Two-window pivot reversal square-off: `14:45`
- `PIVOT_REVERSAL_MONITOR_INTERVAL = 1`

Data paths:

- `data/source/ind_nifty50list.csv` is the required source universe file.
- `data/output/` contains generated outputs and should not be treated as source.

Upstox instrument constants:

- `NIFTY50_INDEX_KEY = "NSE_INDEX|Nifty 50"`
- `NIFTYBEES_KEY = "NSE_EQ|INF204KB14I2"`

## Source Data

`data/source/ind_nifty50list.csv` columns:

- `Company Name`
- `Industry`
- `Symbol`
- `Series`
- `ISIN Code`

`live/instruments.py` maps each row to `NSE_EQ|{ISIN Code}`. The live bot also
adds a special observer where Nifty 50 index is used as the signal instrument
and NIFTYBEES is used as the execution instrument.

## Generated Data

`data/output/` contains local historical candle archives, trade logs, backtest
reports, charts, and other generated files. This context document summarizes
them only; it does not embed their contents.

`.gitignore` excludes `.env`, `*.env`, Python caches/build outputs, virtual
environments, generated CSVs, generated PNGs, spreadsheet reports, disposable
isolated-test folders, and logs. It explicitly keeps `data/source/*.csv`.

## Core Modules

`core/broker.py`:

- `UpstoxBroker` owns Upstox REST interactions.
- Builds OAuth login URLs.
- Exchanges auth codes for access tokens.
- Places market orders through `/order/place`.
- Checks order status via `/order/history`.
- Fetches option contracts via `/option/contract`.
- Fetches live quotes and single-instrument LTP.
- Uses one `requests.Session` with auth headers.

`core/data_fetcher.py`:

- `DataFetcher` owns historical and intraday candle retrieval.
- Chunks historical requests by `FETCH_CHUNK_DAYS`.
- Fetches recent data, intraday data, combined historical + intraday data, and
  expired instruments.
- Normalizes candles into a sorted `DateTimeIndex` with OHLCV columns.
- Converts timezone-aware timestamps to naive Asia/Kolkata timestamps where
  possible.

`core/notifier.py`:

- `TelegramNotifier` sends alerts through Telegram when credentials exist.
- Logs all messages even when Telegram is disabled.
- Provides helpers for watchlists, missed breakouts, skipped symbols,
  heartbeats, trade entries, and exits.

## Strategy Layer

`strategies/base.py`:

- Defines `TradeDirection`, `Signal`, and abstract `BaseStrategy`.
- Strategies prepare data and generate signal columns.
- `Signal.risk_reward_ratio` computes reward/risk from trigger, target, and SL.

`strategies/indicators.py`:

- Calculates floor pivots from prior-day OHLC.
- Calculates CPR levels: `BC`, `TC`.
- Calculates Camarilla pivots.
- Provides sorted pivot navigation helpers:
  - `get_next_pivot_above`
  - `get_next_pivot_below`
  - `get_sorted_pivot_levels`

`strategies/three_candle.py`:

- Implements 3Candle for backtesting.
- Builds initial balance from `09:15-09:29`.
- Requires at least `MIN_INSIDE_CANDLES` fully inside candles from
  `09:30-10:14`.
- Invalidates a day when consolidation breaks IB.
- After `10:15`, detects close above IB high or below IB low.
- Sets trigger from breakout candle high/low.
- Maps targets to the nearest floor pivot, CPR level, or previous-day
  high/low.
- Maps stops to the nearest floor pivot or previous-day high/low and
  intentionally excludes CPR levels (`BC`, `TC`).
- Emits `is_reset` at and after `14:30`.

`strategies/camarilla.py`:

- Implements a 15-minute-signal/1-minute-execution Camarilla strategy.
- Supports H4/L4 breakout and L3/H3 reversal setups.
- Uses Camarilla H3/H4/H5 and L3/L4/L5 levels.
- Backtest-only in the current architecture.

`strategies/two_window_pivot_reversal.py`:

- Reuses shared daily floor pivots, CPR levels, and previous-day high/low.
- Captures first range `09:15-09:29` and second range `09:30-09:44`.
- Qualifies only when the second range strictly breaks exactly one side of the
  first range.
- Requires a one-minute close beyond the second-range trigger, then enters on
  the next one-minute open in backtests.
- Chooses the nearest strict target and stop from shared levels and the
  relevant range boundary.
- Accepts qualifying signals through `14:29` and resets open state at `14:45`.

## Backtesting

`backtesting/engine.py`:

- `BacktestEngine` is strategy-agnostic.
- Calls `strategy.prepare_data()` then `strategy.generate_signals()`.
- Simulates bar-by-bar execution.
- Uses previous-bar signal for current-bar trigger checks.
- Supports an opt-in next-minute-open fill for strategies that require it.
- Entry price is conservative:
  - Long: `max(open, trigger)`
  - Short: `min(open, trigger)`
- For same-candle entry/exit, stop is checked before target.
- EOD reset force-closes open positions at bar open.
- Tracks `MAX_TRADES_PER_DAY`.

`backtesting/metrics.py`:

- Computes total trades, return, win rate, drawdown, average win/loss, largest
  win/loss, profit factor, and long/short counts.
- Prints metrics.
- Saves trades CSV, metrics text, and equity curve PNG.

## Live Stock/Nifty Bot

Entrypoint: `scripts/run_live.py`

Live flow:

1. Requires `--confirm-live`.
2. Requires `UPSTOX_ACCESS_TOKEN`.
3. Builds observers through `live.instruments.build_observer_list()`.
4. Starts `LiveEngine`.
5. Waits until `10:15` IST unless already past that time.
6. Builds watchlist from morning setups.
7. Monitors LTP for breakouts/triggers.
8. Places real market orders.
9. Confirms orders through broker history.
10. Monitors target/SL.
11. Forces EOD square-off.

`live/setup.py`:

- `evaluate_morning_setup()` computes daily pivots from yesterday and validates
  the 3Candle morning range.
- `find_missed_breakout()` rejects setups that already broke out after `10:15`
  in the fetched candles.

`live/risk.py`:

- `RiskManager` calculates quantity as `TOTAL_EXPOSURE / price`.
- Tracks `trades_today`.
- Enforces max daily trades.
- Validates LONG/SHORT target and SL orientation.
- Rejects reward:risk below `MIN_RISK_REWARD`.
- Provides market-hours and EOD checks.

`live/engine.py`:

- State enum: `IDLE`, `SCANNING`, `WATCHLIST_READY`, `MONITORING`, `IN_TRADE`,
  `DONE`.
- Watchlist item states include `WAITING_BREAKOUT`, `WAITING_TRIGGER`,
  `SKIPPED`, `REJECTED`, and `ACTIVE`.
- Breakout checks use LTP, not candle close.
- Current live breakout trigger is set to the IB high/low, not the breakout
  candle high/low used in the backtest strategy.
- If LTP has already moved beyond target, the symbol is skipped.
- Entry order failure or unconfirmed entry records the daily trade count.
- Exit failure does not clear `active_trade`; the engine retries and alerts.
- EOD square-off retries up to 3 times, then alerts for manual intervention.

## Nifty Options Package

Entrypoints:

- `scripts/run_nifty_options_live.py`
- `scripts/run_nifty_two_window_pivot_reversal_options_live.py`

`options_trading/config.py`:

- `OptionsTradingSettings` extends `Settings`.
- Reads options-specific values from the root `.env`.
- Required live settings:
  - `UPSTOX_ACCESS_TOKEN`
  - `NIFTY_FUTURES_KEY`

Options-specific `.env` keys documented in `options_trading/.env.example`:

- `NIFTY_FUTURES_KEY`
- `NIFTY_OPTION_LOTS`
- `NIFTY_OPTION_STRIKE_STEP`
- `NIFTY_OPTION_SELL_OFFSET`
- `NIFTY_OPTION_HEDGE_OFFSET`
- `NIFTY_OPTION_PRODUCT`
- `PIVOT_REVERSAL_MONITOR_INTERVAL`

`options_trading/models.py`:

- `OptionLeg`
- `SpreadPlan`

`options_trading/strategies/nifty_futures_breakout.py`:

- Reuses `live.setup.evaluate_morning_setup()` and `find_missed_breakout()`.
- Returns `LONG`, `SHORT`, or `None` from futures LTP.

`options_trading/execution/nifty_spread_planner.py`:

- Rounds futures LTP to nearest strike.
- LONG futures signal creates a call credit spread:
  - Sell OTM CE at base + sell offset.
  - Buy farther OTM CE at base + hedge offset.
- SHORT futures signal creates a put credit spread:
  - Sell OTM PE at base - sell offset.
  - Buy farther OTM PE at base - hedge offset.
- Selects nearest current/future expiry unless a specific expiry is supplied.

`options_trading/engines/nifty_options_live.py`:

- Waits until `10:15` IST.
- Prepares futures 3Candle setup.
- Monitors futures LTP.
- Fetches Nifty option contracts.
- Builds a spread plan.
- Places and confirms hedge leg first, then short leg.
- Holds spread until EOD square-off.
- Exits short leg first, then hedge leg.
- Alerts if any leg fails or remains unconfirmed.

`options_trading/strategies/nifty_futures_two_window_pivot_reversal.py`:

- Adapts the shared two-window pivot reversal strategy to futures candles.
- Reuses the existing options strike mapping and spread execution workflow.

`options_trading/engines/nifty_two_window_pivot_reversal_live.py`:

- Runs independently from the active 1+3 runner.
- Places one options spread after the futures trigger close and a valid next
  live futures price.
- Exits immediately when futures LTP reaches target.
- Exits on stop only when a newly completed aligned five-minute futures candle
  closes beyond stop.
- Force-closes at `14:45`.
- Stops automatic retries after a partial exit failure.

## Scripts

`scripts/authenticate.py`:

- Starts local Flask callback server on `127.0.0.1:5000/callback`.
- Prints Upstox login URL.
- Exchanges callback code for access token.
- Writes `UPSTOX_ACCESS_TOKEN` to `.env`.

`scripts/fetch_data.py`:

- Fetches `nifty50`, `niftybees`, `all_stocks`, or a supplied instrument key.
- Writes output CSVs under `data/output/Data/`.
- Skips a symbol if the target file already exists.

`scripts/run_backtest.py`:

- Strategy registry: `three_candle`, `camarilla`, `two_window_pivot_reversal`.
- Reads CSV with `timestamp` index.
- Removes timezone if present.
- Runs backtest, prints metrics, saves report.

`scripts/check_trade_status.py`:

- Prints token presence, market status, live mode, Telegram status, current
  config, trading schedule, and monitoring checklist.

`scripts/monitor_trades.py`:

- Console dashboard that captures logs in memory.
- Tracks state, alerts, active trades, breakouts, and checklist information.
- It is standalone and currently infers activity mostly from in-process logs.

`scripts/run_nifty_two_window_pivot_reversal_options_live.py`:

- Starts the separate futures-driven two-window pivot reversal options runner.

## Tests

Current tests cover:

- Floor pivot calculations and pivot navigation.
- 3Candle signal generation.
- EOD reset behavior.
- Backtest engine shape and metrics.
- Live morning setup qualification/rejection.
- Missed breakout detection.
- Live watchlist behavior around pre-start breakouts.
- Nifty options spread planning for call and put credit spreads.
- CPR calculations.
- Two-window qualification, stale-signal handling, and next-open invalidation.
- Long and short hybrid live exits and five-minute stop API throttling.
- Partial-exit retry protection.

Current baseline: `52 passed`.

Known test gaps from the code and docs:

- `RiskManager` edge cases.
- Broker calls with mocked Upstox responses.
- DataFetcher retries and normalization.
- Live trigger/entry/exit decision functions in isolation.
- Options live engine order-failure paths.
- Persistent state and restart/recovery, once implemented.

## Existing Planning Docs

`docs/PROJECT_BASELINE.md`:

- Existing source-of-truth baseline.
- Details purpose, runtime flows, strategy logic, modularity, cloud/static IP
  considerations, risks, tests, source-control baseline, decisions, and open
  questions.

`docs/PROJECT_IMPROVEMENT_PLAN.md`:

- Roadmap from local development to cloud-ready trading system.
- Phases include repository hygiene, config hardening, auth redesign, strategy
  interface unification, live engine decomposition, execution safety,
  persistent state, observability, cloud deployment, and strategy expansion.

`docs/trade_plan.md`:

- Human-readable 3Candle trade plan.
- States that live execution is real-only and must use
  `python scripts/run_live.py --confirm-live`.

`docs/two_window_pivot_reversal_trade_plan.md`:

- Human-readable two-window pivot reversal rules and live operating notes.

## Important Architecture Notes

- Live and backtest 3Candle behavior are similar but not fully unified.
- Backtest breakout detection uses candle close and breakout candle high/low as
  trigger.
- Live stock/Nifty engine currently detects breakout using LTP and uses the IB
  high/low as trigger.
- Live engine owns too many responsibilities: scanning, breakout state, entries,
  exits, retries, notifications, and lifecycle state.
- Runtime live state is in memory only. A process restart loses watchlist,
  active trade, order ids, and trade counters.
- Entry failure or unconfirmed entry consumes the one-trade-per-day counter.
  That may be intentional as a safety brake, but it affects retry behavior.
- Settings are class attributes loaded at import time, which keeps simple usage
  but makes validation and test isolation weaker.
- `.env` is the local secret/token store. It is not suitable for cloud
  production.
- Order reconciliation with broker positions/order book is not implemented.
- There is no persistent kill switch yet.
- The options engine buys the hedge first and exits the short leg first, which
  is the safer ordering for credit spreads.

## Safety Notes

- `scripts/run_live.py`, `scripts/run_nifty_options_live.py`, and
  `scripts/run_nifty_two_window_pivot_reversal_options_live.py` place real
  Upstox market orders when confirmed.
- Do not run them without reviewing `.env`, the active token, instrument keys,
  market hours, and capital/leverage settings.
- Do not store `.env` contents in docs or version control.
- Treat `data/output/` as generated artifacts, not source.

## Suggested Next Work

Most valuable near-term improvements:

1. Add validated instance settings and startup checks.
2. Split authentication into an importable module plus thin CLI.
3. Extract live breakout/trigger logic into testable pure functions.
4. Align live and backtest 3Candle trigger semantics or document the intentional
   difference.
5. Add tests for `RiskManager`, broker mocks, data fetcher normalization, and
   options engine failure paths.
6. Add persistent live state and broker reconciliation before unattended use.
7. Add replay or mocked-broker simulation for both options runners.
