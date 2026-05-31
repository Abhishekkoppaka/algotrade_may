"""
Backtest Metrics & Reporting

Calculates standard trading performance metrics from a trades DataFrame.
All metric calculations are centralized here — no other module should
re-implement win rate, drawdown, etc.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from typing import Optional


def calculate_metrics(trades_df: pd.DataFrame) -> dict:
    """
    Calculate comprehensive trading performance metrics.

    Args:
        trades_df: DataFrame with columns: pnl, entry_time, exit_time, type, reason

    Returns:
        Dictionary of metric name → value. Returns empty metrics if no trades.
    """
    if trades_df.empty:
        return {
            "total_trades": 0,
            "total_return": 0.0,
            "win_rate": 0.0,
            "max_drawdown": 0.0,
            "avg_profit": 0.0,
            "avg_loss": 0.0,
            "largest_winner": 0.0,
            "largest_loser": 0.0,
            "profit_factor": 0.0,
            "long_trades": 0,
            "short_trades": 0,
        }

    total_trades = len(trades_df)
    winners = trades_df[trades_df["pnl"] > 0]
    losers = trades_df[trades_df["pnl"] <= 0]

    # Cumulative PnL for drawdown calculation
    cum_pnl = trades_df["pnl"].cumsum()
    running_max = cum_pnl.cummax()
    drawdown = running_max - cum_pnl
    max_drawdown = drawdown.max()

    # Profit factor: gross profit / gross loss
    gross_profit = winners["pnl"].sum() if len(winners) > 0 else 0
    gross_loss = abs(losers["pnl"].sum()) if len(losers) > 0 else 1
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    return {
        "total_trades": total_trades,
        "total_return": trades_df["pnl"].sum(),
        "win_rate": (len(winners) / total_trades * 100) if total_trades > 0 else 0.0,
        "max_drawdown": max_drawdown,
        "avg_profit": winners["pnl"].mean() if len(winners) > 0 else 0.0,
        "avg_loss": losers["pnl"].mean() if len(losers) > 0 else 0.0,
        "largest_winner": trades_df["pnl"].max(),
        "largest_loser": trades_df["pnl"].min(),
        "profit_factor": profit_factor,
        "long_trades": len(trades_df[trades_df["type"] == "Long"]),
        "short_trades": len(trades_df[trades_df["type"] == "Short"]),
    }


def print_metrics(metrics: dict, title: str = "BACKTEST RESULTS") -> None:
    """
    Print formatted metrics to console.

    Args:
        metrics: Dictionary from calculate_metrics().
        title: Header text for the output block.
    """
    print(f"\n{'=' * 50}")
    print(f"  {title}")
    print(f"{'=' * 50}")
    print(f"  Total Trades:      {metrics['total_trades']}")
    print(f"  Long / Short:      {metrics['long_trades']} / {metrics['short_trades']}")
    print(f"  Total Return:      {metrics['total_return']:.2f} pts")
    print(f"  Win Rate:          {metrics['win_rate']:.2f}%")
    print(f"  Profit Factor:     {metrics['profit_factor']:.2f}")
    print(f"  Max Drawdown:      {metrics['max_drawdown']:.2f} pts")
    print(f"  Avg Winner:        {metrics['avg_profit']:.2f} pts")
    print(f"  Avg Loser:         {metrics['avg_loss']:.2f} pts")
    print(f"  Largest Winner:    {metrics['largest_winner']:.2f} pts")
    print(f"  Largest Loser:     {metrics['largest_loser']:.2f} pts")
    print(f"{'=' * 50}")


def plot_equity_curve(
    trades_df: pd.DataFrame,
    title: str = "Strategy Equity Curve",
    save_path: Optional[Path] = None,
) -> None:
    """
    Plot and optionally save the cumulative PnL equity curve.

    Args:
        trades_df: DataFrame with 'pnl' and 'exit_time' columns.
        title: Chart title.
        save_path: If provided, saves the chart to this file path.
    """
    if trades_df.empty:
        print("No trades to plot.")
        return

    trades_df = trades_df.copy()
    trades_df["cumulative_pnl"] = trades_df["pnl"].cumsum()
    dates = pd.to_datetime(trades_df["exit_time"])

    plt.figure(figsize=(14, 7))
    plt.style.use("dark_background")

    # Main equity line
    plt.plot(dates, trades_df["cumulative_pnl"], color="#00ff9d", linewidth=2)
    # Fill under curve
    plt.fill_between(
        dates, trades_df["cumulative_pnl"], 0, color="#00ff9d", alpha=0.1
    )

    plt.title(title, fontsize=14, pad=15)
    plt.xlabel("Date", fontsize=11)
    plt.ylabel("Cumulative PnL (Points)", fontsize=11)
    plt.grid(True, alpha=0.2)
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches="tight")
        print(f"Equity curve saved to: {save_path}")
    else:
        plt.show()

    plt.close()


def save_report(
    trades_df: pd.DataFrame,
    metrics: dict,
    output_dir: Path,
    strategy_name: str = "strategy",
) -> None:
    """
    Save complete backtest report (trades CSV + metrics text + equity curve).

    Args:
        trades_df: The trades DataFrame.
        metrics: Calculated metrics dictionary.
        output_dir: Directory to save all output files.
        strategy_name: Used in filenames.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save trades log
    trades_path = output_dir / f"{strategy_name}_trades.csv"
    trades_df.to_csv(trades_path, index=False)

    # Save metrics text
    metrics_path = output_dir / f"{strategy_name}_metrics.txt"
    with open(metrics_path, "w") as f:
        f.write(f"{strategy_name.upper()} BACKTEST RESULTS\n")
        f.write("=" * 40 + "\n")
        for key, value in metrics.items():
            if isinstance(value, float):
                f.write(f"{key}: {value:.2f}\n")
            else:
                f.write(f"{key}: {value}\n")

    # Save equity curve
    plot_path = output_dir / f"{strategy_name}_equity_curve.png"
    plot_equity_curve(trades_df, title=f"{strategy_name} Equity Curve", save_path=plot_path)

    print(f"Full report saved to: {output_dir}")
