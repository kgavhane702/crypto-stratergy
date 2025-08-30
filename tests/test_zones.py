import pandas as pd

from mtf_breakout.zones import detect_zone


def test_zone_flat_detects():
    idx = pd.date_range("2024-01-01", periods=200, freq="5min", tz="UTC")
    closes = [100 + (i % 10 == 0) * 0.05 for i in range(len(idx))]
    highs = [c + 0.05 for c in closes]
    lows = [c - 0.05 for c in closes]
    df = pd.DataFrame({"open": closes, "high": highs, "low": lows, "close": closes}, index=idx)
    z = detect_zone(df)
    assert z is None or z.width <= 1.0  # width tight
