from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import pandas as pd

from .pivots import swing_highs, swing_lows, Pivot
from .resample import resample_ohlcv


@dataclass
class Targets:
    t1: Optional[float]
    t2: Optional[float]


def nearest_targets_from_htfs(df_5m: pd.DataFrame, side: str) -> Targets:
    # Use 1H, 4H, 1D to find nearest favorable swings; choose nearest as T1, next as T2
    if df_5m.empty:
        return Targets(None, None)
    h1 = resample_ohlcv(df_5m, "1h")
    h4 = resample_ohlcv(df_5m, "4h")
    d1 = resample_ohlcv(df_5m, "1D")

    prices: list[float] = []
    if side == "LONG":
        for d in (h1, h4, d1):
            for p in swing_highs(d):
                prices.append(p.price)
        prices = sorted(set(prices))
    else:
        for d in (h1, h4, d1):
            for p in swing_lows(d):
                prices.append(p.price)
        prices = sorted(set(prices), reverse=True)

    if len(prices) == 0:
        return Targets(None, None)
    if side == "LONG":
        # choose prices above last close
        last_close = float(df_5m["close"].iloc[-1])
        above = [p for p in prices if p > last_close]
        if not above:
            return Targets(None, None)
        t1 = above[0]
        t2 = above[1] if len(above) > 1 else None
        return Targets(t1, t2)
    else:
        last_close = float(df_5m["close"].iloc[-1])
        below = [p for p in prices if p < last_close]
        if not below:
            return Targets(None, None)
        t1 = below[0]
        t2 = below[1] if len(below) > 1 else None
        return Targets(t1, t2)


def swing_trailing_stop(df_5m: pd.DataFrame, side: str, left: int = 2, right: int = 2) -> Optional[float]:
    # Latest confirmed swing low (for longs) or swing high (for shorts)
    if df_5m.empty:
        return None
    if side == "LONG":
        lows = swing_lows(df_5m, left, right)
        return lows[-1].price if lows else None
    else:
        highs = swing_highs(df_5m, left, right)
        return highs[-1].price if highs else None


@dataclass
class ExitDecision:
    exit_now: bool
    reason: Optional[str]
    exit_price: Optional[float]


def evaluate_exit(side: str, bar: pd.Series, sl_price: float, t1: Optional[float], t2: Optional[float]) -> ExitDecision:
    high = float(bar.get("high", bar["close"]))
    low = float(bar.get("low", bar["close"]))
    close = float(bar["close"])

    # Hard stop
    if side == "LONG" and low <= sl_price:
        return ExitDecision(True, "SL", sl_price)
    if side == "SHORT" and high >= sl_price:
        return ExitDecision(True, "SL", sl_price)

    # Targets
    if side == "LONG":
        if t2 is not None and high >= t2:
            return ExitDecision(True, "T2", t2)
        if t1 is not None and high >= t1:
            return ExitDecision(True, "T1", t1)
    else:
        if t2 is not None and low <= t2:
            return ExitDecision(True, "T2", t2)
        if t1 is not None and low <= t1:
            return ExitDecision(True, "T1", t1)

    return ExitDecision(False, None, None)
