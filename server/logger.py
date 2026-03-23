import logging
import sys
from typing import Final

_DEFAULT_FORMAT: Final = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    numeric = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(numeric)
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(numeric)
    handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT))
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
