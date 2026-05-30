# Perez OCR Policy — Hernandez Custom Concrete (Regions HCC)

**Date**: 2026-05-27 (owner decision **B3**, R/L)  
**Scope**: Spike + future G1 integration for **Hernandez Custom Concrete** Regions checks  
**Status**: **Binding** — do not override in check rules, normalization, or post-processing

---

## Correct payee spellings

For this client, the check-writer uses non-standard spellings that Azure CV Read often captures correctly:

| Correct form (keep) | Common wrong variants (do **not** force) |
|---------------------|------------------------------------------|
| **Misaen Perez** | Misael Perez, Misael Hernandez |
| **Jerman Perez** | German Perez, Jerman Hernandez |

Laura confirmed these spellings on **4 human-graded crops** (P05_K02, P05_K03, P06_K03, P07_K01, P07_K04 — Misaen/Jerman mix).

---

## Human validation evidence

| crop_id | Human-confirmed payee | Engine (profile_yaml_v4 / p7) |
|---------|----------------------|-------------------------------|
| P05_K02 | Jerman Perez | Jerman Perez |
| P05_K03 | Misaen Perez | Misaen Perez |
| P06_K03 | Misaen Perez | Misaen Perez |
| P07_K01 | Misaen Perez | Misaen Perez |
| P07_K04 | Jerman Perez | Jerman Perez |

Post-page-7 rescore (`profile_yaml_v4_p7`): **16/16** on the human review package — Perez spellings unchanged.

---

## Rules audit (2026-05-27)

| Location | Perez-related logic | Verdict |
|----------|---------------------|---------|
| `Data/check_payee_rules.csv` | No Perez patterns | **Safe** — no normalization rules |
| `payee_extractor/engine.py` | No Perez name mapping | **Safe** |
| `payee_extractor/apply_check_rules.py` | Client-scoped rules only; none for Perez | **Safe** |
| Smoke test `test_sionature_ocr_marker_detected` | Uses `Misael Hernandez` as synthetic **Hernandez-family** example only — not Perez policy | **Documented** — unrelated to Perez crops |

**Action for G1 sprint**: Do **not** add rules that map `Misaen` → `Misael` or `Jerman` → `German`. Display extracted payee as-is unless Laura explicitly requests a display alias (separate product decision).

---

## Related payees (not Perez policy)

Page-7 recovery introduced other Perez-family names on ungraded crops (e.g. `Luis Jorge Perez Garcia`, `Luis Fernando Perez`). These are **distinct payees**, not spelling variants of Misaen/Jerman — treat under normal human review, not this policy.

---

**Cross-references**: `HCC_HUMAN_VALIDATION_REPORT.md` §5, `G1_READINESS_BRIEF.md`, `PRE_G1_INTEGRATION_CHECKLIST.md`, `artifacts/hcc_e1_human_review_package_20260527.csv`
