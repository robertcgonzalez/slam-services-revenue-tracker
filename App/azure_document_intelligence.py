"""Azure Document Intelligence integration test — prebuilt bank statement model.

Calls Azure DI only on pages selected by :mod:`azure_di_utils` (cost control).
Maps results into the canonical 12-column GROK_CSV shape for Phase 1 UI.
"""

from __future__ import annotations

import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from azure_di_utils import (
    PageFilterDecision,
    estimate_azure_cost_usd,
    filter_pdf_for_azure,
    format_filter_user_message,
    summarize_page_filter,
)

AZURE_DI_ENDPOINT_ENV = "AZURE_DI_ENDPOINT"
AZURE_DI_KEY_ENV = "AZURE_DI_KEY"
AZURE_DI_MODEL_ENV = "AZURE_DI_MODEL"
AZURE_DI_DEFAULT_MODEL = "prebuilt-bankStatement.us"
AZURE_DI_CHECK_MODEL_ENV = "AZURE_DI_CHECK_MODEL"
AZURE_DI_CHECK_DEFAULT_MODEL = "prebuilt-check.us"
AZURE_DI_CHECK_ENDPOINT_ENV = "AZURE_DI_CHECK_ENDPOINT"
AZURE_DI_CHECK_KEY_ENV = "AZURE_DI_CHECK_KEY"
AZURE_DI_TIMEOUT_SEC = int(os.environ.get("AZURE_DI_TIMEOUT_SEC", "180"))


def azure_di_configured() -> bool:
    endpoint = (os.environ.get(AZURE_DI_ENDPOINT_ENV) or "").strip()
    key = (os.environ.get(AZURE_DI_KEY_ENV) or "").strip()
    return bool(endpoint) and bool(key)


def azure_di_status() -> dict[str, Any]:
    endpoint = (os.environ.get(AZURE_DI_ENDPOINT_ENV) or "").strip()
    key = (os.environ.get(AZURE_DI_KEY_ENV) or "").strip()
    model = (os.environ.get(AZURE_DI_MODEL_ENV) or "").strip() or AZURE_DI_DEFAULT_MODEL
    return {
        "configured": bool(endpoint) and bool(key),
        "endpoint": endpoint,
        "has_key": bool(key),
        "model": model,
        "hint": (
            f"Set `{AZURE_DI_ENDPOINT_ENV}` and `{AZURE_DI_KEY_ENV}` in `.env` "
            "(local) or App Settings (Azure) to enable the Azure DI test path."
        ),
    }


def _model_id() -> str:
    return (os.environ.get(AZURE_DI_MODEL_ENV) or "").strip() or AZURE_DI_DEFAULT_MODEL


def _check_model_id() -> str:
    return (os.environ.get(AZURE_DI_CHECK_MODEL_ENV) or "").strip() or AZURE_DI_CHECK_DEFAULT_MODEL


def _resolve_check_di_credentials() -> tuple[str, str]:
    """Dedicated check reader (e.g. ``slam-check-reader`` S0) or fall back to main DI."""

    check_ep = (os.environ.get(AZURE_DI_CHECK_ENDPOINT_ENV) or "").strip().rstrip("/")
    check_key = (os.environ.get(AZURE_DI_CHECK_KEY_ENV) or "").strip()
    if check_ep and check_key:
        return check_ep, check_key

    # Alias: CONTENTUNDERSTANDING_* sometimes holds a FormRecognizer check resource
    # (cognitiveservices.azure.com), not a Foundry CU project (*.services.ai.azure.com).
    cu_ep = (os.environ.get("CONTENTUNDERSTANDING_ENDPOINT") or "").strip().rstrip("/")
    cu_key = (os.environ.get("CONTENTUNDERSTANDING_KEY") or "").strip()
    if cu_ep and cu_key and "cognitiveservices.azure.com" in cu_ep.lower():
        return cu_ep, cu_key

    endpoint = (os.environ.get(AZURE_DI_ENDPOINT_ENV) or "").strip().rstrip("/")
    key = (os.environ.get(AZURE_DI_KEY_ENV) or "").strip()
    return endpoint, key


def azure_check_reader_configured() -> bool:
    ep, key = _resolve_check_di_credentials()
    return bool(ep) and bool(key)


def azure_check_reader_status() -> dict[str, Any]:
    ep, key = _resolve_check_di_credentials()
    main_ep = (os.environ.get(AZURE_DI_ENDPOINT_ENV) or "").strip().rstrip("/")
    dedicated = bool(ep and key and ep != main_ep)
    return {
        "configured": bool(ep) and bool(key),
        "endpoint": ep,
        "has_key": bool(key),
        "dedicated_resource": dedicated,
        "model": _check_model_id(),
    }


def _sdk_available() -> tuple[bool, str]:
    try:
        import azure.ai.documentintelligence  # noqa: F401
    except ImportError:
        return (
            False,
            "Install `azure-ai-documentintelligence` in this environment "
            "(see requirements.txt).",
        )
    return True, ""


def _unwrap_field_value(field: Any) -> Any:
    """Recursively unwrap Azure DocumentField / dict shapes."""
    if field is None:
        return None
    if isinstance(field, dict):
        if "valueArray" in field:
            return [_unwrap_field_value(item) for item in field.get("valueArray") or []]
        if "valueObject" in field:
            obj = field.get("valueObject") or {}
            return {k: _unwrap_field_value(v) for k, v in obj.items()}
        for key in (
            "valueString",
            "valueNumber",
            "valueInteger",
            "valueDate",
            "valueTime",
            "valueCurrency",
            "valueAddress",
            "valuePhoneNumber",
            "valueCountryRegion",
            "content",
        ):
            if key in field and field[key] is not None:
                val = field[key]
                if key == "valueCurrency" and isinstance(val, dict):
                    return val.get("amount")
                if key == "valueDate" and isinstance(val, str):
                    return val[:10] if len(val) >= 10 else val
                return val
        if "value" in field:
            return field["value"]
        return field

    for attr, _key in (
        ("value_array", "valueArray"),
        ("value_object", "valueObject"),
        ("value_string", "valueString"),
        ("value_number", "valueNumber"),
        ("value_date", "valueDate"),
        ("value_currency", "valueCurrency"),
        ("content", "content"),
    ):
        if hasattr(field, attr):
            raw = getattr(field, attr)
            if raw is not None:
                if attr == "value_array":
                    return [_unwrap_field_value(item) for item in raw]
                if attr == "value_object":
                    return {k: _unwrap_field_value(v) for k, v in raw.items()}
                if attr == "value_currency" and hasattr(raw, "amount"):
                    return raw.amount
                if attr == "value_date":
                    s = str(raw)
                    return s[:10] if len(s) >= 10 else s
                return raw
    return field


def _field_confidence(field: Any) -> float | None:
    if isinstance(field, dict):
        conf = field.get("confidence")
        return float(conf) if conf is not None else None
    conf = getattr(field, "confidence", None)
    return float(conf) if conf is not None else None


def _confidence_label(score: float | None) -> str:
    if score is None:
        return "Medium"
    if score >= 0.9:
        return "High"
    if score >= 0.75:
        return "Medium"
    return "Low"


def _format_date(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    if not text:
        return ""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00")[:19])
        return parsed.strftime("%Y-%m-%d")
    except ValueError:
        return text[:10] if len(text) >= 10 else text


def _format_amount(val: float | None) -> str:
    if val is None:
        return ""
    return f"{val:.2f}"


def _transaction_from_azure_row(
    row: dict[str, Any],
    *,
    default_year: int,
    field_confidences: dict[str, float | None],
) -> dict[str, str]:
    date_raw = row.get("Date")
    description = str(row.get("Description") or "").strip()
    check_num = str(row.get("CheckNumber") or row.get("Check#") or "").strip()
    deposit = row.get("DepositAmount")
    withdrawal = row.get("WithdrawalAmount")

    deposit_f = float(deposit) if deposit not in (None, "") else 0.0
    withdrawal_f = float(withdrawal) if withdrawal not in (None, "") else 0.0

    if deposit_f and not withdrawal_f:
        signed = deposit_f
    elif withdrawal_f and not deposit_f:
        signed = -abs(withdrawal_f)
    elif deposit_f and withdrawal_f:
        signed = deposit_f if deposit_f >= withdrawal_f else -abs(withdrawal_f)
    else:
        amount = row.get("Amount")
        try:
            signed = float(amount) if amount not in (None, "") else 0.0
        except (TypeError, ValueError):
            signed = 0.0

    date_str = _format_date(date_raw)
    year_month = date_str[:7] if len(date_str) >= 7 else f"{default_year}-01"

    scores = [v for v in field_confidences.values() if v is not None]
    avg_conf = sum(scores) / len(scores) if scores else None
    confidence = _confidence_label(avg_conf)
    needs_review = "Yes" if confidence == "Low" or not date_str or signed == 0.0 else "No"
    review_reason = ""
    if not date_str:
        review_reason = "Missing date from Azure"
    elif signed == 0.0:
        review_reason = "Missing or zero amount from Azure"

    payee = str(row.get("Payee") or "").strip()

    signed_str = _format_amount(signed) if signed else ""
    return {
        "Date": date_str,
        "Description": description,
        "Payee": payee,
        "Amount": signed_str,
        "Check#": check_num,
        "Category": "Uncategorized",
        "SubCategory": "",
        "SignedAmount": signed_str,
        "YearMonth": year_month,
        "Confidence": confidence,
        "NeedsReview": needs_review,
        "ReviewReason": review_reason,
    }


def _extract_transactions_from_analyze_result(result: Any) -> list[dict[str, str]]:
    """Walk Accounts[].Transactions[] from an AnalyzeResult."""
    if hasattr(result, "as_dict"):
        payload = result.as_dict()
    elif hasattr(result, "to_dict"):
        payload = result.to_dict()
    else:
        return []

    documents = payload.get("documents") or []
    default_year = datetime.now().year
    transactions: list[dict[str, str]] = []

    for doc in documents:
        fields = doc.get("fields") or {}
        accounts = _unwrap_field_value(fields.get("Accounts")) or []
        if not isinstance(accounts, list):
            continue

        for account in accounts:
            if not isinstance(account, dict):
                continue
            tx_rows = _unwrap_field_value(account.get("Transactions")) or []
            if not isinstance(tx_rows, list):
                continue
            for tx in tx_rows:
                if not isinstance(tx, dict):
                    continue
                conf_map = {k: _field_confidence(v) for k, v in tx.items()}
                flat = {k: _unwrap_field_value(v) for k, v in tx.items()}
                transactions.append(
                    _transaction_from_azure_row(
                        flat,
                        default_year=default_year,
                        field_confidences=conf_map,
                    )
                )

    return transactions


def _extract_checks_from_analyze_result(result: Any) -> list[dict[str, Any]]:
    """Walk documents from ``prebuilt-check.us`` (Content Understanding financial analyzer)."""

    if hasattr(result, "as_dict"):
        payload = result.as_dict()
    elif hasattr(result, "to_dict"):
        payload = result.to_dict()
    else:
        return []

    documents = payload.get("documents") or []
    checks: list[dict[str, Any]] = []

    for doc in documents:
        fields = doc.get("fields") or {}
        micr = _unwrap_field_value(fields.get("MICR")) or {}
        check_number = ""
        if isinstance(micr, dict):
            check_number = str(micr.get("CheckNumber") or "").strip()
            check_number = re.sub(r"[^\d]", "", check_number)

        pay_to = str(_unwrap_field_value(fields.get("PayTo")) or "").strip()
        payer = str(_unwrap_field_value(fields.get("PayerName")) or "").strip()
        amount_raw = _unwrap_field_value(fields.get("NumberAmount"))
        try:
            amount = float(amount_raw) if amount_raw not in (None, "") else None
        except (TypeError, ValueError):
            amount = None

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

        checks.append(
            {
                "check_number": check_number,
                "pay_to": pay_to,
                "payer_name": payer,
                "amount": amount,
                "confidence": avg_conf,
                "confidence_label": _confidence_label(avg_conf),
                "source": "azure_document_intelligence",
                "model": _check_model_id(),
            }
        )

    return [c for c in checks if c.get("check_number") or c.get("pay_to")]


def _imaging_page_range_1based() -> tuple[int, int]:
    try:
        from hybrid_cv_check_leg import imaging_page_range

        first, last = imaging_page_range()
    except Exception:
        first, last = 5, 9
    if not isinstance(last, int):
        last = first
    return int(first), int(last)


def _imaging_page_indices_0based() -> set[int]:
    """0-based PDF page indices for check-image pages (excluded from bank-statement model)."""

    first, last = _imaging_page_range_1based()
    return set(range(first - 1, last))


def register_pages_string_for_bank_statement(pdf_bytes: bytes) -> tuple[str, dict[str, Any], list]:
    """Prefilter pages but exclude check-image pages from the bank-statement model pass."""

    from azure_di_utils import (
        get_pages_to_analyze,
        pages_list_to_azure_string,
    )

    imaging_idx = _imaging_page_indices_0based()
    kept, decisions = get_pages_to_analyze(pdf_bytes)
    register_idx = [p for p in kept if p not in imaging_idx]
    pages_str = pages_list_to_azure_string(register_idx)
    imaging_str = pages_list_to_azure_string(sorted(imaging_idx)) if imaging_idx else ""

    summary = {
        "original_pages": len(decisions),
        "kept_count": len(register_idx),
        "skipped_count": len(decisions) - len(register_idx),
        "imaging_pages_excluded": imaging_str,
        "user_message": (
            f"Register/tabular pages for bank-statement model: {pages_str or 'none'} "
            f"(check-image pages {imaging_str or '—'} use prebuilt-check.us instead)."
        ),
    }
    return pages_str, summary, decisions


def analyze_checks_on_pdf_pages(
    pdf_bytes: bytes,
    pages: str,
    *,
    logger=None,
    log_event=None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Azure DI / Content Understanding ``prebuilt-check.us`` on one or more PDF pages."""

    ok, err = _sdk_available()
    if not ok:
        raise RuntimeError(err)
    if not azure_check_reader_configured():
        raise RuntimeError(azure_di_status()["hint"])

    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential

    endpoint, key = _resolve_check_di_credentials()
    model_id = _check_model_id()

    client = DocumentIntelligenceClient(endpoint, AzureKeyCredential(key))
    started = time.perf_counter()
    if log_event and logger:
        log_event(
            logger,
            "bank_stmt_azure_check_request",
            model=model_id,
            pages=pages,
            pdf_bytes=len(pdf_bytes or b""),
        )

    poller = client.begin_analyze_document(
        model_id=model_id,
        body=pdf_bytes,
        content_type="application/pdf",
        pages=pages or None,
    )
    result = poller.result(timeout=AZURE_DI_TIMEOUT_SEC)
    duration_sec = round(time.perf_counter() - started, 2)

    checks = _extract_checks_from_analyze_result(result)
    warnings: list[str] = []
    if hasattr(result, "warnings") and result.warnings:
        for w in result.warnings:
            code = getattr(w, "code", None) or (w.get("code") if isinstance(w, dict) else "")
            msg = getattr(w, "message", None) or (w.get("message") if isinstance(w, dict) else str(w))
            warnings.append(f"{code}: {msg}".strip(": "))

    check_status = azure_check_reader_status()
    meta = {
        "model": model_id,
        "pages_analyzed": pages,
        "duration_sec": duration_sec,
        "check_count": len(checks),
        "warnings": warnings,
        "engine": "azure_document_intelligence",
        "check_endpoint": endpoint,
        "dedicated_check_resource": check_status.get("dedicated_resource"),
    }
    if log_event and logger:
        log_event(
            logger,
            "bank_stmt_azure_check_response",
            model=model_id,
            pages=pages,
            duration_sec=duration_sec,
            checks=len(checks),
            warnings=len(warnings),
        )
    return checks, meta


def analyze_check_image_bytes(
    image_bytes: bytes,
    *,
    content_type: str = "image/png",
    logger=None,
    log_event=None,
    source_name: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Azure DI ``prebuilt-check.us`` on a single cropped check image."""

    ok, err = _sdk_available()
    if not ok:
        raise RuntimeError(err)
    if not azure_check_reader_configured():
        raise RuntimeError(azure_di_status()["hint"])

    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential

    endpoint, key = _resolve_check_di_credentials()
    model_id = _check_model_id()
    client = DocumentIntelligenceClient(endpoint, AzureKeyCredential(key))
    started = time.perf_counter()

    poller = client.begin_analyze_document(
        model_id=model_id,
        body=image_bytes,
        content_type=content_type,
    )
    result = poller.result(timeout=AZURE_DI_TIMEOUT_SEC)
    duration_sec = round(time.perf_counter() - started, 2)
    checks = _extract_checks_from_analyze_result(result)
    if source_name:
        for check in checks:
            check["crop_file"] = source_name
    return checks, {"duration_sec": duration_sec, "model": model_id}


def _dedupe_check_dicts(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for check in checks:
        num = str(check.get("check_number") or "").strip()
        payee = str(check.get("pay_to") or "").strip().lower()
        amount = check.get("amount")
        amt_key = f"{float(amount):.2f}" if amount not in (None, "") else ""
        key = (num, payee, amt_key)
        if key in seen and any(key):
            continue
        seen.add(key)
        out.append(check)
    return out


def analyze_checks_from_crop_directory(
    crop_dir: Path | str,
    *,
    logger=None,
    log_event=None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run ``prebuilt-check.us`` on each PNG in the geometry cropper output folder."""

    folder = Path(crop_dir)
    if not folder.is_dir():
        return [], {"check_count": 0, "warnings": ["crop directory missing"]}

    png_files = sorted(folder.glob("*.png"))
    if not png_files:
        return [], {"check_count": 0, "warnings": ["no crop PNG files"]}

    all_checks: list[dict[str, Any]] = []
    total_duration = 0.0
    warnings: list[str] = []
    failed = 0

    if log_event and logger:
        log_event(logger, "bank_stmt_azure_check_crops_start", files=len(png_files))

    for png_path in png_files:
        try:
            image_bytes = png_path.read_bytes()
            crop_checks, crop_meta = analyze_check_image_bytes(
                image_bytes,
                content_type="image/png",
                logger=logger,
                log_event=log_event,
                source_name=png_path.name,
            )
            all_checks.extend(crop_checks)
            total_duration += float(crop_meta.get("duration_sec") or 0)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            warnings.append(f"{png_path.name}: {exc}")

    all_checks = _dedupe_check_dicts(all_checks)
    check_status = azure_check_reader_status()
    meta = {
        "model": _check_model_id(),
        "pages_analyzed": f"{len(png_files)} crop(s)",
        "duration_sec": round(total_duration, 2),
        "check_count": len(all_checks),
        "warnings": warnings,
        "engine": "azure_document_intelligence",
        "check_endpoint": check_status.get("endpoint"),
        "dedicated_check_resource": check_status.get("dedicated_resource"),
        "crop_files_analyzed": len(png_files),
        "crop_files_failed": failed,
        "source": "cropped_pngs",
    }
    if log_event and logger:
        log_event(
            logger,
            "bank_stmt_azure_check_crops_done",
            files=len(png_files),
            checks=len(all_checks),
            failed=failed,
        )
    return all_checks, meta


def analyze_checks_on_imaging_pages(
    pdf_bytes: bytes,
    *,
    logger=None,
    log_event=None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Call ``prebuilt-check.us`` once per imaging page (multiple checks per page)."""

    first, last = _imaging_page_range_1based()
    all_checks: list[dict[str, Any]] = []
    total_duration = 0.0
    warnings: list[str] = []
    pages_called: list[str] = []

    for page in range(first, last + 1):
        page_checks, page_meta = analyze_checks_on_pdf_pages(
            pdf_bytes,
            str(page),
            logger=logger,
            log_event=log_event,
        )
        for check in page_checks:
            check["page"] = page
        all_checks.extend(page_checks)
        pages_called.append(str(page))
        total_duration += float(page_meta.get("duration_sec") or 0)
        warnings.extend(page_meta.get("warnings") or [])

    meta = {
        "model": _check_model_id(),
        "pages_analyzed": ",".join(pages_called),
        "duration_sec": round(total_duration, 2),
        "check_count": len(all_checks),
        "warnings": warnings,
        "engine": "azure_document_intelligence",
        "per_page_calls": len(pages_called),
    }
    if log_event and logger:
        log_event(
            logger,
            "bank_stmt_azure_check_imaging_done",
            pages=meta["pages_analyzed"],
            checks=len(all_checks),
            duration_sec=meta["duration_sec"],
        )
    return all_checks, meta


def checks_to_transaction_rows(checks: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Build canonical transaction rows from Azure check fields (withdrawals)."""

    default_year = datetime.now().year
    rows: list[dict[str, str]] = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        amount = check.get("amount")
        try:
            signed = -abs(float(amount)) if amount not in (None, "") else 0.0
        except (TypeError, ValueError):
            signed = 0.0
        if signed == 0.0:
            continue
        payee = str(check.get("pay_to") or "").strip()
        check_num = str(check.get("check_number") or "").strip()
        desc_parts = ["CHECK"]
        if check_num:
            desc_parts.append(check_num)
        if payee:
            desc_parts.append(payee)
        description = " ".join(desc_parts)
        conf_label = str(check.get("confidence_label") or "Medium")
        rows.append(
            {
                "Date": "",
                "Description": description,
                "Payee": payee,
                "Amount": f"{abs(signed):.2f}",
                "Check#": check_num,
                "Category": "Uncategorized",
                "SubCategory": "",
                "SignedAmount": f"{signed:.2f}",
                "YearMonth": f"{default_year}-01",
                "Confidence": conf_label,
                "NeedsReview": "Yes" if conf_label != "High" else "No",
                "ReviewReason": "From Azure prebuilt-check.us (imaging page)",
            }
        )
    return rows


def imaging_pages_string() -> str:
    """1-based page span for check imaging (env ``SLAM_IMAGING_*``)."""

    first, last = _imaging_page_range_1based()
    return f"{first}-{last}"


def analyze_bank_statement_pdf(
    pdf_bytes: bytes,
    pages: str,
    *,
    logger=None,
    log_event=None,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """
    Call Azure Document Intelligence prebuilt bank statement model.

    Returns ``(transactions, meta)`` where meta includes duration, model, pages, warnings.
    """
    ok, err = _sdk_available()
    if not ok:
        raise RuntimeError(err)
    if not azure_di_configured():
        raise RuntimeError(azure_di_status()["hint"])

    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential

    endpoint = (os.environ.get(AZURE_DI_ENDPOINT_ENV) or "").strip()
    key = (os.environ.get(AZURE_DI_KEY_ENV) or "").strip()
    model_id = _model_id()

    client = DocumentIntelligenceClient(endpoint, AzureKeyCredential(key))
    started = time.perf_counter()
    if log_event and logger:
        log_event(
            logger,
            "bank_stmt_azure_di_request",
            model=model_id,
            pages=pages,
            pdf_bytes=len(pdf_bytes or b""),
        )

    poller = client.begin_analyze_document(
        model_id=model_id,
        body=pdf_bytes,
        content_type="application/pdf",
        pages=pages or None,
    )
    result = poller.result(timeout=AZURE_DI_TIMEOUT_SEC)
    duration_sec = round(time.perf_counter() - started, 2)

    transactions = _extract_transactions_from_analyze_result(result)
    warnings: list[str] = []
    if hasattr(result, "warnings") and result.warnings:
        for w in result.warnings:
            code = getattr(w, "code", None) or (w.get("code") if isinstance(w, dict) else "")
            msg = getattr(w, "message", None) or (w.get("message") if isinstance(w, dict) else str(w))
            warnings.append(f"{code}: {msg}".strip(": "))

    meta = {
        "model": model_id,
        "pages_analyzed": pages,
        "duration_sec": duration_sec,
        "transaction_count": len(transactions),
        "warnings": warnings,
    }
    if log_event and logger:
        log_event(
            logger,
            "bank_stmt_azure_di_response",
            model=model_id,
            pages=pages,
            duration_sec=duration_sec,
            rows=len(transactions),
            warnings=len(warnings),
        )
    return transactions, meta


def run_azure_di_prefilter(
    pdf_bytes: bytes,
    *,
    logger=None,
    log_event=None,
) -> tuple[bytes | None, str, dict[str, Any], list[PageFilterDecision]]:
    """
    Local pre-filter only. Returns pdf bytes (unchanged), pages= string, summary dict, decisions.
    """
    _pdf, pages_str, decisions = filter_pdf_for_azure(pdf_bytes)
    summary = summarize_page_filter(decisions, pages_str)
    summary["user_message"] = format_filter_user_message(summary)
    summary["est_cost_usd"] = estimate_azure_cost_usd(pages_str)

    if log_event and logger:
        log_event(
            logger,
            "bank_stmt_azure_di_prefilter",
            original_pages=summary["original_pages"],
            kept=summary["kept_count"],
            skipped=summary["skipped_count"],
            pages_sent=pages_str,
        )
        for d in decisions:
            if not d.kept:
                log_event(
                    logger,
                    "bank_stmt_azure_di_page_skipped",
                    page=d.page_number + 1,
                    reason=d.reason,
                )

    return _pdf, pages_str, summary, decisions
