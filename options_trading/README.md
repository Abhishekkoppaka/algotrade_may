# Options Trading Package

This package is the main home for Nifty options trading logic.

The older direct stock/Nifty+50 live bot remains under `live/` and is launched
with `scripts/run_live.py`. Do not add new options strategies there.

## Structure

```text
options_trading/
  config.py                 Option-strategy-specific settings.
  models.py                 Shared option leg and spread models.
  engines/                  Live orchestration for options trading.
  execution/                Option contract selection and spread planning.
  strategies/               Signal strategies that can trigger option spreads.
  .env.example              Option-specific environment variables.
```

## Strategies

`NiftyFuturesBreakoutStrategy` tracks the configured current/front-month Nifty
futures instrument. When the futures produces a fresh 3Candle breakout:

- LONG futures signal: sell OTM CE and buy farther OTM CE.
- SHORT futures signal: sell OTM PE and buy farther OTM PE.

The spread planner owns strike selection and contract lookup. The live engine
owns broker calls, order confirmation, and EOD square-off.

`NiftyFuturesTwoWindowPivotReversalStrategy` is a separate Nifty futures signal
strategy. It compares the `09:15-09:29` and `09:30-09:44` ranges and qualifies
only strict one-sided second-range breaks. Its options runner remains separate
from the 1+3 runner so both strategies can be operated independently.

## Adding Strategies

Add new signal logic under `options_trading/strategies/`. A strategy should
return only a directional signal such as `LONG` or `SHORT`; option strike
selection should stay in `options_trading/execution/`.

## Two-Window Pivot Reversal Runner

The two-window pivot reversal strategy is available as a separate live runner:

```text
python scripts/run_nifty_two_window_pivot_reversal_options_live.py --confirm-live
```

It places real option spread orders, polls the Nifty futures LTP for immediate
target exits, evaluates stop loss only on completed five-minute futures candle
closes, and force-closes any open spread at 14:45 IST. Target polling defaults
to one second and can be configured with `PIVOT_REVERSAL_MONITOR_INTERVAL`.
