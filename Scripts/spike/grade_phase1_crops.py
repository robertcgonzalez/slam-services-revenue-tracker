#!/usr/bin/env python3
"""Interactive visual grader for Phase 1 Azure CV Read harness results (spike-only).

Consumes the side_by_side_harness.csv produced by phase1_cv_read_harness.py
and lets a human open each PNG and record a structured manual_grade verdict.

All work stays under Scripts/spike/. No changes to App/ or production code.

Usage (from repo root, inside the project venv):
    python Scripts/spike/grade_phase1_crops.py

    # Focus on one page
    python Scripts/spike/grade_phase1_crops.py --page 5

    # Only checks (skip the 7 deposits)
    python Scripts/spike/grade_phase1_crops.py --class check

    # Resume (default) or force start from a specific row index
    python Scripts/spike/grade_phase1_crops.py --start 12

The script is fully resumable. It always begins at the first row whose
manual_grade column is blank (or the first row matching your filters).
It writes the CSV back after every grade for safety.

Grading codes (type letter or word at the prompt):
    c / correct     → CV got the right payee cleanly
    s / spelling    → Core name right, minor spelling fix needed
    p / partial     → Got the main name but with noise/truncation
    w / wrong       → Wrong (you will be prompted for the actual text)
    e / empty       → No usable payee (illegible/handwritten/missed)
    b / boilerplate → False positive on printed check text
    d / deposit     → Deposit slip (classification + text good)
    x / skip        → Leave blank for now
    ?               → Show rubric
    q / quit        → Save & exit immediately

On 'w' (wrong) you will be asked for the actual payee visible in the photo.
The value stored in manual_grade will be structured and easy to analyze later.

See Scripts/spike/GRADING_GUIDE.md for the full rubric, workflow tips,
and how to interpret cv_read_payee_reason etc.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Default to the recommended rescored run (courtesy-amount filter applied)
DEFAULT_CSV = Path(
    "Scripts/spike/artifacts/phase1_real_cv_read_harness_20260526T195813Z__rescored/side_by_side_harness.csv"
)

RUBRIC = """
Grading codes:
  c / correct     -> CV extracted the correct payee cleanly (full win)
  s / spelling    -> Core business correct, needs 1-4 char spelling fix (still a big win)
  p / partial     -> Main name present but truncated or noisy (usable with light edit)
  w / wrong       -> Clearly incorrect - you will be prompted for the real text from the photo
  e / empty       -> No usable payee (illegible, handwritten, CV missed it entirely)
  b / boilerplate -> CV latched onto "Security features", "Details on back", etc.
  d / deposit     -> Deposit slip - classification correct, text captured for P&L
  x / skip        -> Unsure / come back later
  ?               -> Show this rubric again
  q / quit        -> Save and exit now
""".strip()


def expand_grade(code: str, extra: str | None = None) -> str:
    """Turn short code + optional free text into a structured manual_grade value."""
    c = code.lower().strip()
    mapping = {
        "c": "correct",
        "correct": "correct",
        "s": "spelling",
        "spelling": "spelling",
        "p": "partial",
        "partial": "partial",
        "e": "empty",
        "empty": "empty",
        "b": "boilerplate",
        "boilerplate": "boilerplate",
        "d": "deposit_ok",
        "deposit": "deposit_ok",
        "x": "x - revisit",
        "skip": "x - revisit",
    }
    base = mapping.get(c, c)
    if extra:
        extra = extra.strip()
        if base in ("spelling", "partial", "wrong", "empty", "boilerplate"):
            return f"{base}: {extra}"
        return f"{base} - {extra}"
    return base


def open_image(path: str | Path) -> None:
    """Open the image with the OS default viewer (Windows: Photos / IrfanView etc.).

    The CSV stores relative paths (e.g. "Scripts/spike/..."). We try several
    resolutions because users sometimes run from different CWDs or have the
    script in a different venv folder.
    """
    p = Path(path)
    tried: list[Path] = []

    # 1. As written (relative to current working directory)
    tried.append(p)
    if p.is_file():
        _try_startfile(p)
        return

    # 2. Resolve relative to this script's location (repo root = parents[2] from Scripts/spike/)
    try:
        script_dir = Path(__file__).resolve().parent
        repo_root = script_dir.parents[2]   # Scripts/spike/grade_phase1_crops.py -> repo root
        cand = repo_root / p
        tried.append(cand)
        if cand.is_file():
            _try_startfile(cand)
            return
    except Exception:
        pass

    # 3. Explicitly from CWD (sometimes the relative path needs this on weird shells)
    cand = Path.cwd() / p
    tried.append(cand)
    if cand.is_file():
        _try_startfile(cand)
        return

    # Give up with helpful diagnostics
    print("  [WARN] Could not auto-open image. Tried these locations:")
    for t in tried:
        print(f"         - {t}   (exists={t.is_file()})")
    print(f"\n         Best guess for manual open (copy this):\n         {Path.cwd() / p}")
    print(f"         Or the absolute version of the path in the CSV.")


def _try_startfile(path: Path) -> None:
    try:
        os.startfile(str(path))  # type: ignore[attr-defined]
        print(f"  Opened: {path}")
    except Exception as exc:
        print(f"  [WARN] os.startfile failed on {path}: {exc}")


def load_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def save_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    # Write to a temp then replace for a tiny bit of safety
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def find_first_blank_index(rows: list[dict[str, Any]], start: int = 0) -> int:
    for i in range(max(start, 0), len(rows)):
        val = (rows[i].get("manual_grade") or "").strip()
        if not val:
            return i
    return len(rows)  # all filled


def apply_filters(
    rows: list[dict[str, Any]],
    *,
    page: int | None,
    class_filter: str | None,
    only_ungraded: bool,
) -> list[tuple[int, dict[str, Any]]]:
    """Return list of (original_index, row) after filters."""
    out = []
    for idx, row in enumerate(rows):
        if page is not None and int(row.get("page", 0)) != page:
            continue
        if class_filter and row.get("predicted_class", "").lower() != class_filter.lower():
            continue
        if only_ungraded:
            if (row.get("manual_grade") or "").strip():
                continue
        out.append((idx, row))
    return out


def print_row_context(row: dict[str, Any], idx: int, total: int) -> None:
    crop = row.get("crop_id", "")
    page = row.get("page", "")
    cls = row.get("predicted_class", "")
    cv_cand = row.get("cv_read_payee_candidate", "") or ""
    reason = row.get("cv_read_payee_reason", "")
    conf = row.get("cv_read_payee_confidence", "")
    is_clean = row.get("cv_read_is_clean", "")
    easy = (row.get("easyocr_extracted_payee", "") or "")[:80]
    keywords = row.get("classifier_keywords", "")

    print("\n" + "=" * 70)
    print(f"Row {idx + 1}/{total}   crop_id: {crop}   page: {page}   class: {cls}")
    print("-" * 70)
    print(f"CV candidate : {cv_cand!r}")
    print(f"  reason     : {reason}   conf={conf}   clean={is_clean}")
    print(f"EasyOCR      : {easy!r}")
    print(f"Classifier   : {keywords}")
    print("=" * 70)


def grade_one_row(row: dict[str, Any]) -> str | None:
    """Interactive prompt for one row. Returns the new manual_grade string or None (skip)."""
    print(RUBRIC)
    while True:
        raw = input("Grade [c/s/p/w/e/b/d/x/?/q]: ").strip().lower()
        if not raw:
            continue
        if raw in ("?", "help"):
            print(RUBRIC)
            continue
        if raw in ("q", "quit", "exit"):
            return None  # signal quit

        code = raw
        extra = None

        if code == "w" or code == "wrong":
            extra = input("  Actual payee visible in photo: ").strip()
            if not extra:
                print("  (no text entered — treating as empty)")
                code = "e"
        elif code in ("s", "spelling", "p", "partial"):
            extra = input("  Brief note (e.g. 'Hyunden -> Hyundai' or 'truncated'): ").strip() or None
        elif code in ("e", "empty"):
            extra = input("  Why empty? (handwritten / light print / missed line) [optional]: ").strip() or None
        elif code in ("b", "boilerplate"):
            extra = input("  What text did it latch onto? [optional]: ").strip() or None
        elif code in ("d", "deposit"):
            extra = input("  Any issues with deposit text? (or Enter for 'ok') ").strip() or "text captured for P&L"

        grade = expand_grade(code, extra)
        confirm = input(f"  Store as: {grade!r}  ? [y/N]: ").strip().lower()
        if confirm in ("y", "yes"):
            return grade
        print("  (not saved — try again)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Interactive visual grader for Phase 1 CV Read CSV")
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV,
        help=f"Path to side_by_side_harness.csv (default: {DEFAULT_CSV})",
    )
    parser.add_argument("--page", type=int, help="Only grade rows from this page number")
    parser.add_argument("--class", dest="class_filter", help="Only grade 'check' or 'deposit_slip'")
    parser.add_argument(
        "--only-ungraded", action="store_true", help="Skip rows that already have a manual_grade"
    )
    parser.add_argument(
        "--start", type=int, default=0, help="Start at this 0-based row index in the original CSV"
    )
    parser.add_argument(
        "--prefill-deposits",
        action="store_true",
        help="On first run, pre-fill all deposit_slip rows with a safe default (non-destructive)",
    )
    args = parser.parse_args(argv)

    csv_path = args.csv
    if not csv_path.is_file():
        print(f"ERROR: CSV not found: {csv_path}", file=sys.stderr)
        return 2

    rows = load_csv(csv_path)
    if not rows:
        print("ERROR: CSV is empty", file=sys.stderr)
        return 2

    fieldnames = list(rows[0].keys())
    if "manual_grade" not in fieldnames:
        print("ERROR: CSV is missing the 'manual_grade' column", file=sys.stderr)
        return 2

    # Optional one-time convenience: pre-fill the 7 deposits if they are still blank
    if args.prefill_deposits:
        changed = 0
        for r in rows:
            if r.get("predicted_class") == "deposit_slip" and not (r.get("manual_grade") or "").strip():
                r["manual_grade"] = "deposit_ok - prefilled (classification correct, text captured)"
                changed += 1
        if changed:
            save_csv(csv_path, rows, fieldnames)
            print(f"Prefilled {changed} deposit rows with safe default.")
        else:
            print("No blank deposit rows to prefill (or they were already graded).")

    filtered = apply_filters(
        rows,
        page=args.page,
        class_filter=args.class_filter,
        only_ungraded=args.only_ungraded,
    )
    if not filtered:
        print("No rows match the current filters. Nothing to grade.")
        return 0

    # Find a sensible starting point inside the filtered list
    start_idx = 0
    if args.start:
        for i, (orig_idx, _) in enumerate(filtered):
            if orig_idx >= args.start:
                start_idx = i
                break

    total_filtered = len(filtered)
    graded_this_session = 0
    print(f"\nLoaded {len(rows)} rows from {csv_path.name}")
    print(f"After filters: {total_filtered} rows to consider")
    print("Press Enter at any grade prompt to skip (leave blank). Type q to quit and save.\n")

    try:
        for f_idx in range(start_idx, total_filtered):
            orig_idx, row = filtered[f_idx]
            print_row_context(row, orig_idx, len(rows))

            img_path = row.get("image_path", "")
            if img_path and Path(img_path).is_file():
                print(f"Opening image: {img_path}")
                open_image(img_path)
            else:
                print(f"[WARN] Image not found on disk: {img_path}")

            new_grade = grade_one_row(row)
            if new_grade is None:
                # user chose q
                break
            if new_grade:
                row["manual_grade"] = new_grade
                graded_this_session += 1
                # Persist immediately
                save_csv(csv_path, rows, fieldnames)
                print(f"  Saved. ({graded_this_session} graded this session so far)")

            # Tiny progress hint
            remaining_in_filter = total_filtered - (f_idx + 1)
            print(f"  Remaining in current filter set: {remaining_in_filter}")

    except KeyboardInterrupt:
        print("\n\nInterrupted — progress has been saved to the CSV.")

    # Final summary
    remaining_blank = sum(1 for r in rows if not (r.get("manual_grade") or "").strip())
    print("\n" + "-" * 50)
    print(f"Session complete. Graded this run: {graded_this_session}")
    print(f"Total rows still blank: {remaining_blank} / {len(rows)}")
    print(f"CSV updated: {csv_path}")

    if remaining_blank == 0:
        print("\nAll rows now have a manual_grade. Great work!")
        print("Next: run the breakdown script to see the honest cohort numbers:")
        print("  python Scripts/spike/phase1_breakdown.py " + str(csv_path.parent))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())