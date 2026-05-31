# Trading Bot Project Baseline

This document is the working source of truth for the project. Use it when
planning changes, reviewing architecture, adding strategies, moving to cloud
deployment, or deciding what should be modularized next.

## 1. Project Purpose

The project is an algorithmic intraday trading system for Indian markets using
Upstox as the broker and market data provider. It supports:

- Historical data download from Upstox.
- Backtesting strategy logic on 1-minute OHLCV data.
- Live scanning of Nifty 50 index and Nifty 50 constituents.
- Confirmed live order execution through Upstox.
- Separate Nifty futures-driven options spread runners for the 1+3 and
  two-window pivot reversal strategies.
- Telegram notifications for operational visibility.
- Basic risk controls such as max trades per day, position sizing, minimum
  reward:risk, and forced end-of-day square-off.

The currently active live flow uses:

- `scripts/authenticate.py`
- `scripts/run_live.py`
- `live/engine.py`
- `live/instruments.py`
- `live/setup.py`
- `live/risk.py`
- `core/broker.py`
- `core/data_fetcher.py`
- `core/notifier.py`
- `config/settings.py`

## 2. Current Directory Structure

```text
backtesting/
  engine.py          Generic bar-by-bar backtest execution engine.
  metrics.py         Backtest metrics, report, and equity curve output.

config/
  settings.py        Central settings, environment loading, paths, constants.

core/
  broker.py          Upstox OAuth, order placement, order status, live quotes.
  data_fetcher.py    Historical and intraday Upstox candle data retrieval.
  notifier.py        Telegram notification interface.

data/
  source/            Small source data required by the app, such as Nifty list.
  output/            Generated data, reports, charts, logs, and backtest output.

docs/
  PROJECT_BASELINE.md        This source-of-truth document.
  PROJECT_IMPROVEMENT_PLAN.md Project improvement roadmap.
  trade_plan.md              3Candle trading rules and operating notes.
  two_window_pivot_reversal_trade_plan.md
                             Two-window pivot reversal rules and operating notes.

live/
  engine.py          Live trading orchestration and state machine.
  instruments.py     Signal/execution instrument universe construction.
  setup.py           Live 3Candle morning setup and missed-breakout checks.
  risk.py            Live position sizing and risk validation.

scripts/
  authenticate.py        Local Upstox OAuth helper.
  run_live.py            Live bot entrypoint.
  run_nifty_options_live.py
                         Futures-driven 1+3 options live entrypoint.
  run_nifty_two_window_pivot_reversal_options_live.py
                         Separate two-window pivot options entrypoint.
  run_backtest.py        Backtest entrypoint.
  fetch_data.py          Historical data download entrypoint.
  monitor_trades.py      Local log/status monitoring helper.
  check_trade_status.py  Operational status helper.
  test_trade.py          Real-order smoke test script.

strategies/
  base.py            Strategy interface and signal dataclass.
  three_candle.py    3Candle vectorized backtest strategy.
  camarilla.py       Camarilla strategy implementation.
  indicators.py      Shared pivot and indicator helpers.
  two_window_pivot_reversal.py
                     Shared two-window pivot reversal strategy.

options_trading/
  strategies/        Futures-signal adapters for options spread execution.
  engines/           Separate live options runner engines.
  execution/         Options spread planning and order execution.

tests/
  test_*.py          Unit tests for strategies, indicators, backtesting, live setup.
```

## 3. Runtime Flows

### 3.1 Authentication Flow

Current flow:

1. User runs `python scripts/authenticate.py`.
2. Script builds an Upstox OAuth login URL.
3. User opens the URL in a browser.
4. Upstox redirects to `http://127.0.0.1:5000/callback`.
5. Local Flask app receives the authorization code.
6. `core.broker.UpstoxBroker.exchange_code_for_token()` exchanges the code.
7. Access token is written to `.env` as `UPSTOX_ACCESS_TOKEN`.

Current limitations:

- The redirect endpoint is local and depends on the user machine.
- Token refresh and token expiry handling are not yet robust.
- Authentication state is stored in `.env`, which is acceptable locally but not
  suitable as a long-term cloud secret store.
- No audit log exists for token creation, expiry, or failure reasons.

Future direction:

- Move OAuth callback to a cloud-hosted service with HTTPS.
- Use a stable public URL and a configured redirect URI in the Upstox app.
- Use a secrets manager or encrypted database instead of `.env`.
- Add explicit token expiry detection and refresh or re-authentication workflow.
- If Upstox or the deployment platform requires IP whitelisting, deploy outbound
  traffic behind a static egress IP such as a NAT gateway or reserved cloud IP.

### 3.2 Live Trading Flow

Current flow:

1. User runs `python scripts/run_live.py --confirm-live`.
2. `Settings` loads configuration and environment variables.
3. `live.instruments.build_observer_list()` builds the universe:
   - Nifty 50 index as signal source, NIFTYBEES as execution instrument.
   - Nifty 50 stocks from `data/source/ind_nifty50list.csv`.
4. `LiveEngine` waits until 10:15 IST.
5. For each observer, `DataFetcher.fetch_combined()` fetches recent historical
   candles plus current intraday candles.
6. `live.setup.evaluate_morning_setup()` checks the 3Candle morning condition.
7. Qualified instruments are added to the watchlist.
8. Engine monitors live LTP through `UpstoxBroker.get_ltp()`.
9. Breakout and trigger logic creates a trade candidate.
10. `RiskManager` validates reward:risk and calculates quantity.
11. `UpstoxBroker.place_market_order()` executes real orders.
12. Engine monitors active position until target, stop, or EOD square-off.
13. `TelegramNotifier` sends state, entry, exit, and warning messages.

### 3.3 Backtesting Flow

Current flow:

1. User runs `python scripts/run_backtest.py --strategy ... --data ...`.
2. CSV is loaded into a Pandas DataFrame with timestamp index.
3. Strategy prepares indicators and generates signal columns.
4. `BacktestEngine` simulates bar-by-bar execution.
5. Metrics and reports are generated through `backtesting.metrics`.

Important difference from live trading:

- Backtesting uses vectorized strategy signal generation from `strategies/`.
- Live trading currently uses live-specific setup evaluation from `live/setup.py`
  and live-specific breakout/trigger code in `live/engine.py`.
- These are close in behavior but not fully unified yet.

### 3.4 Separate Two-Window Pivot Reversal Options Flow

Current flow:

1. User runs
   `python scripts/run_nifty_two_window_pivot_reversal_options_live.py --confirm-live`.
2. The runner fetches Nifty futures candles and evaluates the shared two-window
   setup.
3. It accepts a one-minute trigger close only through `14:29`.
4. On the next live futures price, it rejects a gap beyond target or stop and
   otherwise places the mapped options spread.
5. It exits immediately when futures LTP reaches target.
6. It exits on stop only when a newly completed aligned five-minute futures
   candle closes beyond stop.
7. It closes any open spread at `14:45`.

This runner is intentionally separate from the active 1+3 options runner so
the two strategies can be validated independently before orchestration is
combined.

## 4. Current Strategy Logic

### 4.1 3Candle Strategy

Purpose:

- Identify a morning consolidation after the initial balance.
- Trade breakouts from that range.
- Use floor pivots, CPR levels, and previous-day high/low for target selection.
- Exclude CPR levels (`BC`, `TC`) from stop-loss selection.

Current rules:

- Initial balance window: 09:15 to 09:29 IST.
- Consolidation window: 09:30 to 10:14 IST.
- Minimum inside candles: `Settings.MIN_INSIDE_CANDLES`, currently `3`.
- Trading starts: 10:15 IST.
- EOD square-off: 14:30 IST.
- Long setup:
  - Price breaks above initial balance high.
  - Target is next pivot above trigger.
  - Stop is next pivot below trigger.
- Short setup:
  - Price breaks below initial balance low.
  - Target is next pivot below trigger.
  - Stop is next pivot above trigger.

Live implementation:

- Morning qualification lives in `live/setup.py`.
- Live breakout, trigger, entry, and exit management live in `live/engine.py`.

Backtest implementation:

- Vectorized signal generation lives in `strategies/three_candle.py`.
- Bar-by-bar trade simulation lives in `backtesting/engine.py`.

Risk:

- The live and backtest paths can drift because they do not share one strategy
  execution contract yet.

### 4.2 Camarilla Strategy

Purpose:

- Use Camarilla pivot levels for breakout or mean-reversion style setups.

Current status:

- Strategy implementation exists in `strategies/camarilla.py`.
- It is available in the backtest runner.
- It is not yet integrated into live trading as a selectable live strategy.

Future direction:

- Define a common strategy interface that both live and backtest can use.
- Add a live adapter for Camarilla only after the interface is stable.

### 4.3 Two-Window Pivot Reversal Strategy

Purpose:

- Detect a one-sided reversal setup in the first two 15-minute windows.
- Reuse shared pivots, CPR levels, and previous-day high/low.
- Keep the backtest and separate live futures adapter aligned.

Current rules:

- First range: `09:15-09:29`.
- Second range: `09:30-09:44`.
- Setup qualifies only if the second range strictly breaks exactly one side of
  the first range.
- A low-side break prepares a long trade with second-range high as trigger.
- A high-side break prepares a short trade with second-range low as trigger.
- Entry requires a one-minute close beyond trigger and uses the next one-minute
  open in backtests.
- Target and stop use the nearest strict shared level or relevant range
  boundary.
- Final qualifying signal: `14:29`.
- Live force-close: `14:45`.

## 5. Modularity Assessment

### Already Modular

- `config/settings.py`
  - Centralized configuration and environment loading.

- `core/broker.py`
  - Upstox API interaction is mostly isolated.

- `core/data_fetcher.py`
  - Historical and intraday data access is centralized.

- `core/notifier.py`
  - Telegram notifications are isolated from strategy and engine logic.

- `backtesting/engine.py`
  - Backtest execution is strategy-agnostic.

- `strategies/base.py`
  - Provides the start of a strategy abstraction.

- `strategies/two_window_pivot_reversal.py`
  - Shares the two-window setup between backtest and options live execution.

- `options_trading/`
  - Keeps futures-driven options execution isolated from the direct live bot.

- `live/instruments.py`
  - Instrument universe construction is now separated from the live script.

- `live/setup.py`
  - Live morning setup evaluation is now separated from the live engine.

### Needs More Modularization

- `live/engine.py`
  - Still owns too much: monitoring loop, breakout state, trigger checks,
    active trade management, exit retry handling, and notification sequencing.

- Authentication
  - Local Flask callback, token exchange, and `.env` persistence are coupled in
    `scripts/authenticate.py`.

- Strategy behavior across live and backtest
  - Backtest strategy code and live setup/breakout code are similar but not
    driven by one shared contract.

- Order execution
  - Broker placement exists, but there is no execution abstraction for
    idempotency, position reconciliation, or persistent order lifecycle tracking.

- Runtime state
  - Live bot state is in memory only. Restarting the process loses active trade
    context and daily counters.

- Observability
  - Logs and Telegram messages exist, but structured logs, metrics, health
    checks, and persistent audit trails are missing.

- Configuration
  - Settings are class attributes loaded at import time. This is simple but
    makes validation, environment overrides, testing, and cloud deployment less
    explicit.

## 6. Cloud and Static IP Considerations

The current local model is suitable for development and manual operation. For
production, the system should move toward a controlled cloud runtime.

### Why a Static IP May Matter

A static public IP can be useful or required for:

- Broker API IP whitelisting, if enabled or required.
- Stable webhook/callback infrastructure.
- Auditability of order traffic.
- Firewall rules and operational security.

Static IP should not be confused with OAuth redirect URL. OAuth needs a stable
HTTPS callback URL. API access may additionally need a stable outbound egress IP.

### Recommended Cloud Shape

Development stage:

- Continue local backtesting and supervised live runs only.
- Keep `.env` local.
- Avoid running unattended live orders.

Early cloud stage:

- Run the bot in a small VM or container service.
- Use a cloud reserved static IP or NAT gateway for outbound API calls.
- Use HTTPS for the OAuth callback.
- Store secrets in a secrets manager.
- Run backtests and supervised local live checks before unattended operation.
- Add process supervision and automatic restart.

Production stage:

- Separate services:
  - Auth service.
  - Scheduler/live engine worker.
  - Market data service or adapter.
  - Order execution service.
  - State store.
  - Monitoring and alerting.
- Persist trade state and order events in a database.
- Add broker reconciliation on startup and during runtime.
- Add kill switch and manual intervention workflow.
- Add deployment pipeline and rollback process.

## 7. Operational Risks

### Trading Risk

- Market orders can slip.
- LTP-based trigger logic may not match candle-close backtest assumptions.
- Same-candle target/SL behavior is not identical between live and backtest.
- One-trade-per-day state is in memory only.

### System Risk

- Process crash during active trade can lose state.
- Network failure can delay exits.
- Token expiry can stop quote/order calls.
- Telegram failure should not block trading, but missing alerts can hide issues.
- Local machine sleep, network changes, and IP changes can interrupt live runs.

### Data Risk

- Historical and intraday data may have missing candles or duplicates.
- Corporate actions, symbol changes, and instrument metadata changes need
  explicit handling.
- Generated CSVs and reports can become large and should stay out of Git.

## 8. Testing Baseline

Current tests cover:

- Indicator pivot calculations.
- CPR calculations.
- 3Candle signal generation.
- Backtest engine behavior.
- Backtest metrics.
- Extracted live setup helpers.
- Two-window qualification, stale-signal behavior, and next-open invalidation.
- Long and short two-window live target/stop handling.
- Five-minute stop candle API throttling and partial-exit retry protection.

Current suite result: `52 passed`.

Needed test improvements:

- Unit tests for `RiskManager`.
- Unit tests for live breakout and trigger decisions.
- Mocked tests for `UpstoxBroker`.
- Mocked tests for `DataFetcher` retry and normalization.
- End-to-end simulation with fake broker and fake market data.
- Restart/recovery tests once persistent state is added.

## 9. Source Control Baseline

The project was detached from its old Git repository by removing `.git`.

Before connecting to a fresh GitHub repository:

- Keep `.env` out of Git.
- Keep generated `data/output` files out of Git.
- Keep only small required source data under `data/source`.
- Keep README setup and operating commands current.
- Run tests.
- Initialize Git with a clean first commit.

## 10. Decision Log

Use this section to record major design decisions.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-05-25 | Keep local development sandboxed by default. | Protect credentials, local files, and live-order scripts. |
| 2026-05-25 | Split live instrument loading into `live/instruments.py`. | Keep `run_live.py` as a thin entrypoint. |
| 2026-05-25 | Split live morning setup checks into `live/setup.py`. | Reduce `live/engine.py` complexity and make setup logic testable. |
| 2026-05-25 | Keep generated output data out of Git. | Avoid large repo size and leaking operational artifacts. |
| 2026-05-30 | Keep the two-window pivot reversal live runner separate from the active 1+3 options runner. | Validate the new strategy independently before combining live orchestration. |
| 2026-05-30 | Use immediate futures LTP target exits and completed five-minute futures candle-close stop exits for two-window live trades. | Match the revised strategy exit rules while preserving fast target capture. |

## 11. Open Questions

- Should a separate dry-run simulator be added for strategy rehearsals?
- Should strategies be configured through CLI, config file, or database?
- Should the first cloud target be a VM, container service, or scheduled worker?
- What broker constraints apply around static IP, token lifetime, and rate limits?
- Should the system support multiple strategies running at the same time?
- Should order execution be market-only or support stop/limit/protective orders?
- What level of manual control is required during live operation?
