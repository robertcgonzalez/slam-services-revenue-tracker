import io
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from app_logging import log_event, setup_app_logging

try:
    from bank_statements import (
        GROK_CSV_FIELDS,
        GROK_VISION_HINT,
        PIVOT_GROUP_BY_OPTIONS,
        PIVOT_VALUE_KIND_OPTIONS,
        ZERO_TRANSACTIONS_MSG,
        apply_payee_rules,
        azure_ocr_status,
        build_grok_vision_prompt,
        build_statement_pivot,
        count_pattern_matches,
        emit_gate_a3_smoke_evidence,
        filter_transactions_by_confidence,
        format_processing_log,
        hybrid_cv_status,
        load_grok_vision_csv,
        load_payee_rules,
        missing_document_counts,
        reconcile_statement_totals,
        reconciliation_reference_totals,
        resolve_payee_rules_path,
        rules_library_summary,
        run_azure_ocr_pipeline,
        scripts_available,
        style_low_confidence_rows,
        suggest_payee_pattern,
        transaction_summary_metrics,
        upsert_payee_rule,
    )
except ImportError:

    def filter_transactions_by_confidence(df, confidence_level="High"):
        if confidence_level in ("High", "Show All", ""):
            return df
        if "Confidence" not in df.columns:
            return df.iloc[0:0].copy()
        conf = df["Confidence"].astype(str).str.strip()
        return df[(conf != "High") & (conf != "")].copy()

    def format_processing_log(logs):
        return "\n".join(logs)

    def hybrid_cv_status():
        return {
            "enabled": False,
            "di_configured": False,
            "azure_cv_configured": False,
            "ready": False,
            "imaging_first_page": 5,
            "imaging_last_page": None,
        }

    def style_low_confidence_rows(df):
        return df.style

    def build_grok_vision_prompt(client_name, pdf_filename, **_kwargs):
        return (
            f"Please extract every transaction from the attached bank statement PDF for "
            f"client '{client_name}' (file: {pdf_filename}). Return a CSV with columns: "
            "Date,Description,Payee,Amount,Check#,Category,SubCategory,SignedAmount,YearMonth,"
            "Confidence,NeedsReview,ReviewReason. Skip the Daily Balance Summary section."
        )

    ZERO_TRANSACTIONS_MSG = (
        "No transactions were extracted from this PDF. The file may be a scanned image "
        "or an unsupported layout."
    )
    GROK_VISION_HINT = "Try the Grok Vision skill with Export Raw Text or the PDF pages."
    GROK_CSV_FIELDS = (
        "Date,Description,Payee,Amount,Check#,Category,SubCategory,SignedAmount,YearMonth,"
        "Confidence,NeedsReview,ReviewReason"
    )

    def load_grok_vision_csv(_source):
        raise RuntimeError(
            "Paste Grok CSV is unavailable in this deploy — bank_statements module is out of sync."
        )

    def reconcile_statement_totals(_df, _grok_totals=None):
        return {
            "status": "no_reference",
            "message": (
                "Reconciliation unavailable in this deploy — bank_statements module is out of sync."
            ),
            "differences": {},
            "needs_review": False,
            "computed": {},
            "reported": None,
        }

    def apply_payee_rules(df, _client_name=None, _rules=None, **_kwargs):
        return df, {"rows_changed": 0, "rules_used": 0, "rules_total": 0, "source_path": None}

    def load_payee_rules(_path=None):
        import pandas as _pd

        return _pd.DataFrame(
            columns=[
                "pattern",
                "clean_payee",
                "suggested_category",
                "client_override",
                "notes",
                "last_used",
            ]
        )

    def resolve_payee_rules_path(_create_if_missing=False):
        return None

    def upsert_payee_rule(*_args, **_kwargs):
        return False, None

    def suggest_payee_pattern(description, **_kwargs):
        text = str(description or "").strip()
        return text.split()[0] if text else ""

    def count_pattern_matches(_df, _pattern, **_kwargs):
        return 0

    def rules_library_summary(_rules_df, **_kwargs):
        import pandas as _pd

        empty = _pd.DataFrame(
            columns=["Pattern", "Clean Payee", "Suggested Category", "Scope", "Last used"]
        )
        return empty, {"total": 0, "client_specific": 0, "used_30d": 0}

    def build_statement_pivot(_df, **_kwargs):
        import pandas as _pd

        return _pd.DataFrame()

    PIVOT_GROUP_BY_OPTIONS = ("Category", "Payee")
    PIVOT_VALUE_KIND_OPTIONS = ("sum", "count")

    def azure_ocr_configured():
        import os as _os

        return bool(
            (_os.environ.get("AZURE_OCR_FUNCTION_URL") or "").strip()
            and (_os.environ.get("AZURE_OCR_FUNCTION_KEY") or "").strip()
        )

    def azure_ocr_status():
        import os as _os

        url = (_os.environ.get("AZURE_OCR_FUNCTION_URL") or "").strip()
        key = (_os.environ.get("AZURE_OCR_FUNCTION_KEY") or "").strip()
        return {
            "configured": bool(url) and bool(key),
            "url": url,
            "has_key": bool(key),
            "hint": (
                "Set AZURE_OCR_FUNCTION_URL and AZURE_OCR_FUNCTION_KEY App Settings "
                "(or direct Azure Document Intelligence env vars) for bank statements."
            ),
        }

    def emit_gate_a3_smoke_evidence(*_args, **_kwargs):
        return False

    def run_azure_ocr_pipeline(_pdf_bytes, _pdf_filename, _client_name, _logger, **_kwargs):
        return (
            None,
            ["[WARN] Azure OCR pipeline unavailable in this deploy (bank_statements out of sync)."],
            {
                "status": "error",
                "configured": False,
                "transaction_count": 0,
                "grok_totals": None,
                "message": "bank_statements module out of sync",
            },
        )

    from bank_statements import (
        missing_document_counts,
        scripts_available,
        transaction_summary_metrics,
    )
from data_paths import render_data_path_error, resolve_data_path
from diagnostics import (
    get_app_info,
    get_app_user,
    get_data_freshness,
    get_operational_hints,
    get_qms_status,
    get_time_greeting,
)

st.set_page_config(page_title="SLAM Services Revenue Tracker", layout="wide", page_icon="📊")

APP_VERSION = "v2.45.6"
LOGGER = setup_app_logging()

SLAM_CSS = """
<style>
    .slam-header { font-size: 1.05rem; color: #1e3a5f; margin-bottom: 0.25rem; }
    .slam-subtle { color: #5a6c7d; font-size: 0.9rem; }
    .slam-action-card {
        background: #fff8e6;
        border-left: 4px solid #d97706;
        padding: 0.75rem 1rem;
        border-radius: 4px;
        margin-bottom: 1rem;
    }
    .slam-dashboard-hero {
        background: linear-gradient(135deg, #f0f7ff 0%, #f8fafc 100%);
        border: 1px solid #cbd5e1;
        border-left: 5px solid #1e3a5f;
        padding: 1.25rem 1.5rem;
        border-radius: 10px;
        margin-bottom: 1.25rem;
        box-shadow: 0 1px 4px rgba(30, 58, 95, 0.06);
    }
    .slam-dashboard-greeting {
        margin: 0;
        color: #1e3a5f;
        font-size: 1.75rem;
        font-weight: 700;
        line-height: 1.25;
    }
    .slam-dashboard-date {
        margin: 0.4rem 0 0;
        color: #5a6c7d;
        font-size: 0.95rem;
    }
    .slam-section-header {
        color: #1e3a5f;
        font-size: 1.05rem;
        font-weight: 600;
        margin: 0 0 0.75rem 0;
        padding-bottom: 0.35rem;
        border-bottom: 1px solid #e2e8f0;
    }
    .slam-section-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 1rem 1.15rem;
        margin-bottom: 1.25rem;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
    }
    .slam-priority-hero {
        background: linear-gradient(135deg, #fff1f2 0%, #fff8e6 100%);
        border: 2px solid #dc2626;
        border-left: 6px solid #dc2626;
        padding: 1.15rem 1.35rem;
        border-radius: 10px;
        margin: 0.5rem 0 1.25rem 0;
        box-shadow: 0 3px 12px rgba(220, 38, 38, 0.14);
    }
    .slam-priority-hero h4 {
        margin: 0 0 0.4rem 0;
        color: #991b1b;
        font-size: 1.2rem;
        font-weight: 700;
    }
    .slam-priority-hero p { margin: 0; color: #7f1d1d; font-size: 0.95rem; line-height: 1.45; }
    .slam-priority-caught-up {
        background: linear-gradient(135deg, #ecfdf5 0%, #f0fdf4 100%);
        border: 2px solid #059669;
        border-left: 6px solid #059669;
        padding: 1.15rem 1.35rem;
        border-radius: 10px;
        margin: 0.5rem 0 1.25rem 0;
        box-shadow: 0 2px 8px rgba(5, 150, 105, 0.1);
    }
    .slam-priority-caught-up strong { color: #065f46; font-size: 1.05rem; }
    div[data-testid="stMetric"] {
        background: #f8fafc;
        padding: 0.65rem 0.75rem;
        border-radius: 8px;
        border: 1px solid #e2e8f0;
    }
    .slam-sidebar-user {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 0.65rem 0.85rem;
        margin-bottom: 0.5rem;
    }
    .slam-sidebar-user-name {
        color: #1e3a5f;
        font-size: 0.95rem;
        font-weight: 600;
        margin: 0;
    }
    .slam-sidebar-status {
        color: #64748b;
        font-size: 0.82rem;
        margin: 0.25rem 0 0;
        line-height: 1.4;
    }
    .slam-login-header {
        text-align: center;
        margin-bottom: 1.25rem;
    }
    .slam-login-icon {
        font-size: 2.5rem;
        line-height: 1;
        display: block;
        margin-bottom: 0.5rem;
    }
    .slam-login-header h2 {
        margin: 0;
        color: #1e3a5f;
        font-size: 1.65rem;
        font-weight: 700;
    }
    .slam-login-tagline {
        color: #5a6c7d;
        font-size: 0.95rem;
        margin: 0.35rem 0 0;
    }
    .slam-login-note {
        color: #64748b;
        font-size: 0.85rem;
        text-align: center;
        margin: 0 0 1rem 0;
        padding: 0.5rem 0.75rem;
        background: #f1f5f9;
        border-radius: 6px;
        border-left: 3px solid #1e3a5f;
    }
    @media (max-width: 768px) {
        .slam-dashboard-greeting { font-size: 1.4rem; }
        .slam-dashboard-hero { padding: 1rem; }
        .slam-section-card { padding: 0.85rem; }
    }
</style>
"""
st.markdown(SLAM_CSS, unsafe_allow_html=True)

# --- Data source mode (Phase 3 dual mode) ---
POSTGRES_REQUESTED = os.environ.get("USE_POSTGRES", "").strip().lower() in ("1", "true", "yes")
USE_POSTGRES = POSTGRES_REQUESTED
DATA_SOURCE = "postgresql" if USE_POSTGRES else "csv"
DB_HEALTH = "ok"  # ok | warn | error
DB_STATUS_TITLE = ""
DB_STATUS_DETAIL = ""

# --- Auth (shared team password; username is personalization only) ---
HAS_CUSTOM_PASSWORD = "SLAM_APP_PASSWORD" in os.environ
APP_PASSWORD = os.environ.get("SLAM_APP_PASSWORD", "SLAM2026")
LOGIN_USER_CHOICES = ("Laura", "Stef", "Patty", "Robert", "Other")

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "current_user" not in st.session_state:
    st.session_state.current_user = ""


def login():
    _, col, _ = st.columns([1, 1.25, 1])
    with col:
        with st.container(border=True):
            st.markdown(
                """
                <div class="slam-login-header">
                    <span class="slam-login-icon">📊</span>
                    <h2>SLAM Services</h2>
                    <p class="slam-login-tagline">Revenue Reporting Tracker</p>
                </div>
                <p class="slam-login-note">Shared team access — select your name for personalization</p>
                """,
                unsafe_allow_html=True,
            )

            selected_user = st.selectbox("Username", LOGIN_USER_CHOICES, index=0)
            display_user = selected_user
            if selected_user == "Other":
                custom_name = st.text_input("Your name", placeholder="Enter your name")
                display_user = (custom_name or "").strip()

            password = st.text_input("Password", type="password", placeholder="Team password")
            if not HAS_CUSTOM_PASSWORD:
                st.caption(
                    "⚠️ Default password in use — set **SLAM_APP_PASSWORD** in Azure for production."
                )

            if st.button("Sign in", type="primary", use_container_width=True):
                if not display_user:
                    st.error("Please enter your name before signing in.")
                elif password != APP_PASSWORD:
                    log_event(LOGGER, "login_failed", user=display_user or None)
                    st.error("Incorrect password. Contact Robert if you need a reset.")
                else:
                    st.session_state.authenticated = True
                    st.session_state.current_user = display_user
                    log_event(LOGGER, "login_success", user=display_user)
                    st.rerun()


if not st.session_state.authenticated:
    login()
    st.stop()


# --- Data path resolution (CSV fallback) ---
DATA_PATH: Path | None = None
DATA_PATH_LOGS: list[str] = []


def _init_csv_data_path() -> None:
    global DATA_PATH, DATA_PATH_LOGS
    DATA_PATH, DATA_PATH_LOGS = resolve_data_path()


class DataLoadError(Exception):
    """Raised when client or request data cannot be loaded."""


if not POSTGRES_REQUESTED:
    _init_csv_data_path()
    if DATA_PATH is None:
        DB_HEALTH = "error"
        DB_STATUS_TITLE = "CSV files — not found"
        DB_STATUS_DETAIL = render_data_path_error(DATA_PATH_LOGS)
        st.error(f"❌ Critical: {DB_STATUS_DETAIL}")
        with st.expander("Debug: path resolution log"):
            st.code("\n".join(DATA_PATH_LOGS))
        st.stop()
    DB_STATUS_TITLE = "CSV files"
    DB_STATUS_DETAIL = f"Reading from `{DATA_PATH}`"
else:
    try:
        from db_utils import get_connection_status

        status = get_connection_status()
        ok = status["connected"]
        msg = status["message"]
        if not ok:
            st.warning(
                "⚠️ PostgreSQL is configured but not reachable — using CSV files for now. "
                "Your saved edits will go to the CSV until the database is available."
            )
            USE_POSTGRES = False
            DATA_SOURCE = "csv"
            DB_HEALTH = "warn"
            DB_STATUS_TITLE = "CSV fallback (PostgreSQL unavailable)"
            DB_STATUS_DETAIL = msg
            _init_csv_data_path()
            if DATA_PATH is None:
                DB_HEALTH = "error"
                st.error(
                    "❌ Critical: PostgreSQL failed and no CSV backup folder was found.\n\n"
                    f"{msg}\n\n"
                    "Ask Robert to check Azure App Settings (USE_POSTGRES, DATABASE_URL) "
                    "or restore the Data folder."
                )
                st.stop()
            DB_STATUS_DETAIL = f"{msg} · CSV: `{DATA_PATH}`"
        else:
            DB_STATUS_TITLE = "PostgreSQL"
            stats = status.get("stats") or {}
            DB_STATUS_DETAIL = (
                f"{msg} · {stats.get('clients', 0)} clients, "
                f"{stats.get('requests', 0)} revenue requests"
            )
            if DATA_PATH is None:
                resolved, _ = resolve_data_path()
                if resolved is not None:
                    DATA_PATH = resolved
    except ImportError as exc:
        st.warning(f"⚠️ Database tools not available ({exc}). Using CSV files.")
        USE_POSTGRES = False
        DATA_SOURCE = "csv"
        DB_HEALTH = "warn"
        DB_STATUS_TITLE = "CSV fallback (db_utils missing)"
        DB_STATUS_DETAIL = str(exc)
        _init_csv_data_path()
        if DATA_PATH is None:
            DB_HEALTH = "error"
            st.error("❌ Critical: Could not load database utilities or CSV data.")
            st.stop()
        DB_STATUS_DETAIL = f"{exc} · CSV: `{DATA_PATH}`"


def render_data_source_status(client_count: int = 0, request_count: int = 0) -> None:
    """Sidebar indicator — CSV vs PostgreSQL, connection health, recovery tips."""
    with st.sidebar.expander("📊 Data Source Status", expanded=DB_HEALTH != "ok"):
        if DATA_SOURCE == "postgresql" and DB_HEALTH == "ok":
            st.success(f"✅ {DB_STATUS_TITLE} — connected")
            st.caption("Edits save directly to the database.")
            if client_count or request_count:
                st.metric("Loaded records", f"{client_count} clients · {request_count} requests")
        elif DB_HEALTH == "warn":
            st.warning(f"⚠️ {DB_STATUS_TITLE}")
            st.caption(DB_STATUS_DETAIL)
            if client_count or request_count:
                st.caption(f"Showing {client_count} clients · {request_count} requests from CSV.")
        elif DB_HEALTH == "error":
            st.error(f"❌ {DB_STATUS_TITLE}")
            st.caption(DB_STATUS_DETAIL)
        else:
            st.info(f"📁 {DB_STATUS_TITLE}")
            st.caption(DB_STATUS_DETAIL)
            if client_count or request_count:
                st.caption(f"{client_count} clients · {request_count} requests loaded.")

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button(
                "🔍 Test connection",
                key="btn_test_db",
                disabled=not POSTGRES_REQUESTED,
                use_container_width=True,
            ):
                try:
                    from db_utils import get_connection_status

                    result = get_connection_status(reset=True)
                    if result["connected"]:
                        stats = result.get("stats") or {}
                        st.success(
                            f"{result['message']} "
                            f"({stats.get('clients', 0)} clients, "
                            f"{stats.get('requests', 0)} requests in DB)"
                        )
                    else:
                        st.error(result["message"])
                except Exception as exc:
                    st.error(f"Connection test failed: {exc}")
        with col_b:
            if st.button("🔄 Refresh status", key="btn_refresh_status", use_container_width=True):
                st.cache_data.clear()
                st.rerun()

        if POSTGRES_REQUESTED and DB_HEALTH == "warn":
            with st.expander("Recovery options", expanded=False):
                st.markdown(
                    "**If saves aren't working:**\n"
                    "1. Wait 30 seconds and click **Test connection**\n"
                    "2. Ask Robert to check Azure firewall + App Settings\n"
                    "3. **Temporary CSV fallback:** set `USE_POSTGRES=false` in Azure "
                    "(edits save to CSV until Postgres is fixed)"
                )


# --- Data loading helpers (cached) ---
def _load_clients_csv() -> pd.DataFrame:
    if DATA_PATH is None:
        return pd.DataFrame()
    try:
        p = DATA_PATH / "Clients.csv"
        if not p.exists():
            return pd.DataFrame()
        df = pd.read_csv(p)
        if "Business Name" not in df.columns:
            df.columns = [c.strip() for c in df.iloc[0]]
            df = df.iloc[1:]
        df = df[df["Business Name"].notna() & (df["Business Name"].str.strip() != "")]
        df = df.reset_index(drop=True)

        def cat(name):
            n = str(name).upper()
            if any(
                x in n
                for x in [
                    "GRILL",
                    "CANTINA",
                    "RESTAURANT",
                    "TACOS",
                    "MEX",
                    "BAR",
                    "TAQUERIA",
                    "FIESTA",
                ]
            ):
                return "Restaurant/Bar"
            if any(
                x in n
                for x in [
                    "CONCRETE",
                    "ROOF",
                    "BUILDER",
                    "MASON",
                    "PAINT",
                    "REMODEL",
                    "PLUMB",
                    "CONTRACT",
                    "DRY",
                ]
            ):
                return "Construction/Trades"
            return "Other"

        df["industry_category"] = df["Business Name"].apply(cat)
        for col in ["EIN", "Entity Type", "City State Zip"]:
            if col not in df.columns:
                df[col] = ""
        for col in ["EIN", "Entity Type", "City State Zip"]:
            df[col] = df[col].fillna("").astype(str).replace({"nan": "", "None": ""})
        return df[["Business Name", "EIN", "Entity Type", "City State Zip", "industry_category"]]
    except Exception as exc:
        raise DataLoadError(
            "We couldn't read the client list from CSV. "
            "Please check that Clients.csv exists and try again."
        ) from exc


def _load_clients_db() -> pd.DataFrame:
    from db_utils import Client, friendly_db_error, get_session

    try:
        with get_session() as session:
            rows = session.query(Client).filter(Client.is_deleted.is_(False)).all()
            if not rows:
                return pd.DataFrame()
            return pd.DataFrame(
                [
                    {
                        "Business Name": r.business_name,
                        "EIN": r.ein or "",
                        "Entity Type": r.entity_type or "",
                        "City State Zip": r.address or "",
                        "industry_category": r.industry_type or "Other",
                    }
                    for r in rows
                ]
            )
    except Exception as exc:
        raise DataLoadError(
            "We couldn't load clients from the database. "
            "Try refreshing the page — if this continues, contact Robert."
            f" ({friendly_db_error(exc)})"
        ) from exc


@st.cache_data(ttl=60)
def load_clients():
    if USE_POSTGRES:
        return _load_clients_db()
    return _load_clients_csv()


def _load_requests_csv() -> pd.DataFrame:
    if DATA_PATH is None:
        return pd.DataFrame()
    try:
        p = DATA_PATH / "RevenueRequests.csv"
        if not p.exists():
            return pd.DataFrame()
        df = pd.read_csv(p)
        required = [
            "request_id",
            "business_name",
            "request_type",
            "period",
            "status",
            "amount_due",
            "due_date",
            "received_date",
            "notes",
            "bank_statement_received",
            "sales_report_received",
        ]
        for c in required:
            if c not in df.columns:
                df[c] = ""
        df["amount_due"] = pd.to_numeric(df["amount_due"], errors="coerce").fillna(0)
        for col in ["bank_statement_received", "sales_report_received"]:
            df[col] = (
                df[col]
                .astype(str)
                .str.strip()
                .str.lower()
                .isin(["yes", "y", "true", "1", "✔", "✓"])
            )
            df[col] = df[col].fillna(False).astype(bool)
        if "request_id" in df.columns:
            df["request_id"] = df["request_id"].astype(str)
        if "business_name" in df.columns:
            df["business_name"] = df["business_name"].fillna("").astype(str)
        return df
    except Exception as exc:
        raise DataLoadError(
            "We couldn't read RevenueRequests.csv. Please check the file exists and try again."
        ) from exc


def _load_requests_db() -> pd.DataFrame:
    from db_utils import Client, RevenueRequest, friendly_db_error, get_session

    try:
        with get_session() as session:
            rows = (
                session.query(RevenueRequest, Client.business_name)
                .join(Client, RevenueRequest.client_id == Client.client_id)
                .filter(RevenueRequest.is_deleted.is_(False))
                .all()
            )
            if not rows:
                return pd.DataFrame()
            records = []
            for req, business_name in rows:
                records.append(
                    {
                        "request_id": str(req.request_id),
                        "business_name": business_name or "",
                        "request_type": req.request_type or "",
                        "period": req.period or "",
                        "status": req.status or "Pending",
                        "amount_due": float(req.amount_due or 0),
                        "due_date": req.due_date.isoformat() if req.due_date else "",
                        "received_date": req.received_date.isoformat() if req.received_date else "",
                        "notes": req.notes or "",
                        "bank_statement_received": bool(req.bank_statement_received),
                        "sales_report_received": bool(req.sales_report_received),
                    }
                )
            return pd.DataFrame(records)
    except Exception as exc:
        raise DataLoadError(
            "We couldn't load revenue requests from the database. "
            "Try refreshing the page — if this continues, contact Robert."
            f" ({friendly_db_error(exc)})"
        ) from exc


@st.cache_data(ttl=60)
def load_requests():
    if USE_POSTGRES:
        return _load_requests_db()
    return _load_requests_csv()


def format_request_id(rid) -> str:
    """Display-friendly request_id (load_requests stores as str)."""
    s = str(rid).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        return s[:-2]
    return s


def bulk_select_label(rid, name: str) -> str:
    return f"{format_request_id(rid)} – {name}"


def days_overdue(due_date) -> int | None:
    """Whole days past due (positive = overdue). None if not parseable."""
    parsed = pd.to_datetime(due_date, errors="coerce")
    if pd.isna(parsed):
        return None
    delta = (datetime.now().date() - parsed.date()).days
    return delta if delta > 0 else 0


def _editor_has_unsaved_changes(edited: pd.DataFrame, original: pd.DataFrame) -> bool:
    """True when the data editor differs from the loaded filter view."""
    if edited.shape != original.shape:
        return True
    compare_cols = [c for c in original.columns if c in edited.columns]
    if not compare_cols:
        return False
    left = edited[compare_cols].fillna("").astype(str)
    right = original[compare_cols].fillna("").astype(str)
    return not left.equals(right)


def render_uat_welcome() -> None:
    """One-time dismissible banner for Laura/Stef UAT kickoff."""
    if st.session_state.get("uat_welcome_dismissed"):
        return
    st.info(
        "**Welcome to UAT week** — your daily workflow: "
        "1) Dashboard → Today's priority  "
        "2) Sidebar quick views (Overdue / This Month)  "
        "3) Revenue Requests → edit → **Save**  "
        "4) Use **Undo** if you make a mistake  "
        "5) Submit feedback in the sidebar if anything feels wrong."
    )
    if st.button("Got it — hide this banner", key="btn_dismiss_uat"):
        st.session_state["uat_welcome_dismissed"] = True
        st.rerun()


# --- Global filters in sidebar (propagate across pages) ---
def render_global_filters(req_df):
    st.sidebar.title("🔎 Global Filters")

    overdue_count = int(
        (
            (req_df["status"].isin(["Pending", "Received"]))
            & (pd.to_datetime(req_df["due_date"], errors="coerce") < datetime.now())
        ).sum()
    )
    if overdue_count:
        st.sidebar.caption(f"⚠️ {overdue_count} overdue item(s) need attention")

    st.sidebar.markdown("**Quick views**")
    preset = st.session_state.get("filter_preset")
    c1, c2 = st.sidebar.columns(2)
    with c1:
        if st.button("Overdue", key="preset_overdue", use_container_width=True):
            st.session_state["filter_preset"] = "overdue"
            st.rerun()
    with c2:
        if st.button("Pending", key="preset_pending", use_container_width=True):
            st.session_state["filter_preset"] = "pending"
            st.rerun()
    c3, c4 = st.sidebar.columns(2)
    with c3:
        if st.button("This Month", key="preset_this_month", use_container_width=True):
            st.session_state["filter_preset"] = "this_month"
            st.rerun()
    with c4:
        if st.button("Missing Docs", key="preset_missing_docs", use_container_width=True):
            st.session_state["filter_preset"] = "missing_docs"
            st.rerun()

    doc_counts = missing_document_counts(req_df)
    if doc_counts["missing_either"]:
        st.sidebar.caption(
            f"📄 Missing docs (Pending/Received): **{doc_counts['missing_bank']}** bank stmt · "
            f"**{doc_counts['missing_sales']}** sales rpt · "
            f"**{doc_counts['missing_both']}** both"
        )

    preset_labels = {
        "overdue": "overdue",
        "pending": "pending (Pending + Received status)",
        "this_month": "due **this month**",
        "missing_docs": "requests **missing bank statement and/or sales report**",
    }
    if preset in preset_labels:
        st.sidebar.info(f"Showing {preset_labels[preset]} only. Reset filters to see everything.")
        if preset == "missing_docs":
            st.sidebar.caption(
                f"Bank stmt only: {doc_counts['missing_bank']} · "
                f"Sales rpt only: {doc_counts['missing_sales']}"
            )

    overdue_only = preset == "overdue"
    preset_locked = preset in ("overdue", "this_month", "missing_docs")

    min_d = pd.to_datetime(req_df["due_date"], errors="coerce").min()
    max_d = pd.to_datetime(req_df["due_date"], errors="coerce").max()
    if pd.isna(min_d):
        min_d = datetime(2025, 10, 1)
    if pd.isna(max_d):
        max_d = datetime(2026, 6, 10)

    all_status = ["Pending", "Received", "Invoiced", "Paid"]
    default_status = ["Pending", "Received"] if preset == "pending" else all_status
    if overdue_only:
        default_status = ["Pending", "Received"]

    date_range = st.sidebar.date_input(
        "Due date range",
        value=(min_d.date(), max_d.date()),
        min_value=min_d.date(),
        max_value=max_d.date(),
        disabled=preset_locked,
    )
    sel_status = st.sidebar.multiselect(
        "Status", all_status, default=default_status, disabled=preset_locked
    )

    base_types = req_df["request_type"].dropna().unique().tolist() if len(req_df) else []
    extra_types = ["Payroll", "Tax prep"]
    all_types = sorted(set(base_types) | set(extra_types))
    sel_type = st.sidebar.multiselect(
        "Request Type", all_types, default=all_types, disabled=preset_locked
    )

    all_ind = ["All", "Restaurant/Bar", "Construction/Trades", "Other"]
    sel_ind = st.sidebar.selectbox("Industry Segment", all_ind, index=0, disabled=preset_locked)

    if st.sidebar.button("Reset Filters", key="btn_reset_filters"):
        for k in list(st.session_state.keys()):
            if k.startswith(
                ("filter_", "revenue_editor", "last_filter_industry", "widget_", "filter_preset")
            ):
                try:
                    del st.session_state[k]
                except Exception:
                    pass
        st.session_state.pop("filter_preset", None)
        st.cache_data.clear()
        st.rerun()

    return {
        "date_range": date_range,
        "status": sel_status,
        "request_type": sel_type,
        "industry": sel_ind,
        "overdue_only": overdue_only,
        "this_month_only": preset == "this_month",
        "missing_docs_only": preset == "missing_docs",
        "filter_preset": preset,
    }


def apply_filters(req_df, clients_df, f):
    df = req_df.copy()
    df["due_date_parsed"] = pd.to_datetime(df["due_date"], errors="coerce")
    overdue_mask = (df["status"].isin(["Pending", "Received"])) & (
        df["due_date_parsed"] < datetime.now()
    )

    if f.get("overdue_only"):
        df = df[overdue_mask]
    elif f.get("this_month_only"):
        now = datetime.now()
        month_start = datetime(now.year, now.month, 1)
        if now.month == 12:
            month_end = datetime(now.year + 1, 1, 1)
        else:
            month_end = datetime(now.year, now.month + 1, 1)
        df = df[(df["due_date_parsed"] >= month_start) & (df["due_date_parsed"] < month_end)]
    elif f.get("missing_docs_only"):
        df = df[df["status"].isin(["Pending", "Received"])]
        df = df[(~df["bank_statement_received"]) | (~df["sales_report_received"])]
    else:
        if len(f["date_range"]) == 2:
            lo, hi = pd.to_datetime(f["date_range"][0]), pd.to_datetime(f["date_range"][1])
            df = df[(df["due_date_parsed"] >= lo) & (df["due_date_parsed"] <= hi)]
        if f["status"]:
            df = df[df["status"].isin(f["status"])]
        if f["request_type"]:
            df = df[df["request_type"].isin(f["request_type"])]
        if f["industry"] != "All":
            matched_clients = clients_df[clients_df["industry_category"] == f["industry"]][
                "Business Name"
            ].tolist()
            df = df[df["business_name"].isin(matched_clients)]

    enriched = enrich_with_overdue_fields(df.drop(columns=["due_date_parsed"], errors="ignore"))
    return enriched


# --- Persist helper (CSV default; PostgreSQL when USE_POSTGRES=true) ---
def _requests_csv_path() -> Path:
    if DATA_PATH is None:
        raise RuntimeError(
            "CSV path unavailable. Deploy Data/Revenue_Tracker_Migration or enable PostgreSQL writes."
        )
    return DATA_PATH / "RevenueRequests.csv"


def save_requests(df, path: Path | None = None) -> list[str]:
    """Persist revenue requests to CSV or PostgreSQL. Returns non-fatal warnings."""
    if USE_POSTGRES:
        from db_utils import friendly_db_error, save_revenue_requests_from_df, test_connection

        ok, msg = test_connection(reset=True)
        if not ok:
            hint = (
                "\n\nThe app is using CSV files as a backup. Contact Robert if this persists."
                if POSTGRES_REQUESTED
                else ""
            )
            raise RuntimeError(
                "Could not save — the database is not responding right now. "
                "Your changes were **not** written. Please wait a moment and try again.\n\n"
                f"{msg}{hint}"
            )
        try:
            updated, warnings = save_revenue_requests_from_df(df)
        except Exception as exc:
            raise RuntimeError(
                "Could not save your changes to the database. "
                "Nothing was written — please try again or contact Robert.\n\n"
                f"{friendly_db_error(exc)}"
            ) from exc
        if updated == 0 and warnings:
            raise RuntimeError(
                "No rows were saved. "
                + "; ".join(warnings[:5])
                + (" …" if len(warnings) > 5 else "")
            )
        return warnings
    try:
        target = path or _requests_csv_path()
        df.to_csv(target, index=False)
    except OSError as exc:
        raise RuntimeError(
            "Could not save to RevenueRequests.csv. "
            "Check that the data folder is writable and try again."
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"Could not save changes to CSV: {exc}") from exc
    return []


def _feedback_log_path() -> Path:
    if DATA_PATH is not None:
        return DATA_PATH / "feedback_log.csv"
    resolved, _ = resolve_data_path()
    if resolved is not None:
        return resolved / "feedback_log.csv"
    fallback = Path("/home/site/wwwroot/Data/Revenue_Tracker_Migration")
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback / "feedback_log.csv"


def enrich_with_overdue_fields(df: pd.DataFrame) -> pd.DataFrame:
    """Add overdue flag and days_overdue from full request data (ignores sidebar filters)."""
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()
    out = df.copy()
    parsed = pd.to_datetime(out["due_date"], errors="coerce")
    out["overdue"] = (out["status"].isin(["Pending", "Received"])) & (parsed < datetime.now())
    out["days_overdue"] = parsed.apply(lambda d: days_overdue(d) if pd.notna(d) else None)
    return out


def get_all_overdue(req_df: pd.DataFrame) -> pd.DataFrame:
    """All overdue Pending/Received requests, sorted by due date (oldest first)."""
    if req_df is None or req_df.empty:
        return pd.DataFrame()
    enriched = enrich_with_overdue_fields(req_df)
    overdue = enriched[enriched["overdue"]].copy()
    if overdue.empty:
        return overdue
    overdue["_sort_due"] = pd.to_datetime(overdue["due_date"], errors="coerce")
    overdue = overdue.sort_values(["_sort_due", "days_overdue"], ascending=[True, False])
    return overdue.drop(columns=["_sort_due"], errors="ignore")


def render_todays_priority(req_df: pd.DataFrame) -> None:
    """Prominent dashboard briefing — always uses full dataset, not sidebar filters."""
    overdue = get_all_overdue(req_df)

    if overdue.empty:
        st.markdown(
            '<div class="slam-priority-caught-up">'
            "<strong>Today's priority</strong><br>"
            "All caught up — no overdue revenue requests need follow-up right now."
            "</div>",
            unsafe_allow_html=True,
        )
        return

    count = len(overdue)
    total_due = overdue["amount_due"].sum()
    oldest = overdue["days_overdue"].max()
    oldest = int(oldest) if pd.notna(oldest) else 0
    st.markdown(
        f'<div class="slam-priority-hero">'
        f"<h4>Today's priority — {count} overdue request{'s' if count != 1 else ''}</h4>"
        f"<p>Oldest item is <strong>{oldest} day(s)</strong> past due · "
        f"Total amount due: <strong>${total_due:,.0f}</strong>. "
        "Contact clients, then update status on Revenue Requests.</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    show = overdue.head(10).copy()
    show["request_id"] = show["request_id"].map(format_request_id)
    show["days_overdue"] = show["days_overdue"].fillna(0).astype(int)
    if "amount_due" in show.columns:
        show["amount_due"] = show["amount_due"].apply(
            lambda x: f"${float(x):,.0f}" if pd.notna(x) else ""
        )
    display_cols = [
        "days_overdue",
        "business_name",
        "request_type",
        "amount_due",
        "due_date",
        "request_id",
        "period",
        "status",
    ]
    display_cols = [c for c in display_cols if c in show.columns]
    st.dataframe(
        show[display_cols],
        width="stretch",
        hide_index=True,
        column_config={
            "days_overdue": st.column_config.NumberColumn("Days overdue", format="%d"),
            "business_name": "Business",
            "request_type": "Type",
            "amount_due": "Amount",
            "due_date": "Due date",
            "request_id": "Request ID",
        },
    )
    if count > 10:
        st.caption(f"Showing 10 of {count} overdue items (sorted by due date).")

    c1, c2 = st.columns(2)
    with c1:
        if st.button(
            "🔴 Open Overdue quick view",
            type="primary",
            key="btn_priority_overdue",
            use_container_width=True,
        ):
            st.session_state["filter_preset"] = "overdue"
            st.rerun()
    with c2:
        if st.button(
            "📝 Update on Revenue Requests",
            key="btn_priority_revenue",
            use_container_width=True,
        ):
            st.session_state["goto_page"] = "Revenue Requests"
            st.rerun()


# --- Dashboard page enhancements (dynamic KPIs, overdue alerts) ---
def dashboard_page(clients_df, req_df, filtered):
    greeting = get_time_greeting()
    user = get_app_user()
    date_str = datetime.now().strftime("%A, %B %d, %Y")
    st.markdown(
        f'<div class="slam-dashboard-hero">'
        f'<h2 class="slam-dashboard-greeting">{greeting}, {user}!</h2>'
        f'<p class="slam-dashboard-date">{date_str}</p>'
        f"</div>",
        unsafe_allow_html=True,
    )

    render_uat_welcome()
    render_todays_priority(req_df)

    total_clients = len(clients_df)
    total_pending_amt = filtered[filtered["status"].isin(["Pending", "Received", "Invoiced"])][
        "amount_due"
    ].sum()
    overdue_cnt = filtered["overdue"].sum() if "overdue" in filtered.columns else 0
    completion_pct = round(
        100 * len(filtered[filtered["status"] == "Paid"]) / max(1, len(filtered)), 1
    )

    with st.container(border=True):
        st.markdown('<p class="slam-section-header">Key metrics</p>', unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Clients", total_clients)
        c2.metric("Pending Amount", f"${total_pending_amt:,.0f}")
        c3.metric("Overdue Items", overdue_cnt)
        c4.metric("Paid Rate", f"{completion_pct}%")

        full_doc = missing_document_counts(req_df)
        if full_doc["missing_either"]:
            st.caption(
                f"**Missing documents** (all active requests): "
                f"{full_doc['missing_bank']} need bank statement · "
                f"{full_doc['missing_sales']} need sales report · "
                f"{full_doc['missing_both']} need both. "
                "Use **Bank Statements** page to process PDFs, then **Mark as Received**."
            )

    with st.container(border=True):
        st.markdown('<p class="slam-section-header">Status breakdown</p>', unsafe_allow_html=True)
        status_counts = filtered["status"].value_counts().reset_index()
        status_counts.columns = ["status", "count"]
        st.bar_chart(status_counts, x="status", y="count")

    with st.container(border=True):
        st.markdown(
            '<p class="slam-section-header">Overdue requests — action required</p>',
            unsafe_allow_html=True,
        )
        overdue = filtered[filtered.get("overdue", False)]
        if not overdue.empty:
            overdue_display = overdue.copy()
            overdue_display["request_id"] = overdue_display["request_id"].map(format_request_id)
            cols = [
                "request_id",
                "business_name",
                "request_type",
                "period",
                "amount_due",
                "due_date",
                "days_overdue",
                "notes",
            ]
            cols = [c for c in cols if c in overdue_display.columns]
            st.dataframe(overdue_display[cols], width="stretch", hide_index=True)
        else:
            st.success("No overdue items in current filter.")

    with st.container(border=True):
        st.markdown(
            '<p class="slam-section-header">Recent activity</p>',
            unsafe_allow_html=True,
        )
        st.caption("Last 10 records under current filters (by due date).")
        recent = filtered.sort_values("due_date", ascending=False).head(10)
        st.dataframe(
            recent[["business_name", "request_type", "period", "status", "amount_due", "due_date"]],
            width="stretch",
            hide_index=True,
        )


# --- Clients page with revenue aggregates + enriched info ---
def clients_page(clients_df, req_df, filtered):
    st.header("👥 Client Roster & Revenue Status")

    search = st.text_input("Search clients", "")
    dfc = clients_df.copy()
    if search:
        dfc = dfc[dfc["Business Name"].str.contains(search, case=False, na=False)]

    # Aggregate revenue info per client
    agg = (
        req_df.groupby("business_name")
        .agg(
            outstanding_amt=(
                "amount_due",
                lambda x: x[
                    req_df.loc[x.index, "status"].isin(["Pending", "Received", "Invoiced"])
                ].sum(),
            ),
            total_requests=("request_id", "count"),
            last_status=("status", lambda s: s.iloc[-1] if len(s) else ""),
        )
        .reset_index()
    )
    agg.columns = ["Business Name", "Outstanding Amount", "Total Requests", "Most Recent Status"]

    merged = dfc.merge(agg, on="Business Name", how="left")
    merged = merged.fillna({"Outstanding Amount": 0, "Total Requests": 0, "Most Recent Status": ""})

    # Apply global industry filter if active
    if "industry_category" in merged:
        if st.session_state.get("last_filter_industry") not in [None, "All"]:
            merged = merged[merged["industry_category"] == st.session_state["last_filter_industry"]]

    st.dataframe(
        merged[
            [
                "Business Name",
                "EIN",
                "Entity Type",
                "City State Zip",
                "industry_category",
                "Outstanding Amount",
                "Total Requests",
                "Most Recent Status",
            ]
        ],
        width="stretch",
        hide_index=True,
    )

    if st.button("Export Filtered Clients CSV"):
        csv_buf = io.StringIO()
        merged.to_csv(csv_buf, index=False)
        st.download_button(
            "Download clients_export.csv",
            csv_buf.getvalue(),
            file_name=f"clients_enriched_{datetime.now().strftime('%Y%m%d')}.csv",
        )


# --- Revenue Requests page: advanced filtering, editable table, bulk + save ---
def requests_page(req_df, clients_df, filtered_global):
    st.header("💰 Revenue Requests — Live Editor")

    # Additional client-side search on top of global filters
    search_term = st.text_input("Search client name or notes", "")
    df = filtered_global.copy()
    if search_term:
        mask = df["business_name"].str.contains(search_term, case=False, na=False) | df[
            "notes"
        ].astype(str).str.contains(search_term, case=False, na=False)
        df = df[mask]

    st.caption(f"Showing {len(df)} of {len(req_df)} total requests under current filters.")

    if df.empty:
        st.info("No matching rows after filtering.")
        return

    # Minimal defensive undo stack init (v2.14 P2 quick-win)
    if "undo_stack" not in st.session_state or not isinstance(
        st.session_state.get("undo_stack"), list
    ):
        st.session_state.undo_stack = []

    editor_cols = [
        "request_id",
        "business_name",
        "request_type",
        "period",
        "status",
        "amount_due",
        "due_date",
        "received_date",
        "notes",
        "bank_statement_received",
        "sales_report_received",
    ]
    edited = st.data_editor(
        df[editor_cols],
        num_rows="fixed",
        width="stretch",
        key="revenue_editor",
        hide_index=True,
        column_config={
            "request_id": st.column_config.TextColumn("Request #", disabled=True),
            "business_name": st.column_config.TextColumn("Client", disabled=True),
            "request_type": st.column_config.TextColumn("Type", disabled=True),
            "period": st.column_config.TextColumn("Period", disabled=True),
            "status": st.column_config.SelectboxColumn(
                "Status",
                options=["Pending", "Received", "Invoiced", "Paid"],
                required=True,
            ),
            "amount_due": st.column_config.NumberColumn("Amount Due ($)", min_value=0, step=50),
            "due_date": st.column_config.TextColumn("Due Date"),
            "received_date": st.column_config.TextColumn("Received Date"),
            "notes": st.column_config.TextColumn("Notes"),
            "bank_statement_received": st.column_config.CheckboxColumn("Bank Stmt"),
            "sales_report_received": st.column_config.CheckboxColumn("Sales Rpt"),
        },
    )

    has_unsaved = _editor_has_unsaved_changes(edited, df[editor_cols])
    st.session_state["revenue_unsaved"] = has_unsaved
    if has_unsaved:
        st.warning(
            "⚠️ **Unsaved changes** — click **Save** before switching pages or reloading data."
        )

    col1, col2 = st.columns(2)
    save_label = "💾 Save All Changes to Database" if USE_POSTGRES else "💾 Save All Changes to CSV"
    with col1:
        if st.button(save_label, type="primary"):
            try:
                # Snapshot pre-edit state for undo (P2 stack, last 5 per Section 14.2)
                snapshot = req_df.copy()
                master = req_df.set_index("request_id")
                for _, row in edited.iterrows():
                    rid = row["request_id"]
                    for col in [
                        "status",
                        "amount_due",
                        "due_date",
                        "received_date",
                        "notes",
                        "bank_statement_received",
                        "sales_report_received",
                    ]:
                        if rid in master.index:
                            master.at[rid, col] = row[col]
                updated = master.reset_index()
                warnings = save_requests(updated)
                dest = "PostgreSQL" if USE_POSTGRES else "CSV"
                log_event(LOGGER, "save_requests", destination=dest, rows=len(edited))
                # Push to defensive undo stack (trim to last 5)
                if not isinstance(st.session_state.get("undo_stack"), list):
                    st.session_state.undo_stack = []
                st.session_state.undo_stack.append(snapshot)
                st.session_state.undo_stack = st.session_state.undo_stack[-5:]
                st.session_state["last_save_message"] = (
                    f"Saved at {datetime.now().strftime('%H:%M')} to {dest}."
                )
                st.session_state.pop("revenue_unsaved", None)
                if USE_POSTGRES:
                    st.success("✅ Saved changes to PostgreSQL. Filters will pick up immediately.")
                else:
                    st.success(
                        "✅ Saved changes to RevenueRequests.csv. Filters will pick up immediately."
                    )
                if warnings:
                    st.warning("Some rows were skipped: " + "; ".join(warnings[:5]))
                st.cache_data.clear()
                st.rerun()
            except Exception as exc:
                log_event(LOGGER, "save_failed", error=str(exc)[:200])
                st.error(
                    f"Save failed — **no data was written**. Your edits are still on screen.\n\n{exc}"
                )
                st.info(
                    "Wait a few seconds, then click **Save** again. If it keeps failing, use sidebar **Submit Runtime Feedback** or contact Robert."
                )

        if st.session_state.get("undo_stack"):
            if st.button("↩️ Undo Last Change", type="secondary"):
                try:
                    prev = st.session_state.undo_stack.pop()
                    undo_warnings = save_requests(prev)
                    st.warning("Last edit undone from in-memory snapshot (within this session).")
                    if undo_warnings:
                        st.warning(
                            "Some rows were skipped on undo: " + "; ".join(undo_warnings[:5])
                        )
                    st.cache_data.clear()
                    st.rerun()
                except Exception as exc:
                    st.error(f"Undo failed. {exc}")

    with col2:
        # Export of current filtered view
        csv_buf = io.StringIO()
        df.to_csv(csv_buf, index=False)
        st.download_button(
            "📥 Export filtered CSV",
            csv_buf.getvalue(),
            file_name=f"revenue_filtered_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        )

    st.markdown("---")
    st.subheader("Quick Bulk Status Update")

    # === P1 UX FIX (v2.11) – directly addresses runtime feedback: "Use business_name column values in bulk dropdown" ===
    # Build human-readable labels while keeping the stable PK (request_id) for the write path.
    # One client may have multiple open requests, so we show "request_id – business_name" and resolve back to PKs.
    df_for_select = df.copy()
    display_options = [
        bulk_select_label(rid, name)
        for rid, name in zip(
            df_for_select["request_id"], df_for_select["business_name"], strict=True
        )
    ]
    id_map = {
        label: rid for label, rid in zip(display_options, df_for_select["request_id"], strict=True)
    }

    selected_labels = st.multiselect(
        "Select requests to bulk-update (Client name shown for clarity):",
        options=display_options,
        default=[],
    )
    selected_ids = [
        id_map[label] for label in selected_labels
    ]  # resolved back to the real numeric PKs

    new_bulk = st.selectbox("Set status to:", ["Pending", "Received", "Invoiced", "Paid"], index=1)

    bulk_confirm = False
    if selected_labels:
        bulk_confirm = st.checkbox(
            f"I confirm updating **{len(selected_labels)}** request(s) to **{new_bulk}**",
            key="bulk_confirm_checkbox",
        )

    if st.button(
        "Apply Bulk Update",
        disabled=len(selected_labels) == 0 or not bulk_confirm,
        type="primary",
    ):
        if selected_ids:
            try:
                snapshot = req_df.copy()
                master = req_df.set_index("request_id")
                for rid in selected_ids:
                    if rid in master.index:
                        master.at[rid, "status"] = new_bulk
                updated = master.reset_index()
                warnings = save_requests(updated)
                if not isinstance(st.session_state.get("undo_stack"), list):
                    st.session_state.undo_stack = []
                st.session_state.undo_stack.append(snapshot)
                st.session_state.undo_stack = st.session_state.undo_stack[-5:]
                dest = "PostgreSQL" if USE_POSTGRES else "RevenueRequests.csv"
                st.success(
                    f"Updated {len(selected_ids)} request(s) to status '{new_bulk}' ({dest})."
                )
                if warnings:
                    st.warning("Some rows were skipped: " + "; ".join(warnings[:5]))
                st.cache_data.clear()
                st.rerun()
            except Exception as exc:
                st.error(f"Bulk update failed — no data written. {exc}")


def _render_grok_vision_section(selected_client: str) -> None:
    """Prominent "Prepare for Grok Vision" panel — shown after any Process Statement run.

    Auto-expands when Azure Document Intelligence extracted 0 transactions (the most common
    case for scanned/image-only statements). Always available as a collapsed expander
    once a PDF has been processed, so Laura can route any statement through Grok if
    Azure OCR misses something.
    """
    pdf_name = st.session_state.get("bank_stmt_pdf_name") or ""
    pdf_path = st.session_state.get("bank_stmt_pdf_path") or ""
    if not pdf_name:
        return

    txn_df = st.session_state.get("bank_stmt_txn_df")
    parsed_zero = txn_df is not None and isinstance(txn_df, pd.DataFrame) and txn_df.empty
    no_text_layer = not st.session_state.get("bank_stmt_text_layer", False)
    auto_expand = parsed_zero or no_text_layer

    cropped_dir = st.session_state.get("bank_stmt_cropped_dir")
    cropped_count = int(st.session_state.get("bank_stmt_cropped_count") or 0)

    header = "🤖 Prepare for Grok Vision" + (
        " — recommended (no text extracted)" if parsed_zero else ""
    )
    with st.expander(header, expanded=auto_expand):
        if parsed_zero:
            st.warning(
                "No transactions were extracted (often a scanned/image-only PDF). "
                "Use Grok Vision below to extract transactions, then paste the CSV at the "
                "bottom of this page or save it for Process-Statement.ps1."
            )
        else:
            st.caption(
                "Use this if you want to double-check Azure OCR output against Grok's vision, "
                "or if any transactions look wrong."
            )

        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**Client**: {selected_client}")
            st.markdown(f"**PDF**: `{pdf_name}`")
        with c2:
            if pdf_path:
                st.markdown(f"**Saved PDF**: `{pdf_path}`")
                st.caption("Upload this file to Grok Vision (drag-and-drop from the path above).")
            azure_checks = int(st.session_state.get("bank_stmt_azure_check_count") or 0)
            if azure_checks > 0:
                st.markdown(
                    f"**Azure check analyzer**: {azure_checks} check(s) read from imaging pages "
                    f"(`prebuilt-check.us` — no local crop files)."
                )
            elif cropped_count > 0 and cropped_dir:
                checks = st.session_state.get("bank_stmt_cropped_checks") or 0
                deposits = st.session_state.get("bank_stmt_cropped_deposits") or 0
                if checks or deposits:
                    st.markdown(
                        f"**Cropped images**: {cropped_count} total "
                        f"({checks} checks + {deposits} deposit slips) in `{cropped_dir}`"
                    )
                else:
                    st.markdown(f"**Cropped checks**: {cropped_count} image(s) in `{cropped_dir}`")

            # Convenience button to re-organize (useful after code changes or on old folders)
            if cropped_count > 0 and cropped_dir:
                with st.expander("Organize crops (checks vs deposits)", expanded=False):
                    st.caption(
                        "Moves images into clean `checks/` and `deposits/` subfolders based on current classification rules."
                    )
                    if st.button("Re-organize now", key="reorg_crops_btn"):
                        try:
                            import subprocess
                            import sys
                            from pathlib import Path as _P

                            script = (
                                _P(__file__).parent.parent
                                / "Scripts"
                                / "reorganize_cropped_checks.py"
                            )
                            if script.exists():
                                result = subprocess.run(
                                    [sys.executable, str(script), "--crop-dir", cropped_dir],
                                    capture_output=True,
                                    text=True,
                                    timeout=60,
                                )
                                if result.returncode == 0:
                                    st.success("Crops re-organized successfully.")
                                    st.code(result.stdout or "Done.", language="text")
                                else:
                                    st.error("Re-organization had issues.")
                                    st.code(result.stderr or result.stdout, language="text")
                            else:
                                st.warning("Reorganizer script not found.")
                        except Exception as e:
                            st.error(f"Failed to run reorganizer: {e}")

        prompt_text = build_grok_vision_prompt(
            selected_client,
            pdf_name,
            saved_pdf_path=pdf_path or None,
            cropped_dir=cropped_dir or None,
            cropped_check_count=cropped_count or None,
        )
        st.markdown(
            "**Copy this prompt into Grok, then attach the PDF "
            "(and cropped check images if available):**"
        )
        # st.code adds a built-in copy-to-clipboard button on hover.
        st.code(prompt_text, language="markdown")

        st.download_button(
            "📥 Download Grok prompt (.txt)",
            prompt_text,
            file_name=f"grok_vision_prompt_{Path(pdf_name).stem}.txt",
            mime="text/plain",
            key="bank_stmt_grok_prompt_download",
        )
        st.caption(
            "Tip: Save Grok's CSV output as "
            f"`{Path(pdf_name).stem}_Transactions_With_Payees.csv` "
            "to drop straight into Process-Statement.ps1 and the Power Query model."
        )


def _render_grok_csv_paste_section(selected_client: str) -> None:
    """Native 'Paste Grok-extracted CSV' panel — manual fallback when Azure OCR is insufficient.

    Closes the manual save-as-CSV → PowerShell gap by letting Laura paste (or upload)
    the CSV Grok Vision emits and load it directly into the same review UI as Azure OCR.
    Stores the parsed DataFrame in the shared ``bank_stmt_txn_df`` session key so all
    downstream metrics, filters, the data_editor, the Download transactions CSV button,
    and "Link to revenue request" work identically to the Azure OCR path.
    """
    placeholder = (
        f"{GROK_CSV_FIELDS}\n"
        "2026-01-15,DEPOSIT ABC CO,ABC Co,1234.56,,Uncategorized,,1234.56,2026-01,High,No,\n"
        "2026-01-16,CHECK 2473,Acme Supply,-250.00,2473,Uncategorized,,-250.00,2026-01,High,No,\n"
        "...\n"
        "TOTALS: deposits=1234.56 withdrawals=250.00 checks=1 transactions=2"
    )

    with st.expander("📋 Option 2: Paste Grok-extracted CSV here", expanded=False):
        st.caption(
            "Already ran Grok Vision in another tab? Paste the CSV output below "
            "(or upload the saved CSV file) to load transactions directly into the "
            "review UI — no save-as-CSV / PowerShell step required."
        )

        pasted = st.text_area(
            "Paste the full CSV output from Grok here (including the TOTALS line at the bottom)",
            height=400,
            placeholder=placeholder,
            key="bank_stmt_grok_csv_paste",
        )

        uploaded_csv = st.file_uploader(
            "…or upload the saved Grok CSV file",
            type=["csv"],
            key="bank_stmt_grok_csv_upload",
        )

        if st.button(
            "Load / Parse Grok CSV",
            type="primary",
            key="bank_stmt_grok_csv_load",
        ):
            source_label: str | None = None
            df: pd.DataFrame | None = None
            grok_totals: dict | None = None
            try:
                if uploaded_csv is not None:
                    df, grok_totals = load_grok_vision_csv(uploaded_csv.getvalue())
                    source_label = uploaded_csv.name
                elif pasted and pasted.strip():
                    df, grok_totals = load_grok_vision_csv(pasted)
                    source_label = "pasted CSV"
                else:
                    st.warning("Paste CSV text or upload a CSV file before loading.")
            except ValueError as exc:
                st.error(f"Could not parse Grok CSV — {exc}")
                log_event(
                    LOGGER,
                    "bank_stmt_grok_csv_parse_error",
                    client=selected_client,
                    error=str(exc)[:200],
                )
            except Exception as exc:
                st.error(f"Unexpected error parsing Grok CSV: {exc}")
                log_event(
                    LOGGER,
                    "bank_stmt_grok_csv_unexpected_error",
                    client=selected_client,
                    error=str(exc)[:200],
                )

            if df is not None:
                if df.empty:
                    st.warning(
                        "No transactions found in the CSV. "
                        "Check that the Grok output contains data rows under the header."
                    )
                else:
                    # Auto-apply persistent payee rules before storing in session state.
                    rules_info: dict | None = None
                    try:
                        df, rules_info = apply_payee_rules(df, client_name=selected_client)
                        log_event(
                            LOGGER,
                            "bank_stmt_payee_rules_applied",
                            client=selected_client,
                            source="grok_paste",
                            rows_changed=int((rules_info or {}).get("rows_changed", 0)),
                            rules_used=int((rules_info or {}).get("rules_used", 0)),
                            rules_total=int((rules_info or {}).get("rules_total", 0)),
                        )
                    except Exception as exc:
                        log_event(LOGGER, "bank_stmt_payee_rules_error", error=str(exc)[:200])

                    st.session_state["bank_stmt_txn_df"] = df
                    st.session_state["bank_stmt_pipeline_status"] = "success"
                    st.session_state["bank_stmt_csv_path"] = None
                    st.session_state["bank_stmt_cropper_msg"] = None
                    st.session_state["bank_stmt_grok_totals"] = grok_totals
                    st.session_state["bank_stmt_rules_info"] = rules_info
                    # Reset any prior reconciliation flags so the new load is judged fresh.
                    st.session_state.pop("bank_stmt_needs_review", None)
                    st.session_state.pop("bank_stmt_reconciliation", None)
                    st.session_state.pop("bank_stmt_reconciliation_note", None)
                    totals_note = (
                        " · TOTALS line detected (will reconcile against detail rows)"
                        if grok_totals
                        else " · no TOTALS line in CSV"
                    )
                    rules_note = ""
                    if rules_info and rules_info.get("rows_changed", 0) > 0:
                        rules_note = (
                            f" · payee rules improved {rules_info['rows_changed']} row(s) "
                            f"via {rules_info['rules_used']} rule(s)"
                        )
                    st.session_state["bank_stmt_logs"] = (
                        f"[INFO] Loaded {len(df)} transactions from Grok CSV "
                        f"({source_label}){totals_note}{rules_note}."
                    )
                    metrics = transaction_summary_metrics(df)
                    st.success(
                        f"Loaded **{len(df)}** transactions from {source_label} · "
                        f"deposits ${metrics['deposits']:,.2f} · "
                        f"withdrawals ${metrics['withdrawals']:,.2f} · "
                        f"need review {int(metrics['needs_review'])}."
                    )
                    if rules_info and rules_info.get("rows_changed", 0) > 0:
                        st.success(
                            f"🧠 **{rules_info['rows_changed']} payee mapping(s) applied** "
                            f"via {rules_info['rules_used']} rule(s) from "
                            "`Data/payee_rules.csv`."
                        )
                    log_event(
                        LOGGER,
                        "bank_stmt_grok_csv_loaded",
                        client=selected_client,
                        rows=len(df),
                        source=source_label,
                        totals_detected=bool(grok_totals),
                    )
                    st.rerun()


def _render_payee_rules_controls(selected_client: str, txn_df: pd.DataFrame) -> None:
    """Payee rules engine UI — Apply button, Learn-this-mapping form, usage metric.

    Sits between the reconciliation banner and the `st.data_editor` on the Bank
    Statements page (v2.39). Keeps Laura's workflow self-improving: every time she
    teaches a clean Payee + Category for a messy description, the rule persists to
    `Data/payee_rules.csv` and gets reapplied on the next statement.
    """

    rules_info = st.session_state.get("bank_stmt_rules_info") or {}
    rules_path = resolve_payee_rules_path(create_if_missing=False)

    metric_col, btn_col, src_col = st.columns([1, 1, 2])
    with metric_col:
        st.metric(
            "Rules improved",
            f"{int(rules_info.get('rows_changed', 0))} rows",
            help=(
                f"{int(rules_info.get('rules_used', 0))} of "
                f"{int(rules_info.get('rules_total', 0))} rules matched on the last apply."
            ),
        )
    with btn_col:
        if st.button(
            "🔄 Apply Payee Rules",
            key="bank_stmt_apply_payee_rules",
            help=(
                "Re-run the persistent rules engine against the current transactions. "
                "Only blank Payee values and Uncategorized rows are touched — your "
                "manual edits are preserved."
            ),
        ):
            try:
                updated, info = apply_payee_rules(txn_df, client_name=selected_client)
                st.session_state["bank_stmt_txn_df"] = updated
                st.session_state["bank_stmt_rules_info"] = info
                log_event(
                    LOGGER,
                    "bank_stmt_payee_rules_reapplied",
                    client=selected_client,
                    rows_changed=int(info.get("rows_changed", 0)),
                    rules_used=int(info.get("rules_used", 0)),
                )
                if info.get("rows_changed", 0) > 0:
                    st.success(
                        f"🧠 {info['rows_changed']} row(s) updated via "
                        f"{info['rules_used']} rule(s)."
                    )
                elif info.get("rules_total", 0) == 0:
                    st.info(
                        "No rules loaded yet. Use **💡 Learn this mapping** below to "
                        "teach the system its first rule."
                    )
                else:
                    st.info("No new matches — everything already looks clean.")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not apply payee rules: {exc}")
                log_event(LOGGER, "bank_stmt_payee_rules_error", error=str(exc)[:200])
    with src_col:
        if rules_path and Path(rules_path).is_file():
            st.caption(f"Rules file: `{rules_path}`")
        else:
            st.caption(
                "Rules file not found — the **Learn** form below will create "
                "`Data/payee_rules.csv` on first save."
            )

    with st.expander("💡 Learn this mapping (teach a new rule)", expanded=False):
        if txn_df is None or txn_df.empty:
            st.info("Load transactions first, then return here to teach a rule.")
        else:
            _render_learn_mapping_form(selected_client, txn_df)

    _render_rules_library_expander(selected_client)


def _render_learn_mapping_form(selected_client: str, txn_df: pd.DataFrame) -> None:
    """Smart-default + reactive-preview Learn-this-mapping form (v2.40).

    The pattern field lives OUTSIDE st.form so the "would affect X rows" preview
    can re-render on every keystroke. Submit + other inputs stay inside the form
    so we don't trigger noisy reruns on each character.
    """

    display_descriptions = txn_df["Description"].astype(str).tolist()
    labels = [
        f"#{i:>3} · {desc[:80]}" + (" …" if len(desc) > 80 else "")
        for i, desc in enumerate(display_descriptions)
    ]
    choice = st.selectbox(
        "Pick a transaction to learn from",
        options=list(range(len(labels))),
        format_func=lambda i: labels[i] if 0 <= i < len(labels) else f"#{i}",
        key="bank_stmt_learn_row_pick",
    )
    if choice is None or choice < 0 or choice >= len(txn_df):
        return

    picked_row = txn_df.iloc[int(choice)]
    picked_desc = str(picked_row.get("Description", "")).strip()
    picked_payee = str(picked_row.get("Payee", "")).strip()
    picked_cat = str(picked_row.get("Category", "")).strip()
    st.caption(
        f"Selected: **{picked_desc[:120]}** · "
        f"current Payee: `{picked_payee or '—'}` · "
        f"current Category: `{picked_cat or '—'}`"
    )

    # Smart default pattern from the selected row (strip noise prefixes, store #s,
    # location codes). Recomputed only when the picked row changes so we don't
    # overwrite Laura's edits on every rerun.
    smart_default = suggest_payee_pattern(picked_desc)
    last_idx_key = "bank_stmt_learn_last_row_idx"
    if st.session_state.get(last_idx_key) != int(choice):
        st.session_state["bank_stmt_learn_pattern"] = smart_default
        st.session_state[last_idx_key] = int(choice)

    # Pattern input OUTSIDE the form so Streamlit reruns the live preview as Laura types.
    pattern_input = st.text_input(
        "Match pattern (case-insensitive substring; prefix with `re:` for regex)",
        help=(
            "Smart-suggested from the selected description. Keep it short and unique "
            "to the merchant — e.g. `WAL-MART` (not the full description). The rule "
            "matches every description that contains this substring."
        ),
        key="bank_stmt_learn_pattern",
    )

    # Live impact preview — counts how many rows on THIS statement the pattern would touch.
    if pattern_input and pattern_input.strip():
        match_count = count_pattern_matches(txn_df, pattern_input, client_name=selected_client)
        if match_count == 0:
            st.caption(
                f"⚠️ Pattern `{pattern_input.strip()}` matches **0 rows** on this "
                "statement — double-check the spelling before saving."
            )
        elif match_count > 20:
            st.caption(
                f"⚠️ Pattern `{pattern_input.strip()}` would affect **{match_count} rows** — "
                "that's broader than typical merchant rules. Consider tightening the pattern."
            )
        else:
            st.caption(
                f"✅ Pattern `{pattern_input.strip()}` would affect "
                f"**{match_count} row(s)** on this statement."
            )
        log_event(
            LOGGER,
            "bank_stmt_payee_rule_preview",
            client=selected_client,
            pattern=pattern_input.strip()[:80],
            match_count=int(match_count),
        )

    with st.form("bank_stmt_learn_form", clear_on_submit=False):
        clean_input = st.text_input(
            "Clean Payee",
            value=picked_payee or "",
            key="bank_stmt_learn_clean_payee",
        )
        category_input = st.text_input(
            "Suggested Category (optional)",
            value=(picked_cat if picked_cat.lower() not in ("", "uncategorized") else ""),
            key="bank_stmt_learn_category",
        )
        scope_specific = st.checkbox(
            f"Apply only to **{selected_client}** (client-specific override)",
            value=False,
            key="bank_stmt_learn_scope_specific",
        )
        notes_input = st.text_input(
            "Notes (optional)",
            value="",
            key="bank_stmt_learn_notes",
        )
        submitted = st.form_submit_button("💾 Save mapping", type="primary")

    if not submitted:
        return

    pattern_value = st.session_state.get("bank_stmt_learn_pattern", "")
    if not pattern_value or not pattern_value.strip():
        st.warning("Pattern cannot be blank.")
        return
    if not clean_input.strip():
        st.warning("Clean Payee cannot be blank.")
        return
    override = selected_client if scope_specific else ""
    # Snapshot the picked row's Payee BEFORE save so we can show a clean before→after diff.
    before_payee = picked_payee or "(blank)"
    try:
        ok, saved_path = upsert_payee_rule(
            pattern=pattern_value,
            clean_payee=clean_input,
            suggested_category=category_input,
            client_override=override,
            notes=notes_input,
        )
    except Exception as exc:
        st.error(f"Could not save rule: {exc}")
        log_event(LOGGER, "bank_stmt_payee_rule_save_error", error=str(exc)[:200])
        return

    if not ok:
        st.error(
            "Could not write to `Data/payee_rules.csv`. Check folder "
            "permissions or set the `SLAM_PAYEE_RULES_PATH` environment variable."
        )
        return

    log_event(
        LOGGER,
        "bank_stmt_payee_rule_learned",
        client=selected_client,
        pattern=pattern_value.strip()[:80],
        clean_payee=clean_input.strip()[:80],
        client_specific=bool(override),
    )

    rows_changed = 0
    after_payee = before_payee
    try:
        updated, info = apply_payee_rules(
            st.session_state.get("bank_stmt_txn_df"),
            client_name=selected_client,
        )
        st.session_state["bank_stmt_txn_df"] = updated
        st.session_state["bank_stmt_rules_info"] = info
        rows_changed = int((info or {}).get("rows_changed", 0))
        if updated is not None and int(choice) < len(updated):
            after_payee = str(updated.iloc[int(choice)].get("Payee", "")).strip() or "(blank)"
    except Exception as exc:
        log_event(LOGGER, "bank_stmt_payee_rules_error", error=str(exc)[:200])

    st.success(
        f"Saved rule **{pattern_value.strip()} → {clean_input.strip()}** to "
        f"`{saved_path}`. Reapplied across the current statement."
    )
    if before_payee != after_payee:
        st.caption(
            f"Selected row Payee: `{before_payee}` → `{after_payee}` "
            f"({rows_changed} row(s) updated in this run)."
        )
    elif rows_changed == 0:
        st.warning(
            "Rule saved but matched 0 rows on this statement after apply — your "
            "manual edits may have prevented overwrite. The rule will still apply "
            "to future statements with blank/default Payee values."
        )
    st.rerun()


def _render_rules_library_expander(selected_client: str) -> None:
    """Read-only Rules Library quick view — top 25 rules with scope + sort filters."""

    with st.expander("📚 Rules Library", expanded=False):
        try:
            rules_df = load_payee_rules()
        except Exception as exc:
            st.warning(f"Could not load rules library: {exc}")
            return

        if rules_df is None or rules_df.empty:
            st.info(
                "No rules saved yet. Use **💡 Learn this mapping** above to teach "
                "the first rule — it will appear here once saved."
            )
            return

        ctl_col1, ctl_col2 = st.columns([1, 1])
        with ctl_col1:
            scope = st.radio(
                "Scope",
                options=["All", "Global only", f"{selected_client} only"],
                index=0,
                horizontal=True,
                key="bank_stmt_rules_library_scope",
            )
        with ctl_col2:
            sort_by = st.selectbox(
                "Sort",
                options=["Recently used", "Most specific", "Alphabetical"],
                index=0,
                key="bank_stmt_rules_library_sort",
            )

        # Normalize scope label for the helper ("<client> only" → "Client only").
        scope_norm = scope
        if scope.endswith(" only") and not scope.startswith("Global"):
            scope_norm = "Client only"

        view, summary = rules_library_summary(
            rules_df,
            client_name=selected_client,
            scope=scope_norm,
            sort_by=sort_by,
            limit=25,
        )

        st.caption(
            f"**{summary['total']}** total rule(s) · "
            f"**{summary['client_specific']}** client-specific · "
            f"**{summary['used_30d']}** used in the last 30 days"
        )

        if view.empty:
            st.info("No rules match the current filters.")
        else:
            st.dataframe(view, width="stretch", hide_index=True)

        st.caption(
            "To edit or delete a rule, open `Data/payee_rules.csv` in Excel. "
            "Changes take effect on the next **Apply Payee Rules** click."
        )

        # Lightweight audit hook — gated by session state so we log once per filter change.
        snapshot = f"{scope_norm}|{sort_by}|{summary['total']}"
        if st.session_state.get("bank_stmt_rules_library_last_snapshot") != snapshot:
            st.session_state["bank_stmt_rules_library_last_snapshot"] = snapshot
            log_event(
                LOGGER,
                "bank_stmt_payee_rules_library_viewed",
                client=selected_client,
                scope=scope_norm,
                sort_by=sort_by,
                rule_count=int(summary["total"]),
            )


def _render_statement_pivot_section(selected_client: str, txn_df: pd.DataFrame) -> None:
    """📊 Statement Summary — in-app pivot view (v2.40, first step toward Power Query independence).

    Aggregates the current statement by Category or Payee across YearMonth columns using
    pandas.pivot_table. Defaults to **Category × YearMonth, sum of SignedAmount** which is
    the most common bookkeeping view. Quick buttons set sensible presets; the full pivot CSV
    is exportable separately. The existing Download transactions CSV button (Power Query
    safety net) is preserved unchanged below this section.
    """

    st.subheader("📊 Statement Summary")
    st.caption(
        "In-app pivot view — group by Category or Payee across YearMonth. "
        "The detailed CSV download below remains available for Power Query."
    )

    # Seed defaults BEFORE any widget renders so the preset buttons + widgets share state
    # without tripping Streamlit's "value/index AND key already in session_state" rules.
    st.session_state.setdefault("bank_stmt_pivot_group_by", "Category")
    st.session_state.setdefault("bank_stmt_pivot_kind", "sum")
    st.session_state.setdefault("bank_stmt_pivot_uncategorized", False)

    # Preset buttons mutate session state BEFORE the corresponding widgets render below.
    preset_col1, preset_col2, preset_col3, preset_col4 = st.columns(4)
    with preset_col1:
        if st.button("📁 By Category", key="bank_stmt_pivot_by_cat"):
            st.session_state["bank_stmt_pivot_group_by"] = "Category"
            st.session_state["bank_stmt_pivot_uncategorized"] = False
            st.session_state["bank_stmt_pivot_kind"] = "sum"
    with preset_col2:
        if st.button("👥 By Payee", key="bank_stmt_pivot_by_payee"):
            st.session_state["bank_stmt_pivot_group_by"] = "Payee"
            st.session_state["bank_stmt_pivot_uncategorized"] = False
            st.session_state["bank_stmt_pivot_kind"] = "sum"
    with preset_col3:
        if st.button("❓ Uncategorized Only", key="bank_stmt_pivot_uncat"):
            st.session_state["bank_stmt_pivot_group_by"] = "Payee"
            st.session_state["bank_stmt_pivot_uncategorized"] = True
            st.session_state["bank_stmt_pivot_kind"] = "sum"
    with preset_col4:
        export_placeholder = st.empty()

    kind_labels = {"sum": "Sum of SignedAmount", "count": "Count of transactions"}

    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([1, 1, 1])
    with ctrl_col1:
        group_by = st.radio(
            "Group by",
            options=list(PIVOT_GROUP_BY_OPTIONS),
            horizontal=True,
            key="bank_stmt_pivot_group_by",
        )
    with ctrl_col2:
        kind_choice = st.selectbox(
            "Values",
            options=list(kind_labels.keys()),
            format_func=lambda k: kind_labels[k],
            key="bank_stmt_pivot_kind",
        )
    with ctrl_col3:
        uncategorized_only = st.checkbox(
            "Uncategorized only",
            help="Filter to rows where Category is blank or 'Uncategorized'.",
            key="bank_stmt_pivot_uncategorized",
        )

    try:
        pivot = build_statement_pivot(
            txn_df,
            group_by=group_by,
            value_kind=kind_choice,
            uncategorized_only=uncategorized_only,
        )
    except Exception as exc:
        st.warning(f"Could not build pivot summary: {exc}")
        return

    if pivot is None or pivot.empty:
        if uncategorized_only:
            st.info(
                "✅ No Uncategorized transactions — every row has a category. "
                "Switch off the filter to see the full pivot."
            )
        else:
            st.info("No data to pivot. Load a statement and apply rules first.")
        return

    # Format the display copy: dollars get $ + 2 decimals; counts stay as integers.
    display = pivot.copy()
    if kind_choice == "sum":
        formatter = {col: "${:,.2f}" for col in display.columns}
        st.dataframe(display.style.format(formatter), width="stretch")
    else:
        st.dataframe(display, width="stretch")

    st.caption(
        f"{len(pivot)} row(s) · {len(pivot.columns) - 1} month column(s) + Total · "
        f"sorted by {'absolute total' if kind_choice == 'sum' else 'transaction count'} (descending)."
    )

    # Export — pivot-only CSV; the full 12-column CSV download remains below.
    pivot_buf = io.StringIO()
    pivot.to_csv(pivot_buf)
    file_safe_client = selected_client.replace(" ", "_")
    file_safe_group = group_by.lower()
    suffix = "_uncategorized" if uncategorized_only else ""
    with export_placeholder.container():
        st.download_button(
            "📥 Export Pivot CSV",
            pivot_buf.getvalue(),
            file_name=f"{file_safe_client}_pivot_{file_safe_group}_{kind_choice}{suffix}.csv",
            mime="text/csv",
            key="bank_stmt_pivot_export",
            help="Pivot summary only — full transaction CSV stays available below.",
        )

    # Audit hook — once per snapshot change.
    snapshot = f"{group_by}|{kind_choice}|{uncategorized_only}|{len(pivot)}"
    if st.session_state.get("bank_stmt_pivot_last_snapshot") != snapshot:
        st.session_state["bank_stmt_pivot_last_snapshot"] = snapshot
        log_event(
            LOGGER,
            "bank_stmt_pivot_viewed",
            client=selected_client,
            group_by=group_by,
            value_kind=kind_choice,
            uncategorized_only=bool(uncategorized_only),
            rows=int(len(pivot)),
        )


_MODE_SUFFIX_MAP = {
    "azure_ocr": " via Azure Document Intelligence",
}


def _mode_suffix(mode: str | None) -> str:
    """Human-friendly suffix for the success/partial banner ("via …")."""

    return _MODE_SUFFIX_MAP.get(str(mode or ""), "")


def bank_statements_page(clients_df: pd.DataFrame, req_df: pd.DataFrame) -> None:
    """Core Workstream #2 MVP — upload PDF, Azure Document Intelligence OCR, review, mark received."""
    st.header("🏦 Bank Statements")
    st.markdown(
        '<p class="slam-subtle">Upload a client bank statement PDF, run <strong>Process Statement</strong> '
        "(Azure Document Intelligence — the sole OCR engine), review transactions, then mark the "
        "matching revenue request as received.</p>",
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

    default_client = st.session_state.get("bank_stmt_client")
    if default_client not in client_names:
        default_client = client_names[0]

    col_client, col_hint = st.columns([2, 1])
    with col_client:
        selected_client = st.selectbox(
            "Client",
            client_names,
            index=client_names.index(default_client),
            key="bank_stmt_client_select",
        )
    st.session_state["bank_stmt_client"] = selected_client
    with col_hint:
        open_requests = req_df[
            (req_df["business_name"] == selected_client)
            & (req_df["status"].isin(["Pending", "Received"]))
            & (~req_df["bank_statement_received"].fillna(False))
        ]
        st.metric("Open requests (bank stmt missing)", len(open_requests))

    uploaded = st.file_uploader(
        "Bank statement PDF(s)",
        type=["pdf"],
        accept_multiple_files=True,
        key="bank_stmt_pdf_upload",
    )

    ocr_status = azure_ocr_status()

    hybrid = hybrid_cv_status()
    check_leg = hybrid.get("check_leg") or "document_intelligence"
    check_leg_label = (
        "Content Understanding (Foundry)"
        if check_leg == "content_understanding"
        else "Document Intelligence (fallback)"
    )
    st.caption(
        "**Register/tabular pages**: Azure Document Intelligence `prebuilt-bankStatement.us`. "
        "**Check images**: geometry cropper (OpenCV only, checks + deposit slips) → "
        "`prebuilt-check.us` on each PNG "
        f"via **{check_leg_label}** (full-page fallback if cropping finds nothing)."
    )
    if not ocr_status.get("configured"):
        st.warning(
            "Azure OCR is not configured. **Process Statement** will not run until you set "
            "`AZURE_OCR_FUNCTION_URL` and `AZURE_OCR_FUNCTION_KEY`, or "
            "`AZURE_DI_ENDPOINT` and `AZURE_DI_KEY`, in repo-root `.env` (loaded automatically)."
        )

    if st.button("Process Statement", type="primary", key="bank_stmt_process"):
        if not uploaded:
            st.warning("Upload at least one PDF before processing.")
        else:
            with st.spinner(
                "Azure OCR + check cropper (register pages, then crop + read checks; "
                "may take 1–3 min)…"
            ):
                _run_bank_statement_azure_process(
                    uploaded=uploaded,
                    selected_client=selected_client,
                    ocr_status=ocr_status,
                )

    pipeline_status = st.session_state.get("bank_stmt_pipeline_status")
    if st.session_state.get("bank_stmt_cropper_msg") and pipeline_status == "partial":
        st.caption(st.session_state["bank_stmt_cropper_msg"])

    if st.session_state.get("bank_stmt_logs"):
        with st.expander("Processing log", expanded=pipeline_status in ("error", None)):
            st.code(st.session_state["bank_stmt_logs"], language=None)
    smoke_files = st.session_state.get("bank_stmt_smoke_evidence_files") or []
    if smoke_files:
        st.caption(
            "Gate A3: validation evidence emitted to App Service logs for "
            + ", ".join(f"`{n}`" for n in smoke_files)
            + ". Run `Collect-GateA3Evidence.ps1 -Both` after both canonical PDFs are processed."
        )

    txn_df = st.session_state.get("bank_stmt_txn_df")
    ocr_meta = st.session_state.get("bank_stmt_azure_ocr_meta") or {}
    if isinstance(ocr_meta, dict) and (
        ocr_meta.get("register_transaction_count") is not None
        or ocr_meta.get("check_transaction_count") is not None
    ):
        reg_n = int(ocr_meta.get("register_transaction_count") or 0)
        chk_n = int(ocr_meta.get("check_transaction_count") or 0)
        st.info(
            f"Azure split: **{reg_n}** register row(s) from tabular pages + "
            f"**{chk_n}** withdrawal row(s) built from check images "
            f"(combined in the table below)."
        )

    if txn_df is not None and isinstance(txn_df, pd.DataFrame) and not txn_df.empty:
        metrics = transaction_summary_metrics(txn_df)
        st.markdown(
            f"**{metrics['count']}** transactions · deposits **${metrics['deposits']:,.2f}** · "
            f"withdrawals **${metrics['withdrawals']:,.2f}** · "
            f"**{int(metrics['needs_review'])}** need review"
        )

    _render_azure_check_summary()

    if "bank_stmt_raw_text" in st.session_state:
        raw_export = st.session_state.get("bank_stmt_raw_text") or ""
        if not raw_export.strip():
            raw_export = (
                "(No extractable text in PDF — likely a scanned/image statement. "
                "Use Prepare for Grok Vision below; Azure Document Intelligence is the only OCR engine.)"
            )
        st.download_button(
            "Export Raw Text",
            raw_export,
            file_name="bank_statement_raw_text.txt",
            mime="text/plain",
            key="bank_stmt_export_raw_text",
        )

    if txn_df is not None and isinstance(txn_df, pd.DataFrame) and not txn_df.empty:
        metrics = transaction_summary_metrics(txn_df)
        review_n = int(metrics["needs_review"])

        if st.session_state.get("bank_stmt_csv_path"):
            st.caption(f"Output CSV: `{st.session_state['bank_stmt_csv_path']}`")

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
            ]
            if c in txn_df.columns
        ]
        view_df = txn_df[display_cols] if display_cols else txn_df

        recon_ref = reconciliation_reference_totals(
            st.session_state.get("bank_stmt_grok_totals"),
            st.session_state.get("bank_stmt_statement_summary")
            or (ocr_meta.get("statement_summary") if isinstance(ocr_meta, dict) else None),
        )
        recon = reconcile_statement_totals(txn_df, recon_ref)
        st.session_state["bank_stmt_reconciliation"] = recon
        if recon_ref:
            if recon["status"] == "match":
                st.success(f"✅ **Totals match source statement.** {recon['message']}")
            elif recon["status"] == "mismatch":
                st.session_state["bank_stmt_needs_review"] = True
                st.error(f"⚠️ **Reconciliation mismatch — review required.** {recon['message']}")
                with st.expander("Reconciliation details", expanded=True):
                    rows = []
                    reported = recon.get("reported") or {}
                    computed = recon.get("computed") or {}
                    differences = recon.get("differences") or {}
                    for key in ("deposits", "withdrawals", "checks", "transactions"):
                        rep = reported.get(key)
                        comp = computed.get(key)
                        if rep is None and comp is None:
                            continue
                        is_amount = key in ("deposits", "withdrawals")
                        diff_info = differences.get(key)
                        if rep is None:
                            rep_display = "—"
                        elif is_amount:
                            rep_display = f"${float(rep):,.2f}"
                        else:
                            rep_display = f"{int(rep)}"
                        if comp is None:
                            comp_display = "—"
                        elif is_amount:
                            comp_display = f"${float(comp):,.2f}"
                        else:
                            comp_display = f"{int(comp)}"
                        if diff_info is None:
                            diff_display = "✅ match"
                        elif is_amount:
                            diff_display = f"⚠️ off by ${diff_info['diff']:+,.2f}"
                        else:
                            diff_display = f"⚠️ off by {diff_info['diff']:+d}"
                        rows.append(
                            {
                                "Field": key.title(),
                                "Source (statement summary)": rep_display,
                                "Detailed rows (computed)": comp_display,
                                "Status": diff_display,
                            }
                        )
                    if rows:
                        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
                    guidance = recon.get("human_review_guidance") or (
                        "Compare detailed rows to the bank statement before proceeding."
                    )
                    st.info(guidance)
                    review_note = st.text_area(
                        "Reconciliation review note (optional — for Laura/Stef handoff)",
                        value=st.session_state.get("bank_stmt_reconciliation_note", ""),
                        key="bank_stmt_reconciliation_note_input",
                        placeholder="e.g. Accepted $273.45 withdrawal gap after manual check of imaging rows.",
                        height=80,
                    )
                    if review_note != st.session_state.get("bank_stmt_reconciliation_note", ""):
                        st.session_state["bank_stmt_reconciliation_note"] = review_note
                    st.caption(
                        "The whole statement is flagged for review. Re-check the detailed rows "
                        "against the bank statement (or re-run Grok) before proceeding."
                    )
                log_event(
                    LOGGER,
                    "bank_stmt_reconciliation_mismatch",
                    client=selected_client,
                    differences=", ".join(sorted((recon.get("differences") or {}).keys())),
                )
        else:
            st.info(
                "ℹ️ No source TOTALS line or Statement Summary available — reconciliation "
                "cross-check skipped (Azure run without summary metadata, or older Grok CSV)."
            )

        st.subheader("Transactions (review & edit)")
        _render_payee_rules_controls(selected_client, txn_df)

        conf_filter = st.radio(
            "Transaction filter",
            ["Show All", "Low/Medium Confidence Only"],
            horizontal=True,
            key="bank_stmt_conf_filter",
        )
        filtered_df = filter_transactions_by_confidence(view_df, confidence_level=conf_filter)
        if conf_filter == "Low/Medium Confidence Only" and filtered_df.empty:
            st.info("No Low or Medium confidence rows — all transactions are High confidence.")
        elif review_n > 0:
            st.caption(
                f"**{review_n}** item(s) need review (Confidence is not High). "
                "Non-High rows are highlighted in amber."
            )
            st.dataframe(
                style_low_confidence_rows(filtered_df),
                width="stretch",
                hide_index=True,
            )
            st.caption("Edit values:")
        st.data_editor(
            filtered_df,
            num_rows="fixed",
            width="stretch",
            hide_index=True,
            key="bank_stmt_txn_editor",
        )

        _render_statement_pivot_section(selected_client, txn_df)

        st.caption(
            "💾 **Power Query safety net**: download the full 12-column CSV below to keep "
            "the existing Process-Statement.ps1 / Excel workflow available."
        )
        buf = io.StringIO()
        txn_df.to_csv(buf, index=False)
        st.download_button(
            "Download transactions CSV",
            buf.getvalue(),
            file_name=f"{selected_client.replace(' ', '_')}_transactions.csv",
            mime="text/csv",
        )

    elif txn_df is not None and isinstance(txn_df, pd.DataFrame) and txn_df.empty:
        st.warning(ZERO_TRANSACTIONS_MSG)
        st.info(GROK_VISION_HINT)
        if st.session_state.get("bank_stmt_csv_path"):
            st.caption(f"Output CSV (header only): `{st.session_state['bank_stmt_csv_path']}`")

    _render_grok_vision_section(selected_client)
    _render_grok_csv_paste_section(selected_client)

    st.divider()
    st.subheader("Link to revenue request")

    if open_requests.empty:
        st.info(
            f"No Pending/Received requests for **{selected_client}** with bank statement still missing. "
            "You can still process PDFs for review; use Revenue Requests to update other clients."
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
        choice = st.selectbox("Revenue request to update", options, key="bank_stmt_request_pick")
        request_id = id_map[choice]

        if st.button("Mark as Received", type="primary", key="bank_stmt_mark_received"):
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
                        LOGGER,
                        "bank_stmt_mark_received",
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
                log_event(LOGGER, "bank_stmt_mark_failed", error=str(exc)[:200])


def _run_bank_statement_azure_process(
    *,
    uploaded,
    selected_client: str,
    ocr_status: dict,
) -> None:
    all_logs: list[str] = []
    last_df: pd.DataFrame | None = None
    last_csv: Path | None = None
    last_status = "error"
    cropper_msg: str | None = None
    last_meta: dict = {}
    last_pdf_name: str = ""
    last_grok_totals: dict | None = None
    smoke_evidence_files: list[str] = []

    # Azure Document Intelligence (via Function or direct DI) is the *only* OCR path.
    # No local image processing, no EasyOCR, no pdfplumber fallback for bank statements.
    if not ocr_status.get("configured"):
        st.error(
            "Azure OCR is not configured. This is the only supported workflow for bank statements. "
            "Set `AZURE_OCR_FUNCTION_URL` and `AZURE_OCR_FUNCTION_KEY` (App Settings or .env) and reload."
        )
        log_event(LOGGER, "bank_stmt_azure_not_configured_block", client=selected_client)
        st.stop()

    run_mode = "azure_ocr"

    for up in uploaded:
        all_logs.append(f"========== {up.name} ==========")
        log_event(
            LOGGER,
            "bank_stmt_process_start",
            client=selected_client,
            file=up.name,
            mode=run_mode,
        )

        df_ocr, logs_ocr, meta_ocr = run_azure_ocr_pipeline(
            up.getvalue(),
            up.name,
            selected_client,
            LOGGER,
        )
        all_logs.extend(logs_ocr)
        df = df_ocr
        meta = {
            "status": meta_ocr.get("status", "partial"),
            "csv_path": meta_ocr.get("csv_path"),
            "pdf_path": meta_ocr.get("pdf_path"),
            "cropper_skipped": meta_ocr.get("cropper_skipped", True),
            "cropper_user_message": meta_ocr.get("cropper_user_message"),
            "raw_text": meta_ocr.get("raw_text", ""),
            "text_layer_found": bool(meta_ocr.get("text_layer_found", False)),
            "cropped_dir": meta_ocr.get("cropped_dir"),
            "cropped_check_count": int(
                meta_ocr.get("azure_check_count") or meta_ocr.get("cropped_check_count") or 0
            ),
            "azure_check_count": int(meta_ocr.get("azure_check_count") or 0),
            "azure_check_payees_merged": int(meta_ocr.get("azure_check_payees_merged") or 0),
            "transaction_count": (int(len(df)) if df is not None and not df.empty else 0),
            "grok_totals": meta_ocr.get("grok_totals"),
            "statement_summary": meta_ocr.get("statement_summary"),
            "azure_ocr_meta": meta_ocr,
        }
        if meta_ocr.get("grok_totals"):
            last_grok_totals = meta_ocr["grok_totals"]
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            all_logs.append(
                "[WARN] Azure Document Intelligence returned no transactions for this file — "
                "use Prepare for Grok Vision below if the PDF is scanned."
            )

        file_rules_info: dict | None = None
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            try:
                df, file_rules_info = apply_payee_rules(df, client_name=selected_client)
                if file_rules_info and file_rules_info.get("rows_changed", 0) > 0:
                    all_logs.append(
                        f"[INFO] Payee rules engine ({up.name}): "
                        f"{file_rules_info['rows_changed']} row(s) via "
                        f"{file_rules_info['rules_used']} rule(s)."
                    )
            except Exception as exc:
                all_logs.append(f"[WARN] Payee rules skipped for {up.name}: {exc}")

        ocr_meta_full = meta_ocr if isinstance(meta_ocr, dict) else {}
        if emit_gate_a3_smoke_evidence(
            up.name,
            df,
            ocr_meta_full,
            logs_ocr,
            LOGGER,
            rules_info=file_rules_info,
            client_name=selected_client,
        ):
            smoke_evidence_files.append(up.name)
            all_logs.append("[INFO] Validation evidence emitted to logs (Gate A3 collector).")

        last_meta = meta
        last_pdf_name = up.name
        if meta.get("cropper_user_message"):
            cropper_msg = meta["cropper_user_message"]
        if df is not None:
            last_df = df
            last_csv = meta.get("csv_path")
            last_status = meta.get("status", "success")
        elif last_status != "partial":
            last_status = "error"
    rules_info: dict | None = None
    if last_df is not None and not last_df.empty:
        log_event(
            LOGGER,
            "bank_stmt_payee_rules_applied",
            client=selected_client,
            source="azure_ocr",
            files=len(uploaded),
        )

    st.session_state["bank_stmt_smoke_evidence_files"] = smoke_evidence_files
    st.session_state["bank_stmt_logs"] = format_processing_log(all_logs)
    st.session_state["bank_stmt_txn_df"] = last_df
    st.session_state["bank_stmt_csv_path"] = str(last_csv) if last_csv else None
    st.session_state["bank_stmt_pipeline_status"] = last_status
    st.session_state["bank_stmt_cropper_msg"] = cropper_msg
    st.session_state["bank_stmt_raw_text"] = last_meta.get("raw_text", "")
    st.session_state["bank_stmt_pdf_name"] = last_pdf_name
    st.session_state["bank_stmt_pdf_path"] = (
        str(last_meta.get("pdf_path")) if last_meta.get("pdf_path") else None
    )
    st.session_state["bank_stmt_cropped_dir"] = (
        str(last_meta.get("cropped_dir")) if last_meta.get("cropped_dir") else None
    )
    st.session_state["bank_stmt_cropped_count"] = int(last_meta.get("cropped_check_count") or 0)
    # New breakdown for checks vs deposit slips (available on paid-tier cropping runs)
    st.session_state["bank_stmt_cropped_checks"] = int(last_meta.get("cropped_likely_checks") or 0)
    st.session_state["bank_stmt_cropped_deposits"] = int(
        last_meta.get("cropped_likely_deposits") or 0
    )
    st.session_state["bank_stmt_text_layer"] = bool(last_meta.get("text_layer_found", False))
    st.session_state["bank_stmt_rules_info"] = rules_info
    # Azure OCR may return grok_totals for reconciliation; Grok CSV paste supplies its own.
    st.session_state["bank_stmt_grok_totals"] = last_grok_totals
    st.session_state["bank_stmt_statement_summary"] = last_meta.get("statement_summary") or (
        last_meta.get("azure_ocr_meta") or {}
    ).get("statement_summary")
    st.session_state["bank_stmt_last_mode"] = run_mode
    st.session_state["bank_stmt_azure_ocr_meta"] = (
        last_meta.get("azure_ocr_meta") if isinstance(last_meta, dict) else None
    )
    st.session_state["bank_stmt_azure_check_count"] = int(last_meta.get("azure_check_count") or 0)
    _ocr_full = last_meta.get("azure_ocr_meta")
    _checks_list = last_meta.get("azure_checks")
    if not isinstance(_checks_list, list) and isinstance(_ocr_full, dict):
        _checks_list = _ocr_full.get("azure_checks")
    st.session_state["bank_stmt_azure_checks"] = (
        _checks_list if isinstance(_checks_list, list) else []
    )
    st.session_state.pop("bank_stmt_needs_review", None)
    st.session_state.pop("bank_stmt_reconciliation", None)
    st.session_state.pop("bank_stmt_reconciliation_note", None)
    if last_df is not None:
        row_count = len(last_df)
        if row_count == 0:
            st.warning(ZERO_TRANSACTIONS_MSG)
            st.info(GROK_VISION_HINT)
        elif last_status == "partial":
            via = _mode_suffix(st.session_state.get("bank_stmt_last_mode"))
            st.warning(
                f"Partial success: {row_count} transactions extracted{via} from "
                f"{len(uploaded)} file(s). See processing log for details."
            )
        else:
            via = _mode_suffix(st.session_state.get("bank_stmt_last_mode"))
            st.success(
                f"Success: extracted {row_count} transactions{via} from {len(uploaded)} file(s)."
            )
        if last_csv:
            st.info(f"Output CSV: `{last_csv}`")
        if cropper_msg:
            st.info(cropper_msg)
        if rules_info and rules_info.get("rows_changed", 0) > 0:
            st.success(
                f"🧠 **{rules_info['rows_changed']} payee mapping(s) applied** "
                f"via {rules_info['rules_used']} rule(s) "
                f"(of {rules_info['rules_total']} loaded from "
                "`Data/payee_rules.csv`)."
            )
        log_event(
            LOGGER,
            "bank_stmt_process_done",
            client=selected_client,
            rows=len(last_df),
            status=last_status,
        )
    else:
        st.error(
            "Processing failed — no transaction CSV was produced. "
            "See the processing log below for details."
        )
        log_event(LOGGER, "bank_stmt_process_failed", client=selected_client)


def _render_azure_check_summary() -> None:
    """Show Azure ``prebuilt-check.us`` results (structured fields, not local PNG crops)."""

    count = int(st.session_state.get("bank_stmt_azure_check_count") or 0)
    checks = st.session_state.get("bank_stmt_azure_checks") or []
    if count <= 0 and not checks:
        return

    check_meta = {}
    ocr_meta = st.session_state.get("bank_stmt_azure_ocr_meta") or {}
    if isinstance(ocr_meta, dict):
        check_meta = ocr_meta.get("azure_check_meta") or {}

    pages = check_meta.get("pages_analyzed") or "—"
    duration = check_meta.get("duration_sec")
    dur_note = f" in {duration}s" if duration is not None else ""

    engine = check_meta.get("engine") or "azure_document_intelligence"
    engine_label = (
        "Content Understanding (Foundry)"
        if engine == "azure_content_understanding"
        else "Document Intelligence (cropped PNGs)"
        if check_meta.get("source") == "cropped_pngs"
        else "Document Intelligence"
    )
    cropped_n = int(st.session_state.get("bank_stmt_cropped_count") or 0)
    crop_dir = st.session_state.get("bank_stmt_cropped_dir")
    st.subheader("Azure check analysis")
    crop_note = (
        f" from **{cropped_n}** geometry-cropped PNG(s) in `{crop_dir}`"
        if cropped_n > 0 and crop_dir
        else f" on imaging pages **{pages}**"
    )
    st.caption(
        f"**{count}** check(s) via `prebuilt-check.us` ({engine_label}){crop_note}{dur_note}."
    )
    if checks:
        rows = []
        for c in checks:
            if not isinstance(c, dict):
                continue
            amount = c.get("amount")
            rows.append(
                {
                    "Check#": c.get("check_number") or "",
                    "Pay to": c.get("pay_to") or "",
                    "Payer": c.get("payer_name") or "",
                    "Amount": f"${float(amount):,.2f}" if amount is not None else "",
                    "Confidence": c.get("confidence_label") or "",
                }
            )
        if rows:
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    payee_merged = 0
    ocr_meta_full = st.session_state.get("bank_stmt_azure_ocr_meta")
    if isinstance(ocr_meta_full, dict):
        payee_merged = int(ocr_meta_full.get("azure_check_payees_merged") or 0)
    if payee_merged > 0:
        st.info(f"Merged payee names from Azure checks into **{payee_merged}** transaction row(s).")


def _sidebar_overdue_count(req_df: pd.DataFrame) -> int:
    return int(
        (
            (req_df["status"].isin(["Pending", "Received"]))
            & (pd.to_datetime(req_df["due_date"], errors="coerce") < datetime.now())
        ).sum()
    )


def render_sidebar_header(req_df: pd.DataFrame) -> None:
    """Top sidebar: signed-in user and one-line operational status."""
    user = get_app_user()
    mode_label = "PostgreSQL" if DATA_SOURCE == "postgresql" else "CSV"
    mode_icon = "🗄️" if DATA_SOURCE == "postgresql" else "📁"
    overdue = _sidebar_overdue_count(req_df)
    status_bits = [f"{mode_icon} {mode_label}"]
    if overdue:
        status_bits.append(f"⚠️ {overdue} overdue")
    else:
        status_bits.append("✅ No overdue items")
    st.sidebar.markdown(
        f'<div class="slam-sidebar-user">'
        f'<p class="slam-sidebar-user-name">Signed in as {user}</p>'
        f'<p class="slam-sidebar-status">{" · ".join(status_bits)}</p>'
        f"</div>",
        unsafe_allow_html=True,
    )
    if st.session_state.get("last_save_message"):
        st.sidebar.success(st.session_state["last_save_message"])


def render_sidebar_freshness() -> None:
    """Data freshness expander — auto-open when unavailable or DB degraded."""
    freshness = get_data_freshness(data_source=DATA_SOURCE, data_path=DATA_PATH)
    expand_freshness = not freshness.get("available") or DB_HEALTH != "ok"
    with st.sidebar.expander("📅 Data freshness", expanded=expand_freshness):
        if freshness.get("available"):
            if DATA_SOURCE == "postgresql":
                st.write(f"**{freshness.get('label')}** — {freshness.get('message', '')}")
                st.caption(
                    f"{freshness.get('clients', 0)} clients · "
                    f"{freshness.get('requests', 0)} requests in database"
                )
            else:
                st.write(f"**Last CSV update:** {freshness.get('last_updated', '—')}")
                st.caption(f"Requests file: {freshness.get('requests_updated', '—')}")
                st.caption(f"Clients file: {freshness.get('clients_updated', '—')}")
        else:
            st.warning(freshness.get("message", "Data freshness unavailable"))


def render_sidebar_help() -> None:
    """Collapsed daily workflow + UAT checklist."""
    with st.sidebar.expander("❓ Daily workflow help", expanded=False):
        st.markdown(
            "**Morning (2 min)**\n"
            "1. Open **Dashboard** — **Today's priority** (top section, full overdue list — not affected by filters)\n"
            "2. Use **Open Overdue quick view** or sidebar **Overdue** / **This Month**\n"
            "3. **Missing Docs** shows bank stmt / sales report gaps (counts in sidebar)\n\n"
            "**During the day**\n"
            "4. **Bank Statements** — upload PDF → **Process Statement** → **Mark as Received**\n"
            "5. **Revenue Requests** — update Status, checkboxes, notes\n"
            "6. Watch for the **unsaved changes** warning — click **Save** when ready\n"
            "7. Use **Undo Last Change** if you made a mistake\n\n"
            "**End of day**\n"
            "8. **Force reload data** if Stef edited on another machine (CSV mode)\n"
            "9. Submit feedback below if something feels wrong"
        )

    with st.sidebar.expander("📋 UAT checklist (week 1)", expanded=False):
        st.markdown(
            "- [ ] Log in and confirm your name shows in the sidebar\n"
            "- [ ] Dashboard loads with client counts (not blank tables)\n"
            "- [ ] **Today's priority** shows at top (overdue list or **All caught up!**)\n"
            "- [ ] Try **Overdue** quick view — reset filters after\n"
            "- [ ] Edit one row on Revenue Requests → **Save** → confirm green message\n"
            "- [ ] Try **Undo** once to verify it works\n"
            "- [ ] **Bank Statements** — upload PDF → Process → Mark as Received\n"
            "- [ ] Submit one test feedback item (sidebar form)\n"
            "- [ ] Tell Robert if anything blocks daily work (P0)"
        )


def render_sidebar_system() -> None:
    """Collapsed system / Azure pipeline diagnostics."""
    info = get_app_info(app_version=APP_VERSION, data_source=DATA_SOURCE, use_postgres=USE_POSTGRES)
    with st.sidebar.expander("🔧 System status", expanded=False):
        st.caption(f"Version **{info['version']}** · Mode: **{info['data_source']}**")
        st.caption(f"Host: `{info['host']}`")
        if info["custom_password"]:
            st.caption("✅ Production password configured")
        else:
            st.caption("⚠️ Default password — set SLAM_APP_PASSWORD in Azure")
        if info["data_path_override"]:
            st.caption("SLAM_DATA_PATH override active")

        ocr_state = azure_ocr_status()
        if ocr_state["configured"]:
            st.caption("🤖 Azure Document Intelligence (bank statements): **configured** ✅")
        else:
            st.caption("🤖 Azure Document Intelligence (bank statements): **not configured**")
            st.caption(f"  ↳ {ocr_state['hint']}")

        hybrid_state = hybrid_cv_status()
        if hybrid_state.get("ready"):
            check_pages = hybrid_state.get("check_pages") or "—"
            check_leg = hybrid_state.get("check_leg") or "document_intelligence"
            leg_short = "CU" if check_leg == "content_understanding" else "DI"
            reader_note = ""
            if hybrid_state.get("dedicated_check_reader"):
                reader_note = " · slam-check-reader"
            st.caption(
                "Azure bank pipeline: **configured** ✅ "
                f"(register=DI · checks={leg_short}{reader_note} · imaging {check_pages})"
            )
        else:
            st.caption("Azure bank pipeline: **not configured**")
            if hybrid_state.get("hint"):
                st.caption(f"  ↳ {hybrid_state['hint']}")

        for hint in get_operational_hints(data_source=DATA_SOURCE, db_health=DB_HEALTH):
            st.caption(f"• {hint}")


def render_sidebar_qms() -> None:
    """Collapsed QMS baseline summary."""
    with st.sidebar.expander("📋 QMS status", expanded=False):
        qms = get_qms_status(data_path=DATA_PATH)
        if qms["summary"] == "healthy":
            st.caption("Baseline: **healthy** ✅")
        else:
            st.caption("Baseline: **watch** ⚠️")
        if qms["last_state_alignment"]:
            st.caption(f"Last State Alignment: `{qms['last_state_alignment']}`")
        if qms["last_management_review"]:
            st.caption(f"Last Management Review: `{qms['last_management_review']}`")
        if qms["feedback"]["available"]:
            st.caption(
                f"Feedback log: {qms['feedback']['open']} open / {qms['feedback']['total']} total"
            )
        for issue in qms["issues"]:
            st.caption(f"• {issue}")


def render_sidebar_bottom(req_df: pd.DataFrame) -> None:
    """Bottom sidebar: feedback, exports, reload, logout."""
    st.sidebar.markdown("---")

    with st.sidebar.expander("📣 Submit runtime feedback", expanded=False):
        st.caption("Writes to feedback_log.csv for the next iteration cycle.")
        with st.form("feedback_form", clear_on_submit=True):
            reported_by = st.selectbox("Reported by", ["Laura", "Stef", "Patty", "Robert", "Other"])
            category = st.selectbox(
                "Category",
                [
                    "Global Filter",
                    "Dashboard",
                    "Revenue Requests Table",
                    "Bank Statements",
                    "Bulk Update",
                    "Data/Export",
                    "Performance/Security",
                    "Other",
                ],
            )
            description = st.text_area("What is broken or missing? (be specific)", height=80)
            priority = st.selectbox(
                "Priority (your view)",
                ["P0 - Blocking daily work", "P1 - Important for accuracy", "P2 - Nice to have"],
            )
            if st.form_submit_button("Submit feedback"):
                if description.strip():
                    log_path = _feedback_log_path()
                    import csv as _csv
                    from datetime import datetime as _dt

                    row = [
                        _dt.now().isoformat(timespec="seconds"),
                        reported_by,
                        category,
                        description.strip().replace("\n", " "),
                        priority,
                        "Open",
                        APP_VERSION,
                    ]
                    with open(log_path, "a", encoding="utf-8", newline="") as f:
                        _csv.writer(f).writerow(row)
                    st.success(
                        "✅ Feedback recorded. Thank you — it will be reviewed in the next cycle."
                    )
                else:
                    st.warning("Please enter a description before submitting.")

    if st.sidebar.button("📆 Generate monthly revenue summary", use_container_width=True):
        summary = req_df.copy()
        summary["due_month"] = (
            pd.to_datetime(summary["due_date"], errors="coerce").dt.to_period("M").astype(str)
        )
        summary_group = (
            summary.groupby(["due_month", "status"])
            .agg(total_requests=("request_id", "count"), total_amount=("amount_due", "sum"))
            .reset_index()
        )
        csv_sum = io.StringIO()
        summary_group.to_csv(csv_sum, index=False)
        st.sidebar.download_button(
            label="📥 Download monthly summary CSV",
            data=csv_sum.getvalue(),
            file_name=f"monthly_revenue_summary_{datetime.now().strftime('%Y%m')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    if st.sidebar.button("🔄 Force reload data", use_container_width=True):
        if st.session_state.get("revenue_unsaved"):
            st.sidebar.error(
                "You have unsaved edits on Revenue Requests. Save or undo before reloading."
            )
        else:
            log_event(LOGGER, "force_reload")
            st.cache_data.clear()
            st.session_state.pop("revenue_unsaved", None)
            st.rerun()

    if st.sidebar.button("🚪 Log out", use_container_width=True):
        log_event(LOGGER, "logout", user=get_app_user())
        st.session_state.authenticated = False
        st.session_state.current_user = ""
        st.session_state.pop("last_save_message", None)
        st.cache_data.clear()
        st.rerun()


# --- Main application body ---
def main():
    log_event(
        LOGGER,
        "app_start",
        version=APP_VERSION,
        data_source=DATA_SOURCE,
        postgres=USE_POSTGRES,
    )
    try:
        clients_df = load_clients()
        req_df = load_requests()
    except DataLoadError as exc:
        log_event(LOGGER, "data_load_error", error=str(exc)[:200])
        st.error(str(exc))
        if POSTGRES_REQUESTED and USE_POSTGRES:
            st.info(
                "If PostgreSQL was just enabled, run:\n"
                "`python Scripts/init_db.py` then `python Scripts/migrate_to_postgres.py`"
            )
        st.stop()

    render_sidebar_header(req_df)
    render_data_source_status(len(clients_df), len(req_df))
    render_sidebar_freshness()

    filters = render_global_filters(req_df)
    st.session_state["last_filter_industry"] = filters["industry"]

    filtered = apply_filters(req_df, clients_df, filters)

    # Page navigation (goto_page set by Today's priority CTAs)
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Navigation**")
    _nav_pages = ["Dashboard", "Clients", "Revenue Requests", "Bank Statements"]
    if st.session_state.get("goto_page") in _nav_pages:
        st.session_state["nav_page"] = st.session_state.pop("goto_page")
    if st.session_state.get("nav_page") not in _nav_pages:
        st.session_state["nav_page"] = "Dashboard"
    page = st.sidebar.radio("Go to", _nav_pages, key="nav_page", label_visibility="collapsed")

    render_sidebar_help()
    render_sidebar_system()
    render_sidebar_qms()

    if USE_POSTGRES and len(req_df) == 0:
        st.warning(
            "Database connected but no revenue requests were found. "
            "Run `python Scripts/migrate_to_postgres.py` to load your CSV data."
        )
    elif not USE_POSTGRES and POSTGRES_REQUESTED and len(req_df) == 0:
        st.warning(
            "Showing CSV fallback data but no requests loaded. "
            "Check that RevenueRequests.csv exists in the data folder."
        )

    if page == "Dashboard":
        dashboard_page(clients_df, req_df, filtered)
    elif page == "Clients":
        clients_page(clients_df, req_df, filtered)
    elif page == "Revenue Requests":
        requests_page(req_df, clients_df, filtered)
    elif page == "Bank Statements":
        bank_statements_page(clients_df, req_df)

    # Footer + export helpers
    st.caption(f"SLAM Services Digital Transformation • Azure Revenue Tracker • {APP_VERSION}")

    render_sidebar_bottom(req_df)


if __name__ == "__main__":
    main()
