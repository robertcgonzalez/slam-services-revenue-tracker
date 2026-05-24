import io
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from data_paths import render_data_path_error, resolve_data_path

st.set_page_config(page_title="SLAM Services Revenue Tracker", layout="wide", page_icon="📊")

# --- Data source mode (Phase 3 dual mode) ---
USE_POSTGRES = os.environ.get("USE_POSTGRES", "").strip().lower() in ("1", "true", "yes")
DATA_SOURCE = "postgresql" if USE_POSTGRES else "csv"

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
    password = st.text_input("Enter Password", type="password")
    if st.button("Login"):
        if password == APP_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password")


if not st.session_state.authenticated:
    login()
    st.stop()


# --- Data path resolution (CSV fallback) ---
DATA_PATH: Path | None = None
DATA_PATH_LOGS: list[str] = []


def _init_csv_data_path() -> None:
    global DATA_PATH, DATA_PATH_LOGS
    DATA_PATH, DATA_PATH_LOGS = resolve_data_path()


if not USE_POSTGRES:
    _init_csv_data_path()
    if DATA_PATH is None:
        st.error(f"❌ Critical: {render_data_path_error(DATA_PATH_LOGS)}")
        with st.expander("Debug: path resolution log"):
            st.code("\n".join(DATA_PATH_LOGS))
        st.stop()
else:
    try:
        from db_utils import test_connection

        ok, msg = test_connection()
        if not ok:
            st.warning(f"⚠️ PostgreSQL unavailable ({msg}). Falling back to CSV.")
            USE_POSTGRES = False
            DATA_SOURCE = "csv"
            _init_csv_data_path()
            if DATA_PATH is None:
                st.error(f"❌ Critical: PostgreSQL failed and CSV fallback missing.\n{msg}")
                st.stop()
        else:
            st.sidebar.caption("🗄️ Data source: PostgreSQL")
            if DATA_PATH is None:
                resolved, _ = resolve_data_path()
                if resolved is not None:
                    DATA_PATH = resolved
    except ImportError as exc:
        st.warning(f"⚠️ db_utils not available ({exc}). Falling back to CSV.")
        USE_POSTGRES = False
        DATA_SOURCE = "csv"
        _init_csv_data_path()
        if DATA_PATH is None:
            st.error("❌ Critical: Could not load database utilities or CSV data.")
            st.stop()


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
    except Exception:
        return pd.DataFrame()


def _load_clients_db() -> pd.DataFrame:
    from db_utils import Client, get_session

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
    except Exception:
        return pd.DataFrame()


def _load_requests_db() -> pd.DataFrame:
    from db_utils import Client, RevenueRequest, get_session

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


# --- Global filters in sidebar (propagate across pages) ---
def render_global_filters(req_df):
    st.sidebar.title("🔎 Global Filters")
    # Date range
    min_d = pd.to_datetime(req_df["due_date"], errors="coerce").min()
    max_d = pd.to_datetime(req_df["due_date"], errors="coerce").max()
    if pd.isna(min_d):
        min_d = datetime(2025, 10, 1)
    if pd.isna(max_d):
        max_d = datetime(2026, 6, 10)
    date_range = st.sidebar.date_input(
        "Due date range",
        value=(min_d.date(), max_d.date()),
        min_value=min_d.date(),
        max_value=max_d.date(),
    )

    # Status multi-select
    all_status = ["Pending", "Received", "Invoiced", "Paid"]
    sel_status = st.sidebar.multiselect("Status", all_status, default=all_status)

    base_types = req_df["request_type"].dropna().unique().tolist() if len(req_df) else []
    extra_types = ["Payroll", "Tax prep"]
    all_types = sorted(set(base_types) | set(extra_types))
    sel_type = st.sidebar.multiselect("Request Type", all_types, default=all_types)

    # Industry segments
    all_ind = ["All", "Restaurant/Bar", "Construction/Trades", "Other"]
    sel_ind = st.sidebar.selectbox("Industry Segment", all_ind, index=0)

    if st.sidebar.button("Reset Filters", key="btn_reset_filters"):
        for k in list(st.session_state.keys()):
            if k.startswith(("filter_", "revenue_editor", "last_filter_industry", "widget_")):
                try:
                    del st.session_state[k]
                except Exception:
                    pass
        st.cache_data.clear()
        st.rerun()

    return {
        "date_range": date_range,
        "status": sel_status,
        "request_type": sel_type,
        "industry": sel_ind,
    }


def apply_filters(req_df, clients_df, f):
    df = req_df.copy()
    # Date filter
    if len(f["date_range"]) == 2:
        lo, hi = pd.to_datetime(f["date_range"][0]), pd.to_datetime(f["date_range"][1])
        df["due_date_parsed"] = pd.to_datetime(df["due_date"], errors="coerce")
        df = df[(df["due_date_parsed"] >= lo) & (df["due_date_parsed"] <= hi)]

    # Status
    if f["status"]:
        df = df[df["status"].isin(f["status"])]

    # Type
    if f["request_type"]:
        df = df[df["request_type"].isin(f["request_type"])]

    # Industry join + filter
    if f["industry"] != "All":
        matched_clients = clients_df[clients_df["industry_category"] == f["industry"]][
            "Business Name"
        ].tolist()
        df = df[df["business_name"].isin(matched_clients)]

    # Add overdue flag
    df["overdue"] = (df["status"].isin(["Pending", "Received"])) & (
        pd.to_datetime(df["due_date"], errors="coerce") < datetime.now()
    )
    return df.drop(columns=["due_date_parsed"], errors="ignore")


# --- Persist helper (CSV; PostgreSQL write-back is Phase 3 follow-up) ---
def _requests_csv_path() -> Path:
    if DATA_PATH is None:
        raise RuntimeError(
            "CSV path unavailable. Deploy Data/Revenue_Tracker_Migration or enable PostgreSQL writes."
        )
    return DATA_PATH / "RevenueRequests.csv"


def save_requests(df, path: Path | None = None):
    if USE_POSTGRES:
        raise RuntimeError(
            "PostgreSQL write-back not enabled yet — save remains CSV-only during transition."
        )
    target = path or _requests_csv_path()
    df.to_csv(target, index=False)


def _feedback_log_path() -> Path:
    if DATA_PATH is not None:
        return DATA_PATH / "feedback_log.csv"
    resolved, _ = resolve_data_path()
    if resolved is not None:
        return resolved / "feedback_log.csv"
    fallback = Path("/home/site/wwwroot/Data/Revenue_Tracker_Migration")
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback / "feedback_log.csv"


# --- Dashboard page enhancements (dynamic KPIs, overdue alerts) ---
def dashboard_page(clients_df, req_df, filtered):
    st.header("📈 SLAM Services Revenue Overview")

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

    st.subheader("Status Breakdown")
    status_counts = filtered["status"].value_counts().reset_index()
    status_counts.columns = ["status", "count"]
    st.bar_chart(status_counts, x="status", y="count")

    st.subheader("Overdue Requests (Action Required)")
    overdue = filtered[filtered.get("overdue", False)]
    if not overdue.empty:
        # P0 final polish (v2.11): hide implicit pandas index so no spurious blank first column appears
        st.dataframe(
            overdue[
                [
                    "request_id",
                    "business_name",
                    "request_type",
                    "period",
                    "amount_due",
                    "due_date",
                    "notes",
                ]
            ],
            width="stretch",
            hide_index=True,
        )
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

    # Editable version — P0 FIX v2.11
    # Explicitly include the two service flag columns and render them as boolean checkboxes
    # so the right-most columns the user mentioned are now visible and editable (Yes/No).
    edited = st.data_editor(
        df[
            [
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
        ],
        num_rows="fixed",
        width="stretch",
        key="revenue_editor",
        hide_index=True,  # Eliminates the useless "first column" complaint
        column_config={
            "status": st.column_config.SelectboxColumn(
                "status", options=["Pending", "Received", "Invoiced", "Paid"], required=True
            ),
            "amount_due": st.column_config.NumberColumn("amount_due", min_value=0, step=50),
            "bank_statement_received": st.column_config.CheckboxColumn("Bank Stmt Rcvd"),
            "sales_report_received": st.column_config.CheckboxColumn("Sales Rpt Rcvd"),
        },
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Save All Changes to CSV", type="primary"):
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
                save_requests(updated)
                # Push to defensive undo stack (trim to last 5)
                if not isinstance(st.session_state.get("undo_stack"), list):
                    st.session_state.undo_stack = []
                st.session_state.undo_stack.append(snapshot)
                st.session_state.undo_stack = st.session_state.undo_stack[-5:]
                st.success(
                    "✅ Saved changes to RevenueRequests.csv. Filters will pick up immediately."
                )
                st.cache_data.clear()
                st.rerun()
            except Exception:
                st.error("Save failed — no data written. Please retry or reload.")

        if st.session_state.get("undo_stack"):
            if st.button("↩️ Undo Last Change", type="secondary"):
                try:
                    prev = st.session_state.undo_stack.pop()
                    save_requests(prev)
                    st.warning("Last edit undone from in-memory snapshot (within this session).")
                    st.cache_data.clear()
                    st.rerun()
                except Exception:
                    st.error("Undo failed.")

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

    if st.button("Apply Bulk Update", disabled=len(selected_labels) == 0):
        if selected_ids:
            master = req_df.set_index("request_id")
            for rid in selected_ids:
                if rid in master.index:
                    master.at[rid, "status"] = new_bulk
            updated = master.reset_index()
            save_requests(updated)
            st.success(f"Updated {len(selected_ids)} request(s) to status '{new_bulk}'")
            st.cache_data.clear()
            st.rerun()


# --- Main application body ---
def main():
    clients_df = load_clients()
    req_df = load_requests()

    filters = render_global_filters(req_df)
    st.session_state["last_filter_industry"] = filters["industry"]

    filtered = apply_filters(req_df, clients_df, filters)

    # Page navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Go to", ["Dashboard", "Clients", "Revenue Requests"], index=0)

    if page == "Dashboard":
        dashboard_page(clients_df, req_df, filtered)
    elif page == "Clients":
        clients_page(clients_df, req_df, filtered)
    elif page == "Revenue Requests":
        requests_page(req_df, clients_df, filtered)

    # Footer + export helpers
    st.caption(
        "SLAM Services Digital Transformation • Azure-hosted Revenue Reporter • Production-Ready v2"
    )

    if st.sidebar.button("🔄 Force reload data (clear caches)"):
        st.cache_data.clear()
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
                        "v2.26",
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
