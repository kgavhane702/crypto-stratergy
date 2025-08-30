#!/usr/bin/env python3
"""
Simple backtest runner for MTF Breakout Strategy
"""

import sys
import os
from datetime import datetime

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from mtf_breakout.config import get_settings
from mtf_breakout.data.binance_client import BinanceDataClient
from mtf_breakout.universe import get_top_usdt_symbols
from mtf_breakout.backtest.engine import Backtester
from mtf_breakout.reporting import compute_summary, plot_equity
from mtf_breakout.utils.logger import get_logger

logger = get_logger(__name__)


def run_backtest(symbols=None, universe_n=None, start_date="2024-08-01", end_date="2024-08-30", export_dir="./backtest_results"):
    """Run backtest with given parameters."""
    
    settings = get_settings()
    
    # Universe selection
    if universe_n is not None:
        symbols = get_top_usdt_symbols(universe_n)
        logger.info(f"Selected top {universe_n} symbols: {symbols}")
    elif symbols is None:
        symbols = settings.default_symbols
        logger.info(f"Using default symbols: {symbols}")
    
    # Create export directory
    os.makedirs(export_dir, exist_ok=True)
    
    # Run backtest
    logger.info(f"Starting backtest for {len(symbols)} symbols from {start_date} to {end_date}")
    bt = Backtester(symbols, start=start_date, end=end_date, interval="5m")
    bt.run()
    
    # Save results
    trades_csv = os.path.join(export_dir, "trades.csv")
    bt.save_trades_csv(trades_csv)
    logger.info(f"Saved trades CSV: {trades_csv}")
    
    # Compute and display summary
    summary = compute_summary(bt.trades)
    logger.info(f"=== BACKTEST SUMMARY ===")
    logger.info(f"Win Rate: {summary.win_rate:.2f}%")
    logger.info(f"Profit Factor: {summary.profit_factor:.2f}")
    logger.info(f"Average R: {summary.avg_r:.2f}")
    logger.info(f"Sharpe Ratio: {summary.sharpe:.2f}")
    logger.info(f"Total Trades: {summary.trade_count}")
    logger.info(f"Total P&L: ${summary.total_pnl:.2f}")
    logger.info(f"Max Drawdown: {summary.max_drawdown:.2f}%")
    
    # Save equity plot
    eq_path = os.path.join(export_dir, "equity.png")
    plot_equity(bt.trades, eq_path)
    logger.info(f"Saved equity plot: {eq_path}")
    
    return summary


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="MTF Breakout Strategy Backtest Runner")
    parser.add_argument("--symbols", nargs="*", help="Specific symbols to test")
    parser.add_argument("--universe-n", type=int, help="Top N symbols by volume")
    parser.add_argument("--start", default="2024-08-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default="2024-08-30", help="End date (YYYY-MM-DD)")
    parser.add_argument("--export-dir", default="./backtest_results", help="Export directory")
    
    args = parser.parse_args()
    
    run_backtest(
        symbols=args.symbols,
        universe_n=args.universe_n,
        start_date=args.start,
        end_date=args.end,
        export_dir=args.export_dir
    )
