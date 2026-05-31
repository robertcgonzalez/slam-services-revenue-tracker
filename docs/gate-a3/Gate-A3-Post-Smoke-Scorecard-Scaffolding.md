# Gate A3 — Post-Smoke Scorecard & Verdict Scaffolding

**Use this after `Collect-GateA3Evidence.ps1 -Both -UpdateDocs` (auto-filled) or manual evidence intake.**

**Session:** Deploy `4fa54010` · Collected 2026-05-30 22:24 UTC · Headless re-smoke after totals-assembly hotfix seed.

---

## 1. Quick Summary Table (Cursor fills this)

| Dimension                        | Result for HCC 2026-04 | Result for Auto Body Center | Notes |
|----------------------------------|------------------------|-----------------------------|-------|
| Register / tabular extraction    | 98 reg + 0 supp        | 110 rows (44 reg + 66 supp) | auto-collected |
| Check/imaging leg — detection    | Yes — 42 crops         | Yes — 56 crops              | `imaging_active=true` |
| Check/imaging leg — payee quality| 1 merge; sample payees | 4 merges; sample payees     | Option 2 rules not applied |
| Cropper activation (OpenCV)      | Yes                    | Yes                         | DPI=300, min_height=320 |
| Totals vs gold                   | PASS ($163,914 / $45,703.76) | **FAIL** withdrawals $354,909 vs gold $41,403 | Deposits match gold |
| New meta fields                  | `register_incomplete=false` | `register_incomplete=true`, `supplemental_by_amount=20` | Populated |
| Processing log cleanliness       | Clean                  | Clean                       | No poppler skip |

---

## 2. Check/Imaging Leg Verdict (The Critical One)

**Did the check/imaging leg deliver production-ready behavior on the live App Service?**

- [ ] **PASS — Production Ready**
- [x] **NEEDS MORE WORK**
- [ ] **CONDITIONAL PASS**
- [ ] **FAIL — Register-Only Recommended for Now**

**Primary Evidence:**

HCC is stable: 98 register rows, 42 crops, deposits/withdrawals match gold. Auto Body imaging leg is active (56 crops, 69 check DI extractions) and `register_incomplete` correctly appends 66 supplemental rows (110 total ≥85), but **withdrawal totals are inflated** ($354,909 vs gold $41,403) — supplemental dedupe/amount matching needs tightening before Laura pilot.

---

## 3. Overall Path Recommendation

- **Path A (Full Go-Live)**: Blocked — Auto Body withdrawal totals fail gold threshold.
- **Path A with Caveats**: Not recommended until withdrawal dedupe fixed.
- **Path B (Register-Only)**: Viable interim — HCC register+imaging payee merge works; Auto Body register-only (44 rows) was prior stable baseline.
- **Recommended next action**: Fix supplemental amount dedupe (Option 2 payee rules + stricter `_dedupe_azure_transactions` for amount-only check rows), re-smoke, then reassess Path A.

---

## 4. Commit & Documentation Scope

**Proposed commit message** (when owner requests commit):

```
Gate A3 re-smoke — HCC PASS, Auto Body rows PASS / withdrawals NEEDS WORK

Deploy 4fa54010; headless smoke + evidence collector; register_incomplete
assembly live after App hotfix seed; smoke waiter uses fresh gate-a3-smoke.log.
Auto Body: 110 rows but withdrawal totals inflated — dedupe follow-up required.
```

---

## 5. Risk / Rollback Notes

- One-command rollback for imaging leg: `.\Scripts\PowerShell\Set-AzureBankStatementDIAppSettings.ps1 -DisableDI`
- Full DI disable + redeploy still available.
- Postgres rollback not required for imaging issues (data layer is independent).

---

<!-- auto-collected 2026-05-30T22:24:00+00:00 -->
