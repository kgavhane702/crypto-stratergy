import pandas as pd

from mtf_breakout.trend import label_trend_ladder


def make_series(rising: bool = True) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=300, freq="5min", tz="UTC")
    base = 100.0
    step = 0.1 if rising else -0.1
    vals = [base + i * step for i in range(len(idx))]
    df = pd.DataFrame({"open": vals, "high": [v + 0.2 for v in vals], "low": [v - 0.2 for v in vals], "close": vals}, index=idx)
    return df


def test_trend_bullish():
    df = make_series(True)
    labels = label_trend_ladder(df, ["1M", "1W", "1D", "1h"])  # type: ignore
    assert all(v.label in ("Bullish", "Neutral") for v in labels.values())


def test_trend_bearish():
    df = make_series(False)
    labels = label_trend_ladder(df, ["1M", "1W", "1D", "1h"])  # type: ignore
    assert all(v.label in ("Bearish", "Neutral") for v in labels.values())
