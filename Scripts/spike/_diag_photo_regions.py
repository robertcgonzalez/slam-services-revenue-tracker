#!/usr/bin/env python3
"""
Temporary high-recall diagnostic for the cropper gap (May 2026).

Purpose
-------
Count *every* plausible rectangular photo-like region on the composite imaging
pages (5+) of the hard test PDF, using only geometry (size + aspect) + dedup.
No keyword / EasyOCR filter at all. This gives the objective upper bound of
what the current OpenCV contour primitive can ever detect.

Run from repo root:
    python Scripts/spike/_diag_photo_regions.py

Compare the output to:
- pdfplumber result (1 large composite image per imaging page)
- Phase 0 baseline (40 crops with cap=40 + strict keywords)
- Bank's statement summary (49 checks)
- User visual count (53 images + 7 deposit slips on page 5+)
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import cv2
import numpy as np
from pdf2image import convert_from_path
from PIL import Image

PDF = Path("Data/Auto_Body_Center_Jan_26_Statement.pdf")
DPI = 250

# Slightly relaxed geometry vs production (to catch deposits and edge-case checks)
MIN_W, MAX_W = 80, 1600
MIN_H, MAX_H = 180, 1200
MIN_A, MAX_A = 1.4, 3.8


def simple_hash(arr: np.ndarray) -> str:
    pil = Image.fromarray(arr).resize((8, 8)).convert("L")
    px = list(pil.getdata())
    avg = sum(px) / len(px) if px else 0
    bits = "".join("1" if p > avg else "0" for p in px)
    return hashlib.md5(bits.encode()).hexdigest()


def main() -> int:
    if not PDF.is_file():
        print(f"ERROR: PDF not found: {PDF}", file=sys.stderr)
        return 1

    print(f"Rasterizing imaging pages (5-10) at {DPI} DPI ... (30-90s)")
    pages = convert_from_path(str(PDF), dpi=DPI, first_page=5, last_page=10)
    print(f"Rasterized {len(pages)} pages (PDF pages 5-{4+len(pages)})")

    all_regions: list[dict] = []
    seen: set[str] = set()
    per_page: dict[int, int] = {}

    for page_offset, page in enumerate(pages):
        pdf_page_num = 5 + page_offset
        img = np.array(page)
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

        thresholds = [
            cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 9, 3),
            cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 11, 2),
            cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY_INV)[1],
        ]

        page_hits = 0
        for thresh in thresholds:
            kernel = np.ones((3, 3), np.uint8)
            dilated = cv2.dilate(thresh, kernel, iterations=2)
            contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                if not (MIN_W < w < MAX_W and MIN_H < h < MAX_H):
                    continue
                aspect = w / h if h else 0.0
                if not (MIN_A < aspect < MAX_A):
                    continue
                crop = img[y : y + h, x : x + w]
                hsh = simple_hash(crop)
                if hsh in seen:
                    continue
                seen.add(hsh)
                all_regions.append(
                    {
                        "page": pdf_page_num,
                        "w": int(w),
                        "h": int(h),
                        "aspect": round(aspect, 3),
                    }
                )
                page_hits += 1

        per_page[pdf_page_num] = page_hits

    print()
    print("=" * 70)
    print("HIGH-RECALL PHOTO REGION COUNT (geometry + dedup ONLY — no keywords)")
    print("=" * 70)
    print(f"Total unique photo-like rectangles found on pages 5-10: {len(all_regions)}")
    print()
    print("Per-page counts (after dedup):")
    for pg in sorted(per_page):
        print(f"  Page {pg}: {per_page[pg]}")
    print()
    print("Sample regions (first 3 per page):")
    for pg in sorted(per_page):
        on_pg = [r for r in all_regions if r["page"] == pg][:3]
        for r in on_pg:
            print(f"  P{pg}  w={r['w']:4d}  h={r['h']:4d}  aspect={r['aspect']:.2f}")
    print()
    print("Compare to:")
    print("  - pdfplumber: 1 large composite image per imaging page (6 total)")
    print("  - Phase 0 baseline (cap=40 + strict keywords): 40 crops")
    print("  - Bank statement summary: 49 checks")
    print("  - User visual count: 53 images + 7 deposit slips on page 5+")
    print()
    print("This number is the practical upper bound for the current contour primitive.")
    print("If it is still well below 53+7, the geometry bands or DPI need further tuning.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
