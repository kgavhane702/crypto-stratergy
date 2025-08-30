from __future__ import annotations

import argparse
import os
from typing import List

import pandas as pd

from .config import get_settings
from .data.binance_client import BinanceDataClient
from .universe import get_top_usdt_symbols
from .monitor import Monitor
from .backtest.engine import Backtester
from .reporting import compute_summary, plot_equity
from .utils.logger import get_logger

logger = get_logger(__name__)


def _to_ms(ts_str: str) -> int:
    ts = pd.Timestamp(ts_str, tz="UTC")
    return int(ts.value // 1_000_000)  # ns -> ms


def cmd_fetch(args: argparse.Namespace) -> None:
    settings = get_settings()
    client = BinanceDataClient(settings)

    os.makedirs(settings.data_dir, exist_ok=True)

    start_ms = _to_ms(args.start)
    end_ms = _to_ms(args.end)

    symbols: List[str] = args.symbols
    interval = args.interval

    for sym in symbols:
        logger.info(f"Fetching {sym} {interval} klines {args.start} -> {args.end}")
        df = client.get_klines_range(sym, interval, start_ms, end_ms)
        if df.empty:
            logger.warning(f"No data for {sym}")
            continue
        out_path = os.path.join(settings.data_dir, f"{sym}_{interval}.csv")
        df.to_csv(out_path, index=True)
        logger.info(f"Saved {len(df)} rows to {out_path}")


def cmd_monitor(args: argparse.Namespace) -> None:
    settings = get_settings()

    # Universe selection
    symbols: List[str]
    if args.universe_n is not None:
        symbols = get_top_usdt_symbols(args.universe_n)
    elif args.symbols:
        symbols = args.symbols
    else:
        symbols = settings.default_symbols

    monitor = Monitor(symbols, interval=args.interval, max_positions=args.max_positions)
    monitor.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received; stopping monitor...")
        monitor.stop()


def cmd_backtest(args: argparse.Namespace) -> None:
    settings = get_settings()
    # Universe selection
    symbols: List[str]
    if args.universe_n is not None:
        symbols = get_top_usdt_symbols(args.universe_n)
    elif args.symbols:
        symbols = args.symbols
    else:
        symbols = settings.default_symbols

    bt = Backtester(symbols, start=args.start, end=args.end, interval=args.interval)
    bt.run()

    export_dir = args.export_dir or settings.export_dir
    os.makedirs(export_dir, exist_ok=True)
    trades_csv = os.path.join(export_dir, "trades.csv")
    bt.save_trades_csv(trades_csv)
    logger.info(f"Saved trades CSV: {trades_csv}")

    summary = compute_summary(bt.trades)
    logger.info(f"Summary: win_rate={summary.win_rate:.2f} profit_factor={summary.profit_factor:.2f} avg_R={summary.avg_r:.2f} sharpe={summary.sharpe:.2f} trades={summary.trade_count}")

    eq_path = os.path.join(export_dir, "equity.png")
    plot_equity(bt.trades, eq_path)
    logger.info(f"Saved equity plot: {eq_path}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mtf-breakout", description="MTF 5m Breakout/Retest Strategy Tools")
    sub = p.add_subparsers(dest="command")

    f = sub.add_parser("fetch", help="Fetch klines and save to CSV")
    f.add_argument("--symbols", nargs="+", default=["BTCUSDT"], help="Symbol list, e.g., BTCUSDT ETHUSDT")
    f.add_argument("--start", required=True, help="Start date/time UTC, e.g., 2024-01-01 or 2024-01-01 00:00")
    f.add_argument("--end", required=True, help="End date/time UTC")
    f.add_argument("--interval", default="5m", help="Binance interval, e.g., 5m, 1h, 1d")
    f.set_defaults(func=cmd_fetch)

    m = sub.add_parser("monitor", help="Monitor breakout candidates and log prompt entries")
    m.add_argument("--symbols", nargs="*", default=[], help="Optional explicit symbols")
    m.add_argument("--universe-n", type=int, default=None, help="If set, select top N USDT symbols by 24h quote volume")
    m.add_argument("--interval", default="5m", help="Monitoring interval timeframe, default 5m")
    m.add_argument("--max-positions", type=int, default=3, help="Maximum simultaneous positions allowed (dry-run)")
    m.set_defaults(func=cmd_monitor)

    b = sub.add_parser("backtest", help="Run event-driven backtest and save outputs")
    b.add_argument("--symbols", nargs="*", default=[], help="Optional explicit symbols")
    b.add_argument("--universe-n", type=int, default=None, help="If set, select top N USDT symbols by 24h quote volume")
    b.add_argument("--interval", default="5m", help="Backtest timeframe (5m)")
    b.add_argument("--start", required=True, help="Start date/time UTC")
    b.add_argument("--end", required=True, help="End date/time UTC")
    b.add_argument("--export-dir", default=None, help="Export directory for outputs")
    b.set_defaults(func=cmd_backtest)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
