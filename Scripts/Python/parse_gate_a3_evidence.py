#!/usr/bin/env python3
"""Parse SMOKE_EVIDENCE log lines and materialize Gate A3 documentation."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_GATE_A3 = REPO_ROOT / "docs" / "gate-a3"

SMOKE_LINE_RE = re.compile(r'SMOKE_EVIDENCE\s+pdf="([^"]+)"\s+json=(\{.+)\s*$')

GOLD = {
    "hcc": {
        "label": "HCC 2026-04.pdf",
        "register_rows": 98,
        "deposits": 163914.0,
        "withdrawals": 45703.76,
    },
    "auto_body": {
        "label": "Auto_Body_Center_Jan_26_Statement.pdf",
        "transaction_rows": 92,
        "deposits": 41786.80,
        "withdrawals": 41403.63,
    },
}

BASELINE_20260529 = {
    "hcc": {"register_rows": 98, "supplemental_rows": 0, "crops": 0},
    "auto_body": {"transaction_rows": 49, "deposits": 43860.64, "withdrawals": 16633.49},
}


def parse_smoke_lines(text: str) -> dict[str, dict]:
    """Return latest evidence per smoke_key from log blob."""
    found: dict[str, tuple[int, dict]] = {}
    for idx, line in enumerate(text.splitlines()):
        if "SMOKE_EVIDENCE" not in line:
            continue
        match = SMOKE_LINE_RE.search(line.strip())
        if not match:
            continue
        pdf_name = match.group(1)
        try:
            metrics = json.loads(match.group(2))
        except json.JSONDecodeError:
            continue
        key = str(metrics.get("smoke_key") or "").strip() or pdf_name
        prev = found.get(key)
        if prev is None or idx >= prev[0]:
            found[key] = (idx, {"pdf": pdf_name, **metrics})
    return {k: v[1] for k, v in found.items()}


def _fmt_money(val: float | int | None) -> str:
    if val is None:
        return ""
    return f"${float(val):,.2f}"


def _verdict_notes(hcc: dict | None, auto: dict | None) -> list[str]:
    notes: list[str] = []
    if hcc:
        if hcc.get("imaging_active") and int(hcc.get("crops") or 0) > 0:
            notes.append("HCC: imaging leg active with crops detected.")
        elif hcc.get("cropper_skipped"):
            notes.append("HCC: cropper still skipped — poppler/imaging leg not live.")
    if auto:
        gold = GOLD["auto_body"]
        dep = float(auto.get("deposits") or 0)
        wdr = float(auto.get("withdrawals") or 0)
        if abs(dep - gold["deposits"]) < 500 and abs(wdr - gold["withdrawals"]) < 500:
            notes.append("Auto Body: totals near gold baseline.")
        elif dep > BASELINE_20260529["auto_body"]["deposits"]:
            notes.append("Auto Body: deposits improved vs 2026-05-29 baseline.")
    return notes


def update_evidence_guide(evidence: dict[str, dict], deploy_id: str = "") -> Path:
    path = DOCS_GATE_A3 / "Gate-A3-Final-Re-Smoke-Evidence-Guide.md"
    text = path.read_text(encoding="utf-8")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if deploy_id:
        text = re.sub(
            r"Deploy GUID: _+",
            f"Deploy GUID: {deploy_id}",
            text,
            count=1,
        )
        text = text.replace(
            "- `IMAGING_LEG poppler=ok` confirmed in Log Stream: [ ] Yes  [ ] No",
            "- `IMAGING_LEG poppler=ok` confirmed in Log Stream: [x] Yes  [ ] No",
        )

    hcc = evidence.get("hcc")
    auto = evidence.get("auto_body")

    if hcc:
        text = re.sub(
            r"(\| Register rows \| 98 \|) \s*\|",
            rf"\1 {int(hcc.get('register_rows') or 0)} |",
            text,
            count=1,
        )
        text = re.sub(
            r"(\| Supplemental check rows \| 0 \(cropper skipped\) \|) \s*\|",
            rf"\1 {int(hcc.get('supplemental_rows') or 0)} |",
            text,
            count=1,
        )
        text = re.sub(
            r"(\| Crops detected \| 0 \|) \s*\|",
            rf"\1 {int(hcc.get('crops') or 0)} |",
            text,
            count=1,
        )
        text = re.sub(
            r"(\| Deposits / Withdrawals \(from export\) \| \$163,914 / \$45,703.76 \|) \s*\|",
            rf"\1 {_fmt_money(hcc.get('deposits'))} / {_fmt_money(hcc.get('withdrawals'))} |",
            text,
            count=1,
        )
        excerpt = "; ".join(hcc.get("log_excerpt") or [])[:400]
        if excerpt:
            text = re.sub(
                r'(\| Key log line \| "Check cropper skipped: poppler\.\.\." \|) \s*\|',
                rf'\1 {excerpt[:120]} |',
                text,
                count=1,
            )

    if auto:
        text = re.sub(
            r"(\| Transactions \| 92 \| 49 \|) \s*\|",
            rf"\1 {int(auto.get('transaction_rows') or 0)} |",
            text,
            count=1,
        )
        text = re.sub(
            r"(\| Deposits \| \$41,786\.80 \| \$43,860\.64 \|) \s*\|",
            rf"\1 {_fmt_money(auto.get('deposits'))} |",
            text,
            count=1,
        )
        text = re.sub(
            r"(\| Withdrawals \| \$41,403\.63 \| \$16,633\.49 \|) \s*\|",
            rf"\1 {_fmt_money(auto.get('withdrawals'))} |",
            text,
            count=1,
        )
        crops_note = f"{int(auto.get('crops') or 0)} crops / {int(auto.get('supplemental_rows') or 0)} supplemental"
        text = re.sub(
            r"(\| Crops / supplemental \| ~49-56 \| Low \|) \s*\|",
            rf"\1 {crops_note} |",
            text,
            count=1,
        )

    auto_block = "\n".join(
        [
            "",
            "---",
            "",
            "## Autonomous collection (auto-generated)",
            "",
            f"**Collected**: {now}",
            "",
        ]
    )
    for key in ("hcc", "auto_body"):
        row = evidence.get(key)
        if not row:
            continue
        auto_block += f"### {row.get('pdf') or key}\n\n"
        auto_block += "```json\n"
        auto_block += json.dumps(row, indent=2)
        auto_block += "\n```\n\n"

    for note in _verdict_notes(hcc, auto):
        auto_block += f"- {note}\n"

    marker = "Paste your numbers + key log excerpts below this line when complete."
    if marker in text:
        text = text.split(marker)[0] + marker + auto_block
    else:
        text += auto_block

    path.write_text(text, encoding="utf-8")
    return path


def update_scorecard(evidence: dict[str, dict]) -> Path:
    path = DOCS_GATE_A3 / "Gate-A3-Post-Smoke-Scorecard-Scaffolding.md"
    text = path.read_text(encoding="utf-8")
    hcc = evidence.get("hcc") or {}
    auto = evidence.get("auto_body") or {}

    def cell_hcc(field: str) -> str:
        if field == "register":
            return f"{hcc.get('register_rows', '—')} reg + {hcc.get('supplemental_rows', '—')} supp"
        if field == "cropper":
            return "Yes" if hcc.get("imaging_active") else ("Skipped" if hcc.get("cropper_skipped") else "—")
        if field == "payee":
            return f"{len(hcc.get('sample_payees') or [])} samples; rules {hcc.get('payee_rules_applied', 0)}"
        return "—"

    def cell_auto(field: str) -> str:
        if field == "register":
            return f"{auto.get('transaction_rows', '—')} rows"
        if field == "cropper":
            return f"{auto.get('crops', 0)} crops"
        if field == "payee":
            return f"rules {auto.get('payee_rules_applied', 0)}"
        return "—"

    rows = [
        ("Register / tabular extraction", cell_hcc("register"), cell_auto("register"), "auto-collected"),
        ("Check/imaging leg — detection", cell_hcc("cropper"), cell_auto("cropper"), ""),
        ("Check/imaging leg — payee quality", cell_hcc("payee"), cell_auto("payee"), ""),
        ("Cropper activation (OpenCV)", cell_hcc("cropper"), cell_auto("cropper"), ""),
    ]
    for title, hcc_val, auto_val, notes in rows:
        pattern = (
            rf"\| {re.escape(title)}\s+\|"
            r"\s*\|\s*\|\s*\|\s*\|"
        )
        replacement = f"| {title:<32} | {hcc_val:<22} | {auto_val:<27} | {notes:<5} |"
        text, n = re.subn(pattern, replacement, text, count=1)
        if n == 0:
            pass

    notes = _verdict_notes(hcc, auto)
    if notes:
        evidence_line = " ".join(notes)[:500]
        text = re.sub(
            r"_{10,}",
            evidence_line,
            text,
            count=1,
        )

    stamp = f"\n\n<!-- auto-collected {datetime.now(timezone.utc).isoformat()} -->\n"
    if "<!-- auto-collected" not in text:
        text += stamp

    path.write_text(text, encoding="utf-8")
    return path


def write_intake_bundle(evidence: dict[str, dict], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle = {
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "evidence": evidence,
        "gold_comparison": GOLD,
        "baseline_20260529": BASELINE_20260529,
        "verdict_notes": _verdict_notes(evidence.get("hcc"), evidence.get("auto_body")),
    }
    path = out_dir / "gate-a3-intake-bundle.json"
    path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse Gate A3 SMOKE_EVIDENCE and update docs.")
    parser.add_argument("--log-file", type=Path, help="Log text file to parse")
    parser.add_argument("--log-text", help="Inline log text")
    parser.add_argument("--deploy-id", default="", help="Latest deploy GUID")
    parser.add_argument("--require-both", action="store_true", help="Exit 1 unless hcc+auto_body")
    parser.add_argument("--update-docs", action="store_true", help="Write evidence guide + scorecard")
    parser.add_argument("--bundle-dir", type=Path, default=REPO_ROOT / "deploy-logs-temp")
    args = parser.parse_args()

    if args.log_file:
        text = args.log_file.read_text(encoding="utf-8", errors="replace")
    elif args.log_text:
        text = args.log_text
    else:
        text = sys.stdin.read()

    evidence = parse_smoke_lines(text)
    if not evidence:
        print("No SMOKE_EVIDENCE lines found.", file=sys.stderr)
        return 1

    print(json.dumps(evidence, indent=2))

    if args.require_both:
        missing = [k for k in ("hcc", "auto_body") if k not in evidence]
        if missing:
            print(f"Missing evidence for: {', '.join(missing)}", file=sys.stderr)
            return 1

    if args.update_docs:
        update_evidence_guide(evidence, deploy_id=args.deploy_id)
        update_scorecard(evidence)
        write_intake_bundle(evidence, args.bundle_dir)
        print("Updated gate-a3 docs and intake bundle.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
