# Two-Window Pivot Reversal Trade Plan

## Purpose

This Nifty futures strategy looks for a reversal after the second 15-minute
range strictly breaks exactly one side of the opening 15-minute range.

It is available through a separate options spread runner so it can be operated
and reviewed independently from the existing 1+3 runner.

## Setup

Build two ranges from one-minute Nifty futures candles:

- First range: `09:15-09:29`.
- Second range: `09:30-09:44`.

Qualification:

- LONG setup: second-range low is strictly below the first-range low.
- SHORT setup: second-range high is strictly above the first-range high.
- Reject the day if both sides break.
- Reject the day if neither side breaks.

Levels reuse shared previous-day floor pivots and CPR levels:

- `PP`, `BC`, `TC`
- `R1-R3`, `S1-S3`
- `PDH`, `PDL`

## Entry

LONG:

- Trigger: second-range high.
- Wait for a one-minute candle close strictly above the trigger.
- Enter during the following minute.

SHORT:

- Trigger: second-range low.
- Wait for a one-minute candle close strictly below the trigger.
- Enter during the following minute.

Reject an entry when the next-minute price is already at or beyond the planned
target or stop.

The last qualifying signal candle is `14:29`.

## Target And Stop

LONG:

- Target: nearest strict level above the trigger, including first-range high.
- Stop: nearest strict level below the trigger, including second-range low.

SHORT:

- Target: nearest strict level below the trigger, including first-range low.
- Stop: nearest strict level above the trigger, including second-range high.

## Live Exit Behavior

- Target: close immediately when futures LTP reaches or crosses the target.
- Stop: close only when a completed session-aligned five-minute futures candle
  closes beyond the stop.
- Forced square-off: close any remaining spread at `14:45` IST.

The runner polls futures LTP every second by default for target exits. Configure
the interval with `PIVOT_REVERSAL_MONITOR_INTERVAL`.

## Options Mapping

- LONG futures signal: sell OTM CE and buy farther OTM CE.
- SHORT futures signal: sell OTM PE and buy farther OTM PE.

The spread planner selects contracts. The strategy module only produces futures
direction, trigger, target, and stop decisions.

## Runner

```powershell
python scripts/run_nifty_two_window_pivot_reversal_options_live.py --confirm-live
```

This command places real option orders.
