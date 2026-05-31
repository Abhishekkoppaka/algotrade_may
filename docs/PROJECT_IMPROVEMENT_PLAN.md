# Project Improvement Plan

This document is the action plan for improving the trading bot from the current
local development setup into a more robust, modular, cloud-ready system.

## 1. Guiding Principles

- Protect capital first. Any live-order path must fail safely and alert clearly.
- Keep live behavior and backtest behavior aligned.
- Make scripts thin. Business logic should live in importable modules.
- Keep broker, strategy, execution, state, and notification concerns separated.
- Prefer backtest, replay, and mocked-broker validation before any broader live deployment.
- Persist enough state to recover safely after crashes or restarts.
- Keep secrets, generated outputs, and credentials out of Git.

## 2. Current Baseline

Completed recently:

- Existing Git metadata removed so the project can become a fresh repository.
- `run_live.py` simplified to a CLI entrypoint.
- Instrument universe moved to `live/instruments.py`.
- Live morning setup checks moved to `live/setup.py`.
- `MIN_RISK_REWARD` centralized in settings.
- Live setup tests added.
- Added modular two-window pivot reversal backtest and separate Nifty options
  live runner.
- Added shared CPR levels (`BC`, `TC`) without changing active 1+3 live targets.
- Added immediate futures target exits and completed five-minute-close futures
  stop exits for the separate pivot reversal runner.
- Added top-level setup documentation and expanded ignore rules for generated
  reports, caches, and disposable isolated-test folders.
- Test suite passes: `52 passed`.

Primary active runtime:

```text
scripts/authenticate.py -> core/broker.py -> .env token
scripts/run_live.py -> live/instruments.py -> live/engine.py
live/engine.py -> core/data_fetcher.py, core/broker.py, core/notifier.py, live/risk.py
```

## 3. Recommended Phased Roadmap

### Phase 1: Repository and Documentation Hygiene

Goal:

- Make the project clean and safe to publish to a new private GitHub repo.

Tasks:

- Keep the top-level `README.md` current with setup, auth, confirmed live run,
  backtest, and test commands.
- Review `.gitignore` periodically and ensure generated data, logs, `.env`,
  caches, reports, and disposable experiments stay out of Git.
- Decide whether existing `data/output` files should be archived outside the repo.
- Keep `data/source/ind_nifty50list.csv` because it is required source data.
- Add a first clean Git commit after reviewing files.
- Add this baseline document and improvement plan as required planning references.

Deliverables:

- Clean GitHub-ready project.
- `README.md`.
- Updated docs.

### Phase 2: Configuration Hardening

Goal:

- Make configuration explicit, validated, and environment-safe.

Tasks:

- Convert `Settings` from class attributes to instance-level validated settings.
- Consider `pydantic-settings` or a lightweight dataclass validation approach.
- Add explicit config fields for:
  - environment: local, live, cloud.
  - live confirmation and safety settings.
  - strategy selection.
  - scan intervals.
  - broker retry settings.
  - auth callback host and port.
  - state storage path or database URL.
- Keep live trading blocked unless the operator passes explicit confirmation.
- Add startup validation that blocks trading if required credentials or safety settings are missing.

Deliverables:

- Safer `Settings`.
- Clear `.env.example`.
- Startup validation errors that are actionable.

### Phase 3: Authentication Redesign

Goal:

- Make authentication robust locally and cloud-ready.

Tasks:

- Split authentication into modules:
  - `auth/oauth_server.py`
  - `auth/token_store.py`
  - `auth/upstox_auth.py`
- Keep `scripts/authenticate.py` as a thin CLI wrapper.
- Add token metadata:
  - created time.
  - expiry time, if provided by Upstox.
  - account/user identifier, if available.
- Detect expired or missing tokens before live startup.
- Add safe token update behavior that does not corrupt `.env`.
- For cloud:
  - Replace local callback with HTTPS callback URL.
  - Store secrets in cloud secrets manager.
  - Store token in encrypted database or secrets manager.
  - Document static outbound IP requirements separately from callback URL.

Deliverables:

- Modular authentication package.
- Local auth still works.
- Cloud auth design ready.

### Phase 4: Strategy Interface Unification

Goal:

- Reduce drift between backtest logic and live logic.

Tasks:

- Define a strategy contract for both historical and live decisions.
- Extract common 3Candle setup concepts into reusable domain objects:
  - initial balance.
  - consolidation result.
  - breakout candidate.
  - trigger plan.
  - exit plan.
- Make live `evaluate_morning_setup()` and backtest `ThreeCandleStrategy` share common helper logic where practical.
- Add strategy registry for live and backtest.
- Add CLI option: `python scripts/run_live.py --strategy three_candle --confirm-live`.
- Keep Camarilla backtest-only until the shared live contract is stable.

Deliverables:

- Shared strategy domain layer.
- Reduced duplication.
- Tests proving live and backtest setup decisions match on the same input data.

### Phase 5: Live Engine Decomposition

Goal:

- Make `live/engine.py` smaller, easier to test, and safer.

Suggested modules:

```text
live/
  engine.py              Top-level orchestration only.
  instruments.py         Instrument universe.
  setup.py               Morning setup checks.
  breakout.py            Breakout and trigger decision logic.
  positions.py           Active trade model and PnL calculations.
  execution.py           Entry/exit workflow and order verification.
  state_store.py         Persist and restore bot state.
  risk.py                Risk validation and sizing.
```

Tasks:

- Move breakout/trigger decisions into `live/breakout.py`.
- Move active trade data shape into dataclasses.
- Move entry/exit order workflow into `live/execution.py`.
- Keep notification formatting out of core decision functions.
- Add tests for each decision function using fake market data.

Deliverables:

- Smaller live engine.
- Testable live decisions.
- Clear active trade model.

### Phase 6: Broker and Execution Safety

Goal:

- Make order placement safer and recoverable.

Tasks:

- Add an execution interface around `UpstoxExecutionClient` so order state,
  retries, and reconciliation are isolated from the live engine.
- Add idempotency or duplicate-order protection where possible.
- Add order lifecycle model:
  - requested.
  - submitted.
  - complete.
  - rejected.
  - cancelled.
  - unknown.
- Add reconciliation:
  - fetch open positions.
  - fetch order book.
  - verify expected active trade matches broker state.
- Add explicit behavior for partial fills if Upstox exposes them.
- Add kill switch:
  - local file flag.
  - environment flag.
  - future admin endpoint.

Deliverables:

- Safer order workflow.
- Better restart behavior.
- Manual intervention path.

### Phase 7: Persistent State and Recovery

Goal:

- Allow safe restart during trading day.

Tasks:

- Store live runtime state:
  - trading date.
  - watchlist.
  - skipped/rejected symbols.
  - active trade.
  - order ids.
  - trades today.
  - last heartbeat.
- Start with SQLite for local use.
- Use Postgres or managed database for cloud.
- On startup:
  - load state.
  - reconcile with broker.
  - resume monitoring or force manual intervention if state conflicts.

Deliverables:

- Restart-safe live bot.
- State recovery tests.

### Phase 8: Observability and Operations

Goal:

- Make the bot observable enough to operate safely.

Tasks:

- Add structured JSON logs for cloud.
- Keep human-readable console logs for local use.
- Add log rotation locally.
- Track metrics:
  - quotes requested.
  - quote failures.
  - order submissions.
  - order failures.
  - active state.
  - last successful broker call.
- Add health check endpoint or heartbeat file.
- Add Telegram alerts for:
  - auth failure.
  - token expiry.
  - quote outage.
  - order rejection.
  - repeated exit failure.
  - process startup/shutdown.
- Add daily summary report.

Deliverables:

- Operational visibility.
- Better incident response.

### Phase 9: Cloud Deployment

Goal:

- Run the system in a controlled, cloud-hosted environment.

Recommended first cloud option:

- Small VM with static public IP or static outbound NAT.
- Process managed by systemd, Docker Compose, or a lightweight supervisor.
- Secrets stored outside code.
- Logs shipped to cloud logging.
- Backtest and supervised local live checks first.

Later cloud option:

- Container service with static egress through NAT gateway.
- Managed secrets.
- Managed database.
- CI/CD pipeline.

Tasks:

- Create Dockerfile.
- Create deployment config.
- Add environment-specific settings.
- Add startup command for confirmed live mode.
- Add backup and restore process for state DB.
- Document static IP setup and Upstox redirect URL setup.

Deliverables:

- Reproducible deployment.
- Static IP design.
- Cloud runbook.

### Phase 10: Strategy Expansion

Goal:

- Add or modify strategies without destabilizing the live engine.

Tasks:

- Define strategy metadata:
  - name.
  - allowed instruments.
  - required timeframe.
  - max trades.
  - market session.
- Add strategy-specific config.
- Add walk-forward or out-of-sample testing process.
- Add historical replay and mocked-broker validation before strategy activation.
- Integrate Camarilla live only after the live strategy interface is stable.

Deliverables:

- Strategy plugin-like architecture.
- Safer strategy rollout.

## 4. Immediate Next Actions

Recommended order:

1. Refresh `.env.example` as configuration evolves.
2. Keep live mode blocked unless `--confirm-live` is passed.
3. Refactor `Settings` into validated instance settings.
4. Split auth into a small `auth/` package while preserving current local workflow.
5. Add replay or mocked-broker simulation for each options runner.
6. Add persistent state with SQLite.
7. Add broker reconciliation before live cloud deployment.

## 5. Design Decisions Needed From User

Before implementation, decide:

- Should the first GitHub repo be private?
- Should generated `data/output` be deleted locally, archived, or ignored only?
- Should a separate dry-run simulator be added later?
- Which cloud provider should be targeted first?
- Is static IP required by Upstox for your account, or only desired for robustness?
- Should the first cloud deployment be VM-based or container-based?
- Should one strategy run at a time, or multiple strategies concurrently?
- What is the acceptable manual intervention workflow if an exit order fails?

## 6. Suggested Technical Backlog

High priority:

- Periodic repo cleanup.
- Confirmed live startup.
- Settings validation.
- Auth module split.
- Live engine tests.
- Persistent state.
- Order reconciliation.

Medium priority:

- Structured logging.
- Daily summary reports.
- Dockerfile.
- Health checks.
- Strategy registry for live mode.
- Better data validation.

Lower priority:

- Web dashboard.
- Multi-strategy orchestration.
- Multi-account support.
- Advanced analytics.
- Cloud autoscaling.

## 7. Acceptance Criteria For Production Readiness

The system should not be considered production-ready for unattended live trading
until these are true:

- Live mode cannot start accidentally.
- Token validity is checked before startup.
- Active trade state survives restart.
- Broker positions are reconciled on startup.
- Exit order failure creates repeated alerts and does not clear state falsely.
- Logs and alerts are sufficient to diagnose failures.
- Backtest, replay, and supervised local live checks have passed before cloud use.
- Static IP and OAuth callback setup are documented and tested.
- Secrets are not stored in Git or plain local files in cloud.
- Tests cover strategy setup, live decisions, risk, execution, and recovery.
