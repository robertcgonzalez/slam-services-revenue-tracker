# Imaging Leg Roadmap (Checks + Deposit Slips)

**Status**: June 2026  
**Context**: SLAM Services bank statement processing. Two-leg Document Intelligence architecture.

## Current State (Implemented)

- **Register leg**: `prebuilt-bankStatement` (or Layout) on non-imaging pages.
- **Imaging leg (primary)**: High-quality geometric cropping (v5) → per-crop `prebuilt-check.us` via Document Intelligence.
- Both checks and deposit slips are reliably cropped.
- Deposit slips are automatically organized into a `deposits/` subfolder (with `checks/` for symmetry).
- Crop metadata (classification) is persisted as sidecar JSONs.
- `Source` column in output CSVs shows `register` vs `check_image_crop`.
- Standalone reorganizer script available: `Scripts/reorganize_cropped_checks.py`
- UI shows breakdown and has a manual "Re-organize now" button.
- Deposit slip **data extraction** is intentionally deferred (wishlist for income stream metrics).

## Phase 1 – Stabilization (Current)

- Robust cropping for both checks and deposit slips.
- Clean folder organization.
- Good provenance and logging.
- Manual review path always available.

**Done.**

## Phase 2 – Deposit Slip Extraction (High Value)

- Create or tune a dedicated analyzer (Content Understanding or Custom Neural in DI) for deposit slips.
- Route `likely_deposit_slip` crops to the deposit analyzer.
- Extract key fields: amount, date, account, payer, memo, etc.
- Begin feeding deposit data into client income stream views/metrics.

**Owner decision needed**: Prioritize this before or after custom model work?

## Phase 3 – Custom Model for Imaging Pages (Highest Quality)

- Train a **Custom Neural model** (Document Intelligence) on your specific imaging pages from multiple banks/clients.
- Goal: Best possible extraction quality for both checks and deposit slips from photographs.
- This often outperforms generic prebuilts on real-world scanned/photographed financial documents.
- Can reduce reliance on geometric cropping over time (or use crops only for difficult cases).

**Expected benefit**: Significantly higher accuracy + fewer manual corrections.

## Phase 4 – Income Stream Metrics & Reporting

- Aggregate deposit data by client, category, time period.
- Compare deposits vs checks (cash flow view).
- Client-facing or internal dashboards for revenue visibility.
- Integration points with existing Revenue Requests / Power Query workflows.

## Phase 5 – Optional Enhancements

- Smarter crop selection (only send high-value or uncertain crops to paid models).
- Confidence-based human review queue focused on imaging leg.
- OneDrive watcher or scheduled job for new statements.
- Versioning of crop classification rules + analyzer versions for auditability.

## Quick Reference – Tools

- Reorganize any old crop folder:  
  `python Scripts/reorganize_cropped_checks.py --crop-dir "path/to/crops"`

- UI button: Available on Bank Statements page after processing a statement with crops.

---

**Next decision point**: Should we start Phase 2 (deposit slip extraction) or Phase 3 (Custom Neural model) first?

Both are high-leverage once on paid tier. Phase 3 usually gives the biggest quality jump for photographed documents. Phase 2 unlocks the income metrics work you mentioned.

Document owner: Robert  
Last updated: 2026-06 (post paid-tier transition planning)
