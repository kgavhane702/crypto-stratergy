from __future__ import annotations

from typing import List

import ccxt

from .config import get_settings
from .utils.logger import get_logger

logger = get_logger(__name__)


def get_top_usdt_symbols(n: int) -> List[str]:
    settings = get_settings()
    
    # Use CCXT for symbol selection
    exchange = ccxt.binance({
        'apiKey': settings.binance_api_key,
        'secret': settings.binance_api_secret,
        'sandbox': settings.use_testnet,
        'enableRateLimit': True,
    })
    
    if settings.use_testnet:
        exchange.set_sandbox_mode(True)

    try:
        tickers = exchange.fetch_tickers()
        # Keep symbols in CCXT format (e.g., "BTC/USDT")
        filtered = [symbol for symbol in tickers.keys() if symbol.endswith("USDT")]
        if not filtered:
            logger.warning("No USDT pairs found, using fallback symbols")
            return ["BTC/USDT", "ETH/USDT", "BNB/USDT", "ADA/USDT", "SOL/USDT"]
        
        # Sort by 24h volume
        def get_volume(symbol):
            try:
                return float(tickers[symbol].get('quoteVolume', 0))
            except:
                return 0
        
        filtered.sort(key=get_volume, reverse=True)
        symbols = filtered[:n]
        logger.info(f"Selected top {n} USDT symbols by quote volume: {symbols}")
        return symbols
    except Exception as e:
        logger.error(f"Failed to fetch symbols: {e}")
        # Fallback to default symbols
        return ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT"]
