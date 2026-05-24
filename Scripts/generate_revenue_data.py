import pandas as pd
import random
from datetime import datetime, timedelta
from pathlib import Path

# Project paths
BASE = Path(r"C:\SLAM-Services-Project")
DATA_DIR = BASE / "Data" / "Revenue_Tracker_Migration"
CLIENTS_CSV = DATA_DIR / "Clients.csv"
REQUESTS_CSV = DATA_DIR / "RevenueRequests.csv"

def clean_clients(df):
    # Rename and clean: first row is junk, skip lines with empty Business Name
    df.columns = [c.strip() for c in df.columns]
    df = df.iloc[1:]  # skip first data line that was header
    df = df[df["Business Name"].str.strip() != ""]
    df = df[df["Business Name"].notna()]
    # Keep only name + useful metadata
    cols_to_keep = ["Business Name", "EIN", "Entity Type", "City State Zip"]
    for col in cols_to_keep:
        if col not in df.columns:
            df[col] = ""
    return df[cols_to_keep].reset_index(drop=True)

def generate_requests(clients_df, num_samples=30):
    random.seed(42)  # reproducible

    # Industries hints
    is_restaurant = lambda name: any(x in name.upper() for x in ["GRILL", "CANTINA", "RESTAURANT", "TACOS", "MEX", "BAR", "TAQUERIA", "FIESTA"])
    is_construction = lambda name: any(x in name.upper() for x in ["CONTRACT", "CONCRETE", "ROOF", "BUILDER", "MASON", "PAINT", "REMODEL", "LEVEL", "PLUMB", "DRY"])

    types_pool = ["Monthly Bookkeeping", "Sales Tax", "Liquor Tax"]
    statuses = ["Pending", "Received", "Invoiced", "Paid"]

    today = datetime(2026, 5, 23)
    rows = []

    # Sample 28 diverse high-likelihood clients
    sample_clients = clients_df.sample(n=min(28, len(clients_df)), random_state=42).reset_index(drop=True)

    request_id = 1000
    for _, row in sample_clients.iterrows():
        name = str(row["Business Name"]).strip()
        # 1-2 requests per client (some recent, some older)
        for i in range(random.randint(1, 2)):
            rtype = random.choice(types_pool)
            # Period choices last 9 months
            months_back = random.randint(0, 8)
            period_dt = today - timedelta(days=30 * months_back)
            period = period_dt.strftime("%Y-%m")

            due_dt = period_dt + timedelta(days=random.randint(5, 12))
            due = due_dt.strftime("%Y-%m-%d")

            # received_date: None, or past due_date
            received = ""
            status = random.choice(statuses)
            if status in ["Received", "Invoiced", "Paid"]:
                received_dt = due_dt + timedelta(days=random.randint(0, 6))
                received = received_dt.strftime("%Y-%m-%d")

            amount = round(random.uniform(450, 1850), 2) if rtype == "Monthly Bookkeeping" else round(random.uniform(280, 720), 2)

            notes_options = ["", "Follow up by text 5/12", "Partial payment $300", "Waiting on bank recs", "Missing liquor report"]
            notes = random.choice(notes_options)
            doc_bank = "✓" if random.random() > 0.35 else ""
            doc_sales = "✓" if rtype in ("Sales Tax", "Liquor Tax") and random.random() > 0.4 else ""

            rows.append({
                "request_id": request_id,
                "business_name": name,
                "request_type": rtype,
                "period": period,
                "status": status,
                "amount_due": amount,
                "due_date": due,
                "received_date": received,
                "notes": notes,
                "bank_statement_received": doc_bank,
                "sales_report_received": doc_sales
            })
            request_id += 1

    return pd.DataFrame(rows)

def main():
    print("Loading Clients.csv...")
    raw = pd.read_csv(CLIENTS_CSV, encoding="utf-8")
    clients = clean_clients(raw)
    print(f"Found {len(clients)} active clients after cleaning.")

    print("Generating realistic RevenueRequests sample data...")
    requests = generate_requests(clients, num_samples=30)
    print(f"Generated {len(requests)} request rows.")

    # Backup old requests if present
    if REQUESTS_CSV.exists():
        backup = REQUESTS_CSV.with_name("RevenueRequests.csv.bak")
        REQUESTS_CSV.rename(backup)
        print(f"Backed up existing requests to {backup.name}")

    requests.to_csv(REQUESTS_CSV, index=False)
    print(f"Wrote new enriched requests file: {REQUESTS_CSV}")

    # Show sample output
    print("\nSample of new RevenueRequests.csv:")
    print(requests.head(8).to_string())

if __name__ == "__main__":
    main()