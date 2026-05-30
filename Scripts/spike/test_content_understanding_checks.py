#!/usr/bin/env python3
"""Smoke test: Content Understanding prebuilt-check.us on imaging pages.

Requires repo-root `.env` with CONTENTUNDERSTANDING_ENDPOINT + CONTENTUNDERSTANDING_KEY
(Foundry *.services.ai.azure.com) and a sample PDF path.

Usage (from repo root, .venv active):
  python Scripts/spike/test_content_understanding_checks.py path/to/statement.pdf
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "App"))

from dotenv import load_dotenv

load_dotenv(REPO / ".env")

from azure_content_understanding import (  # noqa: E402
    analyze_checks_on_imaging_pages,
    content_understanding_configured,
    content_understanding_status,
)
from azure_document_intelligence import checks_to_transaction_rows  # noqa: E402


def main() -> int:
    status = content_understanding_status()
    if not content_understanding_configured():
        print("Content Understanding not configured:")
        print(status.get("hint"))
        return 1

    if len(sys.argv) < 2:
        print("Usage: python Scripts/spike/test_content_understanding_checks.py <statement.pdf>")
        return 2

    pdf_path = Path(sys.argv[1])
    if not pdf_path.is_file():
        print(f"File not found: {pdf_path}")
        return 2

    pdf_bytes = pdf_path.read_bytes()
    checks, meta = analyze_checks_on_imaging_pages(pdf_bytes)
    txns = checks_to_transaction_rows(checks)

    print(f"Endpoint: {status.get('endpoint')}")
    print(f"Pages analyzed: {meta.get('pages_analyzed')}")
    print(f"Checks: {len(checks)}  ->  transaction rows: {len(txns)}")
    for i, c in enumerate(checks[:10], 1):
        print(
            f"  {i}. page={c.get('page')} #{c.get('check_number')} "
            f"pay_to={c.get('pay_to')!r} amount={c.get('amount')}"
        )
    if len(checks) > 10:
        print(f"  ... and {len(checks) - 10} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
