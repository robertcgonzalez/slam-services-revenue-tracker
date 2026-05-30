#!/usr/bin/env python3
"""Smoke tests for payee_extractor refactor (spike-only).

Active gate: 15 tests in ``__main__`` (see ``artifacts/LATEST_HCC_E1.txt``).
Two historical 16-crop parity tests are kept for archaeology but not executed.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from App.payee_extractor import boilerplate as bp  # noqa: E402
from App.payee_extractor.engine import (  # noqa: E402
    ExtractorProfile,
    _find_authorized_signature_index,
    _legacy_extract,
    extract_payee_from_cv_lines,
    load_profile,
    looks_like_payer_header,
    rank_candidates,
)

TRADITIONS_RESCORED = (
    REPO / "Scripts/spike/artifacts/phase1_real_cv_read_harness_20260526T195813Z__rescored"
)
HCC_RESCORED_V2 = REPO / "Scripts/spike/artifacts/phase1_g2_hcc_202604__rescored_e1_regions_v2"
HCC_RESCORED_HUMAN_V3 = REPO / "Scripts/spike/artifacts/phase1_g2_hcc_202604__rescored_e1_human_v3"
HCC_RESCORED_P7 = (
    REPO / "Scripts/spike/artifacts/phase1_g2_hcc_202604__rescored_e1_profile_yaml_v4_p7"
)
HCC_RESCORED_FULL_HUMAN = (
    REPO / "Scripts/spike/artifacts/phase1_g2_hcc_202604__rescored_e1_profile_yaml_v4_p7_full_human"
)
HCC_HUMAN_REVIEW_CSV = REPO / "Scripts/spike/artifacts/hcc_e1_human_review_package_20260527.csv"
HCC_FULL_GROUND_TRUTH_CSV = REPO / "Scripts/spike/artifacts/HCC_E1_FULL_HUMAN_GROUND_TRUTH.csv"
LEGACY_PROFILE = ExtractorProfile(legacy_mode=True, ranking_mode="legacy")


def test_traditions_legacy_parity() -> None:
    csv_path = TRADITIONS_RESCORED / "side_by_side_harness.csv"
    raw_dir = TRADITIONS_RESCORED / "raw_cv_responses"
    assert csv_path.is_file(), csv_path
    mismatches = []
    for row in csv.DictReader(open(csv_path, encoding="utf-8")):
        cid = row["crop_id"]
        jp = raw_dir / f"{cid}.json"
        if not jp.is_file():
            continue
        lines = json.loads(jp.read_text(encoding="utf-8")).get("lines") or []
        old_payee = row.get("cv_read_payee_candidate", "")
        new_payee, _, _ = _legacy_extract(lines)
        if new_payee != old_payee:
            mismatches.append((cid, old_payee, new_payee))
    assert not mismatches, f"Legacy parity failures: {mismatches[:5]}"


def test_hcc_v2_cached_sanity() -> None:
    """Quick sanity: v2 HCC rescore has no obvious boilerplate winners."""
    csv_path = HCC_RESCORED_V2 / "side_by_side_harness.csv"
    assert csv_path.is_file(), csv_path
    garbage_samples = ("protectis", "pretected", "cash >", "regions bank", "authorized sign")
    hits = []
    for row in csv.DictReader(open(csv_path, encoding="utf-8")):
        payee = (row.get("cv_read_payee_candidate") or "").lower()
        if any(g in payee for g in garbage_samples):
            hits.append((row["crop_id"], row.get("cv_read_payee_candidate")))
    assert not hits, f"HCC v2 still has obvious garbage: {hits}"


def test_obvious_garbage_rejection() -> None:
    samples = [
        "CASH >",
        "Protectis by -PINKcryph",
        "Pretected by",
        "REGIONS BANK",
        "Security innitems",
        "AUTHORIZED SIGNALILL",
    ]
    for text in samples:
        assert bp.is_boilerplate(text, "regions"), text
        assert bp.extra_clean_rejects(text), text


def test_hcc_human_v3_matches_review_package() -> None:
    """human_v3 rescore must match Laura's 16-crop ground truth.

    Archived: superseded by ``test_hcc_full_human_matches_ground_truth`` (50 crops).
    Kept for regression archaeology only — not run from ``__main__``.
    """
    assert HCC_HUMAN_REVIEW_CSV.is_file(), HCC_HUMAN_REVIEW_CSV
    assert (HCC_RESCORED_HUMAN_V3 / "side_by_side_harness.csv").is_file(), HCC_RESCORED_HUMAN_V3
    v3 = {
        r["crop_id"]: r
        for r in csv.DictReader(
            open(HCC_RESCORED_HUMAN_V3 / "side_by_side_harness.csv", encoding="utf-8")
        )
    }
    misses = []
    for row in csv.DictReader(open(HCC_HUMAN_REVIEW_CSV, encoding="utf-8")):
        hg = (row.get("human_grade") or "").strip().lower()
        truth = (row.get("notes") if hg == "w" else row.get("e1_payee") or "").strip()
        got = (v3.get(row["crop_id"], {}).get("cv_read_payee_candidate") or "").strip()
        if got != truth:
            misses.append((row["crop_id"], got, truth))
    assert not misses, f"human_v3 vs human grades: {misses}"


def test_hcc_p7_matches_review_package() -> None:
    """Post page-7 rescore must still match Laura's 16-crop ground truth.

    Archived: superseded by full-human bundle + 50-crop ground truth test.
    Kept for regression archaeology only — not run from ``__main__``.
    """
    assert HCC_HUMAN_REVIEW_CSV.is_file(), HCC_HUMAN_REVIEW_CSV
    assert (HCC_RESCORED_P7 / "side_by_side_harness.csv").is_file(), HCC_RESCORED_P7
    p7 = {
        r["crop_id"]: r
        for r in csv.DictReader(
            open(HCC_RESCORED_P7 / "side_by_side_harness.csv", encoding="utf-8")
        )
    }
    misses = []
    for row in csv.DictReader(open(HCC_HUMAN_REVIEW_CSV, encoding="utf-8")):
        hg = (row.get("human_grade") or "").strip().lower()
        truth = (row.get("notes") if hg == "w" else row.get("e1_payee") or "").strip()
        got = (p7.get(row["crop_id"], {}).get("cv_read_payee_candidate") or "").strip()
        if got != truth:
            misses.append((row["crop_id"], got, truth))
    assert not misses, f"p7 vs human grades: {misses}"


def test_perez_ocr_spellings_not_in_check_rules() -> None:
    """B3: no check rules normalize Misaen/Jerman away from Laura-confirmed spellings."""
    from App.payee_extractor.apply_check_rules import load_check_rules

    rules = load_check_rules(REPO / "Data" / "check_payee_rules.csv")
    forbidden_outputs = {"Misael Perez", "German Perez", "Misael Hernandez", "German Hernandez"}
    for rule in rules:
        pattern = (rule.get("pattern") or "").lower()
        clean = (rule.get("clean_payee") or "").strip()
        if any(
            tok in pattern for tok in ("perez", "misaen", "jerman", "misaen", "misael p", "german")
        ):
            assert clean not in forbidden_outputs, f"Rule would override Perez policy: {rule}"
    patterns = {(r.get("pattern") or "").lower() for r in rules}
    assert "misaen" not in " ".join(patterns)
    assert "jerman" not in " ".join(patterns)


def test_check_rules_load() -> None:
    from App.payee_extractor.apply_check_rules import load_check_rules

    rules = load_check_rules(REPO / "Data" / "check_payee_rules.csv")
    assert len(rules) >= 6
    patterns = {r["pattern"] for r in rules}
    for required in (
        "Custom Conercte",
        "Fernando Hernadnez",
        "Cristone Concrete",
        "Customs Concreto",
        "Custonie Concrete",
        "OHernandez",
    ):
        assert required in patterns, f"missing rule pattern: {required}"


def _human_payee_truth(row: dict[str, str]) -> str:
    mg = (row.get("human_grade") or row.get("manual_grade") or "").strip().lower()
    if mg == "w":
        truth = (row.get("human_payee_truth") or row.get("notes") or "").strip()
        if truth == "Ocar Hernandez":
            return "Oscar Hernandez"
        return truth
    if mg == "c":
        return (
            row.get("human_payee_truth")
            or row.get("engine_payee_p7")
            or row.get("cv_read_payee_candidate")
            or ""
        ).strip()
    return (row.get("human_payee_truth") or row.get("cv_read_payee_candidate") or "").strip()


def test_hcc_full_human_matches_ground_truth() -> None:
    """Full 50-crop Laura grades must match latest rescore (post full-human check rules)."""
    assert HCC_FULL_GROUND_TRUTH_CSV.is_file(), HCC_FULL_GROUND_TRUTH_CSV
    assert (HCC_RESCORED_FULL_HUMAN / "side_by_side_harness.csv").is_file(), HCC_RESCORED_FULL_HUMAN
    engine = {
        r["crop_id"]: r
        for r in csv.DictReader(
            open(HCC_RESCORED_FULL_HUMAN / "side_by_side_harness.csv", encoding="utf-8")
        )
    }
    misses = []
    w_fixed = []
    for row in csv.DictReader(open(HCC_FULL_GROUND_TRUTH_CSV, encoding="utf-8")):
        cid = row["crop_id"]
        truth = _human_payee_truth(row)
        got = (engine.get(cid, {}).get("cv_read_payee_candidate") or "").strip()
        if got != truth:
            misses.append((cid, got, truth, row.get("human_grade")))
        if (row.get("human_grade") or "").strip().lower() == "w":
            p7 = (row.get("engine_payee_p7") or "").strip()
            if got == truth and p7 != truth:
                w_fixed.append(cid)
    assert len(w_fixed) == 4, f"expected 4 w-case fixes, got {w_fixed}"
    assert not misses, f"full_human vs ground truth: {misses}"


def test_hcc_full_human_manual_grades_present() -> None:
    csv_path = HCC_RESCORED_FULL_HUMAN / "side_by_side_harness.csv"
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
    assert len(rows) == 50
    graded = sum(1 for r in rows if (r.get("manual_grade") or "").strip())
    assert graded == 50
    from collections import Counter

    counts = Counter((r.get("manual_grade") or "").strip().lower() for r in rows)
    assert counts["c"] == 46
    assert counts["w"] == 4


def test_regions_profile_scoring_loaded() -> None:
    prof = load_profile("regions")
    assert prof.scoring.signature_zone.boost_after == 16.0
    assert prof.scoring.business_block_penalty.penalty == -20.0
    assert prof.scoring.payer_header_penalty.generic_suffix_enabled is True
    assert "authorized sign" in prof.signature_markers.primary_substrings


def test_payer_header_generic_heuristic() -> None:
    assert looks_like_payer_header("QUALITY CHOICE ROOFING LLC")
    assert not looks_like_payer_header("Jan Fontana")


def test_payer_header_person_wins_over_account_holder() -> None:
    """FM-7: payer LLC header must not beat payee after signature (regions)."""
    prof = load_profile("regions")
    lines = [
        _line("QUALITY CHOICE ROOFING LLC", 0),
        _line("PAY TO THE ORDER OF", 1),
        _line("Jan Fontana", 2),
        _line("AUTHORIZED SIGNATURE", 3),
        _line("Jan Fontana", 4),
    ]
    best = rank_candidates(lines, prof)
    assert best is not None
    assert best.text == "Jan Fontana"


def test_first_metro_profile_payer_substring() -> None:
    prof = load_profile("first_metro")
    assert "quality choice roofing" in prof.scoring.payer_header_penalty.substrings


def _line(text: str, idx: int = 0) -> dict:
    return {"text": text, "confidence": 0.9, "bbox": [0, idx * 20, 100, idx * 20 + 15]}


def test_signature_zone_person_wins_over_business_block() -> None:
    """Person name after AUTHORIZED SIGNATURE must beat Hernandez Custom Concrete LLC."""
    prof = load_profile("regions")
    lines = [
        _line("Hernandez Custom Concrete LLC", 0),
        _line("REGIONS BANK", 1),
        _line("AUTHORIZED SIGNATURE", 2),
        _line("Gabriel Hernandez", 3),
    ]
    best = rank_candidates(lines, prof)
    assert best is not None
    assert best.text == "Gabriel Hernandez"


def test_sionature_ocr_marker_detected() -> None:
    """OCR typo SIONATURE still triggers signature-line detection."""
    prof = load_profile("regions")
    lines = [
        _line("Hernandez Custom Concrete LLC", 0),
        _line("AUTHORIZED SIONATURE", 1),
        _line("Misael Hernandez", 2),
    ]
    sig_idx = _find_authorized_signature_index(lines, prof)
    assert sig_idx == 1
    best = rank_candidates(lines, prof)
    assert best is not None
    assert best.text == "Misael Hernandez"


def test_signalill_ocr_marker_detected() -> None:
    """AUTHORIZED SIGNALILL (page-7 OCR) triggers signature detection via profile markers."""
    prof = load_profile("regions")
    lines = [
        _line("REGIONS BANK", 0),
        _line("AUTHORIZED SIGNALILL", 1),
        _line("Jesus Hernandez", 2),
    ]
    sig_idx = _find_authorized_signature_index(lines, prof)
    assert sig_idx == 1


def test_engine_import() -> None:
    prof = load_profile("generic")
    assert prof.bank_id == "generic"
    payee, conf, reason = extract_payee_from_cv_lines([], prof)
    assert payee == "" and reason == "no_lines"


if __name__ == "__main__":
    _ACTIVE = (
        test_engine_import,
        test_obvious_garbage_rejection,
        test_check_rules_load,
        test_regions_profile_scoring_loaded,
        test_payer_header_generic_heuristic,
        test_payer_header_person_wins_over_account_holder,
        test_first_metro_profile_payer_substring,
        test_signature_zone_person_wins_over_business_block,
        test_sionature_ocr_marker_detected,
        test_signalill_ocr_marker_detected,
        test_traditions_legacy_parity,
        test_hcc_v2_cached_sanity,
        test_hcc_full_human_matches_ground_truth,
        test_hcc_full_human_manual_grades_present,
        test_perez_ocr_spellings_not_in_check_rules,
    )
    # Archived (not run): test_hcc_human_v3_matches_review_package, test_hcc_p7_matches_review_package
    for fn in _ACTIVE:
        fn()
    print(f"OK: payee_extractor smoke tests passed ({len(_ACTIVE)} active)")
