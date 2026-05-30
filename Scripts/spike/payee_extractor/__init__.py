"""Spike compatibility shim — re-exports ``App/payee_extractor`` when repo root is on sys.path."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from App.payee_extractor import *  # noqa: E402, F403
from App.payee_extractor import __all__  # noqa: E402, F401
