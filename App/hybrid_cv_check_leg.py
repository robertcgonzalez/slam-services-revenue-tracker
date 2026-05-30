"""Hybrid Azure CV Read check leg — configuration and shared helpers (G1 integration).

Check-image contract (wired in ``local_enhanced_ocr.run_pipeline``):

- The OpenCV cropper is geometry-only — it never runs EasyOCR on crop images.
- ``check_leg_mode="hybrid_cv"`` or ``None`` (auto): when :func:`cv_check_leg_available`
  is true (``AZURE_CV_*`` creds and/or ``SLAM_CV_CACHE_DIR``), imaging-page check crops
  use Azure Computer Vision Read, then ``App.payee_extractor`` + check rules.
- When CV is unavailable, crops are still produced for review but no automatic text is read.
- ``check_leg_mode="strict"``: skip the CV leg (no EasyOCR fallback on crops).

Sprint 3.3 makes CV the **default** check-photo leg for Local Enhanced when creds or
cache are present. ``SLAM_HYBRID_CV_ENABLED`` remains for optional production gating
later; Local Enhanced no longer requires it.

Secrets (never commit): ``AZURE_CV_ENDPOINT``, ``AZURE_CV_KEY`` — same pattern as
``AZURE_OCR_FUNCTION_URL`` / ``AZURE_OCR_FUNCTION_KEY`` in ``bank_statements.py``.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import time
from enum import Enum
from pathlib import Path
from typing import Any

from app_logging import format_pipeline_log as _hybrid_log

# Env var names (mirror AZURE_OCR_FUNCTION_* style in bank_statements.py)
AZURE_CV_ENDPOINT_ENV = "AZURE_CV_ENDPOINT"
AZURE_CV_KEY_ENV = "AZURE_CV_KEY"
SLAM_HYBRID_CV_ENABLED_ENV = "SLAM_HYBRID_CV_ENABLED"
SLAM_IMAGING_FIRST_PAGE_ENV = "SLAM_IMAGING_FIRST_PAGE"
SLAM_IMAGING_LAST_PAGE_ENV = "SLAM_IMAGING_LAST_PAGE"
SLAM_CV_CACHE_DIR_ENV = "SLAM_CV_CACHE_DIR"
SLAM_CLIENT_NAME_ENV = "SLAM_CLIENT_NAME"

DEFAULT_IMAGING_FIRST_PAGE = 5
DEFAULT_IMAGING_LAST_PAGE: int | None = None
DEFAULT_CV_RATE_LIMIT_SECONDS = 3.2

_CHECK_NO_RE = re.compile(r"\b([0-9]{3,6})\b")
# Pipeline cropper uses 0-based page index in check_id (P04C00 = physical page 5).
_PIPELINE_CROP_ID_RE = re.compile(r"^P(?P<page_idx>\d{2})C(?P<slot>\d{2})$")
# Phase-1 spike harness cache uses 1-based page + K slot: P05_K00_w1127_h453_a2.49.json
_SPIKE_CACHE_PREFIX_RE = re.compile(r"^P(?P<page>\d{2})_K(?P<slot>\d{2})_")


class CheckLegMode(str, Enum):
    STRICT = "strict"
    HYBRID_CV = "hybrid_cv"


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def is_hybrid_cv_enabled() -> bool:
    """Optional legacy feature flag — not required for Local Enhanced (Sprint 3.3)."""
    return _env_truthy(SLAM_HYBRID_CV_ENABLED_ENV)


def cv_check_leg_available() -> bool:
    """True when the CV check leg can run (live creds and/or dev cache directory)."""
    if azure_cv_configured():
        return True
    return _resolve_cv_cache_dir(None) is not None


def resolve_check_leg_mode(mode: str | CheckLegMode | None = None) -> CheckLegMode:
    """Normalize mode; auto-prefer hybrid when creds or cache are available."""
    if mode is not None and str(mode).strip():
        try:
            requested = CheckLegMode(str(mode).strip().lower())
        except ValueError:
            requested = CheckLegMode.STRICT
        if requested is CheckLegMode.STRICT:
            return CheckLegMode.STRICT
        return CheckLegMode.HYBRID_CV if cv_check_leg_available() else CheckLegMode.STRICT
    return CheckLegMode.HYBRID_CV if cv_check_leg_available() else CheckLegMode.STRICT


def _looks_like_placeholder_credential(value: str) -> bool:
    """True when .env still has sample/placeholder text from cv-read.env.sample."""
    lowered = value.strip().lower()
    if not lowered:
        return True
    placeholders = (
        "your-cv-resource",
        "your-primary-key",
        "changeme",
        "replace-me",
        "xxx",
        "<",
    )
    return any(token in lowered for token in placeholders)


def azure_cv_configured() -> bool:
    endpoint = (os.environ.get(AZURE_CV_ENDPOINT_ENV) or "").strip()
    key = (os.environ.get(AZURE_CV_KEY_ENV) or "").strip()
    if not endpoint or not key:
        return False
    if _looks_like_placeholder_credential(endpoint) or _looks_like_placeholder_credential(key):
        return False
    return True


def imaging_page_range(
    *,
    first_page: int | None = None,
    last_page: int | None = None,
) -> tuple[int, int | None]:
    """Resolve imaging page bounds (Traditions default: pages 5–9 on hard PDF)."""
    if first_page is None:
        raw = os.environ.get(SLAM_IMAGING_FIRST_PAGE_ENV, "").strip()
        first_page = int(raw) if raw.isdigit() else DEFAULT_IMAGING_FIRST_PAGE
    if last_page is None:
        raw = os.environ.get(SLAM_IMAGING_LAST_PAGE_ENV, "").strip()
        last_page = int(raw) if raw.isdigit() else DEFAULT_IMAGING_LAST_PAGE
    return first_page, last_page


def _spike_cache_sort_key(path: Path) -> tuple[int, str]:
    m = _SPIKE_CACHE_PREFIX_RE.match(path.name)
    if m:
        return (int(m.group("slot")), path.name)
    return (0, path.name)


def _page_ordered_cache_path(cache_dir: Path, page: int, slot_index: int) -> Path | None:
    """Fallback: pair pipeline crop order with spike ``P{page}_K{nn}`` sort order."""
    files = sorted(cache_dir.glob(f"P{page:02d}_K*.json"), key=_spike_cache_sort_key)
    if 0 <= slot_index < len(files):
        return files[slot_index]
    return None


def _cv_cache_paths_for_crop(
    cache_dir: Path,
    crop_id: str,
    *,
    page: int | None = None,
    width: int | None = None,
    height: int | None = None,
    page_slot_index: int | None = None,
) -> list[Path]:
    """Resolve cache JSON path(s) for a pipeline or spike crop id."""
    exact = cache_dir / f"{crop_id}.json"
    if exact.is_file():
        return [exact]

    m = _PIPELINE_CROP_ID_RE.match(crop_id)
    if m and page:
        slot = int(m.group("slot"))
        prefix = f"P{page:02d}_K{slot:02d}_"
        matches = sorted(cache_dir.glob(f"{prefix}*.json"))
        if matches:
            return matches

    # Spike harness names embed raster dimensions (w/h); pipeline slot order may differ.
    if page and width and height:
        dim_glob = f"P{page:02d}_K*_w{width}_h{height}_*.json"
        dim_matches = sorted(cache_dir.glob(dim_glob))
        if dim_matches:
            return dim_matches

    if page is not None and page_slot_index is not None:
        ordered = _page_ordered_cache_path(cache_dir, page, page_slot_index)
        if ordered is not None:
            return [ordered]

    # Spike harness crop_id stem (e.g. P05_K00_w1127_h453_a2.49)
    if _SPIKE_CACHE_PREFIX_RE.match(crop_id):
        return sorted(cache_dir.glob(f"{crop_id}.json")) + sorted(
            cache_dir.glob(f"{crop_id}_*.json")
        )

    return []


def load_cv_cache(
    cache_dir: Path,
    crop_id: str,
    *,
    page: int | None = None,
    width: int | None = None,
    height: int | None = None,
    page_slot_index: int | None = None,
) -> dict[str, Any] | None:
    """Load cached CV Read JSON for a crop (exact id or pipeline↔spike alias)."""
    for path in _cv_cache_paths_for_crop(
        cache_dir,
        crop_id,
        page=page,
        width=width,
        height=height,
        page_slot_index=page_slot_index,
    ):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
    return None


def save_cv_cache(cache_dir: Path, crop_id: str, payload: dict[str, Any]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{crop_id}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def cv_lines_to_easyocr_detections(lines: list[dict[str, Any]]) -> list[Any]:
    """Convert CV Read line dicts to EasyOCR-style (bbox, text, conf) tuples for matcher."""
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


def _page_in_imaging_range(page: int, first_page: int, last_page: int | None) -> bool:
    if page < first_page:
        return False
    if last_page is not None and page > last_page:
        return False
    return True


# ---------------------------------------------------------------------------
# Text classification (spike parity — heuristic on CV Read raw text)
# ---------------------------------------------------------------------------

_DEPOSIT_KEYWORDS = (
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

_CHECK_KEYWORDS = (
    "pay to the order of",
    "pay to the",
    "order of",
    "memo",
    "void after",
    "dollars",
    "non-negotiable",
)


def classify_from_text(raw_text: str) -> tuple[str, float, list[str]]:
    """Return (predicted_class, confidence, matched_keywords)."""
    if not raw_text:
        return "unknown", 0.0, []

    low = raw_text.lower()
    matched: list[str] = []

    deposit_hits = 0
    for kw in _DEPOSIT_KEYWORDS:
        if kw in low:
            deposit_hits += 1
            matched.append(f"+dep:{kw}")

    check_hits = 0
    for kw in _CHECK_KEYWORDS:
        if kw in low:
            check_hits += 1
            matched.append(f"+chk:{kw}")

    if deposit_hits >= 2 and deposit_hits >= check_hits:
        return "deposit_slip", min(0.5 + 0.15 * deposit_hits, 0.99), matched
    if check_hits >= 1 and check_hits > deposit_hits:
        return "check", min(0.6 + 0.10 * check_hits, 0.98), matched
    if deposit_hits >= 1:
        return "deposit_slip", 0.55, matched
    return "unknown", 0.25, matched


def guess_check_no(lines: list[dict[str, Any]]) -> str:
    """Best-effort check number from CV line bounding boxes (upper-right quadrant)."""
    if not lines:
        return ""

    candidates: list[tuple[float, str]] = []
    for ln in lines:
        text = (ln.get("text") or "").strip()
        match = _CHECK_NO_RE.search(text)
        if not match:
            continue
        bbox = ln.get("bbox") or []
        if not bbox or len(bbox) < 8:
            continue
        x_left = min(bbox[0::2])
        y_top = min(bbox[1::2])
        candidates.append((y_top - x_left, match.group(1)))

    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0])
    return candidates[-1][1]


# ---------------------------------------------------------------------------
# Azure Computer Vision Read client (optional SDK)
# ---------------------------------------------------------------------------


def get_cv_client() -> Any | None:
    """Return a ComputerVisionClient when SDK + env creds are available."""
    try:
        from azure.cognitiveservices.vision.computervision import ComputerVisionClient
        from msrest.authentication import CognitiveServicesCredentials
    except ImportError:
        return None

    endpoint = (os.environ.get(AZURE_CV_ENDPOINT_ENV) or "").strip()
    key = (os.environ.get(AZURE_CV_KEY_ENV) or "").strip()
    if not endpoint or not key:
        return None
    return ComputerVisionClient(
        endpoint=endpoint,
        credentials=CognitiveServicesCredentials(key),
    )


def call_cv_read_on_image(
    client: Any,
    image_bytes: bytes,
    *,
    poll_secs: float = 1.0,
    max_polls: int = 25,
) -> dict[str, Any]:
    """One Read call on image bytes. Same shape as spike ``call_cv_read``."""
    from azure.cognitiveservices.vision.computervision.models import OperationStatusCodes

    started = time.time()
    try:
        result = client.read_in_stream(io.BytesIO(image_bytes), raw=True)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "raw_text": "",
            "lines": [],
            "line_count": 0,
            "elapsed_ms": int((time.time() - started) * 1000),
            "error": f"submit_failed: {exc}",
        }

    op_location = result.headers.get("Operation-Location") or result.headers.get(
        "operation-location"
    )
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
        if read_result.status not in (
            OperationStatusCodes.not_started,
            OperationStatusCodes.running,
        ):
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


def call_cv_read_on_crop(
    client: Any,
    image_b64: str,
    *,
    poll_secs: float = 1.0,
    max_polls: int = 25,
) -> dict[str, Any]:
    """Read API entry for a base64 PNG crop from ``_crop_checks``."""
    try:
        image_bytes = base64.b64decode(image_b64)
    except (ValueError, TypeError) as exc:
        return {
            "status": "error",
            "raw_text": "",
            "lines": [],
            "line_count": 0,
            "elapsed_ms": 0,
            "error": f"invalid_b64: {exc}",
        }
    return call_cv_read_on_image(client, image_bytes, poll_secs=poll_secs, max_polls=max_polls)


def _resolve_cv_cache_dir(cache_dir: Path | str | None) -> Path | None:
    if cache_dir is not None:
        path = Path(cache_dir)
        return path if path.is_dir() else None
    raw = os.environ.get(SLAM_CV_CACHE_DIR_ENV, "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def _extract_payee_with_rules(
    lines: list[dict[str, Any]],
    *,
    bank_id: str,
    client_name: str | None,
    rules_path: Path | None,
) -> tuple[str, float, str]:
    payee, conf, reason = extract_payee_from_cv_lines(lines, bank_id)
    if not payee:
        return payee, conf, reason
    cleaned, rule = apply_check_payee_rules(
        payee,
        rules_path=rules_path,
        client_name=client_name,
        bank_id=bank_id,
    )
    if rule and cleaned != payee:
        return cleaned, conf, f"{reason}+check_rule"
    return cleaned, conf, reason


def run_hybrid_check_leg(
    cropped_checks: list[dict[str, Any]],
    detections_by_id: dict[str, list[Any]],
    *,
    register_page1_text: str | None = None,
    client_name: str | None = None,
    cache_dir: Path | str | None = None,
    write_cache_dir: Path | str | None = None,
    rate_limit_seconds: float = DEFAULT_CV_RATE_LIMIT_SECONDS,
    first_page: int | None = None,
    last_page: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, list[Any]], list[str]]:
    """3.2 — Azure CV Read on imaging-page crops; enrich ``detections_by_id`` for matcher.

    Only imaging-page crops classified as ``check`` receive CV-based detections (deposit
    slips are skipped for matcher). The cropper does not populate EasyOCR detections.
    """
    logs: list[str] = []
    first, last = imaging_page_range(first_page=first_page, last_page=last_page)
    resolved_cache = _resolve_cv_cache_dir(cache_dir)
    write_cache = Path(write_cache_dir) if write_cache_dir else resolved_cache

    if client_name is None:
        client_name = (os.environ.get(SLAM_CLIENT_NAME_ENV) or "").strip() or None

    bank_result = detect_bank(
        client_name=client_name,
        register_page1_text=register_page1_text,
    )
    bank_id = bank_result.bank_id
    rules_path = resolve_check_rules_path()

    logs.append(
        _hybrid_log(
            "info",
            f"Hybrid CV check leg: imaging pages {first}"
            f"{f'-{last}' if last is not None else '+'}; bank profile={bank_id!r}.",
        )
    )

    client = None
    if azure_cv_configured():
        client = get_cv_client()
        if client is None:
            logs.append(
                _hybrid_log(
                    "warn",
                    "AZURE_CV_* set but azure-cognitiveservices-vision-computervision "
                    "not installed — cache-only hybrid runs.",
                )
            )
    elif resolved_cache is None:
        logs.append(
            _hybrid_log(
                "warn",
                "Hybrid CV: no Azure credentials and no SLAM_CV_CACHE_DIR — "
                "skipping CV enrichment.",
            )
        )
        return cropped_checks, detections_by_id, logs

    scoped = [
        c for c in cropped_checks if _page_in_imaging_range(int(c.get("page") or 0), first, last)
    ]
    logs.append(
        _hybrid_log(
            "info",
            f"Hybrid CV: {len(scoped)}/{len(cropped_checks)} crop(s) in imaging page range.",
        )
    )

    cv_calls = 0
    checks_enriched = 0
    page_slot_counters: dict[int, int] = {}
    for idx, check in enumerate(scoped):
        check_id = str(check.get("check_id") or "")
        image_b64 = str(check.get("image_b64") or "")
        if not check_id or not image_b64:
            continue

        page_num = int(check.get("page") or 0)
        slot_on_page = page_slot_counters.get(page_num, 0)
        page_slot_counters[page_num] = slot_on_page + 1
        cached = (
            load_cv_cache(
                resolved_cache,
                check_id,
                page=page_num or None,
                width=int(check.get("width") or 0) or None,
                height=int(check.get("height") or 0) or None,
                page_slot_index=slot_on_page,
            )
            if resolved_cache
            else None
        )
        cv_result: dict[str, Any] | None = None

        if cached is not None:
            cv_result = {
                "status": str(cached.get("status") or "cached"),
                "raw_text": cached.get("raw_text") or "",
                "lines": cached.get("lines") or [],
            }
        elif client is not None:
            cv_result = call_cv_read_on_crop(client, image_b64)
            cv_calls += 1
            if write_cache is not None and cv_result.get("status") == "succeeded":
                save_cv_cache(
                    write_cache,
                    check_id,
                    {
                        "crop_id": check_id,
                        "page": check.get("page"),
                        "status": cv_result.get("status"),
                        "raw_text": cv_result.get("raw_text"),
                        "lines": cv_result.get("lines"),
                        "elapsed_ms": cv_result.get("elapsed_ms"),
                    },
                )
            if rate_limit_seconds > 0 and idx + 1 < len(scoped):
                time.sleep(rate_limit_seconds)
        else:
            continue

        if not cv_result or cv_result.get("status") not in ("succeeded", "cached"):
            continue

        raw_text = str(cv_result.get("raw_text") or "")
        lines = list(cv_result.get("lines") or [])
        predicted_class, _, _ = classify_from_text(raw_text)
        if predicted_class != "check":
            continue

        payee, payee_conf, _reason = _extract_payee_with_rules(
            lines,
            bank_id=bank_id,
            client_name=client_name,
            rules_path=rules_path,
        )
        profile = load_profile(bank_id)
        clean = bool(payee and is_clean_payee(payee, profile))
        guessed_no = guess_check_no(lines)

        detections_by_id[check_id] = cv_lines_to_easyocr_detections(lines)
        check["notes"] = "G1 hybrid CV Read (3.2)"
        if clean:
            check["extracted_payee"] = payee
            check["extracted_payee_confidence"] = round(float(payee_conf), 3)
        if guessed_no:
            check["extracted_check_number"] = guessed_no
        checks_enriched += 1

    logs.append(
        _hybrid_log(
            "info",
            f"Hybrid CV: {cv_calls} live Read call(s); {checks_enriched} check crop(s) "
            "enriched with CV detections.",
        )
    )
    return cropped_checks, detections_by_id, logs


# Re-export payee engine surface for integration callers (single import path).
try:
    from .payee_extractor import (  # noqa: E402
        apply_check_payee_rules,
        detect_bank,
        extract_payee_from_cv_lines,
        is_clean_payee,
        load_profile,
        resolve_bank_arg,
        resolve_check_rules_path,
    )
except ImportError:
    from payee_extractor import (  # type: ignore[no-redef]  # noqa: E402
        apply_check_payee_rules,
        detect_bank,
        extract_payee_from_cv_lines,
        is_clean_payee,
        load_profile,
        resolve_bank_arg,
        resolve_check_rules_path,
    )

__all__ = [
    "AZURE_CV_ENDPOINT_ENV",
    "AZURE_CV_KEY_ENV",
    "CheckLegMode",
    "DEFAULT_CV_RATE_LIMIT_SECONDS",
    "DEFAULT_IMAGING_FIRST_PAGE",
    "DEFAULT_IMAGING_LAST_PAGE",
    "SLAM_CLIENT_NAME_ENV",
    "SLAM_CV_CACHE_DIR_ENV",
    "SLAM_HYBRID_CV_ENABLED_ENV",
    "SLAM_IMAGING_FIRST_PAGE_ENV",
    "SLAM_IMAGING_LAST_PAGE_ENV",
    "apply_check_payee_rules",
    "azure_cv_configured",
    "cv_check_leg_available",
    "call_cv_read_on_crop",
    "call_cv_read_on_image",
    "classify_from_text",
    "cv_lines_to_easyocr_detections",
    "detect_bank",
    "extract_payee_from_cv_lines",
    "get_cv_client",
    "guess_check_no",
    "imaging_page_range",
    "is_clean_payee",
    "is_hybrid_cv_enabled",
    "load_cv_cache",
    "load_profile",
    "resolve_bank_arg",
    "resolve_check_leg_mode",
    "resolve_check_rules_path",
    "run_hybrid_check_leg",
    "save_cv_cache",
]
