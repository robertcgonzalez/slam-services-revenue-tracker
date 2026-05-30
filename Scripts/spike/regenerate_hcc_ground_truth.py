#!/usr/bin/env python3
"""
Regenerate the HCC_E1_FULL_HUMAN_GROUND_TRUTH.csv snapshot from the living side_by_side harness.

This script exists as preventive hygiene so the frozen ground truth used by smoke tests
can be easily refreshed if Laura ever updates manual_grade/notes in the living CSV.

Usage:
    python Scripts/spike/regenerate_hcc_ground_truth.py

It reads from the current "blessed" p7 side_by_side (the one with full human grades)
and overwrites artifacts/HCC_E1_FULL_HUMAN_GROUND_TRUTH.csv with a clean snapshot.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

SPIKE = Path(__file__).resolve().parent
REPO = SPIKE.parents[1]

# This should point to the living side_by_side that contains the manual grades
LIVING_GRADES_CSV = (
    SPIKE / "artifacts" / "phase1_g2_hcc_202604__rescored_e1_profile_yaml_v4_p7" / "side_by_side_harness.csv"
)

OUTPUT_CSV = SPIKE / "artifacts" / "HCC_E1_FULL_HUMAN_GROUND_TRUTH.csv"

DESIRED_COLUMNS = [
    "crop_id",
    "page",
    "image_path",
    "human_grade",
    "human_payee_truth",
    "human_notes",
    "engine_payee_p7",
    "engine_payee_full_human",
    "engine_reason",
    "engine_confidence",
    "cv_read_is_clean",
    "classifier_confidence",
]


def main() -> None:
    if not LIVING_GRADES_CSV.is_file():
        raise FileNotFoundError(f"Living grades CSV not found: {LIVING_GRADES_CSV}")

    rows = list(csv.DictReader(open(LIVING_GRADES_CSV, encoding="utf-8")))

    output_rows = []
    for r in rows:
        manual = (r.get("manual_grade") or "").strip()
        notes = (r.get("notes") or "").strip()

        # human_payee_truth logic mirrors what the smoke test does
        if manual.lower().startswith("w") and notes:
            truth = notes
        else:
            truth = r.get("cv_read_payee_candidate", "") or r.get("e1_payee", "")

        output_rows.append(
            {
                "crop_id": r["crop_id"],
                "page": r.get("page", ""),
                "image_path": r.get("image_path", ""),
                "human_grade": manual,
                "human_payee_truth": truth,
                "human_notes": notes,
                "engine_payee_p7": r.get("cv_read_payee_candidate", ""),
                "engine_payee_full_human": "",  # Will be empty on regeneration; filled during full_human rescore
                "engine_reason": r.get("cv_read_payee_reason", ""),
                "engine_confidence": r.get("cv_read_payee_confidence", r.get("cv_read_confidence", "")),
                "cv_read_is_clean": r.get("cv_read_is_clean", ""),
                "classifier_confidence": r.get("classifier_confidence", ""),
            }
        )

    # Write header + data
    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=DESIRED_COLUMNS)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"Regenerated {len(output_rows)} rows -> {OUTPUT_CSV.relative_to(REPO)}")
    print(f"Timestamp: {datetime.now().isoformat(timespec='seconds')}")
    print("Note: 'engine_payee_full_human' column is intentionally left blank on regeneration.")
    print("      It gets populated during the full_human rescore run.")


if __name__ == "__main__":
    main()