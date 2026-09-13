# SPDX-License-Identifier: GPL-3.0-or-later
#
# Logging setup for the Proxmox display monitor.
#
# The vendored display driver only defines a named logger (see display_driver/log.py).
# This module attaches handlers to that same logger so both the application and the
# driver log through a single, consistently configured logger.

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

LOGGER_NAME = "proxmox-status-screen"

logger = logging.getLogger(LOGGER_NAME)

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(log_file: Optional[str] = None, console_level: str = "INFO") -> logging.Logger:
    """Configure the shared logger.

    Console output is filtered at ``console_level``; the optional rotating file
    handler always captures DEBUG so issues can be diagnosed after the fact.
    Safe to call multiple times (existing handlers are replaced).
    """
    logger.setLevel(logging.DEBUG)

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.setLevel(getattr(logging, str(console_level).upper(), logging.INFO))
    logger.addHandler(console)

    if log_file:
        path = Path(log_file)
        if path.parent and str(path.parent) not in ("", "."):
            path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3)
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)

    return logger
