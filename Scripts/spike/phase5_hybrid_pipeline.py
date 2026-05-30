#!/usr/bin/env python3
"""Phase 5 — Hybrid CV Read check leg (spike-only orchestrator).

SPIKE-ONLY. NOT PART OF THE PRODUCTION PIPELINE.
Does not modify App/, AzureFunctions/, or Bank Statements UI behavior.

Combines:
  1. Register transactions from Phase 0 baseline (12-column, unchanged parser leg).
  2. Fast photo regions (_find_photo_regions fast=True) on imaging pages only.
  3. Azure CV Read per crop (reuses phase1_cv_read_harness).
  4. Check vs deposit_slip classification + payee extraction.
  5. Production matcher (_match_checks_to_transactions) via read-only imports.

Schema: Option A (12-column freeze) — see Scripts/spike/SCHEMA_DECISION.md.

Usage (from repo root, venv active):

    python Scripts/spike/phase5_hybrid_pipeline.py \\
        --pdf Data/Auto_Body_Center_Jan_26_Statement.pdf \\
        --baseline-dir Scripts/spike/artifacts/baseline_<UTC> \\
        --first-imaging-page 5 --last-imaging-page 9 \\
        --real

    # Run baseline inline then hybrid:
    python Scripts/spike/phase5_hybrid_pipeline.py --pdf Data/...pdf --run-baseline --real

    # Reuse cached CV JSON when crop_id matches (zero Azure cost for those crops):
    python Scripts/spike/phase5_hybrid_pipeline.py --pdf Data/...pdf \\
        --baseline-dir Scripts/spike/artifacts/baseline_<UTC> \\
        --reuse-cv-dir Scripts/spike/artifacts/phase1_real_cv_read_harness_*__rescored/raw_cv_responses

    # Detection + export only (no Azure):
    python Scripts/spike/phase5_hybrid_pipeline.py --pdf Data/...pdf \\
        --baseline-dir Scripts/spike/artifacts/baseline_<UTC> --dry-run
"""

from __future__ import annotations

import argparse
import base64
import copy
import csv
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
APP_DIR = REPO_ROOT / "App"
SPIKE_DIR = Path(__file__).resolve().parent
ARTIFACTS_DIR = SPIKE_DIR / "artifacts"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(SPIKE_DIR) not in sys.path:
    sys.path.insert(0, str(SPIKE_DIR))

import local_enhanced_ocr as leo  # noqa: E402
import phase1_cv_read_harness as p1  # noqa: E402

try:
    from bank_statements import GROK_CSV_COLUMNS, apply_payee_rules  # noqa: E402
except Exception:
    GROK_CSV_COLUMNS = leo.TRANSACTION_FIELDS  # type: ignore[misc]

    def apply_payee_rules(df, **_kwargs):  # type: ignore[misc]
        return df, {"rows_changed": 0}

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(REPO_ROOT / ".env")
except Exception:
    pass

DEFAULT_PDF = REPO_ROOT / "Data" / "Auto_Body_Center_Jan_26_Statement.pdf"
S1_G2_USD_PER_1K = 1.50


@dataclass
class PhotoCrop:
    crop_id: str
    page: int
    width: int
    height: int
    aspect_ratio: float
    image_b64: str
    png_path: Path | None = None


@dataclass
class ProcessedCrop:
    crop: PhotoCrop
    predicted_class: str = "unknown"
    class_confidence: float = 0.0
    class_keywords: list[str] = field(default_factory=list)
    cv_status: str = ""
    cv_raw_text: str = ""
    cv_lines: list[dict[str, Any]] = field(default_factory=list)
    cv_payee: str = ""
    cv_payee_confidence: float = 0.0
    cv_payee_reason: str = ""
    cv_is_clean: bool = False
    guessed_check_no: str = ""


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase 5 hybrid CV Read pipeline (spike-only).")
    p.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    p.add_argument(
        "--baseline-dir",
        type=Path,
        default=None,
        help="Phase 0 baseline artifact dir (must contain transactions_all.csv).",
    )
    p.add_argument(
        "--run-baseline",
        action="store_true",
        help="Run baseline_current_ocr.py into --baseline-dir or a new timestamped folder.",
    )
    p.add_argument("--out-dir", type=Path, default=None)
    p.add_argument("--first-imaging-page", type=int, default=5)
    p.add_argument("--last-imaging-page", type=int, default=9)
    p.add_argument("--real", action="store_true", help="Call Azure CV Read (requires AZURE_CV_*).")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Fast detection + page filter + exports; skip Azure CV Read.",
    )
    p.add_argument(
        "--reuse-cv-dir",
        type=Path,
        default=None,
        help="Directory of raw_cv_responses/<crop_id>.json to load instead of calling Azure.",
    )
    p.add_argument(
        "--harness-dir",
        type=Path,
        default=None,
        help=(
            "Use final_kept/ crops from diagnose_check_deposit_cropper.py instead of "
            "fast detection (crop IDs align with phase1 raw_cv_responses)."
        ),
    )
    p.add_argument("--rate-limit-seconds", type=float, default=3.2)
    p.add_argument("--apply-payee-rules", action="store_true", default=False)
    p.add_argument("--client-name", type=str, default="Spike Hybrid Test")
    p.add_argument(
        "--bank",
        type=str,
        default="auto",
        help="Bank profile for payee extraction: auto|traditions|regions|generic.",
    )
    p.add_argument(
        "--check-rules-path",
        type=Path,
        default=None,
        help="Optional check_payee_rules.csv for photo-leg fragment cleanup.",
    )
    return p.parse_args(argv)


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _resolve_out_dir(arg: Path | None) -> Path:
    return (arg or (ARTIFACTS_DIR / f"phase5_hybrid_{_utc_stamp()}")).resolve()


def _run_baseline(pdf: Path, out_dir: Path) -> None:
    import baseline_current_ocr as baseline  # noqa: PLC0415

    print(f"[phase5] Running Phase 0 baseline -> {out_dir}")
    rc = baseline.main(["--pdf", str(pdf), "--out-dir", str(out_dir)])
    if rc != 0:
        raise RuntimeError(f"baseline_current_ocr.py exited {rc}")


def _load_baseline_transactions(baseline_dir: Path) -> list[dict[str, Any]]:
    csv_path = baseline_dir / "transactions_all.csv"
    if not csv_path.is_file():
        raise FileNotFoundError(f"Missing {csv_path}")

    fields = list(leo.TRANSACTION_FIELDS)
    txns: list[dict[str, Any]] = []
    with csv_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            txn = {k: (row.get(k) or "") for k in fields}
            if "linked_check_id" in row:
                txn["linked_check_id"] = row.get("linked_check_id") or ""
            txns.append(txn)
    return txns


def _filter_regions(
    regions: list[dict[str, Any]],
    first_page: int,
    last_page: int,
) -> tuple[list[dict[str, Any]], int]:
    before = len(regions)
    filtered = [
        r
        for r in regions
        if first_page <= int(r.get("page") or 0) <= last_page
    ]
    return filtered, before


def _harness_to_crops(harness_dir: Path, crops_dir: Path, first_page: int, last_page: int) -> list[PhotoCrop]:
    """Load crops from harness final_kept/ (matches phase1 CV cache IDs)."""
    discovered = p1.discover_crops(harness_dir.resolve())
    crops_dir.mkdir(parents=True, exist_ok=True)
    out: list[PhotoCrop] = []
    for c in discovered:
        if not (first_page <= c.page <= last_page):
            continue
        raw = c.raw_path
        b64 = base64.b64encode(raw.read_bytes()).decode("ascii")
        png_path = crops_dir / f"{c.crop_id}.png"
        png_path.write_bytes(raw.read_bytes())
        out.append(
            PhotoCrop(
                crop_id=c.crop_id,
                page=c.page,
                width=c.width,
                height=c.height,
                aspect_ratio=c.aspect,
                image_b64=b64,
                png_path=png_path,
            )
        )
    return out


def _regions_to_crops(regions: list[dict[str, Any]], crops_dir: Path) -> list[PhotoCrop]:
    crops_dir.mkdir(parents=True, exist_ok=True)
    out: list[PhotoCrop] = []
    for i, r in enumerate(regions):
        b64 = r.get("image_b64") or ""
        if not b64:
            continue
        page = int(r.get("page") or 0)
        crop_id = str(r.get("check_id") or f"P{page:02d}H{i:02d}")
        png_path = crops_dir / f"{crop_id}.png"
        try:
            png_path.write_bytes(base64.b64decode(b64))
        except (ValueError, OSError):
            png_path = None
        out.append(
            PhotoCrop(
                crop_id=crop_id,
                page=page,
                width=int(r.get("width") or 0),
                height=int(r.get("height") or 0),
                aspect_ratio=float(r.get("aspect_ratio") or 0.0),
                image_b64=b64,
                png_path=png_path,
            )
        )
    return out


def _load_cached_cv(cache_dir: Path, crop_id: str) -> dict[str, Any] | None:
    path = cache_dir / f"{crop_id}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _save_cv_cache(cache_dir: Path, crop_id: str, payload: dict[str, Any]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{crop_id}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _cv_lines_to_detections(lines: list[dict[str, Any]]) -> list[Any]:
    """Convert CV Read lines to EasyOCR-style (bbox, text, conf) tuples."""
    detections: list[Any] = []
    for ln in lines:
        text = (ln.get("text") or "").strip()
        if not text:
            continue
        conf = float(ln.get("confidence") or 0.9)
        flat = ln.get("bbox") or []
        if isinstance(flat, list) and len(flat) >= 8:
            pts = [(float(flat[i]), float(flat[i + 1])) for i in range(0, 8, 2)]
        else:
            pts = [(0.0, 0.0), (100.0, 0.0), (100.0, 20.0), (0.0, 20.0)]
        detections.append((pts, text, conf))
    return detections


def _process_crops(
    crops: list[PhotoCrop],
    *,
    use_real: bool,
    dry_run: bool,
    reuse_cv_dir: Path | None,
    out_cv_dir: Path,
    rate_limit: float,
) -> list[ProcessedCrop]:
    client = None
    if use_real and not dry_run:
        client = p1.get_cv_client()
        if client is None:
            raise RuntimeError(
                "Azure CV Read requested but AZURE_CV_ENDPOINT / AZURE_CV_KEY missing in .env"
            )

    results: list[ProcessedCrop] = []
    for i, crop in enumerate(crops):
        proc = ProcessedCrop(crop=crop)
        cached = None
        if reuse_cv_dir is not None:
            cached = _load_cached_cv(reuse_cv_dir, crop.crop_id)

        if dry_run:
            proc.cv_status = "dry_run"
        elif cached is not None:
            proc.cv_status = str(cached.get("status") or "cached")
            proc.cv_raw_text = cached.get("raw_text") or ""
            proc.cv_lines = cached.get("lines") or []
        elif client is not None and crop.png_path and crop.png_path.is_file():
            cv = p1.call_cv_read(client, crop.png_path)
            proc.cv_status = cv.get("status") or ""
            proc.cv_raw_text = cv.get("raw_text") or ""
            proc.cv_lines = cv.get("lines") or []
            _save_cv_cache(
                out_cv_dir,
                crop.crop_id,
                {
                    "crop_id": crop.crop_id,
                    "page": crop.page,
                    "status": proc.cv_status,
                    "raw_text": proc.cv_raw_text,
                    "lines": proc.cv_lines,
                    "elapsed_ms": cv.get("elapsed_ms"),
                },
            )
            if use_real and rate_limit > 0 and i + 1 < len(crops):
                time.sleep(rate_limit)
        else:
            proc.cv_status = "skipped"

        cls, c_conf, kws = p1.classify_from_text(proc.cv_raw_text)
        proc.predicted_class = cls
        proc.class_confidence = c_conf
        proc.class_keywords = kws

        if cls == "check":
            payee, p_conf, reason = p1.extract_payee_from_cv_lines(proc.cv_lines)
            proc.cv_payee = payee
            proc.cv_payee_confidence = p_conf
            proc.cv_payee_reason = reason
            proc.cv_is_clean = bool(payee and p1._is_clean_payee(payee))
            proc.guessed_check_no = p1.guess_check_no(proc.cv_lines)

        results.append(proc)
        if (i + 1) % 10 == 0:
            print(f"[phase5] CV processed {i + 1}/{len(crops)} crops")

    return results


def _build_cropped_checks_for_matcher(checks: list[ProcessedCrop]) -> tuple[
    list[dict[str, Any]], dict[str, list[Any]]
]:
    cropped: list[dict[str, Any]] = []
    detections_by_id: dict[str, list[Any]] = {}

    for proc in checks:
        c = proc.crop
        entry = {
            "check_id": c.crop_id,
            "page": c.page,
            "width": c.width,
            "height": c.height,
            "aspect_ratio": c.aspect_ratio,
            "image_b64": c.image_b64,
            "notes": "phase5 hybrid CV Read",
            "extracted_payee": proc.cv_payee if proc.cv_is_clean else "",
            "extracted_payee_confidence": proc.cv_payee_confidence if proc.cv_is_clean else 0.0,
            "extracted_check_number": proc.guessed_check_no,
        }
        cropped.append(entry)
        detections_by_id[c.crop_id] = _cv_lines_to_detections(proc.cv_lines)

    return cropped, detections_by_id


def _write_transactions_csv(path: Path, transactions: list[dict[str, Any]]) -> None:
    cols = list(GROK_CSV_COLUMNS)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for txn in transactions:
            writer.writerow({k: txn.get(k, "") for k in cols})


def _write_manifest(path: Path, processed: list[ProcessedCrop]) -> None:
    fields = [
        "crop_id",
        "page",
        "width",
        "height",
        "aspect_ratio",
        "predicted_class",
        "class_confidence",
        "cv_read_status",
        "cv_read_payee",
        "cv_read_confidence",
        "cv_read_is_clean",
        "cv_read_reason",
        "guessed_check_no",
        "image_path",
        "class_keywords",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for p in processed:
            c = p.crop
            w.writerow(
                {
                    "crop_id": c.crop_id,
                    "page": c.page,
                    "width": c.width,
                    "height": c.height,
                    "aspect_ratio": c.aspect_ratio,
                    "predicted_class": p.predicted_class,
                    "class_confidence": round(p.class_confidence, 3),
                    "cv_read_status": p.cv_status,
                    "cv_read_payee": p.cv_payee,
                    "cv_read_confidence": round(p.cv_payee_confidence, 3),
                    "cv_read_is_clean": "Yes" if p.cv_is_clean else "No",
                    "cv_read_reason": p.cv_payee_reason,
                    "guessed_check_no": p.guessed_check_no,
                    "image_path": str(c.png_path) if c.png_path else "",
                    "class_keywords": ";".join(p.class_keywords),
                }
            )


def _deposit_slips_payload(deposits: list[ProcessedCrop]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in deposits:
        out.append(
            {
                "crop_id": p.crop.crop_id,
                "page": p.crop.page,
                "predicted_class": "deposit_slip",
                "cv_read_raw_text": p.cv_raw_text,
                "matched_transaction_index": None,
                "notes": "Option A sidecar — credit-side P&L attribution in Phase 6",
            }
        )
    return out


def _write_report(
    path: Path,
    summary: dict[str, Any],
    match_logs: list[str],
) -> None:
    lines = [
        "# Phase 5 Hybrid Pipeline Report",
        "",
        f"**Generated**: {summary.get('generated_utc')}",
        f"**PDF**: `{summary.get('pdf')}`",
        f"**Mode**: {summary.get('mode')}",
        "",
        "## Headline",
        "",
        f"- Regions (scoped pages {summary.get('pages_scoped')}): "
        f"{summary.get('regions_after_filter')} "
        f"(from {summary.get('regions_before_filter')} before filter)",
        f"- Classified checks: **{summary.get('checks_classified')}**",
        f"- Classified deposits: **{summary.get('deposits_classified')}**",
        f"- CV Read calls: **{summary.get('cv_read_calls')}**",
        f"- Matcher linked checks: **{summary.get('matcher_linked_checks')}**",
        f"- Clean CV payees (checks): **{summary.get('cv_clean_payees')}**",
        "",
        "## Timing",
        "",
        f"- Detection: {summary.get('detect_wall_sec')}s",
        f"- CV Read: {summary.get('cv_read_wall_sec')}s",
        f"- Total: {summary.get('total_wall_sec')}s",
        "",
        "## Matcher log (excerpt)",
        "",
    ]
    for log_line in match_logs[:40]:
        lines.append(f"- `{log_line}`")
    if len(match_logs) > 40:
        lines.append(f"- ... ({len(match_logs) - 40} more lines)")
    lines.append("")
    lines.append("All artifacts are under `Scripts/spike/artifacts/` (gitignored).")
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    pdf_path = args.pdf.resolve()
    if not pdf_path.is_file():
        print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        return 1

    if args.real and args.dry_run:
        print("ERROR: use only one of --real or --dry-run", file=sys.stderr)
        return 1

    out_dir = _resolve_out_dir(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    crops_dir = out_dir / "crops"
    raw_cv_dir = out_dir / "raw_cv_responses"

    baseline_dir = args.baseline_dir
    if args.run_baseline or baseline_dir is None:
        baseline_dir = out_dir / "baseline_prereq"
        if not (baseline_dir / "transactions_all.csv").is_file():
            _run_baseline(pdf_path, baseline_dir)
    else:
        baseline_dir = baseline_dir.resolve()

    print(f"[phase5] PDF          : {pdf_path}")
    print(f"[phase5] Baseline     : {baseline_dir}")
    print(f"[phase5] Out dir      : {out_dir}")
    print(f"[phase5] Pages        : {args.first_imaging_page}-{args.last_imaging_page}")

    resolved_bank = p1.configure_extractor(
        bank=args.bank,
        client_name=args.client_name,
        check_rules_path=args.check_rules_path,
        baseline_summary_path=(baseline_dir / "summary.json"),
    )
    print(f"[phase5] Bank profile : {resolved_bank}")

    use_real = bool(args.real)
    mode = "dry_run" if args.dry_run else ("real" if use_real else "reuse_or_skip")

    t0 = time.perf_counter()
    pdf_bytes = pdf_path.read_bytes()

    # Step 1 — fast regions
    t_detect = time.perf_counter()
    before_count = 0
    if args.harness_dir:
        crops = _harness_to_crops(
            args.harness_dir,
            crops_dir,
            args.first_imaging_page,
            args.last_imaging_page,
        )
        detect_logs = [
            leo._log("info", f"Using harness crops from {args.harness_dir} (final_kept/).")
        ]
        print(f"[phase5] Harness crops (pages {args.first_imaging_page}-{args.last_imaging_page}): {len(crops)}")
    else:
        regions, detect_logs = leo._find_photo_regions(
            pdf_bytes, fast=True, purpose="cv_read"
        )
        regions, before_count = _filter_regions(
            regions, args.first_imaging_page, args.last_imaging_page
        )
        crops = _regions_to_crops(regions, crops_dir)
        print(f"[phase5] Detection: {before_count} -> {len(regions)} regions")
    detect_sec = round(time.perf_counter() - t_detect, 1)
    print(f"[phase5] Detection wall time: {detect_sec}s")
    for line in detect_logs:
        if "geometry" in line.lower() or "extracted" in line.lower() or "harness" in line.lower():
            safe = line.encode("ascii", errors="replace").decode("ascii")
            print(f"  {safe}")

    # Step 2–3 — CV Read + classify
    t_cv = time.perf_counter()
    processed = _process_crops(
        crops,
        use_real=use_real,
        dry_run=args.dry_run,
        reuse_cv_dir=args.reuse_cv_dir.resolve() if args.reuse_cv_dir else None,
        out_cv_dir=raw_cv_dir,
        rate_limit=args.rate_limit_seconds,
    )
    cv_sec = round(time.perf_counter() - t_cv, 1)

    check_procs = [p for p in processed if p.predicted_class == "check"]
    deposit_procs = [p for p in processed if p.predicted_class == "deposit_slip"]
    unknown_procs = [p for p in processed if p.predicted_class == "unknown"]

    cv_calls = sum(1 for p in processed if p.cv_status == "succeeded")

    # Step 4–5 — matcher + export
    transactions = _load_baseline_transactions(baseline_dir)
    for txn in transactions:
        txn.pop("linked_check_id", None)

    cropped_checks, detections_by_id = _build_cropped_checks_for_matcher(check_procs)
    txns_copy = copy.deepcopy(transactions)
    merged_txns, _merged_checks, match_logs, _cv_payees_used = leo._match_checks_to_transactions(
        txns_copy, cropped_checks, detections_by_id
    )

    if args.apply_payee_rules:
        try:
            import pandas as pd  # noqa: PLC0415

            df = pd.DataFrame(merged_txns)
            df, rules_info = apply_payee_rules(df, client_name=args.client_name)
            merged_txns = df.to_dict(orient="records")
            print(f"[phase5] Payee rules changed {rules_info.get('rows_changed', 0)} row(s)")
        except Exception as exc:
            print(f"[phase5] Payee rules skipped: {exc}", file=sys.stderr)

    _write_transactions_csv(out_dir / "transactions_hybrid.csv", merged_txns)
    _write_manifest(out_dir / "hybrid_photo_manifest.csv", processed)
    (out_dir / "deposit_slips.json").write_text(
        json.dumps(_deposit_slips_payload(deposit_procs), indent=2),
        encoding="utf-8",
    )

    linked = sum(1 for c in cropped_checks if int(c.get("linked_transaction_index", -1) or -1) >= 0)
    clean_payees = sum(1 for p in check_procs if p.cv_is_clean)

    total_sec = round(time.perf_counter() - t0, 1)
    summary = {
        "spike": "Phase 5 hybrid CV Read pipeline",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pdf": str(pdf_path.relative_to(REPO_ROOT) if pdf_path.is_relative_to(REPO_ROOT) else pdf_path),
        "baseline_dir": str(baseline_dir),
        "mode": mode,
        "pages_scoped": f"{args.first_imaging_page}-{args.last_imaging_page}",
        "regions_before_filter": before_count if not args.harness_dir else len(crops),
        "regions_after_filter": len(crops),
        "harness_dir": str(args.harness_dir) if args.harness_dir else None,
        "checks_classified": len(check_procs),
        "deposits_classified": len(deposit_procs),
        "unknown_classified": len(unknown_procs),
        "cv_read_calls": cv_calls if use_real else 0,
        "cv_clean_payees": clean_payees,
        "matcher_linked_checks": linked,
        "detect_wall_sec": detect_sec,
        "cv_read_wall_sec": cv_sec,
        "total_wall_sec": total_sec,
        "tier": "F0" if use_real else "n/a",
        "estimated_cost_usd_s1_g2": round(cv_calls * S1_G2_USD_PER_1K / 1000.0, 4) if cv_calls else 0.0,
        "schema": "Option A (12-column)",
    }
    (out_dir / "hybrid_run_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    _write_report(out_dir / "phase5_hybrid_report.md", summary, match_logs)

    print()
    print("=" * 72)
    print("PHASE 5 HYBRID PIPELINE — COMPLETE")
    print("=" * 72)
    print(f"Photo crops (pages {args.first_imaging_page}-{args.last_imaging_page}): {len(crops)}")
    print(f"  checks={len(check_procs)} deposits={len(deposit_procs)} unknown={len(unknown_procs)}")
    print(f"CV clean payees (checks): {clean_payees}")
    print(f"Matcher linked: {linked}/{len(check_procs)} checks")
    print(f"Wall time: {total_sec}s (detect {detect_sec}s, cv {cv_sec}s)")
    print(f"Output: {out_dir}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
