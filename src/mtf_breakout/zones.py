from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from .indicators import atr
from .config import get_settings


@dataclass
class Zone:
    start_idx: int
    end_idx: int
    low_close: float
    high_close: float
    width: float
    touches_top: int
    touches_bottom: int
    atr: float
    dwell_bars: int


def detect_zone(df: pd.DataFrame) -> Optional[Zone]:
    if df.empty or len(df) < 50:
        return None

    s = get_settings()
    window = s.dwell_bars

    look = df.tail(window)
    a = atr(df).iloc[-1]
    if a is None or a != a:
        return None

    # Band from closes
    low_c = float(look["close"].min())
    high_c = float(look["close"].max())
    width = high_c - low_c

    # Tightness
    if width > s.atr_tight_mult * float(a):
        return None

    # Count touches with ATR buffer and separation
    buf = s.touch_buffer_frac * float(a)
    top_level = high_c
    bot_level = low_c

    touches_top = 0
    touches_bottom = 0
    last_touch_top_i = -10_000
    last_touch_bottom_i = -10_000

    for i in range(len(look)):
        row = look.iloc[i]
        hi = float(row.get("high", row["close"]))
        lo = float(row.get("low", row["close"]))
        # top touch
        if hi >= top_level - buf:
            if i - last_touch_top_i >= s.touch_separation_bars:
                touches_top += 1
                last_touch_top_i = i
        # bottom touch
        if lo <= bot_level + buf:
            if i - last_touch_bottom_i >= s.touch_separation_bars:
                touches_bottom += 1
                last_touch_bottom_i = i

    return Zone(
        start_idx=len(df) - window,
        end_idx=len(df) - 1,
        low_close=bot_level,
        high_close=top_level,
        width=width,
        touches_top=touches_top,
        touches_bottom=touches_bottom,
        atr=float(a),
        dwell_bars=window,
    )
