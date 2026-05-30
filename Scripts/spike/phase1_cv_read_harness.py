"""SLAM Services - Phase 1 Azure CV Read prototype, harness-fed edition.

SPIKE-ONLY. NOT PART OF THE PRODUCTION PIPELINE.

Historical note (pre-G1): During the exploratory spike phase (Phases 0–7), all work was strictly limited to Scripts/spike/.
As of the G1 integration sprint (owner decision B1, 2026-05-27), authorized changes are now being made under App/
(see POST_SPIKE_INTEGRATION_PLAN.md §3 and the G1 kickoff prompt).

Do not modify production runtime behavior in App/local_enhanced_ocr.py, bank_statements.py, or app.py
without explicit owner approval and proper feature flags.

Purpose
-------
This is the harness-fed sibling of ``phase1_cv_read_prototype.py``.
It consumes the clean ``final_kept/`` PNG set produced by

    Scripts/spike/diagnose_check_deposit_cropper.py

(which uses a two-stage dedup that finally recovers the full ~12 photos
per imaging page = 49 checks + 7 deposit slips on
``Data/Auto_Body_Center_Jan_26_Statement.pdf``), and runs real Azure
Computer Vision Read against each crop. The earlier prototype was wired
to the older baseline ``cropped_checks/`` shape (transaction-linked,
~40-row strict cap) and could not see the deposit slips on page 5 at all.

What this script does (in order):
  1. Discover the harness ``final_kept/`` directory.
  2. Build the canonical crop list (raw + enhanced pair per photo).
  3. For each crop:
       a. Run local EasyOCR on the enhanced PNG (best-effort, mirrors the
          current production "extract payee from photo" path).
       b. Run Azure Computer Vision Read on the raw PNG (one call).
       c. Heuristically classify the crop as "check" / "deposit_slip" /
          "unknown" based on the Read text content (size+aspect were
          already validated upstream by the harness).
       d. Extract a best-guess payee for checks using the same spirit as
          the production ``_extract_payee_from_check_detections`` /
          ``_is_clean_payee`` logic (re-used via a read-only import).
  4. Write a grading CSV keyed by ``crop_id`` (== PNG stem). Columns
     include page, image_path, easyocr fields, cv_read fields,
     is_deposit, predicted_class, manual_grade (blank) and any matched
     check# from the MICR line if Read happened to surface one.
  5. Write a summary JSON + concise Markdown report.

Output bundle layout::

    Scripts/spike/artifacts/phase1_real_cv_read_harness_<UTC>/
    ├── side_by_side_harness.csv
    ├── summary_phase1_harness.json
    ├── phase1_harness_report.md
    └── raw_cv_responses/<crop_id>.json   (one file per crop)

Quick start (after the harness has been run and the F0 .env is in place)::

    # Default: real Azure CV Read on every crop in the latest harness run.
    python Scripts/spike/phase1_cv_read_harness.py --real

    # Specific harness output (recommended for reproducibility)
    python Scripts/spike/phase1_cv_read_harness.py --real \
        --harness-dir Scripts/spike/artifacts/crop_diagnosis_20260527T001907Z

    # Dry run (no Azure calls, only local EasyOCR + classifier)
    python Scripts/spike/phase1_cv_read_harness.py --dry-run

    # Skip EasyOCR if it is slow / unavailable in this environment
    python Scripts/spike/phase1_cv_read_harness.py --real --no-easyocr

Environment variables (loaded via python-dotenv from repo-root ``.env``)::

    AZURE_CV_ENDPOINT=https://<name>.cognitiveservices.azure.com/
    AZURE_CV_KEY=<primary or secondary key>

All artifacts live strictly under ``Scripts/spike/`` and never enter git
(see ``Scripts/spike/artifacts/.gitignore``).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
APP_DIR = REPO_ROOT / "App"
ARTIFACTS_DIR = REPO_ROOT / "Scripts" / "spike" / "artifacts"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

try:
    import local_enhanced_ocr as leo  # type: ignore  # noqa: E402
except Exception as exc:  # pragma: no cover - defensive
    leo = None  # type: ignore[assignment]
    print(f"[phase1-harness] WARNING: could not import production OCR helpers: {exc}", file=sys.stderr)

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(REPO_ROOT / ".env")
except Exception:
    pass


# ---------------------------------------------------------------------------
# Classification: heuristic-only, runs against the CV Read text per crop.
# Geometry is already validated by the harness so we lean entirely on text
# content. This is intentionally a "good enough for the spike" classifier.
# ---------------------------------------------------------------------------

DEPOSIT_KEYWORDS = (
    "deposit slip",
    "deposit ticket",
    "for deposit only",
    "total deposit",
    "less cash",
    "less cash received",
    "subtotal",
    "credit total",
    "deposit",
    "endorse here",
    "endorsement",
    "list checks singly",
    "checks or coupons",
    "currency",
    "coin",
    "ticket",
)

CHECK_KEYWORDS = (
    "pay to the order of",
    "pay to the",
    "order of",
    "memo",
    "void after",
    "dollars",
    "non-negotiable",
)


def classify_from_text(raw_text: str) -> tuple[str, float, list[str]]:
    """Return (predicted_class, confidence, matched_keywords).

    Predicted class is one of "deposit_slip", "check", "unknown".
    Confidence is a crude 0-1 score derived from keyword hits.
    """
    if not raw_text:
        return "unknown", 0.0, []

    low = raw_text.lower()
    matched: list[str] = []

    deposit_hits = 0
    for kw in DEPOSIT_KEYWORDS:
        if kw in low:
            deposit_hits += 1
            matched.append(f"+dep:{kw}")

    check_hits = 0
    for kw in CHECK_KEYWORDS:
        if kw in low:
            check_hits += 1
            matched.append(f"+chk:{kw}")

    # Strong deposit signals trump weak check overlap
    if deposit_hits >= 2 and deposit_hits >= check_hits:
        return "deposit_slip", min(0.5 + 0.15 * deposit_hits, 0.99), matched
    if check_hits >= 1 and check_hits > deposit_hits:
        return "check", min(0.6 + 0.10 * check_hits, 0.98), matched
    if deposit_hits >= 1:
        return "deposit_slip", 0.55, matched
    return "unknown", 0.25, matched


# ---------------------------------------------------------------------------
# Payee extraction — App/payee_extractor/ (G1 port). Harness keeps thin wrappers.
# ---------------------------------------------------------------------------

from payee_extractor import (  # noqa: E402
    apply_check_payee_rules,
    extract_payee_from_cv_lines as _engine_extract_payee,
    is_clean_payee as _engine_is_clean_payee,
    load_profile,
    looks_like_amount_line,
    resolve_bank_arg,
    resolve_check_rules_path,
)

_EXTRACTOR_BANK = "generic"
_EXTRACTOR_CLIENT: str | None = None
_EXTRACTOR_CHECK_RULES: Path | None = None


def configure_extractor(
    *,
    bank: str = "generic",
    client_name: str | None = None,
    check_rules_path: Path | None = None,
    register_page1_text: str | None = None,
    baseline_summary_path: Path | None = None,
) -> str:
    """Set module-level extractor options; returns resolved bank profile id."""
    global _EXTRACTOR_BANK, _EXTRACTOR_CLIENT, _EXTRACTOR_CHECK_RULES
    resolved = resolve_bank_arg(
        bank,
        client_name=client_name,
        register_page1_text=register_page1_text,
        baseline_summary_path=baseline_summary_path,
    )
    _EXTRACTOR_BANK = resolved
    _EXTRACTOR_CLIENT = client_name
    if check_rules_path is not None:
        _EXTRACTOR_CHECK_RULES = check_rules_path if check_rules_path.is_file() else None
    else:
        _EXTRACTOR_CHECK_RULES = resolve_check_rules_path()
    return resolved


def _active_profile():
    return load_profile(_EXTRACTOR_BANK)


def _is_clean_payee(text: str) -> bool:
    return _engine_is_clean_payee(text, _active_profile())


def extract_payee_from_cv_lines(lines: list[dict[str, Any]]) -> tuple[str, float, str]:
    """Pick the best payee candidate from Read lines."""
    payee, conf, reason = _engine_extract_payee(lines, _active_profile())
    if payee:
        cleaned, rule = apply_check_payee_rules(
            payee,
            rules_path=_EXTRACTOR_CHECK_RULES,
            client_name=_EXTRACTOR_CLIENT,
            bank_id=_EXTRACTOR_BANK,
        )
        if rule and cleaned != payee:
            return cleaned, conf, f"{reason}+check_rule"
        if rule:
            return cleaned, conf, reason
    return payee, conf, reason


# ---------------------------------------------------------------------------
# Check# extraction from MICR-ish bottom line (best effort)
# ---------------------------------------------------------------------------

_CHECK_NO_RE = re.compile(r"\b([0-9]{3,6})\b")


def guess_check_no(lines: list[dict[str, Any]]) -> str:
    """Best-effort: the top-right of a check is the check#.

    With CV Read we get bounding-box coords. We grab numeric tokens that
    appear in the upper-right quadrant of the crop (small relative bbox
    coordinates).
    """
    if not lines:
        return ""

    candidates: list[tuple[float, str]] = []
    for ln in lines:
        text = (ln.get("text") or "").strip()
        m = _CHECK_NO_RE.search(text)
        if not m:
            continue
        bbox = ln.get("bbox") or []
        if not bbox or len(bbox) < 8:
            continue
        x_left = min(bbox[0::2])
        y_top = min(bbox[1::2])
        candidates.append((y_top - x_left, m.group(1)))

    if not candidates:
        return ""
    candidates.sort(key=lambda t: t[0])
    return candidates[0][1]


# ---------------------------------------------------------------------------
# Azure CV Read client
# ---------------------------------------------------------------------------


def get_cv_client():
    from azure.cognitiveservices.vision.computervision import ComputerVisionClient
    from msrest.authentication import CognitiveServicesCredentials

    endpoint = os.getenv("AZURE_CV_ENDPOINT")
    key = os.getenv("AZURE_CV_KEY")
    if not endpoint or not key:
        return None
    return ComputerVisionClient(
        endpoint=endpoint,
        credentials=CognitiveServicesCredentials(key),
    )


def call_cv_read(client, image_path: Path, *, poll_secs: float = 1.0, max_polls: int = 25) -> dict[str, Any]:
    """One Read call on one image. Returns structured lines + raw text.

    Output shape:
        {
            "status": "succeeded" | "failed" | "timeout" | "error",
            "raw_text": "line1\nline2\n...",
            "lines": [{"text": str, "confidence": float, "bbox": [x1,y1,...]}],
            "line_count": int,
            "elapsed_ms": int,
            "error": str | None,
        }
    """
    from azure.cognitiveservices.vision.computervision.models import OperationStatusCodes

    started = time.time()
    try:
        with image_path.open("rb") as fh:
            result = client.read_in_stream(fh, raw=True)
    except Exception as exc:
        return {
            "status": "error",
            "raw_text": "",
            "lines": [],
            "line_count": 0,
            "elapsed_ms": int((time.time() - started) * 1000),
            "error": f"submit_failed: {exc}",
        }

    op_location = result.headers.get("Operation-Location") or result.headers.get("operation-location")
    if not op_location:
        return {
            "status": "error",
            "raw_text": "",
            "lines": [],
            "line_count": 0,
            "elapsed_ms": int((time.time() - started) * 1000),
            "error": "missing_operation_location",
        }
    operation_id = op_location.rstrip("/").split("/")[-1]

    final = None
    for _ in range(max_polls):
        read_result = client.get_read_result(operation_id)
        if read_result.status not in (OperationStatusCodes.not_started, OperationStatusCodes.running):
            final = read_result
            break
        time.sleep(poll_secs)

    if final is None:
        return {
            "status": "timeout",
            "raw_text": "",
            "lines": [],
            "line_count": 0,
            "elapsed_ms": int((time.time() - started) * 1000),
            "error": "poll_timeout",
        }

    if final.status != OperationStatusCodes.succeeded:
        return {
            "status": str(final.status).lower(),
            "raw_text": "",
            "lines": [],
            "line_count": 0,
            "elapsed_ms": int((time.time() - started) * 1000),
            "error": f"status={final.status}",
        }

    lines_out: list[dict[str, Any]] = []
    for page in final.analyze_result.read_results:
        for line in page.lines:
            lines_out.append(
                {
                    "text": line.text,
                    "confidence": float(getattr(line, "confidence", 0.0) or 0.0),
                    "bbox": list(line.bounding_box) if getattr(line, "bounding_box", None) else [],
                }
            )

    return {
        "status": "succeeded",
        "raw_text": "\n".join(ln["text"] for ln in lines_out),
        "lines": lines_out,
        "line_count": len(lines_out),
        "elapsed_ms": int((time.time() - started) * 1000),
        "error": None,
    }


# ---------------------------------------------------------------------------
# Optional local EasyOCR pass (for side-by-side honesty)
# ---------------------------------------------------------------------------

_easyocr_reader = None


def get_easyocr_reader():
    global _easyocr_reader
    if _easyocr_reader is not None:
        return _easyocr_reader
    try:
        import easyocr  # type: ignore

        _easyocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        return _easyocr_reader
    except Exception as exc:
        print(f"[phase1-harness] EasyOCR unavailable: {exc}", file=sys.stderr)
        return None


def call_easyocr(image_path: Path) -> dict[str, Any]:
    reader = get_easyocr_reader()
    if reader is None:
        return {"text": "", "payee": "", "confidence": 0.0, "available": False}
    try:
        detections = reader.readtext(str(image_path), detail=1, paragraph=False)
    except Exception as exc:
        return {"text": "", "payee": "", "confidence": 0.0, "available": False, "error": str(exc)}

    if leo is not None:
        try:
            payee, conf = leo._extract_payee_from_check_detections(detections)  # type: ignore[attr-defined]
        except Exception:
            payee, conf = "", 0.0
    else:
        payee, conf = "", 0.0

    text_concat = " | ".join(str(d[1]) for d in detections[:25])
    return {
        "text": text_concat,
        "payee": payee or "",
        "confidence": float(conf or 0.0),
        "available": True,
    }


# ---------------------------------------------------------------------------
# Discovery: the harness final_kept/ folder
# ---------------------------------------------------------------------------


@dataclass
class Crop:
    crop_id: str
    page: int
    raw_path: Path
    enh_path: Path | None
    width: int = 0
    height: int = 0
    aspect: float = 0.0


_STEM_RE = re.compile(
    r"^P(?P<page>\d+)_K(?P<idx>\d+)_w(?P<w>\d+)_h(?P<h>\d+)_a(?P<a>[0-9.]+)_final$"
)


def discover_crops(harness_dir: Path) -> list[Crop]:
    final_dir = harness_dir / "final_kept"
    if not final_dir.is_dir():
        raise FileNotFoundError(f"final_kept/ not found in {harness_dir}")

    raws: dict[str, Path] = {}
    enhs: dict[str, Path] = {}
    for p in sorted(final_dir.glob("*.png")):
        stem = p.stem
        if stem.endswith("_enh"):
            enhs[stem[:-4]] = p
        else:
            raws[stem] = p

    crops: list[Crop] = []
    for stem, raw_p in raws.items():
        m = _STEM_RE.match(stem)
        page = int(m.group("page")) if m else 0
        w = int(m.group("w")) if m else 0
        h = int(m.group("h")) if m else 0
        a = float(m.group("a")) if m else 0.0
        crop_id = stem.replace("_final", "")
        crops.append(
            Crop(
                crop_id=crop_id,
                page=page,
                raw_path=raw_p,
                enh_path=enhs.get(stem),
                width=w,
                height=h,
                aspect=a,
            )
        )

    crops.sort(key=lambda c: (c.page, c.crop_id))
    return crops


def latest_harness_dir() -> Path | None:
    candidates = sorted(ARTIFACTS_DIR.glob("crop_diagnosis_*"))
    return candidates[-1] if candidates else None


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class RowResult:
    crop_id: str
    page: int
    image_path: str
    width: int
    height: int
    aspect: float
    easyocr_text: str = ""
    easyocr_payee: str = ""
    easyocr_confidence: float = 0.0
    easyocr_available: bool = False
    cv_read_status: str = ""
    cv_read_line_count: int = 0
    cv_read_raw_text: str = ""
    cv_read_payee_candidate: str = ""
    cv_read_payee_confidence: float = 0.0
    cv_read_payee_reason: str = ""
    cv_read_is_clean: str = ""
    cv_read_elapsed_ms: int = 0
    cv_read_error: str = ""
    cv_read_guess_check_no: str = ""
    predicted_class: str = ""
    classifier_confidence: float = 0.0
    classifier_keywords: str = ""
    is_deposit: str = ""
    manual_grade: str = ""


def run_for_crop(crop: Crop, *, client, do_easyocr: bool, raw_resp_dir: Path) -> RowResult:
    row = RowResult(
        crop_id=crop.crop_id,
        page=crop.page,
        image_path=str(crop.raw_path.relative_to(REPO_ROOT)).replace("\\", "/"),
        width=crop.width,
        height=crop.height,
        aspect=crop.aspect,
    )

    if do_easyocr:
        easy_target = crop.enh_path or crop.raw_path
        easy = call_easyocr(easy_target)
        row.easyocr_text = easy.get("text", "")
        row.easyocr_payee = easy.get("payee", "")
        row.easyocr_confidence = round(float(easy.get("confidence", 0.0) or 0.0), 3)
        row.easyocr_available = bool(easy.get("available", False))

    if client is not None:
        cv = call_cv_read(client, crop.raw_path)
        row.cv_read_status = cv["status"]
        row.cv_read_line_count = cv["line_count"]
        row.cv_read_raw_text = cv["raw_text"]
        row.cv_read_elapsed_ms = cv["elapsed_ms"]
        row.cv_read_error = cv.get("error") or ""

        payee, p_conf, reason = extract_payee_from_cv_lines(cv["lines"])
        row.cv_read_payee_candidate = payee
        row.cv_read_payee_confidence = round(p_conf, 3)
        row.cv_read_payee_reason = reason
        row.cv_read_is_clean = "Yes" if (payee and _is_clean_payee(payee)) else "No"
        row.cv_read_guess_check_no = guess_check_no(cv["lines"])

        cls, c_conf, keywords = classify_from_text(cv["raw_text"])
        row.predicted_class = cls
        row.classifier_confidence = round(c_conf, 3)
        row.classifier_keywords = ";".join(keywords[:8])
        row.is_deposit = "Yes" if cls == "deposit_slip" else ("No" if cls == "check" else "Unknown")

        try:
            (raw_resp_dir / f"{crop.crop_id}.json").write_text(
                json.dumps(cv, indent=2, default=str), encoding="utf-8"
            )
        except Exception as exc:  # pragma: no cover
            print(f"[phase1-harness] could not write raw_resp for {crop.crop_id}: {exc}", file=sys.stderr)
    else:
        row.cv_read_status = "skipped"

    return row


def write_csv(rows: list[RowResult], out_path: Path) -> None:
    if not rows:
        out_path.write_text("", encoding="utf-8")
        return
    fields = list(asdict(rows[0]).keys())
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))


def write_summary(
    *,
    out_dir: Path,
    harness_dir: Path,
    rows: list[RowResult],
    use_real: bool,
    use_easyocr: bool,
) -> dict[str, Any]:
    total = len(rows)
    cv_succeeded = sum(1 for r in rows if r.cv_read_status == "succeeded")
    cv_clean_payees = sum(1 for r in rows if r.cv_read_is_clean == "Yes")
    easy_clean = sum(1 for r in rows if r.easyocr_payee and _is_clean_payee(r.easyocr_payee))
    deposits = sum(1 for r in rows if r.predicted_class == "deposit_slip")
    checks = sum(1 for r in rows if r.predicted_class == "check")
    unknowns = sum(1 for r in rows if r.predicted_class == "unknown")

    by_page: dict[int, dict[str, int]] = {}
    for r in rows:
        d = by_page.setdefault(r.page, {"total": 0, "check": 0, "deposit_slip": 0, "unknown": 0, "cv_clean": 0})
        d["total"] += 1
        d[r.predicted_class] = d.get(r.predicted_class, 0) + 1
        if r.cv_read_is_clean == "Yes":
            d["cv_clean"] += 1

    cost_per_txn = 0.0  # F0 free tier
    paid_cost_estimate = round(total * 0.0015, 4)  # if it were S1 / Group 2 first tier

    summary = {
        "spike": "Phase 1 harness-fed real CV Read (F0)",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "harness_dir": str(harness_dir.relative_to(REPO_ROOT)).replace("\\", "/"),
        "mode": "real" if use_real else "dry-run",
        "easyocr_enabled": use_easyocr,
        "totals": {
            "crops_processed": total,
            "cv_read_succeeded": cv_succeeded,
            "cv_read_clean_payees": cv_clean_payees,
            "cv_read_clean_pct": round(cv_clean_payees / total * 100, 1) if total else 0.0,
            "easyocr_clean_payees": easy_clean,
            "easyocr_clean_pct": round(easy_clean / total * 100, 1) if total else 0.0,
            "predicted_checks": checks,
            "predicted_deposits": deposits,
            "predicted_unknowns": unknowns,
        },
        "by_page": by_page,
        "cost": {
            "tier": "F0 (free, used in this run)",
            "calls": total,
            "free_tier_cost_usd": cost_per_txn,
            "would_cost_at_s1_group2_usd": paid_cost_estimate,
            "pricing_note": "F0: 5 000 free transactions / month, 20 calls / minute. "
            "Paid Group 2 Read ≈ $1.50 / 1 000 transactions (first tier).",
        },
    }

    (out_dir / "summary_phase1_harness.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    return summary


def write_report(summary: dict[str, Any], rows: list[RowResult], out_dir: Path) -> Path:
    totals = summary["totals"]
    cost = summary["cost"]
    by_page = summary["by_page"]
    by_page_md = "\n".join(
        f"- Page {pg}: total={d['total']}, checks={d.get('check',0)}, deposits={d.get('deposit_slip',0)}, "
        f"unknown={d.get('unknown',0)}, cv_clean_payees={d.get('cv_clean',0)}"
        for pg, d in sorted(by_page.items())
    )

    # Pull a few notable rows for the report
    notable = []
    for r in rows[:200]:
        if r.cv_read_status == "succeeded" and (
            r.cv_read_is_clean == "Yes" or r.predicted_class == "deposit_slip"
        ):
            notable.append(
                f"- `{r.crop_id}` (page {r.page}, class={r.predicted_class}): "
                f"CV Read payee = '{r.cv_read_payee_candidate}' "
                f"(conf {r.cv_read_payee_confidence}, {r.cv_read_payee_reason}) "
                f"| EasyOCR payee = '{r.easyocr_payee}' (conf {r.easyocr_confidence})"
            )
        if len(notable) >= 12:
            break

    md = f"""# Phase 1 — Harness-fed Azure CV Read (F0) Report

**Generated**: {summary['generated_utc']}  
**Harness output**: `{summary['harness_dir']}`  
**Mode**: {summary['mode']}  
**EasyOCR side-by-side**: {'enabled' if summary['easyocr_enabled'] else 'disabled'}

## Headline numbers

- Crops processed                : **{totals['crops_processed']}**
- CV Read calls succeeded        : **{totals['cv_read_succeeded']}**
- CV Read clean payees           : **{totals['cv_read_clean_payees']}** ({totals['cv_read_clean_pct']}%)
- EasyOCR clean payees           : **{totals['easyocr_clean_payees']}** ({totals['easyocr_clean_pct']}%)
- Predicted checks               : **{totals['predicted_checks']}**
- Predicted deposit slips        : **{totals['predicted_deposits']}**
- Unknown / ambiguous            : **{totals['predicted_unknowns']}**

## Per-page breakdown

{by_page_md}

## Cost (this run)

- Tier              : {cost['tier']}
- Calls             : {cost['calls']}
- Free-tier cost    : ${cost['free_tier_cost_usd']}
- If billed (S1 G2) : ${cost['would_cost_at_s1_group2_usd']}
- Note              : {cost['pricing_note']}

## Notable rows (CV Read clean or deposits)

{chr(10).join(notable) if notable else '_None yet — open the CSV and grade visually._'}

## How to grade (per spike plan §6)

1. Open `side_by_side_harness.csv` next to the `final_kept/*.png` files.
2. For each row, open the listed `image_path` (raw PNG, full resolution).
3. Compare against the visible "Pay to the order of" on the actual check
   photograph (or the deposit slip body) — never against any historical
   Grok Vision CSV Payee column.
4. Record your verdict in the `manual_grade` column
   (e.g. "CV correct", "CV wrong - should be X", "deposit ok",
   "deposit body unreadable", "still manual").

## Remaining manual payee effort (placeholder until manual grading is done)

The CV-Read-clean count above is the *upper bound* of automated payee
wins on this statement. Realistic remaining manual entry =
{totals['crops_processed']} – grader-confirmed-correct count.
Record the final number in `PHASE1_NOTES.md` after the visual grading
pass.

## Artifacts in this folder

- `side_by_side_harness.csv` — primary grading sheet
- `summary_phase1_harness.json` — machine-readable numbers
- `phase1_harness_report.md` — this file
- `raw_cv_responses/<crop_id>.json` — full Read response per crop

All work is strictly isolated under `Scripts/spike/`.
"""
    out_path = out_dir / "phase1_harness_report.md"
    out_path.write_text(md, encoding="utf-8")
    return out_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--harness-dir",
        type=Path,
        default=None,
        help="Path to a crop_diagnosis_<UTC>/ folder. Default: latest under artifacts/.",
    )
    p.add_argument(
        "--real",
        action="store_true",
        help="Call real Azure CV Read (requires AZURE_CV_* env vars). "
        "Without this flag the script runs in dry-run mode (no Azure calls).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Alias for the default when --real is not provided. Explicit for clarity.",
    )
    p.add_argument(
        "--no-easyocr",
        action="store_true",
        help="Skip local EasyOCR pass (much faster; only CV Read column is populated).",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N crops (useful for a smoke run before the full pass).",
    )
    p.add_argument(
        "--crop-ids",
        type=str,
        default=None,
        help=(
            "Comma-separated crop_id list to process (e.g. page-7 retry subset). "
            "When set, only matching crops are read; --limit applies after filtering."
        ),
    )
    p.add_argument(
        "--rate-limit-seconds",
        type=float,
        default=3.2,
        help=(
            "Minimum seconds between Azure CV Read submissions. F0 is capped at "
            "20 calls/min — the default 3.2s keeps us safely under that."
        ),
    )
    p.add_argument(
        "--rescore",
        type=Path,
        default=None,
        help=(
            "Re-score an existing run by re-extracting payees from the cached "
            "raw_cv_responses/*.json files. Argument is the existing "
            "phase1_real_cv_read_harness_* folder. Zero Azure cost. The output "
            "is written to --out-dir (default: <input>__rescored)."
        ),
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output folder. Default: artifacts/phase1_real_cv_read_harness_<UTC>/.",
    )
    p.add_argument(
        "--bank",
        type=str,
        default="generic",
        help="Bank profile: auto|traditions|regions|generic (default: generic).",
    )
    p.add_argument(
        "--client-name",
        type=str,
        default=None,
        help="Client name for --bank auto and check-scoped rules.",
    )
    p.add_argument(
        "--check-rules-path",
        type=Path,
        default=None,
        help="Optional check_payee_rules.csv (default: Data/check_payee_rules.csv if present).",
    )
    return p.parse_args(argv)


def resolve_out_dir(arg: Path | None) -> Path:
    if arg is not None:
        return arg
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return ARTIFACTS_DIR / f"phase1_real_cv_read_harness_{stamp}"


def rescore_existing(
    prev_dir: Path,
    out_dir: Path,
    *,
    bank: str = "generic",
    client_name: str | None = None,
    check_rules_path: Path | None = None,
) -> int:
    """Re-extract payees from cached raw_cv_responses/*.json + emit new CSV/report.

    Zero Azure cost. Used to evaluate extractor improvements (e.g. the
    courtesy-amount filter) without re-billing the F0 quota.
    """
    raw_dir = prev_dir / "raw_cv_responses"
    if not raw_dir.is_dir():
        print(f"ERROR: {raw_dir} not found.", file=sys.stderr)
        return 1
    prev_csv = prev_dir / "side_by_side_harness.csv"
    if not prev_csv.is_file():
        print(f"ERROR: {prev_csv} not found.", file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    new_raw_dir = out_dir / "raw_cv_responses"
    new_raw_dir.mkdir(exist_ok=True)

    resolved_bank = configure_extractor(
        bank=bank,
        client_name=client_name,
        check_rules_path=check_rules_path,
    )
    print(f"[rescore] bank profile: {_EXTRACTOR_BANK} (from --bank {bank!r})")

    prev_rows = {r["crop_id"]: r for r in csv.DictReader(open(prev_csv, encoding="utf-8"))}
    rows: list[RowResult] = []
    for json_path in sorted(raw_dir.glob("*.json")):
        crop_id = json_path.stem
        prev = prev_rows.get(crop_id, {})
        try:
            cv = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[rescore] could not read {json_path}: {exc}", file=sys.stderr)
            continue

        try:
            page = int(prev.get("page", "0"))
        except ValueError:
            page = 0

        row = RowResult(
            crop_id=crop_id,
            page=page,
            image_path=prev.get("image_path", ""),
            width=int(prev.get("width", 0) or 0),
            height=int(prev.get("height", 0) or 0),
            aspect=float(prev.get("aspect", 0.0) or 0.0),
            easyocr_text=prev.get("easyocr_text", ""),
            easyocr_payee=prev.get("easyocr_payee", ""),
            easyocr_confidence=float(prev.get("easyocr_confidence", 0.0) or 0.0),
            easyocr_available=(prev.get("easyocr_available", "False") == "True"),
            cv_read_status=cv.get("status", ""),
            cv_read_line_count=cv.get("line_count", 0),
            cv_read_raw_text=cv.get("raw_text", ""),
            cv_read_elapsed_ms=cv.get("elapsed_ms", 0),
            cv_read_error=cv.get("error") or "",
        )

        lines = cv.get("lines") or []
        payee, p_conf, reason = extract_payee_from_cv_lines(lines)
        row.cv_read_payee_candidate = payee
        row.cv_read_payee_confidence = round(p_conf, 3)
        row.cv_read_payee_reason = reason
        row.cv_read_is_clean = "Yes" if (payee and _is_clean_payee(payee) and not looks_like_amount_line(payee)) else "No"
        row.cv_read_guess_check_no = guess_check_no(lines)

        cls, c_conf, keywords = classify_from_text(cv.get("raw_text", ""))
        row.predicted_class = cls
        row.classifier_confidence = round(c_conf, 3)
        row.classifier_keywords = ";".join(keywords[:8])
        row.is_deposit = "Yes" if cls == "deposit_slip" else ("No" if cls == "check" else "Unknown")

        # Copy the raw response forward for repeatability
        try:
            (new_raw_dir / json_path.name).write_text(
                json_path.read_text(encoding="utf-8"), encoding="utf-8"
            )
        except Exception:
            pass

        rows.append(row)

    csv_path = out_dir / "side_by_side_harness.csv"
    write_csv(rows, csv_path)
    summary = write_summary(
        out_dir=out_dir,
        harness_dir=prev_dir,
        rows=rows,
        use_real=True,
        use_easyocr=True,
    )
    summary["rescore_source"] = str(prev_dir.relative_to(REPO_ROOT)).replace("\\", "/")
    summary["extractor_bank"] = resolved_bank
    (out_dir / "summary_phase1_harness.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    report_path = write_report(summary, rows, out_dir)

    totals = summary["totals"]
    print()
    print("=" * 72)
    print("Phase 1 RESCORE complete (zero Azure cost)")
    print("=" * 72)
    print(f"Source                  : {prev_dir.relative_to(REPO_ROOT)}")
    print(f"Crops re-scored         : {totals['crops_processed']}")
    print(f"CV Read clean payees    : {totals['cv_read_clean_payees']} "
          f"({totals['cv_read_clean_pct']}%)")
    print(f"Predicted checks/deps   : {totals['predicted_checks']}"
          f" / {totals['predicted_deposits']}"
          f" (unknown={totals['predicted_unknowns']})")
    print(f"CSV     : {csv_path.relative_to(REPO_ROOT)}")
    print(f"Report  : {report_path.relative_to(REPO_ROOT)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.rescore is not None:
        prev_dir = args.rescore.resolve()
        out_dir = resolve_out_dir(args.out_dir)
        if args.out_dir is None:
            suffix = "__rescored"
            if args.bank != "generic":
                suffix += f"_{args.bank.replace(' ', '')}"
            out_dir = prev_dir.parent / (prev_dir.name + suffix)
        return rescore_existing(
            prev_dir,
            out_dir.resolve(),
            bank=args.bank,
            client_name=args.client_name,
            check_rules_path=args.check_rules_path,
        )

    harness_dir = (args.harness_dir or latest_harness_dir() or Path()).resolve()
    if not harness_dir or not harness_dir.is_dir():
        print("ERROR: could not find a harness output. Run diagnose_check_deposit_cropper.py first.", file=sys.stderr)
        return 1
    print(f"[phase1-harness] Harness dir : {harness_dir}")

    crops = discover_crops(harness_dir)
    if args.crop_ids:
        wanted = {c.strip() for c in args.crop_ids.split(",") if c.strip()}
        crops = [c for c in crops if c.crop_id in wanted]
        missing = sorted(wanted - {c.crop_id for c in crops})
        if missing:
            print(f"[phase1-harness] WARNING: crop IDs not found in harness: {missing}", file=sys.stderr)
    if args.limit:
        crops = crops[: args.limit]
    if not crops:
        print(f"ERROR: no crops discovered in {harness_dir / 'final_kept'}", file=sys.stderr)
        return 1
    print(f"[phase1-harness] Crops found : {len(crops)}")

    out_dir = resolve_out_dir(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_resp_dir = out_dir / "raw_cv_responses"
    raw_resp_dir.mkdir(exist_ok=True)
    print(f"[phase1-harness] Output dir  : {out_dir}")

    configure_extractor(
        bank=args.bank,
        client_name=args.client_name,
        check_rules_path=args.check_rules_path,
    )
    print(f"[phase1-harness] Bank profile: {_EXTRACTOR_BANK}")

    use_real = bool(args.real) and not args.dry_run
    use_easyocr = not args.no_easyocr

    client = None
    if use_real:
        client = get_cv_client()
        if client is None:
            print(
                "[phase1-harness] AZURE_CV_ENDPOINT / AZURE_CV_KEY missing. "
                "Aborting real run. (Set them in .env at the repo root.)",
                file=sys.stderr,
            )
            return 2
        print("[phase1-harness] Azure CV Read client ready.")
    else:
        print("[phase1-harness] Dry-run mode (no Azure calls).")

    rows: list[RowResult] = []
    started = time.time()
    last_cv_call_at = 0.0
    for i, crop in enumerate(crops, 1):
        if client is not None:
            wait = args.rate_limit_seconds - (time.time() - last_cv_call_at)
            if wait > 0:
                time.sleep(wait)
        print(f"[phase1-harness] [{i:3d}/{len(crops)}] {crop.crop_id} (page {crop.page}) ...", end="", flush=True)
        try:
            row = run_for_crop(crop, client=client, do_easyocr=use_easyocr, raw_resp_dir=raw_resp_dir)
            rows.append(row)
        except Exception as exc:
            print(f" ERROR: {exc}")
            continue
        if client is not None:
            last_cv_call_at = time.time()
        cls = row.predicted_class or "-"
        payee = (row.cv_read_payee_candidate or "")[:36]
        print(f" cv={row.cv_read_status:>10s} class={cls:>12s} payee='{payee}'")

    csv_path = out_dir / "side_by_side_harness.csv"
    write_csv(rows, csv_path)
    print(f"[phase1-harness] Wrote {csv_path.relative_to(REPO_ROOT)} ({len(rows)} rows)")

    summary = write_summary(
        out_dir=out_dir,
        harness_dir=harness_dir,
        rows=rows,
        use_real=use_real,
        use_easyocr=use_easyocr,
    )
    report_path = write_report(summary, rows, out_dir)
    elapsed = int(time.time() - started)

    print()
    print("=" * 72)
    print("Phase 1 harness-fed CV Read run complete")
    print("=" * 72)
    print(f"Crops processed        : {summary['totals']['crops_processed']}")
    print(f"CV Read succeeded      : {summary['totals']['cv_read_succeeded']}")
    print(f"CV Read clean payees   : {summary['totals']['cv_read_clean_payees']} "
          f"({summary['totals']['cv_read_clean_pct']}%)")
    print(f"EasyOCR clean payees   : {summary['totals']['easyocr_clean_payees']} "
          f"({summary['totals']['easyocr_clean_pct']}%)")
    print(f"Predicted checks/deps  : {summary['totals']['predicted_checks']}"
          f" / {summary['totals']['predicted_deposits']}"
          f" (unknown={summary['totals']['predicted_unknowns']})")
    print(f"Free-tier cost         : ${summary['cost']['free_tier_cost_usd']} "
          f"(equiv S1 G2: ${summary['cost']['would_cost_at_s1_group2_usd']})")
    print(f"Wall time              : {elapsed}s")
    print()
    print(f"CSV     : {csv_path.relative_to(REPO_ROOT)}")
    print(f"Report  : {report_path.relative_to(REPO_ROOT)}")
    print()
    print("Open the CSV next to the PNGs in final_kept/ and grade visually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
