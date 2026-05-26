"""Dump EasyOCR-extracted lines for the Auto Body Center Jan-26 statement.

Skips the full pipeline so we can iterate on `_parse_lines_to_transactions`
without re-running EasyOCR repeatedly: caches the extracted lines (per DPI)
to ``Scripts/_easyocr_cache_<dpi>.json`` so subsequent runs are seconds.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "App"))


def dump_lines(pdf_bytes: bytes, dpi: int, *, cache: Path) -> list[list[str]]:
    if cache.is_file():
        data = json.loads(cache.read_text(encoding="utf-8"))
        if data.get("dpi") == dpi:
            print(f"[cache] Reusing EasyOCR cache for DPI={dpi}: {cache.name}")
            return [list(pg) for pg in data.get("pages", [])]

    import easyocr
    import numpy as np
    from pdf2image import convert_from_bytes

    pages = convert_from_bytes(pdf_bytes, dpi=dpi)
    reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    print(f"[ocr] EasyOCR running on {len(pages)} page(s) at DPI={dpi}...")

    import local_enhanced_ocr  # noqa: PLC0415

    out: list[list[str]] = []
    for i, page in enumerate(pages):
        img = np.array(page)
        dets = reader.readtext(img, detail=1, paragraph=False)
        lines = local_enhanced_ocr._easyocr_to_lines(dets)
        out.append(lines)
        print(f"  page {i+1}: {len(dets)} tokens -> {len(lines)} lines")

    cache.write_text(
        json.dumps({"dpi": dpi, "pages": out}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"[cache] wrote {cache.name}")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--page", type=int, default=0, help="1-based page to print fully (0=all)")
    args = parser.parse_args(argv)

    pdf_path = REPO_ROOT / "Data" / "Auto_Body_Center_Jan_26_Statement.pdf"
    if not pdf_path.is_file():
        print(f"PDF not found: {pdf_path}")
        return 1

    pdf_bytes = pdf_path.read_bytes()
    print(f"Loaded {pdf_path.name} ({len(pdf_bytes) / 1024:.1f} KiB)")

    cache_path = Path(__file__).resolve().parent / f"_easyocr_cache_{args.dpi}.json"
    if args.force and cache_path.is_file():
        cache_path.unlink()
    pages = dump_lines(pdf_bytes, args.dpi, cache=cache_path)

    print(f"\n=== EXTRACTED LINES (DPI={args.dpi}) ===")
    for pi, lines in enumerate(pages):
        if args.page and (pi + 1) != args.page:
            continue
        print(f"\n--- PAGE {pi+1} ({len(lines)} lines) ---")
        for li, line in enumerate(lines):
            print(f"  [{pi+1:02d}.{li:03d}] {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
