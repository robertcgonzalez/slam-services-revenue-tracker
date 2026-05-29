---
name: payee-extractor-hardening
category: payee
difficulty: medium
recommended_mode: reviewer-implementer
---

# Task: Payee Extractor Hardening / New Bank Profile

You are working on the photo-leg payee extraction system in `Scripts/spike/payee_extractor/` (and eventually `App/payee_extractor/`).

## Context
- The system uses bank-specific YAML profiles + scoring + rule application.
- Current profiles exist for: generic, traditions, regions, first_metro.
- Work must stay compatible with existing harnesses (`phase1_cv_read_harness.py`, `phase5_hybrid_pipeline.py`) and the `--rescore` workflow.
- Photo-leg only — do not touch tabular bank statement register parsing.

## Instructions
1. Analyze the current `engine.py`, `profiles/`, and `apply_check_rules.py`.
2. Identify the weakest failure modes on the target bank/client (ask user for specific bank or use recent HCC/Regions/Traditions evidence).
3. Create or significantly improve a bank-specific profile (new YAML or major update to existing one).
4. Add or refine scoring rules, denylists, signature markers, or business block penalties.
5. Add corresponding check rules to `Data/check_payee_rules.csv` if pattern-based cleaning is needed.
6. Validate using the existing rescoring harnesses on cached artifacts.
7. Produce a short "Profile Evolution Report" (markdown) documenting:
   - What changed
   - Before/after numbers on the test set
   - Any new edge cases discovered

## Success Criteria
- Measurable improvement on the target bank's hard cases (human-graded or rubric)
- Zero regressions on Traditions (the main regression guardrail)
- Clean, well-documented profile YAML
- All changes remain spike-compatible

## Constraints
- Prefer working on existing cached artifacts before making new Azure calls.
- Keep changes isolated to payee extraction logic.
- Update relevant spike docs (E1_E2_STATUS.md, POST_E1_VALIDATION_STATUS.md, etc.) if they exist.
