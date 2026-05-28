"""Azure AI Content Understanding — check imaging leg (``prebuilt-check.us``).

Uses the Foundry Content Understanding API (``*.services.ai.azure.com``), not the
Document Intelligence ``cognitiveservices.azure.com`` endpoint. Tabular register
pages stay on Document Intelligence via :mod:`azure_document_intelligence`.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any

AZURE_CU_ENDPOINT_ENV = "CONTENTUNDERSTANDING_ENDPOINT"
AZURE_CU_KEY_ENV = "CONTENTUNDERSTANDING_KEY"
AZURE_CU_CHECK_ANALYZER_ENV = "CONTENTUNDERSTANDING_CHECK_ANALYZER"
AZURE_CU_DEFAULT_CHECK_ANALYZER = "prebuilt-check.us"
AZURE_CU_TIMEOUT_SEC = int(os.environ.get("AZURE_CU_TIMEOUT_SEC", "180"))


def _cu_endpoint() -> str:
    return (os.environ.get(AZURE_CU_ENDPOINT_ENV) or "").strip().rstrip("/")


def _cu_key() -> str:
    return (os.environ.get(AZURE_CU_KEY_ENV) or "").strip()


def _check_analyzer_id() -> str:
    return (
        os.environ.get(AZURE_CU_CHECK_ANALYZER_ENV) or ""
    ).strip() or AZURE_CU_DEFAULT_CHECK_ANALYZER


def content_understanding_configured() -> bool:
    endpoint = _cu_endpoint()
    key = _cu_key()
    if not endpoint or not key:
        return False
    return "services.ai.azure.com" in endpoint.lower()


def content_understanding_status() -> dict[str, Any]:
    endpoint = _cu_endpoint()
    key = _cu_key()
    configured = bool(endpoint) and bool(key)
    valid_host = "services.ai.azure.com" in endpoint.lower() if endpoint else False
    di_alias = "cognitiveservices.azure.com" in endpoint.lower() if endpoint else False
    hint = ""
    if configured and di_alias:
        hint = (
            f"`{AZURE_CU_ENDPOINT_ENV}` points at Document Intelligence "
            "(cognitiveservices.azure.com). The app uses that as the dedicated check reader "
            f"via DI (`prebuilt-check.us`). For Foundry CU, use `*.services.ai.azure.com`, "
            "or set `AZURE_DI_CHECK_ENDPOINT` / `AZURE_DI_CHECK_KEY` explicitly."
        )
    elif not (configured and valid_host):
        hint = (
            f"Set `{AZURE_CU_ENDPOINT_ENV}` (Foundry project URL, "
            "`https://<resource>.services.ai.azure.com`) and `{AZURE_CU_KEY_ENV}` in `.env`. "
            "Create a Microsoft Foundry resource with Content Understanding enabled; "
            "configure default GPT-4.1 / embedding deployments for prebuilt analyzers."
        )
    return {
        "configured": configured and valid_host,
        "endpoint": endpoint,
        "has_key": bool(key),
        "analyzer": _check_analyzer_id(),
        "valid_endpoint_host": valid_host,
        "di_endpoint_alias": di_alias,
        "hint": hint,
    }


def _sdk_available() -> tuple[bool, str]:
    try:
        import azure.ai.contentunderstanding  # noqa: F401
    except ImportError:
        return (
            False,
            "Install `azure-ai-contentunderstanding` in this environment (see requirements.txt).",
        )
    return True, ""


def _confidence_label(score: float | None) -> str:
    if score is None:
        return "Medium"
    if score >= 0.9:
        return "High"
    if score >= 0.75:
        return "Medium"
    return "Low"


def _field_confidence(field: Any) -> float | None:
    if field is None:
        return None
    conf = getattr(field, "confidence", None)
    if conf is None and isinstance(field, dict):
        conf = field.get("confidence")
    return float(conf) if conf is not None else None


def _unwrap_cu_field(field: Any) -> Any:
    """Recursively unwrap Content Understanding ``ContentField`` objects."""
    if field is None:
        return None
    if isinstance(field, dict):
        if field.get("type") == "object" and "valueObject" in field:
            obj = field.get("valueObject") or {}
            return {k: _unwrap_cu_field(v) for k, v in obj.items()}
        if field.get("type") == "array" and "valueArray" in field:
            return [_unwrap_cu_field(item) for item in field.get("valueArray") or []]
        for key in (
            "valueString",
            "valueNumber",
            "valueInteger",
            "valueDate",
            "value",
        ):
            if key in field and field[key] is not None:
                val = field[key]
                if isinstance(val, dict):
                    return {k: _unwrap_cu_field(v) for k, v in val.items()}
                return val
        return field

    val = getattr(field, "value", None)
    if val is not None:
        if isinstance(val, dict):
            return {k: _unwrap_cu_field(v) for k, v in val.items()}
        return val

    value_object = getattr(field, "value_object", None)
    if value_object is not None:
        return {k: _unwrap_cu_field(v) for k, v in value_object.items()}

    value_array = getattr(field, "value_array", None)
    if value_array is not None:
        return [_unwrap_cu_field(item) for item in value_array]

    for attr in ("value_string", "value_number", "value_date", "value_integer"):
        if hasattr(field, attr):
            raw = getattr(field, attr)
            if raw is not None:
                return raw

    if hasattr(field, "as_dict"):
        return _unwrap_cu_field(field.as_dict())
    return field


def _check_from_fields(
    fields: dict[str, Any],
    *,
    page: int | None,
    analyzer_id: str,
) -> dict[str, Any] | None:
    pay_to = str(_unwrap_cu_field(fields.get("PayTo")) or "").strip()
    payer = str(_unwrap_cu_field(fields.get("PayerName")) or "").strip()
    amount_raw = _unwrap_cu_field(fields.get("NumberAmount"))
    try:
        amount = float(amount_raw) if amount_raw not in (None, "") else None
    except (TypeError, ValueError):
        amount = None

    micr = _unwrap_cu_field(fields.get("MICR")) or {}
    check_number = ""
    if isinstance(micr, dict):
        check_number = str(micr.get("CheckNumber") or "").strip()
        check_number = re.sub(r"[^\d]", "", check_number)

    conf_scores = [
        c
        for c in (
            _field_confidence(fields.get("PayTo")),
            _field_confidence(fields.get("MICR")),
            _field_confidence(fields.get("NumberAmount")),
        )
        if c is not None
    ]
    avg_conf = sum(conf_scores) / len(conf_scores) if conf_scores else None

    if not (check_number or pay_to or amount):
        return None

    out: dict[str, Any] = {
        "check_number": check_number,
        "pay_to": pay_to,
        "payer_name": payer,
        "amount": amount,
        "confidence": avg_conf,
        "confidence_label": _confidence_label(avg_conf),
        "source": "azure_content_understanding",
        "model": analyzer_id,
        "engine": "azure_content_understanding",
    }
    if page is not None:
        out["page"] = page
    return out


def _extract_checks_from_cu_result(
    result: Any, *, page: int | None, analyzer_id: str
) -> list[dict[str, Any]]:
    """Map ``AnalysisResult.contents[]`` to canonical check dicts (one per content block)."""
    contents = getattr(result, "contents", None) or []
    checks: list[dict[str, Any]] = []

    for content in contents:
        fields = getattr(content, "fields", None) or {}
        if not fields:
            continue
        content_page = page
        if content_page is None:
            start = getattr(content, "start_page_number", None)
            if start is not None:
                content_page = int(start)

        check = _check_from_fields(fields, page=content_page, analyzer_id=analyzer_id)
        if check:
            checks.append(check)

    return checks


def analyze_checks_on_pdf_page(
    pdf_bytes: bytes,
    page: int,
    *,
    logger=None,
    log_event=None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Content Understanding ``prebuilt-check.us`` on a single 1-based PDF page."""

    ok, err = _sdk_available()
    if not ok:
        raise RuntimeError(err)
    if not content_understanding_configured():
        raise RuntimeError(content_understanding_status()["hint"])

    from azure.ai.contentunderstanding import ContentUnderstandingClient
    from azure.ai.contentunderstanding.models import AnalysisInput
    from azure.core.credentials import AzureKeyCredential

    endpoint = _cu_endpoint()
    key = _cu_key()
    analyzer_id = _check_analyzer_id()

    client = ContentUnderstandingClient(endpoint, AzureKeyCredential(key))
    started = time.perf_counter()
    if log_event and logger:
        log_event(
            logger,
            "bank_stmt_azure_cu_check_request",
            analyzer=analyzer_id,
            page=page,
            pdf_bytes=len(pdf_bytes or b""),
        )

    poller = client.begin_analyze(
        analyzer_id=analyzer_id,
        inputs=[
            AnalysisInput(
                data=pdf_bytes,
                mime_type="application/pdf",
                name="statement.pdf",
                content_range=str(page),
            )
        ],
    )
    result = poller.result(timeout=AZURE_CU_TIMEOUT_SEC)
    duration_sec = round(time.perf_counter() - started, 2)

    checks = _extract_checks_from_cu_result(result, page=page, analyzer_id=analyzer_id)
    meta = {
        "model": analyzer_id,
        "pages_analyzed": str(page),
        "duration_sec": duration_sec,
        "check_count": len(checks),
        "warnings": [],
        "engine": "azure_content_understanding",
        "endpoint": endpoint,
    }
    if log_event and logger:
        log_event(
            logger,
            "bank_stmt_azure_cu_check_response",
            analyzer=analyzer_id,
            page=page,
            duration_sec=duration_sec,
            checks=len(checks),
        )
    return checks, meta


def analyze_checks_on_imaging_pages(
    pdf_bytes: bytes,
    *,
    logger=None,
    log_event=None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Call Content Understanding once per imaging page (env ``SLAM_IMAGING_*``)."""

    try:
        from hybrid_cv_check_leg import imaging_page_range

        first, last = imaging_page_range()
    except Exception:
        first, last = 5, 9
    if not isinstance(last, int):
        last = first
    first, last = int(first), int(last)
    all_checks: list[dict[str, Any]] = []
    total_duration = 0.0
    pages_called: list[str] = []
    warnings: list[str] = []

    for page in range(first, last + 1):
        try:
            page_checks, page_meta = analyze_checks_on_pdf_page(
                pdf_bytes,
                page,
                logger=logger,
                log_event=log_event,
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"page {page}: {exc}")
            continue
        all_checks.extend(page_checks)
        pages_called.append(str(page))
        total_duration += float(page_meta.get("duration_sec") or 0)

    meta = {
        "model": _check_analyzer_id(),
        "pages_analyzed": ",".join(pages_called),
        "duration_sec": round(total_duration, 2),
        "check_count": len(all_checks),
        "warnings": warnings,
        "engine": "azure_content_understanding",
        "per_page_calls": len(pages_called),
        "endpoint": _cu_endpoint(),
    }
    if log_event and logger:
        log_event(
            logger,
            "bank_stmt_azure_cu_check_imaging_done",
            pages=meta["pages_analyzed"],
            checks=len(all_checks),
            duration_sec=meta["duration_sec"],
        )
    return all_checks, meta
