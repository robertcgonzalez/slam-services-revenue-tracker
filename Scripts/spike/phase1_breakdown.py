"""SLAM Services - Phase 1 result breakdown helper (spike-only).

Reads a ``phase1_real_cv_read_harness_*`` folder's ``side_by_side_harness.csv``
and prints an honest split of CV Read payee candidates by quality cohort:

    real-payee  (clean & not amount-line) → what Laura would see
    amount-line pollution                 → courtesy amount mis-extracted
    empty / not clean                     → manual entry needed
    deposit slips                         → separate cohort

Usage::

    python Scripts/spike/phase1_breakdown.py \
        Scripts/spike/artifacts/phase1_real_cv_read_harness_<UTC>

No Azure calls. Tiny diagnostic. Not part of the production pipeline.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path


def amount_like(t: str) -> bool:
    if not t:
        return False
    low = t.lower()
    bad_words = (
        " dollar",
        "dollar ",
        "dollars",
        " cent",
        "cents",
        "/no",
        "/wo",
        "/100",
        "xx/100",
        "and no/",
    )
    if any(w in low for w in bad_words):
        return True
    digits = sum(c.isdigit() for c in t)
    letters = sum(c.isalpha() for c in t)
    return bool(letters and digits / letters > 0.30)


def main(folder: str) -> int:
    csv_path = Path(folder) / "side_by_side_harness.csv"
    if not csv_path.is_file():
        print(f"ERROR: {csv_path} not found.", file=sys.stderr)
        return 1
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
    print(f"rows: {len(rows)}\n")

    reasons = Counter(r["cv_read_payee_reason"] for r in rows)
    print(f"extraction reasons: {dict(reasons)}\n")

    real_payees = [
        r for r in rows
        if r["cv_read_is_clean"] == "Yes"
        and not amount_like(r["cv_read_payee_candidate"])
        and r["predicted_class"] != "deposit_slip"
    ]
    amount_polluted = [
        r for r in rows
        if r["cv_read_is_clean"] == "Yes"
        and amount_like(r["cv_read_payee_candidate"])
        and r["predicted_class"] != "deposit_slip"
    ]
    empty_or_unclean = [
        r for r in rows
        if (r["cv_read_payee_candidate"] == "" or r["cv_read_is_clean"] != "Yes")
        and r["predicted_class"] != "deposit_slip"
    ]
    deposits = [r for r in rows if r["predicted_class"] == "deposit_slip"]

    print("Honest breakdown (post amount-line filter):")
    print(f"  real-payee candidates (clean & not amount-like): {len(real_payees)}")
    print(f"  amount-line pollution (was courtesy amount)    : {len(amount_polluted)}")
    print(f"  empty / not clean                              : {len(empty_or_unclean)}")
    print(f"  predicted deposit slips (separate cohort)      : {len(deposits)}")
    print()

    if deposits:
        print("Deposit slips:")
        for r in deposits:
            print(f"  {r['crop_id']}: keywords='{r['classifier_keywords']}'")
        print()

    print("Real-payee candidates (post-filter, what Laura would actually see):")
    for r in real_payees:
        print(f"  {r['crop_id']} (p{r['page']}, {r['cv_read_payee_reason']}): {r['cv_read_payee_candidate']}")
    print()

    if amount_polluted:
        print("Amount-line FALSE POSITIVES (extractor confused courtesy amount for payee):")
        for r in amount_polluted:
            print(f"  {r['crop_id']} (p{r['page']}, {r['cv_read_payee_reason']}): '{r['cv_read_payee_candidate']}'")
        print()

    print("Empty / not clean (manual entry needed):")
    for r in empty_or_unclean:
        print(f"  {r['crop_id']} (p{r['page']}, {r['cv_read_payee_reason']}): '{r['cv_read_payee_candidate']}'")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python Scripts/spike/phase1_breakdown.py <phase1_real_cv_read_harness_folder>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
