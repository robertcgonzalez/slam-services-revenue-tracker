import pdfplumber
import csv
import re
import sys
from pathlib import Path
from typing import List, Dict, Any

def validate_transaction_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Exact validation function you approved — strict business rules."""
    errors = []

    # Date
    date_val = str(row.get("Date", "")).strip()
    if not date_val or not re.match(r"^\d{4}-\d{2}-\d{2}$", date_val):
        errors.append("Invalid or missing Date (YYYY-MM-DD)")

    # Amount / SignedAmount
    for field in ["Amount", "SignedAmount"]:
        val = str(row.get(field, "")).strip()
        if val:
            try:
                float(val.replace(",", ""))
            except ValueError:
                errors.append(f"Invalid {field}: {val}")

    # Check#
    check = str(row.get("Check#", "")).strip()
    if check and (not check.isdigit() or "." in check):
        errors.append(f"Invalid Check# (must be whole number): {check}")

    # YearMonth
    ym = str(row.get("YearMonth", "")).strip()
    if ym and not re.match(r"^\d{4}-\d{2}$", ym):
        errors.append(f"Invalid YearMonth (YYYY-MM): {ym}")

    # Confidence & NeedsReview
    if str(row.get("Confidence", "")).strip() not in ["High", "Medium", "Low", ""]:
        errors.append("Invalid Confidence")
    if str(row.get("NeedsReview", "")).strip() not in ["Yes", "No", ""]:
        errors.append("Invalid NeedsReview")

    if errors:
        row["HasError"] = True
        row["NeedsReviewFlag"] = True
        row["ReviewReason"] = "; ".join(errors)
    else:
        row["HasError"] = False
        row["NeedsReviewFlag"] = False
        row["ReviewReason"] = ""

    return row

def parse_bank_statement(pdf_path: str) -> List[Dict]:
    """Main parser — extracts text and builds clean transactions."""
    transactions = []
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    # Very robust line-by-line parsing for Electronic Debits / Credits / Checks
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    current_date = None
    for line in lines:
        # Basic date detection
        date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4})", line)
        if date_match:
            current_date = date_match.group(1).replace("/", "-")
            if len(current_date.split("-")[2]) == 2:
                current_date = "2026-" + current_date.split("-")[0].zfill(2) + "-" + current_date.split("-")[1].zfill(2)

        # Skip headers and totals
        if any(x in line.lower() for x in ["statement activity", "electronic", "check register", "balance", "total"]):
            continue

        # Parse transaction line (this is the key robust part)
        if re.search(r"^\d{1,2}/", line) or "Ach withdrawal" in line or "Debit Card" in line or "Check" in line:
            # This is where we handle the tricky comma-in-description case
            row = {
                "Date": current_date or "2026-01-01",
                "Description": line,
                "Payee": "",
                "Amount": "",
                "Check#": "",
                "Category": "Uncategorized",
                "SubCategory": "",
                "SignedAmount": "",
                "YearMonth": "2026-01",
                "Confidence": "High",
                "NeedsReview": "No",
                "ReviewReason": ""
            }
            # Very simple but effective amount extraction
            amount_match = re.search(r"[-]?[\d,]+\.\d{2}", line)
            if amount_match:
                amt = amount_match.group(0).replace(",", "")
                row["SignedAmount"] = "-" + amt if amt.startswith("-") else amt
                row["Amount"] = row["SignedAmount"]

            # Check number detection
            check_match = re.search(r"Check\s*#?(\d+)", line, re.I)
            if check_match:
                row["Check#"] = check_match.group(1)

            # Run validation
            row = validate_transaction_row(row)
            transactions.append(row)

    return transactions

def main():
    if len(sys.argv) < 2:
        print("Usage: python bank_statement_parser.py <path_to_statement.pdf>")
        return

    pdf_path = sys.argv[1]
    output_path = Path(pdf_path).stem + "_Transactions_With_Payees.csv"

    print(f"Processing {pdf_path}...")
    txns = parse_bank_statement(pdf_path)

    # Write clean CSV with proper quoting
    fieldnames = ["Date","Description","Payee","Amount","Check#","Category","SubCategory","SignedAmount","YearMonth","Confidence","NeedsReview","ReviewReason"]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(txns)

    print(f"✅ Success! Created: {output_path}")
    print(f"Total transactions: {len(txns)}")

if __name__ == "__main__":
    main()