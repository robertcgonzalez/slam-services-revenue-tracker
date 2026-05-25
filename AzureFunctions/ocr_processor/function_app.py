"""SLAM Services OCR Processor — Azure Function (v2 programming model).

Strategic milestone from Blueprint Section 8.1: offload heavy OCR / check
cropping from the Streamlit App Service (F1) to a dedicated Function so the
daily-driver app stays lightweight.

v2.43 — Intelligent Check Image Linking & Payee Enhancement
-----------------------------------------------------------

The HTTP wire contract is identical to v2.42 (same 12-column transaction shape
+ `grok_totals` + `cropped_checks` array). New in v2.43: after both the OCR
parser and the check cropper run, ``_match_checks_to_transactions`` links each
cropped check image to its best-matching transaction and replaces the
parser's heuristic Payee with the human-written name extracted from the check
image via EasyOCR on the "Pay to the order of" line.

Pipeline stages:

1. **Fast path** — ``pdfplumber`` extracts text / words / tables from native
   text-layer PDFs and runs them through the same regex parser used by
   ``Scripts/bank-statement-parser.py`` (SECTION_MARKERS, CHECK_REGISTER_ROW_RE,
   pick_transaction_amount, etc.). This handles ~95% of real US bank statements
   in a fraction of a second.
2. **Scanned fallback** — when the fast path yields too few transactions
   (or zero text on a page), each page is rasterized via ``pdf2image`` at
   300 DPI and run through ``easyocr.Reader(['en'])``. The OCR text lines
   feed the same parser, so the response shape is identical.
3. **Check cropping** — port of ``Scripts/smart_check_cropper_final_dynamic.py``:
   OpenCV adaptive thresholds + contour detection at 250 DPI, aspect-ratio
   filter, EasyOCR keyword validation ("pay to", "order of", "memo",
   "dollars"), perceptual-hash dedup. Returns cropped checks as base64 PNGs.
   v2.43 also keeps the EasyOCR token-level detections in memory (not in the
   response) so the matcher can locate the payee line spatially.
4. **Check ↔ transaction matching (v2.43)** — for each cropped check, the
   matcher extracts (a) the check number (3–6 digit token in the upper-right
   region) and (b) the payee name (tokens on the "Pay to the order of" line)
   from the in-memory EasyOCR detections. It then tries to link the check to
   a transaction via three strategies, in priority order:

   - **Primary** — exact match on ``Check#``.
   - **Secondary** — amount + date proximity (when an amount can be parsed
     from the check image).
   - **Tertiary** — fuzzy match between the extracted payee and the
     transaction's Description (``difflib`` SequenceMatcher ratio ≥ 0.6).

   When a match is found, the matcher:

   - Replaces the transaction's ``Payee`` with the human-written name from
     the check image (e.g. ``"JOHN SMITH"`` → ``"John Smith"``) — but only
     when the extracted payee is more informative than what the parser
     already inferred from the Check Register row.
   - Bumps ``Confidence`` to ``High``, sets ``NeedsReview="No"``, and adds a
     ``ReviewReason="Payee from check image (...)"`` audit trail.
   - Adds a non-canonical ``linked_check_id`` field on the transaction so
     the Streamlit Bank Statements page can render the cropped image inline
     (planned for the App-side update; the wire contract preserves extras).
   - Adds ``linked_transaction_index`` / ``extracted_check_number`` /
     ``extracted_payee`` / ``extracted_payee_confidence`` on the
     ``cropped_checks`` entry for traceability.

   Unmatched checks are still returned in ``cropped_checks`` for manual
   review (``linked_transaction_index = -1``).

Wire format
-----------

POST  /api/ocr/process

Multipart form-data (preferred — large PDFs):
    file:        <pdf bytes>            (required)
    client:      "ACME Corp"            (optional metadata)
    filename:    "2026-01-statement.pdf"  (optional, falls back to upload name)
    request_id:  "<uuid>"               (optional, echoed back for traceability)

JSON body (alternative — small PDFs or testing):
    {
      "pdf_b64": "<base64-encoded PDF bytes>",
      "client":  "ACME Corp",
      "filename": "2026-01-statement.pdf",
      "request_id": "<uuid>"
    }

Response (always JSON):
    {
      "status": "success" | "partial" | "error",
      "version": "v2.43",
      "client": "...",
      "filename": "...",
      "request_id": "...",
      "transaction_count": <int>,
      "transactions": [
          {"Date": "YYYY-MM-DD", "Description": "...", "Payee": "...",
           "Amount": "<str>", "Check#": "", "Category": "Uncategorized",
           "SubCategory": "", "SignedAmount": "<str>", "YearMonth": "YYYY-MM",
           "Confidence": "High" | "Medium" | "Low",
           "NeedsReview": "Yes" | "No", "ReviewReason": "",
           "linked_check_id": "P00C01"},  # v2.43: optional, when matched
          ...
      ],
      "grok_totals": {
          "deposits": <float>, "withdrawals": <float>,
          "checks": <int>, "transactions": <int>
      },
      "cropped_checks": [
          {"check_id": "P00C00", "page": 1, "width": 980, "height": 420,
           "aspect_ratio": 2.33, "image_b64": "<base64 PNG>", "notes": "...",
           # v2.43: matcher metadata (always present, even when no match):
           "extracted_check_number": "1234",
           "extracted_payee": "John Smith",
           "extracted_payee_confidence": 0.87,
           "linked_transaction_index": 4}
      ],
      "logs": ["[INFO] ...", "[WARN] ...", ...],
      "message": "..."
    }

The 12-column transaction shape matches ``GROK_CSV_COLUMNS`` /
``GROK_CSV_FIELDS`` in ``App/bank_statements.py`` so the response drops
straight into the existing review UI, payee rules engine, reconciliation
banner, and Power Query / Process-Statement.ps1 downstream workflow.
"""

from __future__ import annotations

import base64
import difflib
import hashlib
import io
import json
import logging
import os
import re
import uuid
from datetime import datetime
from typing import Any

import azure.functions as func

PIPELINE_VERSION = "v2.43"

# Match the canonical 12-column order Bank Statements expects so the response
# drops straight into the same review UI / Power Query workflow.
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

# Auth level is FUNCTION by default — caller must pass `?code=<key>` or the
# `x-functions-key` header. ANONYMOUS is allowed for local dev only when the
# OCR_FUNCTION_ANON_LOCAL env var is set to "1" (never in production).
_AUTH_LEVEL = (
    func.AuthLevel.ANONYMOUS
    if os.environ.get("OCR_FUNCTION_ANON_LOCAL", "").strip() in ("1", "true", "yes")
    else func.AuthLevel.FUNCTION
)

# Pipeline tunables (override via App Settings if a specific client needs different limits).
OCR_DPI_TEXT = int(os.environ.get("OCR_DPI_TEXT", "300"))
OCR_DPI_CROP = int(os.environ.get("OCR_DPI_CROP", "250"))
OCR_MAX_PAGES_RASTER = int(os.environ.get("OCR_MAX_PAGES_RASTER", "30"))
OCR_MAX_CHECKS = int(os.environ.get("OCR_MAX_CHECKS", "40"))
# If pdfplumber finds at least this many rows the raster fallback is skipped.
OCR_FAST_PATH_MIN_ROWS = int(os.environ.get("OCR_FAST_PATH_MIN_ROWS", "3"))

# Module-level cache for the heavy easyocr Reader (avoids reloading on warm calls).
_EASYOCR_READER: Any = None


app = func.FunctionApp(http_auth_level=_AUTH_LEVEL)


# ---------------------------------------------------------------------------
# HTTP entry points
# ---------------------------------------------------------------------------


@app.function_name(name="ocr_process")
@app.route(route="ocr/process", methods=["POST"])
def ocr_process(req: func.HttpRequest) -> func.HttpResponse:
    """Main entry point — accepts a PDF + metadata, returns structured transactions."""

    request_id = req.headers.get("x-request-id") or str(uuid.uuid4())
    logger = logging.getLogger("slam.ocr")
    logger.setLevel(logging.INFO)

    logs: list[str] = []
    logs.append(_log("info", f"ocr_process invoked (request_id={request_id})"))

    try:
        pdf_bytes, metadata, parse_logs = _parse_request(req)
        logs.extend(parse_logs)
    except ValueError as exc:
        logs.append(_log("error", f"Bad request: {exc}"))
        return _json_response(
            status_code=400,
            body={
                "status": "error",
                "version": PIPELINE_VERSION,
                "request_id": request_id,
                "transaction_count": 0,
                "transactions": [],
                "logs": logs,
                "message": str(exc),
            },
        )

    metadata.setdefault("request_id", request_id)
    client = str(metadata.get("client") or "(unknown)")
    filename = str(metadata.get("filename") or "statement.pdf")

    logs.append(
        _log(
            "info",
            f"client={client!r} filename={filename!r} bytes={len(pdf_bytes)} "
            f"({len(pdf_bytes) / (1024 * 1024):.2f} MiB)",
        )
    )

    try:
        result = _run_ocr_pipeline(pdf_bytes, metadata, logs)
    except Exception as exc:  # noqa: BLE001 — function boundary; log and return 500
        logger.exception("OCR pipeline failed for request_id=%s", request_id)
        logs.append(_log("error", f"OCR pipeline crashed: {exc}"))
        return _json_response(
            status_code=500,
            body={
                "status": "error",
                "version": PIPELINE_VERSION,
                "client": client,
                "filename": filename,
                "request_id": request_id,
                "transaction_count": 0,
                "transactions": [],
                "logs": logs,
                "message": f"OCR pipeline crashed: {exc}",
            },
        )

    response_body: dict[str, Any] = {
        "status": result["status"],
        "version": PIPELINE_VERSION,
        "client": client,
        "filename": filename,
        "request_id": request_id,
        "transaction_count": len(result["transactions"]),
        "transactions": result["transactions"],
        "grok_totals": result["grok_totals"],
        "cropped_checks": result.get("cropped_checks", []),
        "logs": logs + result.get("logs", []),
        "message": result.get("message", ""),
    }

    return _json_response(status_code=200, body=response_body)


@app.function_name(name="ocr_health")
@app.route(route="ocr/health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def ocr_health(req: func.HttpRequest) -> func.HttpResponse:
    """Lightweight unauthenticated health check for the Streamlit sidebar status indicator."""

    capabilities = _detect_capabilities()
    return _json_response(
        status_code=200,
        body={
            "status": "ok",
            "version": PIPELINE_VERSION,
            "service": "slam-ocr-function",
            "auth_required": _AUTH_LEVEL == func.AuthLevel.FUNCTION,
            "capabilities": capabilities,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        },
    )


# ---------------------------------------------------------------------------
# Request parsing
# ---------------------------------------------------------------------------


def _parse_request(req: func.HttpRequest) -> tuple[bytes, dict[str, Any], list[str]]:
    """Resolve PDF bytes + metadata from either multipart form-data or JSON body."""

    logs: list[str] = []
    content_type = (
        req.headers.get("Content-Type") or req.headers.get("content-type") or ""
    ).lower()

    if "multipart/form-data" in content_type:
        files = getattr(req, "files", None)
        if not files or "file" not in files:
            raise ValueError(
                "multipart/form-data request must include a 'file' part with the PDF bytes."
            )
        file_part = files["file"]
        pdf_bytes = file_part.read() if hasattr(file_part, "read") else bytes(file_part)
        if not pdf_bytes:
            raise ValueError("Uploaded PDF is empty.")

        form = getattr(req, "form", None) or {}
        metadata: dict[str, Any] = {
            "client": form.get("client", ""),
            "filename": form.get("filename") or getattr(file_part, "filename", "statement.pdf"),
            "request_id": form.get("request_id", ""),
        }
        logs.append(_log("info", "Parsed multipart/form-data payload."))
        return pdf_bytes, metadata, logs

    raw_body = req.get_body() or b""
    if not raw_body:
        raise ValueError(
            "Empty request body. POST a PDF as multipart/form-data (preferred) or JSON "
            "with a 'pdf_b64' field."
        )

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Request body is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object with a 'pdf_b64' field.")

    pdf_b64 = payload.get("pdf_b64") or payload.get("pdf")
    if not pdf_b64 or not isinstance(pdf_b64, str):
        raise ValueError(
            "JSON body missing 'pdf_b64' (base64-encoded PDF bytes). "
            "Multipart upload is preferred for large files."
        )

    try:
        pdf_bytes = base64.b64decode(pdf_b64, validate=False)
    except Exception as exc:
        raise ValueError(f"Could not base64-decode 'pdf_b64': {exc}") from exc

    if not pdf_bytes:
        raise ValueError("Decoded PDF payload is empty.")

    metadata = {
        "client": payload.get("client", ""),
        "filename": payload.get("filename", "statement.pdf"),
        "request_id": payload.get("request_id", ""),
    }
    logs.append(_log("info", "Parsed JSON/base64 payload."))
    return pdf_bytes, metadata, logs


# ---------------------------------------------------------------------------
# OCR pipeline orchestration
# ---------------------------------------------------------------------------


def _run_ocr_pipeline(
    pdf_bytes: bytes,
    metadata: dict[str, Any],
    parent_logs: list[str],
) -> dict[str, Any]:
    """Production OCR pipeline (v2.42).

    Strategy:
        1. ``pdfplumber`` fast path → text + words + tables → regex parser.
        2. If transaction count is below the fast-path threshold, fall back to
           ``pdf2image`` rasterization at OCR_DPI_TEXT and run ``easyocr`` on
           each page; feed the OCR lines through the same parser.
        3. Always attempt the check cropper (OpenCV + EasyOCR validation);
           skip gracefully if cv2/PIL are missing.

    Returns the same dict shape as the v2.41 skeleton; callers see no contract change.
    """

    pipeline_logs: list[str] = []
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
                fallback_txns = _parse_lines_to_transactions(ocr_lines, default_year)
                fallback_txns = _filter_balance_only_rows(_dedupe_transactions(fallback_txns))
                fallback_rows = len(fallback_txns)
                pipeline_logs.append(
                    _log(
                        "info",
                        f"EasyOCR fallback produced {fallback_rows} transaction(s) "
                        f"from {len(ocr_lines)} OCR line(s).",
                    )
                )
                # Merge with fast-path output (dedup handles overlap on partial OCR).
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

    # 4) Normalize → 12-column shape + grok_totals + status -------------------
    canonical = [
        {field: row.get(field, "") for field in TRANSACTION_FIELDS} for row in transactions
    ]

    # 5) v2.43: link cropped checks to transactions + enrich Payee from image
    # (must run after canonicalization so the matcher mutates the canonical
    # rows that ship in the response). Safe no-op when there are 0 checks or
    # 0 transactions.
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
            f"Real OCR pipeline extracted {len(canonical)} transaction(s) "
            f"(fast path: {fast_path_rows}, OCR fallback: {fallback_rows}, "
            f"cropped checks: {len(cropped_checks)}, linked checks: {linked_count})."
        )
    elif canonical:
        status = "partial"
        message = (
            f"Real OCR pipeline extracted {len(canonical)} transaction(s) but below the "
            f"confidence threshold — please review."
        )
    else:
        status = "partial"
        message = (
            "Real OCR pipeline returned zero transactions. The PDF may have an "
            "unsupported layout or the raster libraries are not yet installed."
        )

    parent_logs.append(
        _log(
            "info",
            f"Pipeline complete: {len(canonical)} transaction(s), "
            f"{len(cropped_checks)} cropped check(s), {linked_count} linked.",
        )
    )

    return {
        "status": status,
        "transactions": canonical,
        "grok_totals": grok_totals,
        "cropped_checks": cropped_checks,
        "logs": pipeline_logs,
        "message": message,
    }


def _compute_grok_totals(transactions: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute reconciliation totals for the response (matches Grok TOTALS line)."""

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
                "truncating raster fallback to keep Y1 memory in bounds.",
            )
        )
        pages = pages[:OCR_MAX_PAGES_RASTER]

    reader = _get_easyocr_reader()
    logs.append(_log("info", f"EasyOCR reader ready; running on {len(pages)} page(s)."))

    all_lines: list[str] = []
    for page_idx, page in enumerate(pages):
        try:
            img = np.array(page)
            # detail=1 returns (bbox, text, confidence); we re-bucket by y to recover line order.
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


# Geometry tunables — slightly relaxed vs the 400 DPI script because we crop
# at 250 DPI here to keep Y1 memory bounded.
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
    """Detect, crop, and validate check images.

    v2.43 also returns a parallel ``detections_by_id`` mapping (check_id →
    raw EasyOCR token detections ``[(bbox, text, confidence), ...]``) so the
    matcher can locate the "Pay to the order of" line spatially without
    re-running OCR. The detections are intentionally NOT included in the
    HTTP response (they'd inflate the payload by 5-10×); only the matcher
    consumes them.
    """

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

                # v2.43: detail=1 + paragraph=False gives us per-token bboxes
                # so the matcher can locate the "Pay to the order of" line
                # without re-running OCR. The validation step below uses the
                # joined text exactly like v2.42 did, so the keyword/junk
                # filters are unchanged.
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
                        "notes": f"v2.43 grid+dedup (thresh {thresh_idx})",
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
#
# Inputs: the canonical transaction list (12-column dicts) + the cropped_checks
# list (each with check_id, page, image_b64, ...) + an in-memory mapping of
# check_id → raw EasyOCR detections [(bbox, text, confidence), ...] returned
# alongside `_crop_checks`.
#
# Outputs: same lists, mutated in place. Each matched transaction gains a
# `linked_check_id` field and (often) a better `Payee` taken from the
# "Pay to the order of" line in the check image. Each cropped check gains
# `extracted_check_number`, `extracted_payee`, `extracted_payee_confidence`,
# and `linked_transaction_index` (-1 when no match).
#
# Matching strategies in priority order:
#   1) Primary   — exact match on Check# (normalized: leading zeros stripped).
#   2) Secondary — amount + date proximity, when a $ amount can be parsed
#      from the check image (numeric "Pay $X" line).
#   3) Tertiary  — fuzzy match between the extracted payee and the
#      transaction's Description (difflib SequenceMatcher ratio ≥ _FUZZY_MIN).
#
# Logging: every check produces a single [INFO]/[WARN] line summarizing the
# extracted check#, extracted payee, match strategy used, and resulting
# Payee swap. Surfaces directly in the Streamlit Processing log expander.

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
# Catches "PAY TO THE ORDER OF" prefix even when EasyOCR returns it as a
# single multi-word token (so the per-token noise filter doesn't see it).
_PAYEE_LINE_PREFIX_RE = re.compile(
    r"^(?:pay(?:ee)?(?:\s+to)?(?:\s+the)?(?:\s+order)?(?:\s+of)?[:\s\-*$]*)+",
    re.IGNORECASE,
)
_CHECK_IMAGE_AMOUNT_RE = re.compile(r"\$\s*(\d{1,3}(?:,\d{3})*\.\d{2})")
_FUZZY_MIN = 0.60
_AMOUNT_MATCH_TOLERANCE = 0.01  # cents-level tolerance for amount equality


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
    """Find a 3-6 digit token in the upper-right of the check image.

    Personal/business checks print the check number in the top-right corner,
    typically twice (engraved + MICR line at the bottom). We score by
    (x_right - y_center) so upper-right tokens win.
    """

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

    # Only consider tokens in the upper ~35% (y) and right ~45% (x) of the crop.
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
        # Higher x and lower y win.
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

    Strategy:
        1. Bucket EasyOCR tokens into rough text lines by y-coordinate.
        2. Find the line containing "order of" (preferred) or "pay to".
        3. Take tokens to the right of "of"/"to" on that same line. If those
           tokens are too short / amount-like / missing, fall back to the
           tokens on the line immediately below (handwritten payee often
           overflows onto the next visual row in OCR output).
        4. Strip noise tokens (the/pay/to/order/of) and trailing $X.YZ amounts.
        5. Title-case all-caps results for nicer review UI.

    Returns (payee, avg_confidence). Empty string when no payee line found.
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
            # Find the rightmost edge of the "of" token to use as the x-cutoff.
            for j, tok in enumerate(line["tokens"]):
                t_low = tok["text"].lower().strip(":.,-* ")
                if t_low == "of":
                    cutoff_x = tok["x_right"]
                    break
                # Some OCR runs merge "order" and "of" → fall back to next-token edge.
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

    # First try same-line tokens to the right of "of"/"to".
    same_line_tokens = [
        tok
        for tok in lines[payee_line_idx]["tokens"]
        if cutoff_x is None or tok["x_left"] > cutoff_x
    ]
    candidates = _filter_payee_tokens(same_line_tokens)

    # If same-line is empty or too short, try the next line down.
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
        # Strip leading "PAY TO THE ORDER OF" even when it arrived as one
        # multi-word OCR token (the per-token filter only handles individual
        # noise words). Also strips a stray leading "$".
        out = _PAYEE_LINE_PREFIX_RE.sub("", out).strip()
        out = _PAYEE_TRAILING_AMOUNT_RE.sub("", out).strip(" -:|.,*$")
        out = re.sub(r"\s{2,}", " ", out).strip()
        return out

    raw = _clean_payee(" ".join(t["text"] for t in candidates))

    # If the same-line content cleaned down to nothing (because the entire line
    # WAS the "Pay to the order of" header itself), fall back to the next line.
    if (not raw or len(raw) < 2) and payee_line_idx + 1 < len(lines):
        next_line_tokens = lines[payee_line_idx + 1]["tokens"]
        next_candidates = _filter_payee_tokens(next_line_tokens)
        if next_candidates:
            candidates = next_candidates
            raw = _clean_payee(" ".join(t["text"] for t in candidates))

    if not raw or len(raw) < 2:
        return "", 0.0

    avg_conf = sum(t["conf"] for t in candidates) / max(len(candidates), 1)

    # Title-case obvious all-caps merchant names.
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
    """Link each cropped check to its best-matching transaction (in place).

    See module-level docstring for the strategy. Both ``transactions`` and
    ``cropped_checks`` are mutated in place (matched transactions gain a
    ``linked_check_id``; matched checks gain ``linked_transaction_index``).
    Returns ``(transactions, cropped_checks, logs)`` for clean inlining.
    """

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

    # Pre-index transactions by normalized Check# (primary match path).
    by_check_no: dict[str, list[int]] = {}
    for i, txn in enumerate(transactions):
        norm = _norm_check_no(str(txn.get("Check#", "")))
        if norm:
            by_check_no.setdefault(norm, []).append(i)

    # Prefer Check Register rows when amount+date matching, but allow any txn.
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

        # 1) Primary — exact Check# match.
        if extracted_check_no:
            norm = _norm_check_no(extracted_check_no)
            for idx in by_check_no.get(norm, []):
                if idx in used_txn_indices:
                    continue
                match_idx = idx
                match_reason = f"check# {extracted_check_no}"
                break

        # 2) Secondary — amount equality (only if check image yielded an amount).
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

        # 3) Tertiary — fuzzy match on extracted payee vs Description.
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

        # Only swap when the extracted payee is more informative than what we
        # already have (parser leaves Check# rows with Payee="" deliberately).
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
#
# Keeping this inline (rather than importing from /Scripts) so the Function is
# fully self-contained — the deployment zip never sees the Streamlit repo.

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

# Common merchant noise prefixes — used to infer Payee from Description when the
# Streamlit payee rules engine hasn't seen this merchant yet.
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
    """Cheap heuristic — strip common noise prefixes to surface the merchant.

    Real refinement happens in the App-side payee rules engine; this just gives
    a non-empty starting point so the Confidence column can be more useful.

    Checks deliberately return ``""`` so Laura can fill in the actual payee from
    the cropped check image (the number alone isn't a payee).
    """

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
    # Trim trailing run-on artifacts: store numbers / state codes / inline dates.
    cleaned = re.sub(r"\s+#\d+\b.*$", "", cleaned)
    cleaned = re.sub(r"\s+\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\s*$", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    # Title-case all-caps merchant names for nicer review UI.
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

    # Confidence baseline by source — pdfplumber text-layer is High when fully formed.
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
        conf = "Medium"  # OCR is never fully trusted as High
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


# ---------------------------------------------------------------------------
# Capability detection + low-level helpers
# ---------------------------------------------------------------------------


def _detect_capabilities() -> dict[str, bool]:
    """Report which optional OCR libraries are importable. Drives /ocr/health."""

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


def _log(level: str, message: str) -> str:
    """Format a structured log line matching the Streamlit-side processing log style."""

    return f"[{level.upper()}] {message}"


def _json_response(status_code: int, body: dict[str, Any]) -> func.HttpResponse:
    """Return a UTF-8 JSON response with consistent headers."""

    return func.HttpResponse(
        body=json.dumps(body, default=str),
        status_code=status_code,
        mimetype="application/json",
        charset="utf-8",
    )
