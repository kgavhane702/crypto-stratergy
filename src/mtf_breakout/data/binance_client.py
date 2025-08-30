from __future__ import annotations

from typing import Iterable, Optional

import os
import pandas as pd
from binance.spot import Spot
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

from ..config import get_settings, Settings
from ..utils.logger import get_logger

logger = get_logger(__name__)


class BinanceDataClient:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.client = Spot(
            api_key=self.settings.binance_api_key,
            api_secret=self.settings.binance_api_secret,
            base_url=self.settings.binance_base_url,
        )

    @retry(wait=wait_exponential(multiplier=1, min=1, max=30), stop=stop_after_attempt(5), reraise=True)
    def get_klines(
        self,
        symbol: str,
        interval: str = "5m",
        start_time_ms: Optional[int] = None,
        end_time_ms: Optional[int] = None,
        limit: int = 1000,
    ) -> pd.DataFrame:
        raw = self.client.klines(
            symbol=symbol,
            interval=interval,
            startTime=start_time_ms,
            endTime=end_time_ms,
            limit=limit,
        )
        if not raw:
            return pd.DataFrame(
                columns=[
                    "open_time", "open", "high", "low", "close", "volume",
                    "close_time", "quote_volume", "trades",
                    "taker_base_volume", "taker_quote_volume",
                ]
            ).set_index("open_time")

        df = pd.DataFrame(raw, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_base_volume", "taker_quote_volume", "ignore",
        ])
        df = df.drop(columns=["ignore"])  # type: ignore[assignment]

        num_cols = ["open", "high", "low", "close", "volume", "quote_volume", "taker_base_volume", "taker_quote_volume"]
        for c in num_cols:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["trades"] = pd.to_numeric(df["trades"], errors="coerce").astype("Int64")

        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
        df = df.set_index("open_time").sort_index()
        return df

    def _cache_path(self, symbol: str, interval: str) -> str:
        os.makedirs(self.settings.data_dir, exist_ok=True)
        fname = f"{symbol}_{interval}.csv"
        return os.path.join(self.settings.data_dir, fname)

    def _read_cache(self, symbol: str, interval: str) -> pd.DataFrame:
        path = self._cache_path(symbol, interval)
        if os.path.exists(path):
            try:
                df = pd.read_csv(path, parse_dates=["open_time"], index_col="open_time")
                df.index = pd.to_datetime(df.index, utc=True)
                return df
            except Exception:
                return pd.DataFrame()
        return pd.DataFrame()

    def _write_cache(self, symbol: str, interval: str, df: pd.DataFrame) -> None:
        path = self._cache_path(symbol, interval)
        df.to_csv(path, index=True)

    def get_klines_range(
        self,
        symbol: str,
        interval: str,
        start_time_ms: int,
        end_time_ms: int,
        max_batch: int = 1000,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        next_start = start_time_ms
        while True:
            df = self.get_klines(symbol, interval, start_time_ms=next_start, end_time_ms=end_time_ms, limit=max_batch)
            if df.empty:
                break
            frames.append(df)
            last_close_ms = int(df["close_time"].iloc[-1].value // 1_000_000)
            if last_close_ms >= end_time_ms:
                break
            next_start = last_close_ms + 1
        new_df = pd.concat(frames, axis=0).sort_index() if frames else pd.DataFrame()

        if not use_cache:
            if new_df.empty:
                return new_df
            return new_df.loc[pd.to_datetime(start_time_ms, unit="ms", utc=True): pd.to_datetime(end_time_ms, unit="ms", utc=True)]

        # Merge with cache
        cache_df = self._read_cache(symbol, interval)
        if cache_df.empty and new_df.empty:
            return pd.DataFrame()
        merged = pd.concat([cache_df, new_df], axis=0)
        merged = merged[~merged.index.duplicated(keep="last")].sort_index()
        # Persist
        self._write_cache(symbol, interval, merged)
        return merged.loc[pd.to_datetime(start_time_ms, unit="ms", utc=True): pd.to_datetime(end_time_ms, unit="ms", utc=True)]
