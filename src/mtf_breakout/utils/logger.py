import logging
import os
from typing import Optional

_LEVEL_MAP = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}


def _resolve_level(level_name: Optional[str]) -> int:
    if not level_name:
        return logging.INFO
    return _LEVEL_MAP.get(level_name.upper(), logging.INFO)


def get_logger(name: str) -> logging.Logger:
    level_name = os.getenv("APP_LOG_LEVEL", "INFO")
    level = _resolve_level(level_name)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler()
        fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        handler.setFormatter(logging.Formatter(fmt))
        logger.addHandler(handler)

    return logger
