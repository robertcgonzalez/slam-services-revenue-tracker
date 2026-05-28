"""Utilities for Azure Document Intelligence / Content Understanding.

Focus: cost control by skipping blank and reconciliation/summary pages
before sending PDFs to Azure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from typing import Any

import pdfplumber

# ------------------------------------------------------------------
# Heuristics – tune these as you see real statements
# ------------------------------------------------------------------

RECONCILIATION_KEYWORDS = [
    r"reconciliation",
    r"daily balance",
    r"account summary",
    r"beginning balance",
    r"ending balance",
    r"total deposits",
    r"total withdrawals",
    r"deposits and credits",
    r"withdrawals and debits",
    r"statement period",
    r"account number",
]

# Very loose date + amount pattern (catches most transaction rows)
TRANSACTION_LINE_RE = re.compile(
    r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b.*\d{1,3}(?:,\d{3})*\.\d{2}"
)

BLANK_TEXT_THRESHOLD = 40          # characters of real text
LOW_TRANSACTION_DENSITY = 2        # fewer than this many tx-like lines → suspicious page


def _is_likely_blank_page(page: pdfplumber.page.Page) -> bool:
    """Fast text-based blank page check."""
    text = (page.extract_text() or "").strip()
    if len(text) < BLANK_TEXT_THRESHOLD:
        return True
    # Very few words is also suspicious on a statement page
    words = len(text.split())
    return words < 8


def _count_transaction_signals(text: str) -> int:
    """Rough count of lines that look like actual transactions."""
    if not text:
        return 0
    return len(TRANSACTION_LINE_RE.findall(text))


def _is_reconciliation_or_summary_page(text: str, tx_count: int) -> bool:
    """Detect pages that are mostly totals/reconciliation rather than transactions."""
    if not text:
        return False

    lowered = text.lower()
    keyword_hits = sum(1 for kw in RECONCILIATION_KEYWORDS if re.search(kw, lowered))

    # Strong signal: lots of reconciliation keywords + very few real transaction lines
    if keyword_hits >= 2 and tx_count <= LOW_TRANSACTION_DENSITY:
        return True

    # Common pattern: page is almost entirely "Beginning / Ending Balance" + totals
    balance_hits = len(re.findall(r"beginning|ending.*balance", lowered))
    if balance_hits >= 2 and tx_count <= 1:
        return True

    return False


def _cheap_blank_check_via_raster(pdf_bytes: bytes, page_number: int, dpi: int = 72) -> bool:
    """Fallback raster check for heavily scanned PDFs with almost no extractable text."""
    try:
        from pdf2image import convert_from_bytes  # lazy import
    except ImportError:
        return False  # can't check, assume not blank

    try:
        images = convert_from_bytes(
            pdf_bytes,
            first_page=page_number + 1,   # pdf2image is 1-based
            last_page=page_number + 1,
            dpi=dpi,
        )
        if not images:
            return True

        img = images[0].convert("L")  # grayscale
        # Count pixels that are not almost pure white
        pixels = list(img.getdata())
        non_white = sum(1 for p in pixels if p < 245)
        coverage = non_white / max(len(pixels), 1)
        return coverage < 0.015   # less than 1.5% "ink" → probably blank
    except Exception:
        return False


@dataclass
class PageFilterDecision:
    """Detailed record of why a page was kept or skipped."""
    page_number: int          # 0-based
    kept: bool
    reason: str               # Human-readable explanation


def get_pages_to_analyze(
    pdf_bytes: bytes,
    *,
    min_tx_signals: int = 1,
    enable_raster_fallback: bool = True,
) -> tuple[list[int], list[PageFilterDecision]]:
    """
    Returns (pages_to_keep_0based, detailed_decisions).

    Use the first value for the Azure `pages=` parameter.
    Use the second value to show the user exactly what was filtered and why
    (critical for cost transparency).
    """
    decisions: list[PageFilterDecision] = []
    pages_to_keep: list[int] = []

    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            tx_signals = _count_transaction_signals(text)
            kept = True
            reason = "Contains transactions"

            # 1. Blank page detection
            if _is_likely_blank_page(page):
                if enable_raster_fallback and _cheap_blank_check_via_raster(pdf_bytes, page_idx):
                    kept = False
                    reason = "Blank page (low ink coverage on raster check)"
                elif not enable_raster_fallback:
                    kept = False
                    reason = "Blank or near-blank page (very little extractable text)"

            # 2. Reconciliation / summary page
            elif _is_reconciliation_or_summary_page(text, tx_signals):
                if tx_signals < min_tx_signals:
                    kept = False
                    reason = "Reconciliation / summary page (dominated by totals & balances)"

            # 3. Very low information page
            elif tx_signals < min_tx_signals and len(text.strip()) < 80:
                if enable_raster_fallback and _cheap_blank_check_via_raster(pdf_bytes, page_idx):
                    kept = False
                    reason = "Very low information page (treated as blank)"

            decision = PageFilterDecision(
                page_number=page_idx,
                kept=kept,
                reason=reason
            )
            decisions.append(decision)

            if kept:
                pages_to_keep.append(page_idx)

    return pages_to_keep, decisions


def pages_list_to_azure_string(pages: list[int]) -> str:
    """
    Convert a list of 0-based page indices into the format Azure expects:
    "1-3,5,7-9" (1-based, ranges allowed).
    """
    if not pages:
        return ""

    pages = sorted(set(pages))
    ranges: list[str] = []
    start = pages[0] + 1  # convert to 1-based
    prev = start

    for p in pages[1:]:
        current = p + 1
        if current == prev + 1:
            prev = current
        else:
            if start == prev:
                ranges.append(str(start))
            else:
                ranges.append(f"{start}-{prev}")
            start = prev = current

    if start == prev:
        ranges.append(str(start))
    else:
        ranges.append(f"{start}-{prev}")

    return ",".join(ranges)


def filter_pdf_for_azure(
    pdf_bytes: bytes,
    *,
    min_tx_signals: int = 1,
) -> tuple[bytes | None, str, list[PageFilterDecision]]:
    """
    Main entry point for the Azure integration test.

    Returns:
        (pdf_bytes_to_send, pages_string_for_azure, filter_decisions)

    - Use `pages_string_for_azure` in the `pages=` parameter when calling Azure DI.
    - Use `filter_decisions` to show the user exactly which pages were kept/skipped and why
      (extremely important for cost transparency and trust).
    """
    useful_pages_0based, decisions = get_pages_to_analyze(
        pdf_bytes, min_tx_signals=min_tx_signals
    )

    if not useful_pages_0based:
        return None, "", decisions

    pages_str = pages_list_to_azure_string(useful_pages_0based)
    return pdf_bytes, pages_str, decisions


def count_original_pages(pdf_bytes: bytes) -> int:
    """Return total page count without retaining the open PDF handle."""
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        return len(pdf.pages)


def summarize_page_filter(
    decisions: list[PageFilterDecision],
    pages_str: str,
) -> dict[str, Any]:
    """Human-readable summary for UI and logs (cost-control transparency)."""
    total = len(decisions)
    kept = [d for d in decisions if d.kept]
    skipped = [d for d in decisions if not d.kept]
    blank_skips = sum(1 for d in skipped if "blank" in d.reason.lower())
    recon_skips = sum(
        1 for d in skipped if "reconciliation" in d.reason.lower() or "summary" in d.reason.lower()
    )
    other_skips = len(skipped) - blank_skips - recon_skips
    return {
        "original_pages": total,
        "kept_count": len(kept),
        "skipped_count": len(skipped),
        "pages_sent": pages_str,
        "blank_skipped": blank_skips,
        "reconciliation_skipped": recon_skips,
        "other_skipped": other_skips,
        "decisions": decisions,
    }


def format_filter_user_message(summary: dict[str, Any]) -> str:
    """One-line filter summary for Streamlit."""
    orig = summary["original_pages"]
    sent = summary["pages_sent"] or "(none)"
    skipped = summary["skipped_count"]
    if skipped == 0:
        return f"Original pages: {orig} · Pages sent to Azure: {sent} (no pages skipped)"
    parts: list[str] = []
    if summary["blank_skipped"]:
        parts.append(f"{summary['blank_skipped']} blank")
    if summary["reconciliation_skipped"]:
        parts.append(f"{summary['reconciliation_skipped']} reconciliation/summary")
    if summary["other_skipped"]:
        parts.append(f"{summary['other_skipped']} other low-info")
    skip_detail = " + ".join(parts) if parts else f"{skipped} low-value"
    return (
        f"Original pages: {orig} · Pages sent to Azure: {sent} "
        f"(skipped {skip_detail} page{'s' if skipped != 1 else ''})"
    )


# Rough list price guidance for S0 (varies by region/tier; informational only).
AZURE_DI_EST_COST_PER_PAGE_USD = 0.01


def estimate_azure_cost_usd(pages_sent_str: str) -> float | None:
    """Estimate billable pages from the Azure pages= string (ranges count as inclusive)."""
    if not pages_sent_str:
        return None
    count = 0
    for part in pages_sent_str.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            try:
                count += int(end_s) - int(start_s) + 1
            except ValueError:
                continue
        else:
            try:
                count += 1
            except ValueError:
                continue
    return round(count * AZURE_DI_EST_COST_PER_PAGE_USD, 3)


# ------------------------------------------------------------------
# Example usage (for documentation / testing)
# ------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    from pathlib import Path

    if len(sys.argv) < 2:
        print("Usage: python -m App.azure_di_utils /path/to/statement.pdf")
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    pdf_bytes = pdf_path.read_bytes()

    pages_to_send, decisions = get_pages_to_analyze(pdf_bytes)
    pages_str = pages_list_to_azure_string(pages_to_send)

    print(f"Original pages : {len(pdfplumber.open(BytesIO(pdf_bytes)).pages)}")
    print(f"Pages to analyze: {pages_str or '(none)'}")

    print("\nPage decisions:")
    for d in decisions:
        status = "KEEP" if d.kept else "SKIP"
        print(f"  Page {d.page_number + 1}: {status} — {d.reason}")