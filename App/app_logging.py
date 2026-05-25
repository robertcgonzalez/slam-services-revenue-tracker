"""Structured logging for Revenue Tracker — Azure log stream + local dev."""

from __future__ import annotations

import logging
import os
import sys


def setup_app_logging() -> logging.Logger:
    """Configure slam_app logger once per process."""
    logger = logging.getLogger("slam_app")
    if logger.handlers:
        return logger

    level_name = os.environ.get("SLAM_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] slam_app: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def log_event(logger: logging.Logger, event: str, **fields: object) -> None:
    parts = [f"{k}={v!r}" for k, v in fields.items() if v is not None]
    detail = " ".join(parts)
    logger.info("%s%s", event, f" ({detail})" if detail else "")
