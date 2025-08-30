import os
import sys
import time
from typing import List

from dotenv import load_dotenv

# Ensure src/ is on sys.path for local execution without install
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(BASE_DIR, "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from mtf_breakout.config import get_settings
from mtf_breakout.universe import get_top_usdt_symbols
from mtf_breakout.monitor import Monitor
from mtf_breakout.utils.logger import get_logger


def parse_symbols_env() -> List[str]:
    raw = os.getenv("SYMBOLS", "").strip()
    if not raw:
        return []
    parts = [p.strip().upper() for p in raw.replace(",", " ").split() if p.strip()]
    return parts


def main() -> None:
    # Load env first
    load_dotenv(dotenv_path="env.txt", override=False)
    load_dotenv(override=False)

    logger = get_logger("runner")
    settings = get_settings()

    symbols = parse_symbols_env()
    if not symbols:
        if settings.universe_n is not None and settings.universe_n > 0:
            symbols = get_top_usdt_symbols(settings.universe_n)
        else:
            symbols = settings.default_symbols

    logger.info(f"DRY_RUN={settings.dry_run}")

    monitor = Monitor(
        symbols=symbols,
        interval=settings.execution_timeframe,
        max_positions=settings.max_positions,
        scan_every_sec=settings.monitor_interval_seconds,
    )

    logger.info("Runner starting monitor...")
    monitor.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Runner stopping...")
        monitor.stop()


if __name__ == "__main__":
    main()
