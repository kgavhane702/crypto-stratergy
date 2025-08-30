from __future__ import annotations

from typing import List

from binance.um_futures import UMFutures

from .config import get_settings
from .utils.logger import get_logger

logger = get_logger(__name__)


def get_top_usdt_symbols(n: int) -> List[str]:
    settings = get_settings()
    
    # Choose API credentials based on testnet setting
    if settings.use_testnet:
        api_key = settings.binance_testnet_api_key
        api_secret = settings.binance_testnet_api_secret
        base_url = settings.binance_testnet_url
    else:
        api_key = settings.binance_api_key
        api_secret = settings.binance_api_secret
        base_url = settings.binance_base_url
        
    client = UMFutures(
        key=api_key,
        secret=api_secret,
        base_url=base_url,
    )

    tickers = client.ticker_24hr()
    filtered = [t for t in tickers if isinstance(t, dict) and str(t.get("symbol", "")).endswith("USDT")]

    def _qv(x: dict) -> float:
        try:
            return float(x.get("quoteVolume", 0.0))
        except Exception:
            return 0.0

    filtered.sort(key=_qv, reverse=True)
    symbols = [t["symbol"] for t in filtered[:max(0, n)]]
    logger.info(f"Selected top {n} USDT symbols by quote volume: {symbols}")
    return symbols
