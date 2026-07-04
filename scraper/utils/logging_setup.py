"""Central logging configuration.

Every run writes a dedicated log file ``logs/run_YYYYMMDD_HHMMSS.log`` at
DEBUG level while the console shows the configured level (INFO by default).
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(log_dir: Path, console_level: str = "INFO") -> Path:
    """Configure root logging for a run and return the log-file path."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"run_{datetime.now():%Y%m%d_%H%M%S}.log"

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    # Reconfiguring in tests / repeated calls: drop stale handlers.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, console_level, logging.INFO))
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(console_handler)

    # curl_cffi / urllib3 are chatty at DEBUG
    logging.getLogger("curl_cffi").setLevel(logging.INFO)
    return log_file
