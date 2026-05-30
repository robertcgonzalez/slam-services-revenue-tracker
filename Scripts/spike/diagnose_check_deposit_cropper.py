#!/usr/bin/env python3
"""
SLAM Services — Check + Deposit Slip Cropper Diagnostic (Step-by-Step Development Tool)

Purpose
-------
This script exists because the production check-cropping feature (used by both the
legacy subprocess path and the Local Enhanced OCR path) is badly failing on real
scanned bank statements, especially the hard test case:

    Data/Auto_Body_Center_Jan_26_Statement.pdf

That PDF contains 10 pages. Pages 5–10 are composite raster "imaging pages" (the
bank photographed the physical checks and deposit slips, assembled them with
register text into full-page images, and embedded those composites). There are
~49–53 check photographs + 7 deposit slips on page 5 alone. pdfplumber / PyMuPDF
cannot extract them as separate XObjects — the only reliable approach is high-DPI
raster + OpenCV contour finding (exactly what the production cropper does).

Current production problems (as of 2026-05):
- Three divergent copies of the cropper (standalone legacy, App/local_enhanced_ocr.py,
  Azure Function) with different constants, caps, and junk lists.
- The legacy standalone (still called by the app's default path) uses old tight
  geometry (MIN_HEIGHT=500 at 400 DPI, aspect 2.0–3.0) that drops real items.
- Deposit slips are treated as junk in the strict "check only" path, but users
  now need accurate crops of BOTH checks and deposit slips.
- Zero visualization: when it under- or over-crops you have no idea why a
  particular rectangle was rejected.

This script is the development harness to fix that. We build it **step-by-step**
in conversation:

  v1 (this file, current) : High-recall geometry + rich debug overlays + manifest.
                            No OCR. Fast. Shows the raw contour reality vs your
                            mental model of "what should be found".
  v2 (next)               : Add cheap image heuristics + light EasyOCR / keyword
                            classification → reliable "check" vs "deposit_slip"
                            vs "junk" labels on every candidate.
  v3+                     : Tuned final bands + classification that we then
                            port back into the three production copies and the
                            app's bank_statements.py integration.

Run from repo root (project venv active):

    # Full PDF, default 300 DPI, rich debug output
    python Scripts/spike/diagnose_check_deposit_cropper.py

    # Just the imaging pages (fast iteration)
    python Scripts/spike/diagnose_check_deposit_cropper.py --pages 5-10

    # Try different DPI or relax the bands live
    python Scripts/spike/diagnose_check_deposit_cropper.py --dpi 350 --min-aspect 1.6 --max-aspect 4.0

    # Specific output folder
    python Scripts/spike/diagnose_check_deposit_cropper.py --out-dir Scripts/spike/artifacts/crop_diagnosis_20260527

Requirements (already in the project):
    pdf2image, opencv-python(-headless), pillow, numpy

The script deliberately stays lightweight in v1 so you can run it repeatedly
while we tune. Later versions will add EasyOCR only on the candidate set (not
on every contour).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from pdf2image import convert_from_path
from PIL import Image, ImageDraw, ImageEnhance, ImageFont

# =============================================================================
# DEFAULT GEOMETRY (v1 — deliberately relaxed for high-recall diagnosis)
# These are STARTING values. We will tune them in conversation based on the
# debug overlays and manifest this script produces.
# =============================================================================

DEFAULT_DPI = 300

# Size bands (pixels at the chosen DPI). Relaxed vs production on purpose.
MIN_WIDTH = 90
MAX_WIDTH = 1600
MIN_HEIGHT = 200
MAX_HEIGHT = 1100

# Aspect ratio (width / height). Real checks are ~2.3–2.9; deposits vary.
MIN_ASPECT = 1.5
MAX_ASPECT = 4.0

# Dilation kernel + iterations (same primitive as production).
DILATE_KERNEL = (3, 3)
DILATE_ITERATIONS = 2

# Perceptual hash size for dedup (8x8 is what production uses).
HASH_SIZE = 8

# How many raw + enhanced crops to save per page in v1 (keeps output manageable).
MAX_CANDIDATES_SAVED_PER_PAGE = 30

# Color palette for debug overlays (RGB).
COLORS = {
    "kept": (0, 200, 0),           # bright green — passed size + aspect + dedup
    "aspect_fail": (255, 180, 0),  # orange — size ok, aspect rejected
    "size_fail": (220, 50, 50),    # red — size rejected
    "dedup": (0, 140, 255),        # blue — duplicate of an earlier candidate
    "deposit_hint": (180, 0, 200), # magenta — tall-ish or deposit-like aspect
}


@dataclass
class Candidate:
    page: int
    x: int
    y: int
    w: int
    h: int
    aspect: float
    area: int
    mean_brightness: float
    var_brightness: float
    hash: str
    kept: bool
    reason: str  # "kept", "size_fail", "aspect_fail", "dedup"


def simple_hash(img: np.ndarray, size: int = HASH_SIZE) -> str:
    """8x8 (or NxN) perceptual hash. Now uses np.array to avoid Pillow 14 deprecation."""
    pil = Image.fromarray(img).resize((size, size)).convert("L")
    arr = np.array(pil)
    pixels = arr.flatten().tolist()
    avg = float(np.mean(pixels)) if pixels else 0.0
    bits = "".join("1" if p > avg else "0" for p in pixels)
    return hashlib.md5(bits.encode()).hexdigest()


def enhanced_hash(crop_rgb: np.ndarray, size: int = 12) -> str:
    """Higher-resolution hash on a contrast-enhanced crop (much more stable for dedup)."""
    pil = Image.fromarray(crop_rgb)
    gray = pil.convert("L")
    # Same contrast boost the production cropper applies before OCR / hashing
    enh = ImageEnhance.Contrast(gray).enhance(3.0)
    small = enh.resize((size, size))
    arr = np.array(small)
    pixels = arr.flatten().tolist()
    avg = float(np.mean(pixels)) if pixels else 0.0
    bits = "".join("1" if p > avg else "0" for p in pixels)
    return hashlib.md5(bits.encode()).hexdigest()


def two_stage_dedup(
    geometry_passed: list[Candidate],
    page_img: Image.Image,
    hash_size: int = 12,
    min_center_dist: int = 45,
) -> list[Candidate]:
    """
    Second-stage dedup that is far less aggressive than the raw 8x8 hash.

    Stage A: perceptual hash on the contrast-enhanced crop (higher resolution).
    Stage B: spatial non-max suppression by center distance (exploits the regular grid).

    Returns a new list of Candidates marked kept=True with reason="kept_improved".
    All other input candidates are left untouched (we only promote a subset to final kept).
    """
    if not geometry_passed:
        return []

    img = np.array(page_img)

    # Build enhanced hashes for every geometry passer
    for c in geometry_passed:
        crop = img[c.y : c.y + c.h, c.x : c.x + c.w]
        c.hash = enhanced_hash(crop, size=hash_size)  # overwrite with better hash

    # Stage A — enhanced hash dedup (greedy, first-seen wins)
    seen: set[str] = set()
    hash_survivors: list[Candidate] = []
    for c in geometry_passed:
        if c.hash in seen:
            continue
        seen.add(c.hash)
        hash_survivors.append(c)

    # Stage B — spatial NMS by center distance (keep the largest / highest-variance when close)
    # Sort by descending variance * area (favors "busier" photo content)
    hash_survivors.sort(key=lambda c: c.var_brightness * c.area, reverse=True)

    final: list[Candidate] = []
    kept_centers: list[tuple[int, int]] = []

    def center(c: Candidate) -> tuple[int, int]:
        return (c.x + c.w // 2, c.y + c.h // 2)

    for c in hash_survivors:
        cx, cy = center(c)
        too_close = False
        for kx, ky in kept_centers:
            if abs(cx - kx) + abs(cy - ky) < min_center_dist:  # Manhattan is fast & good enough
                too_close = True
                break
        if too_close:
            continue
        kept_centers.append((cx, cy))
        # Mark as the improved-kept representative
        c.kept = True
        c.reason = "kept_improved"
        final.append(c)

    return final


def draw_text_safe(draw: ImageDraw.ImageDraw, pos: tuple[int, int], text: str, fill: tuple[int, int, int], font: ImageFont.ImageFont | None = None) -> None:
    try:
        draw.text(pos, text, fill=fill, font=font)
    except Exception:
        draw.text(pos, text, fill=fill)


def rasterize_pages(pdf_path: Path, dpi: int, first_page: int | None = None, last_page: int | None = None) -> list[Image.Image]:
    """Rasterize with pdf2image. Returns list of PIL RGB images."""
    print(f"[1/6] Rasterizing PDF at {dpi} DPI ... (this can take 30–120s for a 10-page scan)")
    kwargs: dict[str, Any] = {"dpi": dpi}
    if first_page is not None:
        kwargs["first_page"] = first_page
    if last_page is not None:
        kwargs["last_page"] = last_page
    pages = convert_from_path(str(pdf_path), **kwargs)
    print(f"      Rasterized {len(pages)} page(s)")
    return pages


def find_candidates_on_page(
    page_img: Image.Image,
    page_num: int,
    min_w: int,
    max_w: int,
    min_h: int,
    max_h: int,
    min_a: float,
    max_a: float,
) -> list[Candidate]:
    """Run the exact same 3-threshold contour pipeline used in production."""
    img = np.array(page_img)
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    thresholds = [
        cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 9, 3),
        cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 11, 2),
        cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY_INV)[1],
    ]

    kernel = np.ones(DILATE_KERNEL, np.uint8)
    seen_hashes: set[str] = set()
    cands: list[Candidate] = []

    for thresh in thresholds:
        dilated = cv2.dilate(thresh, kernel, iterations=DILATE_ITERATIONS)
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)

            # Size test
            if not (min_w < w < max_w and min_h < h < max_h):
                cands.append(
                    Candidate(
                        page=page_num,
                        x=x,
                        y=y,
                        w=w,
                        h=h,
                        aspect=round(w / h, 3) if h else 0.0,
                        area=w * h,
                        mean_brightness=float(np.mean(gray[y : y + h, x : x + w])) if h and w else 0.0,
                        var_brightness=float(np.var(gray[y : y + h, x : x + w])) if h and w else 0.0,
                        hash="",
                        kept=False,
                        reason="size_fail",
                    )
                )
                continue

            aspect = w / h if h else 0.0

            # Aspect test
            if not (min_a < aspect < max_a):
                cands.append(
                    Candidate(
                        page=page_num,
                        x=x,
                        y=y,
                        w=w,
                        h=h,
                        aspect=round(aspect, 3),
                        area=w * h,
                        mean_brightness=float(np.mean(gray[y : y + h, x : x + w])),
                        var_brightness=float(np.var(gray[y : y + h, x : x + w])),
                        hash="",
                        kept=False,
                        reason="aspect_fail",
                    )
                )
                continue

            # Passed geometry — compute hash for dedup
            crop = img[y : y + h, x : x + w]
            hsh = simple_hash(crop)

            if hsh in seen_hashes:
                cands.append(
                    Candidate(
                        page=page_num,
                        x=x,
                        y=y,
                        w=w,
                        h=h,
                        aspect=round(aspect, 3),
                        area=w * h,
                        mean_brightness=float(np.mean(gray[y : y + h, x : x + w])),
                        var_brightness=float(np.var(gray[y : y + h, x : x + w])),
                        hash=hsh,
                        kept=False,
                        reason="dedup",
                    )
                )
                continue

            seen_hashes.add(hsh)
            cands.append(
                Candidate(
                    page=page_num,
                    x=x,
                    y=y,
                    w=w,
                    h=h,
                    aspect=round(aspect, 3),
                    area=w * h,
                    mean_brightness=float(np.mean(gray[y : y + h, x : x + w])),
                    var_brightness=float(np.var(gray[y : y + h, x : x + w])),
                    hash=hsh,
                    kept=True,
                    reason="kept",
                )
            )

    return cands


def save_debug_overlay(
    page_img: Image.Image,
    cands: list[Candidate],
    out_path: Path,
    page_num: int,
    *,
    final_kept: list[Candidate] | None = None,
    min_center_dist: int = 0,
) -> None:
    """
    Draw colored rectangles on a full-page copy.

    When final_kept is supplied, the original cands are drawn first (showing the
    raw multi-threshold + old dedup behavior), then the final kept are over-drawn
    with thicker bright-green outlines so you can instantly see what the improved
    two-stage dedup kept.
    """
    overlay = page_img.copy()
    draw = ImageDraw.Draw(overlay)

    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font = None

    kept = 0
    for c in cands:
        x, y, w, h = c.x, c.y, c.w, c.h
        if c.reason == "kept":
            color = COLORS["kept"]
            kept += 1
        elif c.reason == "aspect_fail":
            color = COLORS["aspect_fail"]
        elif c.reason == "size_fail":
            color = COLORS["size_fail"]
        else:
            color = COLORS["dedup"]

        for t in range(3):
            draw.rectangle([x - t, y - t, x + w + t, y + h + t], outline=color)

        label = f"{c.w}x{c.h} a={c.aspect:.2f}"
        draw_text_safe(draw, (x + 2, y + 2), label, fill=color, font=font)

    # Over-draw the final kept from the improved dedup in thick bright green
    final_count = 0
    if final_kept:
        for c in final_kept:
            x, y, w, h = c.x, c.y, c.w, c.h
            # Very thick outline (5 px)
            for t in range(5):
                draw.rectangle([x - t, y - t, x + w + t, y + h + t], outline=COLORS["kept"])
            # Add a small "K" marker so they stand out even at a glance
            draw_text_safe(draw, (x + w - 18, y + 2), "K", fill=COLORS["kept"], font=font)
            final_count += 1

    # Header + legend
    if final_kept is not None:
        header = f"Page {page_num} — raw_kept={kept}  final_kept={final_count} (thick green = two-stage dedup)  min_dist={min_center_dist}"
    else:
        header = f"Page {page_num} — kept={kept}  (green=kept, orange=aspect, red=size, blue=dedup)"

    draw_text_safe(draw, (20, 10), header, fill=(255, 255, 255), font=font)

    legend_y = 40
    items = [("kept", COLORS["kept"]), ("aspect_fail", COLORS["aspect_fail"]), ("size_fail", COLORS["size_fail"]), ("dedup", COLORS["dedup"])]
    for name, col in items:
        draw.rectangle([20, legend_y, 40, legend_y + 16], fill=col)
        draw_text_safe(draw, (48, legend_y), name, fill=(255, 255, 255), font=font)
        legend_y += 22

    if final_kept is not None:
        draw.rectangle([20, legend_y, 40, legend_y + 16], fill=COLORS["kept"])
        draw_text_safe(draw, (48, legend_y), "final_kept (thick)", fill=(255, 255, 255), font=font)

    overlay.save(out_path)
    if final_kept is not None:
        print(f"      Saved overlay: {out_path.name} (raw kept={kept}, final kept after two-stage dedup={final_count})")
    else:
        print(f"      Saved overlay: {out_path.name} ({kept} kept)")


def save_candidate_crops(
    page_img: Image.Image,
    kept_cands: list[Candidate],
    raw_dir: Path,
    enh_dir: Path,
    page_num: int,
    max_save: int,
) -> list[Path]:
    """Save raw + contrast-enhanced crops for the first N kept candidates on the page."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    enh_dir.mkdir(parents=True, exist_ok=True)

    saved: list[Path] = []
    for i, c in enumerate(kept_cands[:max_save]):
        crop = page_img.crop((c.x, c.y, c.x + c.w, c.y + c.h))
        stem = f"P{page_num:02d}_C{i:03d}_w{c.w}_h{c.h}_a{c.aspect:.2f}"

        raw_path = raw_dir / f"{stem}.png"
        crop.save(raw_path)
        saved.append(raw_path)

        # Simple contrast boost (same spirit as production enhancement)
        from PIL import ImageEnhance

        gray = crop.convert("L")
        enhanced = ImageEnhance.Contrast(gray).enhance(3.2).convert("RGB")
        enh_path = enh_dir / f"{stem}_enh.png"
        enhanced.save(enh_path)

    return saved


def save_final_kept_crops(
    page_img: Image.Image,
    final_kept: list[Candidate],
    out_dir: Path,
    page_num: int,
) -> list[Path]:
    """Save the survivors after the improved two-stage dedup (raw + enhanced)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for i, c in enumerate(final_kept):
        crop = page_img.crop((c.x, c.y, c.x + c.w, c.y + c.h))
        stem = f"P{page_num:02d}_K{i:02d}_w{c.w}_h{c.h}_a{c.aspect:.2f}_final"

        raw_path = out_dir / f"{stem}.png"
        crop.save(raw_path)
        saved.append(raw_path)

        from PIL import ImageEnhance

        gray = crop.convert("L")
        enhanced = ImageEnhance.Contrast(gray).enhance(3.2).convert("RGB")
        enh_path = out_dir / f"{stem}_enh.png"
        enhanced.save(enh_path)

    return saved


def build_manifest(cands: list[Candidate], out_csv: Path) -> None:
    import pandas as pd

    rows = [asdict(c) for c in cands]
    df = pd.DataFrame(rows)
    df = df.sort_values(["page", "y", "x"])
    df.to_csv(out_csv, index=False)
    print(f"[4/6] Wrote manifest: {out_csv} ({len(df)} total contours)")


# FM-9: minimum final_kept count to treat a page as an "imaging" page (check/deposit grid).
_IMAGING_PAGE_MIN_FINAL_KEPT = 3


def detect_imaging_pages(
    pdf_path: Path,
    dpi: int,
    *,
    min_final_kept: int = _IMAGING_PAGE_MIN_FINAL_KEPT,
    min_w: int = MIN_WIDTH,
    max_w: int = MAX_WIDTH,
    min_h: int = MIN_HEIGHT,
    max_h: int = MAX_HEIGHT,
    min_a: float = MIN_ASPECT,
    max_a: float = MAX_ASPECT,
    hash_size: int = 12,
    min_center_dist: int = 45,
) -> dict[str, Any]:
    """
    Proof-of-concept: scan every PDF page and score imaging likelihood (FM-9).

    Heuristic: after relaxed geometry + two-stage dedup, pages with >= min_final_kept
    photo rectangles are imaging pages. Used to recommend SLAM_IMAGING_FIRST/LAST_PAGE
    instead of hard-coded 5-9 (missed QCR pages 5-8 when only 9-10 had crops).

    Limitations (as of 2026-05-27):
    - This is a PoC. The heuristic (final_kept >= 3) can be brittle across banks/scan quality.
    - Performs a full-PDF rasterization pass — not cheap for high-volume production use.
    - Intended to feed environment variables or per-statement configuration during G1 (B6).
    """
    print(f"[FM-9] Rasterizing full PDF at {dpi} DPI for imaging-page scan ...")
    pages = rasterize_pages(pdf_path, dpi)
    page_scores: list[dict[str, Any]] = []

    for idx, page_img in enumerate(pages):
        page_num = idx + 1
        cands = find_candidates_on_page(
            page_img,
            page_num,
            min_w,
            max_w,
            min_h,
            max_h,
            min_a,
            max_a,
        )
        geometry_passed = [c for c in cands if c.reason in ("kept", "dedup")]
        final_kept = two_stage_dedup(
            geometry_passed,
            page_img,
            hash_size=hash_size,
            min_center_dist=min_center_dist,
        )
        raw_kept = sum(1 for c in cands if c.kept)
        is_imaging = len(final_kept) >= min_final_kept
        page_scores.append(
            {
                "page": page_num,
                "raw_kept": raw_kept,
                "final_kept": len(final_kept),
                "is_imaging": is_imaging,
            }
        )
        print(
            f"      Page {page_num:2d}: final_kept={len(final_kept):2d} "
            f"(raw={raw_kept:3d}) -> {'IMAGING' if is_imaging else 'skip'}"
        )

    imaging_pages = [p["page"] for p in page_scores if p["is_imaging"]]
    recommended = None
    if imaging_pages:
        recommended = f"{imaging_pages[0]}-{imaging_pages[-1]}"

    return {
        "pdf": str(pdf_path),
        "dpi": dpi,
        "min_final_kept": min_final_kept,
        "imaging_pages": imaging_pages,
        "recommended_pages_arg": recommended,
        "per_page": page_scores,
    }


def print_summary(all_cands: list[Candidate], pages_processed: list[int]) -> None:
    kept = [c for c in all_cands if c.kept]
    per_page_kept: dict[int, int] = {}
    per_page_total: dict[int, int] = {}

    for c in all_cands:
        per_page_total[c.page] = per_page_total.get(c.page, 0) + 1
        if c.kept:
            per_page_kept[c.page] = per_page_kept.get(c.page, 0) + 1

    print("\n" + "=" * 72)
    print("CROP DIAGNOSTIC SUMMARY (v1 — geometry only)")
    print("=" * 72)
    print(f"Pages processed: {pages_processed}")
    print(f"Total contours evaluated: {len(all_cands)}")
    print(f"Kept after size+aspect+dedup: {len(kept)}")
    print()
    print("Per-page kept (after dedup):")
    for pg in sorted(per_page_kept):
        print(f"  Page {pg:2d}: {per_page_kept[pg]:3d} kept  (from {per_page_total.get(pg, 0)} raw contours)")
    print()
    print("Rejection breakdown:")
    for reason in ("size_fail", "aspect_fail", "dedup"):
        n = sum(1 for c in all_cands if c.reason == reason)
        print(f"  {reason:12s}: {n:4d}")
    print()
    print("Compare against ground truth for this PDF:")
    print("  - ~49 checks total (bank statement summary)")
    print("  - ~53 photo rectangles + 7 deposit slips visible on pages 5-10 (user count)")
    print("  - Page 5 alone has the 7 deposit slips + many checks")
    print()
    print("Next steps (we will do these together):")
    print("  1. Open the debug_overlays/*.png and visually inspect why real items were missed.")
    print("  2. Look at the manifest.csv — sort by page + y to see spatial layout.")
    print("  3. Decide: relax/tighten bands? Add brightness/var filters? Edge density?")
    print("  4. Add classification (check vs deposit vs junk) in v2.")
    print("=" * 72 + "\n")


def main() -> int:
    p = argparse.ArgumentParser(
        description="Step-by-step diagnostic for check + deposit slip cropping on the hard test PDF."
    )
    p.add_argument(
        "--pdf",
        type=Path,
        default=Path("Data/Auto_Body_Center_Jan_26_Statement.pdf"),
        help="Path to the target bank statement PDF (default: the known hard test case).",
    )
    p.add_argument("--dpi", type=int, default=DEFAULT_DPI, help=f"Raster DPI (default {DEFAULT_DPI}). 250-350 is usually best.")
    p.add_argument(
        "--pages",
        type=str,
        default="5-9",
        help='Limit to specific pages (default "5-9" now that page 10 is known to be the reconciliation sheet with no checks/deposits). Use "5-10" or "all" for full runs.',
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory (default: Scripts/spike/artifacts/crop_diagnosis_YYYYMMDDTHHMMSSZ).",
    )
    p.add_argument("--min-width", type=int, default=MIN_WIDTH)
    p.add_argument("--max-width", type=int, default=MAX_WIDTH)
    p.add_argument("--min-height", type=int, default=MIN_HEIGHT)
    p.add_argument("--max-height", type=int, default=MAX_HEIGHT)
    p.add_argument("--min-aspect", type=float, default=MIN_ASPECT)
    p.add_argument("--max-aspect", type=float, default=MAX_ASPECT)
    p.add_argument(
        "--max-save-per-page",
        type=int,
        default=MAX_CANDIDATES_SAVED_PER_PAGE,
        help="How many kept crops (raw + enhanced) to write per page.",
    )
    p.add_argument(
        "--hash-size",
        type=int,
        default=12,
        help="Perceptual hash size for improved dedup stage (higher = more discrimination, slower). Default 12 for diagnosis (production uses 8).",
    )
    p.add_argument(
        "--min-center-dist",
        type=int,
        default=45,
        help="Minimum center-to-center distance (pixels at this DPI) for spatial NMS in the second dedup stage. 40-60 is good for the 2-column grid on this PDF.",
    )
    p.add_argument(
        "--detect-imaging-pages",
        action="store_true",
        help="FM-9 PoC (experimental): scan all pages, write imaging_pages.json with recommended range. "
             "Not production hardened; heuristic may need tuning per bank layout.",
    )
    p.add_argument(
        "--imaging-min-final-kept",
        type=int,
        default=_IMAGING_PAGE_MIN_FINAL_KEPT,
        help="Pages with at least this many final_kept crops count as imaging pages (default 3).",
    )
    args = p.parse_args()

    pdf_path = args.pdf.resolve()
    if not pdf_path.is_file():
        print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        return 1

    if args.detect_imaging_pages:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_dir = args.out_dir or (Path("Scripts/spike/artifacts") / f"imaging_detect_{ts}")
        out_dir.mkdir(parents=True, exist_ok=True)
        result = detect_imaging_pages(
            pdf_path,
            args.dpi,
            min_final_kept=args.imaging_min_final_kept,
            min_w=args.min_width,
            max_w=args.max_width,
            min_h=args.min_height,
            max_h=args.max_height,
            min_a=args.min_aspect,
            max_a=args.max_aspect,
            hash_size=args.hash_size,
            min_center_dist=args.min_center_dist,
        )
        out_json = out_dir / "imaging_pages.json"
        out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print("\n" + "=" * 72)
        print("IMAGING PAGE DETECTION (FM-9 PoC)")
        print("=" * 72)
        print(f"Imaging pages : {result['imaging_pages']}")
        print(f"Recommended   : --pages {result['recommended_pages_arg'] or '(none)'}")
        print(f"Wrote         : {out_json}")
        print("=" * 72 + "\n")
        return 0

    # Parse --pages
    first_page = last_page = None
    page_list: list[int] | None = None
    if args.pages:
        s = args.pages.strip()
        if "-" in s:
            a, b = s.split("-", 1)
            first_page = int(a)
            last_page = int(b)
        else:
            page_list = [int(x) for x in s.split(",")]

    # Output layout
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.out_dir or (Path("Scripts/spike/artifacts") / f"crop_diagnosis_{ts}")
    out_dir.mkdir(parents=True, exist_ok=True)
    overlays_dir = out_dir / "debug_overlays"
    raw_dir = out_dir / "candidates_raw"
    enh_dir = out_dir / "candidates_enhanced"
    overlays_dir.mkdir(exist_ok=True)
    raw_dir.mkdir(exist_ok=True)
    enh_dir.mkdir(exist_ok=True)

    print(f"PDF           : {pdf_path}")
    print(f"DPI           : {args.dpi}")
    print(f"Geometry      : w=[{args.min_width},{args.max_width}] h=[{args.min_height},{args.max_height}] aspect=[{args.min_aspect},{args.max_aspect}]")
    print(f"Output dir    : {out_dir}")
    print()

    # 1. Rasterize
    pages = rasterize_pages(pdf_path, args.dpi, first_page=first_page, last_page=last_page)
    if page_list:
        # Filter after raster (pdf2image first/last is 1-based inclusive)
        # For simplicity we just keep the ones the user asked for.
        # (If user gave 5,6,7 we still rasterized 1-7; we can trim.)
        pass  # For v1 we accept the first/last filter; page_list is documented for future.

    pages_processed = list(range(1, len(pages) + 1))
    if first_page:
        pages_processed = list(range(first_page, first_page + len(pages)))

    # 2. Find candidates on every page
    print("[2/6] Running 3-threshold contour pipeline on each page ...")
    all_cands: list[Candidate] = []

    # New dirs for the improved dedup output
    final_kept_dir = out_dir / "final_kept"
    final_kept_dir.mkdir(exist_ok=True)

    for idx, page_img in enumerate(pages):
        pdf_page_num = pages_processed[idx]
        cands = find_candidates_on_page(
            page_img,
            pdf_page_num,
            args.min_width,
            args.max_width,
            args.min_height,
            args.max_height,
            args.min_aspect,
            args.max_aspect,
        )
        all_cands.extend(cands)

        # Old "kept" count (what the original 8x8 raw-hash dedup produced)
        kept_on_page = [c for c in cands if c.kept]
        print(f"      Page {pdf_page_num}: {len(kept_on_page)} kept after geometry+dedup (from {len(cands)} raw contours)")

        # NEW: Two-stage improved dedup on the geometry passers
        geometry_passed = [c for c in cands if c.reason in ("kept", "dedup")]  # anything that passed size+aspect
        final_kept = two_stage_dedup(
            geometry_passed,
            page_img,
            hash_size=args.hash_size,
            min_center_dist=args.min_center_dist,
        )
        print(f"             -> after two-stage dedup (hash {args.hash_size}x{args.hash_size} + center_dist {args.min_center_dist}): {len(final_kept)} final unique kept")

        # 3. Debug overlay — now shows both the raw behavior (blue/green) and the improved final kept (thick green + K)
        overlay_path = overlays_dir / f"page_{pdf_page_num:02d}_debug.png"
        save_debug_overlay(
            page_img,
            cands,
            overlay_path,
            pdf_page_num,
            final_kept=final_kept,
            min_center_dist=args.min_center_dist,
        )

        # 4. Save raw/enhanced crops for the old "kept" set (for comparison)
        if kept_on_page:
            save_candidate_crops(page_img, kept_on_page, raw_dir, enh_dir, pdf_page_num, args.max_save_per_page)

        # 5. Save the final survivors after improved dedup (these are the ones we will classify in v2)
        if final_kept:
            save_final_kept_crops(page_img, final_kept, final_kept_dir, pdf_page_num)

    # 6. Manifest + summary
    print("[3/6] Building manifest ...")
    manifest_path = out_dir / "manifest.csv"
    build_manifest(all_cands, manifest_path)

    # Write a small json summary for later scripts to consume
    summary = {
        "pdf": str(pdf_path),
        "dpi": args.dpi,
        "geometry": {
            "min_w": args.min_width,
            "max_w": args.max_width,
            "min_h": args.min_height,
            "max_h": args.max_height,
            "min_aspect": args.min_aspect,
            "max_aspect": args.max_aspect,
        },
        "hash_size": args.hash_size,
        "min_center_dist": args.min_center_dist,
        "pages_processed": pages_processed,
        "total_contours": len(all_cands),
        "kept_raw": len([c for c in all_cands if c.kept]),
        "timestamp_utc": ts,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    print_summary(all_cands, pages_processed)

    print(f"Done. Open the overlays in {overlays_dir} (now with thick green final kept + 'K' markers) and the manifest.")
    print(f"Final unique kept crops after improved dedup are in: {final_kept_dir}")
    print("Reply with what you see in the new green boxes and we will iterate (v2 = classification of the final kept set).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
