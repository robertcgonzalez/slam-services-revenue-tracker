"""SLAM Services — Phase 0 baseline runner for the Computer Vision Read spike.

SPIKE-ONLY. NOT PART OF THE PRODUCTION PIPELINE.

Purpose
-------
Run the *current* Local Enhanced OCR pipeline (``App.local_enhanced_ocr.run_pipeline``,
v2.44.3) against the hard test PDF and dump a self-contained artifact bundle that
later Phase 1/2 prototypes can diff against without re-rasterizing the PDF.

Captured per run (default ``Scripts/spike/artifacts/<timestamp>/``):

- ``summary.json``               — version, capabilities, totals, counts, status
- ``pipeline_logs.txt``          — full ``result["logs"]`` list, one per line
- ``transactions_all.csv``       — every transaction in the canonical 12-col shape
                                   plus ``linked_check_id`` for diffing
- ``transactions_checks.csv``    — subset of rows where ``Check#`` is populated
                                   (the Payee leg this spike is targeting)
- ``cropped_checks/manifest.csv``— one row per cropped check image: check_id,
                                   page, dimensions, extracted_payee, confidence,
                                   extracted_check_number, linked txn index, the
                                   matched transaction's Payee / Confidence /
                                   ReviewReason, and the on-disk PNG path
- ``cropped_checks/<check_id>.png`` — every cropped check PNG, decoded from the
                                   ``image_b64`` field returned by ``_crop_checks``;
                                   filenames intentionally use only the spike's
                                   ``check_id`` so they can be visually correlated
                                   to the manifest without leaking client data

Why this exists
---------------
The revised hybrid spike plan
(``Spike-Plan-Microsoft-Document-Intelligence-PnL.md`` v2) calls for a clean
Phase 0 baseline against the *actual* check photographs in the PDF — not the
old Grok Vision CSV. To compare Phase 1's Azure Computer Vision Read output
against today's EasyOCR-based Payee extraction, we need:

  1. The exact ``extracted_payee`` / ``extracted_payee_confidence`` the current
     pipeline produces per cropped check.
  2. The exact PNGs the cropper fed to EasyOCR (so Phase 1 sends *the same*
     images to CV Read — apples-to-apples comparison).
  3. The final per-transaction Payee / Confidence / NeedsReview after the
     v2.44.3 matcher + ``_is_clean_payee`` guard run.

This skeleton is intentionally thin: it imports the real ``run_pipeline``
without monkey-patching, writes only into ``Scripts/spike/artifacts/``, and
never mutates production state. Phase 1 will reuse it as a fixture loader.

Usage
-----
    # From repo root, with the project .venv active:
    python Scripts/spike/baseline_current_ocr.py

    # Custom PDF / output dir:
    python Scripts/spike/baseline_current_ocr.py \
        --pdf Data/Auto_Body_Center_Jan_26_Statement.pdf \
        --out-dir Scripts/spike/artifacts/baseline_v2_44_3

    # Skip the heavy OpenCV cropper for quick smoke (parser-only):
    python Scripts/spike/baseline_current_ocr.py --skip-crop

The script exits 0 on a ``success`` or ``partial`` pipeline result, and 1 only
when the PDF cannot be loaded or ``run_pipeline`` raises.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
APP_DIR = REPO_ROOT / "App"
DEFAULT_PDF = REPO_ROOT / "Data" / "Auto_Body_Center_Jan_26_Statement.pdf"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import local_enhanced_ocr as leo  # noqa: E402  — path injection above


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase 0 baseline runner for the CV Read spike (spike-only)."
    )
    parser.add_argument(
        "--pdf",
        type=Path,
        default=DEFAULT_PDF,
        help=f"PDF to process (default: {DEFAULT_PDF.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help=(
            "Output directory for the artifact bundle. "
            "Default: Scripts/spike/artifacts/<UTC timestamp>/."
        ),
    )
    parser.add_argument(
        "--skip-crop",
        action="store_true",
        help="Monkey-patch _crop_checks to a no-op (fast parser-only smoke).",
    )
    parser.add_argument(
        "--skip-images",
        action="store_true",
        help="Do not write decoded check PNGs (manifest only).",
    )
    parser.add_argument(
        "--relaxed-crop",
        action="store_true",
        help=(
            "For the CV Read spike path: bypass the strict check-keyword filter so all "
            "plausible photo regions (including deposits and weak-text crops on page 5+) "
            "are captured and sent to CV Read. Still applies size/aspect/dedup/junk-bank filters. "
            "Production EasyOCR path remains strict."
        ),
    )
    return parser.parse_args(argv)


def _resolve_out_dir(arg_value: Path | None) -> Path:
    if arg_value is not None:
        return arg_value
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return REPO_ROOT / "Scripts" / "spike" / "artifacts" / f"baseline_{stamp}"


def _write_summary(result: dict[str, Any], pdf: Path, out_dir: Path) -> dict[str, Any]:
    grok_totals = result.get("grok_totals") or {}
    txns = result.get("transactions") or []
    checks = result.get("cropped_checks") or []

    check_rows = [t for t in txns if str(t.get("Check#") or "").strip()]
    linked_check_rows = [t for t in check_rows if t.get("linked_check_id")]

    summary = {
        "spike": "Phase 0 — current Local Enhanced OCR baseline",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "pdf": str(pdf.relative_to(REPO_ROOT)) if pdf.is_relative_to(REPO_ROOT) else str(pdf),
        "pdf_bytes": pdf.stat().st_size if pdf.is_file() else None,
        "pipeline_version": leo.LOCAL_ENHANCED_OCR_VERSION,
        "environment": leo.environment_summary(),
        "capabilities": leo.detect_capabilities(),
        "status": result.get("status"),
        "message": result.get("message"),
        "fast_path_rows": result.get("fast_path_rows"),
        "fallback_rows": result.get("fallback_rows"),
        "linked_count": result.get("linked_count"),
        "totals": {
            "transactions": len(txns),
            "check_rows": len(check_rows),
            "linked_check_rows": len(linked_check_rows),
            "cropped_checks": len(checks),
            "deposits": grok_totals.get("deposits"),
            "withdrawals": grok_totals.get("withdrawals"),
            "checks": grok_totals.get("checks"),
            "grok_totals_transactions": grok_totals.get("transactions"),
        },
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    return summary


def _write_logs(result: dict[str, Any], out_dir: Path) -> None:
    logs = result.get("logs") or []
    (out_dir / "pipeline_logs.txt").write_text("\n".join(str(line) for line in logs), encoding="utf-8")


def _write_transactions(result: dict[str, Any], out_dir: Path) -> None:
    txns = result.get("transactions") or []
    fields = list(leo.TRANSACTION_FIELDS) + ["linked_check_id"]

    def _row(t: dict[str, Any]) -> dict[str, str]:
        return {k: ("" if t.get(k) is None else str(t.get(k))) for k in fields}

    with (out_dir / "transactions_all.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for t in txns:
            writer.writerow(_row(t))

    check_only = [t for t in txns if str(t.get("Check#") or "").strip()]
    with (out_dir / "transactions_checks.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for t in check_only:
            writer.writerow(_row(t))


def _write_check_artifacts(
    result: dict[str, Any], out_dir: Path, *, write_images: bool
) -> None:
    checks = result.get("cropped_checks") or []
    txns = result.get("transactions") or []
    checks_dir = out_dir / "cropped_checks"
    checks_dir.mkdir(parents=True, exist_ok=True)

    manifest_fields = [
        "check_id",
        "page",
        "width",
        "height",
        "aspect_ratio",
        "extracted_check_number",
        "extracted_payee",
        "extracted_payee_confidence",
        "linked_transaction_index",
        "linked_txn_check_no",
        "linked_txn_amount",
        "linked_txn_payee",
        "linked_txn_confidence",
        "linked_txn_needs_review",
        "linked_txn_review_reason",
        "image_path",
        "notes",
    ]
    with (checks_dir / "manifest.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=manifest_fields, extrasaction="ignore")
        writer.writeheader()
        for c in checks:
            check_id = str(c.get("check_id") or "").strip() or "unknown"
            idx = int(c.get("linked_transaction_index", -1) or -1)
            linked_txn = txns[idx] if 0 <= idx < len(txns) else {}

            image_path = ""
            if write_images and c.get("image_b64"):
                png_path = checks_dir / f"{check_id}.png"
                try:
                    png_path.write_bytes(base64.b64decode(c["image_b64"]))
                    image_path = str(png_path.relative_to(out_dir))
                except (ValueError, OSError) as exc:
                    image_path = f"<decode error: {exc}>"

            writer.writerow(
                {
                    "check_id": check_id,
                    "page": c.get("page"),
                    "width": c.get("width"),
                    "height": c.get("height"),
                    "aspect_ratio": c.get("aspect_ratio"),
                    "extracted_check_number": c.get("extracted_check_number"),
                    "extracted_payee": c.get("extracted_payee"),
                    "extracted_payee_confidence": c.get("extracted_payee_confidence"),
                    "linked_transaction_index": idx if idx >= 0 else "",
                    "linked_txn_check_no": linked_txn.get("Check#", ""),
                    "linked_txn_amount": linked_txn.get("SignedAmount") or linked_txn.get("Amount") or "",
                    "linked_txn_payee": linked_txn.get("Payee", ""),
                    "linked_txn_confidence": linked_txn.get("Confidence", ""),
                    "linked_txn_needs_review": linked_txn.get("NeedsReview", ""),
                    "linked_txn_review_reason": linked_txn.get("ReviewReason", ""),
                    "image_path": image_path,
                    "notes": c.get("notes", ""),
                }
            )


def _print_console_summary(summary: dict[str, Any]) -> None:
    print()
    print("=" * 72)
    print(f"SLAM spike Phase 0 baseline — {summary['pipeline_version']}")
    print("=" * 72)
    print(f"PDF              : {summary['pdf']} ({summary['pdf_bytes']} bytes)")
    print(f"Status           : {summary['status']}")
    print(f"Message          : {summary['message']}")
    print(f"Fast path rows   : {summary['fast_path_rows']}")
    print(f"Fallback rows    : {summary['fallback_rows']}")
    totals = summary["totals"]
    print(f"Transactions     : {totals['transactions']}")
    print(f"  of which checks: {totals['check_rows']} "
          f"({totals['linked_check_rows']} linked to a cropped image)")
    print(f"Cropped checks   : {totals['cropped_checks']}")
    print(f"Deposits         : ${totals['deposits']}")
    print(f"Withdrawals      : ${totals['withdrawals']}")
    print(f"Capabilities     : {summary['capabilities']}")
    print(f"Environment      : {summary['environment']}")
    print()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    pdf_path: Path = args.pdf.resolve()
    if not pdf_path.is_file():
        print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        return 1

    out_dir = _resolve_out_dir(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[spike] PDF     : {pdf_path}")
    print(f"[spike] Out dir : {out_dir}")
    print(f"[spike] Pipeline: Local Enhanced OCR {leo.LOCAL_ENHANCED_OCR_VERSION}")

    if args.skip_crop:
        # Monkey-patch the cropper to a no-op for the rare case we only want
        # to validate the parser leg. Production code is never touched —
        # this only mutates the in-process module reference for this run.
        leo._crop_checks = lambda _b: ([], {}, [leo._log("info", "Cropper skipped (--skip-crop).")])  # type: ignore[assignment]
        print("[spike] Cropper : SKIPPED (--skip-crop)")

    if args.relaxed_crop:
        # For the CV Read spike path only: replace the strict keyword gate with a
        # very loose one so every plausible photo region on the composite imaging
        # pages reaches CV Read. We still reject obvious bank junk blocks and
        # non-rectangular noise. This is the recommended way to get the full ~53
        # checks + 7 deposits for CV grading without polluting the EasyOCR path.
        orig_crop = leo._crop_checks

        def _relaxed_crop(pdf_bytes: bytes):
            # Temporarily widen the accepted keywords for this run only.
            old_check_kw = getattr(leo, "_CROP_CHECK_KEYWORDS", ("pay to", "order of", "memo", "dollars"))
            try:
                # Accept almost anything that is not pure junk; CV Read will decide.
                leo._CROP_CHECK_KEYWORDS = ("pay", "order", "memo", "dollar", "check", "dep", "ticket", "")
                return orig_crop(pdf_bytes)
            finally:
                leo._CROP_CHECK_KEYWORDS = old_check_kw

        leo._crop_checks = _relaxed_crop  # type: ignore[assignment]
        print("[spike] Cropper : RELAXED (CV Read path — all plausible photo regions)")

    pdf_bytes = pdf_path.read_bytes()

    try:
        result = leo.run_pipeline(pdf_bytes)
    except Exception as exc:  # noqa: BLE001 — surface the failure clearly in spike output
        print(f"ERROR: run_pipeline raised: {exc!r}", file=sys.stderr)
        return 1

    summary = _write_summary(result, pdf_path, out_dir)
    _write_logs(result, out_dir)
    _write_transactions(result, out_dir)
    _write_check_artifacts(result, out_dir, write_images=not args.skip_images)

    _print_console_summary(summary)
    print(f"[spike] Wrote artifacts to: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
