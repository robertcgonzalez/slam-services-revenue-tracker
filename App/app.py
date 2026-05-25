import io
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from app_logging import log_event, setup_app_logging

try:
    from bank_statements import (
        GROK_VISION_HINT,
        ZERO_TRANSACTIONS_MSG,
        build_grok_vision_prompt,
        filter_transactions_by_confidence,
        format_processing_log,
        missing_document_counts,
        run_statement_pipeline,
        scripts_available,
        style_low_confidence_rows,
        transaction_summary_metrics,
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

    from bank_statements import (
        missing_document_counts,
        run_statement_pipeline,
        scripts_available,
        transaction_summary_metrics,
    )
from data_paths import render_data_path_error, resolve_data_path
from diagnostics import get_app_info, get_app_user, get_data_freshness, get_operational_hints

st.set_page_config(page_title="SLAM Services Revenue Tracker", layout="wide", page_icon="📊")

APP_VERSION = "v2.37"
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
    .slam-priority-hero {
        background: linear-gradient(135deg, #fff1f2 0%, #fff8e6 100%);
        border: 2px solid #dc2626;
        border-left: 6px solid #dc2626;
        padding: 1rem 1.25rem;
        border-radius: 8px;
        margin: 0.5rem 0 1rem 0;
        box-shadow: 0 2px 8px rgba(220, 38, 38, 0.12);
    }
    .slam-priority-hero h4 { margin: 0 0 0.35rem 0; color: #991b1b; font-size: 1.15rem; }
    .slam-priority-hero p { margin: 0; color: #7f1d1d; font-size: 0.95rem; }
    .slam-priority-caught-up {
        background: #ecfdf5;
        border: 2px solid #059669;
        border-left: 6px solid #059669;
        padding: 1rem 1.25rem;
        border-radius: 8px;
        margin: 0.5rem 0 1rem 0;
    }
    div[data-testid="stMetric"] {
        background: #f8fafc;
        padding: 0.5rem;
        border-radius: 6px;
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

# --- Auth (unchanged contract) ---
HAS_CUSTOM_PASSWORD = "SLAM_APP_PASSWORD" in os.environ
APP_PASSWORD = os.environ.get("SLAM_APP_PASSWORD", "SLAM2026")
if not HAS_CUSTOM_PASSWORD:
    st.warning(
        "⚠️ Using default password. Set SLAM_APP_PASSWORD App Setting in Azure for production security."
    )

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False


def login():
    st.title("🔐 SLAM Services Login")
    st.caption("Revenue Reporting Tracker — secure access for SLAM Services staff.")
    password = st.text_input("Enter Password", type="password")
    if st.button("Login", type="primary"):
        if password == APP_PASSWORD:
            st.session_state.authenticated = True
            log_event(LOGGER, "login_success")
            st.rerun()
        else:
            log_event(LOGGER, "login_failed")
            st.error("Incorrect password. Contact Robert if you need the password reset.")


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
    except Exception as exc:
        raise DataLoadError(
            "We couldn't load clients from the database. "
            "Try refreshing the page — if this continues, contact Robert."
            f" ({friendly_db_error(exc)})"
        ) from exc
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
    except Exception as exc:
        raise DataLoadError(
            "We couldn't load revenue requests from the database. "
            "Try refreshing the page — if this continues, contact Robert."
            f" ({friendly_db_error(exc)})"
        ) from exc
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
        st.success("✅ **All caught up!** Nothing overdue across your full client list.")
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
    st.header("📈 SLAM Services Revenue Overview")
    st.markdown(
        f'<p class="slam-subtle">Welcome — {datetime.now().strftime("%A, %B %d, %Y")}</p>',
        unsafe_allow_html=True,
    )
    render_uat_welcome()
    render_todays_priority(req_df)
    st.divider()

    total_clients = len(clients_df)
    total_pending_amt = filtered[filtered["status"].isin(["Pending", "Received", "Invoiced"])][
        "amount_due"
    ].sum()
    overdue_cnt = filtered["overdue"].sum() if "overdue" in filtered.columns else 0
    completion_pct = round(
        100 * len(filtered[filtered["status"] == "Paid"]) / max(1, len(filtered)), 1
    )

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

    st.subheader("Status Breakdown")
    status_counts = filtered["status"].value_counts().reset_index()
    status_counts.columns = ["status", "count"]
    st.bar_chart(status_counts, x="status", y="count")

    st.subheader("Overdue Requests (Action Required)")
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

    st.subheader("Recent Activity (last 10 records)")
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

    Auto-expands when the lightweight parser extracted 0 transactions (the most common
    case for scanned/image-only statements). Always available as a collapsed expander
    once a PDF has been processed, so Laura can route any statement through Grok if
    the parser misses something.
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
                "The lightweight parser couldn't read this PDF (likely scanned/image-only). "
                "Use Grok Vision to extract transactions, then drop the resulting CSV next to "
                "the PDF for the existing Power Query / Process-Statement workflow."
            )
        else:
            st.caption(
                "Use this if you want to double-check the parser output against Grok's vision, "
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
            if cropped_count > 0 and cropped_dir:
                st.markdown(f"**Cropped checks**: {cropped_count} image(s) in `{cropped_dir}`")
            elif cropped_dir:
                st.markdown(f"**Cropped checks folder**: `{cropped_dir}` (no images this run)")

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


def bank_statements_page(clients_df: pd.DataFrame, req_df: pd.DataFrame) -> None:
    """Core Workstream #2 MVP — upload PDF, run parser pipeline, review, mark received."""
    st.header("🏦 Bank Statements")
    st.markdown(
        '<p class="slam-subtle">Upload a client bank statement PDF, run the SLAM parser pipeline, '
        "review transactions, then mark the matching revenue request as received.</p>",
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

    if st.button("Process Statement", type="primary", key="bank_stmt_process"):
        if not uploaded:
            st.warning("Upload at least one PDF before processing.")
        else:
            all_logs: list[str] = []
            last_df: pd.DataFrame | None = None
            last_csv: Path | None = None
            last_status = "error"
            cropper_msg: str | None = None
            last_meta: dict = {}
            last_pdf_name: str = ""
            for up in uploaded:
                all_logs.append(f"========== {up.name} ==========")
                log_event(LOGGER, "bank_stmt_process_start", client=selected_client, file=up.name)
                df, logs, csv_path, meta = run_statement_pipeline(
                    up.getvalue(),
                    up.name,
                    LOGGER,
                )
                last_meta = meta
                last_pdf_name = up.name
                all_logs.extend(logs)
                if meta.get("cropper_user_message"):
                    cropper_msg = meta["cropper_user_message"]
                if df is not None:
                    last_df = df
                    last_csv = csv_path or meta.get("csv_path")
                    last_status = meta.get("status", "success")
                elif last_status != "partial":
                    last_status = "error"
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
            st.session_state["bank_stmt_cropped_count"] = int(
                last_meta.get("cropped_check_count") or 0
            )
            st.session_state["bank_stmt_text_layer"] = bool(
                last_meta.get("text_layer_found", False)
            )
            if last_df is not None:
                row_count = len(last_df)
                if row_count == 0:
                    if not st.session_state.get("bank_stmt_text_layer", False):
                        st.warning(
                            "📷 **Scanned/image-only PDF detected** — no text layer to parse. "
                            "Use the **Prepare for Grok Vision** section below to extract "
                            "transactions in one paste."
                        )
                    else:
                        st.warning(ZERO_TRANSACTIONS_MSG)
                    st.info(GROK_VISION_HINT)
                elif last_status == "partial":
                    st.warning(
                        f"Partial success: {row_count} transactions extracted from "
                        f"{len(uploaded)} file(s). Optional check cropping did not complete — "
                        "see processing log."
                    )
                else:
                    st.success(
                        f"Success: extracted {row_count} transactions from {len(uploaded)} file(s)."
                    )
                if last_csv:
                    st.info(f"Output CSV: `{last_csv}`")
                if cropper_msg:
                    st.info(cropper_msg)
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
            st.rerun()

    pipeline_status = st.session_state.get("bank_stmt_pipeline_status")
    if st.session_state.get("bank_stmt_cropper_msg") and pipeline_status == "partial":
        st.caption(st.session_state["bank_stmt_cropper_msg"])

    if st.session_state.get("bank_stmt_logs"):
        with st.expander("Processing log", expanded=pipeline_status == "error"):
            st.code(st.session_state["bank_stmt_logs"], language=None)

    if "bank_stmt_raw_text" in st.session_state:
        raw_export = st.session_state.get("bank_stmt_raw_text") or ""
        if not raw_export.strip():
            raw_export = (
                "(No extractable text in PDF — likely a scanned/image statement. "
                "Use Grok Vision on the PDF pages or a OCR tool.)"
            )
        st.download_button(
            "Export Raw Text",
            raw_export,
            file_name="bank_statement_raw_text.txt",
            mime="text/plain",
            key="bank_stmt_export_raw_text",
        )

    txn_df = st.session_state.get("bank_stmt_txn_df")
    if txn_df is not None and isinstance(txn_df, pd.DataFrame) and not txn_df.empty:
        metrics = transaction_summary_metrics(txn_df)
        review_n = int(metrics["needs_review"])
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Transactions", metrics["count"])
        m2.metric("Total deposits", f"${metrics['deposits']:,.2f}")
        m3.metric("Total withdrawals", f"${metrics['withdrawals']:,.2f}")
        m4.metric("Items need review", review_n)

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

        st.subheader("Transactions (review & edit)")
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


def render_sidebar_extras(
    clients_df: pd.DataFrame,
    req_df: pd.DataFrame,
) -> None:
    """Daily-driver sidebar: user, freshness, help, diagnostics, logout."""
    st.sidebar.markdown("---")
    st.sidebar.caption(f"Signed in · **{get_app_user()}**")
    if st.session_state.get("last_save_message"):
        st.sidebar.success(st.session_state["last_save_message"])

    freshness = get_data_freshness(data_source=DATA_SOURCE, data_path=DATA_PATH)
    with st.sidebar.expander("📅 Data freshness", expanded=False):
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
        for hint in get_operational_hints(data_source=DATA_SOURCE, db_health=DB_HEALTH):
            st.caption(f"• {hint}")

    if st.sidebar.button("🚪 Log out", use_container_width=True):
        log_event(LOGGER, "logout")
        st.session_state.authenticated = False
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

    render_data_source_status(len(clients_df), len(req_df))
    render_sidebar_extras(clients_df, req_df)

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

    filters = render_global_filters(req_df)
    st.session_state["last_filter_industry"] = filters["industry"]

    filtered = apply_filters(req_df, clients_df, filters)

    # Page navigation (goto_page set by Today's priority CTAs)
    st.sidebar.title("Navigation")
    _nav_pages = ["Dashboard", "Clients", "Revenue Requests", "Bank Statements"]
    if st.session_state.get("goto_page") in _nav_pages:
        st.session_state["nav_page"] = st.session_state.pop("goto_page")
    if st.session_state.get("nav_page") not in _nav_pages:
        st.session_state["nav_page"] = "Dashboard"
    page = st.sidebar.radio("Go to", _nav_pages, key="nav_page")

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

    if st.sidebar.button("🔄 Force reload data (clear caches)"):
        if st.session_state.get("revenue_unsaved"):
            st.sidebar.error(
                "You have unsaved edits on Revenue Requests. Save or undo before reloading."
            )
        else:
            log_event(LOGGER, "force_reload")
            st.cache_data.clear()
            st.session_state.pop("revenue_unsaved", None)
            st.rerun()

    # --- Structured, Persistent Feedback Collection (Phase 2.5 core process) ---
    with st.sidebar.expander("📣 Submit Runtime Feedback", expanded=False):
        st.caption(
            "This form writes directly to the persistent feedback_log.csv so every observation is captured for the next iteration cycle."
        )
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
            if st.form_submit_button("Submit Feedback to Log"):
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

    # Monthly revenue summary export (always available)
    if st.sidebar.button("📆 Generate Monthly Revenue Summary"):
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
            label="📥 Download Monthly Summary CSV",
            data=csv_sum.getvalue(),
            file_name=f"monthly_revenue_summary_{datetime.now().strftime('%Y%m')}.csv",
            mime="text/csv",
        )


if __name__ == "__main__":
    main()
