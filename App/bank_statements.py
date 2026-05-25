"""Bank statement upload + pipeline runner for Streamlit (Core Workstream #2 MVP)."""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from app_logging import log_event

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "Scripts"

UPLOAD_WORK_DIR = SCRIPTS_DIR / "_streamlit_bank_uploads"

CROPPED_CHECKS_DIR = SCRIPTS_DIR / "cropped_checks_final_dynamic"

CROPPER_SCRIPT = "smart_check_cropper_final_dynamic.py"

PARSER_SCRIPT = "bank-statement-parser.py"

PIPELINE_TIMEOUT_SEC = 600


CROPPER_SKIP_USER_MSG = (
    "Check image cropping skipped (optional feature). Continuing with transaction extraction..."
)

ZERO_TRANSACTIONS_MSG = (
    "No transactions were extracted from this PDF. The file may be a **scanned image** "
    "(no text layer), or the statement layout may not match the parser yet."
)

GROK_VISION_HINT = (
    "Try the **Grok Vision** skill: use **Export Raw Text** below (if any text was found), "
    "or upload statement images to Grok to produce a transaction list, then paste into CSV format."
)

# CSV column order — must stay in sync with Scripts/bank-statement-parser.py CSV_FIELDNAMES
# and the Power Query / Process-Statement.ps1 downstream workflow.
GROK_CSV_FIELDS = (
    "Date,Description,Payee,Amount,Check#,Category,SubCategory,SignedAmount,YearMonth,"
    "Confidence,NeedsReview,ReviewReason"
)


def build_grok_vision_prompt(
    client_name: str,
    pdf_filename: str,
    *,
    saved_pdf_path: Path | str | None = None,
    cropped_dir: Path | str | None = None,
    cropped_check_count: int | None = None,
    statement_period: str | None = None,
) -> str:
    """Return a copy-paste-ready Grok Vision prompt that mirrors the lightweight parser's CSV.

    Optimized for Laura's workflow: keeps the exact CSV column order so the Grok output
    can be saved directly as `<PDF_STEM>_Transactions_With_Payees.csv` for Process-Statement.ps1
    and the Power Query model.
    """

    client = (client_name or "").strip() or "(unknown client)"
    pdf = (pdf_filename or "").strip() or "(no file selected)"

    saved_line = ""
    if saved_pdf_path:
        saved_line = f"\n- Local PDF path: `{saved_pdf_path}`"

    checks_line = ""
    if cropped_dir and cropped_check_count:
        checks_line = (
            f"\n- Cropped check images available: **{cropped_check_count} file(s)** in "
            f"`{cropped_dir}` — please ALSO analyze these and match the check numbers, "
            "dates, payees, and amounts back to the Check Register rows."
        )
    elif cropped_dir:
        checks_line = (
            f"\n- Cropped check images folder (may be empty): `{cropped_dir}`. "
            "If you have check images, match check numbers/payees back to the Check Register."
        )

    period_line = f"\n- Statement period: **{statement_period}**" if statement_period else ""

    return f"""You are a meticulous bookkeeping assistant for SLAM Services LLC.
I am uploading a bank statement PDF for client **{client}**.

Context:
- PDF filename: `{pdf}`{saved_line}{period_line}{checks_line}

Task:
1. Read every page of the PDF (use vision/OCR — assume no text layer).
2. Extract **every** transaction from these sections (preserve sign — credits positive, debits/checks negative):
   - Deposits / Deposits and Other Credits
   - Electronic Credits (ACH IN, Zelle/Venmo received, wires in, mobile deposits)
   - Electronic Debits (ACH OUT, debit card, online bill pay, PayPal/Venmo out)
   - Check Register / Checks Paid
   - Service Charges / Fees
3. IGNORE the Daily Balance Summary table and the Account Summary block — those are running balances, not transactions.
4. For each transaction, separate the **transaction amount** from the **running balance** that often appears to its right. Use the transaction amount only.
5. Infer a Payee from the description when possible (e.g. "ACH DEPOSIT VENMO PAYMENT JOHN SMITH" → Payee = "John Smith").
6. Output ONLY a CSV (no commentary, no markdown fences) with this exact header:

{GROK_CSV_FIELDS}

Column rules:
- `Date` = YYYY-MM-DD (use the statement year if only MM/DD is shown).
- `Description` = trimmed, single line, no trailing balance numbers.
- `Payee` = inferred merchant / person / vendor (best effort; blank if unclear).
- `Amount` = signed decimal (no $ sign, no commas, two decimals).
- `Check#` = the check number for Check Register rows, blank otherwise.
- `Category` = `Uncategorized` (Laura will categorize in Power Query).
- `SubCategory` = blank.
- `SignedAmount` = same as `Amount`.
- `YearMonth` = `YYYY-MM` derived from Date.
- `Confidence` = `High` if you are sure, `Medium` if image was hard to read, `Low` for guesses.
- `NeedsReview` = `Yes` when Confidence is Medium or Low, otherwise `No`.
- `ReviewReason` = short note when NeedsReview is Yes; blank otherwise.

After the CSV, on a single final line, write:
TOTALS: deposits=<sum_positive> withdrawals=<sum_negative_abs> checks=<count> transactions=<total_count>

Save the CSV as `{Path(pdf).stem}_Transactions_With_Payees.csv` so I can drop it straight into Process-Statement.ps1.
"""


PipelineStatus = Literal["success", "partial", "error"]

_PARSER_MODULE = None


def _load_parser_module():
    global _PARSER_MODULE
    if _PARSER_MODULE is None:
        script = SCRIPTS_DIR / PARSER_SCRIPT
        spec = importlib.util.spec_from_file_location("slam_bank_statement_parser", script)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load parser from {script}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _PARSER_MODULE = mod
    return _PARSER_MODULE


def extract_pdf_raw_text(pdf_path: Path) -> str:
    """Extract statement text for debugging / Grok Vision (same logic as parser)."""
    return _load_parser_module().extract_pdf_text(str(pdf_path))


def scripts_available() -> tuple[bool, str]:

    if not SCRIPTS_DIR.is_dir():
        return False, f"Scripts folder not found at `{SCRIPTS_DIR}`"

    if not (SCRIPTS_DIR / PARSER_SCRIPT).is_file():
        return False, f"Missing `{PARSER_SCRIPT}` in Scripts/"

    return True, ""


def _safe_stem(filename: str) -> str:

    stem = Path(filename).stem

    return re.sub(r"[^\w\-.]", "_", stem) or "statement"


def expected_csv_path(pdf_path: Path) -> Path:

    return SCRIPTS_DIR / f"{pdf_path.stem}_Transactions_With_Payees.csv"


def _log(level: str, message: str) -> str:

    return f"[{level.upper()}] {message}"


def cropper_available() -> tuple[bool, str]:
    """Optional check cropper — never required for transaction extraction."""

    script = SCRIPTS_DIR / CROPPER_SCRIPT

    if not script.is_file():
        return False, "cropper script not found"

    try:
        import cv2  # noqa: F401

    except ImportError:
        return False, "opencv (cv2) not installed in this Python environment"

    return True, ""


def _subprocess_env() -> dict[str, str]:

    env = os.environ.copy()

    env.setdefault("PYTHONIOENCODING", "utf-8")

    return env


def _append_process_output(
    logs: list[str], proc: subprocess.CompletedProcess[str], *, tail: int
) -> None:

    if proc.stdout:
        lines = proc.stdout.strip().splitlines()

        logs.extend(lines[-tail:] if tail else lines)

    if proc.stderr:
        for line in proc.stderr.strip().splitlines()[-10:]:
            logs.append(_log("stderr", line))


def run_statement_pipeline(
    pdf_bytes: bytes,
    filename: str,
    logger,
    *,
    run_cropper: bool = True,
) -> tuple[pd.DataFrame | None, list[str], Path | None, dict[str, Any]]:
    """

    Save PDF under Scripts/, run cropper (optional) + parser, return transactions DF.

    Output CSV is written to Scripts/ cwd (matches Process-Statement.ps1 behavior).

    """

    logs: list[str] = []

    meta: dict[str, Any] = {
        "status": "error",
        "cropper_skipped": False,
        "cropper_user_message": None,
        "csv_path": None,
        "pdf_path": None,
        "cropped_dir": None,
        "cropped_check_count": 0,
    }

    ok, err = scripts_available()

    if not ok:
        logs.append(_log("error", err))

        return None, logs, None, meta

    UPLOAD_WORK_DIR.mkdir(parents=True, exist_ok=True)

    stem = _safe_stem(filename)

    pdf_path = UPLOAD_WORK_DIR / f"{stem}.pdf"

    pdf_path.write_bytes(pdf_bytes)

    meta["pdf_path"] = pdf_path

    logs.append(_log("info", f"Saved upload: {pdf_path.name}"))

    try:
        raw_text = extract_pdf_raw_text(pdf_path)
        meta["raw_text"] = raw_text
        meta["text_layer_found"] = bool(raw_text.strip())
        if not meta["text_layer_found"]:
            logs.append(
                _log(
                    "warn",
                    "No text layer in PDF (likely scanned). Parser may return 0 transactions.",
                )
            )
    except Exception as exc:
        meta["raw_text"] = ""
        meta["text_layer_found"] = False
        logs.append(_log("warn", f"PDF text preview failed: {exc}"))

    py = sys.executable

    cwd = str(SCRIPTS_DIR)

    env = _subprocess_env()

    cropper_issue = False

    if run_cropper:
        can_crop, crop_reason = cropper_available()

        if not can_crop:
            cropper_issue = True

            meta["cropper_skipped"] = True

            meta["cropper_user_message"] = CROPPER_SKIP_USER_MSG

            logs.append(_log("warn", f"Check cropper skipped: {crop_reason}."))

            logs.append(_log("info", "Continuing with transaction parser."))

        else:
            logs.append(_log("info", "--- Check cropper (optional) ---"))

            try:
                proc = subprocess.run(
                    [py, CROPPER_SCRIPT, str(pdf_path)],
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=PIPELINE_TIMEOUT_SEC,
                    check=False,
                    env=env,
                )

                _append_process_output(logs, proc, tail=20)

                if proc.returncode != 0:
                    cropper_issue = True

                    logs.append(_log("warn", "Cropper exited non-zero; continuing with parser."))

                else:
                    logs.append(_log("info", "Cropper finished."))
                    if CROPPED_CHECKS_DIR.is_dir():
                        cropped_files = sorted(CROPPED_CHECKS_DIR.glob("*.png"))
                        meta["cropped_dir"] = CROPPED_CHECKS_DIR
                        meta["cropped_check_count"] = len(cropped_files)
                        if cropped_files:
                            logs.append(
                                _log("info", f"Cropped {len(cropped_files)} check image(s).")
                            )

                log_event(logger, "bank_stmt_cropper", exit_code=proc.returncode)

            except subprocess.TimeoutExpired:
                cropper_issue = True

                logs.append(_log("warn", "Cropper timed out; continuing with parser."))

            except Exception as exc:
                cropper_issue = True

                logs.append(_log("warn", f"Cropper failed ({exc}); continuing with parser."))

            if cropper_issue:
                meta["cropper_skipped"] = True

                meta["cropper_user_message"] = CROPPER_SKIP_USER_MSG

    else:
        meta["cropper_skipped"] = True

        logs.append(_log("info", "Check cropper disabled for this run."))

    logs.append(_log("info", "--- Transaction parser ---"))

    try:
        proc = subprocess.run(
            [py, PARSER_SCRIPT, str(pdf_path)],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=PIPELINE_TIMEOUT_SEC,
            check=False,
            env=env,
        )

        _append_process_output(logs, proc, tail=0)

        log_event(
            logger,
            "bank_stmt_parser",
            exit_code=proc.returncode,
            pdf=pdf_path.name,
        )

        if proc.returncode != 0:
            logs.append(_log("error", f"Parser exited with code {proc.returncode}"))

            return None, logs, None, meta

    except subprocess.TimeoutExpired:
        logs.append(_log("error", "Parser timed out."))

        return None, logs, None, meta

    except Exception as exc:
        logs.append(_log("error", f"Parser failed: {exc}"))

        return None, logs, None, meta

    csv_path = expected_csv_path(pdf_path)

    if not csv_path.is_file():
        logs.append(_log("error", f"Expected CSV not found: {csv_path.name}"))

        return None, logs, None, meta

    logs.append(_log("ok", f"Created: {csv_path}"))

    meta["csv_path"] = csv_path

    try:
        df = pd.read_csv(csv_path)

    except Exception as exc:
        logs.append(_log("error", f"Could not read CSV: {exc}"))

        return None, logs, None, meta

    meta["transaction_count"] = len(df)
    if len(df) == 0:
        meta["status"] = "partial"
        logs.append(
            _log(
                "warn",
                "Parser finished but extracted 0 transactions. See zero-transaction guidance in app.",
            )
        )
    else:
        meta["status"] = "partial" if cropper_issue else "success"

    return df, logs, csv_path, meta


def format_processing_log(logs: list[str]) -> str:
    """Single block for the Processing log expander."""

    return "\n".join(logs)


def confidence_review_count(df: pd.DataFrame | None) -> int:
    """Rows where Confidence is not High (primary review signal)."""

    if df is None or df.empty:
        return 0

    n = 0

    if "Confidence" in df.columns:
        conf = df["Confidence"].astype(str).str.strip()

        n = int(((conf != "High") & (conf != "")).sum())

    if "NeedsReview" in df.columns:
        n = max(n, int((df["NeedsReview"].astype(str).str.lower() == "yes").sum()))

    elif "NeedsReviewFlag" in df.columns:
        n = max(n, int(df["NeedsReviewFlag"].fillna(False).astype(bool).sum()))

    return n


def filter_transactions_by_confidence(
    df: pd.DataFrame,
    confidence_level: str = "High",
) -> pd.DataFrame:
    """Return all rows when confidence_level is High/Show All; else Low/Medium only."""
    show_all = confidence_level in ("High", "Show All", "")
    if show_all or "Confidence" not in df.columns:
        return df

    conf = df["Confidence"].astype(str).str.strip()
    return df[(conf != "High") & (conf != "")].copy()


__all__ = [
    "CROPPED_CHECKS_DIR",
    "CROPPER_SKIP_USER_MSG",
    "GROK_CSV_FIELDS",
    "GROK_VISION_HINT",
    "UPLOAD_WORK_DIR",
    "ZERO_TRANSACTIONS_MSG",
    "build_grok_vision_prompt",
    "confidence_review_count",
    "cropper_available",
    "expected_csv_path",
    "extract_pdf_raw_text",
    "filter_transactions_by_confidence",
    "format_processing_log",
    "missing_document_counts",
    "run_statement_pipeline",
    "scripts_available",
    "style_low_confidence_rows",
    "transaction_summary_metrics",
]


def style_low_confidence_rows(df: pd.DataFrame):
    """Amber background for rows that need confidence review."""

    if df.empty or "Confidence" not in df.columns:

        def _empty(_row):

            return [""] * len(df.columns)

        return df.style.apply(_empty, axis=1)

    def _highlight(row: pd.Series):

        conf = str(row.get("Confidence", "High")).strip()

        if conf and conf != "High":
            return ["background-color: #fef3c7; color: #78350f"] * len(row)

        return [""] * len(row)

    return df.style.apply(_highlight, axis=1)


def transaction_summary_metrics(df: pd.DataFrame) -> dict[str, float | int]:
    """Deposits (credits) and withdrawals (debits) from SignedAmount or Amount."""

    if df is None or df.empty:
        return {
            "count": 0,
            "deposits": 0.0,
            "withdrawals": 0.0,
            "needs_review": 0,
        }

    amount_col = "SignedAmount" if "SignedAmount" in df.columns else "Amount"

    if amount_col not in df.columns:
        return {
            "count": len(df),
            "deposits": 0.0,
            "withdrawals": 0.0,
            "needs_review": confidence_review_count(df),
        }

    amounts = pd.to_numeric(
        df[amount_col].astype(str).str.replace(",", "", regex=False),
        errors="coerce",
    ).fillna(0.0)

    deposits = float(amounts[amounts > 0].sum())

    withdrawals = float(abs(amounts[amounts < 0].sum()))

    return {
        "count": len(df),
        "deposits": deposits,
        "withdrawals": withdrawals,
        "needs_review": confidence_review_count(df),
    }


def missing_document_counts(req_df: pd.DataFrame) -> dict[str, int]:
    """Counts for Missing Docs quick view (active Pending/Received only)."""

    if req_df is None or req_df.empty:
        return {"missing_bank": 0, "missing_sales": 0, "missing_either": 0, "missing_both": 0}

    active = req_df[req_df["status"].isin(["Pending", "Received"])].copy()

    if active.empty:
        return {"missing_bank": 0, "missing_sales": 0, "missing_either": 0, "missing_both": 0}

    no_bank = ~active["bank_statement_received"].fillna(False)

    no_sales = ~active["sales_report_received"].fillna(False)

    return {
        "missing_bank": int(no_bank.sum()),
        "missing_sales": int(no_sales.sum()),
        "missing_either": int((no_bank | no_sales).sum()),
        "missing_both": int((no_bank & no_sales).sum()),
    }
