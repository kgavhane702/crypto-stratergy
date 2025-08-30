from __future__ import annotations

from typing import Iterable, Optional

import os
import pandas as pd
import ccxt
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

from ..config import get_settings, Settings
from ..utils.logger import get_logger

logger = get_logger(__name__)


class BinanceDataClient:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        
        # Use CCXT for data fetching
        self.exchange = ccxt.binance({
            'apiKey': self.settings.binance_api_key,
            'secret': self.settings.binance_api_secret,
            'sandbox': self.settings.use_testnet,
            'enableRateLimit': True,
        })
        
        if self.settings.use_testnet:
            self.exchange.set_sandbox_mode(True)
            logger.info("Using Binance Testnet via CCXT")
        else:
            logger.info("Using Binance Live via CCXT")

    def _convert_interval(self, interval: str) -> str:
        """Convert interval format for CCXT."""
        interval_map = {
            "1m": "1m",
            "5m": "5m", 
            "15m": "15m",
            "30m": "30m",
            "1h": "1h",
            "4h": "4h",
            "1d": "1d",
            "1w": "1w",
            "1M": "1M"
        }
        return interval_map.get(interval, interval)

    @retry(wait=wait_exponential(multiplier=1, min=1, max=30), stop=stop_after_attempt(5), reraise=True)
    def get_klines(
        self,
        symbol: str,
        interval: str = "5m",
        start_time_ms: Optional[int] = None,
        end_time_ms: Optional[int] = None,
        limit: int = 1000,
    ) -> pd.DataFrame:
        # Convert interval format for CCXT
        ccxt_interval = self._convert_interval(interval)
        
        try:
            raw = self.exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=ccxt_interval,
                since=start_time_ms,
                limit=limit,
            )
        except Exception as e:
            logger.error(f"Failed to fetch OHLCV for {symbol}: {e}")
            return pd.DataFrame(
                columns=["open_time", "open", "high", "low", "close", "volume"]
            ).set_index("open_time")
        
        if not raw:
            return pd.DataFrame(
                columns=["open_time", "open", "high", "low", "close", "volume"]
            ).set_index("open_time")

        # CCXT returns: [timestamp, open, high, low, close, volume]
        df = pd.DataFrame(raw, columns=["open_time", "open", "high", "low", "close", "volume"])
        
        # Convert to numeric
        num_cols = ["open", "high", "low", "close", "volume"]
        for c in num_cols:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        # Convert timestamp to datetime
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df = df.set_index("open_time").sort_index()
        
        return df

    def _cache_path(self, symbol: str, interval: str) -> str:
        # Ensure data directory exists
        data_dir = self.settings.data_dir
        try:
            os.makedirs(data_dir, exist_ok=True)
        except Exception as e:
            logger.warning(f"Failed to create data directory {data_dir}: {e}")
            # Fallback to current directory
            data_dir = "."
        
        # Clean symbol name for file system (replace / with _)
        clean_symbol = symbol.replace("/", "_")
        fname = f"{clean_symbol}_{interval}.csv"
        return os.path.join(data_dir, fname)

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
        try:
            path = self._cache_path(symbol, interval)
            # Ensure the directory exists before writing
            cache_dir = os.path.dirname(path)
            if cache_dir:
                os.makedirs(cache_dir, exist_ok=True)
            df.to_csv(path, index=True)
            logger.debug(f"Successfully wrote cache for {symbol} to {path}")
        except Exception as e:
            logger.warning(f"Failed to write cache for {symbol}: {e}")
            # Continue without caching if there's an issue

    def get_klines_range(
        self,
        symbol: str,
        interval: str,
        start_time_ms: int,
        end_time_ms: int,
        max_batch: int = 1000,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        # Ensure data directory exists before any cache operations
        if use_cache:
            try:
                os.makedirs(self.settings.data_dir, exist_ok=True)
            except Exception as e:
                logger.warning(f"Failed to create data directory {self.settings.data_dir}: {e}")
                use_cache = False
        
        # Disable caching if we're in a container environment without proper write permissions
        if use_cache and not os.access(self.settings.data_dir, os.W_OK):
            logger.warning(f"Caching disabled - no write access to {self.settings.data_dir}")
            use_cache = False
        frames: list[pd.DataFrame] = []
        next_start = start_time_ms
        while True:
            df = self.get_klines(symbol, interval, start_time_ms=next_start, end_time_ms=end_time_ms, limit=max_batch)
            if df.empty:
                break
            frames.append(df)
            last_close_ms = int(df.index[-1].value // 1_000_000)
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
