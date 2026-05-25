"""Bank statement upload + pipeline runner for Streamlit (Core Workstream #2 MVP)."""

from __future__ import annotations

import base64
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
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

# Canonical column order for any DataFrame that flows downstream
# (parser output, Grok CSV paste/upload, Power Query, Process-Statement.ps1).
GROK_CSV_COLUMNS: tuple[str, ...] = (
    "Date",
    "Description",
    "Payee",
    "Amount",
    "Check#",
    "Category",
    "SubCategory",
    "SignedAmount",
    "YearMonth",
    "Confidence",
    "NeedsReview",
    "ReviewReason",
)

# Minimum columns Grok must produce for us to consider the paste/upload valid.
GROK_REQUIRED_COLUMNS: tuple[str, ...] = ("Date", "Description", "Amount")


# ---------------------------------------------------------------------------
# Persistent payee rules engine (v2.39) — Quick Parallel Win from Section 8.1
# ---------------------------------------------------------------------------
# Lightweight, QuickBooks-style mapping that learns from real usage. Rules live
# in `Data/payee_rules.csv` (gitignored) with the columns below. Matching is
# case-insensitive substring on the transaction Description, with optional full
# regex via a `re:` prefix on the pattern. Client-specific overrides win over
# global rules; on tie, the longest pattern wins. The engine is intentionally
# small (pandas + re only), defensive (missing file → no-op), and never
# overwrites a manually-curated Payee — only blanks or the raw description.

PAYEE_RULES_COLUMNS: tuple[str, ...] = (
    "pattern",
    "clean_payee",
    "suggested_category",
    "client_override",
    "notes",
    "last_used",
)

PAYEE_RULES_FILENAME = "payee_rules.csv"


def _payee_rules_candidate_paths() -> list[Path]:
    """Locations where `payee_rules.csv` may live, in precedence order."""

    app_dir = Path(__file__).resolve().parent
    repo_root = app_dir.parent

    candidates: list[Path] = []

    env_override = os.environ.get("SLAM_PAYEE_RULES_PATH", "").strip()
    if env_override:
        candidates.append(Path(env_override))

    bases = [repo_root, Path.cwd(), Path("/home/site/wwwroot"), app_dir]
    for base in bases:
        candidates.append(base / "Data" / PAYEE_RULES_FILENAME)

    seen: set[str] = set()
    unique: list[Path] = []
    for raw in candidates:
        key = str(raw)
        if key in seen:
            continue
        seen.add(key)
        unique.append(raw)
    return unique


def resolve_payee_rules_path(create_if_missing: bool = False) -> Path | None:
    """Return the first existing `payee_rules.csv`, optionally creating an empty seed file."""

    candidates = _payee_rules_candidate_paths()
    for path in candidates:
        try:
            if path.is_file():
                return path
        except OSError:
            continue

    if not create_if_missing:
        return candidates[0] if candidates else None

    for path in candidates:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                with path.open("w", encoding="utf-8", newline="") as fh:
                    fh.write(",".join(PAYEE_RULES_COLUMNS) + "\n")
            return path
        except OSError:
            continue
    return None


def load_payee_rules(path: Path | None = None) -> pd.DataFrame:
    """Load `payee_rules.csv` into a normalized DataFrame (empty when missing/blank)."""

    target = path or resolve_payee_rules_path(create_if_missing=False)
    empty = pd.DataFrame(columns=list(PAYEE_RULES_COLUMNS))
    if not target:
        return empty
    target = Path(target)
    if not target.is_file():
        return empty

    try:
        df = pd.read_csv(target, dtype=str, keep_default_na=False)
    except Exception:
        return empty

    for col in PAYEE_RULES_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    # Drop rows with blank pattern (header-only files yield zero rules)
    df["pattern"] = df["pattern"].astype(str).str.strip()
    df = df[df["pattern"] != ""].copy()

    return df[list(PAYEE_RULES_COLUMNS)].reset_index(drop=True)


def save_payee_rules(rules: pd.DataFrame, path: Path | None = None) -> Path | None:
    """Persist the rules DataFrame to disk (creates the file/folder when missing)."""

    target = path or resolve_payee_rules_path(create_if_missing=True)
    if not target:
        return None

    out = rules.copy() if rules is not None else pd.DataFrame()
    for col in PAYEE_RULES_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out = out[list(PAYEE_RULES_COLUMNS)]

    try:
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(target, index=False)
        return Path(target)
    except OSError:
        return None


def _compile_rule_pattern(pattern: str) -> re.Pattern[str] | None:
    """Compile a rule pattern. `re:` prefix → full regex, otherwise case-insensitive substring."""

    if not pattern:
        return None
    raw = pattern.strip()
    if not raw:
        return None
    try:
        if raw.lower().startswith("re:"):
            return re.compile(raw[3:].lstrip(), re.IGNORECASE)
        return re.compile(re.escape(raw), re.IGNORECASE)
    except re.error:
        return None


# Noise prefixes routinely found on bank-statement descriptions. Stripping these
# before suggesting a pattern lets us surface the actual merchant token instead
# of generic words like "POS" or "ACH" that would match every debit-card row.
# Order matters: longer prefixes first so we don't half-strip a phrase.
_PAYEE_NOISE_PREFIXES: tuple[str, ...] = (
    "DEBIT CARD PURCHASE",
    "CHECK CARD PURCHASE",
    "POS DEBIT PURCHASE",
    "POS PURCHASE",
    "POS DEBIT",
    "ACH DEBIT",
    "ACH CREDIT",
    "ACH DEPOSIT",
    "ACH WITHDRAWAL",
    "ACH PAYMENT",
    "ELECTRONIC DEBIT",
    "ELECTRONIC CREDIT",
    "ELECTRONIC WITHDRAWAL",
    "ELECTRONIC DEPOSIT",
    "ONLINE BANKING TRANSFER",
    "ONLINE BANKING",
    "ONLINE PAYMENT",
    "MOBILE DEPOSIT",
    "EXTERNAL TRANSFER",
    "INTERNAL TRANSFER",
    "ATM WITHDRAWAL",
    "ATM DEPOSIT",
    "WIRE TRANSFER",
    "BILL PAYMENT",
    "CHECK #",
    "CHECK#",
    "WITHDRAWAL",
    "DEPOSIT",
)

# Tokens that indicate the merchant portion is over (location codes, store #s,
# transaction IDs, dates embedded in the description). We trim everything from
# the first such token onwards when suggesting a pattern.
_PAYEE_STOP_TOKEN_RE = re.compile(
    r"""(?ix)
    (
        \#?\d{2,}                                # STORE #1234, 123456
      | \b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b         # 06/15 or 6/15/26
      | \b(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY)\b
      | \bUS[A]?\b
    )
    """
)


def suggest_payee_pattern(description: str, *, max_length: int = 32) -> str:
    """Suggest a sensible match pattern for the Learn-this-mapping form.

    Strips common noise prefixes (POS PURCHASE, ACH DEBIT, etc.), trims trailing
    location codes / store numbers / dates, and returns a bounded substring that
    captures the merchant portion. Falls back to the first non-empty token when
    the description doesn't contain a clear merchant signal (e.g. "CHECK 2473").

    The result is intentionally a substring (not regex). The Learn form treats
    it as a default that Laura can edit before saving — the goal is to save her
    keystrokes on the common cases, not to be perfect.
    """

    if not description:
        return ""
    cleaned = " ".join(str(description).split()).strip()
    if not cleaned:
        return ""

    # Strip a single recognized noise prefix (longest match wins).
    upper = cleaned.upper()
    for prefix in _PAYEE_NOISE_PREFIXES:
        if upper.startswith(prefix):
            cleaned = cleaned[len(prefix) :].lstrip(" -:#*")
            break

    if not cleaned:
        cleaned = " ".join(str(description).split()).strip()

    # Trim at the first stop token (store #, date, state code) — keeps "WAL-MART"
    # but drops "STORE #1234 GARDENDALE AL".
    stop_match = _PAYEE_STOP_TOKEN_RE.search(cleaned)
    if stop_match and stop_match.start() > 0:
        cleaned = cleaned[: stop_match.start()].strip(" -:#*,")

    # Bound the length so the default stays readable in the text input.
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip(" -:#*,")

    if not cleaned:
        # Fallback: first non-empty token from the original description.
        for token in str(description).split():
            stripped = token.strip(" -:#*,")
            if stripped:
                return stripped[:max_length]
        return ""

    return cleaned


def count_pattern_matches(
    df: pd.DataFrame | None,
    pattern: str,
    client_name: str | None = None,
) -> int:
    """Count rows in ``df`` whose Description would match the given rule pattern.

    Powers the live "this pattern would affect X rows" preview in the Learn form.
    Uses the same compilation rules as :func:`apply_payee_rules` (case-insensitive
    substring by default, full regex with ``re:`` prefix). ``client_name`` is
    accepted for symmetry with the rules engine but currently doesn't filter the
    DataFrame — the preview always counts against the open statement.
    """

    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return 0
    if "Description" not in df.columns:
        return 0
    matcher = _compile_rule_pattern(pattern)
    if matcher is None:
        return 0
    try:
        return int(df["Description"].astype(str).str.contains(matcher, regex=True, na=False).sum())
    except re.error:
        return 0


def _relative_last_used(value: str) -> str:
    """Render a `last_used` ISO date as a friendly relative string for the Library view."""

    raw = (value or "").strip()
    if not raw:
        return "—"
    try:
        when = datetime.strptime(raw[:10], "%Y-%m-%d")
    except ValueError:
        return raw
    days = (datetime.now().date() - when.date()).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    if days < 30:
        weeks = days // 7
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"
    if days < 365:
        months = days // 30
        return f"{months} month{'s' if months != 1 else ''} ago"
    return raw


def rules_library_summary(
    rules_df: pd.DataFrame | None,
    *,
    client_name: str | None = None,
    scope: str = "All",
    sort_by: str = "Recently used",
    limit: int = 25,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Return a display-ready DataFrame for the Rules Library expander plus summary counts.

    ``scope`` is one of ``"All"``, ``"Global only"``, or ``"Client only"`` (the
    latter filters to ``client_override == client_name``). ``sort_by`` is one of
    ``"Recently used"`` (default), ``"Most specific"`` (longest pattern first),
    or ``"Alphabetical"`` (pattern ascending).

    The returned summary dict has keys ``total``, ``client_specific``, and
    ``used_30d`` so the UI can render a one-line "X total · Y client-specific ·
    Z used in last 30 days" caption above the table.
    """

    empty_view = pd.DataFrame(
        columns=["Pattern", "Clean Payee", "Suggested Category", "Scope", "Last used"]
    )
    summary = {"total": 0, "client_specific": 0, "used_30d": 0}

    if rules_df is None or not isinstance(rules_df, pd.DataFrame) or rules_df.empty:
        return empty_view, summary

    df = rules_df.copy()
    for col in PAYEE_RULES_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df["client_override"] = df["client_override"].astype(str).str.strip()
    df["pattern"] = df["pattern"].astype(str).str.strip()
    df = df[df["pattern"] != ""].copy()

    summary["total"] = int(len(df))
    summary["client_specific"] = int((df["client_override"] != "").sum())

    # 30-day usage count uses the master file (unfiltered) so the headline stays stable.
    cutoff = datetime.now().date()
    used_30d = 0
    for raw in df["last_used"].astype(str):
        raw = raw.strip()
        if not raw:
            continue
        try:
            when = datetime.strptime(raw[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if (cutoff - when).days <= 30:
            used_30d += 1
    summary["used_30d"] = used_30d

    # Scope filter
    scope_norm = (scope or "All").strip().lower()
    if scope_norm in ("global", "global only"):
        df = df[df["client_override"] == ""].copy()
    elif scope_norm in ("client", "client only") and client_name:
        df = df[df["client_override"].str.lower() == client_name.strip().lower()].copy()

    if df.empty:
        return empty_view, summary

    # Sort
    sort_norm = (sort_by or "Recently used").strip().lower()
    if sort_norm.startswith("most specific"):
        df["_plen"] = df["pattern"].str.len()
        df = df.sort_values(by=["_plen", "pattern"], ascending=[False, True])
        df = df.drop(columns=["_plen"])
    elif sort_norm.startswith("alphabet"):
        df = df.sort_values(by="pattern", ascending=True)
    else:
        # Recently used (default) — empty last_used sinks to the bottom.
        df["_lu"] = pd.to_datetime(df["last_used"].astype(str).str[:10], errors="coerce")
        df = df.sort_values(by="_lu", ascending=False, na_position="last")
        df = df.drop(columns=["_lu"])

    if limit and limit > 0:
        df = df.head(limit)

    view = pd.DataFrame(
        {
            "Pattern": df["pattern"].astype(str),
            "Clean Payee": df["clean_payee"].astype(str),
            "Suggested Category": df["suggested_category"].astype(str),
            "Scope": df["client_override"].astype(str).where(df["client_override"] != "", "Global"),
            "Last used": df["last_used"].astype(str).map(_relative_last_used),
        }
    ).reset_index(drop=True)
    return view, summary


def apply_payee_rules(
    df: pd.DataFrame,
    client_name: str | None = None,
    rules: pd.DataFrame | None = None,
    *,
    touch_last_used: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply the persistent payee rules to a transactions DataFrame.

    Behavior:
    - Loads `Data/payee_rules.csv` when `rules` is not provided.
    - For each rule, finds rows whose `Description` matches the pattern (case-insensitive
      substring by default, full regex when the pattern starts with ``re:``).
    - Overwrites `Payee` only when the existing value is blank OR equal to the raw
      `Description` (i.e. Grok's fall-back). Manual edits are preserved.
    - Overwrites `Category` only when blank or `Uncategorized` so Laura's downstream
      Power Query work is never clobbered.
    - Client-specific rules (matching `client_override`) win over global rules; on tie,
      the longest pattern wins.
    - When ``touch_last_used`` is True, refreshes the `last_used` ISO date on rules
      that fired and silently writes the file back (best-effort; never fatal).

    Returns ``(out_df, info)`` where ``info`` has keys ``rows_changed``, ``rules_used``,
    ``rules_total``, and ``source_path``.
    """

    info: dict[str, Any] = {
        "rows_changed": 0,
        "rules_used": 0,
        "rules_total": 0,
        "source_path": None,
    }

    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df, info

    if rules is None:
        path = resolve_payee_rules_path(create_if_missing=False)
        info["source_path"] = str(path) if path else None
        rules = load_payee_rules(path)

    info["rules_total"] = len(rules)
    if rules.empty or "Description" not in df.columns:
        return df, info

    out = df.copy()
    if "Payee" not in out.columns:
        out["Payee"] = ""
    if "Category" not in out.columns:
        out["Category"] = "Uncategorized"

    desc_series = out["Description"].astype(str)
    payee_series = out["Payee"].astype(str).str.strip()
    category_series = out["Category"].astype(str).str.strip().str.lower()

    # Filter: keep rules with no client_override OR matching the current client
    client_lc = (client_name or "").strip().lower()
    rules_view = rules.copy()
    rules_view["client_override"] = rules_view["client_override"].astype(str).str.strip()
    keep_mask = rules_view["client_override"].apply(lambda v: (not v) or (v.lower() == client_lc))
    rules_view = rules_view[keep_mask].copy()
    if rules_view.empty:
        return out, info

    # Sort: client-specific first, then longest pattern (more specific wins on overlap)
    rules_view["_is_specific"] = (rules_view["client_override"] != "").astype(int)
    rules_view["_plen"] = rules_view["pattern"].astype(str).str.len()
    rules_view = rules_view.sort_values(by=["_is_specific", "_plen"], ascending=[False, False])

    matched_any = pd.Series(False, index=out.index)
    fired_patterns: set[str] = set()

    for _, rule in rules_view.iterrows():
        pattern = str(rule.get("pattern") or "").strip()
        matcher = _compile_rule_pattern(pattern)
        if matcher is None:
            continue

        try:
            row_match = desc_series.str.contains(matcher, regex=True, na=False)
        except re.error:
            continue
        if not row_match.any():
            continue

        clean_payee = str(rule.get("clean_payee") or "").strip()
        suggested_category = str(rule.get("suggested_category") or "").strip()

        # Preserve manual edits: only overwrite Payee when blank OR equal to description
        if clean_payee:
            overwrite_payee = row_match & (
                payee_series.eq("") | payee_series.eq(desc_series.str.strip())
            )
            if overwrite_payee.any():
                out.loc[overwrite_payee, "Payee"] = clean_payee
                payee_series = out["Payee"].astype(str).str.strip()

        # Overwrite Category only when blank / Uncategorized
        if suggested_category:
            overwrite_cat = row_match & category_series.isin(["", "uncategorized"])
            if overwrite_cat.any():
                out.loc[overwrite_cat, "Category"] = suggested_category
                category_series = out["Category"].astype(str).str.strip().str.lower()

        if clean_payee or suggested_category:
            matched_any = matched_any | row_match
            fired_patterns.add(pattern)

    info["rows_changed"] = int(matched_any.sum())
    info["rules_used"] = len(fired_patterns)

    # Best-effort: bump last_used on rules that fired so Laura sees real usage
    if touch_last_used and fired_patterns:
        try:
            master = load_payee_rules()
            if not master.empty:
                today_iso = datetime.now().strftime("%Y-%m-%d")
                touched = master["pattern"].astype(str).isin(fired_patterns)
                if touched.any():
                    master.loc[touched, "last_used"] = today_iso
                    save_payee_rules(master)
        except Exception:
            pass

    return out, info


def upsert_payee_rule(
    pattern: str,
    clean_payee: str,
    suggested_category: str = "",
    client_override: str = "",
    notes: str = "",
) -> tuple[bool, Path | None]:
    """Add or update a single rule in `payee_rules.csv` (creates the file when missing).

    Uniqueness is `(pattern, client_override)` — same pattern can have a global rule plus
    per-client overrides. Returns ``(success, path)``.
    """

    pattern_clean = (pattern or "").strip()
    if not pattern_clean:
        return False, None

    rules = load_payee_rules()
    if rules.empty:
        rules = pd.DataFrame(columns=list(PAYEE_RULES_COLUMNS))

    co_clean = (client_override or "").strip()
    today_iso = datetime.now().strftime("%Y-%m-%d")

    pattern_col = rules["pattern"].astype(str).str.strip()
    co_col = rules["client_override"].astype(str).str.strip().str.lower()
    existing = rules.index[(pattern_col == pattern_clean) & (co_col == co_clean.lower())]

    if len(existing) > 0:
        idx = existing[0]
        rules.at[idx, "clean_payee"] = clean_payee or rules.at[idx, "clean_payee"]
        if suggested_category:
            rules.at[idx, "suggested_category"] = suggested_category
        if notes:
            rules.at[idx, "notes"] = notes
        rules.at[idx, "last_used"] = today_iso
    else:
        new_row = {
            "pattern": pattern_clean,
            "clean_payee": (clean_payee or "").strip(),
            "suggested_category": (suggested_category or "").strip(),
            "client_override": co_clean,
            "notes": (notes or "").strip(),
            "last_used": today_iso,
        }
        rules = pd.concat([rules, pd.DataFrame([new_row])], ignore_index=True)

    path = save_payee_rules(rules)
    return path is not None, path


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

Common failure modes to avoid (these are the three I see most often):
- DUAL AMOUNTS: When a row has two numbers (the transaction amount AND a running balance to its right),
  use the LEFT/transaction amount only. The rightmost number is the post-transaction balance and is
  NOT a transaction. Example: `01/15 WAL-MART STORE #1234 250.00 6,079.01` → Amount is `-250.00`, NOT `-6079.01`.
- CHECK REGISTER: Rows like `2473 * 01/15 250.00 6,079.01` are check entries. Set `Check#` = `2473`,
  `Date` = `01/15` (formatted to `YYYY-MM-DD` with the statement year), `Amount` = `-250.00` (checks
  are always debits — negative), and ignore the trailing balance (`6,079.01`).
- MULTI-PAGE: Read every page of the PDF. Do not stop at page 1. The Check Register section often
  starts on page 2 or 3, and Electronic Debits / Service Charges frequently spill onto a later page.
  Include ALL transactions from ALL pages in a single CSV.

After the CSV, on a single final line, write:
TOTALS: deposits=<sum_positive> withdrawals=<sum_negative_abs> checks=<count> transactions=<total_count>

Save the CSV as `{Path(pdf).stem}_Transactions_With_Payees.csv` so I can drop it straight into Process-Statement.ps1.

Note: after import, SLAM Services' Bank Statements page will automatically apply a persistent
payee rules engine (`Data/payee_rules.csv`) that cleans common merchant names and suggests
categories (e.g. `WAL-MART STORE #1234` → `Walmart` / `Supplies`). Your best-effort Payee /
Category values are still very helpful — the rules engine refines them, never replaces them.
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


def _strip_grok_csv_noise(text: str) -> str:
    """Remove the trailing TOTALS line and any stray markdown fences Grok sometimes emits."""

    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("```")]

    cleaned: list[str] = []
    for ln in lines:
        stripped = ln.strip()
        # Drop the TOTALS summary line Grok adds at the end of the CSV.
        if stripped.lower().startswith("totals:"):
            continue
        # Drop empty trailing/leading lines but keep blanks inside the CSV body
        # (pd.read_csv handles them).
        cleaned.append(ln)

    # Trim leading blank lines that would confuse pd.read_csv header detection.
    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)

    return "\n".join(cleaned).strip() + "\n"


# Grok emits one summary line at the very end of the CSV in the form:
#   TOTALS: deposits=1234.56 withdrawals=250.00 checks=1 transactions=2
# We capture this BEFORE _strip_grok_csv_noise removes it so we can use it
# as a reconciliation anchor against the detailed rows.
_GROK_TOTALS_RE = re.compile(r"(?im)^\s*TOTALS\s*:\s*(?P<body>.+?)\s*$")
_GROK_TOTALS_KV_RE = re.compile(
    r"(?i)\b(deposits|withdrawals|checks|transactions)\s*=\s*([-+]?\d+(?:\.\d+)?)"
)


def _parse_grok_totals_line(text: str) -> dict[str, float | int | None] | None:
    """Extract Grok's trailing ``TOTALS: deposits=... withdrawals=... checks=... transactions=...`` line.

    Returns a dict with keys ``deposits``, ``withdrawals`` (floats), ``checks``,
    ``transactions`` (ints), or ``None`` when the marker is absent. Any individual
    field that is missing from the line is set to ``None`` so callers can detect
    partial reports.
    """

    if not text:
        return None

    matches = list(_GROK_TOTALS_RE.finditer(text))
    if not matches:
        return None

    # Use the LAST occurrence (Grok always appends it at the end of the CSV).
    body = matches[-1].group("body")

    parsed: dict[str, float | int | None] = {
        "deposits": None,
        "withdrawals": None,
        "checks": None,
        "transactions": None,
    }
    for key, raw_value in _GROK_TOTALS_KV_RE.findall(body):
        key_lc = key.lower()
        try:
            num = float(raw_value)
        except ValueError:
            continue
        if key_lc in ("checks", "transactions"):
            parsed[key_lc] = int(round(num))
        else:
            parsed[key_lc] = num

    if all(v is None for v in parsed.values()):
        return None

    return parsed


def _coerce_amount_series(s: pd.Series) -> pd.Series:
    """Normalize a money-ish column to float (strips $, commas, blanks)."""

    return pd.to_numeric(
        s.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.strip(),
        errors="coerce",
    ).fillna(0.0)


def _coerce_yes_no(s: pd.Series) -> pd.Series:
    """Normalize a boolean-ish review flag to 'Yes' / 'No' strings."""

    truthy = {"yes", "y", "true", "1", "needs review"}
    return s.astype(str).str.strip().str.lower().map(lambda v: "Yes" if v in truthy else "No")


def load_grok_vision_csv(
    source: str | bytes | Any,
) -> tuple[pd.DataFrame, dict[str, float | int | None] | None]:
    """Parse a Grok Vision CSV (pasted text, uploaded file, or raw bytes) into a normalized DataFrame.

    Accepts:
    - A pasted string of CSV text (with or without the trailing ``TOTALS:`` summary line).
    - Raw ``bytes`` (e.g. from ``UploadedFile.getvalue()``).
    - A Streamlit ``UploadedFile`` / any file-like object exposing ``getvalue()`` or ``read()``.

    Returns a 2-tuple ``(df, grok_totals)``:
    - ``df``: DataFrame with columns matching :data:`GROK_CSV_COLUMNS` (same shape as the
      lightweight parser output). Missing columns are filled with safe defaults so the result
      drops straight into the Bank Statements review UI and downstream Power Query workflow.
    - ``grok_totals``: dict with ``deposits``, ``withdrawals`` (floats), ``checks``,
      ``transactions`` (ints) parsed from Grok's trailing ``TOTALS:`` summary line, or
      ``None`` when the line is absent. Used by :func:`reconcile_statement_totals` to
      cross-check the detailed rows against Grok's own self-reported summary.

    Raises ``ValueError`` with a clear, user-facing message when the input cannot be parsed
    or is missing required columns.
    """

    # --- Resolve input → text ---
    if source is None:
        raise ValueError("No CSV text or file provided.")

    text: str
    if isinstance(source, str):
        text = source
    elif isinstance(source, (bytes, bytearray)):
        text = bytes(source).decode("utf-8-sig", errors="replace")
    elif hasattr(source, "getvalue"):
        raw = source.getvalue()
        text = (
            raw.decode("utf-8-sig", errors="replace")
            if isinstance(raw, (bytes, bytearray))
            else str(raw)
        )
    elif hasattr(source, "read"):
        raw = source.read()
        text = (
            raw.decode("utf-8-sig", errors="replace")
            if isinstance(raw, (bytes, bytearray))
            else str(raw)
        )
    else:
        raise ValueError("Unsupported CSV source — expected text, bytes, or an uploaded file.")

    # Capture Grok's trailing TOTALS line BEFORE _strip_grok_csv_noise removes it,
    # so reconcile_statement_totals can use it as the reconciliation anchor.
    grok_totals = _parse_grok_totals_line(text)

    cleaned = _strip_grok_csv_noise(text)
    if not cleaned.strip():
        raise ValueError("CSV is empty — nothing to parse.")

    # --- Read CSV ---
    # Real-world Grok output sometimes contains unquoted commas inside the
    # Description/Payee fields (e.g. "AMAZON.COM*XX1, INC"), which breaks the
    # default C parser with "Expected 12 fields in line X, saw Y". The python
    # engine plus QUOTE_NONE + on_bad_lines='warn' makes the read tolerant of
    # those rows while preserving the rest of the CSV.
    try:
        df = pd.read_csv(
            io.StringIO(cleaned),
            dtype=str,
            keep_default_na=False,
            engine="python",  # More tolerant of embedded commas
            on_bad_lines="warn",  # Don't crash on malformed lines
            quoting=3,  # csv.QUOTE_NONE — treat commas literally
        )
    except Exception as exc:
        raise ValueError(
            f"Could not read CSV — most likely due to commas inside Description/Payee fields. "
            f"Try re-copying the full output from Grok (include the TOTALS line). "
            f"Original error: {exc}"
        ) from exc

    if df.empty:
        raise ValueError("No transactions found in the CSV (header only).")

    # --- Validate header ---
    df.columns = [c.strip() for c in df.columns]
    missing_required = [c for c in GROK_REQUIRED_COLUMNS if c not in df.columns]
    if missing_required:
        raise ValueError(
            "CSV must contain the Grok Vision header. Missing required column(s): "
            + ", ".join(missing_required)
            + ". Expected header: "
            + GROK_CSV_FIELDS
        )

    # --- Fill missing optional columns with safe defaults ---
    defaults: dict[str, str] = {
        "Payee": "",
        "Check#": "",
        "Category": "Uncategorized",
        "SubCategory": "",
        "SignedAmount": "",
        "YearMonth": "",
        "Confidence": "High",
        "NeedsReview": "No",
        "ReviewReason": "",
    }
    for col, default in defaults.items():
        if col not in df.columns:
            df[col] = default

    # --- Normalize types ---
    df["Date"] = df["Date"].astype(str).str.strip()
    df["Description"] = df["Description"].astype(str).str.strip()
    df["Payee"] = df["Payee"].astype(str).str.strip()
    df["Check#"] = df["Check#"].astype(str).str.strip()
    df["Category"] = df["Category"].astype(str).str.strip().replace("", "Uncategorized")
    df["SubCategory"] = df["SubCategory"].astype(str).str.strip()
    df["Confidence"] = df["Confidence"].astype(str).str.strip().str.title().replace("", "High")
    df["ReviewReason"] = df["ReviewReason"].astype(str).str.strip()

    df["Amount"] = _coerce_amount_series(df["Amount"])
    # If SignedAmount is missing/blank, mirror Amount (matches Grok prompt rules).
    signed_raw = df["SignedAmount"].astype(str).str.strip()
    signed_numeric = _coerce_amount_series(df["SignedAmount"])
    df["SignedAmount"] = signed_numeric.where(signed_raw != "", df["Amount"])

    # Derive YearMonth from Date when missing.
    ym = df["YearMonth"].astype(str).str.strip()
    parsed_dates = pd.to_datetime(df["Date"], errors="coerce")
    derived_ym = parsed_dates.dt.strftime("%Y-%m").fillna("")
    df["YearMonth"] = ym.where(ym != "", derived_ym)

    # NeedsReview: respect explicit value, else derive from Confidence (Medium/Low → Yes).
    nr_raw = df["NeedsReview"].astype(str).str.strip()
    nr_normalized = _coerce_yes_no(nr_raw)
    conf_implies_review = df["Confidence"].isin(["Medium", "Low"]).map({True: "Yes", False: "No"})
    df["NeedsReview"] = nr_normalized.where(nr_raw != "", conf_implies_review)

    # Drop rows where every required field is blank (defensive — Grok rarely emits these).
    blank_mask = (df["Date"] == "") & (df["Description"] == "") & (df["Amount"] == 0.0)
    df = df.loc[~blank_mask].copy()

    # --- Reorder to canonical column order, keeping any extras at the end ---
    extras = [c for c in df.columns if c not in GROK_CSV_COLUMNS]
    df = df[list(GROK_CSV_COLUMNS) + extras]

    return df.reset_index(drop=True), grok_totals


__all__ = [
    "AZURE_OCR_FUNCTION_KEY_ENV",
    "AZURE_OCR_FUNCTION_URL_ENV",
    "AZURE_OCR_TIMEOUT_SEC",
    "CROPPED_CHECKS_DIR",
    "CROPPER_SKIP_USER_MSG",
    "GROK_CSV_COLUMNS",
    "GROK_CSV_FIELDS",
    "GROK_REQUIRED_COLUMNS",
    "GROK_VISION_HINT",
    "LOCAL_ENHANCED_OCR_VERSION",
    "PAYEE_RULES_COLUMNS",
    "PAYEE_RULES_FILENAME",
    "PIVOT_GROUP_BY_OPTIONS",
    "PIVOT_VALUE_KIND_OPTIONS",
    "RECONCILIATION_AMOUNT_TOLERANCE",
    "UPLOAD_WORK_DIR",
    "ZERO_TRANSACTIONS_MSG",
    "apply_payee_rules",
    "azure_ocr_configured",
    "azure_ocr_status",
    "build_grok_vision_prompt",
    "build_statement_pivot",
    "confidence_review_count",
    "count_pattern_matches",
    "cropper_available",
    "expected_csv_path",
    "extract_pdf_raw_text",
    "filter_transactions_by_confidence",
    "format_processing_log",
    "load_grok_vision_csv",
    "load_payee_rules",
    "local_enhanced_ocr_available",
    "missing_document_counts",
    "reconcile_statement_totals",
    "resolve_payee_rules_path",
    "rules_library_summary",
    "run_azure_ocr_pipeline",
    "run_local_enhanced_ocr_pipeline",
    "run_statement_pipeline",
    "save_payee_rules",
    "scripts_available",
    "style_low_confidence_rows",
    "suggest_payee_pattern",
    "transaction_summary_metrics",
    "upsert_payee_rule",
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


def _checks_count(df: pd.DataFrame) -> int:
    """Count rows that look like Check Register entries (non-blank Check# field)."""

    if df is None or df.empty or "Check#" not in df.columns:
        return 0

    s = df["Check#"].astype(str).str.strip()
    return int((s != "").sum())


# ---------------------------------------------------------------------------
# In-app pivot summary (v2.40) — first step toward reducing Power Query reliance
# ---------------------------------------------------------------------------
# `build_statement_pivot()` aggregates the current statement's transactions by
# Category or Payee across YearMonth columns using pandas.pivot_table. The
# Bank Statements page renders it directly below the transaction editor so
# Laura can see the high-level picture without opening Excel. The existing
# "Download transactions CSV" button stays in place as the Power Query safety
# net — the pivot is additive, never a replacement.

PIVOT_GROUP_BY_OPTIONS: tuple[str, ...] = ("Category", "Payee")
PIVOT_VALUE_KIND_OPTIONS: tuple[str, ...] = ("sum", "count")


def build_statement_pivot(
    df: pd.DataFrame | None,
    *,
    group_by: str = "Category",
    value_kind: str = "sum",
    uncategorized_only: bool = False,
) -> pd.DataFrame:
    """Aggregate the current statement into a Category-or-Payee × YearMonth pivot.

    - ``group_by``: ``"Category"`` (default) or ``"Payee"`` — the row index.
    - ``value_kind``: ``"sum"`` (signed dollar total per cell) or ``"count"``
      (transaction count per cell).
    - ``uncategorized_only``: when True, filters to rows whose Category is blank
      or literally ``Uncategorized`` so Laura can spot what still needs labels.

    Returns a DataFrame with one row per ``group_by`` value, one column per
    YearMonth, plus a trailing ``Total`` column sorted descending by absolute
    total. Returns an empty DataFrame when the source is empty/missing — the
    caller can render a friendly "no data" caption.
    """

    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()

    group_col = group_by if group_by in PIVOT_GROUP_BY_OPTIONS else "Category"
    kind = value_kind if value_kind in PIVOT_VALUE_KIND_OPTIONS else "sum"

    if group_col not in df.columns:
        return pd.DataFrame()

    work = df.copy()

    # Normalize the row-index column so blanks don't fragment the pivot.
    work[group_col] = work[group_col].astype(str).str.strip()
    if group_col == "Category":
        work.loc[work[group_col] == "", group_col] = "Uncategorized"
    else:
        work.loc[work[group_col] == "", group_col] = "(no payee)"

    if uncategorized_only:
        if "Category" not in work.columns:
            return pd.DataFrame()
        cat_norm = work["Category"].astype(str).str.strip().str.lower()
        work = work[cat_norm.isin(["", "uncategorized"])].copy()
        if work.empty:
            return pd.DataFrame()

    # Ensure we have a YearMonth column; derive from Date when missing/blank.
    if "YearMonth" not in work.columns:
        work["YearMonth"] = ""
    ym = work["YearMonth"].astype(str).str.strip()
    parsed_dates = pd.to_datetime(work.get("Date", ""), errors="coerce")
    derived_ym = parsed_dates.dt.strftime("%Y-%m").fillna("")
    work["YearMonth"] = ym.where(ym != "", derived_ym)
    work.loc[work["YearMonth"] == "", "YearMonth"] = "(no date)"

    # Choose the numeric column. SignedAmount is preferred (preserves debit sign);
    # fall back to Amount when missing so older CSVs still work.
    amount_col = "SignedAmount" if "SignedAmount" in work.columns else "Amount"
    if amount_col not in work.columns:
        return pd.DataFrame()
    work[amount_col] = pd.to_numeric(
        work[amount_col]
        .astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False),
        errors="coerce",
    ).fillna(0.0)

    if kind == "count":
        pivot = pd.pivot_table(
            work,
            index=group_col,
            columns="YearMonth",
            values=amount_col,
            aggfunc="count",
            fill_value=0,
        )
        pivot = pivot.astype(int)
        pivot["Total"] = pivot.sum(axis=1).astype(int)
        pivot = pivot.sort_values(by="Total", ascending=False)
    else:
        pivot = pd.pivot_table(
            work,
            index=group_col,
            columns="YearMonth",
            values=amount_col,
            aggfunc="sum",
            fill_value=0.0,
        )
        pivot = pivot.astype(float)
        pivot["Total"] = pivot.sum(axis=1).astype(float)
        # Sort by absolute total so the biggest movers (positive or negative) surface first.
        pivot = pivot.assign(_abs=pivot["Total"].abs()).sort_values(by="_abs", ascending=False)
        pivot = pivot.drop(columns=["_abs"])

    return pivot


# Penny-level tolerance for comparing reported vs. computed dollar totals.
RECONCILIATION_AMOUNT_TOLERANCE = 0.01


def reconcile_statement_totals(df: pd.DataFrame, grok_totals: dict | None = None) -> dict[str, Any]:
    """Compare computed totals from detailed rows against Grok's reported TOTALS line.

    Returns dict with match status, differences, and reconciliation message for UI.

    Status values:
    - ``"match"``         — every reported field equals the computed value within tolerance.
    - ``"mismatch"``      — at least one reported field differs from computed; ``needs_review``
                            is set to True so the UI can flag the entire statement.
    - ``"no_reference"``  — no Grok TOTALS line was provided (parser path or older Grok output);
                            reconciliation is skipped and the detailed totals stand on their own.
    """

    metrics = transaction_summary_metrics(df)
    computed: dict[str, Any] = {
        "deposits": float(metrics["deposits"]),
        "withdrawals": float(metrics["withdrawals"]),
        "transactions": int(metrics["count"]),
        "checks": _checks_count(df),
    }

    if not grok_totals:
        return {
            "status": "no_reference",
            "message": (
                "No source TOTALS line available — reconciliation cross-check skipped. "
                "Detailed transactions stand on their own."
            ),
            "differences": {},
            "needs_review": False,
            "computed": computed,
            "reported": None,
        }

    differences: dict[str, dict[str, Any]] = {}
    for key in ("deposits", "withdrawals", "checks", "transactions"):
        reported = grok_totals.get(key)
        if reported is None:
            continue
        if key in ("deposits", "withdrawals"):
            comp_val = float(computed[key])
            rep_val = float(reported)
            diff = comp_val - rep_val
            if abs(diff) > RECONCILIATION_AMOUNT_TOLERANCE:
                differences[key] = {
                    "reported": rep_val,
                    "computed": comp_val,
                    "diff": diff,
                }
        else:
            comp_val = int(computed[key])
            rep_val = int(reported)
            diff = comp_val - rep_val
            if diff != 0:
                differences[key] = {
                    "reported": rep_val,
                    "computed": comp_val,
                    "diff": diff,
                }

    if not differences:
        message = (
            f"All four totals match the source statement — "
            f"deposits ${computed['deposits']:,.2f} · "
            f"withdrawals ${computed['withdrawals']:,.2f} · "
            f"checks {computed['checks']} · "
            f"transactions {computed['transactions']}."
        )
        return {
            "status": "match",
            "message": message,
            "differences": {},
            "needs_review": False,
            "computed": computed,
            "reported": dict(grok_totals),
        }

    parts: list[str] = []
    for key, vals in differences.items():
        if key in ("deposits", "withdrawals"):
            parts.append(
                f"{key}: detail ${vals['computed']:,.2f} vs source ${vals['reported']:,.2f} "
                f"(off by ${vals['diff']:+,.2f})"
            )
        else:
            parts.append(
                f"{key}: detail {vals['computed']} vs source {vals['reported']} "
                f"(off by {vals['diff']:+d})"
            )
    message = "Detailed totals do not match the source statement → " + "; ".join(parts)
    return {
        "status": "mismatch",
        "message": message,
        "differences": differences,
        "needs_review": True,
        "computed": computed,
        "reported": dict(grok_totals),
    }


# ---------------------------------------------------------------------------
# Azure OCR Function client (v2.41) — Strategic Next Milestone from Section 8.1
# ---------------------------------------------------------------------------
# Calls the dedicated `slam-ocr-function` Azure Function over HTTPS so heavy
# OCR / check-cropping stays off the Streamlit App Service. The wire format is
# documented in `AzureFunctions/ocr_processor/function_app.py`. Failures are
# always non-fatal — callers fall back to the existing lightweight parser or
# the Grok CSV paste path so Laura's daily workflow never gets blocked by an
# infrastructure hiccup.

AZURE_OCR_FUNCTION_URL_ENV = "AZURE_OCR_FUNCTION_URL"
AZURE_OCR_FUNCTION_KEY_ENV = "AZURE_OCR_FUNCTION_KEY"
AZURE_OCR_TIMEOUT_SEC = 180


def azure_ocr_configured() -> bool:
    """Return True when both the Function URL and key env vars are set."""

    url = (os.environ.get(AZURE_OCR_FUNCTION_URL_ENV) or "").strip()
    key = (os.environ.get(AZURE_OCR_FUNCTION_KEY_ENV) or "").strip()
    return bool(url) and bool(key)


def azure_ocr_status() -> dict[str, Any]:
    """Snapshot for the sidebar status indicator (no network call).

    Returns ``{configured, url, has_key, hint}`` so the sidebar can render
    "Azure OCR · configured" vs. "Azure OCR · not configured (set
    `AZURE_OCR_FUNCTION_URL` + `AZURE_OCR_FUNCTION_KEY`)".
    """

    url = (os.environ.get(AZURE_OCR_FUNCTION_URL_ENV) or "").strip()
    key = (os.environ.get(AZURE_OCR_FUNCTION_KEY_ENV) or "").strip()
    return {
        "configured": bool(url) and bool(key),
        "url": url,
        "has_key": bool(key),
        "hint": (
            f"Set `{AZURE_OCR_FUNCTION_URL_ENV}` and `{AZURE_OCR_FUNCTION_KEY_ENV}` "
            "App Settings on the Streamlit App Service to enable the heavy-OCR path."
        ),
    }


def _build_ocr_request_body(
    pdf_bytes: bytes,
    pdf_filename: str,
    client_name: str,
) -> tuple[bytes, str]:
    """Encode the OCR request as JSON with a base64 PDF payload.

    Using JSON (instead of multipart) keeps the client self-contained — no
    third-party `requests` / `requests-toolbelt` dependency on the App Service.
    For large PDFs the base64 overhead is acceptable on the Streamlit side; we
    can switch to multipart later if statements ever exceed ~30 MiB.
    """

    payload = {
        "pdf_b64": base64.b64encode(pdf_bytes or b"").decode("ascii"),
        "filename": pdf_filename or "statement.pdf",
        "client": client_name or "",
    }
    body = json.dumps(payload).encode("utf-8")
    return body, "application/json"


def _parse_ocr_response_to_df(payload: dict[str, Any]) -> pd.DataFrame:
    """Convert the Function's `transactions` list into the canonical 12-col DataFrame."""

    txns = payload.get("transactions") or []
    if not isinstance(txns, list) or not txns:
        return pd.DataFrame(columns=list(GROK_CSV_COLUMNS))

    df = pd.DataFrame(txns)
    for col in GROK_CSV_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    # Normalize numeric columns; matches the Grok CSV paste path.
    df["Amount"] = _coerce_amount_series(df["Amount"])
    signed_raw = df["SignedAmount"].astype(str).str.strip()
    signed_numeric = _coerce_amount_series(df["SignedAmount"])
    df["SignedAmount"] = signed_numeric.where(signed_raw != "", df["Amount"])

    # Date / YearMonth normalization (best-effort — the Function returns ISO already).
    df["Date"] = df["Date"].astype(str).str.strip()
    ym = df["YearMonth"].astype(str).str.strip()
    parsed_dates = pd.to_datetime(df["Date"], errors="coerce")
    derived_ym = parsed_dates.dt.strftime("%Y-%m").fillna("")
    df["YearMonth"] = ym.where(ym != "", derived_ym)

    df["Confidence"] = df["Confidence"].astype(str).str.strip().str.title().replace("", "Medium")
    df["NeedsReview"] = _coerce_yes_no(df["NeedsReview"].astype(str))
    df["Category"] = df["Category"].astype(str).str.strip().replace("", "Uncategorized")

    extras = [c for c in df.columns if c not in GROK_CSV_COLUMNS]
    return df[list(GROK_CSV_COLUMNS) + extras].reset_index(drop=True)


def run_azure_ocr_pipeline(
    pdf_bytes: bytes,
    pdf_filename: str,
    client_name: str,
    logger,
    *,
    timeout_sec: int = AZURE_OCR_TIMEOUT_SEC,
) -> tuple[pd.DataFrame | None, list[str], dict[str, Any]]:
    """Call the Azure OCR Function and return ``(df, logs, meta)``.

    Behavior mirrors :func:`run_statement_pipeline` so the Bank Statements page
    can swap implementations on a single radio toggle:

    - ``df`` is the canonical 12-column DataFrame (or ``None`` on error).
    - ``logs`` is a list of structured ``[LEVEL] message`` strings ready for
      the Processing log expander.
    - ``meta`` mirrors the parser meta: ``status`` (``success`` / ``partial``
      / ``error``), ``transaction_count``, ``grok_totals`` (so the
      reconciliation banner can fire), ``request_id``, ``service_version``,
      ``message``, ``configured``.

    Failures (missing config, HTTP error, timeout, malformed JSON) never
    raise — the caller can show a friendly "Azure OCR unavailable, falling
    back to the lightweight parser" message and continue.
    """

    logs: list[str] = []
    meta: dict[str, Any] = {
        "status": "error",
        "transaction_count": 0,
        "grok_totals": None,
        "request_id": None,
        "service_version": None,
        "message": "",
        "configured": False,
        "csv_path": None,
        "pdf_path": None,
    }

    url = (os.environ.get(AZURE_OCR_FUNCTION_URL_ENV) or "").strip()
    key = (os.environ.get(AZURE_OCR_FUNCTION_KEY_ENV) or "").strip()
    if not url or not key:
        logs.append(
            _log(
                "warn",
                "Azure OCR not configured — set `AZURE_OCR_FUNCTION_URL` + "
                "`AZURE_OCR_FUNCTION_KEY` App Settings to enable the heavy-OCR path.",
            )
        )
        meta["message"] = "Azure OCR Function URL/key not configured."
        if logger is not None:
            log_event(logger, "bank_stmt_azure_ocr_not_configured", client=client_name)
        return None, logs, meta

    meta["configured"] = True

    if not pdf_bytes:
        logs.append(_log("error", "Empty PDF payload — nothing to send to the Azure OCR Function."))
        meta["message"] = "Empty PDF payload."
        return None, logs, meta

    body, content_type = _build_ocr_request_body(pdf_bytes, pdf_filename, client_name)

    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": content_type,
            "x-functions-key": key,
            "Accept": "application/json",
        },
    )

    logs.append(
        _log(
            "info",
            f"Calling Azure OCR Function ({len(body) / 1024:.1f} KiB body) "
            f"with timeout={timeout_sec}s...",
        )
    )
    if logger is not None:
        log_event(
            logger,
            "bank_stmt_azure_ocr_request",
            client=client_name,
            filename=pdf_filename,
            bytes=len(pdf_bytes),
        )

    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as resp:
            raw = resp.read()
            status_code = resp.status
    except urllib.error.HTTPError as exc:
        body_text = ""
        try:
            body_text = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        logs.append(
            _log("error", f"Azure OCR Function returned HTTP {exc.code} {exc.reason}: {body_text}")
        )
        meta["message"] = f"HTTP {exc.code} {exc.reason}"
        if logger is not None:
            log_event(
                logger,
                "bank_stmt_azure_ocr_http_error",
                client=client_name,
                code=exc.code,
                reason=str(exc.reason)[:200],
            )
        return None, logs, meta
    except urllib.error.URLError as exc:
        logs.append(_log("error", f"Could not reach Azure OCR Function: {exc.reason}"))
        meta["message"] = f"Network error: {exc.reason}"
        if logger is not None:
            log_event(
                logger,
                "bank_stmt_azure_ocr_network_error",
                client=client_name,
                error=str(exc.reason)[:200],
            )
        return None, logs, meta
    except TimeoutError as exc:
        logs.append(_log("error", f"Azure OCR Function timed out after {timeout_sec}s: {exc}"))
        meta["message"] = f"Timed out after {timeout_sec}s"
        if logger is not None:
            log_event(
                logger, "bank_stmt_azure_ocr_timeout", client=client_name, seconds=timeout_sec
            )
        return None, logs, meta
    except Exception as exc:  # noqa: BLE001 — function boundary; surface as user-friendly error
        logs.append(_log("error", f"Unexpected error calling Azure OCR Function: {exc}"))
        meta["message"] = f"Unexpected error: {exc}"
        if logger is not None:
            log_event(logger, "bank_stmt_azure_ocr_unexpected_error", error=str(exc)[:200])
        return None, logs, meta

    if status_code != 200:
        logs.append(_log("error", f"Azure OCR Function returned non-200 status {status_code}."))
        meta["message"] = f"Non-200 status {status_code}"
        return None, logs, meta

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        logs.append(_log("error", f"Azure OCR Function returned non-JSON body: {exc}"))
        meta["message"] = f"Malformed JSON: {exc}"
        return None, logs, meta

    meta["service_version"] = payload.get("version")
    meta["request_id"] = payload.get("request_id")
    meta["status"] = str(payload.get("status") or "partial")
    meta["message"] = str(payload.get("message") or "")
    meta["grok_totals"] = payload.get("grok_totals")

    server_logs = payload.get("logs") or []
    if isinstance(server_logs, list):
        for line in server_logs:
            logs.append(str(line))

    df = _parse_ocr_response_to_df(payload)
    meta["transaction_count"] = int(len(df))

    if df.empty:
        logs.append(_log("warn", "Azure OCR Function returned zero transactions."))
        if meta["status"] == "success":
            meta["status"] = "partial"
    else:
        logs.append(_log("ok", f"Azure OCR Function returned {len(df)} transaction(s)."))

    if logger is not None:
        log_event(
            logger,
            "bank_stmt_azure_ocr_response",
            client=client_name,
            rows=int(len(df)),
            status=meta["status"],
            service_version=str(meta["service_version"] or ""),
        )

    return df, logs, meta


# ---------------------------------------------------------------------------
# Local Enhanced OCR pipeline (v2.43.2) — local-first port of v2.43
# ---------------------------------------------------------------------------
# In-process version of the Azure Function's v2.43 pipeline for Robert's local
# development environment while the heavy Function deploy (easyocr + torch on
# Y1 Consumption) remains parked behind an infra decision. The pipeline code
# lives in `App/local_enhanced_ocr.py` so this module stays focused on the
# Streamlit-facing entry points (parser subprocess, Grok CSV paste, Azure OCR
# Function client, and now the local enhanced runner). Heavy libraries are
# imported lazily inside the pipeline stages so the module remains importable
# in trimmed-down deploys.

LOCAL_ENHANCED_OCR_VERSION = "v2.43.2"

# Subset of capabilities the pipeline absolutely needs before it's worth even
# attempting (no point spinning up easyocr if pdfplumber + pillow + numpy are
# missing — the fast path can't even open the PDF). The full check-linking
# path additionally needs opencv + pdf2image + easyocr; when those are
# missing the run still produces transactions, but the cropper / matcher
# stages degrade gracefully with [WARN] lines in the processing log.
_LOCAL_OCR_MINIMUM_CAPS: tuple[str, ...] = ("pdfplumber",)
_LOCAL_OCR_FULL_CAPS: tuple[str, ...] = (
    "pdfplumber",
    "pdf2image",
    "easyocr",
    "opencv",
    "pillow",
    "numpy",
)


def local_enhanced_ocr_available() -> tuple[bool, dict[str, bool], list[str]]:
    """Report whether the local enhanced OCR pipeline can run in this environment.

    Returns ``(available, capabilities, missing)`` where:
    - ``available`` is True when at least the fast path (pdfplumber) is
      importable. Missing optional libraries reduce the pipeline gracefully:
      no opencv/easyocr → no check cropping, no easyocr/pdf2image →
      pdfplumber-only.
    - ``capabilities`` mirrors :func:`local_enhanced_ocr.detect_capabilities`.
    - ``missing`` lists the names of optional libraries needed for the full
      v2.43 check-linking experience that are NOT importable. Empty list when
      everything is installed.

    The Streamlit Bank Statements page uses this to show a clear "missing
    libs" warning and fall back to the Lightweight Parser instead of letting
    the pipeline silently degrade to a 0-row result.
    """

    try:
        import local_enhanced_ocr  # noqa: PLC0415

        caps = local_enhanced_ocr.detect_capabilities()
    except Exception:
        return False, {}, list(_LOCAL_OCR_FULL_CAPS)

    available = all(caps.get(name, False) for name in _LOCAL_OCR_MINIMUM_CAPS)
    missing = [name for name in _LOCAL_OCR_FULL_CAPS if not caps.get(name, False)]
    return available, caps, missing


def run_local_enhanced_ocr_pipeline(
    pdf_bytes: bytes,
    pdf_filename: str,
    client_name: str,
    logger,
) -> tuple[pd.DataFrame | None, list[str], dict[str, Any]]:
    """Run the v2.43 OCR pipeline locally (no Azure Function call).

    Behavior mirrors :func:`run_azure_ocr_pipeline` so the Bank Statements
    page can swap implementations on a single radio toggle:

    - ``df`` is the canonical 12-column DataFrame (or ``None`` on error /
      when the heavy libs are not installed).
    - ``logs`` is the same ``[LEVEL] message`` list ready for the Processing
      log expander — every pipeline stage transition, check-linking decision,
      and missing-library warning surfaces here.
    - ``meta`` mirrors the Azure path: ``status`` (``success`` / ``partial``
      / ``error``), ``transaction_count``, ``grok_totals`` (so the
      reconciliation banner fires automatically), ``service_version`` (set
      to :data:`LOCAL_ENHANCED_OCR_VERSION`), ``message``, ``configured``,
      plus a ``cropped_checks`` list and a ``linked_count`` summary so the
      UI can surface "Linked X check(s) to transactions" alongside the
      existing transaction count metric.

    Failures (missing libs, malformed PDF, OCR engine crash) never raise —
    the caller can show a friendly "Local Enhanced OCR unavailable, falling
    back to the Lightweight Parser" message and continue.
    """

    logs: list[str] = []
    meta: dict[str, Any] = {
        "status": "error",
        "transaction_count": 0,
        "grok_totals": None,
        "service_version": LOCAL_ENHANCED_OCR_VERSION,
        "message": "",
        "configured": False,
        "cropped_checks": [],
        "linked_count": 0,
        "capabilities": {},
        "missing_capabilities": [],
        "csv_path": None,
        "pdf_path": None,
    }

    available, caps, missing = local_enhanced_ocr_available()
    meta["capabilities"] = caps
    meta["missing_capabilities"] = missing

    if not available:
        logs.append(
            _log(
                "warn",
                "Local Enhanced OCR unavailable — required library not importable "
                f"(missing: {', '.join(missing) or 'unknown'}). "
                "Install the AzureFunctions requirements locally: "
                "`pip install pdfplumber pdf2image easyocr pillow opencv-python-headless numpy`.",
            )
        )
        meta["message"] = "Local Enhanced OCR not available in this environment."
        if logger is not None:
            log_event(
                logger,
                "bank_stmt_local_ocr_unavailable",
                client=client_name,
                missing=",".join(missing)[:200],
            )
        return None, logs, meta

    meta["configured"] = True

    if not pdf_bytes:
        logs.append(_log("error", "Empty PDF payload — nothing to send to Local Enhanced OCR."))
        meta["message"] = "Empty PDF payload."
        return None, logs, meta

    if missing:
        logs.append(
            _log(
                "warn",
                f"Local Enhanced OCR running with reduced capabilities — missing: "
                f"{', '.join(missing)}. Fast-path transactions will still be extracted, "
                "but check cropping and check-to-transaction linking will be skipped.",
            )
        )

    logs.append(
        _log(
            "info",
            f"Local Enhanced OCR ({LOCAL_ENHANCED_OCR_VERSION}) processing "
            f"{pdf_filename!r} for client {client_name!r} "
            f"({len(pdf_bytes) / 1024:.1f} KiB)...",
        )
    )
    if logger is not None:
        log_event(
            logger,
            "bank_stmt_local_ocr_request",
            client=client_name,
            filename=pdf_filename,
            bytes=len(pdf_bytes),
        )

    try:
        import local_enhanced_ocr  # noqa: PLC0415

        result = local_enhanced_ocr.run_pipeline(pdf_bytes)
    except Exception as exc:  # noqa: BLE001 — function boundary; never crash UI
        logs.append(_log("error", f"Local Enhanced OCR pipeline crashed: {exc}"))
        meta["message"] = f"Local Enhanced OCR pipeline crashed: {exc}"
        if logger is not None:
            log_event(logger, "bank_stmt_local_ocr_error", error=str(exc)[:200])
        return None, logs, meta

    pipeline_logs = result.get("logs") or []
    if isinstance(pipeline_logs, list):
        logs.extend(str(line) for line in pipeline_logs)

    meta["status"] = str(result.get("status") or "partial")
    meta["message"] = str(result.get("message") or "")
    meta["grok_totals"] = result.get("grok_totals")
    meta["cropped_checks"] = result.get("cropped_checks") or []
    meta["linked_count"] = int(result.get("linked_count") or 0)

    df = _txn_list_to_df(result.get("transactions") or [])
    meta["transaction_count"] = int(len(df))

    if df.empty:
        logs.append(_log("warn", "Local Enhanced OCR returned zero transactions."))
        if meta["status"] == "success":
            meta["status"] = "partial"
    else:
        logs.append(
            _log(
                "ok",
                f"Local Enhanced OCR returned {len(df)} transaction(s); "
                f"linked {meta['linked_count']} cropped check(s) to transactions.",
            )
        )

    if logger is not None:
        log_event(
            logger,
            "bank_stmt_local_ocr_response",
            client=client_name,
            rows=int(len(df)),
            cropped=int(len(meta["cropped_checks"])),
            linked=meta["linked_count"],
            status=meta["status"],
            service_version=str(meta["service_version"] or ""),
        )

    return df, logs, meta


def _txn_list_to_df(transactions: list[dict]) -> pd.DataFrame:
    """Convert a list of canonical transaction dicts into the 12-column DataFrame.

    Mirrors :func:`_parse_ocr_response_to_df` so the local pipeline output
    flows through the existing review UI / reconciliation banner / payee
    rules engine identically to the Azure Function path.
    """

    if not transactions:
        return pd.DataFrame(columns=list(GROK_CSV_COLUMNS))

    df = pd.DataFrame(transactions)
    for col in GROK_CSV_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df["Amount"] = _coerce_amount_series(df["Amount"])
    signed_raw = df["SignedAmount"].astype(str).str.strip()
    signed_numeric = _coerce_amount_series(df["SignedAmount"])
    df["SignedAmount"] = signed_numeric.where(signed_raw != "", df["Amount"])

    df["Date"] = df["Date"].astype(str).str.strip()
    ym = df["YearMonth"].astype(str).str.strip()
    parsed_dates = pd.to_datetime(df["Date"], errors="coerce")
    derived_ym = parsed_dates.dt.strftime("%Y-%m").fillna("")
    df["YearMonth"] = ym.where(ym != "", derived_ym)

    df["Confidence"] = df["Confidence"].astype(str).str.strip().str.title().replace("", "Medium")
    df["NeedsReview"] = _coerce_yes_no(df["NeedsReview"].astype(str))
    df["Category"] = df["Category"].astype(str).str.strip().replace("", "Uncategorized")

    extras = [c for c in df.columns if c not in GROK_CSV_COLUMNS]
    return df[list(GROK_CSV_COLUMNS) + extras].reset_index(drop=True)


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
