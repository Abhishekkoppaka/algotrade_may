# Algorithmic Trading Project

Python trading and backtesting project for Indian markets using Upstox.

## Features

- Historical and intraday candle retrieval.
- Reusable floor pivot, CPR, and Camarilla indicators.
- Backtesting for `three_candle`, `camarilla`, and
  `two_window_pivot_reversal`.
- Direct stock/Nifty 3Candle live runner.
- Nifty futures driven options spread runners.
- Telegram notifications and explicit live-order confirmation guards.

## Setup

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python scripts/authenticate.py
```

Add the options-specific values documented in
`options_trading/.env.example` to the root `.env`.

## Backtesting

```powershell
python scripts/run_backtest.py --strategy three_candle --data data/output/Data/NIFTYBEES_1min_2yr.csv
python scripts/run_backtest.py --strategy camarilla --data data/output/Data/NIFTYBEES_1min_2yr.csv
python scripts/run_backtest.py --strategy two_window_pivot_reversal --data data/output/nifty50_1yr_1min.csv
```

## Live Trading

These commands place real orders and require explicit confirmation.

Direct stock/Nifty 3Candle runner:

```powershell
python scripts/run_live.py --confirm-live
```

Nifty futures 1+3 options spread runner:

```powershell
python scripts/run_nifty_options_live.py --confirm-live
```

Separate Nifty futures two-window pivot reversal options spread runner:

```powershell
python scripts/run_nifty_two_window_pivot_reversal_options_live.py --confirm-live
```

## Verification

```powershell
python -m pytest -q
```

## Documentation

- `docs/trade_plan.md`: 3Candle trade plan.
- `docs/two_window_pivot_reversal_trade_plan.md`: two-window pivot reversal plan.
- `docs/PROJECT_BASELINE.md`: architecture baseline.
- `docs/PROJECT_IMPROVEMENT_PLAN.md`: improvement roadmap.
- `docs/CODEX_PROJECT_CONTEXT.md`: maintainer reference.

Generated market data and reports stay under `data/output/` and are ignored by
Git. Keep `.env` private.
