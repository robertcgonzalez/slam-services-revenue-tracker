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

LOCAL_ENHANCED_OCR_VERSION = "v2.44.3"


def _is_codespaces() -> bool:
    """True when running inside a GitHub Codespace.

    Codespaces sets the ``CODESPACES=true`` environment variable
    automatically on every machine in the Codespaces fleet (also
    populated for `gh cs ssh` sessions). We use this to pick safer
    DPI / page / check-count defaults so the heavy OCR pipeline fits
    comfortably on the standard 4-core / 8 GB SKU without swapping.
    """

    return os.environ.get("CODESPACES", "").strip().lower() == "true"


# Default DPIs differ between the primary mirroring environment
# (GitHub Codespace `slam-v2.44-codespaces-migration`, which replicates
# the laptop setup) and a Codespaces container (resource-aware 200/180).
# Either default is overridable per-run via the SLAM_LOCAL_OCR_* env vars
# below — devcontainer.json sets the Codespaces values explicitly, but if
# the env vars are unset and we still detect Codespaces, fall back to the
# safer defaults so scripted runs are well-behaved.
_RUNTIME_IS_CODESPACES = _is_codespaces()
_DEFAULT_DPI_TEXT = "200" if _RUNTIME_IS_CODESPACES else "300"
# v2.44.3: bumped DPI_CROP from 180 → 220 in Codespaces. At 180 the OpenCV
# contour finder produced ZERO check-rectangle candidates on the Auto Body
# Center Jan-26 scanned PDF (verified live in slam-v2.44-codespaces-migration);
# at 220 the same pass returns 50+ candidates, matching the laptop's
# behaviour. The ~1.5x memory cost per rasterized page is well worth the
# matcher actually being exercised.
_DEFAULT_DPI_CROP = "220" if _RUNTIME_IS_CODESPACES else "250"
_DEFAULT_MAX_PAGES_RASTER = "20" if _RUNTIME_IS_CODESPACES else "30"
# v2.44.3: cap raised 30 → 50 in Codespaces so the cropper can reach all 49
# check images on a typical Traditions Bank monthly statement without
# truncating mid-page.
_DEFAULT_MAX_CHECKS = "50" if _RUNTIME_IS_CODESPACES else "40"

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
    # Authoritative source totals from the Statement Summary block. When
    # parsable, these override the row-sum totals in `_compute_grok_totals`
    # so the reconciliation banner anchors against the bank's own number.
    summary_override: dict[str, Any] = {}

    # 1) pdfplumber fast path -------------------------------------------------
    try:
        text_blob, tables, fast_logs, statement_year = _extract_pdfplumber(pdf_bytes)
        pipeline_logs.extend(fast_logs)
        default_year = statement_year or default_year

        if text_blob.strip():
            summary_override = _extract_statement_summary(text_blob) or summary_override
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
                # v2.44 — Pull authoritative source totals from the
                # Statement Summary block BEFORE the strict parser eats
                # those lines as skip-noise. Per-line search is cheap and
                # the parser ignores the lines anyway.
                ocr_summary = _extract_statement_summary(ocr_lines)
                if ocr_summary:
                    # Pdfplumber totals (if any) win on a hybrid PDF, but
                    # for a fully-scanned PDF the OCR summary is the only
                    # source we have.
                    for key, value in ocr_summary.items():
                        summary_override.setdefault(key, value)
                    pipeline_logs.append(
                        _log(
                            "info",
                            "EasyOCR statement summary parsed: "
                            f"deposits=${ocr_summary.get('deposits', '?')} "
                            f"withdrawals=${ocr_summary.get('withdrawals', '?')} "
                            f"(authoritative — overrides row-sum totals).",
                        )
                    )

                # v2.44 — Use the strict OCR-mode parser instead of the
                # general-purpose one. The general-purpose parser produces
                # ~160 noisy rows from this layout (summary lines + check-
                # image attachment garbage); the strict parser produces
                # ~92 clean rows matching the Grok Vision baseline.
                fallback_txns = _parse_ocr_lines_to_transactions(ocr_lines, default_year)
                fallback_txns = _filter_balance_only_rows(_dedupe_transactions(fallback_txns))
                fallback_rows = len(fallback_txns)
                pipeline_logs.append(
                    _log(
                        "info",
                        f"EasyOCR fallback (strict mode) produced {fallback_rows} "
                        f"transaction(s) from {len(ocr_lines)} OCR line(s).",
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

    grok_totals = _compute_grok_totals(canonical, summary_override=summary_override)
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


def _compute_grok_totals(
    transactions: list[dict[str, Any]],
    *,
    summary_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute reconciliation totals (matches Grok TOTALS line shape).

    When ``summary_override`` is provided (typically the result of
    :func:`_extract_statement_summary`), its ``deposits`` / ``withdrawals``
    values take precedence — the statement's own self-reported totals are
    always more trustworthy than rows fished out of OCR text because they
    sit cleanly in the Statement Summary block, not the noisy transaction
    detail. The ``checks`` and ``transactions`` counts always come from the
    detail rows because those are what downstream consumers (Power Query,
    Process-Statement.ps1) actually iterate over.
    """

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

    totals: dict[str, Any] = {
        "deposits": round(deposits, 2),
        "withdrawals": round(withdrawals, 2),
        "checks": checks,
        "transactions": len(transactions),
    }

    if summary_override:
        if isinstance(summary_override.get("deposits"), (int, float)):
            totals["deposits"] = round(float(summary_override["deposits"]), 2)
        if isinstance(summary_override.get("withdrawals"), (int, float)):
            totals["withdrawals"] = round(float(summary_override["withdrawals"]), 2)
    return totals


# ---------------------------------------------------------------------------
# v2.44 — Statement Summary extractor (authoritative source totals)
# ---------------------------------------------------------------------------
# The Statement Summary block at the top of every Traditions Bank statement
# (and most US bank statements) declares the period's deposits/withdrawals
# totals BEFORE the detail rows. Parsing them directly is far more reliable
# than summing OCR-derived transactions — the summary numbers are typeset
# cleanly while the detail rows are scanned at varying quality. We capture
# both values and feed them into ``_compute_grok_totals`` as the source of
# truth so the reconciliation banner anchors against the bank's own number.

_SUMMARY_DEPOSITS_RE = re.compile(
    r"(?im)^\s*(?:deposits?\s+and\s+other\s+(?:credits?|debits?)|"
    r"total\s+deposits?(?:\s+and\s+credits?)?|"
    r"total\s+credits?)\s*[_:\-]*\s*"
    r"\$?\s*(\d{1,3}(?:,\d{3})*\.\d{2})\s*\+?\s*$"
)

_SUMMARY_WITHDRAWALS_RE = re.compile(
    r"(?im)^\s*(?:\d+\s+)?(?:withdrawals?\s+and\s+other\s+(?:debits?|credits?)|"
    r"total\s+withdrawals?(?:\s+and\s+debits?)?|"
    r"total\s+debits?)\s*[_:\-]*\s*"
    r"\$?\s*(\d{1,3}(?:,\d{3})*\.\d{2})\s*[\-+]?\s*$"
)

# "83 Withdrawals and Other Debits 41,403.63 -" → captures leading count
_SUMMARY_WITHDRAWAL_COUNT_RE = re.compile(
    r"(?im)^\s*(\d+)\s+withdrawals?\s+and\s+other\s+(?:debits?|credits?)\s+"
    r"\$?\s*\d{1,3}(?:,\d{3})*\.\d{2}"
)
_SUMMARY_DEPOSIT_COUNT_RE = re.compile(
    r"(?im)^\s*(\d+)\s+deposits?\s+and\s+other\s+(?:credits?|debits?)\s+"
    r"\$?\s*\d{1,3}(?:,\d{3})*\.\d{2}"
)


def _extract_statement_summary(lines_or_text: list[str] | str) -> dict[str, Any]:
    """Parse the Statement Summary block for authoritative deposit/withdrawal totals.

    Returns a dict with any of ``deposits``, ``withdrawals``,
    ``deposits_count``, ``withdrawals_count`` keys that could be parsed
    (missing keys = pattern not found). The parser is intentionally
    permissive about surrounding whitespace and trailing ``+`` / ``-``
    signs because the Traditions Bank PDF prints them, and EasyOCR usually
    reads them as separate tokens but the line text still has them
    appended (e.g. "Deposits and Other Credits_ 41,786.80+").
    """

    if isinstance(lines_or_text, list):
        text = "\n".join(lines_or_text)
    else:
        text = str(lines_or_text or "")
    if not text.strip():
        return {}

    summary: dict[str, Any] = {}
    m = _SUMMARY_DEPOSITS_RE.search(text)
    if m:
        try:
            summary["deposits"] = float(m.group(1).replace(",", ""))
        except ValueError:
            pass
    m = _SUMMARY_WITHDRAWALS_RE.search(text)
    if m:
        try:
            summary["withdrawals"] = float(m.group(1).replace(",", ""))
        except ValueError:
            pass
    m = _SUMMARY_DEPOSIT_COUNT_RE.search(text)
    if m:
        try:
            summary["deposits_count"] = int(m.group(1))
        except ValueError:
            pass
    m = _SUMMARY_WITHDRAWAL_COUNT_RE.search(text)
    if m:
        try:
            summary["withdrawals_count"] = int(m.group(1))
        except ValueError:
            pass
    return summary


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

# v2.44.3: OCR-tolerant strip for the "PAY TO THE ORDER OF" header text that
# EasyOCR keeps re-emitting inside the cropped check tile. Accepts misreads
# like "ORDER OFE", "ORDER OF_", "OFE", "Pay to The OF:" etc. Used by
# ``_is_clean_payee`` and (transitively) ``_match_checks_to_transactions``.
_PAYEE_HEADER_STRIP_RE = re.compile(
    r"^(?:pay\w{0,3}|to|the|order|of\w{0,2}|payee)"
    r"(?:[\s\-*:$_]+(?:pay\w{0,3}|to|the|order|of\w{0,2}|payee))*"
    r"[\s\-*:$_]*",
    re.IGNORECASE,
)


def _is_clean_payee(text: str) -> bool:
    """Return True if ``text`` looks like a usable business/person name.

    The check-image EasyOCR pass routinely produces garbage tokens after
    stripping the "PAY TO THE ORDER OF" header — e.g. ``"0 Os.90"``,
    ``"CRDER OK Som QS0-0j"``, ``"ORDER OF Gstnaktop 1 Oo_ 738.D3"``,
    ``"Order Of 77"``, ``"ORDER OFE Hluuk"``. Without a quality gate the
    matcher swaps these into ``Payee`` and stamps ``Confidence=High``,
    which is exactly the visible bug in
    ``Data/2026-05-26T11-22_export.csv`` (10 rows polluted).

    The function errs on the side of *rejecting* — a false-reject costs
    Laura a single Payee field to fill in by hand (the row is still
    linked via the matcher), while a false-accept pollutes the export.

    Heuristics (any failing rule → reject):
        1. empty / <4 chars / >80 chars after strip
        2. after stripping "(pay)/(to)/(the)/(order)/(of[a-z]{0,2})" header
           variants the remainder must still be ≥4 chars and start with a
           letter
        3. no single token may mix letters + digits (strongest OCR-garbage
           signal — "Slon8if4", "QS0-0j", "Os.90", "738.D3", "4Eiies")
        4. digit-to-letter ratio ≤ 0.40 and non-alnum density ≤ 20%
        5. must contain at least one vowel (random consonants → reject)
        6. single-word remainder must be ≥6 chars (catches "Hluuk",
           "Wuulu", "Eiies"; accepts "Target", "Costco", "Google")
    """

    if not text:
        return False
    s = str(text).strip()
    if len(s) < 4 or len(s) > 80:
        return False

    stripped = _PAYEE_HEADER_STRIP_RE.sub("", s).strip(" -*:_$")
    if len(stripped) < 4:
        return False

    if not stripped[0].isalpha():
        return False

    for tok in stripped.split():
        if any(c.isalpha() for c in tok) and any(c.isdigit() for c in tok):
            return False

    letters = sum(1 for c in stripped if c.isalpha())
    digits = sum(1 for c in stripped if c.isdigit())
    nonalnum_nonspace = sum(
        1 for c in stripped if not c.isalnum() and not c.isspace() and c != "&"
    )
    if letters == 0:
        return False
    if digits / letters > 0.40:
        return False
    if nonalnum_nonspace / len(stripped) > 0.20:
        return False

    if not re.search(r"[aeiouAEIOU]", stripped):
        return False

    if " " not in stripped and len(stripped) < 6:
        return False

    return True


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
        and not bit.startswith("OCR fallback —")
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
        raw_new_payee = extracted_payee.strip() if extracted_payee else ""

        # v2.44.3: gate the payee swap on ``_is_clean_payee`` so OCR garbage
        # tokens (`"Os.90"`, `"CRDER OK Som QS0-0j"`, `"ORDER OF _ 6 3 Zhe"`,
        # …) can never pollute Payee or falsely upgrade Confidence to High.
        # The match_idx assignment itself (check# / amount / fuzzy) IS still
        # authoritative — the row was verified against a cropped check
        # image — so we always record ``linked_check_id`` and a clarifying
        # ReviewReason. We only swap Payee when the cleaned token survives
        # quality checks.
        new_payee_is_clean = _is_clean_payee(raw_new_payee)

        should_swap = new_payee_is_clean and (
            not old_payee
            or old_payee.lower() == "uncategorized"
            or _fuzzy_ratio(old_payee, raw_new_payee) < 0.85
        )

        if should_swap:
            txn["Payee"] = raw_new_payee
            txn["Confidence"] = "High"
            txn["NeedsReview"] = "No"
            txn["ReviewReason"] = _build_review_reason(
                str(txn.get("ReviewReason", "")),
                f"Payee from check image ({match_reason})",
            )
        else:
            # Match found but the extracted payee was empty OR failed the
            # quality guard. Record the link and downgrade Medium-or-lower
            # rows to ``Low`` so Laura sees they need a human-typed payee;
            # never downgrade rows already at ``High`` (e.g. set elsewhere
            # by the rules engine on the fast path).
            cur_conf = str(txn.get("Confidence", "")).strip().lower()
            if cur_conf != "high":
                txn["Confidence"] = "Low"
                txn["NeedsReview"] = "Yes"
            txn["ReviewReason"] = _build_review_reason(
                str(txn.get("ReviewReason", "")),
                f"Linked via {match_reason} (no clean payee from image)",
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
    r"previous\s+balance\s+[\d$,]|previous\s+balance\s+on\s+\d|"
    r"balance\s+as\s+of\s+\d|total\s+for\s|subtotal|"
    r"number\s+of\s+(deposits|withdrawals|credits|debits|checks)|"
    r"^\s*\*\s*indicates\s+a\s+break|interest\s+earned\s+this\s+period|"
    r"telephone\s+banking|www\.|^\s*[(]?\d{3}[)]?[-.\s]?\d{3}[-.\s]?\d{4}\s*$|"
    # v2.44 — summary block + check-image attachment skip patterns. These
    # never produce transactions on their own (the dollar values feed
    # `_extract_statement_summary` directly via the grok_totals path).
    r"^\s*statement\s+summary\s*$|^\s*statement\s+activity\b|"
    r"^\s*\d+\s+(deposits?|withdrawals?|debits?|credits?|checks?)\s+and\s+other\b|"
    r"^\s*(deposits?|withdrawals?|credits?|debits?)\s+and\s+other\s+(credits?|debits?)\s*[_:]*\s*\d|"
    r"^\s*summary\s+of\s+fees\b|^\s*reporting\s+period\b|"
    r"^\s*total\s+(overdraft|returned)\b|^\s*refunded\s+fees\s+for\b|"
    r"^\s*denotes\s+missing\s+check\b|"
    r"^\s*deposit\s+ticket\b|^\s*depobit\s+ticket\b|"
    r"^\s*pay\s+to\s+the\s+order\b|^\s*order\s+of\b|^\s*memo\b|"
    r"^\s*dollars\s*$|^\s*dollars\s+[a-z@]|"
    r"^\s*terminal\s+(d|i|did|id)\s*[:#]?|^\s*serial\s*#|"
    r"^\s*tradition[sa]?\s*bank\b|^\s*building\s+bridges\b|"
    r"^\s*how\s+to\s+balance\b|^\s*in\s+case\s+of\s+errors\b|"
    r"^\s*hints\s+for\s+finding\b|^\s*clip\s+and\s+return\b|"
    r"^\s*for\s+(a\s+)?change\s+of\s+(name|address)\b|"
    r"^\s*new\s+balance\b|^\s*sub\s*total\b|"
    r"^\s*p\.?o\.?\s*box\s+\d|"
    r"^\s*(date|number|amount|balance)(\s+(date|number|amount|balance))+\s*$|"
    r"^\s*date\s+(description|number|check)\s*(amount)?\s*$)"
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
    "daily account balance",
    "daily account balances",
    "statement balance summary",
    "balance summary",
    "account summary",
    # v2.44 — anything after these on a scanned/OCR statement is
    # check-image attachment noise (deposit tickets, pay-to-the-order
    # blocks, memo lines, OCR-garbled letterheads). Hard-stop the parser
    # rather than try to fish real transactions out of OCR jibberish.
    "summary of fees",
    "summary of fees for paying",
    "summary of fees for paying and returning items",
    "fees for paying",
    "refunded fees for",
    "for a change of name",
    "for a change of address",
    "how to balance your account",
    "in case of errors or questions",
    "hints for finding differences",
    "clip and return",
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
        # v2.44.3: when the strict OCR parser already validated date + amount
        # (the common case for the Auto Body Center test PDF), the only
        # thing left to verify is the payee. The longer "verify amount +
        # payee" wording was correct in v2.43 when the parser was producing
        # bogus amounts; with the strict parser it's misleading noise.
        if date and signed:
            review_reasons.append("OCR fallback — verify payee")
        else:
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
        r"^balance\s*(forward|brought\s*forward)?\s*$|^total\b|"
        r"^statement\s+(summary|activity)\b|"
        r"^\d+\s+(deposits?|withdrawals?|debits?|credits?|checks?)\s+and\s+other\b"
    )
    for row in transactions:
        desc = str(row.get("Description", "")).strip()
        if not desc or bad_desc.match(desc):
            continue
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# v2.44 — Strict OCR-mode line parser
# ---------------------------------------------------------------------------
# The general-purpose `_parse_lines_to_transactions` does an OK job on clean
# pdfplumber text but creates a mess on noisy EasyOCR output for scanned
# statements: summary lines like "83 Withdrawals and Other Debits 41,403.63"
# get turned into transactions, multi-amount Check Register rows collapse to
# one row, continuation lines (MERCH BNKCD NSD DEPOSIT, Internet transfer
# to checking 6247002) become standalone date-only rows, and the check-image
# attachment pages (pages 5-9 on Auto Body Center Jan-26) flood the result
# with OCR-garbled gibberish — including the infamous "MEM0393042022.77230"
# memo line that produced a $393M withdrawal in v2.43.2.
#
# `_parse_ocr_lines_to_transactions` is a stricter walk that:
#   1. Hard-stops at the first "Daily Account Balance" / "Summary of Fees"
#      terminator — anything after that on a scanned statement is page
#      footer / check-image attachments and should never be parsed.
#   2. Only starts a new transaction when it sees a full MM/DD/YYYY (or
#      MM/DD/YY) date prefix, never on a bare date fragment.
#   3. Merges continuation lines (no date, no amount, not a section header)
#      into the previous transaction's Description so MERCH BNKCD NSD DEPOSIT
#      attaches to "01/20/2026 Ach deposit 499.22" instead of becoming a
#      zero-amount sibling row. Capped at 2 continuation lines per row to
#      keep descriptions tidy.
#   4. Parses Check Register lines as 1-3 (date, check#, amount) triplets
#      and produces one transaction per triplet with Check# populated so
#      the v2.43 check-image matcher has something to link against.
#   5. Aggressively skips OCR-junk lines (Terminal/Serial #, MEMO, DOLLARS,
#      check-image deposit ticket headers, bank letterhead, page footer).
#
# Designed for the Traditions Bank layout but built from generic patterns
# (section markers, ISO/MDY date, $ amounts) so it should hold up on most
# US small-business bank statements without further tweaking.

_CHECK_REG_TRIPLET_RE = re.compile(
    r"(\d{1,2}[/-]\d{1,2})\s+\*?\s*(\d{3,6})\s*\*?\s+"
    r"(\d{1,3}(?:,\d{3})*\.\d{2})"
)
_FULL_DATE_PREFIX_RE = re.compile(
    r"^\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})(?!\d)(?:\s+(.*))?$"
)
_OCR_JUNK_TERMINAL_RE = re.compile(r"(?i)\b(?:terminal\s+(?:d|i|did|id)\b|serial\s*#)")


def _is_ocr_junk_text(line: str) -> bool:
    """True for lines that are pure OCR noise — memos, gibberish, letterhead.

    Used by the strict OCR parser to refuse merging a noisy continuation
    line into the previous transaction's description, and to reject
    fresh rows whose description would be unreadable downstream.
    """

    if not line:
        return True
    s = line.strip()
    if len(s) < 3:
        return True
    if _OCR_JUNK_TERMINAL_RE.search(s):
        return True
    low = s.lower()
    if low.startswith("memo") or low.startswith("dollars"):
        return True
    if low.startswith("pay to") or "order of" in low:
        return True
    if "deposit ticket" in low or "depobit ticket" in low:
        return True
    if low in {"on", "in", "by", "at", "to", "of", "the", "for"}:
        return True
    # Alphanumeric ratio — gibberish often has lots of punctuation/symbols.
    total = len(s)
    alnum = sum(1 for c in s if c.isalnum() or c.isspace())
    if total >= 4 and (alnum / total) < 0.60:
        return True
    # Mostly digits and noise (no letters at all) — probably an account
    # / routing / serial number fragment, not a description.
    if not re.search(r"[A-Za-z]{2,}", s):
        return True
    return False


def _is_meaningful_ocr_description(desc: str) -> bool:
    """Reject descriptions that are too short or all-gibberish before commit."""

    if not desc or len(desc.strip()) < 3:
        return False
    if not re.search(r"[A-Za-z]{2,}", desc):
        return False
    # Bare check-number fragments slipped through? Allow them; the caller
    # will set Check# explicitly. Otherwise we keep ~92% of valid rows.
    return True


def _eft_ach_fix(text: str) -> str:
    """Normalize the common EasyOCR misread "EFTIACH" → "EFT/ACH".

    EasyOCR reads the slash in "EFT/ACH" as a capital I about half the
    time on the Traditions Bank font. Done here (not in the OCR layer)
    so the fix is local to description text and doesn't accidentally
    touch a serial number or memo field.
    """

    return re.sub(r"\bEFT[I/]?ACH\b", "EFT/ACH", text, flags=re.IGNORECASE).replace(
        "EFTIACH", "EFT/ACH"
    )


# Matches money tokens that may have OCR letter substitutions (O→0, I→1, l→1)
# in either the integer or fractional part. Examples this catches:
#   1,000.00   1,00O.OO   1,Ooo.00   I,000.00   l00.00
_OCR_MONEY_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])\$?(?:[\dOoIl]{1,3}(?:,[\dOoIl]{3})+|[\dOoIl]+)\.[\dOoIl]{2}(?![A-Za-z0-9])"
)


def _preprocess_ocr_line(line: str) -> str:
    """Fix common EasyOCR transcription errors in numeric / money tokens.

    EasyOCR routinely mis-classifies digits 0/1 as letters O/l and
    sometimes scatters whitespace around the thousands separator and
    decimal point in scanned monetary amounts. Examples seen on the
    Auto Body Center Jan-26 PDF:

        ``1,00O.OO``              → ``1,000.00``
        ``1 , Ooo. 00``           → ``1,000.00``
        ``1,000.0O``              → ``1,000.00``
        ``EFTIACH Debit 700.00``  → ``EFT/ACH Debit 700.00``

    The cleanup is intentionally scoped to money-shaped tokens (digits
    + thousands separator + decimal cents) so prose like
    ``"Pay TO the order"`` is never accidentally rewritten to
    ``"Pay 70 the order"``.
    """

    if not line:
        return line

    # Step 1: collapse OCR whitespace around the thousands separator and
    # the decimal point when both neighbors look numeric (or are 0↔O).
    s = re.sub(r"([\d])\s*,\s*([\dOoIl])", r"\1,\2", line)
    s = re.sub(r"([\dOoIl])\s*\.\s*([\dOoIl])", r"\1.\2", s)

    # Step 2: substitute O→0 / o→0 / I→1 / l→1 inside money tokens only.
    def _fix(match: re.Match[str]) -> str:
        tok = match.group(0)
        return (
            tok.replace("O", "0").replace("o", "0").replace("I", "1").replace("l", "1")
        )

    s = _OCR_MONEY_TOKEN_RE.sub(_fix, s)

    # Step 3: normalize EFTIACH / EFT|ACH variants in-line so the amount
    # parser doesn't confuse "Debit 1,000.00" with the I in EFTIACH.
    s = _eft_ach_fix(s)
    return s


_DATE_ONLY_RE = re.compile(r"^\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s*$")
_LEADING_DATE_RE = re.compile(r"^\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})(?!\d)")
_HAS_AMOUNT_RE = re.compile(r"\d{1,3}(?:,\d{3})*\.\d{2}")
_VERB_HINT_RE = re.compile(
    r"(?i)\b(ach|eft/?ach|eftiach|debit|credit|withdrawal|deposit|"
    r"transfer|wire|check|payment|pos|merch|paypal|venmo|zelle|"
    r"card|atm|service|charge|fee|epay)\b"
)


def _fuse_split_date_lines(lines: list[str]) -> list[str]:
    """Fuse adjacent OCR lines where the statement's date column got split.

    Traditions Bank (and other small-bank layouts) prints each
    transaction with its date in the leftmost column, but EasyOCR's
    y-bucket line reconstruction occasionally separates the date into
    its own line. We see three flavors on the Auto Body Center Jan-26
    PDF that all drop transactions or corrupt descriptions when fed
    unmodified through the strict parser:

    **Pattern A** — date arrives AFTER the verb+amount line ::

        "Ach withdrawal 34.65"      -> "01/12/2026 Ach withdrawal 34.65"
        "01/12/2026"                   (line removed)
        "CLOVFR FFES CLOVFR FEE"       (unchanged, becomes continuation)

    **Pattern B** — date arrives BEFORE a verb-only line that belongs
    to the same transaction ::

        "Ach withdrawal"            -> "01/28/2026 Ach withdrawal 226.05"
        "01/28/2026 226.05"            (consumed into preceding line)
        "WOODMEN,OMAHA NE PREMUM"      (unchanged, becomes continuation)

    **Pattern C** — date is alone on its line, next line is verb+amount
    with no date of its own (seen on the Auto Body Center 01/05 Texaco
    72.00 debit, where the bucketed y-positions split the date off) ::

        "01/05/2026"                -> "01/05/2026 Debit Card Transaction 72.00"
        "Debit Card Transaction 72.00" (consumed)
        "TEXACO 0302812 CULLMAN AL"    (unchanged, becomes continuation)

    All patterns are only triggered when the candidate verb line
    contains a clear transaction-verb keyword (ACH / EFT / Debit Card /
    PayPal / etc.) so we never accidentally fuse genuine free-text
    description lines with adjacent date markers.
    """

    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        if i + 1 < n:
            nxt = lines[i + 1].strip()

            # Pattern A: current line is "<verb> <amount>" with no date,
            # next line is just a date.
            date_only_m = _DATE_ONLY_RE.match(nxt)
            if (
                date_only_m
                and not _LEADING_DATE_RE.match(line)
                and _HAS_AMOUNT_RE.search(line)
                and _VERB_HINT_RE.search(line)
            ):
                out.append(f"{date_only_m.group(1)} {line}")
                i += 2
                continue

            # Pattern C: current line is just a date, next line has the
            # verb + amount (no date). EasyOCR bucketed the date into a
            # separate y-row from the rest of the transaction row.
            date_only_cur_m = _DATE_ONLY_RE.match(line)
            if (
                date_only_cur_m
                and not _LEADING_DATE_RE.match(nxt)
                and _HAS_AMOUNT_RE.search(nxt)
                and _VERB_HINT_RE.search(nxt)
            ):
                out.append(f"{date_only_cur_m.group(1)} {nxt}")
                i += 2
                continue

            # Pattern B: current line is a short verb-only line, next
            # line has a date AND an amount BUT no verb of its own. The
            # "no verb on next line" guard is crucial — without it we
            # accidentally hoist genuine continuation lines (PAYPAL NNST
            # XFER, MERCH BNKCD NSD DEPOSIT, Regular Deposit) into the
            # next transaction row, corrupting both rows.
            nxt_date_m = _LEADING_DATE_RE.match(nxt)
            if (
                nxt_date_m
                and not _LEADING_DATE_RE.match(line)
                and not _HAS_AMOUNT_RE.search(line)
                and _HAS_AMOUNT_RE.search(nxt)
                and _VERB_HINT_RE.search(line)
                and len(line.split()) <= 4
            ):
                date_str = nxt_date_m.group(1)
                nxt_rest = nxt[nxt_date_m.end() :].strip()
                if not _VERB_HINT_RE.search(nxt_rest):
                    out.append(f"{date_str} {line} {nxt_rest}".strip())
                    i += 2
                    continue

        out.append(line)
        i += 1
    return out


_DATE_AMT_NO_CHECK_RE = re.compile(
    r"(\d{1,2}[/-]\d{1,2})\s+(\d{1,3}(?:,\d{3})*\.\d{2})(?:\s+|$)"
)
_BARE_CHECK_NUM_RE = re.compile(r"^\s*(\d{4})\s*$")


def _splice_orphan_check_numbers(lines: list[str]) -> list[str]:
    """Splice bare check numbers floated to their own line into the
    check-register triplet that should have contained them.

    EasyOCR occasionally drops one of the three check numbers in a
    3-triplet check-register row to its own y-bucket. Example seen on
    Auto Body Center Jan-26 ::

        "01/08 905.80 01/22 2505 340.97 01/29 2527 643.49"  (missing 2488)
        "2488"                                                (orphan)

    We detect this by scanning each line for a "<date> <amount>" pair
    with no intervening check number (using ``_DATE_AMT_NO_CHECK_RE``)
    and, if the *next* line is a bare 4-digit number that is NOT itself
    a valid check-register triplet line, we splice it in. Cheap and
    conservative — only fires when both halves of the pattern match.
    """

    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        # Look for a "<date> <amount>" pair at the very front of the
        # line with no check number between them. Only mutate when the
        # next line is a bare 4-digit check candidate.
        if (
            i + 1 < n
            and _CHECK_REG_TRIPLET_RE.search(line) is None
            and (m := _DATE_AMT_NO_CHECK_RE.match(line))
            and (bare := _BARE_CHECK_NUM_RE.match(lines[i + 1].strip()))
        ):
            date_str, amt_str = m.group(1), m.group(2)
            check_no = bare.group(1)
            rest = line[m.end() :].strip()
            spliced = f"{date_str} {check_no} {amt_str}"
            if rest:
                spliced = f"{spliced} {rest}"
            out.append(spliced)
            i += 2
            continue
        # Also handle the more general case: any line that already has
        # one or two triplets but starts with a "<date> <amount>" pair
        # (instead of "<date> <check> <amount>"). The bare orphan must
        # be on the very next line.
        if (
            i + 1 < n
            and (mm := _DATE_AMT_NO_CHECK_RE.match(line))
            and _CHECK_REG_TRIPLET_RE.search(line)
            and (bare2 := _BARE_CHECK_NUM_RE.match(lines[i + 1].strip()))
        ):
            date_str = mm.group(1)
            amt_str = mm.group(2)
            check_no = bare2.group(1)
            rest = line[mm.end() :].strip()
            spliced = f"{date_str} {check_no} {amt_str}"
            if rest:
                spliced = f"{spliced} {rest}"
            out.append(spliced)
            i += 2
            continue
        out.append(line)
        i += 1
    return out


def _parse_ocr_lines_to_transactions(
    lines: list[str], default_year: int
) -> list[dict[str, Any]]:
    """Strict OCR-mode parser — see module docstring above for design notes."""

    # Step 0a: clean up OCR letter↔digit substitutions and whitespace so
    # the amount regex can actually fire on lines like "1 , Ooo. 00".
    lines = [_preprocess_ocr_line(raw) for raw in lines]
    # Step 0b: fuse split date-from-row patterns A, B, C (see helper above).
    lines = _fuse_split_date_lines(lines)
    # Step 0c: splice orphan check numbers back into their check-register
    # triplet. EasyOCR sometimes drops one of the three check numbers in
    # a 3-triplet row to its own line (we saw "01/08 905.80 01/22 2505
    # 340.97 01/29 2527 643.49" + "2488" on Auto Body Center Jan-26).
    lines = _splice_orphan_check_numbers(lines)

    out: list[dict[str, Any]] = []
    current_section: str | None = None
    terminated = False

    # Pending row state: we saw at least one half of a transaction (a
    # date, an amount, or partial desc) and are accumulating the rest
    # across the next couple of lines. Common splits on EasyOCR output:
    #   - "01/16/2026 1,177.00" then "Regular Deposit" (date+amt, desc next)
    #   - "01/07/2026 Ach withdrawal" then "30.52" then "PAYPAL NNST XFER"
    pending: dict[str, Any] | None = None
    last_row: dict[str, Any] | None = None
    last_row_continuations = 0
    MAX_CONTINUATIONS = 2

    def _try_commit_pending(*, force_drop: bool = False) -> None:
        """Commit pending if it has date+amount+meaningful desc.

        When ``force_drop`` is True (called at section / new-date / EOL
        boundaries), an incomplete pending row is discarded. Otherwise
        pending stays alive so a follow-on line can supply the missing
        description / amount.
        """

        nonlocal pending, last_row, last_row_continuations
        if pending is None:
            return
        date_ok = bool(pending.get("date"))
        amt_ok = pending.get("amount") is not None
        desc = _eft_ach_fix(_strip_trailing_amounts((pending.get("desc") or "").strip()))
        desc_ok = _is_meaningful_ocr_description(desc)
        if date_ok and amt_ok and desc_ok:
            chk = _extract_check_number(desc) or pending.get("check_num", "")
            row = _build_row(
                date=pending["date"],
                description=desc,
                amount=pending["amount"],
                check_num=chk,
                year_month=pending.get("ym", ""),
                default_year=default_year,
                section=current_section,
                source="easyocr",
            )
            out.append(row)
            last_row = row
            last_row_continuations = 0
            pending = None
        elif force_drop:
            pending = None

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        # 1) Section markers / terminators ---------------------------------
        sec = _detect_section(line)
        if sec == "end":
            _try_commit_pending(force_drop=True)
            current_section = None
            last_row = None
            terminated = True
            continue
        if terminated:
            # Hard-stop: nothing after Daily Account Balance / Summary of
            # Fees ever produces a transaction on a scanned statement.
            continue
        if sec:
            _try_commit_pending(force_drop=True)
            # When the section header is just repeated (page break /
            # "(continued)") keep `last_row` alive so a continuation line
            # arriving right after the repeat (PAYPAL NNST XFER, etc.)
            # still attaches to the prior transaction. Only reset on a
            # genuine section transition (credit→debit→check→end).
            if sec != current_section:
                last_row = None
                last_row_continuations = 0
            current_section = sec
            continue

        # 2) Pure noise / summary lines ------------------------------------
        if _should_skip_line(line):
            continue

        # 3) Check Register multi-triplet rows -----------------------------
        # Lines like "01/20 2419 100.00 01/14 2491 275.03 01/27 2508 99.37"
        # collapse to one transaction in the old parser. Here we extract
        # every (date, check#, amount) triplet and emit one row each.
        if current_section == "check":
            triplets = _CHECK_REG_TRIPLET_RE.findall(line)
            if triplets:
                _try_commit_pending(force_drop=True)
                for date_str, check_no, amt_str in triplets:
                    iso, ym = _normalize_date(date_str, default_year)
                    if not iso:
                        continue
                    try:
                        amt = float(amt_str.replace(",", ""))
                    except ValueError:
                        continue
                    row = _build_row(
                        date=iso,
                        description=f"Check #{check_no}",
                        amount=-abs(amt),
                        check_num=check_no,
                        year_month=ym,
                        default_year=default_year,
                        section="check",
                        source="easyocr",
                    )
                    out.append(row)
                last_row = None
                continue
            # No triplets — probably a header row, "Denotes missing check",
            # or a stray check-image OCR fragment. Don't try to parse it.
            continue

        # 4) Try to start a new transaction with a full date prefix --------
        full = _FULL_DATE_PREFIX_RE.match(line)
        if full:
            _try_commit_pending(force_drop=True)
            date_str, rest = full.group(1), (full.group(2) or "").strip()
            iso, ym = _normalize_date(date_str, default_year)
            if not iso:
                # Unparseable date — fall through and treat as continuation
                # of the last row if any.
                continue
            amounts = _parse_amounts(rest)
            clean_desc = _strip_trailing_amounts(_AMOUNT_RE.sub("", rest).strip())
            pending = {
                "date": iso,
                "ym": ym,
                "desc": clean_desc,
                "amount": _pick_transaction_amount(amounts) if amounts else None,
            }
            # Try to commit now; if desc is empty/short, _try_commit_pending
            # keeps pending alive so the next line can supply the missing
            # description (the "01/16/2026 1,177.00\nRegular Deposit" case).
            _try_commit_pending()
            continue

        # 5) Bare amount line — usually completes a pending date+desc row
        amounts = _parse_amounts(line)
        if amounts and pending is not None and pending.get("amount") is None:
            amt = _pick_transaction_amount(amounts)
            # Any non-numeric text on this line becomes part of the desc
            # (e.g. "30.52 PAYPAL NNST XFER" supplies both).
            extra = _strip_trailing_amounts(_AMOUNT_RE.sub("", line).strip())
            if extra and not _is_ocr_junk_text(extra):
                pending["desc"] = ((pending["desc"] or "") + " " + extra).strip()
            pending["amount"] = amt
            _try_commit_pending()
            continue

        if amounts:
            # Bare amount with no pending row — skip (probably an OCR'd
            # running balance or check-image fragment).
            continue

        # 6) Continuation line for the pending row (still gathering desc) --
        # Handles both "date+amt waiting for desc" and "date+desc waiting
        # for amount" — either way, append meaningful text to pending.desc
        # and re-try the commit.
        if pending is not None:
            if not _is_ocr_junk_text(line):
                merged = ((pending.get("desc") or "") + " " + line).strip()
                if len(merged) <= 120:
                    pending["desc"] = merged
                _try_commit_pending()
            continue

        # 7) Continuation line for the last committed row -------------------
        # Folds e.g. "MERCH BNKCD NSD DEPOSIT" onto the prior
        # "Ach deposit 499.22" row's description.
        if last_row is not None and last_row_continuations < MAX_CONTINUATIONS:
            if not _is_ocr_junk_text(line):
                merged = (str(last_row.get("Description", "")) + " " + line).strip()
                merged = _eft_ach_fix(_strip_trailing_amounts(merged))
                if len(merged) <= 120:
                    last_row["Description"] = merged
                    last_row["Payee"] = _infer_payee_from_description(
                        merged, str(last_row.get("Check#", ""))
                    )
                    last_row_continuations += 1
            continue

        # 8) Otherwise drop. Catches gibberish standalone lines on check
        # attachment pages — anything that doesn't fit a known shape.

    _try_commit_pending(force_drop=True)
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
