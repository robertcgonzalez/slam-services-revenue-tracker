"""SLAM Services — Local Enhanced OCR pipeline (v2.43.2).

This module is an in-process port of the v2.43 Azure OCR Function pipeline
(`AzureFunctions/ocr_processor/function_app.py`) so the Streamlit Bank
Statements page can run the full intelligent check-linking workflow locally
for Robert while the Azure Function deploy remains parked on a Y1
Consumption infra decision (see Blueprint v2.43.1 Change Log).

The HTTP plumbing and `azure.functions` dependency are stripped. The actual
OCR stages (pdfplumber → easyocr fallback → opencv check cropping → check ↔
transaction matcher) and the canonical 12-column transaction shape are kept
byte-identical to the Function so v2.43.2 output drops straight into the same
review UI, payee rules engine, reconciliation banner, and Power Query /
Process-Statement.ps1 downstream workflow.

Heavy dependencies (`pdfplumber`, `pdf2image`, `easyocr`, `opencv-python(-headless)`,
`pillow`, `numpy`) are imported lazily inside the stages so the module can be
imported even when only a subset is installed — `detect_capabilities()` reports
which paths are available and the orchestrator in :func:`run_pipeline` skips
gracefully with a `[WARN]` log when a stage is unreachable.

Public surface:
- :data:`LOCAL_ENHANCED_OCR_VERSION` — pipeline version tag (mirrors Function)
- :data:`TRANSACTION_FIELDS` — canonical 12-column order
- :func:`detect_capabilities` — which optional libs are importable
- :func:`run_pipeline` — main entry; returns the same dict shape as the
  Function's ``_run_ocr_pipeline`` (``status``, ``transactions``,
  ``grok_totals``, ``cropped_checks``, ``logs``, ``message``)
"""

from __future__ import annotations

import base64
import difflib
import hashlib
import io
import os
import re
from datetime import datetime
from typing import Any

LOCAL_ENHANCED_OCR_VERSION = "v2.43.2"


def _is_codespaces() -> bool:
    """True when running inside a GitHub Codespace.

    Codespaces sets the ``CODESPACES=true`` environment variable
    automatically on every machine in the Codespaces fleet (also
    populated for `gh cs ssh` sessions). We use this to pick safer
    DPI / page / check-count defaults so the heavy OCR pipeline fits
    comfortably on the standard 4-core / 8 GB SKU without swapping.
    """

    return os.environ.get("CODESPACES", "").strip().lower() == "true"


# Default DPIs differ between Robert's local Windows machine (high RAM,
# plug for fidelity at 300/250) and a Codespaces container (resource-aware
# 200/180). Either default is overridable per-run via the SLAM_LOCAL_OCR_*
# env vars below — devcontainer.json sets the Codespaces values explicitly,
# but if the env vars are unset and we still detect Codespaces, fall back
# to the safer defaults so scripted runs are well-behaved.
_RUNTIME_IS_CODESPACES = _is_codespaces()
_DEFAULT_DPI_TEXT = "200" if _RUNTIME_IS_CODESPACES else "300"
_DEFAULT_DPI_CROP = "180" if _RUNTIME_IS_CODESPACES else "250"
_DEFAULT_MAX_PAGES_RASTER = "20" if _RUNTIME_IS_CODESPACES else "30"
_DEFAULT_MAX_CHECKS = "30" if _RUNTIME_IS_CODESPACES else "40"

# Canonical 12-column order — must match GROK_CSV_COLUMNS in bank_statements.py
# so the response drops straight into the existing review UI.
TRANSACTION_FIELDS: tuple[str, ...] = (
    "Date",
    "Description",
    "Payee",
    "Amount",
    "Check#",
    "Category",
    "SubCategory",
    "SignedAmount",
    "YearMonth",
    "Confidence",
    "NeedsReview",
    "ReviewReason",
)

# Pipeline tunables — kept aligned with the Function so behavior is identical
# on Robert's local Windows. In Codespaces we lower the defaults (see
# ``_DEFAULT_DPI_*`` above) so the heavy raster + EasyOCR stack fits in 8 GB
# RAM on the standard Codespaces SKU.
OCR_DPI_TEXT = int(os.environ.get("SLAM_LOCAL_OCR_DPI_TEXT", _DEFAULT_DPI_TEXT))
OCR_DPI_CROP = int(os.environ.get("SLAM_LOCAL_OCR_DPI_CROP", _DEFAULT_DPI_CROP))
OCR_MAX_PAGES_RASTER = int(
    os.environ.get("SLAM_LOCAL_OCR_MAX_PAGES_RASTER", _DEFAULT_MAX_PAGES_RASTER)
)
OCR_MAX_CHECKS = int(os.environ.get("SLAM_LOCAL_OCR_MAX_CHECKS", _DEFAULT_MAX_CHECKS))
OCR_FAST_PATH_MIN_ROWS = int(os.environ.get("SLAM_LOCAL_OCR_FAST_PATH_MIN_ROWS", "3"))

# Module-level cache for the heavy easyocr Reader — first call downloads the
# English model (~30-60s cold start); subsequent calls reuse the cached reader.
_EASYOCR_READER: Any = None


# ---------------------------------------------------------------------------
# Logging + capability detection
# ---------------------------------------------------------------------------


def _log(level: str, message: str) -> str:
    """Format a structured log line matching the Streamlit Processing log style."""

    return f"[{level.upper()}] {message}"


def environment_summary() -> dict[str, Any]:
    """Return a structured summary of the OCR runtime environment.

    Used by :func:`run_pipeline` to emit a clear startup log line and by
    the Streamlit sidebar / `slam-info` shell alias to inspect the active
    DPI / page / check-count tunables without running the pipeline.

    Keys:
        ``codespaces``         True when ``CODESPACES=true`` is set.
        ``codespace_name``     Codespaces machine name when available.
        ``dpi_text``           Active raster DPI for the EasyOCR fallback.
        ``dpi_crop``           Active raster DPI for the OpenCV cropper.
        ``max_pages_raster``   Cap on raster fallback pages per PDF.
        ``max_checks``         Cap on cropped checks per PDF.
        ``fast_path_min_rows`` Threshold below which the raster fallback runs.
    """

    return {
        "codespaces": _RUNTIME_IS_CODESPACES,
        "codespace_name": os.environ.get("CODESPACE_NAME", "") or None,
        "dpi_text": OCR_DPI_TEXT,
        "dpi_crop": OCR_DPI_CROP,
        "max_pages_raster": OCR_MAX_PAGES_RASTER,
        "max_checks": OCR_MAX_CHECKS,
        "fast_path_min_rows": OCR_FAST_PATH_MIN_ROWS,
    }


def _build_startup_logs() -> list[str]:
    """One-line startup banner for the Processing log expander.

    Surfaces the active DPI / page / check-count tunables on every run
    so Robert can immediately tell whether he's running with Codespaces-
    safe defaults or his Windows-local high-fidelity defaults — and so
    a future reviewer can correlate "0 cropped checks" against the DPI
    that was actually in effect.
    """

    summary = environment_summary()
    logs: list[str] = []
    if summary["codespaces"]:
        cs_name = summary["codespace_name"]
        suffix = f" ({cs_name})" if cs_name else ""
        logs.append(
            _log(
                "info",
                f"Local Enhanced OCR {LOCAL_ENHANCED_OCR_VERSION} starting in Codespaces{suffix}: "
                f"DPI text={summary['dpi_text']} / crop={summary['dpi_crop']}, "
                f"max pages={summary['max_pages_raster']}, max checks={summary['max_checks']}.",
            )
        )
        logs.append(
            _log(
                "warn",
                "Heavy OCR pipeline (easyocr+torch+opencv) can spike past 6 GB on multi-page "
                "scanned PDFs. If your Codespace was provisioned with the 4-core / 8 GB SKU, "
                "consider switching to the 4-core / 16 GB SKU (Codespaces -> Change machine "
                "type) before running OCR on a >10-page statement.",
            )
        )
    else:
        logs.append(
            _log(
                "info",
                f"Local Enhanced OCR {LOCAL_ENHANCED_OCR_VERSION} starting (local mode): "
                f"DPI text={summary['dpi_text']} / crop={summary['dpi_crop']}, "
                f"max pages={summary['max_pages_raster']}, max checks={summary['max_checks']}.",
            )
        )
    return logs


def detect_capabilities() -> dict[str, bool]:
    """Report which optional OCR libraries are importable in this environment.

    Used by :func:`bank_statements.local_enhanced_ocr_available` so the
    Streamlit UI can show a clear "missing libs — falling back to Lightweight
    Parser" warning instead of silently degrading.
    """

    caps = {
        "pdfplumber": False,
        "pdf2image": False,
        "easyocr": False,
        "opencv": False,
        "pillow": False,
        "numpy": False,
    }
    try:
        import pdfplumber  # noqa: F401, PLC0415

        caps["pdfplumber"] = True
    except Exception:
        pass
    try:
        import pdf2image  # noqa: F401, PLC0415

        caps["pdf2image"] = True
    except Exception:
        pass
    try:
        import easyocr  # noqa: F401, PLC0415

        caps["easyocr"] = True
    except Exception:
        pass
    try:
        import cv2  # noqa: F401, PLC0415

        caps["opencv"] = True
    except Exception:
        pass
    try:
        import PIL  # noqa: F401, PLC0415

        caps["pillow"] = True
    except Exception:
        pass
    try:
        import numpy  # noqa: F401, PLC0415

        caps["numpy"] = True
    except Exception:
        pass
    return caps


# ---------------------------------------------------------------------------
# Main orchestrator (ported from function_app._run_ocr_pipeline)
# ---------------------------------------------------------------------------


def run_pipeline(pdf_bytes: bytes) -> dict[str, Any]:
    """Run the full v2.43 OCR pipeline locally and return the structured result.

    Strategy:
        1. ``pdfplumber`` fast path → text + words + tables → regex parser.
        2. If transaction count < ``OCR_FAST_PATH_MIN_ROWS``, raster fallback
           via ``pdf2image`` + ``easyocr`` at ``OCR_DPI_TEXT``.
        3. Always attempt the OpenCV check cropper at ``OCR_DPI_CROP``;
           skip gracefully if cv2/PIL/pdf2image/easyocr aren't installed.
        4. v2.43 matcher — link each cropped check to its best-matching
           transaction (Check# → amount → fuzzy payee) and enrich Payee from
           the "Pay to the order of" line on the check image.

    Returns the same dict shape as the Function's ``_run_ocr_pipeline``:
    ``{status, transactions, grok_totals, cropped_checks, logs, message}``.
    """

    pipeline_logs: list[str] = list(_build_startup_logs())
    transactions: list[dict[str, Any]] = []
    cropped_checks: list[dict[str, Any]] = []
    detections_by_id: dict[str, list[Any]] = {}
    fast_path_rows = 0
    fallback_rows = 0
    default_year = datetime.utcnow().year

    # 1) pdfplumber fast path -------------------------------------------------
    try:
        text_blob, tables, fast_logs, statement_year = _extract_pdfplumber(pdf_bytes)
        pipeline_logs.extend(fast_logs)
        default_year = statement_year or default_year

        if text_blob.strip():
            lines = [ln.strip() for ln in text_blob.splitlines() if ln.strip()]
            line_rows = _parse_lines_to_transactions(lines, default_year)
            table_rows = _parse_table_rows(tables, default_year) if tables else []
            merged = _dedupe_transactions(line_rows + table_rows)
            merged = _filter_balance_only_rows(merged)
            transactions = merged
            fast_path_rows = len(transactions)
            pipeline_logs.append(
                _log(
                    "info",
                    f"pdfplumber fast path produced {fast_path_rows} transaction(s) "
                    f"({len(line_rows)} from text lines, {len(table_rows)} from tables).",
                )
            )
        else:
            pipeline_logs.append(
                _log(
                    "warn",
                    "pdfplumber returned no text layer (likely a scanned/image PDF).",
                )
            )
    except ModuleNotFoundError as exc:
        pipeline_logs.append(_log("warn", f"pdfplumber unavailable — skipping fast path ({exc})."))
    except Exception as exc:  # noqa: BLE001 — degrade to OCR fallback
        pipeline_logs.append(
            _log("warn", f"pdfplumber fast path failed: {exc}. Falling back to raster OCR.")
        )

    # 2) Raster + EasyOCR fallback -------------------------------------------
    if fast_path_rows < OCR_FAST_PATH_MIN_ROWS:
        pipeline_logs.append(
            _log(
                "info",
                f"Fast path returned {fast_path_rows} rows (< {OCR_FAST_PATH_MIN_ROWS}); "
                f"running EasyOCR fallback at {OCR_DPI_TEXT} DPI.",
            )
        )
        try:
            ocr_lines, ocr_logs = _ocr_extract_lines(pdf_bytes)
            pipeline_logs.extend(ocr_logs)
            if ocr_lines:
                fallback_txns = _parse_lines_to_transactions(
                    ocr_lines, default_year, source="easyocr"
                )
                fallback_txns = _filter_balance_only_rows(_dedupe_transactions(fallback_txns))
                fallback_rows = len(fallback_txns)
                pipeline_logs.append(
                    _log(
                        "info",
                        f"EasyOCR fallback produced {fallback_rows} transaction(s) "
                        f"from {len(ocr_lines)} OCR line(s).",
                    )
                )
                transactions = _dedupe_transactions(transactions + fallback_txns)
                transactions = _filter_balance_only_rows(transactions)
        except ModuleNotFoundError as exc:
            pipeline_logs.append(
                _log(
                    "warn",
                    f"Raster OCR libraries unavailable ({exc}). "
                    "Install pdf2image + easyocr + pillow to enable the scanned fallback.",
                )
            )
        except Exception as exc:  # noqa: BLE001 — never crash the request
            pipeline_logs.append(_log("error", f"EasyOCR fallback failed: {exc}"))

    # 3) Check cropping (best-effort) ----------------------------------------
    try:
        cropped_checks, detections_by_id, crop_logs = _crop_checks(pdf_bytes)
        pipeline_logs.extend(crop_logs)
    except ModuleNotFoundError as exc:
        pipeline_logs.append(
            _log(
                "warn",
                f"Check cropper unavailable ({exc}). Install opencv-python-headless + "
                "pdf2image + easyocr + pillow to enable cropped-check images.",
            )
        )
    except Exception as exc:  # noqa: BLE001 — cropping is optional
        pipeline_logs.append(_log("warn", f"Check cropper failed: {exc}"))

    # 4) Canonicalize → 12-column shape
    canonical = [
        {field: row.get(field, "") for field in TRANSACTION_FIELDS} for row in transactions
    ]

    # 5) v2.43 — link cropped checks to transactions + enrich Payee from image.
    try:
        canonical, cropped_checks, match_logs = _match_checks_to_transactions(
            canonical, cropped_checks, detections_by_id
        )
        pipeline_logs.extend(match_logs)
    except Exception as exc:  # noqa: BLE001 — matcher is best-effort
        pipeline_logs.append(_log("warn", f"Check-to-transaction matcher failed: {exc}"))

    grok_totals = _compute_grok_totals(canonical)
    linked_count = sum(1 for row in canonical if row.get("linked_check_id"))

    if canonical and (fast_path_rows >= OCR_FAST_PATH_MIN_ROWS or fallback_rows >= 1):
        status = "success"
        message = (
            f"Local Enhanced OCR extracted {len(canonical)} transaction(s) "
            f"(fast path: {fast_path_rows}, OCR fallback: {fallback_rows}, "
            f"cropped checks: {len(cropped_checks)}, linked checks: {linked_count})."
        )
    elif canonical:
        status = "partial"
        message = (
            f"Local Enhanced OCR extracted {len(canonical)} transaction(s) but below the "
            f"confidence threshold — please review."
        )
    else:
        status = "partial"
        message = (
            "Local Enhanced OCR returned zero transactions. The PDF may have an "
            "unsupported layout or the raster libraries are not installed."
        )

    return {
        "status": status,
        "transactions": canonical,
        "grok_totals": grok_totals,
        "cropped_checks": cropped_checks,
        "logs": pipeline_logs,
        "message": message,
        "fast_path_rows": fast_path_rows,
        "fallback_rows": fallback_rows,
        "linked_count": linked_count,
    }


def _compute_grok_totals(transactions: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute reconciliation totals (matches Grok TOTALS line shape)."""

    deposits = 0.0
    withdrawals = 0.0
    checks = 0
    for row in transactions:
        signed_raw = str(row.get("SignedAmount") or row.get("Amount") or "").strip()
        try:
            val = float(signed_raw.replace(",", "")) if signed_raw else 0.0
        except ValueError:
            val = 0.0
        if val > 0:
            deposits += val
        elif val < 0:
            withdrawals += abs(val)
        if str(row.get("Check#", "")).strip():
            checks += 1

    return {
        "deposits": round(deposits, 2),
        "withdrawals": round(withdrawals, 2),
        "checks": checks,
        "transactions": len(transactions),
    }


# ---------------------------------------------------------------------------
# pdfplumber fast path
# ---------------------------------------------------------------------------


def _extract_pdfplumber(
    pdf_bytes: bytes,
) -> tuple[str, list[list[list[Any]]], list[str], int | None]:
    """Open the PDF with pdfplumber and return (text_blob, tables, logs, statement_year)."""

    import pdfplumber  # noqa: PLC0415 — heavy import; only load when fast path is used

    logs: list[str] = []
    chunks: list[str] = []
    all_tables: list[list[list[Any]]] = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        logs.append(_log("info", f"pdfplumber opened PDF ({len(pdf.pages)} page(s))."))
        for page_idx, page in enumerate(pdf.pages):
            try:
                text = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
                if not text.strip():
                    text = page.extract_text(x_tolerance=1, y_tolerance=1, layout=True) or ""
                if text.strip():
                    chunks.append(text)

                words = page.extract_words() or []
                if words and not text.strip():
                    chunks.append("\n".join(_words_to_lines(words)))

                for table in page.extract_tables() or []:
                    all_tables.append(table)
                    for row in table:
                        if not row:
                            continue
                        cells = [str(c or "").strip() for c in row if c]
                        if cells:
                            chunks.append(" | ".join(cells))
            except Exception as exc:  # noqa: BLE001 — never let one page break extraction
                logs.append(
                    _log("warn", f"pdfplumber page {page_idx + 1} extraction failed: {exc}")
                )

    text_blob = "\n".join(chunks)
    statement_year = _infer_statement_year(text_blob)
    if statement_year:
        logs.append(_log("info", f"Inferred statement year: {statement_year}."))
    return text_blob, all_tables, logs, statement_year


# ---------------------------------------------------------------------------
# EasyOCR fallback
# ---------------------------------------------------------------------------


def _get_easyocr_reader() -> Any:
    """Lazy-load and cache the EasyOCR Reader so warm calls don't reload models."""

    global _EASYOCR_READER
    if _EASYOCR_READER is not None:
        return _EASYOCR_READER

    import easyocr  # noqa: PLC0415

    _EASYOCR_READER = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _EASYOCR_READER


def _ocr_extract_lines(pdf_bytes: bytes) -> tuple[list[str], list[str]]:
    """Rasterize each page + run EasyOCR; return (ordered_text_lines, logs)."""

    import numpy as np  # noqa: PLC0415
    from pdf2image import convert_from_bytes  # noqa: PLC0415

    logs: list[str] = []
    pages = convert_from_bytes(pdf_bytes, dpi=OCR_DPI_TEXT)
    if not pages:
        logs.append(_log("warn", "pdf2image returned 0 pages — nothing to OCR."))
        return [], logs

    if len(pages) > OCR_MAX_PAGES_RASTER:
        logs.append(
            _log(
                "warn",
                f"PDF has {len(pages)} pages but OCR_MAX_PAGES_RASTER={OCR_MAX_PAGES_RASTER}; "
                "truncating raster fallback to keep memory in bounds.",
            )
        )
        pages = pages[:OCR_MAX_PAGES_RASTER]

    reader = _get_easyocr_reader()
    logs.append(_log("info", f"EasyOCR reader ready; running on {len(pages)} page(s)."))

    all_lines: list[str] = []
    for page_idx, page in enumerate(pages):
        try:
            img = np.array(page)
            detections = reader.readtext(img, detail=1, paragraph=False)
            page_lines = _easyocr_to_lines(detections)
            all_lines.extend(page_lines)
            logs.append(
                _log(
                    "info",
                    f"EasyOCR page {page_idx + 1}: {len(detections)} token(s) → "
                    f"{len(page_lines)} line(s).",
                )
            )
        except Exception as exc:  # noqa: BLE001 — keep going on the next page
            logs.append(_log("warn", f"EasyOCR page {page_idx + 1} failed: {exc}"))

    return all_lines, logs


def _easyocr_to_lines(detections: list[Any], y_tolerance: float = 20.0) -> list[str]:
    """Group EasyOCR token detections by y-coordinate and return ordered text lines."""

    buckets: dict[int, list[tuple[float, str]]] = {}
    for det in detections:
        try:
            bbox, text, _conf = det
            ys = [pt[1] for pt in bbox]
            xs = [pt[0] for pt in bbox]
            y_center = (min(ys) + max(ys)) / 2.0
            x_left = min(xs)
        except Exception:
            continue
        key = int(round(y_center / y_tolerance))
        buckets.setdefault(key, []).append((x_left, str(text)))

    lines: list[str] = []
    for key in sorted(buckets):
        row = sorted(buckets[key], key=lambda t: t[0])
        line = " ".join(text for _, text in row if text and text.strip())
        if line.strip():
            lines.append(line.strip())
    return lines


# ---------------------------------------------------------------------------
# Check cropping (port of Scripts/smart_check_cropper_final_dynamic.py)
# ---------------------------------------------------------------------------


_CROP_MIN_WIDTH = 100
_CROP_MAX_WIDTH = 1500
_CROP_MIN_HEIGHT = 320
_CROP_MAX_HEIGHT = 900
_CROP_MIN_ASPECT = 2.0
_CROP_MAX_ASPECT = 3.2
_CROP_OCR_TEXT_THRESHOLD = 0.25
_CROP_CONTRAST_FACTOR = 3.5
_CROP_CHECK_KEYWORDS = ("pay to", "order of", "memo", "dollars")
_CROP_JUNK_KEYWORDS = (
    "telephone us at",
    "p.o. box 1125",
    "in case of errors",
    "cullman, al 35056",
)


def _crop_checks(
    pdf_bytes: bytes,
) -> tuple[list[dict[str, Any]], dict[str, list[Any]], list[str]]:
    """Detect, crop, and validate check images. Returns (checks, detections_by_id, logs)."""

    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    from pdf2image import convert_from_bytes  # noqa: PLC0415
    from PIL import Image, ImageEnhance  # noqa: PLC0415

    logs: list[str] = []
    pages = convert_from_bytes(pdf_bytes, dpi=OCR_DPI_CROP)
    if not pages:
        logs.append(_log("info", "Check cropper: pdf2image returned 0 pages."))
        return [], {}, logs

    if len(pages) > OCR_MAX_PAGES_RASTER:
        pages = pages[:OCR_MAX_PAGES_RASTER]

    reader = _get_easyocr_reader()
    logs.append(_log("info", f"Check cropper scanning {len(pages)} page(s) at {OCR_DPI_CROP} DPI."))

    seen_hashes: set[str] = set()
    checks: list[dict[str, Any]] = []
    detections_by_id: dict[str, list[Any]] = {}
    check_counter = 0

    for page_idx, page in enumerate(pages):
        if len(checks) >= OCR_MAX_CHECKS:
            logs.append(_log("warn", f"Hit OCR_MAX_CHECKS={OCR_MAX_CHECKS}; stopping cropper."))
            break

        img = np.array(page)
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        thresholds = [
            cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 9, 3
            ),
            cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 11, 2
            ),
            cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY_INV)[1],
        ]

        page_hits = 0
        for thresh_idx, thresh in enumerate(thresholds):
            kernel = np.ones((3, 3), np.uint8)
            dilated = cv2.dilate(thresh, kernel, iterations=2)
            contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for cnt in contours:
                if len(checks) >= OCR_MAX_CHECKS:
                    break

                x, y, w, h = cv2.boundingRect(cnt)
                if not (_CROP_MIN_WIDTH < w < _CROP_MAX_WIDTH):
                    continue
                if not (_CROP_MIN_HEIGHT < h < _CROP_MAX_HEIGHT):
                    continue
                aspect = w / h if h else 0
                if not (_CROP_MIN_ASPECT < aspect < _CROP_MAX_ASPECT):
                    continue

                cropped = img[y : y + h, x : x + w]
                cropped_pil = Image.fromarray(cropped).convert("RGB")
                enhanced = (
                    ImageEnhance.Contrast(cropped_pil.convert("L"))
                    .enhance(_CROP_CONTRAST_FACTOR)
                    .convert("RGB")
                )
                enhanced_np = np.array(enhanced)

                try:
                    detections = reader.readtext(
                        enhanced_np,
                        detail=1,
                        paragraph=False,
                        text_threshold=_CROP_OCR_TEXT_THRESHOLD,
                    )
                except Exception:
                    continue
                text_tokens = [str(d[1]) for d in detections if len(d) >= 2 and d[1]]
                full_text = " ".join(text_tokens).lower()

                if any(kw in full_text for kw in _CROP_JUNK_KEYWORDS):
                    continue
                if not any(kw in full_text for kw in _CROP_CHECK_KEYWORDS) and len(full_text) < 20:
                    continue

                img_hash = _simple_image_hash(enhanced_np)
                if img_hash in seen_hashes:
                    continue
                seen_hashes.add(img_hash)

                buf = io.BytesIO()
                enhanced.save(buf, format="PNG", optimize=True)
                b64 = base64.b64encode(buf.getvalue()).decode("ascii")

                check_id = f"P{page_idx:02d}C{check_counter:02d}"
                checks.append(
                    {
                        "check_id": check_id,
                        "page": page_idx + 1,
                        "width": int(w),
                        "height": int(h),
                        "aspect_ratio": round(float(aspect), 3),
                        "image_b64": b64,
                        "notes": f"v2.43.2 local grid+dedup (thresh {thresh_idx})",
                    }
                )
                detections_by_id[check_id] = detections
                check_counter += 1
                page_hits += 1

        if page_hits:
            logs.append(
                _log("info", f"Check cropper page {page_idx + 1}: {page_hits} candidate(s).")
            )

    logs.append(_log("info", f"Check cropper extracted {len(checks)} unique check(s)."))
    return checks, detections_by_id, logs


def _simple_image_hash(img_array: Any) -> str:
    """Cheap perceptual hash (matches Scripts/smart_check_cropper_final_dynamic.py)."""

    from PIL import Image  # noqa: PLC0415

    pil_img = Image.fromarray(img_array).resize((8, 8)).convert("L")
    pixels = list(pil_img.getdata())
    avg = sum(pixels) / len(pixels) if pixels else 0
    bits = "".join("1" if p > avg else "0" for p in pixels)
    return hashlib.md5(bits.encode()).hexdigest()


# ---------------------------------------------------------------------------
# v2.43 — Check ↔ transaction matcher + payee extraction from check images
# ---------------------------------------------------------------------------

_PAYEE_LINE_NOISE_TOKENS = frozenset(
    {
        "pay",
        "to",
        "the",
        "order",
        "of",
        "payee",
        "$",
        ":",
        ".",
        "-",
        "*",
        "**",
    }
)

_PAYEE_TRAILING_AMOUNT_RE = re.compile(r"\s*\$?\s*-?\d{1,3}(?:,\d{3})*\.\d{2}\s*$")
_PAYEE_AMOUNT_ONLY_RE = re.compile(r"^\s*\$?\s*-?\d{1,3}(?:,\d{3})*\.\d{2}\s*$")
_PAYEE_LINE_PREFIX_RE = re.compile(
    r"^(?:pay(?:ee)?(?:\s+to)?(?:\s+the)?(?:\s+order)?(?:\s+of)?[:\s\-*$]*)+",
    re.IGNORECASE,
)
_CHECK_IMAGE_AMOUNT_RE = re.compile(r"\$\s*(\d{1,3}(?:,\d{3})*\.\d{2})")
_FUZZY_MIN = 0.60
_AMOUNT_MATCH_TOLERANCE = 0.01


def _norm_check_no(raw: str) -> str:
    """Normalize a check number for matching (strip non-digits + leading zeros)."""

    digits = re.sub(r"\D+", "", str(raw or ""))
    if not digits:
        return ""
    stripped = digits.lstrip("0")
    return stripped or digits


def _bucket_detections_by_line(
    detections: list[Any], y_tolerance: float = 18.0
) -> list[dict[str, Any]]:
    """Group EasyOCR token detections into rough lines, sorted top-to-bottom."""

    if not detections:
        return []

    buckets: dict[int, list[dict[str, Any]]] = {}
    for det in detections:
        try:
            bbox, text, conf = det[0], det[1], det[2] if len(det) >= 3 else 0.0
            xs = [pt[0] for pt in bbox]
            ys = [pt[1] for pt in bbox]
            if not xs or not ys:
                continue
            x_left, x_right = float(min(xs)), float(max(xs))
            y_top, y_bottom = float(min(ys)), float(max(ys))
            y_center = (y_top + y_bottom) / 2.0
        except Exception:
            continue
        token = str(text or "").strip()
        if not token:
            continue
        key = int(round(y_center / y_tolerance))
        buckets.setdefault(key, []).append(
            {
                "text": token,
                "conf": float(conf or 0.0),
                "x_left": x_left,
                "x_right": x_right,
                "y_center": y_center,
            }
        )

    lines: list[dict[str, Any]] = []
    for key in sorted(buckets):
        row = sorted(buckets[key], key=lambda t: t["x_left"])
        joined = " ".join(t["text"] for t in row)
        lines.append(
            {
                "y_center": sum(t["y_center"] for t in row) / len(row),
                "text": joined,
                "tokens": row,
            }
        )
    return lines


def _extract_check_number_from_detections(detections: list[Any]) -> str:
    """Find a 3-6 digit token in the upper-right of the check image."""

    if not detections:
        return ""

    tokens: list[tuple[float, float, str]] = []
    max_x = 0.0
    max_y = 0.0
    for det in detections:
        try:
            bbox, text, _ = det[0], det[1], det[2] if len(det) >= 3 else 0.0
            xs = [pt[0] for pt in bbox]
            ys = [pt[1] for pt in bbox]
            if not xs or not ys:
                continue
            x_c = (min(xs) + max(xs)) / 2.0
            y_c = (min(ys) + max(ys)) / 2.0
        except Exception:
            continue
        token = str(text or "").strip()
        if not token:
            continue
        max_x = max(max_x, x_c)
        max_y = max(max_y, y_c)
        tokens.append((y_c, x_c, token))

    if not tokens or max_x == 0:
        return ""

    top_y_cutoff = max_y * 0.40
    right_x_cutoff = max_x * 0.45

    best_score = -1.0
    best_check = ""
    for y_c, x_c, token in tokens:
        if y_c > top_y_cutoff or x_c < right_x_cutoff:
            continue
        m = re.fullmatch(r"\*?\s*(\d{3,6})\s*\*?", token)
        if not m:
            continue
        score = x_c - y_c
        if score > best_score:
            best_score = score
            best_check = m.group(1)
    return best_check


def _extract_amount_from_detections(detections: list[Any]) -> float | None:
    """Look for a $X.YZ amount on the check image (handwritten amount line)."""

    if not detections:
        return None
    for det in detections:
        try:
            text = str(det[1] or "").strip()
        except Exception:
            continue
        m = _CHECK_IMAGE_AMOUNT_RE.search(text)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                continue
    return None


def _extract_payee_from_check_detections(detections: list[Any]) -> tuple[str, float]:
    """Extract the payee name from the "Pay to the order of" line.

    See ``AzureFunctions/ocr_processor/function_app.py`` for the full strategy
    (line bucketing, next-line fallback, prefix scrubber, all-caps title case).
    """

    lines = _bucket_detections_by_line(detections)
    if not lines:
        return "", 0.0

    payee_line_idx = -1
    cutoff_x: float | None = None

    for i, line in enumerate(lines):
        low = line["text"].lower()
        if "order of" in low:
            payee_line_idx = i
            for j, tok in enumerate(line["tokens"]):
                t_low = tok["text"].lower().strip(":.,-* ")
                if t_low == "of":
                    cutoff_x = tok["x_right"]
                    break
                if "order" in t_low and j + 1 < len(line["tokens"]):
                    nxt = line["tokens"][j + 1]
                    if nxt["text"].lower().strip(":.,-* ") in ("of", "of:"):
                        cutoff_x = nxt["x_right"]
                        break
            break

    if payee_line_idx < 0:
        for i, line in enumerate(lines):
            low = line["text"].lower()
            if "pay to" in low or low.startswith("pay "):
                payee_line_idx = i
                for tok in line["tokens"]:
                    t_low = tok["text"].lower().strip(":.,-* ")
                    if t_low == "to":
                        cutoff_x = tok["x_right"]
                        break
                break

    if payee_line_idx < 0:
        return "", 0.0

    def _filter_payee_tokens(tokens: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for tok in tokens:
            t = tok["text"].strip()
            if not t:
                continue
            t_low = t.lower().strip(":.,-* ")
            if t_low in _PAYEE_LINE_NOISE_TOKENS:
                continue
            if _PAYEE_AMOUNT_ONLY_RE.match(t):
                continue
            out.append(tok)
        return out

    same_line_tokens = [
        tok
        for tok in lines[payee_line_idx]["tokens"]
        if cutoff_x is None or tok["x_left"] > cutoff_x
    ]
    candidates = _filter_payee_tokens(same_line_tokens)

    if (
        not candidates or len(" ".join(t["text"] for t in candidates).strip()) < 3
    ) and payee_line_idx + 1 < len(lines):
        next_line_tokens = lines[payee_line_idx + 1]["tokens"]
        next_candidates = _filter_payee_tokens(next_line_tokens)
        if next_candidates:
            candidates = next_candidates

    if not candidates:
        return "", 0.0

    def _clean_payee(text: str) -> str:
        out = re.sub(r"[*_]{2,}", "", text)
        out = _PAYEE_LINE_PREFIX_RE.sub("", out).strip()
        out = _PAYEE_TRAILING_AMOUNT_RE.sub("", out).strip(" -:|.,*$")
        out = re.sub(r"\s{2,}", " ", out).strip()
        return out

    raw = _clean_payee(" ".join(t["text"] for t in candidates))

    if (not raw or len(raw) < 2) and payee_line_idx + 1 < len(lines):
        next_line_tokens = lines[payee_line_idx + 1]["tokens"]
        next_candidates = _filter_payee_tokens(next_line_tokens)
        if next_candidates:
            candidates = next_candidates
            raw = _clean_payee(" ".join(t["text"] for t in candidates))

    if not raw or len(raw) < 2:
        return "", 0.0

    avg_conf = sum(t["conf"] for t in candidates) / max(len(candidates), 1)

    if raw.isupper() and len(raw) > 3:
        raw = raw.title()

    return raw[:80], float(avg_conf)


def _safe_amount(row: dict[str, Any]) -> float | None:
    """Parse a row's SignedAmount (or Amount) into a float; None on failure."""

    raw = str(row.get("SignedAmount") or row.get("Amount") or "").strip().replace(",", "")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _fuzzy_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _build_review_reason(existing: str, new_bit: str) -> str:
    """Replace OCR-fallback / Missing-payee hints with the new audit note."""

    bits = [bit.strip() for bit in (existing or "").split(";") if bit.strip()]
    cleaned = [
        bit
        for bit in bits
        if not bit.startswith("OCR fallback path")
        and bit != "Missing payee"
        and bit != "Missing date"
    ]
    cleaned.append(new_bit)
    return "; ".join(cleaned)


def _match_checks_to_transactions(
    transactions: list[dict[str, Any]],
    cropped_checks: list[dict[str, Any]],
    detections_by_id: dict[str, list[Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Link each cropped check to its best-matching transaction (in place)."""

    logs: list[str] = []
    if not transactions and not cropped_checks:
        return transactions, cropped_checks, logs

    if not cropped_checks:
        logs.append(_log("info", "Check-linking: 0 cropped check(s); nothing to match."))
        return transactions, cropped_checks, logs

    if not transactions:
        logs.append(
            _log(
                "info",
                f"Check-linking: 0 transaction(s); annotating "
                f"{len(cropped_checks)} check(s) with extracted payee only.",
            )
        )

    logs.append(
        _log(
            "info",
            f"Check-linking: matching {len(cropped_checks)} cropped check(s) against "
            f"{len(transactions)} transaction(s).",
        )
    )

    by_check_no: dict[str, list[int]] = {}
    for i, txn in enumerate(transactions):
        norm = _norm_check_no(str(txn.get("Check#", "")))
        if norm:
            by_check_no.setdefault(norm, []).append(i)

    used_txn_indices: set[int] = set()

    for check in cropped_checks:
        check_id = str(check.get("check_id", "?"))
        detections = detections_by_id.get(check_id, [])

        extracted_check_no = _extract_check_number_from_detections(detections)
        extracted_payee, payee_conf = _extract_payee_from_check_detections(detections)
        extracted_amount = _extract_amount_from_detections(detections)

        check["extracted_check_number"] = extracted_check_no
        check["extracted_payee"] = extracted_payee
        check["extracted_payee_confidence"] = (
            round(float(payee_conf), 3) if extracted_payee else 0.0
        )
        check["linked_transaction_index"] = -1

        match_idx: int | None = None
        match_reason = ""

        if extracted_check_no:
            norm = _norm_check_no(extracted_check_no)
            for idx in by_check_no.get(norm, []):
                if idx in used_txn_indices:
                    continue
                match_idx = idx
                match_reason = f"check# {extracted_check_no}"
                break

        if match_idx is None and extracted_amount is not None:
            for i, txn in enumerate(transactions):
                if i in used_txn_indices:
                    continue
                amt = _safe_amount(txn)
                if amt is None:
                    continue
                if abs(abs(amt) - abs(extracted_amount)) <= _AMOUNT_MATCH_TOLERANCE:
                    match_idx = i
                    match_reason = f"amount ${abs(extracted_amount):.2f}"
                    break

        if match_idx is None and extracted_payee:
            best_idx: int | None = None
            best_ratio = 0.0
            for i, txn in enumerate(transactions):
                if i in used_txn_indices:
                    continue
                desc = str(txn.get("Description", "")).strip()
                ratio = _fuzzy_ratio(extracted_payee, desc)
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_idx = i
            if best_idx is not None and best_ratio >= _FUZZY_MIN:
                match_idx = best_idx
                match_reason = f"fuzzy desc match ({best_ratio:.2f})"

        if match_idx is None:
            logs.append(
                _log(
                    "info",
                    f"  {check_id}: no transaction match (extracted "
                    f"check#={extracted_check_no!r}, payee={extracted_payee!r}, "
                    f"amount={extracted_amount}).",
                )
            )
            continue

        txn = transactions[match_idx]
        old_payee = str(txn.get("Payee", "")).strip()
        new_payee = extracted_payee.strip() if extracted_payee else ""

        should_swap = bool(new_payee) and (
            not old_payee
            or old_payee.lower() == "uncategorized"
            or _fuzzy_ratio(old_payee, new_payee) < 0.85
        )

        if should_swap:
            txn["Payee"] = new_payee
            txn["Confidence"] = "High"
            txn["NeedsReview"] = "No"
            txn["ReviewReason"] = _build_review_reason(
                str(txn.get("ReviewReason", "")),
                f"Payee from check image ({match_reason})",
            )

        txn["linked_check_id"] = check_id
        check["linked_transaction_index"] = match_idx
        used_txn_indices.add(match_idx)

        logs.append(
            _log(
                "info",
                f"  {check_id} -> txn #{match_idx} via {match_reason}; "
                f"Payee {old_payee!r} -> {txn.get('Payee', '')!r} "
                f"(check#={extracted_check_no!r}, conf={payee_conf:.2f}).",
            )
        )

    linked = sum(1 for c in cropped_checks if c.get("linked_transaction_index", -1) >= 0)
    logs.append(
        _log(
            "info",
            f"Check-linking: {linked}/{len(cropped_checks)} cropped check(s) linked to "
            f"transactions; {len(cropped_checks) - linked} unmatched (returned for manual review).",
        )
    )

    return transactions, cropped_checks, logs


# ---------------------------------------------------------------------------
# Bank-statement parser (subset ported from Scripts/bank-statement-parser.py)
# ---------------------------------------------------------------------------
# Kept inline (rather than importing from /Scripts) so the module is fully
# self-contained and exactly matches the Function's regex parser output.

_DATE_PATTERNS = [
    (re.compile(r"^(\d{4})-(\d{2})-(\d{2})\b"), "iso"),
    (re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})\b"), "mdy"),
    (re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{2,4})\b"), "mdy_dash"),
    (re.compile(r"^(\d{1,2})/(\d{1,2})(?!\d)"), "md"),
    (re.compile(r"^(\d{1,2})-(\d{1,2})(?!\d)"), "md_dash"),
]

_DATE_INLINE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}-\d{1,2}-\d{2,4}|"
    r"\d{1,2}/\d{1,2}|\d{1,2}-\d{1,2})\b"
)

_AMOUNT_RE = re.compile(r"(?P<neg>\()?-?\$?(?P<num>\d{1,3}(?:,\d{3})*|\d+)\.(?P<cents>\d{2})\)?")

_CHECK_RE = re.compile(r"(?i)\bcheck\s*#?\s*(\d{3,6})\b")
_CHECK_STANDALONE_RE = re.compile(r"^\s*\*?\s*(\d{3,6})\s*\*?\s*$")
_CHECK_REGISTER_ROW_RE = re.compile(
    r"^\s*\*?\s*(\d{3,6})\s*\*?\s+(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\s+(.+?)\s*$"
)

_TXN_HINT_RE = re.compile(
    r"(?i)(ach\s+(deposit|withdrawal|debit|credit)|"
    r"debit\s+card|check\s*#?|eft/?ach|regular\s+deposit|"
    r"wire\s|pos\s|merch\s+bnkcd|merch\s+setl|"
    r"internet\s+transfer|service\s+charge|nsf\s|overdraft|"
    r"paypal|inst\s+xfer|bnkcd|(?<!total\s)\bdeposit\b|"
    r"withdrawal|transfer|epay|zelle|venmo|card\s+tran)"
)

_SKIP_LINE_RE = re.compile(
    r"(?i)(page\s+\d+\s*of\s*\d+|^\s*page\s+\d+\s*$|continued|account\s+number|"
    r"routing\s+number|member\s+fdic|equal\s+housing|summary\s+of\s+accounts|"
    r"statement\s+balance\s+summary|customer\s+service|"
    r"beginning\s+balance|ending\s+balance|average\s+daily\s+balance|"
    r"previous\s+balance\s+[\d$,]|total\s+for\s|subtotal|"
    r"number\s+of\s+(deposits|withdrawals|credits|debits|checks)|"
    r"^\s*\*\s*indicates\s+a\s+break|interest\s+earned\s+this\s+period|"
    r"telephone\s+banking|www\.|^\s*[(]?\d{3}[)]?[-.\s]?\d{3}[-.\s]?\d{4}\s*$)"
)

_BALANCE_TOTAL_RE = re.compile(
    r"(?i)^\s*(total\s+(deposits|withdrawals|credits|debits|checks|fees|service\s+charges)|"
    r"total\s+deposits|total\s+withdrawals|grand\s+total|"
    r"net\s+(deposits|withdrawals|credits|debits))\b"
)

_SECTION_TERMINATORS = {
    "daily balance",
    "daily balances",
    "daily balance summary",
    "daily balance information",
    "statement balance summary",
    "balance summary",
    "account summary",
}

_SECTION_MARKERS: dict[str, str] = {
    "deposits": "credit",
    "deposits and credits": "credit",
    "deposits and additions": "credit",
    "deposits and other credits": "credit",
    "deposits/credits": "credit",
    "credits": "credit",
    "other credits": "credit",
    "electronic credits": "credit",
    "electronic deposits": "credit",
    "atm deposits": "credit",
    "electronic debits": "debit",
    "electronic debit": "debit",
    "other debits": "debit",
    "other withdrawals": "debit",
    "atm withdrawals": "debit",
    "debits": "debit",
    "debit card": "debit",
    "debit card transactions": "debit",
    "check register": "check",
    "checks paid": "check",
    "checks": "check",
    "withdrawals": "debit",
    "withdrawals and debits": "debit",
    "service charges": "debit",
    "fees": "debit",
}

_COLUMN_HEADER_PHRASES = (
    "date description",
    "date description amount",
    "date check",
    "posting date",
    "check number",
    "check #",
)

_PAYEE_NOISE_PREFIXES = (
    "pos purchase",
    "pos pur",
    "pos debit",
    "debit card purchase",
    "debit card",
    "card purchase",
    "card tran",
    "ach debit",
    "ach credit",
    "ach deposit",
    "ach withdrawal",
    "electronic debit",
    "electronic credit",
    "online banking transfer",
    "online banking",
    "mobile deposit",
    "atm withdrawal",
    "atm deposit",
    "check #",
    "check#",
    "eft/ach",
    "eft ach",
    "merch bnkcd",
    "merch setl",
    "bnkcd",
    "inst xfer",
    "internet transfer",
    "wire transfer",
    "wire",
    "epay",
    "zelle payment",
    "zelle",
    "venmo payment",
    "venmo",
    "paypal",
    "regular deposit",
    "deposit",
    "withdrawal",
    "transfer",
)


def _infer_statement_year(text: str, fallback: int = 0) -> int | None:
    fallback = fallback or datetime.utcnow().year
    for pat in (
        r"(?i)statement\s+period[^\d]{0,40}(\d{4})",
        r"(?i)(january|february|march|april|may|june|july|august|september|october|november|december)"
        r"\s+\d{1,2},?\s+(\d{4})",
        r"\b(20\d{2})\b",
    ):
        m = re.search(pat, text[:8000])
        if m:
            year = int(m.groups()[-1])
            if 2000 <= year <= 2099:
                return year
    return fallback


def _normalize_date(raw: str, default_year: int) -> tuple[str, str]:
    raw = (raw or "").strip()
    if not raw:
        return "", ""
    for pat, kind in _DATE_PATTERNS:
        m = pat.match(raw)
        if not m:
            continue
        if kind == "iso":
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        elif kind in ("md", "md_dash"):
            mo, d = int(m.group(1)), int(m.group(2))
            y = default_year
        else:
            mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 100:
                y += 2000 if y < 70 else 1900
            if y < 2000:
                y = default_year
        try:
            dt = datetime(y, mo, d)
            return dt.strftime("%Y-%m-%d"), dt.strftime("%Y-%m")
        except ValueError:
            continue
    m = _DATE_INLINE.search(raw)
    if m:
        return _normalize_date(m.group(1), default_year)
    return "", ""


def _parse_amounts(line: str) -> list[float]:
    values: list[float] = []
    for m in _AMOUNT_RE.finditer(line):
        num = m.group("num").replace(",", "")
        cents = m.group("cents")
        try:
            val = float(f"{num}.{cents}")
        except ValueError:
            continue
        if m.group("neg") or line[m.start() : m.start() + 1] == "-":
            val = -abs(val)
        elif line[max(0, m.start() - 2) : m.start()].strip().endswith("-"):
            val = -abs(val)
        values.append(val)
    return values


def _pick_transaction_amount(
    values: list[float], *, prefer: str = "first_with_balance"
) -> float | None:
    if not values:
        return None
    non_zero = [v for v in values if abs(v) > 0.001]
    if not non_zero:
        return values[-1]
    if prefer == "last":
        return non_zero[-1]
    if prefer == "first" or len(non_zero) >= 2:
        return non_zero[0]
    return non_zero[-1]


def _format_signed_amount(val: float | None) -> str:
    if val is None:
        return ""
    return f"{val:.2f}"


def _strip_trailing_amounts(description: str) -> str:
    prev = None
    while prev != description:
        prev = description
        description = re.sub(r"[-]?\$?\d{1,3}(?:,\d{3})*\.\d{2}\s*$", "", description).strip()
        description = re.sub(r"\(\d{1,3}(?:,\d{3})*\.\d{2}\)\s*$", "", description).strip()
    return description


def _apply_section_sign(amount: float | None, section: str | None) -> float | None:
    if amount is None or section is None:
        return amount
    if section == "debit" and amount > 0:
        return -abs(amount)
    if section == "check" and amount > 0:
        return -abs(amount)
    if section == "credit" and amount < 0:
        return abs(amount)
    return amount


def _detect_section(line: str) -> str | None:
    low = re.sub(r"\s*\|.*$", "", line.lower().strip())
    low = re.sub(r"[^a-z0-9\s/]", " ", low)
    low = re.sub(r"\s+", " ", low).strip()
    if not low:
        return None
    for term in sorted(_SECTION_TERMINATORS, key=len, reverse=True):
        if low == term or low.startswith(term + " "):
            return "end"
    for marker, kind in sorted(_SECTION_MARKERS.items(), key=lambda x: -len(x[0])):
        if low == marker or low.startswith(marker + " ") or low.startswith(marker + "/"):
            return kind
    return None


def _is_column_header_line(line: str) -> bool:
    low = line.lower().strip()
    if _parse_amounts(line):
        return False
    if _DATE_INLINE.search(line[:16]) and not low.startswith("date"):
        return False
    if any(phrase in low for phrase in _COLUMN_HEADER_PHRASES):
        return True
    if re.match(r"(?i)^date\s", low) and (
        "amount" in low or "description" in low or "check" in low
    ):
        return True
    return False


def _words_to_lines(words: list[dict], y_tolerance: float = 4.0) -> list[str]:
    if not words:
        return []
    buckets: dict[int, list] = {}
    for w in words:
        key = int(round(w.get("top", 0) / y_tolerance))
        buckets.setdefault(key, []).append(w)
    lines: list[str] = []
    for key in sorted(buckets):
        row = sorted(buckets[key], key=lambda x: x.get("x0", 0))
        lines.append(" ".join(w.get("text", "") for w in row if w.get("text")))
    return lines


def _should_skip_line(line: str) -> bool:
    low = line.lower().strip()
    if len(low) < 3:
        return True
    if _SKIP_LINE_RE.search(line):
        return True
    if _BALANCE_TOTAL_RE.match(line):
        return True
    if _detect_section(line):
        return True
    if _is_column_header_line(line):
        return True
    if re.match(r"(?i)^(debit|credit|amount|balance)\s*(\s|$|\|)", low):
        return True
    if re.match(r"^\s*date\s*$", low):
        return True
    return False


def _extract_check_number(*parts: str, check_column: bool = False) -> str:
    for part in parts:
        if not part:
            continue
        part = part.strip()
        m = _CHECK_RE.search(part)
        if m:
            return m.group(1)
        if check_column:
            m = _CHECK_STANDALONE_RE.match(part)
            if m:
                return m.group(1)
    return ""


def _is_transaction_candidate(
    line: str,
    *,
    has_amount: bool,
    has_date: bool = False,
    section: str | None = None,
) -> bool:
    if not has_amount:
        return False
    if has_date or re.match(r"^\d{1,2}[/-]\d{1,2}", line.strip()):
        return True
    if section in ("credit", "debit", "check"):
        return True
    if _TXN_HINT_RE.search(line):
        return True
    if _CHECK_RE.search(line) or _CHECK_STANDALONE_RE.match(line.split("|")[0].strip()):
        return True
    return False


def _split_date_prefix(line: str, default_year: int) -> tuple[str, str, str]:
    line = line.strip()
    for pat, _kind in _DATE_PATTERNS:
        m = pat.match(line)
        if m:
            iso, ym = _normalize_date(line[: m.end()], default_year)
            rest = line[m.end() :].strip()
            return iso, rest, ym
    m = _DATE_INLINE.match(line)
    if m and m.start() < 12:
        iso, ym = _normalize_date(m.group(1), default_year)
        rest = (line[m.end() :] or "").strip()
        return iso, rest, ym
    return "", line, ""


def _infer_payee_from_description(description: str, check_num: str = "") -> str:
    """Cheap heuristic — strip common noise prefixes to surface the merchant."""

    cleaned = (description or "").strip()
    if not cleaned:
        return ""
    if check_num or re.match(r"(?i)^check\s*#?\s*\d{3,6}\b", cleaned):
        return ""

    low = cleaned.lower()
    for prefix in _PAYEE_NOISE_PREFIXES:
        if low.startswith(prefix):
            cleaned = cleaned[len(prefix) :].lstrip(" #*-:|,.")
            low = cleaned.lower()
            break
    cleaned = re.sub(r"\s+#\d+\b.*$", "", cleaned)
    cleaned = re.sub(r"\s+\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\s*$", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    if cleaned.isupper() and len(cleaned) > 3:
        cleaned = cleaned.title()
    return cleaned[:60]


def _build_row(
    *,
    date: str,
    description: str,
    amount: float | None,
    check_num: str,
    year_month: str,
    default_year: int,
    section: str | None = None,
    source: str = "pdfplumber",
) -> dict[str, Any]:
    description = _strip_trailing_amounts((description or "").strip())
    amount = _apply_section_sign(amount, section)
    signed = _format_signed_amount(amount)

    if not date:
        ym = year_month
    else:
        ym = year_month or (date[:7] if len(date) >= 7 else "")

    base_conf = "High" if source == "pdfplumber" else "Medium"
    conf = base_conf
    needs = "No"
    review_reasons: list[str] = []

    if not date:
        conf = "Medium"
        needs = "Yes"
        review_reasons.append("Missing date")
    if not signed:
        conf = "Medium"
        needs = "Yes"
        review_reasons.append("Missing amount")

    check_num = check_num or _extract_check_number(description)
    payee = _infer_payee_from_description(description, check_num=check_num)

    if source == "easyocr" and conf == "High":
        conf = "Medium"
    if source == "easyocr":
        review_reasons.append("OCR fallback path — verify amount + payee")
        needs = "Yes"

    row = {
        "Date": date or "",
        "Description": description.strip(),
        "Payee": payee,
        "Amount": signed,
        "Check#": check_num,
        "Category": "Uncategorized",
        "SubCategory": "",
        "SignedAmount": signed,
        "YearMonth": ym or f"{default_year}-01",
        "Confidence": conf,
        "NeedsReview": needs,
        "ReviewReason": "; ".join(review_reasons),
    }
    return _validate_transaction_row(row)


def _validate_transaction_row(row: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    date_val = str(row.get("Date", "")).strip()
    if date_val and not re.match(r"^\d{4}-\d{2}-\d{2}$", date_val):
        errors.append("Date format uncertain")
    elif not date_val:
        errors.append("Missing date")

    signed = str(row.get("SignedAmount", "")).strip()
    if signed:
        try:
            float(signed.replace(",", ""))
        except ValueError:
            errors.append(f"Invalid SignedAmount: {signed}")
    else:
        errors.append("Missing amount")

    check = str(row.get("Check#", "")).strip()
    if check and not check.isdigit():
        errors.append(f"Check# may need review: {check}")

    ym = str(row.get("YearMonth", "")).strip()
    if ym and not re.match(r"^\d{4}-\d{2}$", ym):
        if len(date_val) >= 7:
            row["YearMonth"] = date_val[:7]
        else:
            errors.append("YearMonth adjusted")

    conf = str(row.get("Confidence", "")).strip()
    if conf not in ("High", "Medium", "Low", ""):
        row["Confidence"] = "Medium"
        errors.append("Invalid Confidence corrected")

    if errors:
        row["NeedsReview"] = "Yes"
        existing = str(row.get("ReviewReason", "")).strip()
        merged = "; ".join([s for s in [existing] + errors if s])
        row["ReviewReason"] = merged
        if row.get("Confidence") == "High":
            row["Confidence"] = "Medium"
    return row


def _parse_cells_to_row(
    cells: list[str],
    *,
    default_year: int,
    section: str | None,
    col_date: int | None,
    col_desc: int | None,
    col_amt: int | None,
    col_check: int | None,
    source: str = "pdfplumber",
) -> dict[str, Any] | None:
    if not cells:
        return None
    joined = " ".join(cells)
    if _detect_section(joined) or _is_column_header_line(joined):
        return None

    iso, ym = "", ""
    desc = ""
    amt: float | None = None
    check_num = ""

    if col_date is not None and col_date < len(cells):
        iso, ym = _normalize_date(cells[col_date], default_year)
    if col_desc is not None and col_desc < len(cells):
        desc = cells[col_desc]
    if col_check is not None and col_check < len(cells):
        check_num = _extract_check_number(cells[col_check], check_column=True)
    if col_amt is not None and col_amt < len(cells):
        amt = _pick_transaction_amount(_parse_amounts(cells[col_amt]), prefer="first")

    if col_date is None and len(cells) >= 3:
        iso_guess, ym_guess = _normalize_date(cells[0], default_year)
        if section == "check" and not iso_guess and len(cells) >= 3:
            chk_m = _CHECK_STANDALONE_RE.match(cells[0])
            date_guess, ym_date = _normalize_date(cells[1], default_year)
            if chk_m and date_guess:
                amt_guess = _pick_transaction_amount(_parse_amounts(cells[2]), prefer="first")
                if amt_guess is not None:
                    check_num = chk_m.group(1)
                    iso, ym = date_guess, ym_date
                    amt = amt_guess
                    desc = f"Check #{check_num}"
        if iso_guess:
            if section == "check" and len(cells) >= 4:
                amt_guess = _pick_transaction_amount(_parse_amounts(cells[2]), prefer="first")
                if amt_guess is not None:
                    iso, ym = iso_guess, ym_guess
                    check_num = _extract_check_number(cells[1], check_column=True)
                    amt = amt_guess
                    desc = cells[3]
            else:
                if len(cells) >= 4 and _parse_amounts(cells[-1]) and _parse_amounts(cells[-2]):
                    amt_guess = _pick_transaction_amount(_parse_amounts(cells[-2]), prefer="first")
                    if amt_guess is not None:
                        iso, ym = iso_guess, ym_guess
                        amt = amt_guess
                        desc = " ".join(cells[1:-2])
                else:
                    amt_guess = _pick_transaction_amount(_parse_amounts(cells[-1]), prefer="first")
                    if amt_guess is not None:
                        iso, ym = iso_guess, ym_guess
                        amt = amt_guess
                        desc = " | ".join(cells[1:-1]) if " | " in joined else " ".join(cells[1:-1])

    if section == "check" and not iso and not check_num:
        for c in cells:
            cm = _CHECK_STANDALONE_RE.match(c.strip())
            if cm:
                check_num = cm.group(1)
                break

    if not iso:
        iso, remainder, ym = _split_date_prefix(joined, default_year)
        if iso and not desc:
            desc = remainder

    if not desc:
        desc = joined
    if amt is None:
        amt = _pick_transaction_amount(_parse_amounts(joined))
        if amt is not None and iso:
            desc = _strip_trailing_amounts(_AMOUNT_RE.sub("", joined.replace(iso, "", 1)).strip())

    has_date = bool(iso)
    if not _is_transaction_candidate(
        desc or joined, has_amount=amt is not None, has_date=has_date, section=section
    ):
        return None
    if amt is None:
        return None

    return _build_row(
        date=iso,
        description=desc,
        amount=amt,
        check_num=check_num,
        year_month=ym,
        default_year=default_year,
        section=section,
        source=source,
    )


def _map_table_columns(
    headers: list[str],
) -> tuple[int | None, int | None, int | None, int | None]:
    col_date = next((i for i, h in enumerate(headers) if "date" in h), None)
    col_desc = next(
        (
            i
            for i, h in enumerate(headers)
            if any(k in h for k in ("description", "detail", "memo", "payee"))
        ),
        None,
    )
    col_check = next(
        (i for i, h in enumerate(headers) if "check" in h and "date" not in h),
        None,
    )
    col_amt = next(
        (
            i
            for i, h in enumerate(headers)
            if h in ("amount", "debit", "credit", "withdrawal", "deposit") or "amount" in h
        ),
        None,
    )
    if col_desc is None and col_check is not None and col_amt is not None:
        remaining = [i for i in range(len(headers)) if i not in (col_date, col_check, col_amt)]
        if remaining:
            col_desc = remaining[-1]
    return col_date, col_desc, col_amt, col_check


def _find_header_row(
    table: list[list[Any]], start: int = 0
) -> tuple[int | None, int | None, int | None, int | None, int]:
    for i, row in enumerate(table[start : start + 8], start=start):
        joined = " ".join(str(c or "") for c in row).lower()
        if "date" in joined and (
            "amount" in joined
            or "debit" in joined
            or "credit" in joined
            or "check" in joined
            or "description" in joined
        ):
            headers = [str(c or "").strip().lower() for c in row]
            cols = _map_table_columns(headers)
            return (*cols, i)
    return None, None, None, None, -1


def _parse_table_rows(tables: list[list[list[Any]]], default_year: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for table in tables:
        if not table or len(table) < 2:
            continue
        section: str | None = None
        suppressed = False
        col_date = col_desc = col_amt = col_check = None
        header_idx = -1
        idx = 0
        while idx < len(table):
            row = table[idx]
            cells = [str(c or "").strip() for c in row] if row else []
            joined = " ".join(cells)
            sec = _detect_section(joined)
            if sec == "end":
                suppressed = True
                section = None
                col_date = col_desc = col_amt = col_check = None
                header_idx = -1
                idx += 1
                continue
            if sec:
                suppressed = False
                section = sec
                col_date = col_desc = col_amt = col_check = None
                header_idx = -1
                hdr_cols = _find_header_row(table, idx + 1)
                if hdr_cols[4] >= 0:
                    col_date, col_desc, col_amt, col_check, header_idx = hdr_cols
                idx += 1
                continue
            if suppressed:
                idx += 1
                continue
            if _is_column_header_line(joined):
                headers = [str(c or "").strip().lower() for c in row]
                col_date, col_desc, col_amt, col_check = _map_table_columns(headers)
                header_idx = idx
                idx += 1
                continue
            if header_idx < 0:
                hdr_cols = _find_header_row(table, idx)
                if hdr_cols[4] >= 0:
                    col_date, col_desc, col_amt, col_check, header_idx = hdr_cols
                    if idx == header_idx:
                        idx += 1
                        continue

            parsed = _parse_cells_to_row(
                cells,
                default_year=default_year,
                section=section,
                col_date=col_date,
                col_desc=col_desc,
                col_amt=col_amt,
                col_check=col_check,
                source="pdfplumber",
            )
            if parsed:
                rows.append(parsed)
            idx += 1
    return rows


def _parse_lines_to_transactions(
    lines: list[str], default_year: int, source: str = "pdfplumber"
) -> list[dict[str, Any]]:
    transactions: list[dict[str, Any]] = []
    current_date = ""
    current_ym = ""
    current_section: str | None = None
    pending_desc: list[str] = []
    suppressed = False

    def flush_pending() -> None:
        nonlocal pending_desc
        if pending_desc and not suppressed:
            desc = " ".join(pending_desc).strip()
            if desc and (_TXN_HINT_RE.search(desc) or current_date or current_section):
                row = _build_row(
                    date=current_date,
                    description=desc,
                    amount=None,
                    check_num=_extract_check_number(desc),
                    year_month=current_ym,
                    default_year=default_year,
                    section=current_section,
                    source=source,
                )
                transactions.append(row)
        pending_desc = []

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        sec = _detect_section(line)
        if sec == "end":
            flush_pending()
            suppressed = True
            current_section = None
            continue
        if sec:
            flush_pending()
            current_section = sec
            suppressed = False
            continue

        if suppressed:
            continue

        if " | " in line:
            cells = [c.strip() for c in line.split(" | ")]
            parsed = _parse_cells_to_row(
                cells,
                default_year=default_year,
                section=current_section,
                col_date=None,
                col_desc=None,
                col_amt=None,
                col_check=None,
                source=source,
            )
            if parsed:
                flush_pending()
                if parsed.get("Date"):
                    current_date = parsed["Date"]
                    current_ym = parsed.get("YearMonth", "")
                transactions.append(parsed)
                continue

        if current_section == "check" and not _is_column_header_line(line):
            cm = _CHECK_REGISTER_ROW_RE.match(line)
            if cm:
                check_no = cm.group(1)
                date_str = cm.group(2)
                rest = cm.group(3)
                iso_d, ym_d = _normalize_date(date_str, default_year)
                amts = _parse_amounts(rest)
                amt = _pick_transaction_amount(amts)
                if amt is not None:
                    flush_pending()
                    desc_text = f"Check #{check_no}"
                    extra = _AMOUNT_RE.sub("", rest).strip(" .-")
                    if extra and not extra.isdigit():
                        desc_text = f"{desc_text} {extra}".strip()
                    row = _build_row(
                        date=iso_d or current_date,
                        description=desc_text,
                        amount=amt,
                        check_num=check_no,
                        year_month=ym_d or current_ym,
                        default_year=default_year,
                        section="check",
                        source=source,
                    )
                    transactions.append(row)
                    if iso_d:
                        current_date = iso_d
                        current_ym = ym_d
                    continue

        if _should_skip_line(line):
            continue

        line_date, remainder, line_ym = _split_date_prefix(line, default_year)
        if line_date:
            flush_pending()
            current_date = line_date
            current_ym = line_ym
            line = remainder

        amounts = _parse_amounts(line)
        has_amount = bool(amounts)

        if not has_amount:
            if (
                _TXN_HINT_RE.search(line)
                or _DATE_INLINE.search(line[:20])
                or _extract_check_number(line)
                or current_section
            ):
                pending_desc.append(line)
            continue

        desc_parts = pending_desc + ([line] if line else [])
        pending_desc = []
        description = " ".join(desc_parts).strip()
        amount_vals = _parse_amounts(description)
        amount = _pick_transaction_amount(amount_vals)

        has_date = bool(current_date) or bool(line_date)
        if not _is_transaction_candidate(
            description,
            has_amount=True,
            has_date=has_date,
            section=current_section,
        ):
            if not current_date and not current_section:
                continue

        check_num = _extract_check_number(description, line)
        row = _build_row(
            date=current_date,
            description=description,
            amount=amount,
            check_num=check_num,
            year_month=current_ym,
            default_year=default_year,
            section=current_section,
            source=source,
        )
        transactions.append(row)

    flush_pending()
    return _dedupe_transactions(transactions)


def _dedupe_transactions(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple] = set()
    out: list[dict[str, Any]] = []
    for row in transactions:
        key = (
            row.get("Date"),
            str(row.get("Description", ""))[:80],
            row.get("SignedAmount"),
            row.get("Check#"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _filter_balance_only_rows(
    transactions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    bad_desc = re.compile(
        r"(?i)^(ending|beginning|previous|new|current|available)\s+balance\b|"
        r"^balance\s*(forward|brought\s*forward)?\s*$|^total\b"
    )
    for row in transactions:
        desc = str(row.get("Description", "")).strip()
        if not desc or bad_desc.match(desc):
            continue
        out.append(row)
    return out


__all__ = [
    "LOCAL_ENHANCED_OCR_VERSION",
    "TRANSACTION_FIELDS",
    "OCR_DPI_TEXT",
    "OCR_DPI_CROP",
    "OCR_MAX_PAGES_RASTER",
    "OCR_MAX_CHECKS",
    "OCR_FAST_PATH_MIN_ROWS",
    "detect_capabilities",
    "environment_summary",
    "run_pipeline",
]
