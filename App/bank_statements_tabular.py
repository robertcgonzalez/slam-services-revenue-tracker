"""Phase 1 Bank Statements — upload PDFs and extract tabular transactions only."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pandas as pd
import streamlit as st
from app_logging import log_event
from bank_statements import (
    GROK_CSV_COLUMNS,
    ZERO_TRANSACTIONS_MSG,
    expected_csv_path,
    run_statement_pipeline,
    scripts_available,
    transaction_summary_metrics,
)

FAST_PATH_MIN_ROWS = 3

ParseStatus = Literal["success", "partial", "error"]


@dataclass
class StatementParseResult:
    """Outcome of parsing one uploaded PDF."""

    filename: str
    status: ParseStatus
    message: str
    df: pd.DataFrame | None
    csv_path: Path | None
    used_easyocr: bool
    used_azure_di: bool = False
    azure_pages_sent: str = ""
    azure_duration_sec: float | None = None
    azure_filter_message: str = ""
    azure_warnings: list[str] | None = None


def _transactions_to_dataframe(transactions: list[dict[str, Any]]) -> pd.DataFrame:
    if not transactions:
        return pd.DataFrame(columns=list(GROK_CSV_COLUMNS))
    df = pd.DataFrame(transactions)
    for col in GROK_CSV_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    extras = [c for c in df.columns if c not in GROK_CSV_COLUMNS]
    return df[list(GROK_CSV_COLUMNS) + extras].reset_index(drop=True)


def _write_csv(df: pd.DataFrame, csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)


def parse_statement_pdf(
    pdf_bytes: bytes,
    filename: str,
    logger,
) -> StatementParseResult:
    """Run the proven parser subprocess, then full-page EasyOCR if rows are sparse."""
    ok, err = scripts_available()
    if not ok:
        return StatementParseResult(
            filename=filename,
            status="error",
            message=err,
            df=None,
            csv_path=None,
            used_easyocr=False,
        )

    df, _logs, csv_path, meta = run_statement_pipeline(
        pdf_bytes,
        filename,
        logger,
        run_cropper=False,
    )
    row_count = len(df) if df is not None and not df.empty else 0
    used_easyocr = False

    if row_count < FAST_PATH_MIN_ROWS:
        try:
            import local_enhanced_ocr

            ocr_result = local_enhanced_ocr.run_tabular_extraction_only(pdf_bytes)
            ocr_df = _transactions_to_dataframe(ocr_result.get("transactions") or [])
            ocr_count = len(ocr_df)
            if ocr_count > row_count:
                df = ocr_df
                row_count = ocr_count
                used_easyocr = bool(ocr_result.get("fallback_rows"))
                pdf_path = meta.get("pdf_path")
                if isinstance(pdf_path, Path) and row_count > 0:
                    out_csv = expected_csv_path(pdf_path)
                    _write_csv(df, out_csv)
                    csv_path = out_csv
                status = str(ocr_result.get("status") or "partial")
                if row_count == 0:
                    return StatementParseResult(
                        filename=filename,
                        status="error",
                        message=str(ocr_result.get("message") or ZERO_TRANSACTIONS_MSG),
                        df=df if row_count else None,
                        csv_path=csv_path,
                        used_easyocr=used_easyocr,
                    )
                return StatementParseResult(
                    filename=filename,
                    status=status if status in ("success", "partial", "error") else "partial",
                    message=str(ocr_result.get("message") or f"Extracted {row_count} transaction(s)."),
                    df=df,
                    csv_path=csv_path,
                    used_easyocr=used_easyocr,
                )
        except Exception as exc:
            if row_count == 0:
                detail = str(exc)
                if "pdf2image" in detail or "easyocr" in detail.lower():
                    hint = " Install pdfplumber, pdf2image, easyocr, and pillow for scanned PDFs."
                else:
                    hint = ""
                return StatementParseResult(
                    filename=filename,
                    status="error",
                    message=f"{ZERO_TRANSACTIONS_MSG}{hint}",
                    df=None,
                    csv_path=csv_path,
                    used_easyocr=False,
                )

    if df is None or row_count == 0:
        return StatementParseResult(
            filename=filename,
            status="error",
            message=ZERO_TRANSACTIONS_MSG,
            df=df,
            csv_path=csv_path,
            used_easyocr=False,
        )

    pipe_status = str(meta.get("status") or "success")
    status: ParseStatus = (
        pipe_status if pipe_status in ("success", "partial", "error") else "success"
    )
    via = " (EasyOCR fallback)" if used_easyocr else ""
    return StatementParseResult(
        filename=filename,
        status=status,
        message=f"Extracted {row_count} transaction(s){via}.",
        df=df,
        csv_path=csv_path,
        used_easyocr=used_easyocr,
    )


def parse_statement_pdf_azure_di(
    pdf_bytes: bytes,
    filename: str,
    logger,
) -> StatementParseResult:
    """Azure Document Intelligence test path with local page pre-filter."""
    from azure_document_intelligence import (
        analyze_bank_statement_pdf,
        azure_di_configured,
        azure_di_status,
        run_azure_di_prefilter,
    )

    if not azure_di_configured():
        return StatementParseResult(
            filename=filename,
            status="error",
            message=azure_di_status()["hint"],
            df=None,
            csv_path=None,
            used_easyocr=False,
            used_azure_di=True,
        )

    try:
        _pdf, pages_str, summary, _decisions = run_azure_di_prefilter(
            pdf_bytes,
            logger=logger,
            log_event=log_event,
        )
        filter_msg = str(summary.get("user_message") or "")
        if not pages_str:
            return StatementParseResult(
                filename=filename,
                status="error",
                message=(
                    f"{filter_msg} — no pages qualified for Azure after pre-filter. "
                    "Try the local Parse Statement(s) path."
                ),
                df=None,
                csv_path=None,
                used_easyocr=False,
                used_azure_di=True,
                azure_filter_message=filter_msg,
            )

        with st.spinner("Analyzing with Azure Document Intelligence…"):
            transactions, meta = analyze_bank_statement_pdf(
                pdf_bytes,
                pages_str,
                logger=logger,
                log_event=log_event,
            )

        df = _transactions_to_dataframe(transactions)
        row_count = len(df)
        duration = meta.get("duration_sec")
        est = summary.get("est_cost_usd")
        cost_note = f" · est. cost ~${est:.2f}" if est is not None else ""
        pages_note = pages_str
        base_msg = (
            f"Azure DI: {row_count} transaction(s) in {duration}s "
            f"(pages: {pages_note}){cost_note}."
        )
        warnings = list(meta.get("warnings") or [])
        if warnings:
            base_msg += f" Warnings: {'; '.join(warnings[:3])}"

        if row_count == 0:
            return StatementParseResult(
                filename=filename,
                status="error",
                message=f"{filter_msg} {base_msg} {ZERO_TRANSACTIONS_MSG}",
                df=df,
                csv_path=None,
                used_easyocr=False,
                used_azure_di=True,
                azure_pages_sent=pages_str,
                azure_duration_sec=duration,
                azure_filter_message=filter_msg,
                azure_warnings=warnings or None,
            )

        status: ParseStatus = "success" if row_count >= FAST_PATH_MIN_ROWS else "partial"
        return StatementParseResult(
            filename=filename,
            status=status,
            message=f"{filter_msg} {base_msg}",
            df=df,
            csv_path=None,
            used_easyocr=False,
            used_azure_di=True,
            azure_pages_sent=pages_str,
            azure_duration_sec=duration,
            azure_filter_message=filter_msg,
            azure_warnings=warnings or None,
        )
    except Exception as exc:
        log_event(logger, "bank_stmt_azure_di_failed", file=filename, error=str(exc)[:300])
        return StatementParseResult(
            filename=filename,
            status="error",
            message=f"Azure Document Intelligence failed: {exc}",
            df=None,
            csv_path=None,
            used_easyocr=False,
            used_azure_di=True,
        )


def _status_emoji(status: ParseStatus) -> str:
    if status == "success":
        return "✅"
    if status == "partial":
        return "⚠️"
    return "❌"


def render_bank_statements_phase1_page(
    clients_df: pd.DataFrame,
    req_df: pd.DataFrame,
    logger,
    *,
    bulk_select_label,
    save_requests,
) -> None:
    """Phase 1 UI: client + PDF upload → tabular parse → table → CSV → mark received."""
    st.header("🏦 Bank Statements")
    st.markdown(
        '<p class="slam-phase-badge" style="background:#e0f2fe;color:#0369a1;'
        'padding:0.35rem 0.75rem;border-radius:6px;display:inline-block;'
        'font-weight:600;margin-bottom:0.5rem;">Phase 1: Tabular Extraction</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="slam-subtle">Upload bank statement PDFs for a client. '
        "We extract transactions with the proven parser (pdfplumber, with full-page "
        "EasyOCR only when needed). Review the table, download CSV, and mark the "
        "revenue request received.</p>",
        unsafe_allow_html=True,
    )

    scripts_ok, scripts_err = scripts_available()
    if not scripts_ok:
        st.error(scripts_err)
        st.info("Deploy must include the `Scripts/` folder (see Build-AzureDeployZip.ps1).")
        return

    client_names = sorted(clients_df["Business Name"].dropna().unique().tolist())
    if not client_names:
        st.warning("No clients loaded — cannot associate a statement.")
        return

    default_client = st.session_state.get("bank_stmt_p1_client")
    if default_client not in client_names:
        default_client = client_names[0]

    col_client, col_metric = st.columns([2, 1])
    with col_client:
        selected_client = st.selectbox(
            "Client",
            client_names,
            index=client_names.index(default_client),
            key="bank_stmt_p1_client_select",
        )
    st.session_state["bank_stmt_p1_client"] = selected_client

    open_requests = req_df[
        (req_df["business_name"] == selected_client)
        & (req_df["status"].isin(["Pending", "Received"]))
        & (~req_df["bank_statement_received"].fillna(False))
    ]
    with col_metric:
        st.metric("Open requests (bank stmt missing)", len(open_requests))

    uploaded = st.file_uploader(
        "Bank statement PDF(s)",
        type=["pdf"],
        accept_multiple_files=True,
        key="bank_stmt_p1_pdf_upload",
    )

    # Azure DI Test Path notice + status (always visible)
    try:
        from azure_document_intelligence import azure_di_status
        di_status = azure_di_status()
    except ImportError:
        di_status = {
            "configured": False,
            "hint": "Install `azure-ai-documentintelligence` (see requirements.txt).",
        }

    st.markdown(
        '<p class="slam-subtle" style="margin-top:0.25rem;">'
        '<span style="background:#fef3c7;color:#92400e;padding:0.2rem 0.5rem;'
        'border-radius:4px;font-weight:600;font-size:0.85rem;">Azure DI Test Path</span> '
        "Pre-filters blank and reconciliation pages locally, then calls Azure only on "
        "useful pages (cost control).</p>",
        unsafe_allow_html=True,
    )
    if di_status.get("configured"):
        st.caption(
            f"Azure DI configured · model `{di_status.get('model', 'prebuilt-bankStatement.us')}`"
        )
    else:
        st.caption(di_status.get("hint", "Azure DI not configured."))

    # Radio button for choosing parser (user request)
    parse_mode = st.radio(
        "Parse using",
        options=[
            "Local (pdfplumber + EasyOCR fallback)",
            "Azure Document Intelligence (Test)",
        ],
        horizontal=True,
        key="bank_stmt_p1_parse_mode",
        help="Local = current production path (pdfplumber + EasyOCR when needed). Azure DI = experimental test path with smart page pre-filtering for cost control.",
    )

    run_parse = st.button("Parse Statement(s)", type="primary", key="bank_stmt_p1_parse")

    if run_parse:
        if not uploaded:
            st.warning("Upload at least one PDF before parsing.")
        else:
            results: list[StatementParseResult] = []
            use_azure = parse_mode == "Azure Document Intelligence (Test)"

            for up in uploaded:
                pdf_bytes = up.getvalue()
                if use_azure:
                    log_event(
                        logger,
                        "bank_stmt_p1_azure_di_start",
                        client=selected_client,
                        file=up.name,
                    )
                    result = parse_statement_pdf_azure_di(pdf_bytes, up.name, logger)
                    log_event(
                        logger,
                        "bank_stmt_p1_azure_di_done",
                        client=selected_client,
                        file=up.name,
                        status=result.status,
                        rows=len(result.df) if result.df is not None else 0,
                        pages=result.azure_pages_sent,
                        duration_sec=result.azure_duration_sec,
                    )
                else:
                    log_event(
                        logger,
                        "bank_stmt_p1_parse_start",
                        client=selected_client,
                        file=up.name,
                    )
                    result = parse_statement_pdf(pdf_bytes, up.name, logger)
                    log_event(
                        logger,
                        "bank_stmt_p1_parse_done",
                        client=selected_client,
                        file=up.name,
                        status=result.status,
                        rows=len(result.df) if result.df is not None else 0,
                        easyocr=result.used_easyocr,
                    )
                results.append(result)
            st.session_state["bank_stmt_p1_results"] = results
            st.session_state["bank_stmt_p1_client"] = selected_client
            st.rerun()

    results: list[StatementParseResult] = st.session_state.get("bank_stmt_p1_results") or []
    if results and st.session_state.get("bank_stmt_p1_client") == selected_client:
        st.subheader("Parse results")
        for res in results:
            line = f"{_status_emoji(res.status)} **{res.filename}** — {res.message}"
            if res.used_azure_di:
                pages = res.azure_pages_sent or "?"
                dur = (
                    f"{res.azure_duration_sec:.1f}s"
                    if res.azure_duration_sec is not None
                    else "?"
                )
                line += (
                    f"\n\n🧪 **Azure DI test** · pages `{pages}` · {dur}"
                )
                if res.azure_filter_message:
                    st.info(res.azure_filter_message)
            st.markdown(line)
            if res.azure_warnings:
                for w in res.azure_warnings[:5]:
                    st.warning(w)

        st.divider()
        for res in results:
            if res.df is None or res.df.empty:
                continue
            azure_tag = " · Azure DI" if res.used_azure_di else ""
            metrics = transaction_summary_metrics(res.df)
            with st.expander(
                f"📄 {res.filename} — {metrics['count']} transactions{azure_tag}",
                expanded=len(results) == 1,
            ):
                m1, m2, m3 = st.columns(3)
                m1.metric("Transactions", metrics["count"])
                m2.metric("Deposits", f"${metrics['deposits']:,.2f}")
                m3.metric("Withdrawals", f"${metrics['withdrawals']:,.2f}")

                display_cols = [
                    c
                    for c in [
                        "Date",
                        "Description",
                        "Payee",
                        "Amount",
                        "Check#",
                        "Category",
                        "SignedAmount",
                        "Confidence",
                        "NeedsReview",
                        "ReviewReason",
                        "Source",
                    ]
                    if c in res.df.columns
                ]
                view_df = res.df[display_cols] if display_cols else res.df
                st.data_editor(
                    view_df,
                    num_rows="fixed",
                    width="stretch",
                    hide_index=True,
                    key=f"bank_stmt_p1_editor_{res.filename}",
                )

                buf = io.StringIO()
                res.df.to_csv(buf, index=False)
                stem = Path(res.filename).stem.replace(" ", "_")
                st.download_button(
                    f"Download CSV — {res.filename}",
                    buf.getvalue(),
                    file_name=f"{selected_client.replace(' ', '_')}_{stem}_transactions.csv",
                    mime="text/csv",
                    key=f"bank_stmt_p1_csv_{res.filename}",
                )
                if res.csv_path:
                    st.caption(f"Parser output: `{res.csv_path}`")

    st.divider()
    st.subheader("Link to revenue request")

    if open_requests.empty:
        st.info(
            f"No Pending/Received requests for **{selected_client}** with bank statement still missing. "
            "You can still parse PDFs above; use Revenue Requests for other clients."
        )
    else:
        options = [
            bulk_select_label(row["request_id"], row["business_name"])
            for _, row in open_requests.iterrows()
        ]
        id_map = {
            bulk_select_label(row["request_id"], row["business_name"]): row["request_id"]
            for _, row in open_requests.iterrows()
        }
        choice = st.selectbox(
            "Revenue request to update",
            options,
            key="bank_stmt_p1_request_pick",
        )
        request_id = id_map[choice]

        has_parsed = any(
            r.df is not None and not r.df.empty
            for r in results
            if st.session_state.get("bank_stmt_p1_client") == selected_client
        )
        if not has_parsed:
            st.caption("Parse at least one statement with transactions before marking received.")

        if st.button(
            "Mark as Received",
            type="primary",
            key="bank_stmt_p1_mark_received",
            disabled=not has_parsed,
        ):
            try:
                master = req_df.set_index("request_id")
                if request_id not in master.index:
                    st.error("Request not found. Reload the page and try again.")
                else:
                    master.at[request_id, "bank_statement_received"] = True
                    updated = master.reset_index()
                    warnings = save_requests(updated)
                    st.session_state["last_save_message"] = (
                        f"Bank statement marked received for {selected_client} ({request_id})."
                    )
                    log_event(
                        logger,
                        "bank_stmt_p1_mark_received",
                        request_id=request_id,
                        client=selected_client,
                    )
                    st.cache_data.clear()
                    if warnings:
                        st.warning("; ".join(warnings[:5]))
                    st.success(st.session_state["last_save_message"])
                    st.rerun()
            except Exception as exc:
                st.error(f"Could not save — no changes written. {exc}")
                log_event(logger, "bank_stmt_p1_mark_failed", error=str(exc)[:200])
