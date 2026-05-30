# Scripts/spike — G1 Azure CV hybrid check leg (local workspace)

**Status**: Phases 0–7 complete (see Blueprint v2.44.5+). Production App path is **Azure DI-only**; spike code is **not** wired to Streamlit by default.

**Artifacts**: `Scripts/spike/artifacts/` and `**/artifacts/` are **gitignored** (~184 MB PNG/JSON). Summaries live in markdown below and in [`Spike-Report-Computer-Vision-Check-Leg-20260527.md`](../../Spike-Report-Computer-Vision-Check-Leg-20260527.md) (committed at repo root).

## Read first (tier-1 — promote to git when indexing sprint lands)

| Doc | Role |
|-----|------|
| [`G1_HANDOFF_PACKAGE_INDEX.md`](G1_HANDOFF_PACKAGE_INDEX.md) | Integration entry — consume vs spike-only |
| [`POST_SPIKE_INTEGRATION_PLAN.md`](POST_SPIKE_INTEGRATION_PLAN.md) | Gates, sprint steps 3.1–3.5 |
| [`G1_READINESS_SNAPSHOT.md`](G1_READINESS_SNAPSHOT.md) | Honest go/no-go state |
| [`E1_E2_STATUS.md`](E1_E2_STATUS.md) | Extractor evolution metrics |
| [`EXTRACTOR_EVOLUTION_DESIGN.md`](EXTRACTOR_EVOLUTION_DESIGN.md) | Post-G2 design |
| [`PHASE7_NOTES.md`](PHASE7_NOTES.md) | Script catalog + archive guidance |

## Local-only by policy

- `CURSOR_PROMPT_*.md` — session prompts (gitignored)
- `artifacts/` — diagnostic output (gitignored)
- `Scripts/temp_*.py` — one-off diagnostics (gitignored)

Owner decision (`.gitignore` 2026-05-27): commit **selected** spike sources later; never bundle spike artifacts in Azure deploy zip (`Build-AzureDeployZip.ps1` excludes `spike/`).
