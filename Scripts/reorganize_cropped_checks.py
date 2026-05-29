#!/usr/bin/env python3
"""
Standalone helper: Re-organize an existing cropped checks folder.

Usage:
    python Scripts/reorganize_cropped_checks.py --crop-dir "Scripts/cropped_checks_final_dynamic"

It will:
- Scan for PNG files
- Apply the same aspect-ratio heuristic used by the main cropper (or load sidecar JSON if present)
- Create `checks/` and `deposits/` subfolders
- Move files accordingly

This is useful for re-processing old runs after code changes, or when you only have the PNGs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def classify_crop(aspect: float | None) -> str:
    """Simple heuristic matching the one in check_cropper_v5.py."""
    if aspect is None:
        return "unknown"
    return "deposit" if aspect < 2.1 else "check"


def reorganize_crops(crop_dir: Path) -> None:
    crop_dir = crop_dir.resolve()
    if not crop_dir.is_dir():
        print(f"ERROR: Not a directory: {crop_dir}", file=sys.stderr)
        sys.exit(1)

    checks_dir = crop_dir / "checks"
    deposits_dir = crop_dir / "deposits"
    checks_dir.mkdir(exist_ok=True)
    deposits_dir.mkdir(exist_ok=True)

    moved_checks = 0
    moved_deposits = 0
    skipped = 0

    pngs = sorted(crop_dir.glob("check_*.png"))

    for png_path in pngs:
        stem = png_path.stem  # e.g. "check_P05C03"
        json_path = crop_dir / f"{stem}.json"

        aspect = None
        is_deposit = False

        if json_path.exists():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                aspect = data.get("aspect_ratio")
                is_deposit = bool(data.get("likely_deposit_slip"))
            except Exception:
                pass

        if aspect is None:
            # Fallback: try to infer from filename or just leave it
            skipped += 1
            continue

        is_deposit = classify_crop(aspect) == "deposit"

        target_dir = deposits_dir if is_deposit else checks_dir
        target = target_dir / png_path.name

        if target.exists():
            target.unlink()

        try:
            png_path.rename(target)
            if is_deposit:
                moved_deposits += 1
            else:
                moved_checks += 1
        except Exception as exc:
            print(f"  Failed to move {png_path.name}: {exc}", file=sys.stderr)

    print(f"Done.")
    print(f"  Moved {moved_checks} checks → {checks_dir}")
    print(f"  Moved {moved_deposits} deposit slips → {deposits_dir}")
    if skipped:
        print(f"  Skipped {skipped} files (no aspect metadata available)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-organize cropped check/deposit images into checks/ and deposits/ subfolders.")
    parser.add_argument(
        "--crop-dir",
        type=Path,
        required=True,
        help="Path to the folder containing check_*.png files (e.g. Scripts/cropped_checks_final_dynamic)",
    )
    args = parser.parse_args()

    reorganize_crops(args.crop_dir)


if __name__ == "__main__":
    main()
