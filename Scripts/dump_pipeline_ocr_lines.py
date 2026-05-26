"""Dump live `run_pipeline`-style EasyOCR lines for the regression test.

The regression test at ``Scripts/test_local_ocr_regression.py`` covers
two distinct cache snapshots:

1. ``Scripts/_easyocr_cache_200.json`` — per-page line lists captured via
   ``Scripts/dump_easyocr_lines.py``.
2. ``Scripts/_pipeline_lines.json`` — flat line list captured *exactly*
   the way the live ``run_pipeline`` path produces it (full PDF →
   ``_ocr_extract_lines(pdf_bytes)``). Subtle differences between the
   two cache shapes appear because the live pipeline rasterizes the
   full multi-page PDF as one batch (and EasyOCR's bucketing can drop
   a date or a check number into its own y-row) while the per-page
   helper rebuilds buckets one page at a time. The strict parser plus
   ``_fuse_split_date_lines`` + ``_splice_orphan_check_numbers`` must
   handle both — this dump captures snapshot (2) so the regression
   test can exercise the live-style input without spending 8-10
   minutes on EasyOCR each run.

Run whenever the cropper, EasyOCR engine, or pdf2image rasterization
changes meaningfully.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "App"))

import local_enhanced_ocr as leo  # noqa: E402  (path injection above)


def main() -> int:
    pdf_path = REPO_ROOT / "Data" / "Auto_Body_Center_Jan_26_Statement.pdf"
    if not pdf_path.is_file():
        print(f"PDF not found: {pdf_path}")
        return 1

    pdf_bytes = pdf_path.read_bytes()
    print(f"OCR_DPI_TEXT = {leo.OCR_DPI_TEXT}")
    print(f"OCR_MAX_PAGES_RASTER = {leo.OCR_MAX_PAGES_RASTER}")
    print(f"_RUNTIME_IS_CODESPACES = {leo._RUNTIME_IS_CODESPACES}")

    lines, _logs = leo._ocr_extract_lines(pdf_bytes)
    print(f"\nLINES: {len(lines)}")

    out = REPO_ROOT / "Scripts" / "_pipeline_lines.json"
    out.write_text(
        json.dumps({"lines": lines}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"Wrote pipeline lines to {out.name}")

    txns = leo._parse_ocr_lines_to_transactions(lines, 2026)
    print(f"\nParser on pipeline lines: {len(txns)} txn(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
