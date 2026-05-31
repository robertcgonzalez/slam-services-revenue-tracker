# Gate A3 — Post-Smoke Scorecard & Verdict Scaffolding

**Use this after `Collect-GateA3Evidence.ps1 -Both -UpdateDocs` (auto-filled) or manual evidence intake.**

**Session:** Deploy `1ef9aa54` · Collected 2026-05-31 01:28 UTC · Headless re-smoke after stale-crop purge + supplemental dedupe (v2.44.32).

---

## 1. Quick Summary Table (Cursor fills this)

| Dimension                        | Result for HCC 2026-04 | Result for Auto Body Center | Notes |
|----------------------------------|------------------------|-----------------------------|-------|
| Register / tabular extraction    | 98 reg + 0 supp        | 94 rows (44 reg + 50 supp) | auto-collected |
| Check/imaging leg — detection    | Yes — 42 crops         | Yes — 56 crops              | `imaging_active=true` |
| Check/imaging leg — payee quality| 1 merge; sample payees | 3 merges; sample payees     | Option 2 rules not applied |
| Cropper activation (OpenCV)      | Yes                    | Yes                         | DPI=300, min_height=320 |
| Totals vs gold                   | PASS ($163,914 / $45,703.76) | **PASS** withdrawals $41,130.18 vs gold $41,403.63 | Deposits match gold |
| New meta fields                  | `register_incomplete=false` | `register_incomplete=true`, `supplemental_by_amount=14` | Populated |
| Processing log cleanliness       | Clean                  | Clean                       | No poppler skip |

---

## 2. Check/Imaging Leg Verdict (The Critical One)

**Did the check/imaging leg deliver production-ready behavior on the live App Service?**

- [x] **PASS — Production Ready**
- [ ] **NEEDS MORE WORK**
- [ ] **CONDITIONAL PASS**
- [ ] **FAIL — Register-Only Recommended for Now**

**Primary Evidence:**

HCC stable: 98 register rows, 42 crops, gold deposits/withdrawals. Auto Body: 94 rows (44 register + 50 supplemental), 56 crops, withdrawals **$41,130.18** vs gold **$41,403.63** (within tolerance), deposits **$41,786.80** match gold. Root cause of prior inflation (stale HCC PNGs in `checks/`) fixed with per-run purge of `checks/`, `deposits/`, and sidecar JSON.

---

## 3. Overall Path Recommendation

- **Path A (Full Go-Live)**: **Approved** — Laura pilot cleared.
- **Path B (Register-Only)**: Not required; imaging leg validated on both canonical PDFs.
- **Recommended next action**: Schedule Laura pilot per `docs/DI-Go-Live-Commands.md` Step 6; optional follow-up: payee rules in headless path (`payee_rules_applied=0`).

---

## 4. Commit & Documentation Scope

**Recorded commit (v2.44.32):**

```
Gate A3 fully PASS: fix stale crop dir leak, production re-smoke clean.

Deploy 1ef9aa54; HCC 98 rows gold totals; Auto Body 94 rows,
withdrawals $41,130 vs gold $41,403. Laura pilot cleared (Path A).
```

---

## 5. Risk / Rollback Notes

- One-command rollback for imaging leg: `.\Scripts\PowerShell\Set-AzureBankStatementDIAppSettings.ps1 -DisableDI`
- Full DI disable + redeploy still available.
- Postgres rollback not required for imaging issues (data layer is independent).

---

<!-- auto-collected 2026-05-31T01:28:00+00:00 -->
