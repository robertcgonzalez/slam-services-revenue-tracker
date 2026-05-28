"""Apply check-scoped payee rules to extracted OCR payee strings.

Rules are exact pattern → clean_payee mappings from human grades (see
Data/check_payee_rules.csv). Prefer regions.yaml ranking tweaks before adding
broad patterns — see regions.yaml design note and HCC_E1_FAILURE_MODE_TAXONOMY.md.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

CHECK_RULES_COLUMNS = (
    "pattern",
    "clean_payee",
    "client_override",
    "scope",
    "bank_id",
    "notes",
    "last_used",
)


def resolve_check_rules_path(path: Path | None = None) -> Path | None:
    if path is not None:
        return path if path.is_file() else None
    repo = Path(__file__).resolve().parents[2]
    candidate = repo / "Data" / "check_payee_rules.csv"
    return candidate if candidate.is_file() else None


def load_check_rules(path: Path | None = None) -> list[dict[str, str]]:
    target = resolve_check_rules_path(path)
    if target is None:
        return []
    rows: list[dict[str, str]] = []
    with open(target, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            pattern = (row.get("pattern") or "").strip()
            if not pattern or pattern.startswith("#"):
                continue
            scope = (row.get("scope") or "check").strip().lower()
            if scope not in {"check", "both"}:
                continue
            rows.append({k: (row.get(k) or "").strip() for k in CHECK_RULES_COLUMNS if k in row})
    return rows


def _rule_matches(
    rule: dict[str, str],
    payee: str,
    *,
    client_name: str | None,
    bank_id: str | None,
) -> bool:
    pattern = rule.get("pattern") or ""
    if not pattern:
        return False
    client_override = (rule.get("client_override") or "").strip().lower()
    if client_override:
        cn = (client_name or "").strip().lower()
        if not cn or client_override not in cn:
            return False
    rule_bank = (rule.get("bank_id") or "").strip().lower()
    if rule_bank and bank_id and rule_bank != bank_id.lower():
        return False
    target = payee or ""
    if pattern.startswith("re:"):
        try:
            return bool(re.search(pattern[3:], target, re.IGNORECASE))
        except re.error:
            return False
    return pattern.lower() in target.lower()


def apply_check_payee_rules(
    payee: str,
    *,
    rules_path: Path | None = None,
    client_name: str | None = None,
    bank_id: str | None = None,
    rules: list[dict[str, str]] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Return (possibly cleaned payee, matched rule metadata or None)."""
    if not payee:
        return payee, None
    rule_rows = rules if rules is not None else load_check_rules(rules_path)
    if not rule_rows:
        return payee, None

    matches: list[tuple[int, dict[str, str]]] = []
    for rule in rule_rows:
        if _rule_matches(rule, payee, client_name=client_name, bank_id=bank_id):
            matches.append((len(rule.get("pattern") or ""), rule))
    if not matches:
        return payee, None

    _, best = max(matches, key=lambda t: t[0])
    cleaned = (best.get("clean_payee") or payee).strip()
    return cleaned, best
