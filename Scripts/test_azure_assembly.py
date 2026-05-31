"""Azure DI register + check assembly regression tests (Gate A3 smart supplemental).

Offline unit tests for ``_filter_supplemental_check_txns`` and
``_merge_azure_checks_into_transactions`` in ``App/bank_statements.py``.
Pins HCC-style complete-register behavior (no supplemental inflation) and
Auto Body-style incomplete-register behavior (append deduped check rows).

Usage:
    python Scripts/test_azure_assembly.py
    pytest Scripts/test_azure_assembly.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "App"))

import azure_document_intelligence as adi  # noqa: E402
import bank_statements as bs  # noqa: E402


def _register_row(
    description: str,
    amount: float,
    *,
    check_number: str = "",
) -> dict[str, str]:
    signed = -abs(amount) if amount > 0 else amount
    return {
        "Date": "2026-01-15",
        "Description": description,
        "Payee": "",
        "Amount": f"{abs(signed):.2f}",
        "Check#": check_number,
        "SignedAmount": f"{signed:.2f}",
        "Category": "Uncategorized",
    }


def _check_row(
    payee: str,
    amount: float,
    *,
    check_number: str = "",
) -> dict[str, str]:
    return _register_row(payee or "Check (image)", amount, check_number=check_number)


def _azure_check(pay_to: str, amount: float, check_number: str = "") -> dict:
    return {
        "pay_to": pay_to,
        "amount": amount,
        "check_number": check_number,
        "confidence_label": "High",
    }


def test_hcc_complete_register_no_supplemental() -> None:
    """HCC pattern: 98 register rows, fewer checks — register is authoritative."""

    register = [_register_row(f"Register debit {i}", 100.0 + i) for i in range(98)]
    checks = [_check_row(f"Payee {i}", 500.0 + i, check_number=str(1000 + i)) for i in range(40)]

    supplemental, stats, _ = bs._filter_supplemental_check_txns(register, checks)

    assert supplemental == []
    assert stats["register_incomplete"] is False
    assert stats["supplemental_skipped_duplicates"] == 0
    assert stats["register_is_sparse"] is False


def test_auto_body_incomplete_register_appends_unmatched_checks() -> None:
    """Auto Body pattern: sparse register vs many imaging-leg checks."""

    register = [_register_row(f"Tabular {i}", 50.0 + i) for i in range(44)]
    checks = [_check_row(f"Imaging payee {i}", 200.0 + i) for i in range(69)]

    supplemental, stats, _ = bs._filter_supplemental_check_txns(register, checks)

    assert stats["register_incomplete"] is True
    assert len(supplemental) == 69
    assert stats["supplemental_by_amount"] == 69
    assert stats["supplemental_skipped_duplicates"] == 0


def test_amount_dedup_skips_register_matches() -> None:
    """Checks whose amount already appears in register must not be appended."""

    register = [
        _register_row("Existing debit", 413.63),
        _register_row("Another debit", 250.00),
    ]
    checks = [
        _check_row("Dup by amount", 413.63),
        _check_row("New check", 999.99),
    ]

    supplemental, stats, _ = bs._filter_supplemental_check_txns(register, checks)

    assert len(supplemental) == 1
    assert supplemental[0]["Description"] == "New check"
    assert stats["supplemental_skipped_duplicates"] == 1
    assert stats["supplemental_skipped_by_amount"] == 1


def test_check_number_dedup_skips_register_matches() -> None:
    register = [_register_row("Check 1234", 100.0, check_number="1234")]
    checks = [_check_row("Same check image", 100.0, check_number="1234")]

    supplemental, stats, _ = bs._filter_supplemental_check_txns(register, checks)

    assert supplemental == []
    assert stats["supplemental_skipped_by_check_number"] == 1


def test_sparse_register_always_incomplete() -> None:
    register = [_register_row("Only row", 10.0)]
    checks = [_check_row("Imaging only", 25.0), _check_row("Another", 30.0)]

    supplemental, stats, _ = bs._filter_supplemental_check_txns(register, checks)

    assert stats["register_incomplete"] is True
    assert stats["register_is_sparse"] is True
    assert len(supplemental) == 2


def test_auto_body_partial_overlap_dedupes_known_amounts() -> None:
    """When a few register rows overlap check amounts, only novel checks append."""

    register = [_register_row(f"Tabular {i}", 100.0 + i) for i in range(44)]
    checks = []
    for i in range(69):
        # First 10 check amounts collide with register rows 0-9
        amount = 100.0 + i if i < 10 else 500.0 + i
        checks.append(_check_row(f"Payee {i}", amount))

    supplemental, stats, _ = bs._filter_supplemental_check_txns(register, checks)

    assert stats["register_incomplete"] is True
    assert stats["supplemental_skipped_by_amount"] == 10
    assert len(supplemental) == 59


def test_merge_by_check_number() -> None:
    df = pd.DataFrame(
        [
            {
                "Check#": "5678",
                "Payee": "",
                "SignedAmount": "-150.00",
                "Source": "register",
            }
        ]
    )
    checks = [_azure_check("ACME PLUMBING", 150.0, "5678")]

    out, merged, stats = bs._merge_azure_checks_into_transactions(df, checks)

    assert merged == 1
    assert out.at[0, "Payee"] == "ACME PLUMBING"
    assert stats["merged_by_check_number"] == 1
    assert stats["merged_by_amount"] == 0


def test_merge_by_amount_when_check_number_missing() -> None:
    """Traditions register rows lack Check# — payee merge falls back to amount."""

    df = pd.DataFrame(
        [
            {
                "Check#": "",
                "Payee": "",
                "SignedAmount": "-413.63",
                "Source": "register",
            }
        ]
    )
    checks = [_azure_check("AUTO PARTS SUPPLY", 413.63)]

    out, merged, stats = bs._merge_azure_checks_into_transactions(df, checks)

    assert merged == 1
    assert out.at[0, "Payee"] == "AUTO PARTS SUPPLY"
    assert stats["merged_by_amount"] == 1


def test_merge_respects_existing_payee() -> None:
    df = pd.DataFrame(
        [
            {
                "Check#": "",
                "Payee": "Already Set",
                "SignedAmount": "-100.00",
            }
        ]
    )
    checks = [_azure_check("SHOULD NOT APPLY", 100.0)]

    _, merged, _ = bs._merge_azure_checks_into_transactions(df, checks)

    assert merged == 0


def test_outlier_check_amounts_rejected() -> None:
    """OCR garbage amounts (memo/account bleed) must not append as supplemental."""

    register = [_register_row("EFT debit", 1000.0) for _ in range(44)]
    checks = [
        _check_row("Valid vendor", 250.00, check_number="1001"),
        _check_row("OCR garbage", 238_216.00),
        _check_row("Large but valid", 4995.71, check_number="1002"),
    ] + [_check_row(f"Fill {i}", 100.0 + i) for i in range(50)]

    supplemental, stats, _ = bs._filter_supplemental_check_txns(register, checks)

    amounts = [abs(float(r["SignedAmount"])) for r in supplemental]
    assert 238_216.0 not in amounts
    assert stats["supplemental_rejected_outliers"] == 1
    assert 4995.71 in amounts


def test_deposit_like_checks_skipped() -> None:
    register = [_register_row("Tabular", 50.0) for _ in range(44)]
    checks = [
        _check_row("Regular Deposit", 6904.99),
        _check_row("Real payee", 300.00, check_number="2001"),
    ] + [_check_row(f"Fill {i}", 120.0 + i) for i in range(50)]

    supplemental, stats, _ = bs._filter_supplemental_check_txns(register, checks)

    assert all("deposit" not in r["Description"].lower() for r in supplemental)
    assert stats["supplemental_rejected_deposits"] == 1
    assert any(r["Check#"] == "2001" for r in supplemental)


def test_duplicate_check_number_keeps_median_nearest() -> None:
    register = [_register_row("Tabular", 50.0) for _ in range(44)]
    checks = [
        _check_row("Vendor A", 280.00, check_number="501"),
        _check_row("Vendor A OCR", 6904.99, check_number="501"),
    ] + [_check_row(f"Fill {i}", 90.0 + i) for i in range(50)]

    supplemental, _, _ = bs._filter_supplemental_check_txns(register, checks)

    chk501 = [r for r in supplemental if bs._normalize_check_number(r.get("Check#")) == "501"]
    assert len(chk501) == 1
    assert float(chk501[0]["SignedAmount"]) == -280.00


def test_pick_best_checks_per_crop() -> None:
    checks = [
        {
            "crop_file": "check_P05C00.png",
            "amount": 280.0,
            "check_number": "501",
            "pay_to": "Vendor",
        },
        {
            "crop_file": "check_P05C00.png",
            "amount": 6904.99,
            "check_number": "501",
            "pay_to": "Vendor OCR",
        },
        {
            "crop_file": "check_P05C01.png",
            "amount": 150.0,
            "check_number": "502",
            "pay_to": "Other",
        },
    ]
    picked = adi._pick_best_checks_per_crop(checks)
    assert len(picked) == 2
    by_crop = {c["crop_file"]: c for c in picked}
    assert float(by_crop["check_P05C00.png"]["amount"]) == 280.0


def test_trim_supplemental_to_withdrawal_budget() -> None:
    supplemental = [
        _check_row("High quality", 400.00, check_number="1001"),
        _check_row("Noise A", 9000.00),
        _check_row("Noise B", 8500.00),
        _check_row("Good B", 350.00, check_number="1002"),
    ]
    trimmed, dropped = bs._trim_supplemental_to_withdrawal_budget(supplemental, 800.0)
    assert dropped >= 1
    assert sum(abs(float(r["SignedAmount"])) for r in trimmed) <= 900.0


def test_trim_keeps_all_rows_when_under_budget_despite_row_cap() -> None:
    """Auto Body regression: do not cap row count while supplemental total is under budget."""

    supplemental = [
        _check_row(f"Check {i}", 200.0 + i, check_number=str(1000 + i)) for i in range(50)
    ]
    trimmed, dropped = bs._trim_supplemental_to_withdrawal_budget(
        supplemental,
        41403.63,
        max_rows=49,
    )
    assert dropped == 0
    assert len(trimmed) == 50


def test_prune_register_keeps_unmatched_debits() -> None:
    """Only explicitly matched register rows are removed — not all non-EFT debits."""

    register = [
        {
            "Date": "2026-01-15",
            "Description": "Deposit",
            "Payee": "",
            "Amount": "6904.99",
            "Check#": "",
            "SignedAmount": "6904.99",
            "Category": "Uncategorized",
        },
        _register_row("Unmatched tabular check", 273.45),
        _register_row("EFT ACH", 500.0),
    ]
    supplemental = [_check_row(f"Imaging {i}", 150.0 + i) for i in range(50)]
    _, _, prune_indices = bs._filter_supplemental_check_txns(register, supplemental)
    pruned = bs._prune_register_for_supplemental(
        register,
        register_incomplete=True,
        supplemental=supplemental,
        prune_indices=prune_indices,
    )
    assert len(pruned) == 3
    assert any("Unmatched tabular" in r["Description"] for r in pruned)


def test_auto_body_withdrawal_residual_scenario() -> None:
    """Gate A3 Auto Body: keep unmatched register debit + supplemental imaging leg ≈ gold."""

    register = [_register_row("Unmatched tabular check", 273.45)]
    register.extend(
        {
            "Date": "2026-01-15",
            "Description": f"Deposit {i}",
            "Payee": "",
            "Amount": "100.00",
            "Check#": "",
            "SignedAmount": "100.00",
            "Category": "Uncategorized",
        }
        for i in range(43)
    )
    supplemental = [_check_row(f"Imaging check {i}", 822.6036 + (i - 25) * 0.01) for i in range(50)]

    register_kept = bs._prune_register_for_supplemental(
        register,
        register_incomplete=True,
        supplemental=supplemental,
        prune_indices=set(),
    )
    supplemental, trimmed = bs._trim_supplemental_to_withdrawal_budget(
        supplemental,
        41403.63,
        max_rows=49,
    )
    assert trimmed == 0
    assert len(register_kept) == 44

    for row in register_kept:
        row["Source"] = "register"
    for row in supplemental:
        row["Source"] = "check_image_crop"
    df = bs._parse_ocr_response_to_df({"transactions": register_kept + supplemental})
    df = bs._dedupe_azure_transactions(df)
    metrics = bs.transaction_summary_metrics(df)
    assert len(df) >= 85
    assert abs(float(metrics["withdrawals"]) - 41403.63) <= 100.0


def test_reconciliation_reference_from_statement_summary() -> None:
    summary = {"deposits": 41786.80, "withdrawals": 41403.63, "withdrawals_count": 49}
    ref = bs.reconciliation_reference_totals(None, summary)
    assert ref is not None
    assert ref["withdrawals"] == 41403.63
    assert ref["checks"] == 49


def test_iqr_outlier_rejects_memo_bleed_not_valid_checks() -> None:
    register = [_register_row("Tabular", 50.0) for _ in range(44)]
    checks = [
        _check_row(f"Vendor {i}", 250.0 + i * 3, check_number=str(2000 + i)) for i in range(45)
    ]
    checks.append(_check_row("Memo OCR bleed", 52_500.00))
    checks.append(_check_row("Valid large", 4995.71, check_number="2099"))

    supplemental, stats, _ = bs._filter_supplemental_check_txns(register, checks)
    amounts = [abs(float(r["SignedAmount"])) for r in supplemental]
    assert 52_500.0 not in amounts
    assert stats["supplemental_rejected_outliers"] >= 1
    assert 4995.71 in amounts


def _run_payee_rules_sample_test(rules_path: Path) -> None:
    prev = os.environ.get("SLAM_PAYEE_RULES_PATH")
    os.environ["SLAM_PAYEE_RULES_PATH"] = str(rules_path)
    try:
        bs.bootstrap_payee_rules_file(rules_path)
        df = pd.DataFrame(
            [
                {
                    "Date": "2026-01-15",
                    "Description": "POS PURCHASE WAL-MART STORE #1234",
                    "Payee": "",
                    "Amount": "50.00",
                    "Category": "Uncategorized",
                },
                {
                    "Date": "2026-01-16",
                    "Description": "ACH DEBIT PAYROLL ACME",
                    "Payee": "ACH DEBIT PAYROLL ACME",
                    "Amount": "1200.00",
                    "Category": "Uncategorized",
                },
            ]
        )
        rules = bs.load_payee_rules(rules_path)
        out, info = bs.apply_payee_rules(df, client_name="Test Client", rules=rules)
        assert info["rules_total"] == 25
        assert info["rules_used"] >= 2, info
        assert out.loc[0, "Payee"] == "Walmart"
        assert out.loc[1, "Payee"] == "ACH Payment"
    finally:
        if prev is None:
            os.environ.pop("SLAM_PAYEE_RULES_PATH", None)
        else:
            os.environ["SLAM_PAYEE_RULES_PATH"] = prev


def test_payee_rules_fire_on_sample_descriptions(tmp_path) -> None:
    """Canonical seed must load and match common Description substrings."""
    _run_payee_rules_sample_test(tmp_path / "payee_rules.csv")


def test_dedupe_azure_transactions_collapses_supplemental_amount_dupes() -> None:
    df = pd.DataFrame(
        [
            {"Check#": "", "SignedAmount": "-250.00", "Source": "check_image_crop"},
            {"Check#": "", "SignedAmount": "-250.00", "Source": "check_image_crop"},
            {"Check#": "", "SignedAmount": "-999.00", "Source": "check_image_crop"},
        ]
    )
    out = bs._dedupe_azure_transactions(df)
    assert len(out) == 2
    amounts = sorted(abs(float(x)) for x in out["SignedAmount"])
    assert amounts == [250.0, 999.0]


def main() -> int:
    test_hcc_complete_register_no_supplemental()
    test_auto_body_incomplete_register_appends_unmatched_checks()
    test_amount_dedup_skips_register_matches()
    test_check_number_dedup_skips_register_matches()
    test_sparse_register_always_incomplete()
    test_auto_body_partial_overlap_dedupes_known_amounts()
    test_merge_by_check_number()
    test_merge_by_amount_when_check_number_missing()
    test_merge_respects_existing_payee()
    test_outlier_check_amounts_rejected()
    test_deposit_like_checks_skipped()
    test_duplicate_check_number_keeps_median_nearest()
    test_pick_best_checks_per_crop()
    test_trim_supplemental_to_withdrawal_budget()
    test_trim_keeps_all_rows_when_under_budget_despite_row_cap()
    test_prune_register_keeps_unmatched_debits()
    test_auto_body_withdrawal_residual_scenario()
    test_reconciliation_reference_from_statement_summary()
    test_iqr_outlier_rejects_memo_bleed_not_valid_checks()
    test_dedupe_azure_transactions_collapses_supplemental_amount_dupes()
    with tempfile.TemporaryDirectory() as tmp:
        _run_payee_rules_sample_test(Path(tmp) / "payee_rules.csv")
    print("\n[OK] All Azure assembly regression checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
