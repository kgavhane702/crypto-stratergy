import pandas as pd

from mtf_breakout.indicators import atr
from mtf_breakout.zones import detect_zone


def test_breakout_sl_placeholder():
    # Minimal smoke test: ensure ATR computes and zone detect returns quickly
    idx = pd.date_range("2024-01-01", periods=300, freq="5min", tz="UTC")
    vals = [100 + (i % 50) * 0.02 for i in range(len(idx))]
    highs = [v + 0.05 for v in vals]
    lows = [v - 0.05 for v in vals]
    df = pd.DataFrame({"open": vals, "high": highs, "low": lows, "close": vals}, index=idx)
    a = atr(df).iloc[-1]
    assert a == a  # not NaN
    z = detect_zone(df)
    assert z is None or z.touches_top >= 0
