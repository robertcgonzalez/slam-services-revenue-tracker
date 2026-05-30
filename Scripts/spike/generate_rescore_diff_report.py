#!/usr/bin/env python3
"""Compact before/after diff for two phase1 harness rescored directories (spike-only)."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def load_payees(path: Path) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for row in csv.DictReader(open(path, encoding="utf-8")):
        cid = row["crop_id"]
        out[cid] = {
            "payee": row.get("cv_read_payee_candidate", ""),
            "reason": row.get("cv_read_payee_reason", ""),
            "clean": row.get("cv_read_is_clean", ""),
        }
    return out


def diff_dirs(before: Path, after: Path) -> list[tuple[str, str, str, str, str]]:
    b = load_payees(before / "side_by_side_harness.csv")
    a = load_payees(after / "side_by_side_harness.csv")
    changes = []
    for cid in sorted(set(b) | set(a)):
        pb, rb = b.get(cid, {}).get("payee", ""), b.get(cid, {}).get("reason", "")
        pa, ra = a.get(cid, {}).get("payee", ""), a.get(cid, {}).get("reason", "")
        if pb != pa or rb != ra:
            changes.append((cid, pb, pa, rb, ra))
    return changes


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("before_dir", type=Path, help="Earlier rescored artifact dir")
    p.add_argument("after_dir", type=Path, help="Later rescored artifact dir")
    p.add_argument("-o", "--out", type=Path, help="Optional markdown output path")
    args = p.parse_args()
    changes = diff_dirs(args.before_dir, args.after_dir)
    lines = [
        f"# Rescore diff: `{args.before_dir.name}` → `{args.after_dir.name}`",
        "",
        f"**Changed rows**: {len(changes)}",
        "",
        "| crop_id | before_payee | after_payee | before_reason | after_reason |",
        "|---------|--------------|-------------|---------------|--------------|",
    ]
    for cid, pb, pa, rb, ra in changes:
        lines.append(f"| {cid} | {pb} | {pa} | {rb} | {ra} |")
    text = "\n".join(lines) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
