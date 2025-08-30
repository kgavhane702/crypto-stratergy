from __future__ import annotations

import time
from typing import Dict, List, Optional

from binance.um_futures import UMFutures
from binance.lib.utils import config_logging
from binance.error import ClientError

from .config import get_settings, Settings
from .utils.logger import get_logger

logger = get_logger(__name__)


@retry(wait=wait_exponential(multiplier=1, min=1, max=30), stop=stop_after_attempt(5), reraise=True)
def _api_call(func, *args, **kwargs):
    return func(*args, **kwargs)


class FuturesClient:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        
        # Choose API credentials based on testnet setting
        if self.settings.use_testnet:
            api_key = self.settings.binance_testnet_api_key
            api_secret = self.settings.binance_testnet_api_secret
            base_url = self.settings.binance_testnet_url
            logger.info("Using Binance Testnet API")
        else:
            api_key = self.settings.binance_api_key
            api_secret = self.settings.binance_api_secret
            base_url = self.settings.binance_base_url
            logger.info("Using Binance Live API")
        
        self.client = UMFutures(
            key=api_key,
            secret=api_secret,
            base_url=base_url,
        )

    def setup_symbol(self, symbol: str) -> None:
        """Set leverage and margin mode for a symbol."""
        try:
            # Set isolated margin mode
            _api_call(self.client.change_margin_type, symbol=symbol, marginType="ISOLATED")
            logger.info(f"Set {symbol} to ISOLATED margin mode")
        except Exception as e:
            if "No need to change margin type" not in str(e):
                logger.warning(f"Failed to set margin mode for {symbol}: {e}")

        try:
            # Set leverage
            _api_call(self.client.change_leverage, symbol=symbol, leverage=self.settings.leverage)
            logger.info(f"Set {symbol} leverage to {self.settings.leverage}")
        except Exception as e:
            logger.warning(f"Failed to set leverage for {symbol}: {e}")

    def get_account_info(self) -> Dict:
        """Get account info including balance."""
        return _api_call(self.client.account)

    def get_position_info(self) -> List[Dict]:
        """Get all positions."""
        return _api_call(self.client.get_position_info)

    def calculate_position_size(self, symbol: str, entry_price: float, sl_price: float, trend_aligned: bool = True) -> float:
        """Calculate position size based on trend alignment."""
        account = self.get_account_info()
        available_balance = float(account.get("availableBalance", 0))
        
        # Choose position size based on trend alignment
        if trend_aligned:
            position_value = available_balance * (self.settings.position_size_pct_trend_aligned / 100.0)
        else:
            position_value = available_balance * (self.settings.position_size_pct_counter_trend / 100.0)
        
        # Calculate quantity based on entry and SL distance
        risk_per_unit = abs(entry_price - sl_price)
        if risk_per_unit <= 0:
            return 0.0
        
        quantity = position_value / risk_per_unit
        return quantity

    def place_market_order(self, symbol: str, side: str, quantity: float) -> Dict:
        """Place a market order."""
        if self.settings.dry_run:
            logger.info(f"DRY-RUN: Would place {side} {quantity} {symbol} @ market")
            return {"dry_run": True}
        
        return _api_call(
            self.client.new_order,
            symbol=symbol,
            side=side,
            type="MARKET",
            quantity=quantity,
        )

    def place_stop_loss(self, symbol: str, side: str, quantity: float, stop_price: float) -> Dict:
        """Place a stop loss order."""
        if self.settings.dry_run:
            logger.info(f"DRY-RUN: Would place {side} stop loss {quantity} {symbol} @ {stop_price}")
            return {"dry_run": True}
        
        return _api_call(
            self.client.new_order,
            symbol=symbol,
            side=side,
            type="STOP_MARKET",
            quantity=quantity,
            stopPrice=stop_price,
        )

    def close_position(self, symbol: str, side: str, quantity: float) -> Dict:
        """Close a position."""
        close_side = "SELL" if side == "BUY" else "BUY"
        if self.settings.dry_run:
            logger.info(f"DRY-RUN: Would close {side} position {quantity} {symbol}")
            return {"dry_run": True}
        
        return _api_call(
            self.client.new_order,
            symbol=symbol,
            side=close_side,
            type="MARKET",
            quantity=quantity,
        )

    def clear_orphan_positions(self) -> None:
        """Close any open positions that shouldn't exist."""
        if not self.settings.clear_orphan_positions:
            return
        
        positions = self.get_position_info()
        for pos in positions:
            symbol = pos["symbol"]
            size = float(pos["positionAmt"])
            if abs(size) > 0.001:  # Has position
                logger.warning(f"Found orphan position: {symbol} {size}")
                if not self.settings.dry_run:
                    close_side = "SELL" if size > 0 else "BUY"
                    try:
                        self.close_position(symbol, close_side, abs(size))
                        logger.info(f"Closed orphan position: {symbol}")
                    except Exception as e:
                        logger.error(f"Failed to close orphan position {symbol}: {e}")
                else:
                    logger.info(f"DRY-RUN: Would close orphan position {symbol} {size}")

    def setup_all_symbols(self, symbols: List[str]) -> None:
        """Setup leverage and margin mode for all symbols."""
        for symbol in symbols:
            self.setup_symbol(symbol)
