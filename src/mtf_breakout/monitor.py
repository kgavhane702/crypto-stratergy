from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

from .config import get_settings
from .data.binance_client import BinanceDataClient
from .futures_client import FuturesClient
from .zones import detect_zone, Zone
from .indicators import atr
from .trend import label_trend_ladder, permission_all_bullish, permission_all_bearish
from .utils.logger import get_logger
from .dashboard import dashboard, Trade as DashboardTrade, ZoneInfo

logger = get_logger(__name__)


@dataclass
class Position:
    symbol: str
    side: str  # LONG or SHORT
    entry_price: float
    sl_price: float
    time: pd.Timestamp
    trend_aligned: bool = False # Added for new logic
    trade_id: str = ""


@dataclass
class CandidateInfo:
    symbol: str
    touches: int
    zone_width: float
    priority_score: float


class SymbolWatcher(threading.Thread):
    def __init__(self, symbol: str, interval: str = "5m", max_positions_ref: Dict[str, int] | None = None, scan_every_sec: int = 15) -> None:
        super().__init__(daemon=True)
        self.symbol = symbol
        self.interval = interval
        self.settings = get_settings()
        self.client = BinanceDataClient(self.settings)
        self.futures_client = FuturesClient(self.settings)
        self.stop_event = threading.Event()
        self.candidate_zone: Optional[Zone] = None
        self.max_positions_ref = max_positions_ref
        self.scan_every_sec = scan_every_sec
        self.open_position: Optional[Position] = None
        self.no_dwell_break_time: Optional[pd.Timestamp] = None
        self.awaiting_retest_side: Optional[str] = None
        self.last_breakout_time: Optional[pd.Timestamp] = None
        self.zone_recovery_cooldown_bars = 10  # Wait 10 bars after breakout before looking for new zones
        self.position_exit_time: Optional[pd.Timestamp] = None
        self.position_exit_cooldown_bars = 5  # Wait 5 bars after position exit before new entries

    def _fetch_recent(self, bars: int = 300) -> pd.DataFrame:
        end = pd.Timestamp.utcnow()
        start = end - pd.Timedelta(minutes=5 * bars)
        df = self.client.get_klines_range(
            self.symbol,
            self.interval,
            int(start.value // 1_000_000),
            int(end.value // 1_000_000),
        )
        return df

    def _permission(self, df_5m: pd.DataFrame) -> str:
        labels = label_trend_ladder(df_5m, ["1M", "1W", "1D", "1h"])
        if permission_all_bullish(labels):
            return "LONG"
        if permission_all_bearish(labels):
            return "SHORT"
        return "NONE"

    def _check_retest_logic(self, df: pd.DataFrame, last: pd.Series, zone: Zone, side: str) -> Optional[Position]:
        s = self.settings
        a = atr(df).iloc[-1]
        if a is None or a != a:
            return None
        buf = s.breakout_buffer_frac * float(a)

        if self.no_dwell_break_time is None or self.awaiting_retest_side != side:
            return None
        window_end = self.no_dwell_break_time + pd.Timedelta(minutes=5 * s.retest_window_bars)
        now_ts = last.name
        if now_ts > window_end:
            logger.info(f"{self.symbol}: retest window expired for {side}")
            self.no_dwell_break_time = None
            self.awaiting_retest_side = None
            return None

        in_band = (float(last.get("low", last["close"])) <= zone.high_close and float(last.get("high", last["close"])) >= zone.low_close)
        if not in_band:
            return None

        if side == "LONG" and float(last["close"]) > zone.high_close + buf:
            sl = float(last.get("low", last["close"]))
            logger.info(f"{self.symbol}: retest confirmed LONG entry @ {last['close']}")
            self.no_dwell_break_time = None
            self.awaiting_retest_side = None
            return Position(symbol=self.symbol, side="LONG", entry_price=float(last["close"]), sl_price=sl, time=last.name)
        if side == "SHORT" and float(last["close"]) < zone.low_close - buf:
            sl = float(last.get("high", last["close"]))
            logger.info(f"{self.symbol}: retest confirmed SHORT entry @ {last['close']}")
            self.no_dwell_break_time = None
            self.awaiting_retest_side = None
            return Position(symbol=self.symbol, side="SHORT", entry_price=float(last["close"]), sl_price=sl, time=last.name)
        return None

    def _check_breakout(self, df: pd.DataFrame, zone: Zone) -> Optional[Position]:
        if df.empty:
            return None
        s = self.settings
        last = df.iloc[-1]
        a = atr(df).iloc[-1]
        if a is None or a != a:
            return None
        buf = s.breakout_buffer_frac * float(a)

        # Check trend permission (for position sizing, not entry permission)
        perm = self._permission(df)
        
        # LONG BREAKOUT: Take entry regardless of trend if dwell criteria met
        if float(last["close"]) > zone.high_close + buf and zone.touches_top >= 3:
            dwell = zone.dwell_bars >= s.dwell_bars
            if dwell:
                # Dwell criteria met - take immediate entry
                sl = float(last.get("low", last["close"]))
                trend_aligned = (perm == "LONG")
                size_type = "TREND-ALIGNED" if trend_aligned else "COUNTER-TREND"
                trend_emoji = "🟢" if trend_aligned else "🔴"
                logger.info(f"🚀 RANGE BREAKOUT: LONG entry {self.symbol} close={last['close']:.6f} > {zone.high_close:.6f}+{buf:.6f} (dwell={zone.dwell_bars} bars, {size_type}) {trend_emoji}")
                return Position(symbol=self.symbol, side="LONG", entry_price=float(last["close"]), sl_price=sl, time=last.name, trend_aligned=trend_aligned)
            else:
                # No dwell - wait for retest
                self.no_dwell_break_time = last.name
                self.awaiting_retest_side = "LONG"
                logger.info(f"{self.symbol}: no-dwell LONG breakout detected, waiting for retest (window {s.retest_window_bars} bars)")
                return None

        # SHORT BREAKDOWN: Take entry regardless of trend if dwell criteria met
        if float(last["close"]) < zone.low_close - buf and zone.touches_bottom >= 3:
                    dwell = zone.dwell_bars >= s.dwell_bars
                    if dwell:
                        # Dwell criteria met - take immediate entry
                        sl = float(last.get("high", last["close"]))
                        trend_aligned = (perm == "SHORT")
                        size_type = "TREND-ALIGNED" if trend_aligned else "COUNTER-TREND"
                        trend_emoji = "🟢" if trend_aligned else "🔴"
                        logger.info(f"📉 RANGE BREAKDOWN: SHORT entry {self.symbol} close={last['close']:.6f} < {zone.low_close:.6f}-{buf:.6f} (dwell={zone.dwell_bars} bars, {size_type}) {trend_emoji}")
                        return Position(symbol=self.symbol, side="SHORT", entry_price=float(last["close"]), sl_price=sl, time=last.name, trend_aligned=trend_aligned)
                    else:
                        # No dwell - wait for retest
                        self.no_dwell_break_time = last.name
                        self.awaiting_retest_side = "SHORT"
                        logger.info(f"{self.symbol}: no-dwell SHORT breakdown detected, waiting for retest (window {s.retest_window_bars} bars)")
                        return None

        # Check for retest confirmations (only for no-dwell breakouts)
        ret = self._check_retest_logic(df, last, zone, perm)
        if ret is not None:
            return ret

        return None

    def _execute_trade(self, pos: Position) -> None:
        """Execute the trade using futures client."""
        try:
            # Generate unique trade ID
            trade_id = str(uuid.uuid4())
            pos.trade_id = trade_id
            
            # Calculate position size based on trend alignment
            quantity = self.futures_client.calculate_position_size(pos.symbol, pos.entry_price, pos.sl_price, pos.trend_aligned)
            if quantity <= 0:
                logger.warning(f"{pos.symbol}: Invalid position size {quantity}")
                return

            # Add trade to dashboard
            dashboard_trade = DashboardTrade(
                id=trade_id,
                symbol=pos.symbol,
                side=pos.side,
                entry_time=pos.time.isoformat(),
                entry_price=pos.entry_price,
                sl_price=pos.sl_price,
                quantity=quantity,
                trend_aligned=pos.trend_aligned,
                status="OPEN"
            )
            dashboard.add_trade(dashboard_trade)

            # Place entry order
            side = "BUY" if pos.side == "LONG" else "SELL"
            size_type = "TREND-ALIGNED" if pos.trend_aligned else "COUNTER-TREND"
            entry_result = self.futures_client.place_market_order(pos.symbol, side, quantity)
            
            if not self.settings.dry_run and not entry_result.get("dry_run"):
                # Place stop loss
                sl_side = "SELL" if pos.side == "LONG" else "BUY"
                self.futures_client.place_stop_loss(pos.symbol, sl_side, quantity, pos.sl_price)
                logger.info(f"Placed entry and SL orders for {pos.symbol} ({size_type})")
            else:
                logger.info(f"DRY-RUN: Would place entry and SL for {pos.symbol} ({size_type})")

        except Exception as e:
            logger.error(f"Failed to execute trade for {pos.symbol}: {e}")

    def run(self) -> None:
        logger.info(f"Watcher start: {self.symbol} (interval={self.interval}, scan_every={self.scan_every_sec}s, dry_run={self.settings.dry_run})")
        while not self.stop_event.is_set():
            try:
                df = self._fetch_recent()
                if df.empty:
                    time.sleep(self.scan_every_sec)
                    continue

                # Check if we have an open position and monitor for exit
                if self.open_position is not None:
                    # TODO: Implement position exit monitoring (SL hit, target hit, etc.)
                    # For now, just continue monitoring
                    time.sleep(self.scan_every_sec)
                    continue

                # Check if we're in cooldown period after position exit
                current_time = df.index[-1] if not df.empty else pd.Timestamp.utcnow()
                if self.position_exit_time is not None:
                    bars_since_exit = len(df[df.index > self.position_exit_time])
                    if bars_since_exit < self.position_exit_cooldown_bars:
                        time.sleep(self.scan_every_sec)
                        continue
                    else:
                        # Reset exit time after cooldown
                        self.position_exit_time = None
                        logger.info(f"{self.symbol}: position exit cooldown completed, resuming monitoring")

                # Check if we're in cooldown period after a breakout
                if self.last_breakout_time is not None:
                    bars_since_breakout = len(df[df.index > self.last_breakout_time])
                    if bars_since_breakout < self.zone_recovery_cooldown_bars:
                        time.sleep(self.scan_every_sec)
                        continue

                z = detect_zone(df)
                if z is None:
                    # Zone vanished - check if we should wait for recovery or exit
                    if self.last_breakout_time is not None:
                        bars_since_breakout = len(df[df.index > self.last_breakout_time])
                        if bars_since_breakout < self.zone_recovery_cooldown_bars * 2:  # Extended cooldown for zone recovery
                            logger.info(f"{self.symbol}: zone vanished, waiting for recovery (bars since breakout: {bars_since_breakout})")
                            time.sleep(self.scan_every_sec)
                            continue
                        else:
                            logger.info(f"{self.symbol}: zone vanished after extended cooldown; stopping watcher")
                            break
                    else:
                        logger.info(f"{self.symbol}: candidate zone vanished; stopping watcher")
                        break
                
                # Reset breakout time if we found a new zone
                if self.last_breakout_time is not None:
                    self.last_breakout_time = None
                    logger.info(f"{self.symbol}: new zone detected after false breakout")
                
                if self.candidate_zone is None or (z.end_idx != self.candidate_zone.end_idx or z.width != self.candidate_zone.width):
                    self.candidate_zone = z
                    
                    # Get trend information
                    trend_perm = self._permission(df)
                    trend_emoji = "🟢" if trend_perm == "LONG" else "🔴" if trend_perm == "SHORT" else "🟡"
                    trend_text = f"{trend_emoji} {trend_perm}" if trend_perm != "NONE" else "🟡 NEUTRAL"
                    
                    # Show T/B format using total touches with proper separation
                    logger.info(f"{self.symbol}: candidate refresh width={z.width:.6f} top={z.high_close:.6f} bottom={z.low_close:.6f} touches T/B={z.total_touches}/{z.dwell_bars} | {trend_text}")

                pos = self._check_breakout(df, self.candidate_zone)
                if pos is not None:
                    # Record breakout time for cooldown
                    self.last_breakout_time = current_time
                    
                    if self.max_positions_ref is not None:
                        if self.max_positions_ref.get("open", 0) >= self.max_positions_ref.get("max", 0):
                            logger.warning(f"Max positions reached ({self.max_positions_ref['open']}/{self.max_positions_ref['max']}), skipping entry {pos.side} {pos.symbol}")
                        else:
                            self.max_positions_ref["open"] = self.max_positions_ref.get("open", 0) + 1
                            self.open_position = pos
                            self._execute_trade(pos)
                            # Don't break - continue monitoring for position management
                    else:
                        self.open_position = pos
                        self._execute_trade(pos)
                        # Don't break - continue monitoring for position management

            except Exception as e:
                logger.exception(f"{self.symbol}: exception in watcher loop: {e}")
                time.sleep(self.scan_every_sec)
                continue

            time.sleep(self.scan_every_sec)

        logger.info(f"Watcher exit: {self.symbol}")

    def _handle_position_exit(self, exit_reason: str) -> None:
        """Handle position exit and reset for new opportunities."""
        if self.open_position is not None:
            logger.info(f"{self.symbol}: position exited ({exit_reason}) - {self.open_position.side} @ {self.open_position.entry_price}")
            
            # Update position count
            if self.max_positions_ref is not None:
                self.max_positions_ref["open"] = max(0, self.max_positions_ref.get("open", 0) - 1)
            
            # Record exit time for cooldown
            self.position_exit_time = pd.Timestamp.utcnow()
            
            # Reset position
            self.open_position = None
            
            # Update dashboard if needed
            # TODO: Update dashboard with exit information

    def stop(self) -> None:
        self.stop_event.set()


class GlobalScanner(threading.Thread):
    def __init__(self, symbols: List[str], interval: str, scan_every_sec: int, candidate_cb) -> None:
        super().__init__(daemon=True)
        self.symbols = symbols
        self.interval = interval
        self.scan_every_sec = scan_every_sec
        self.settings = get_settings()
        self.client = BinanceDataClient(self.settings)
        self.stop_event = threading.Event()
        self.candidate_cb = candidate_cb
        self.last_scan_time = ""
        self.total_symbols_scanned = 0

    def run(self) -> None:
        logger.info(f"GlobalScanner start (interval={self.interval}, scan_every={self.scan_every_sec}s)")
        while not self.stop_event.is_set():
            try:
                candidates: List[CandidateInfo] = []
                self.total_symbols_scanned = len(self.symbols)
                self.last_scan_time = pd.Timestamp.utcnow().strftime("%H:%M:%S")
                
                for sym in self.symbols:
                    end = pd.Timestamp.utcnow()
                    start = end - pd.Timedelta(minutes=5 * max(60, self.settings.dwell_bars + 20))
                    df = self.client.get_klines_range(sym, self.interval, int(start.value // 1_000_000), int(end.value // 1_000_000))
                    if df.empty:
                        continue
                    
                    # Only check for zone detection (no trend permission required)
                    z = detect_zone(df)
                    if z is None:
                        continue
                    if z.total_touches >= 2:  # Use total touches with proper separation
                        priority_score = z.total_touches / (z.width + 0.001)  # Higher touches, tighter zone = higher priority
                        candidates.append(CandidateInfo(sym, z.total_touches, z.width, priority_score))
                
                # Sort by priority and call callback for top candidates
                candidates.sort(key=lambda x: x.priority_score, reverse=True)
                for candidate in candidates[:self.settings.max_monitor_pool_size]:
                    self.candidate_cb(candidate.symbol)
                    
                time.sleep(self.scan_every_sec)
            except Exception as e:
                logger.exception(f"GlobalScanner exception: {e}")
                time.sleep(self.scan_every_sec)

    def stop(self) -> None:
        self.stop_event.set()


class Monitor:
    def __init__(self, symbols: List[str], interval: str = "5m", max_positions: int = 3, scan_every_sec: int = 15) -> None:
        self.symbols = symbols
        self.interval = interval
        self.settings = get_settings()
        self.max_positions = max_positions
        self.scan_every_sec = scan_every_sec
        self.max_positions_ref: Dict[str, int] = {"open": 0, "max": max_positions}
        self.candidate_symbols: Set[str] = set()
        self.watchers: Dict[str, SymbolWatcher] = {}
        self.lock = threading.Lock()
        self.scanner = GlobalScanner(symbols, interval, self.settings.global_scan_interval_seconds, self._on_candidate)
        self.futures_client = FuturesClient(self.settings)

    def _on_candidate(self, symbol: str) -> None:
        with self.lock:
            if symbol in self.watchers:
                return
            if symbol not in self.candidate_symbols:
                logger.info(f"Add candidate to monitor pool: {symbol}")
                self.candidate_symbols.add(symbol)
                w = SymbolWatcher(symbol, self.interval, self.max_positions_ref, scan_every_sec=self.scan_every_sec)
                self.watchers[symbol] = w
                w.start()

    def _cleanup_watchers(self) -> None:
        with self.lock:
            to_remove = []
            for sym, w in self.watchers.items():
                if not w.is_alive():
                    to_remove.append(sym)
            for sym in to_remove:
                logger.info(f"Remove symbol from monitor pool: {sym}")
                self.watchers.pop(sym, None)
                self.candidate_symbols.discard(sym)

    def start(self) -> None:
        logger.info(f"Monitor starting with global scanner + monitor pool. symbols={self.symbols}")
        
        # Start dashboard
        dashboard.start()
        
        # Setup futures account and log balance
        if not self.settings.dry_run:
            self.futures_client.setup_all_symbols(self.symbols)
            self.futures_client.clear_orphan_positions()
            
            # Log account balance
            try:
                balance = self.futures_client.get_account_info()
                usdt_balance = balance.get("USDT", {})
                available_balance = float(usdt_balance.get("free", 0))
                total_balance = float(usdt_balance.get("total", 0))
                logger.info(f"💰 Account Balance - Available: ${available_balance:.2f} USDT, Total: ${total_balance:.2f} USDT")
            except Exception as e:
                logger.warning(f"Failed to get account balance: {e}")
        else:
            logger.info("🔍 DRY RUN MODE - No real trades will be executed")
        
        self.scanner.start()
        threading.Thread(target=self._maintenance_loop, daemon=True).start()

    def _maintenance_loop(self) -> None:
        while True:
            try:
                # Update dashboard with system information
                self._update_dashboard_info()
                
                # Cleanup dead watchers
                self._cleanup_watchers()
                
                time.sleep(5)  # Update every 5 seconds
            except Exception as e:
                logger.exception(f"Maintenance loop exception: {e}")
                time.sleep(5)

    def _update_dashboard_info(self) -> None:
        """Update dashboard with current system information."""
        try:
            with self.lock:
                monitor_pool_size = len(self.watchers)
                priority_pool_size = len(self.candidate_symbols)
                active_zones_count = len([w for w in self.watchers.values() if w.candidate_zone is not None])
                
                scanner_status = "RUNNING" if self.scanner.is_alive() else "STOPPED"
                
                dashboard.update_system_info(
                    global_scanner_status=scanner_status,
                    monitor_pool_size=monitor_pool_size,
                    priority_pool_size=priority_pool_size,
                    active_zones_count=active_zones_count,
                    total_symbols_scanned=self.scanner.total_symbols_scanned,
                    last_scan_time=self.scanner.last_scan_time,
                    candidates_in_queue=len(self.candidate_symbols)
                )
        except Exception as e:
            logger.error(f"Failed to update dashboard info: {e}")

    def stop(self) -> None:
        logger.info("Monitor stopping...")
        self.scanner.stop()
        for w in list(self.watchers.values()):
            w.stop()
        for w in list(self.watchers.values()):
            w.join(timeout=5)
        logger.info("Monitor stopped")
