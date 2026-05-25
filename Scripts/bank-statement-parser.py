import csv
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pdfplumber

CSV_FIELDNAMES = [
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
]

DATE_PATTERNS = [
    (re.compile(r"^(\d{4})-(\d{2})-(\d{2})\b"), "iso"),
    (re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})\b"), "mdy"),
    (re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{2,4})\b"), "mdy_dash"),
    # Bare MM/DD (no year) — combined with statement year. Must be last so full dates win.
    (re.compile(r"^(\d{1,2})/(\d{1,2})(?!\d)"), "md"),
    (re.compile(r"^(\d{1,2})-(\d{1,2})(?!\d)"), "md_dash"),
]

DATE_INLINE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}-\d{1,2}-\d{2,4}|\d{1,2}/\d{1,2}|\d{1,2}-\d{1,2})\b"
)

AMOUNT_RE = re.compile(r"(?P<neg>\()?-?\$?(?P<num>\d{1,3}(?:,\d{3})*|\d+)\.(?P<cents>\d{2})\)?")

CHECK_RE = re.compile(r"(?i)\bcheck\s*#?\s*(\d{3,6})\b")
CHECK_STANDALONE_RE = re.compile(r"^\s*\*?\s*(\d{3,6})\s*\*?\s*$")

# Traditions / generic check-register row: "2473 *  01/15  250.00  6,079.01"
# Captures: check#, MM/DD or MM/DD/YY date, then the rest (amount + optional balance).
CHECK_REGISTER_ROW_RE = re.compile(
    r"^\s*\*?\s*(\d{3,6})\s*\*?\s+(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\s+(.+?)\s*$"
)

TXN_HINT_RE = re.compile(
    r"(?i)(ach\s+(deposit|withdrawal|debit|credit)|"
    r"debit\s+card|check\s*#?|eft/?ach|regular\s+deposit|"
    r"wire\s|pos\s|merch\s+bnkcd|merch\s+setl|"
    r"internet\s+transfer|service\s+charge|nsf\s|overdraft|"
    r"paypal|inst\s+xfer|bnkcd|(?<!total\s)\bdeposit\b|"
    r"withdrawal|transfer|epay|zelle|venmo|card\s+tran)"
)

SKIP_LINE_RE = re.compile(
    r"(?i)(page\s+\d+\s*of\s*\d+|^\s*page\s+\d+\s*$|continued|account\s+number|routing\s+number|"
    r"member\s+fdic|equal\s+housing|summary\s+of\s+accounts|"
    r"statement\s+balance\s+summary|customer\s+service|"
    r"beginning\s+balance|ending\s+balance|average\s+daily\s+balance|"
    r"previous\s+balance\s+[\d$,]|total\s+for\s|subtotal|"
    r"number\s+of\s+(deposits|withdrawals|credits|debits|checks)|"
    r"^\s*\*\s*indicates\s+a\s+break|interest\s+earned\s+this\s+period|"
    r"telephone\s+banking|www\.|^\s*[(]?\d{3}[)]?[-.\s]?\d{3}[-.\s]?\d{4}\s*$)"
)

BALANCE_TOTAL_RE = re.compile(
    r"(?i)^\s*(total\s+(deposits|withdrawals|credits|debits|checks|fees|service\s+charges)|"
    r"total\s+deposits|total\s+withdrawals|grand\s+total|"
    r"net\s+(deposits|withdrawals|credits|debits))\b"
)

# When we hit one of these sections, stop accumulating transactions until we see another
# transaction-bearing section header. Daily Balance / Statement Summary are summary tables.
SECTION_TERMINATORS = {
    "daily balance",
    "daily balances",
    "daily balance summary",
    "daily balance information",
    "statement balance summary",
    "balance summary",
    "account summary",
}

SECTION_MARKERS: Dict[str, str] = {
    "deposits": "credit",
    "deposits and credits": "credit",
    "deposits and additions": "credit",
    "deposits and other credits": "credit",
    "deposits/credits": "credit",
    "credits": "credit",
    "other credits": "credit",
    "electronic credits": "credit",
    "electronic deposits": "credit",
    "atm deposits": "credit",
    "electronic debits": "debit",
    "electronic debit": "debit",
    "other debits": "debit",
    "other withdrawals": "debit",
    "atm withdrawals": "debit",
    "debits": "debit",
    "debit card": "debit",
    "debit card transactions": "debit",
    "check register": "check",
    "checks paid": "check",
    "checks": "check",
    "withdrawals": "debit",
    "withdrawals and debits": "debit",
    "service charges": "debit",
    "fees": "debit",
}

COLUMN_HEADER_PHRASES = (
    "date description",
    "date description amount",
    "date check",
    "posting date",
    "check number",
    "check #",
)


def safe_print(*args, **kwargs) -> None:
    """Print without failing on Windows consoles (cp1252) when output contains Unicode."""
    text = " ".join(str(a) for a in args)
    try:
        print(text, **kwargs)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"), **kwargs)


def infer_statement_year(text: str, fallback: int = 2026) -> int:
    for pat in (
        r"(?i)statement\s+period[^\d]{0,40}(\d{4})",
        r"(?i)(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+(\d{4})",
        r"\b(20\d{2})\b",
    ):
        m = re.search(pat, text[:8000])
        if m:
            year = int(m.groups()[-1])
            if 2000 <= year <= 2099:
                return year
    return fallback


def normalize_date(raw: str, default_year: int) -> Tuple[str, str]:
    """Return (YYYY-MM-DD, YYYY-MM) or ('', '') if unparseable."""
    raw = (raw or "").strip()
    if not raw:
        return "", ""

    for pat, kind in DATE_PATTERNS:
        m = pat.match(raw)
        if not m:
            continue
        if kind == "iso":
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        elif kind in ("md", "md_dash"):
            mo, d = int(m.group(1)), int(m.group(2))
            y = default_year
        else:
            mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 100:
                y += 2000 if y < 70 else 1900
            if y < 2000:
                y = default_year
        try:
            dt = datetime(y, mo, d)
            return dt.strftime("%Y-%m-%d"), dt.strftime("%Y-%m")
        except ValueError:
            continue

    m = DATE_INLINE.search(raw)
    if m:
        return normalize_date(m.group(1), default_year)
    return "", ""


def parse_amounts(line: str) -> List[float]:
    """All monetary values on a line (for picking transaction amount)."""
    values: List[float] = []
    for m in AMOUNT_RE.finditer(line):
        num = m.group("num").replace(",", "")
        cents = m.group("cents")
        val = float(f"{num}.{cents}")
        if m.group("neg") or line[m.start() : m.start() + 1] == "-":
            val = -abs(val)
        elif line[max(0, m.start() - 2) : m.start()].strip().endswith("-"):
            val = -abs(val)
        values.append(val)
    return values


def pick_transaction_amount(
    values: List[float], *, prefer: str = "first_with_balance"
) -> float | None:
    """Pick the transaction amount from a list of monetary values found on a line/cell.

    Most US bank statements format transaction lines as `DATE DESC AMOUNT BALANCE`, so
    the rightmost amount is usually the running balance — not the transaction. We default
    to picking the LEFTMOST non-zero amount when 2+ are present, which is the transaction.

    prefer='first' → always leftmost non-zero
    prefer='last'  → always rightmost non-zero (legacy behavior; for single-amount cells)
    prefer='first_with_balance' → leftmost when 2+, else the only value
    """
    if not values:
        return None
    non_zero = [v for v in values if abs(v) > 0.001]
    if not non_zero:
        return values[-1]
    if prefer == "last":
        return non_zero[-1]
    if prefer == "first" or len(non_zero) >= 2:
        return non_zero[0]
    return non_zero[-1]


def format_signed_amount(val: float | None) -> str:
    if val is None:
        return ""
    return f"{val:.2f}"


def _strip_trailing_amounts(description: str) -> str:
    prev = None
    while prev != description:
        prev = description
        description = re.sub(r"[-]?\$?\d{1,3}(?:,\d{3})*\.\d{2}\s*$", "", description).strip()
        description = re.sub(r"\(\d{1,3}(?:,\d{3})*\.\d{2}\)\s*$", "", description).strip()
    return description


def _apply_section_sign(amount: float | None, section: str | None) -> float | None:
    if amount is None or section is None:
        return amount
    if section == "debit" and amount > 0:
        return -abs(amount)
    if section == "check" and amount > 0:
        return -abs(amount)
    if section == "credit" and amount < 0:
        return abs(amount)
    return amount


def _detect_section(line: str) -> str | None:
    """Map a header line to a section kind: 'credit' | 'debit' | 'check' | 'end' | None.

    Returns 'end' for terminator sections (Daily Balance Summary, Statement Summary, etc.)
    which should stop transaction accumulation until another transaction-bearing section
    header is encountered.
    """
    low = re.sub(r"\s*\|.*$", "", line.lower().strip())
    low = re.sub(r"[^a-z0-9\s/]", " ", low)
    low = re.sub(r"\s+", " ", low).strip()
    if not low:
        return None
    for term in sorted(SECTION_TERMINATORS, key=len, reverse=True):
        if low == term or low.startswith(term + " "):
            return "end"
    for marker, kind in sorted(SECTION_MARKERS.items(), key=lambda x: -len(x[0])):
        if low == marker or low.startswith(marker + " ") or low.startswith(marker + "/"):
            return kind
    return None


def _is_column_header_line(line: str) -> bool:
    """True for table header rows only — not data lines that mention checks or amounts."""
    low = line.lower().strip()
    if parse_amounts(line):
        return False
    if DATE_INLINE.search(line[:16]) and not low.startswith("date"):
        return False
    if any(phrase in low for phrase in COLUMN_HEADER_PHRASES):
        return True
    if re.match(r"(?i)^date\s", low) and (
        "amount" in low or "description" in low or "check" in low
    ):
        return True
    return False


def words_to_lines(words: List[dict], y_tolerance: float = 4.0) -> List[str]:
    if not words:
        return []
    buckets: dict[int, list] = {}
    for w in words:
        key = int(round(w.get("top", 0) / y_tolerance))
        buckets.setdefault(key, []).append(w)
    lines: List[str] = []
    for key in sorted(buckets):
        row = sorted(buckets[key], key=lambda x: x.get("x0", 0))
        lines.append(" ".join(w.get("text", "") for w in row if w.get("text")))
    return lines


def extract_pdf_text(pdf_path: str) -> str:
    """Extract text via pdfplumber text, word layout, and table rows (all strategies per page)."""
    chunks: List[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            if not text.strip():
                text = page.extract_text(x_tolerance=1, y_tolerance=1, layout=True) or ""
            if text.strip():
                chunks.append(text)
            words = page.extract_words() or []
            if words and not text.strip():
                chunks.append("\n".join(words_to_lines(words)))
            for table in page.extract_tables() or []:
                for row in table:
                    if not row:
                        continue
                    cells = [str(c or "").strip() for c in row if c]
                    if cells:
                        chunks.append(" | ".join(cells))
    return "\n".join(chunks)


def _should_skip_line(line: str) -> bool:
    low = line.lower().strip()
    if len(low) < 3:
        return True
    if SKIP_LINE_RE.search(line):
        return True
    if BALANCE_TOTAL_RE.match(line):
        return True
    if _detect_section(line):
        return True
    if _is_column_header_line(line):
        return True
    if re.match(r"(?i)^(debit|credit|amount|balance)\s*(\s|$|\|)", low):
        return True
    # Bare date with no description and no amount — header artifact (e.g. "Date" column label row).
    if re.match(r"^\s*date\s*$", low):
        return True
    return False


def _extract_check_number(*parts: str, check_column: bool = False) -> str:
    """Extract check number from cells; standalone digits only in check column cells."""
    for part in parts:
        if not part:
            continue
        part = part.strip()
        m = CHECK_RE.search(part)
        if m:
            return m.group(1)
        if check_column:
            m = CHECK_STANDALONE_RE.match(part)
            if m:
                return m.group(1)
    return ""


def _is_transaction_candidate(
    line: str,
    *,
    has_amount: bool,
    has_date: bool = False,
    section: str | None = None,
) -> bool:
    if not has_amount:
        return False
    if has_date or re.match(r"^\d{1,2}[/-]\d{1,2}", line.strip()):
        return True
    if section in ("credit", "debit", "check"):
        return True
    if TXN_HINT_RE.search(line):
        return True
    if CHECK_RE.search(line) or CHECK_STANDALONE_RE.match(line.split("|")[0].strip()):
        return True
    return False


def _split_date_prefix(line: str, default_year: int) -> Tuple[str, str, str]:
    """Return (iso_date, remainder_line, year_month)."""
    line = line.strip()
    for pat, _kind in DATE_PATTERNS:
        m = pat.match(line)
        if m:
            iso, ym = normalize_date(line[: m.end()], default_year)
            rest = line[m.end() :].strip()
            return iso, rest, ym
    m = DATE_INLINE.match(line)
    if m and m.start() < 12:
        iso, ym = normalize_date(m.group(1), default_year)
        rest = (line[m.end() :] or "").strip()
        return iso, rest, ym
    return "", line, ""


def _build_row(
    *,
    date: str,
    description: str,
    amount: float | None,
    check_num: str,
    year_month: str,
    default_year: int,
    section: str | None = None,
) -> Dict[str, Any]:
    if not date:
        date, ym = "", year_month
    else:
        ym = year_month or (date[:7] if len(date) >= 7 else "")

    description = _strip_trailing_amounts(description.strip())
    amount = _apply_section_sign(amount, section)
    signed = format_signed_amount(amount)
    conf = "High"
    needs = "No"
    if not date:
        conf = "Medium"
        needs = "Yes"
    elif not signed:
        conf = "Medium"
        needs = "Yes"

    check_num = check_num or _extract_check_number(description)
    row = {
        "Date": date or "",
        "Description": description.strip(),
        "Payee": "",
        "Amount": signed,
        "Check#": check_num,
        "Category": "Uncategorized",
        "SubCategory": "",
        "SignedAmount": signed,
        "YearMonth": ym or f"{default_year}-01",
        "Confidence": conf,
        "NeedsReview": needs,
        "ReviewReason": "",
    }
    return validate_transaction_row(row)


def _parse_cells_to_row(
    cells: List[str],
    *,
    default_year: int,
    section: str | None,
    col_date: int | None,
    col_desc: int | None,
    col_amt: int | None,
    col_check: int | None,
) -> Dict[str, Any] | None:
    if not cells:
        return None
    joined = " ".join(cells)
    if _detect_section(joined) or _is_column_header_line(joined):
        return None

    iso, ym = "", ""
    desc = ""
    amt: float | None = None
    check_num = ""

    if col_date is not None and col_date < len(cells):
        iso, ym = normalize_date(cells[col_date], default_year)
    if col_desc is not None and col_desc < len(cells):
        desc = cells[col_desc]
    if col_check is not None and col_check < len(cells):
        check_num = _extract_check_number(cells[col_check], check_column=True)
    if col_amt is not None and col_amt < len(cells):
        # Single cell — only one transaction amount expected; use 'first' to be explicit.
        amt = pick_transaction_amount(parse_amounts(cells[col_amt]), prefer="first")

    if col_date is None and len(cells) >= 3:
        iso_guess, ym_guess = normalize_date(cells[0], default_year)
        # Traditions check register cells: [check#, date, amount, balance]
        if section == "check" and not iso_guess and len(cells) >= 3:
            chk_m = CHECK_STANDALONE_RE.match(cells[0])
            date_guess, ym_date = normalize_date(cells[1], default_year)
            if chk_m and date_guess:
                amt_guess = pick_transaction_amount(parse_amounts(cells[2]), prefer="first")
                if amt_guess is not None:
                    check_num = chk_m.group(1)
                    iso, ym = date_guess, ym_date
                    amt = amt_guess
                    desc = f"Check #{check_num}"
        if iso_guess:
            if section == "check" and len(cells) >= 4:
                amt_guess = pick_transaction_amount(parse_amounts(cells[2]), prefer="first")
                if amt_guess is not None:
                    iso, ym = iso_guess, ym_guess
                    check_num = _extract_check_number(cells[1], check_column=True)
                    amt = amt_guess
                    desc = cells[3]
            else:
                # In freeform pipe-delimited rows, the rightmost cell is typically the
                # running balance and the second-to-last is the transaction amount.
                if len(cells) >= 4 and parse_amounts(cells[-1]) and parse_amounts(cells[-2]):
                    amt_guess = pick_transaction_amount(parse_amounts(cells[-2]), prefer="first")
                    if amt_guess is not None:
                        iso, ym = iso_guess, ym_guess
                        amt = amt_guess
                        desc = " ".join(cells[1:-2])
                else:
                    amt_guess = pick_transaction_amount(parse_amounts(cells[-1]), prefer="first")
                    if amt_guess is not None:
                        iso, ym = iso_guess, ym_guess
                        amt = amt_guess
                        desc = " | ".join(cells[1:-1]) if " | " in joined else " ".join(cells[1:-1])

    # Check-only row: section is 'check' and we have a check number + amount but no date.
    if section == "check" and not iso and not check_num:
        for c in cells:
            cm = CHECK_STANDALONE_RE.match(c.strip())
            if cm:
                check_num = cm.group(1)
                break

    if not iso:
        iso, remainder, ym = _split_date_prefix(joined, default_year)
        if iso and not desc:
            desc = remainder

    if not desc:
        desc = joined
    if amt is None:
        amt = pick_transaction_amount(parse_amounts(joined))
        if amt is not None and iso:
            desc = _strip_trailing_amounts(AMOUNT_RE.sub("", joined.replace(iso, "", 1)).strip())

    has_date = bool(iso)
    if not _is_transaction_candidate(
        desc or joined, has_amount=amt is not None, has_date=has_date, section=section
    ):
        return None
    if amt is None:
        return None

    return _build_row(
        date=iso,
        description=desc,
        amount=amt,
        check_num=check_num,
        year_month=ym,
        default_year=default_year,
        section=section,
    )


def _map_table_columns(headers: List[str]) -> Tuple[int | None, int | None, int | None, int | None]:
    col_date = next((i for i, h in enumerate(headers) if "date" in h), None)
    col_desc = next(
        (
            i
            for i, h in enumerate(headers)
            if any(k in h for k in ("description", "detail", "memo", "payee"))
        ),
        None,
    )
    col_check = next(
        (i for i, h in enumerate(headers) if "check" in h and "date" not in h),
        None,
    )
    col_amt = next(
        (
            i
            for i, h in enumerate(headers)
            if h in ("amount", "debit", "credit", "withdrawal", "deposit") or "amount" in h
        ),
        None,
    )
    if col_desc is None and col_check is not None and col_amt is not None:
        remaining = [i for i in range(len(headers)) if i not in (col_date, col_check, col_amt)]
        if remaining:
            col_desc = remaining[-1]
    return col_date, col_desc, col_amt, col_check


def _find_header_row(
    table: List[List[Any]], start: int = 0
) -> Tuple[int | None, int | None, int | None, int | None, int]:
    for i, row in enumerate(table[start : start + 8], start=start):
        joined = " ".join(str(c or "") for c in row).lower()
        if "date" in joined and (
            "amount" in joined
            or "debit" in joined
            or "credit" in joined
            or "check" in joined
            or "description" in joined
        ):
            headers = [str(c or "").strip().lower() for c in row]
            cols = _map_table_columns(headers)
            return (*cols, i)
    return None, None, None, None, -1


def _parse_table_rows(tables: List[List[List[Any]]], default_year: int) -> List[Dict]:
    rows: List[Dict] = []
    for table in tables:
        if not table or len(table) < 2:
            continue
        section: str | None = None
        suppressed = False
        col_date = col_desc = col_amt = col_check = None
        header_idx = -1
        idx = 0
        while idx < len(table):
            row = table[idx]
            cells = [str(c or "").strip() for c in row] if row else []
            joined = " ".join(cells)
            sec = _detect_section(joined)
            if sec == "end":
                suppressed = True
                section = None
                col_date = col_desc = col_amt = col_check = None
                header_idx = -1
                idx += 1
                continue
            if sec:
                suppressed = False
                section = sec
                col_date = col_desc = col_amt = col_check = None
                header_idx = -1
                hdr_cols = _find_header_row(table, idx + 1)
                if hdr_cols[4] >= 0:
                    col_date, col_desc, col_amt, col_check, header_idx = hdr_cols
                idx += 1
                continue
            if suppressed:
                idx += 1
                continue
            if _is_column_header_line(joined):
                headers = [str(c or "").strip().lower() for c in row]
                col_date, col_desc, col_amt, col_check = _map_table_columns(headers)
                header_idx = idx
                idx += 1
                continue
            if header_idx < 0:
                hdr_cols = _find_header_row(table, idx)
                if hdr_cols[4] >= 0:
                    col_date, col_desc, col_amt, col_check, header_idx = hdr_cols
                    if idx == header_idx:
                        idx += 1
                        continue

            parsed = _parse_cells_to_row(
                cells,
                default_year=default_year,
                section=section,
                col_date=col_date,
                col_desc=col_desc,
                col_amt=col_amt,
                col_check=col_check,
            )
            if parsed:
                rows.append(parsed)
            idx += 1
    return rows


def parse_lines_to_transactions(lines: List[str], default_year: int) -> List[Dict]:
    transactions: List[Dict] = []
    current_date = ""
    current_ym = ""
    current_section: str | None = None
    pending_desc: List[str] = []
    suppressed = False  # True after a terminator section until another txn section header

    def flush_pending() -> None:
        nonlocal pending_desc
        if pending_desc and not suppressed:
            desc = " ".join(pending_desc).strip()
            if desc and (TXN_HINT_RE.search(desc) or current_date or current_section):
                row = _build_row(
                    date=current_date,
                    description=desc,
                    amount=None,
                    check_num=_extract_check_number(desc),
                    year_month=current_ym,
                    default_year=default_year,
                    section=current_section,
                )
                transactions.append(row)
        pending_desc = []

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        sec = _detect_section(line)
        if sec == "end":
            flush_pending()
            suppressed = True
            current_section = None
            continue
        if sec:
            flush_pending()
            current_section = sec
            suppressed = False
            continue

        if suppressed:
            continue

        if " | " in line:
            cells = [c.strip() for c in line.split(" | ")]
            parsed = _parse_cells_to_row(
                cells,
                default_year=default_year,
                section=current_section,
                col_date=None,
                col_desc=None,
                col_amt=None,
                col_check=None,
            )
            if parsed:
                flush_pending()
                if parsed.get("Date"):
                    current_date = parsed["Date"]
                    current_ym = parsed.get("YearMonth", "")
                transactions.append(parsed)
                continue

        # Dedicated check-register row: "2473 * 01/15 250.00 6,079.01"
        if current_section == "check" and not _is_column_header_line(line):
            cm = CHECK_REGISTER_ROW_RE.match(line)
            if cm:
                check_no = cm.group(1)
                date_str = cm.group(2)
                rest = cm.group(3)
                iso_d, ym_d = normalize_date(date_str, default_year)
                amts = parse_amounts(rest)
                amt = pick_transaction_amount(amts)  # leftmost = amount, rightmost = balance
                if amt is not None:
                    flush_pending()
                    desc_text = f"Check #{check_no}"
                    extra = AMOUNT_RE.sub("", rest).strip(" .-")
                    if extra and not extra.isdigit():
                        desc_text = f"{desc_text} {extra}".strip()
                    row = _build_row(
                        date=iso_d or current_date,
                        description=desc_text,
                        amount=amt,
                        check_num=check_no,
                        year_month=ym_d or current_ym,
                        default_year=default_year,
                        section="check",
                    )
                    transactions.append(row)
                    if iso_d:
                        current_date = iso_d
                        current_ym = ym_d
                    continue

        if _should_skip_line(line):
            continue

        line_date, remainder, line_ym = _split_date_prefix(line, default_year)
        if line_date:
            flush_pending()
            current_date = line_date
            current_ym = line_ym
            line = remainder

        amounts = parse_amounts(line)
        has_amount = bool(amounts)

        if not has_amount:
            if (
                TXN_HINT_RE.search(line)
                or DATE_INLINE.search(line[:20])
                or _extract_check_number(line)
                or current_section
            ):
                pending_desc.append(line)
            continue

        desc_parts = pending_desc + ([line] if line else [])
        pending_desc = []
        description = " ".join(desc_parts).strip()
        amount_vals = parse_amounts(description)
        # In text-line mode, lines often end with running balance. Prefer the leftmost
        # non-zero amount when 2+ are present (default behavior of pick_transaction_amount).
        amount = pick_transaction_amount(amount_vals)

        has_date = bool(current_date) or bool(line_date)
        if not _is_transaction_candidate(
            description,
            has_amount=True,
            has_date=has_date,
            section=current_section,
        ):
            if not current_date and not current_section:
                continue

        check_num = _extract_check_number(description, line)
        row = _build_row(
            date=current_date,
            description=description,
            amount=amount,
            check_num=check_num,
            year_month=current_ym,
            default_year=default_year,
            section=current_section,
        )
        transactions.append(row)

    flush_pending()
    return _dedupe_transactions(transactions)


def _dedupe_transactions(transactions: List[Dict]) -> List[Dict]:
    seen = set()
    out: List[Dict] = []
    for row in transactions:
        key = (
            row.get("Date"),
            row.get("Description", "")[:80],
            row.get("SignedAmount"),
            row.get("Check#"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def validate_transaction_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and flag rows; relaxed rules — keep row even with minor issues."""
    errors: List[str] = []
    date_val = str(row.get("Date", "")).strip()

    if date_val and not re.match(r"^\d{4}-\d{2}-\d{2}$", date_val):
        errors.append("Date format uncertain")
    elif not date_val:
        errors.append("Missing date")

    signed = str(row.get("SignedAmount", "")).strip()
    if signed:
        try:
            float(signed.replace(",", ""))
        except ValueError:
            errors.append(f"Invalid SignedAmount: {signed}")
    else:
        errors.append("Missing amount")

    check = str(row.get("Check#", "")).strip()
    if check and not check.isdigit():
        errors.append(f"Check# may need review: {check}")

    ym = str(row.get("YearMonth", "")).strip()
    if ym and not re.match(r"^\d{4}-\d{2}$", ym):
        if len(date_val) >= 7:
            row["YearMonth"] = date_val[:7]
        else:
            errors.append("YearMonth adjusted")

    conf = str(row.get("Confidence", "")).strip()
    if conf not in ("High", "Medium", "Low", ""):
        row["Confidence"] = "Medium"
        errors.append("Invalid Confidence corrected")

    if errors:
        row["HasError"] = any("Invalid" in e for e in errors)
        row["NeedsReviewFlag"] = True
        row["NeedsReview"] = "Yes"
        row["ReviewReason"] = "; ".join(errors)
        if row.get("Confidence") == "High":
            row["Confidence"] = "Medium"
    else:
        row["HasError"] = False
        row["NeedsReviewFlag"] = False
        row["NeedsReview"] = "No"
        row["ReviewReason"] = ""

    return row


def parse_bank_statement(pdf_path: str) -> List[Dict]:
    """Extract transactions from a bank statement PDF (text, words, or tables)."""
    text = extract_pdf_text(pdf_path)
    default_year = infer_statement_year(text)

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    transactions = parse_lines_to_transactions(lines, default_year)

    with pdfplumber.open(pdf_path) as pdf:
        all_tables: List[List[List[Any]]] = []
        for page in pdf.pages:
            all_tables.extend(page.extract_tables() or [])
    if all_tables:
        table_rows = _parse_table_rows(all_tables, default_year)
        transactions = _dedupe_transactions(transactions + table_rows)

    transactions = [t for t in transactions if t.get("Description")]
    transactions = _filter_balance_only_rows(transactions)
    return transactions


def _filter_balance_only_rows(transactions: List[Dict]) -> List[Dict]:
    """Drop rows whose Description is just a balance label or a literal balance phrase."""
    out: List[Dict] = []
    bad_desc = re.compile(
        r"(?i)^(ending|beginning|previous|new|current|available)\s+balance\b|"
        r"^balance\s*(forward|brought\s*forward)?\s*$|^total\b"
    )
    for row in transactions:
        desc = str(row.get("Description", "")).strip()
        if not desc or bad_desc.match(desc):
            continue
        out.append(row)
    return out


def summarize_transactions(transactions: List[Dict]) -> Dict[str, Any]:
    """Return per-section counts and totals for diagnostic logging / UI summaries."""
    summary: Dict[str, Any] = {
        "total": len(transactions),
        "credits": 0,
        "debits": 0,
        "checks": 0,
        "uncategorized": 0,
        "credit_amount": 0.0,
        "debit_amount": 0.0,
        "needs_review": 0,
    }
    for t in transactions:
        signed = t.get("SignedAmount") or t.get("Amount") or ""
        try:
            v = float(str(signed).replace(",", ""))
        except (TypeError, ValueError):
            v = 0.0
        if t.get("Check#"):
            summary["checks"] += 1
        elif v > 0:
            summary["credits"] += 1
            summary["credit_amount"] += v
        elif v < 0:
            summary["debits"] += 1
            summary["debit_amount"] += abs(v)
        else:
            summary["uncategorized"] += 1
        if str(t.get("NeedsReview", "")).lower() == "yes":
            summary["needs_review"] += 1
    return summary


def main():
    if len(sys.argv) < 2:
        safe_print("Usage: python bank-statement-parser.py <path_to_statement.pdf>")
        return

    pdf_path = sys.argv[1]
    if pdf_path in ("--dump-text", "-t") and len(sys.argv) >= 3:
        out = extract_pdf_text(sys.argv[2])
        safe_print(out if out.strip() else "[No extractable text — PDF may be scanned/image-only]")
        return

    output_path = Path(pdf_path).stem + "_Transactions_With_Payees.csv"

    safe_print(f"Processing {pdf_path}...")
    raw = extract_pdf_text(pdf_path)
    if not raw.strip():
        safe_print(
            "WARN: No text layer detected in PDF (likely scanned). "
            "Use Export Raw Text / Grok Vision for extraction."
        )
    txns = parse_bank_statement(pdf_path)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for row in txns:
            writer.writerow({k: row.get(k, "") for k in CSV_FIELDNAMES})

    safe_print(f"[OK] Success! Created: {output_path}")
    safe_print(f"Total transactions: {len(txns)}")
    if txns:
        s = summarize_transactions(txns)
        safe_print(
            f"  Credits: {s['credits']} (${s['credit_amount']:,.2f})  "
            f"Debits: {s['debits']} (${s['debit_amount']:,.2f})  "
            f"Checks: {s['checks']}  Needs review: {s['needs_review']}"
        )


if __name__ == "__main__":
    main()
