#!/usr/bin/env python3
"""Build Laura spot-check CSV + Markdown from latest HCC E1 rescore (spike-only)."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path

SPIKE = Path(__file__).resolve().parent
REPO = SPIKE.parents[1]
DEFAULT_RESCORE = SPIKE / "artifacts/phase1_g2_hcc_202604__rescored_e1_regions_v2"
DEFAULT_BASELINE = SPIKE / "artifacts/phase1_g2_hcc_202604"
CROP_ROOT = SPIKE / "artifacts/crop_diagnosis_g2_hcc_202604/final_kept"


def _snippet(lines: list[dict], payee: str, window: int = 5) -> str:
    texts = [(ln.get("text") or "").strip() for ln in lines if (ln.get("text") or "").strip()]
    if not texts:
        return ""
    idx = 0
    if payee:
        low = payee.lower()
        for i, t in enumerate(texts):
            if low in t.lower():
                idx = i
                break
    start = max(0, idx - 2)
    end = min(len(texts), idx + window)
    return " | ".join(texts[start:end])


def _priority(row: dict, baseline_payee: str) -> tuple[int, str]:
    payee = (row.get("cv_read_payee_candidate") or "").strip()
    reason = row.get("cv_read_payee_reason") or ""
    score = 0
    low = payee.lower()
    if not payee:
        return (100, row["crop_id"])
    if "+check_rule" in reason:
        score += 30
    if baseline_payee and "regions" in baseline_payee.lower():
        score += 25
    if any(x in low for x in ("concrete", "conercte", "concreto", "contrele", "olomut", "nondez", "qfernandez")):
        score += 20
    if "perez" in low or "misaen" in low or "jerman" in low:
        score += 18
    if reason in ("scan", "first_clean") and "hernandez" not in low:
        score += 12
    if "uriostegui" in low or "francisco" in low:
        score += 15
    return (-score, row["crop_id"])


def select_rows(
    rows: list[dict],
    baseline: dict[str, str],
    *,
    limit: int = 16,
    force_ids: list[str] | None = None,
) -> list[dict]:
    force_ids = force_ids or []
    by_id = {r["crop_id"]: r for r in rows}
    picked: list[dict] = []
    for cid in force_ids:
        if cid in by_id:
            picked.append(by_id[cid])
    remaining = [r for r in rows if r["crop_id"] not in {p["crop_id"] for p in picked}]
    ranked = sorted(
        remaining,
        key=lambda r: _priority(r, baseline.get(r["crop_id"], "")),
    )
    for r in ranked:
        if len(picked) >= limit:
            break
        if not (r.get("cv_read_payee_candidate") or "").strip():
            continue
        picked.append(r)
    return picked[:limit]


def build_package(
    rescore_dir: Path,
    baseline_dir: Path,
    out_csv: Path,
    out_md: Path,
    *,
    limit: int = 16,
) -> None:
    csv_path = rescore_dir / "side_by_side_harness.csv"
    raw_dir = rescore_dir / "raw_cv_responses"
    base_rows = {}
    base_csv = baseline_dir / "side_by_side_harness.csv"
    if base_csv.is_file():
        for r in csv.DictReader(open(base_csv, encoding="utf-8")):
            base_rows[r["crop_id"]] = r.get("cv_read_payee_candidate", "")

    rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
    force = [
        "P07_K08_w792_h334_a2.37",
        "P05_K09_w775_h342_a2.27",
        "P06_K09_w762_h342_a2.23",
        "P05_K05_w792_h337_a2.35",
    ]
    selected = select_rows(rows, base_rows, limit=limit, force_ids=force)

    fieldnames = [
        "crop_id",
        "page",
        "image_path",
        "baseline_payee",
        "e1_payee",
        "reason",
        "confidence",
        "raw_cv_text_snippet",
        "human_grade",
        "notes",
    ]
    out_rows = []
    for r in selected:
        cid = r["crop_id"]
        jp = raw_dir / f"{cid}.json"
        lines = []
        if jp.is_file():
            lines = json.loads(jp.read_text(encoding="utf-8")).get("lines") or []
        payee = r.get("cv_read_payee_candidate", "")
        img = r.get("image_path", "")
        if img and not Path(img).is_absolute():
            img_rel = img.replace("\\", "/")
        else:
            stem = cid.split("_")[0] + "_" + "_".join(cid.split("_")[1:3])
            img_rel = f"Scripts/spike/artifacts/crop_diagnosis_g2_hcc_202604/final_kept/{cid}_final.png"
        out_rows.append(
            {
                "crop_id": cid,
                "page": r.get("page", ""),
                "image_path": img_rel,
                "baseline_payee": base_rows.get(cid, ""),
                "e1_payee": payee,
                "reason": r.get("cv_read_payee_reason", ""),
                "confidence": r.get("cv_read_confidence", r.get("cv_read_payee_confidence", "")),
                "raw_cv_text_snippet": _snippet(lines, payee),
                "human_grade": "",
                "notes": "",
            }
        )

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)

    md = _render_md(out_rows, rescore_dir, out_csv)
    out_md.write_text(md, encoding="utf-8")
    print(f"Wrote {len(out_rows)} rows → {out_csv}")
    print(f"Wrote review sheet → {out_md}")


def _render_md(rows: list[dict], rescore_dir: Path, csv_path: Path) -> str:
    lines = [
        "# HCC E1 Human Review Package",
        "",
        f"**Generated**: {date.today().isoformat()}  ",
        f"**Source rescore**: `{rescore_dir.relative_to(REPO)}`  ",
        f"**Grading CSV to return**: fill `human_grade` and `notes` in `{csv_path.relative_to(REPO)}`",
        "",
        "## Review instructions",
        "",
        "1. Open each crop PNG under `Scripts/spike/artifacts/crop_diagnosis_g2_hcc_202604/final_kept/` "
        "(filename = `{crop_id}_final.png`).",
        "2. Compare **e1_payee** to what is written on the check after “Pay to the order of”.",
        "3. Grade using `Scripts/spike/GRADING_GUIDE.md` short codes: **c** / **s** / **p** / **w** / **e** / **b**.",
        "4. Save grades in the CSV `human_grade` column (free text after code is OK).",
        "5. Return the filled CSV to Robert — this gates G1 hybrid wiring for Regions/HCC.",
        "",
        "**Priority**: rows with `+check_rule`, OCR “Concrete” variants, and Perez-name fragments.",
        "",
        "---",
        "",
        "| crop_id | page | e1_payee | reason | baseline | snippet |",
        "|---------|------|----------|--------|----------|---------|",
    ]
    for r in rows:
        snip = (r["raw_cv_text_snippet"] or "")[:80].replace("|", "/")
        lines.append(
            f"| {r['crop_id']} | {r['page']} | {r['e1_payee']} | {r['reason']} | "
            f"{r['baseline_payee']} | {snip} |"
        )
    lines.extend(
        [
            "",
            "## Image paths",
            "",
        ]
    )
    for r in rows:
        lines.append(f"- **{r['crop_id']}**: `{r['image_path']}`")
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--rescore-dir", type=Path, default=DEFAULT_RESCORE)
    p.add_argument("--baseline-dir", type=Path, default=DEFAULT_BASELINE)
    p.add_argument("--limit", type=int, default=16)
    args = p.parse_args()
    today = date.today().strftime("%Y%m%d")
    out_csv = SPIKE / "artifacts" / f"hcc_e1_human_review_package_{today}.csv"
    out_md = SPIKE / "artifacts" / "HCC_E1_Human_Review_Package.md"
    build_package(args.rescore_dir, args.baseline_dir, out_csv, out_md, limit=args.limit)


if __name__ == "__main__":
    main()
