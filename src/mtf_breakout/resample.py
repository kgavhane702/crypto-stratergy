from __future__ import annotations

import pandas as pd


_TIMEFRAME_RULE = {
    "5m": "5T",
    "15m": "15T",
    "30m": "30T",
    "1h": "1h",
    "4h": "4h",
    "1D": "1D",
    "1W": "1W",
    "1M": "MS",
}


def resample_ohlcv(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    rule = _TIMEFRAME_RULE.get(timeframe, timeframe)
    o = df["open"].resample(rule, label="right", closed="right").first()
    h = df["high"].resample(rule, label="right", closed="right").max()
    l = df["low"].resample(rule, label="right", closed="right").min()
    c = df["close"].resample(rule, label="right", closed="right").last()
    v = df.get("volume", pd.Series(index=df.index)).resample(rule, label="right", closed="right").sum()
    out = pd.concat([o, h, l, c, v], axis=1)
    out.columns = ["open", "high", "low", "close", "volume"]
    out = out.dropna(subset=["open", "high", "low", "close"])  # keep only complete bars
    return out
