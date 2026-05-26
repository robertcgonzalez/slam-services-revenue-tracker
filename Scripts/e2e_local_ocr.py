"""End-to-end Local Enhanced OCR pipeline run + baseline diff.

Runs `local_enhanced_ocr.run_pipeline` against
``Data/Auto_Body_Center_Jan_26_Statement.pdf`` (the test case the user
provided), writes the result to ``Data/Auto_Body_Center_Jan_26_Statement_LocalOCR.csv``,
and compares against the v2.43.0 Grok Vision baseline CSV. Prints:

- pipeline status / message
- grok_totals (deposits, withdrawals, checks, transactions)
- per-section row counts (deposits, ACH credits, electronic debits, checks)
- cropped check count + linked count
- baseline comparison (per-row diff on amount + check#)

NOTE: This runs the full pipeline INCLUDING the EasyOCR fallback (it reuses
the cached lines via `_ocr_extract_lines` cache invalidation only on a
fresh cache file) plus the OpenCV check cropper, which can take 60-90s
on a 10-page scanned PDF. Set ``SLAM_LOCAL_OCR_SKIP_CROP=1`` to skip the
cropper if you only want to test the parser path.
"""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "App"))

import local_enhanced_ocr as leo  # noqa: E402  (path injection above)


def write_csv(rows: list[dict], out_path: Path) -> None:
    fields = list(leo.TRANSACTION_FIELDS)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def load_baseline(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            if r.get("Date", "").startswith("TOTALS"):
                continue
            rows.append(r)
    return rows


def amounts_set(rows: list[dict]) -> set[tuple[str, str]]:
    """Return {(Check# or "", SignedAmount)} pairs for quick diff comparison."""

    out: set[tuple[str, str]] = set()
    for r in rows:
        chk = str(r.get("Check#") or "").strip()
        sa = str(r.get("SignedAmount") or r.get("Amount") or "").strip()
        try:
            normalized = f"{float(sa.replace(',', '')):.2f}"
        except (ValueError, AttributeError):
            normalized = sa
        out.add((chk, normalized))
    return out


def main() -> int:
    pdf_path = REPO_ROOT / "Data" / "Auto_Body_Center_Jan_26_Statement.pdf"
    baseline_path = REPO_ROOT / "Data" / "Auto_Body_Center_Jan_26_Statement_Extracted.csv"
    if not pdf_path.is_file():
        print(f"PDF not found: {pdf_path}")
        return 1
    if not baseline_path.is_file():
        print(f"Baseline not found: {baseline_path}")
        return 1

    pdf_bytes = pdf_path.read_bytes()
    print(f"Loaded {pdf_path.name} ({len(pdf_bytes) / 1024:.1f} KiB)")
    print(f"Local Enhanced OCR version: {leo.LOCAL_ENHANCED_OCR_VERSION}")

    skip_crop = os.environ.get("SLAM_LOCAL_OCR_SKIP_CROP", "").strip() == "1"
    if skip_crop:
        # Monkey-patch the cropper to a no-op for fast iteration.
        leo._crop_checks = lambda _b: ([], {}, [leo._log("info", "Cropper skipped (env override).")])  # type: ignore[assignment]

    result = leo.run_pipeline(pdf_bytes)

    print(f"\nstatus={result.get('status')!r}")
    print(f"message={result.get('message')!r}")
    print(f"grok_totals={result.get('grok_totals')}")
    print(f"fast_path_rows={result.get('fast_path_rows')} fallback_rows={result.get('fallback_rows')}")
    print(f"cropped_checks={len(result.get('cropped_checks') or [])}")
    print(f"linked_count={result.get('linked_count')}")

    txns = result.get("transactions") or []
    print(f"\n--- ROW BREAKDOWN ({len(txns)}) ---")
    by_section: dict[str, int] = {"deposit": 0, "ach_credit": 0, "debit": 0, "check": 0, "other": 0}
    for r in txns:
        chk = str(r.get("Check#") or "").strip()
        desc = str(r.get("Description") or "").lower()
        amt = float(str(r.get("SignedAmount") or 0).replace(",", "") or 0)
        if chk:
            by_section["check"] += 1
        elif desc.startswith("regular deposit"):
            by_section["deposit"] += 1
        elif amt > 0:
            by_section["ach_credit"] += 1
        elif amt < 0:
            by_section["debit"] += 1
        else:
            by_section["other"] += 1
    for k, v in by_section.items():
        print(f"  {k:<12}: {v}")

    # Diff against baseline
    baseline = load_baseline(baseline_path)
    base_set = amounts_set(baseline)
    ours_set = amounts_set(txns)
    only_in_ours = ours_set - base_set
    only_in_base = base_set - ours_set
    print("\n--- BASELINE DIFF ---")
    print(f"Baseline rows: {len(baseline)}")
    print(f"Our rows:      {len(txns)}")
    print(f"In ours but not baseline ({len(only_in_ours)}):")
    for item in sorted(only_in_ours):
        print(f"  {item}")
    print(f"In baseline but not ours ({len(only_in_base)}):")
    for item in sorted(only_in_base):
        print(f"  {item}")

    out_csv = REPO_ROOT / "Data" / "Auto_Body_Center_Jan_26_Statement_LocalOCR.csv"
    write_csv(txns, out_csv)
    print(f"\nWrote {out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
