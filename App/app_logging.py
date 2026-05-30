"""Structured logging for Revenue Tracker — Azure log stream + local dev."""

from __future__ import annotations

import json
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


# Gate A3 autonomous smoke assessment — canonical test PDFs only (or SLAM_SMOKE_MODE).
SMOKE_CANONICAL_PDFS: frozenset[str] = frozenset(
    {
        "HCC 2026-04.pdf",
        "Auto_Body_Center_Jan_26_Statement.pdf",
    }
)


def is_smoke_assessment_pdf(filename: str) -> bool:
    """True for Gate A3 canonical PDFs or when SLAM_SMOKE_MODE is enabled."""
    name = (filename or "").strip()
    if name in SMOKE_CANONICAL_PDFS:
        return True
    mode = os.environ.get("SLAM_SMOKE_MODE", "").strip().lower()
    return mode in ("true", "1", "yes", "on")


def log_smoke_evidence(logger: logging.Logger, pdf_name: str, metrics: dict) -> None:
    """Emit one machine-parseable line for Collect-GateA3Evidence.ps1 / Kudu harvest."""
    payload = json.dumps(metrics, separators=(",", ":"), default=str)
    logger.info('SMOKE_EVIDENCE pdf="%s" json=%s', pdf_name, payload)
