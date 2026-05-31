"""Local Enhanced OCR — Auto Body Center Jan-26 regression test (v2.44).

Pins the strict OCR parser output for the Auto Body Center Jan-26 scanned
PDF to the v2.43 Grok Vision baseline so any future change to the parser
(``_parse_ocr_lines_to_transactions``), preprocessor (``_preprocess_ocr_line``,
``_fuse_split_date_lines``, ``_splice_orphan_check_numbers``), or summary
extractor (``_extract_statement_summary``) that drops below the 92-row /
$41,786.80 / $41,403.63 / 49-check target fails fast in CI.

Runs against the cached EasyOCR lines at ``Scripts/_easyocr_cache_200.json``
(produced by ``Scripts/dump_easyocr_lines.py --dpi 200``) so the test is
fully offline and finishes in <2 seconds — no rasterization, no EasyOCR
model load. Re-cache when the cropper or OCR engine changes meaningfully.

Azure DI assembly (register + check supplemental dedupe) is covered separately
by ``Scripts/test_azure_assembly.py`` (HCC + Auto Body fixture patterns).

Usage:
    python Scripts/test_local_ocr_regression.py
    pytest Scripts/test_local_ocr_regression.py        # also works
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "App"))

import local_enhanced_ocr as leo  # noqa: E402

CACHE_PATH = REPO_ROOT / "Scripts" / "_easyocr_cache_200.json"
PIPELINE_LINES_CACHE = REPO_ROOT / "Scripts" / "_pipeline_lines.json"

EXPECTED_DEPOSITS = 41786.80
EXPECTED_WITHDRAWALS = 41403.63
EXPECTED_CHECKS = 49
EXPECTED_TRANSACTIONS = 92


def _load_lines(path: Path) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError(
            f"Cache missing: {path}\nRegenerate with: python Scripts/dump_easyocr_lines.py --dpi 200"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    if "lines" in data:  # _pipeline_lines.json format
        return list(data["lines"])
    if "pages" in data:  # _easyocr_cache_*.json format
        out: list[str] = []
        for page in data["pages"]:
            out.extend(page)
        return out
    raise ValueError(f"Unrecognized cache format in {path}")


def _run(lines: list[str]) -> tuple[list[dict], dict]:
    txns = leo._parse_ocr_lines_to_transactions(lines, 2026)
    txns = leo._filter_balance_only_rows(leo._dedupe_transactions(txns))
    summary = leo._extract_statement_summary(lines)
    grok = leo._compute_grok_totals(txns, summary_override=summary)
    return txns, grok


def _assert_baseline(label: str, lines: list[str]) -> None:
    txns, grok = _run(lines)

    deposits = grok["deposits"]
    withdrawals = grok["withdrawals"]
    checks = grok["checks"]
    transactions = grok["transactions"]

    print(f"\n[{label}] lines={len(lines)} -> {transactions} txn(s) | "
          f"deposits=${deposits:,.2f} | withdrawals=${withdrawals:,.2f} | checks={checks}")

    assert transactions == EXPECTED_TRANSACTIONS, (
        f"[{label}] transaction count regressed: got {transactions}, expected {EXPECTED_TRANSACTIONS}"
    )
    assert checks == EXPECTED_CHECKS, (
        f"[{label}] check count regressed: got {checks}, expected {EXPECTED_CHECKS}"
    )
    assert abs(deposits - EXPECTED_DEPOSITS) < 0.01, (
        f"[{label}] deposits drifted: got ${deposits:,.2f}, expected ${EXPECTED_DEPOSITS:,.2f}"
    )
    assert abs(withdrawals - EXPECTED_WITHDRAWALS) < 0.01, (
        f"[{label}] withdrawals drifted: got ${withdrawals:,.2f}, expected ${EXPECTED_WITHDRAWALS:,.2f}"
    )

    # Sanity: no zero-amount rows, no summary-line pollution
    for t in txns:
        amt = float(str(t.get("SignedAmount") or 0).replace(",", "") or 0)
        desc = str(t.get("Description") or "")
        assert amt != 0.0, f"[{label}] zero-amount row leaked: {t}"
        assert "withdrawals and other" not in desc.lower(), (
            f"[{label}] summary-line pollution leaked: {desc!r}"
        )
        assert "statement activity" not in desc.lower(), (
            f"[{label}] section header leaked as transaction: {desc!r}"
        )


def test_auto_body_center_jan26_cache() -> None:
    """Parser hits 92 / $41,786.80 / $41,403.63 / 49 on cached page-grouped lines."""

    _assert_baseline("cache_per_page", _load_lines(CACHE_PATH))


def test_auto_body_center_jan26_pipeline_lines() -> None:
    """Parser hits same baseline on pipeline-style (live OCR) line output.

    This pinpoints regressions in ``_fuse_split_date_lines`` /
    ``_splice_orphan_check_numbers`` because the live pipeline buckets
    EasyOCR tokens differently (date-only rows split off, orphan check
    numbers floated to their own line) than the per-page cache.
    """

    if not PIPELINE_LINES_CACHE.is_file():
        print(f"[skip] {PIPELINE_LINES_CACHE.name} not cached — run "
              f"Scripts/dump_pipeline_ocr_lines.py once to capture the live OCR output.")
        return
    _assert_baseline("pipeline_lines", _load_lines(PIPELINE_LINES_CACHE))


def test_is_clean_payee_guards() -> None:
    """v2.44.3 — `_is_clean_payee` must reject all 8+ OCR-garbage payees
    observed in live cropper output, AND accept normal multi-word names
    that the laptop run wrote correctly.
    """

    # Live OCR garbage captured from the Codespace cropper @ DPI 220 plus
    # the laptop's 2026-05-26T11-22_export.csv at DPI 250. Every one of
    # these would currently be written into Payee at Confidence=High.
    bad = [
        "Os.90",
        "0 Os.90",
        "Slon8if4 RS0-od",
        "ORDER OFE Hluuk",
        "ORDER OFE Huszadleez 330.4R",
        "ORDER OF Iudsz",
        "ORDER OF _ Wuulu",
        "ORDER OF Gstnaktop 1 Oo_ 738.D3",
        "ORDER OF_ Fhs",
        "ORDER OF [NtssnN 97",
        "ORDER Of _ 6 3 Zhe",
        "ORDER Of",
        "Order Of",
        "Order Of 4Eiies Dcllars @E1",
        "Order Of 77",
        "CRDER OK Som QS0-0j",
        "[NtssnN 97",
    ]
    for s in bad:
        assert not leo._is_clean_payee(s), (
            f"_is_clean_payee falsely accepted OCR garbage: {s!r}"
        )

    # Multi-word business / personal names that should always pass. None
    # of these are present in the Auto Body Center test PDF; they pin the
    # heuristic to common, defensible shapes so we don't drift into
    # over-rejection.
    good = [
        "ACME PLUMBING",
        "John Smith",
        "Walmart Inc",
        "Cullman Electric",
        "ACME Co",
        "Target",
        "Costco Wholesale",
        "STATE OF ALABAMA",
        "MERCH BNKCD DEPOSIT",
        "AMEX EPAYMENT",
        "TLF CULLMAN FLORIST",
    ]
    for s in good:
        assert leo._is_clean_payee(s), f"_is_clean_payee falsely rejected: {s!r}"


def main() -> int:
    test_auto_body_center_jan26_cache()
    test_auto_body_center_jan26_pipeline_lines()
    test_is_clean_payee_guards()
    print("\n[OK] All Local Enhanced OCR regression checks passed for v2.44.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
