#!/usr/bin/env python3
"""Offline smoke test for Azure DI page pre-filter (no Azure call).

Usage (from repo root):
  python Scripts/spike/test_azure_di_prefilter.py path/to/statement.pdf
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "App"))

from azure_di_utils import (  # noqa: E402
    count_original_pages,
    filter_pdf_for_azure,
    format_filter_user_message,
    summarize_page_filter,
)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    pdf_path = Path(sys.argv[1])
    if not pdf_path.is_file():
        print(f"File not found: {pdf_path}")
        return 1

    pdf_bytes = pdf_path.read_bytes()
    _pdf, pages_str, decisions = filter_pdf_for_azure(pdf_bytes)
    summary = summarize_page_filter(decisions, pages_str)
    print(format_filter_user_message(summary))
    print(f"Original pages (count): {count_original_pages(pdf_bytes)}")
    print(f"Pages string for Azure: {pages_str or '(none)'}")
    print("\nPer-page decisions:")
    for d in decisions:
        status = "KEEP" if d.kept else "SKIP"
        print(f"  Page {d.page_number + 1:>3}: {status} — {d.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
