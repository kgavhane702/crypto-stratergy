from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import pandas as pd

from .indicators import ema
from .resample import resample_ohlcv


@dataclass
class TrendLabel:
    timeframe: str
    label: str  # Bullish, Bearish, Neutral


def _label_series(df: pd.DataFrame) -> str:
    if df.empty or len(df) < 210:
        return "Neutral"
    e50 = ema(df["close"], 50)
    e200 = ema(df["close"], 200)

    close = df["close"].iloc[-1]
    e50_now = e50.iloc[-1]
    e200_now = e200.iloc[-1]
    e50_prev = e50.iloc[-2]
    e200_prev = e200.iloc[-2]

    e50_rising = e50_now > e50_prev
    e200_rising = e200_now > e200_prev
    e50_falling = e50_now < e50_prev
    e200_falling = e200_now < e200_prev

    if close > e50_now and e50_now > e200_now and e50_rising and e200_rising:
        return "Bullish"
    if close < e50_now and e50_now < e200_now and e50_falling and e200_falling:
        return "Bearish"
    return "Neutral"


def label_trend_ladder(df_5m: pd.DataFrame, ladder: List[str]) -> Dict[str, TrendLabel]:
    out: Dict[str, TrendLabel] = {}
    for tf in ladder:
        dft = resample_ohlcv(df_5m, tf) if tf != "5m" else df_5m
        lbl = _label_series(dft)
        out[tf] = TrendLabel(timeframe=tf, label=lbl)
    return out


def permission_all_bullish(labels: Dict[str, TrendLabel]) -> bool:
    return all(v.label == "Bullish" for v in labels.values())


def permission_all_bearish(labels: Dict[str, TrendLabel]) -> bool:
    return all(v.label == "Bearish" for v in labels.values())
