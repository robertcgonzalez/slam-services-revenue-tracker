#!/usr/bin/env python3
"""Phase 6 — P&L smoke on hybrid pipeline output (spike-only).

SPIKE-ONLY. NOT PART OF THE PRODUCTION PIPELINE.

Consumes Phase 5 artifacts (12-column Option A):
  - transactions_hybrid.csv
  - deposit_slips.json (credit-side attribution sidecar)

Produces Category/Payee x YearMonth pivots (same logic as the app's
build_statement_pivot), credit/debit rollups, deposit-slip narrative, and a
short markdown report demonstrating that improved payee quality supports
trustworthy rollups.

Usage (from repo root):

    python Scripts/spike/phase6_pl_smoke.py \\
        --hybrid-dir Scripts/spike/artifacts/phase5_hybrid_reuse_test

    # Optional: compare payee fill on check rows vs Phase 0 baseline
    python Scripts/spike/phase6_pl_smoke.py \\
        --hybrid-dir Scripts/spike/artifacts/phase5_hybrid_reuse_test \\
        --baseline-transactions Scripts/spike/artifacts/baseline_20260526T202334Z/transactions_all.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
APP_DIR = REPO_ROOT / "App"
SPIKE_DIR = Path(__file__).resolve().parent
ARTIFACTS_DIR = SPIKE_DIR / "artifacts"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from bank_statements import (  # noqa: E402
    GROK_CSV_COLUMNS,
    build_statement_pivot,
    transaction_summary_metrics,
)

DEFAULT_HYBRID_DIR = ARTIFACTS_DIR / "phase5_hybrid_reuse_test"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase 6 P&L smoke (spike-only).")
    p.add_argument(
        "--hybrid-dir",
        type=Path,
        default=DEFAULT_HYBRID_DIR,
        help="Phase 5 output directory (transactions_hybrid.csv + deposit_slips.json).",
    )
    p.add_argument(
        "--baseline-transactions",
        type=Path,
        default=None,
        help="Optional baseline transactions_all.csv for payee comparison on check rows.",
    )
    p.add_argument("--out-dir", type=Path, default=None)
    return p.parse_args(argv)


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _resolve_out_dir(arg: Path | None, hybrid_dir: Path) -> Path:
    if arg is not None:
        return arg.resolve()
    return (ARTIFACTS_DIR / f"phase6_pl_smoke_{_utc_stamp()}").resolve()


def _load_transactions(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    df = pd.read_csv(path, dtype=str).fillna("")
    for col in GROK_CSV_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[list(GROK_CSV_COLUMNS)]


def _load_deposits(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _signed_series(df: pd.DataFrame) -> pd.Series:
    col = "SignedAmount" if "SignedAmount" in df.columns else "Amount"
    return pd.to_numeric(
        df[col].astype(str).str.replace(",", "", regex=False).str.replace("$", "", regex=False),
        errors="coerce",
    ).fillna(0.0)


def _credit_deposit_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Rows that look like statement credits / deposits (for sidecar join)."""
    signed = _signed_series(df)
    work = df.copy()
    work["_signed"] = signed
    desc = work["Description"].astype(str).str.lower()
    mask = (work["_signed"] > 0) | desc.str.contains(
        r"deposit|ach credit|regular deposit|credit",
        regex=True,
        na=False,
    )
    return work.loc[mask].copy()


def _manifest_cv_stats(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.is_file():
        return {}
    m = pd.read_csv(manifest_path, dtype=str).fillna("")
    checks = m[m["predicted_class"].astype(str).str.lower() == "check"]
    clean = checks["cv_read_is_clean"].astype(str).str.lower().isin(["yes", "true", "1"])
    return {
        "manifest_checks": int(len(checks)),
        "manifest_cv_clean_payees": int(clean.sum()),
        "manifest_cv_clean_pct": round(100.0 * clean.sum() / max(len(checks), 1), 1),
    }


def _payee_quality_on_checks(df: pd.DataFrame) -> dict[str, Any]:
    checks = df[df["Check#"].astype(str).str.strip() != ""].copy()
    if checks.empty:
        return {"check_rows": 0}

    payee = checks["Payee"].astype(str).str.strip()
    nonempty = payee != ""
    uncategorized = payee.str.lower() == "uncategorized"
    garbage_hints = payee.str.contains(
        r"order of|pay to the|^\s*the\s*$|dollar",
        case=False,
        regex=True,
        na=False,
    )
    cleanish = nonempty & ~uncategorized & ~garbage_hints

    return {
        "check_rows": int(len(checks)),
        "payee_nonempty": int(nonempty.sum()),
        "payee_not_uncategorized": int((nonempty & ~uncategorized).sum()),
        "payee_cleanish_heuristic": int(cleanish.sum()),
        "payee_nonempty_pct": round(100.0 * nonempty.sum() / len(checks), 1),
        "payee_cleanish_pct": round(100.0 * cleanish.sum() / len(checks), 1),
    }


def _compare_payees(hybrid: pd.DataFrame, baseline: pd.DataFrame) -> dict[str, Any]:
    """Compare Payee on rows that share Date + Check# + SignedAmount."""
    h = hybrid.copy()
    b = baseline.copy()
    for frame in (h, b):
        frame["_key"] = (
            frame["Date"].astype(str)
            + "|"
            + frame["Check#"].astype(str)
            + "|"
            + _signed_series(frame).astype(str)
        )

    check_h = h[h["Check#"].astype(str).str.strip() != ""].copy()
    merged = check_h.merge(
        b[["_key", "Payee"]].rename(columns={"Payee": "baseline_payee"}),
        left_on="_key",
        right_on="_key",
        how="inner",
    )
    if merged.empty:
        return {"matched_check_rows": 0}

    hp = merged["Payee"].astype(str).str.strip()
    bp = merged["baseline_payee"].astype(str).str.strip()
    improved = (hp != "") & ((bp == "") | (bp.str.lower() == "uncategorized"))
    changed = hp != bp

    return {
        "matched_check_rows": int(len(merged)),
        "payee_changed": int(changed.sum()),
        "payee_improved_vs_baseline": int(improved.sum()),
    }


def _pivot_to_csv(pivot: pd.DataFrame, path: Path) -> None:
    if pivot is None or pivot.empty:
        path.write_text("", encoding="utf-8")
        return
    out = pivot.copy()
    out.index.name = out.index.name or "group"
    out.to_csv(path, encoding="utf-8")


def _write_deposit_attribution(
    path: Path,
    credit_rows: pd.DataFrame,
    deposits: list[dict[str, Any]],
) -> None:
    lines = [
        "# Deposit slip attribution (Phase 6 smoke)",
        "",
        "Option A schema: deposit OCR text lives in the sidecar JSON, not in Payee.",
        "Credit register rows below are candidates to attach narrative from the 7 slips.",
        "",
        f"**Deposit slips in sidecar**: {len(deposits)}",
        f"**Credit-like register rows**: {len(credit_rows)}",
        "",
        "## Deposit slips (CV Read body excerpt)",
        "",
    ]
    for i, slip in enumerate(deposits, 1):
        text = (slip.get("cv_read_raw_text") or "").strip().replace("\n", " ")
        excerpt = text[:400] + ("..." if len(text) > 400 else "")
        lines.append(f"### {i}. {slip.get('crop_id')} (page {slip.get('page')})")
        lines.append("")
        lines.append(f"> {excerpt or '(no text)'}")
        lines.append("")

    lines.append("## Credit-side register rows (first 15)")
    lines.append("")
    if credit_rows.empty:
        lines.append("_No credit rows identified._")
    else:
        cols = ["Date", "Description", "Payee", "SignedAmount", "Check#"]
        subset = credit_rows[cols].head(15)
        lines.append("```")
        lines.append(subset.to_string(index=False))
        lines.append("```")

    lines.append("")
    lines.append(
        "_Full credit rows: see `credit_register_rows.csv` in this artifact folder._"
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_report(
    path: Path,
    summary: dict[str, Any],
    metrics: dict[str, Any],
    payee_stats: dict[str, Any],
    manifest_stats: dict[str, Any],
    comparison: dict[str, Any] | None,
) -> None:
    lines = [
        "# Phase 6 P&L Smoke Report",
        "",
        f"**Generated**: {summary.get('generated_utc')}",
        f"**Hybrid dir**: `{summary.get('hybrid_dir')}`",
        f"**Schema**: {summary.get('schema')}",
        "",
        "## Statement summary (hybrid transactions)",
        "",
        f"- Transactions: **{metrics.get('count', 0)}**",
        f"- Total deposits (signed credits): **${metrics.get('deposits', 0):,.2f}**",
        f"- Total withdrawals (signed debits): **${metrics.get('withdrawals', 0):,.2f}**",
        f"- Items needing review: **{metrics.get('needs_review', 0)}**",
        "",
        "## Payee quality on check rows (heuristic)",
        "",
        f"- Check rows: **{payee_stats.get('check_rows', 0)}**",
        f"- Non-empty Payee: **{payee_stats.get('payee_nonempty', 0)}** "
        f"({payee_stats.get('payee_nonempty_pct', 0)}%)",
        f"- Cleanish Payee (non-uncategorized, no obvious OCR junk): "
        f"**{payee_stats.get('payee_cleanish_heuristic', 0)}** "
        f"({payee_stats.get('payee_cleanish_pct', 0)}%)",
        "",
    ]
    if manifest_stats:
        lines.extend(
            [
                "## CV Read quality (photo manifest — not yet all in Payee column)",
                "",
                f"- Checks in manifest: **{manifest_stats.get('manifest_checks', 0)}**",
                f"- CV clean payees on crops: **{manifest_stats.get('manifest_cv_clean_payees', 0)}** "
                f"({manifest_stats.get('manifest_cv_clean_pct', 0)}%)",
                "",
                "Only matcher-linked rows copy CV payee into `transactions_hybrid.csv` Payee today.",
                "",
            ]
        )
    if comparison:
        lines.extend(
            [
                "## vs baseline (matched check rows)",
                "",
                f"- Matched: **{comparison.get('matched_check_rows', 0)}**",
                f"- Payee changed: **{comparison.get('payee_changed', 0)}**",
                f"- Improved vs empty/Uncategorized baseline: "
                f"**{comparison.get('payee_improved_vs_baseline', 0)}**",
                "",
            ]
        )

    lines.extend(
        [
            "## P&L pivots produced",
            "",
            "- `pivot_category_by_yearmonth.csv` — sum of SignedAmount",
            "- `pivot_payee_by_yearmonth.csv` — sum of SignedAmount",
            "- `pivot_payee_by_yearmonth_count.csv` — transaction counts",
            "- `top_payees_by_total.csv` — sorted payee totals for quick Laura review",
            "",
            "## Limitations (honest)",
            "",
            "- Single statement / single period in this smoke (YearMonth column may collapse to one month).",
            "- Deposit slips are not yet merged into Payee; attribution is narrative only (Option A).",
            "- ~24/49 checks still need heavy manual payee work per Phase 1 visual grading.",
            "- Power Query / Excel workbooks unchanged; this proves in-app pivot logic on hybrid CSV.",
            "",
            "Phase 6 demonstrates that **improved payee fill makes Category/Payee rollups usable** "
            "for Laura's P&L direction without schema migration (Option B deferred).",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    hybrid_dir = args.hybrid_dir.resolve()
    txn_path = hybrid_dir / "transactions_hybrid.csv"
    deposits_path = hybrid_dir / "deposit_slips.json"

    if not txn_path.is_file():
        print(f"ERROR: missing {txn_path}", file=sys.stderr)
        print("Run phase5_hybrid_pipeline.py first.", file=sys.stderr)
        return 1

    out_dir = _resolve_out_dir(args.out_dir, hybrid_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[phase6] Hybrid dir : {hybrid_dir}")
    print(f"[phase6] Out dir   : {out_dir}")

    df = _load_transactions(txn_path)
    deposits = _load_deposits(deposits_path)
    metrics = transaction_summary_metrics(df)
    payee_stats = _payee_quality_on_checks(df)
    manifest_stats = _manifest_cv_stats(hybrid_dir / "hybrid_photo_manifest.csv")

    comparison: dict[str, Any] | None = None
    if args.baseline_transactions and args.baseline_transactions.is_file():
        baseline_df = _load_transactions(args.baseline_transactions.resolve())
        comparison = _compare_payees(df, baseline_df)
        print(f"[phase6] Baseline comparison: {comparison}")

    # Pivots (reuse production helper — read-only)
    pivot_cat = build_statement_pivot(df, group_by="Category", value_kind="sum")
    pivot_payee = build_statement_pivot(df, group_by="Payee", value_kind="sum")
    pivot_payee_count = build_statement_pivot(df, group_by="Payee", value_kind="count")

    _pivot_to_csv(pivot_cat, out_dir / "pivot_category_by_yearmonth.csv")
    _pivot_to_csv(pivot_payee, out_dir / "pivot_payee_by_yearmonth.csv")
    _pivot_to_csv(pivot_payee_count, out_dir / "pivot_payee_by_yearmonth_count.csv")

    # Top payees table (simple rollup for Laura)
    signed = _signed_series(df)
    work = df.copy()
    work["_signed"] = signed
    work["Payee"] = work["Payee"].astype(str).str.strip()
    work.loc[work["Payee"] == "", "Payee"] = "(no payee)"
    top = (
        work.groupby("Payee", dropna=False)["_signed"]
        .sum()
        .reset_index()
        .rename(columns={"_signed": "TotalSignedAmount"})
        .sort_values(by="TotalSignedAmount", key=lambda s: s.abs(), ascending=False)
    )
    top.to_csv(out_dir / "top_payees_by_total.csv", index=False, encoding="utf-8")

    credit_rows = _credit_deposit_rows(df)
    credit_rows.drop(columns=["_signed"], errors="ignore").to_csv(
        out_dir / "credit_register_rows.csv", index=False, encoding="utf-8"
    )

    _write_deposit_attribution(out_dir / "deposit_attribution.md", credit_rows, deposits)

    summary = {
        "spike": "Phase 6 P&L smoke",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hybrid_dir": str(hybrid_dir.relative_to(REPO_ROOT) if hybrid_dir.is_relative_to(REPO_ROOT) else hybrid_dir),
        "schema": "Option A (12-column)",
        "transaction_count": int(metrics.get("count", 0)),
        "deposits_total": metrics.get("deposits"),
        "withdrawals_total": metrics.get("withdrawals"),
        "needs_review": metrics.get("needs_review"),
        "deposit_slips": len(deposits),
        "payee_quality_checks": payee_stats,
        "manifest_cv_stats": manifest_stats,
        "baseline_comparison": comparison,
        "pivot_category_rows": int(len(pivot_cat)) if not pivot_cat.empty else 0,
        "pivot_payee_rows": int(len(pivot_payee)) if not pivot_payee.empty else 0,
    }
    (out_dir / "phase6_pl_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    _write_report(
        out_dir / "phase6_pl_smoke_report.md",
        summary,
        metrics,
        payee_stats,
        manifest_stats,
        comparison,
    )

    print()
    print("=" * 72)
    print("PHASE 6 P&L SMOKE - COMPLETE")
    print("=" * 72)
    print(f"Transactions      : {metrics.get('count')}")
    print(f"Deposits total    : ${metrics.get('deposits', 0):,.2f}")
    print(f"Withdrawals total : ${metrics.get('withdrawals', 0):,.2f}")
    print(f"Check rows        : {payee_stats.get('check_rows')}")
    print(f"Cleanish payees   : {payee_stats.get('payee_cleanish_heuristic')} "
          f"({payee_stats.get('payee_cleanish_pct')}%)")
    print(f"Pivot categories  : {summary['pivot_category_rows']} rows")
    print(f"Pivot payees      : {summary['pivot_payee_rows']} rows")
    print(f"Deposit slips     : {len(deposits)} (sidecar)")
    print(f"Output            : {out_dir}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
