# FM-7 / FM-9 Spike Implementation Notes

**Date**: 2026-05-27  
**Context**: Post-B5 path-forward execution

---

## FM-7 — Payer / account-holder header penalty

### Problem

On QCR (First Metro), the account holder **QUALITY CHOICE ROOFING LLC** prints at the top of many checks. The engine often ranked that line over the true payee (Jan Fontana, vendors, etc.) — **3/16** graded `w` in B5.

### Approach chosen

**Profile-driven scoring penalty** (not new check rules):

1. **Client substrings** — `payer_header_penalty.substrings` in YAML (exact account-holder text from statement header).
2. **Generic suffix heuristic** — `looks_like_payer_header()`: long line, ends with LLC/INC/CORP, mostly uppercase, not a person name.
3. **Top-band extra penalty** — when `y_norm <= top_band_y_max`, additional penalty (header position).

### Alternatives considered

| Alternative | Why not first |
|-------------|----------------|
| Broad check rules (“Roofing LLC” → X) | High false-positive risk without human-confirmed OCR strings |
| Hard denylist in `boilerplate.py` | Bank-specific; belongs in profile for G1 per-client config |
| Strip top N lines before scoring | Fragile across layouts; scoring penalty is safer |

### Files

| File | Change |
|------|--------|
| `payee_extractor/engine.py` | `PayerHeaderPenalty`, `looks_like_payer_header()`, `_score_candidate` |
| `profiles/regions.yaml` | `generic_suffix_enabled: true` (HCC-safe with signature boost) |
| `profiles/first_metro.yaml` | QCR pilot: `quality choice roofing` substring |

### G1 wiring

On new client onboarding, copy account-holder name from statement page 1 into profile `payer_header_penalty.substrings`. Re-run harness `--rescore` only ($0).

---

## FM-9 — Cropper imaging-page detection

### Problem

QCR PDF: **0 crops on pages 5–8**, all **26 crops from 9–10**. Hard-coded `--pages 5-9` (Traditions/HCC) misses First Metro layout.

**Status**: Experimental PoC (not production hardened).

### Approach chosen

**Full-PDF scan PoC** in `diagnose_check_deposit_cropper.py`:

```bash
python Scripts/spike/diagnose_check_deposit_cropper.py \
  --pdf "Data/QCR 2026-04.pdf" \
  --detect-imaging-pages
```

Writes `imaging_pages.json` with `imaging_pages`, `recommended_pages_arg` (e.g. `9-10`).

**Heuristic**: `final_kept >= 3` after geometry + two-stage dedup (same pipeline as production harness).

**Known limitations**:
- Heuristic can be brittle across different bank layouts or scan quality.
- Full-PDF rasterization is relatively expensive if run on every statement.
- Intended as a bridge until a more robust solution (per-bank templates, better layout detection, or App-level configuration) is implemented during G1 (B6).

### Alternatives considered

| Alternative | Why not first |
|-------------|----------------|
| Always scan pages 1–last | Expensive; detector scopes imaging range |
| OCR “CHECK IMAGE” keywords on page | Needs CV/text; geometry-first is faster PoC |
| Relaxed MIN_HEIGHT globally | Over-crops register noise on non-imaging pages |

### G1 wiring

Integration sprint sets `SLAM_IMAGING_FIRST_PAGE` / `SLAM_IMAGING_LAST_PAGE` from detector output per statement (or bank template table). Merge detector into App cropper entry (B6).

### Validation

Re-run on QCR after Laura confirms imaging page range; compare crop count to bank summary check count.

---

## Tests

Smoke (`test_payee_extractor_smoke.py`): **15** active tests including FM-7 heuristic and first_metro profile load.
