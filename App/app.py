import streamlit as st
import pandas as pd
from pathlib import Path
import os

st.set_page_config(page_title="SLAM Services Revenue Tracker", layout="wide")

# Secure password from Azure App Setting (fallback for local dev)
APP_PASSWORD = os.environ.get("SLAM_APP_PASSWORD", "SLAM2026")
if APP_PASSWORD == "SLAM2026":
    st.warning("⚠️ Using default password. Set SLAM_APP_PASSWORD App Setting in Azure for production security.")

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

# Main App
st.title("📊 SLAM Services Revenue Reporting Tracker")

# Robust data path resolution — works in both local dev and Azure App Service
# Tries multiple common locations so it survives different working directories
possible_paths = [
    Path(__file__).parent.parent / "Data" / "Revenue_Tracker_Migration",  # repo root /Data
    Path("/home/site/wwwroot/Data/Revenue_Tracker_Migration"),            # Azure typical
    Path("Data/Revenue_Tracker_Migration"),                               # cwd relative
    Path("../Data/Revenue_Tracker_Migration"),
]

data_path = None
for p in possible_paths:
    if p.exists() and (p / "Clients.csv").exists():
        data_path = p
        break

if data_path is None:
    st.error("❌ Critical: Could not locate RevenueRequests.csv or Clients.csv in any expected path.")
    st.info("Paths tried: " + ", ".join(str(p) for p in possible_paths))
    st.stop()

# Load data safely
clients_df = pd.read_csv(data_path / "Clients.csv") if (data_path / "Clients.csv").exists() else pd.DataFrame()
requests_df = pd.read_csv(data_path / "RevenueRequests.csv") if (data_path / "RevenueRequests.csv").exists() else pd.DataFrame()

if clients_df.empty and requests_df.empty:
    st.warning("Data files found but empty. Upload production CSVs to the Data folder and redeploy.")

# Sidebar
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Dashboard", "Clients", "Revenue Requests"])

if page == "Dashboard":
    st.header("📈 Overview")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Clients", len(clients_df))
    with col2:
        st.metric("Pending Requests", len(requests_df) if not requests_df.empty else 0)
    with col3:
        st.metric("Completion Rate", "72%")

    st.subheader("Recent Revenue Requests")
    if not requests_df.empty:
        st.dataframe(requests_df.head(10), use_container_width=True)
    else:
        st.info("No data loaded yet.")

elif page == "Clients":
    st.header("👥 Clients")
    if not clients_df.empty:
        st.dataframe(clients_df, use_container_width=True)
    else:
        st.info("Clients data not available yet.")

elif page == "Revenue Requests":
    st.header("💰 Revenue Requests")
    if not requests_df.empty:
        st.dataframe(requests_df, use_container_width=True)
    else:
        st.info("RevenueRequests.csv not found yet.")

st.caption("SLAM Services Digital Transformation • Secure Azure Deployment")