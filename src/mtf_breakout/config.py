from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

from dotenv import load_dotenv


@dataclass
class Settings:
    # API
    binance_api_key: str
    binance_api_secret: str
    binance_testnet_api_key: str
    binance_testnet_api_secret: str
    use_testnet: bool = True
    binance_base_url: str = "https://api.binance.com"
    binance_testnet_url: str = "https://testnet.binancefuture.com"

    # App
    app_log_level: str = "INFO"
    data_dir: str = "/app/data"
    export_dir: str = "/app/exports"
    dashboard_port: int = 8080

    # Strategy defaults
    dwell_bars: int = 18  # 18 x 5m = 90m
    touch_separation_bars: int = 3
    retest_window_bars: int = 8
    touch_buffer_frac: float = 0.15
    breakout_buffer_frac: float = 0.15
    atr_tight_mult: float = 0.55

    # Risk/fees
    risk_fraction: float = 0.01
    taker_fee_bps: float = 10.0
    slippage_bps: float = 2.0

    # Futures trading
    leverage: int = 10
    position_size_pct_trend_aligned: float = 5.0
    position_size_pct_counter_trend: float = 3.0
    clear_orphan_positions: bool = True

    # Universe
    default_symbols: List[str] = field(default_factory=lambda: [
        "BTC/USDT", "ETH/USDT", "BNB/USDT", "XRP/USDT", "ADA/USDT",
        "SOL/USDT", "DOGE/USDT", "TRX/USDT", "MATIC/USDT", "DOT/USDT",
        "LTC/USDT", "SHIB/USDT", "AVAX/USDT", "UNI/USDT", "LINK/USDT",
        "ATOM/USDT", "XMR/USDT", "ETC/USDT", "XLM/USDT", "NEAR/USDT",
    ])

    # Timeframes
    execution_timeframe: str = "5m"
    trend_ladder: List[str] = field(default_factory=lambda: ["1M", "1W", "1D", "1h"])

    # Monitoring / runner
    monitor_interval_seconds: int = 15
    global_scan_interval_seconds: int = 30
    max_monitor_pool_size: int = 8
    universe_n: Optional[int] = None
    max_positions: int = 3
    dry_run: bool = True


def get_settings() -> Settings:
    # Load env from env.txt first (if present), then .env
    load_dotenv(dotenv_path="env.txt", override=False)
    load_dotenv(override=False)

    def _get(name: str, default: str) -> str:
        val = os.getenv(name)
        return default if val is None or val == "" else val

    universe_n_env = os.getenv("UNIVERSE_N")
    universe_n = int(universe_n_env) if universe_n_env and universe_n_env.isdigit() else None

    monitor_interval_env = _get("MONITOR_INTERVAL_SECONDS", "15")
    global_scan_interval_env = _get("GLOBAL_SCAN_INTERVAL_SECONDS", "30")

    def _to_bool(v: str) -> bool:
        return v.strip().lower() in ("1", "true", "yes", "on")

    return Settings(
        binance_api_key=_get("BINANCE_API_KEY", ""),
        binance_api_secret=_get("BINANCE_API_SECRET", ""),
        binance_testnet_api_key=_get("BINANCE_TESTNET_API_KEY", ""),
        binance_testnet_api_secret=_get("BINANCE_TESTNET_API_SECRET", ""),
        use_testnet=_to_bool(_get("USE_TESTNET", "true")),
        binance_base_url=_get("BINANCE_BASE_URL", "https://api.binance.com"),
        binance_testnet_url=_get("BINANCE_TESTNET_URL", "https://testnet.binancefuture.com"),
        app_log_level=_get("APP_LOG_LEVEL", "INFO"),
        data_dir=_get("DATA_DIR", "/app/data"),
        export_dir=_get("EXPORT_DIR", "/app/exports"),
        dashboard_port=int(_get("DASHBOARD_PORT", "8080")),
        dwell_bars=int(_get("DWELL_BARS", "18")),
        touch_separation_bars=int(_get("TOUCH_SEPARATION_BARS", "3")),
        retest_window_bars=int(_get("RETEST_WINDOW_BARS", "8")),
        touch_buffer_frac=float(_get("TOUCH_BUFFER_FRAC", "0.15")),
        breakout_buffer_frac=float(_get("BREAKOUT_BUFFER_FRAC", "0.15")),
        atr_tight_mult=float(_get("ATR_TIGHT_MULT", "0.55")),
        risk_fraction=float(_get("RISK_FRACTION", "0.01")),
        taker_fee_bps=float(_get("TAKER_FEE_BPS", "10")),
        slippage_bps=float(_get("SLIPPAGE_BPS", "2")),
        leverage=int(_get("LEVERAGE", "10")),
        position_size_pct_trend_aligned=float(_get("POSITION_SIZE_PCT_TREND_ALIGNED", "5.0")),
        position_size_pct_counter_trend=float(_get("POSITION_SIZE_PCT_COUNTER_TREND", "3.0")),
        clear_orphan_positions=_to_bool(_get("CLEAR_ORPHAN_POSITIONS", "true")),
        execution_timeframe=_get("EXECUTION_TIMEFRAME", "5m"),
        monitor_interval_seconds=int(monitor_interval_env),
        global_scan_interval_seconds=int(global_scan_interval_env),
        max_monitor_pool_size=int(_get("MAX_MONITOR_POOL_SIZE", "8")),
        universe_n=universe_n,
        max_positions=int(_get("MAX_POSITIONS", "3")),
        dry_run=_to_bool(_get("DRY_RUN", "true")),
    )
