from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ..config import get_settings
from ..data.binance_client import BinanceDataClient
from ..zones import detect_zone
from ..trend import label_trend_ladder, permission_all_bullish, permission_all_bearish
from ..indicators import atr
from ..exits import nearest_targets_from_htfs, swing_trailing_stop, evaluate_exit
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Trade:
    symbol: str
    side: str
    entry_time: pd.Timestamp
    entry_price: float
    sl_price: float
    exit_time: Optional[pd.Timestamp]
    exit_price: Optional[float]
    exit_reason: Optional[str]
    mfe: float
    mae: float


class Backtester:
    def __init__(self, symbols: List[str], start: str, end: str, interval: str = "5m") -> None:
        self.settings = get_settings()
        self.client = BinanceDataClient(self.settings)
        self.symbols = symbols
        self.start = pd.Timestamp(start, tz="UTC")
        self.end = pd.Timestamp(end, tz="UTC")
        self.interval = interval
        self.trades: List[Trade] = []

    def _fetch_5m(self, symbol: str) -> pd.DataFrame:
        return self.client.get_klines_range(symbol, self.interval, int(self.start.value // 1_000_000), int(self.end.value // 1_000_000))

    def run(self) -> None:
        for sym in self.symbols:
            logger.info(f"Backtesting {sym} {self.interval} {self.start} -> {self.end}")
            df = self._fetch_5m(sym)
            if df.empty:
                logger.warning(f"{sym}: no data; skipping")
                continue
            open_pos: Optional[Trade] = None
            trailing: Optional[float] = None
            t1: Optional[float] = None
            t2: Optional[float] = None
            high_water = -np.inf
            low_water = np.inf

            for i in range(max(210, len(df))):
                if i >= len(df):
                    break
                window = df.iloc[: i + 1]
                bar = df.iloc[i]

                # Skip incomplete bars at the end by time proximity
                if i == len(df) - 1:
                    now = pd.Timestamp.utcnow().tz_localize("UTC")
                    if (now - window.index[-1]) < pd.Timedelta(minutes=5):
                        break

                if open_pos is None:
                    labels = label_trend_ladder(window, ["1M", "1W", "1D", "1h"])
                    perm = "NONE"
                    if permission_all_bullish(labels):
                        perm = "LONG"
                    elif permission_all_bearish(labels):
                        perm = "SHORT"
                    
                    z = detect_zone(window)
                    if z is None:
                        continue
                    a = atr(window).iloc[-1]
                    if a is None or a != a:
                        continue
                    buf = self.settings.breakout_buffer_frac * float(a)

                    # LONG BREAKOUT: Take entry regardless of trend if dwell criteria met
                    if float(bar["close"]) > z.high_close + buf and z.touches_top >= 3:
                        dwell = z.dwell_bars >= self.settings.dwell_bars
                        if dwell:
                            sl = float(bar.get("low", bar["close"]))
                            trend_aligned = (perm == "LONG")
                            size_type = "TREND-ALIGNED" if trend_aligned else "COUNTER-TREND"
                            open_pos = Trade(sym, "LONG", window.index[-1], float(bar["close"]), sl, None, None, None, 0.0, 0.0)
                            t = nearest_targets_from_htfs(window, "LONG")
                            t1, t2 = t.t1, t.t2
                            trailing = swing_trailing_stop(window, "LONG")
                            high_water = float(bar["high"]) if "high" in bar else float(bar["close"])
                            low_water = open_pos.sl_price
                            logger.info(f"RANGE BREAKOUT: ENTER LONG {sym} @ {open_pos.entry_price:.6f} SL {open_pos.sl_price:.6f} T1 {t1:.6f} T2 {t2:.6f} (dwell={z.dwell_bars} bars, {size_type})")
                            continue
                    
                    # SHORT BREAKDOWN: Take entry regardless of trend if dwell criteria met
                    if float(bar["close"]) < z.low_close - buf and z.touches_bottom >= 3:
                        dwell = z.dwell_bars >= self.settings.dwell_bars
                        if dwell:
                            sl = float(bar.get("high", bar["close"]))
                            trend_aligned = (perm == "SHORT")
                            size_type = "TREND-ALIGNED" if trend_aligned else "COUNTER-TREND"
                            open_pos = Trade(sym, "SHORT", window.index[-1], float(bar["close"]), sl, None, None, None, 0.0, 0.0)
                            t = nearest_targets_from_htfs(window, "SHORT")
                            t1, t2 = t.t1, t.t2
                            trailing = swing_trailing_stop(window, "SHORT")
                            low_water = float(bar["low"]) if "low" in bar else float(bar["close"])
                            high_water = open_pos.sl_price
                            logger.info(f"RANGE BREAKDOWN: ENTER SHORT {sym} @ {open_pos.entry_price:.6f} SL {open_pos.sl_price:.6f} T1 {t1:.6f} T2 {t2:.6f} (dwell={z.dwell_bars} bars, {size_type})")
                            continue
                else:
                    # Update MFE/MAE tracking
                    high_water = max(high_water, float(bar.get("high", bar["close"])))
                    low_water = min(low_water, float(bar.get("low", bar["close"])))

                    # Update trailing to latest confirmed swing
                    trailing_new = swing_trailing_stop(window, open_pos.side)
                    if trailing_new is not None:
                        if open_pos.side == "LONG" and trailing is not None and trailing_new > trailing:
                            trailing = trailing_new
                        if open_pos.side == "SHORT" and trailing is not None and trailing_new < trailing:
                            trailing = trailing_new

                    # Respect hard SL and targets
                    # Choose effective stop = max(current SL, trailing) for LONG; min for SHORT
                    sl_effective = open_pos.sl_price
                    if trailing is not None:
                        if open_pos.side == "LONG":
                            sl_effective = max(sl_effective, trailing)
                        else:
                            sl_effective = min(sl_effective, trailing)

                    decision = evaluate_exit(open_pos.side, bar, sl_effective, t1, t2)
                    if decision.exit_now:
                        open_pos.exit_time = window.index[-1]
                        open_pos.exit_price = decision.exit_price
                        open_pos.exit_reason = decision.reason
                        # MFE/MAE in R multiples
                        risk = abs(open_pos.entry_price - open_pos.sl_price)
                        if risk > 0:
                            if open_pos.side == "LONG":
                                r_mfe = (high_water - open_pos.entry_price) / risk
                                r_mae = (open_pos.entry_price - low_water) / risk
                            else:
                                r_mfe = (open_pos.entry_price - low_water) / risk
                                r_mae = (high_water - open_pos.entry_price) / risk
                            open_pos.mfe = float(r_mfe)
                            open_pos.mae = float(r_mae)
                        self.trades.append(open_pos)
                        logger.info(f"EXIT {open_pos.side} {sym} @ {open_pos.exit_price} reason={open_pos.exit_reason}")
                        open_pos = None
                        trailing = None
                        t1, t2 = None, None
                        high_water, low_water = -np.inf, np.inf
                        continue

            # close any open position at last bar close (mark to market)
            if open_pos is not None:
                bar = df.iloc[-1]
                open_pos.exit_time = df.index[-1]
                open_pos.exit_price = float(bar["close"])
                open_pos.exit_reason = "EOD"
                risk = abs(open_pos.entry_price - open_pos.sl_price)
                if risk > 0:
                    if open_pos.side == "LONG":
                        r_mfe = (high_water - open_pos.entry_price) / risk
                        r_mae = (open_pos.entry_price - low_water) / risk
                    else:
                        r_mfe = (open_pos.entry_price - low_water) / risk
                        r_mae = (high_water - open_pos.entry_price) / risk
                    open_pos.mfe = float(r_mfe)
                    open_pos.mae = float(r_mae)
                self.trades.append(open_pos)
                logger.info(f"FORCE EXIT {open_pos.side} {sym} @ {open_pos.exit_price} reason=EOD")

    def save_trades_csv(self, path: str) -> None:
        if not self.trades:
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        rows = []
        for t in self.trades:
            rows.append({
                "symbol": t.symbol,
                "side": t.side,
                "entry_time": t.entry_time,
                "entry_price": t.entry_price,
                "sl": t.sl_price,
                "exit_time": t.exit_time,
                "exit_price": t.exit_price,
                "exit_reason": t.exit_reason,
                "MFE_R": t.mfe,
                "MAE_R": t.mae,
            })
        pd.DataFrame(rows).to_csv(path, index=False)
