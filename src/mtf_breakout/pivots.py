from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import pandas as pd


@dataclass
class Pivot:
    index: pd.Timestamp
    price: float


def swing_highs(df: pd.DataFrame, left: int = 2, right: int = 2) -> list[Pivot]:
    out: list[Pivot] = []
    for i in range(left, len(df) - right):
        window = df.iloc[i - left : i + right + 1]
        if df["high"].iloc[i] == window["high"].max():
            out.append(Pivot(df.index[i], float(df["high"].iloc[i])))
    return out


def swing_lows(df: pd.DataFrame, left: int = 2, right: int = 2) -> list[Pivot]:
    out: list[Pivot] = []
    for i in range(left, len(df) - right):
        window = df.iloc[i - left : i + right + 1]
        if df["low"].iloc[i] == window["low"].min():
            out.append(Pivot(df.index[i], float(df["low"].iloc[i])))
    return out


def next_targets_from_htf(htf_df: pd.DataFrame, side: str) -> Tuple[Optional[Pivot], Optional[Pivot]]:
    # Find the nearest next two swing levels in trade direction
    if htf_df.empty:
        return None, None
    if side == "LONG":
        highs = swing_highs(htf_df)
        highs_sorted = sorted(highs, key=lambda p: p.index)
        # take the last two (nearest ahead as resistance)
        return (highs_sorted[-1] if len(highs_sorted) >= 1 else None, highs_sorted[-2] if len(highs_sorted) >= 2 else None)
    else:
        lows = swing_lows(htf_df)
        lows_sorted = sorted(lows, key=lambda p: p.index)
        return (lows_sorted[-1] if len(lows_sorted) >= 1 else None, lows_sorted[-2] if len(lows_sorted) >= 2 else None)
