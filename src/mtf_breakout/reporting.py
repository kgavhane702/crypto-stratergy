from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from .backtest.engine import Trade


@dataclass
class Summary:
    win_rate: float
    profit_factor: float
    cagr: float
    max_drawdown: float
    avg_r: float
    expectancy: float
    sharpe: float
    trade_count: int
    avg_holding_minutes: float


def compute_summary(trades: List[Trade]) -> Summary:
    if not trades:
        return Summary(0, 0, 0, 0, 0, 0, 0, 0, 0)
    rows = []
    for t in trades:
        if t.exit_price is None:
            continue
        direction = 1 if t.side == "LONG" else -1
        pnl = direction * (t.exit_price - t.entry_price)
        risk = abs(t.entry_price - t.sl_price)
        r = pnl / risk if risk > 0 else 0
        hold_min = (pd.Timestamp(t.exit_time) - pd.Timestamp(t.entry_time)).total_seconds() / 60.0
        rows.append((r, hold_min))

    if not rows:
        return Summary(0, 0, 0, 0, 0, 0, 0, 0, 0)

    r_vals = np.array([r for r, _ in rows])
    wins = r_vals[r_vals > 0]
    losses = -r_vals[r_vals < 0]
    win_rate = float((r_vals > 0).mean()) if len(r_vals) > 0 else 0.0
    profit_factor = float(wins.mean() / losses.mean()) if len(wins) > 0 and len(losses) > 0 else 0.0
    avg_r = float(r_vals.mean()) if len(r_vals) > 0 else 0.0
    expectancy = float(avg_r)

    # Equity curve (in R units)
    eq = r_vals.cumsum()
    dd = (eq - np.maximum.accumulate(eq))
    max_dd = float(dd.min()) if len(dd) else 0.0

    # Approx Sharpe on daily basis (assumes ~288 5m bars per day)
    daily_r = r_vals.reshape(-1, 1)  # naive
    sharpe = float(r_vals.mean() / (r_vals.std() + 1e-9) * np.sqrt(252)) if len(r_vals) > 1 else 0.0

    avg_hold = float(np.array([h for _, h in rows]).mean())

    return Summary(win_rate, profit_factor, 0.0, max_dd, avg_r, expectancy, sharpe, len(rows), avg_hold)


def plot_equity(trades: List[Trade], path: str) -> None:
    if not trades:
        return
    r_vals = []
    times = []
    for t in trades:
        if t.exit_price is None:
            continue
        direction = 1 if t.side == "LONG" else -1
        pnl = direction * (t.exit_price - t.entry_price)
        risk = abs(t.entry_price - t.sl_price)
        r = pnl / risk if risk > 0 else 0
        r_vals.append(r)
        times.append(pd.Timestamp(t.exit_time))

    if not r_vals:
        return

    eq = np.cumsum(r_vals)
    plt.figure(figsize=(10, 4))
    plt.plot(times, eq, label="Equity (R)")
    plt.title("Equity Curve")
    plt.grid(True)
    plt.legend()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    plt.tight_layout()
    plt.savefig(path)
    plt.close()
