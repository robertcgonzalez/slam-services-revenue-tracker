# Gate A3 — Post-Smoke Scorecard & Verdict Scaffolding

**Use this after the human pastes the completed Evidence Template.**

---

## 1. Quick Summary Table (Cursor fills this)

| Dimension                        | Result for HCC 2026-04 | Result for Auto Body Center | Notes |
|----------------------------------|------------------------|-----------------------------|-------|
| Register / tabular extraction    |                        |                             |       |
| Check/imaging leg — detection    |                        |                             |       |
| Check/imaging leg — payee quality|                        |                             |       |
| Cropper activation (OpenCV)      |                        |                             |       |
| Page-range clamping working      |                        |                             |       |
| Consistency (same PDF, multiple runs) |                   |                             |       |
| Processing log cleanliness       |                        |                             |       |

---

## 2. Check/Imaging Leg Verdict (The Critical One)

**Did the check/imaging leg (the primary reason for the S0 + P0 imaging work) now deliver production-ready behavior on the live App Service?**

**Options (pick one):**

- [ ] **PASS — Production Ready**
  - Both PDFs show reliable cropper activation
  - Check payees are high quality (comparable to or better than spike baselines)
  - No page-range errors
  - Results reasonably consistent
  - Ready for Laura pilot under Path A

- [ ] **CONDITIONAL PASS**
  - Works on most cases but has specific known weaknesses (list them)
  - Acceptable for pilot with monitoring + fast rollback

- [ ] **NEEDS MORE WORK**
  - Still unreliable on one or both PDFs
  - Specific blockers remain (document exactly)

- [ ] **FAIL — Register-Only Recommended for Now**
  - Check/imaging leg still does not deliver value
  - Recommend Path B: keep DI for register only, disable check leg or roll back imaging settings

**Primary Evidence** (1-3 sentences):

_______________________________________________________________________________

---

## 3. Overall Path Recommendation

After reviewing the smoke evidence:

- **Path A (Full Go-Live)**: Proceed to Laura pilot + run `apply docs` on Blueprint + README.
- **Path A with Caveats**: Pilot with extra monitoring + explicit rollback plan.
- **Path B (Register-Only)**: Disable check/imaging leg for daily driver; keep register DI.
- **Rollback to pre-DI state**: Serious regressions observed.

**Recommended next action** (with owner confirmation):

_______________________________________________________________________________

---

## 4. Commit & Documentation Scope (Only if Path A or Conditional)

**Proposed commit message** (update as needed):

```
Gate A3 re-smoke PASS — check/imaging leg production-ready on B2

- All P0 imaging dependencies (OpenCV, pdf2image, Poppler) + page clamping deployed
- Data layer migrated to Postgres via Invoke-DataLayerGoLive.ps1 (98 clients / 36 requests)
- Gate A3 live re-smoke on both real PDFs validated the check/imaging leg
- Runbook updated with full evidence + verdict

Refs: docs/gate-a3/
```

**Files to commit** (after human review):
- All changes under `Scripts/PowerShell/Invoke-DataLayerGoLive.ps1` and related
- P0 imaging code changes + `requirements.txt` + deploy script updates
- `docs/go-live-execution-runbook.md` (final state)
- `docs/gate-a3/` artifacts

**apply docs** on Blueprint v2.44.20+ and README: **Only after explicit owner approval** and only if Path A verdict.

---

## 5. Risk / Rollback Notes

- One-command rollback for imaging leg: `.\Scripts\PowerShell\Set-AzureBankStatementDIAppSettings.ps1 -DisableDI`
- Full DI disable + redeploy still available.
- Postgres rollback not required for imaging issues (data layer is independent).

---

**Cursor: After filling this scorecard, update the main runbook "Gate A3" row, final production state table, and add a short "Gate A3 Verdict" subsection with the outcome and link to this file.**