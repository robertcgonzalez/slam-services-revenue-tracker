"""Minimal bank detection for hybrid CV check leg (register text + client map)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

CLIENT_BANK_MAP: dict[str, str] = {
    "hernandez custom concrete": "regions",
    "hernandez custom concrete llc": "regions",
    "auto body center": "traditions",
}

REGISTER_BANK_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"regions\s+bank", "regions"),
    (r"traditions\s+bank", "traditions"),
    (r"\bregions\b.*\brouting\b", "regions"),
    (r"\btraditions\b.*\brouting\b", "traditions"),
)

CONFIDENCE_THRESHOLD = 0.55


@dataclass
class BankDetectResult:
    bank_id: str
    confidence: float
    signals: list[str] = field(default_factory=list)


def _normalize_client(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def detect_from_client_name(client_name: str | None) -> BankDetectResult | None:
    key = _normalize_client(client_name or "")
    if not key:
        return None
    for prefix, bank_id in CLIENT_BANK_MAP.items():
        if key == prefix or key.startswith(prefix):
            return BankDetectResult(
                bank_id=bank_id,
                confidence=0.95,
                signals=[f"client_map:{prefix}"],
            )
    return None


def detect_from_register_text(text: str) -> BankDetectResult | None:
    if not text:
        return None
    low = text.lower()
    hits: list[tuple[str, str]] = []
    for pattern, bank_id in REGISTER_BANK_PATTERNS:
        if re.search(pattern, low):
            hits.append((pattern, bank_id))
    if not hits:
        return None
    # Prefer the first strong match; multiple hits boost confidence slightly.
    bank_id = hits[0][1]
    conf = min(0.98, 0.75 + 0.1 * len(hits))
    return BankDetectResult(
        bank_id=bank_id,
        confidence=conf,
        signals=[f"register:{p}" for p, _ in hits],
    )


def detect_bank(
    *,
    client_name: str | None = None,
    register_page1_text: str | None = None,
    baseline_summary_path: Path | None = None,
) -> BankDetectResult:
    """Detect bank once per statement; fall back to generic below threshold."""
    signals: list[str] = []
    scores: dict[str, float] = {}

    client_hit = detect_from_client_name(client_name)
    if client_hit:
        scores[client_hit.bank_id] = client_hit.confidence
        signals.extend(client_hit.signals)

    reg_text = register_page1_text or ""
    if not reg_text and baseline_summary_path and baseline_summary_path.is_file():
        try:
            import json

            summary = json.loads(baseline_summary_path.read_text(encoding="utf-8"))
            reg_text = str(summary.get("register_page1_text") or summary.get("page1_text") or "")
        except Exception:
            pass

    reg_hit = detect_from_register_text(reg_text)
    if reg_hit:
        prev = scores.get(reg_hit.bank_id, 0.0)
        scores[reg_hit.bank_id] = max(prev, reg_hit.confidence)
        signals.extend(reg_hit.signals)

    if not scores:
        return BankDetectResult(bank_id="generic", confidence=0.0, signals=["fallback:generic"])

    bank_id = max(scores, key=lambda k: scores[k])
    conf = scores[bank_id]
    if conf < CONFIDENCE_THRESHOLD:
        return BankDetectResult(
            bank_id="generic",
            confidence=conf,
            signals=signals + ["below_threshold:generic"],
        )
    return BankDetectResult(bank_id=bank_id, confidence=conf, signals=signals)


def resolve_bank_arg(
    bank_arg: str,
    *,
    client_name: str | None = None,
    register_page1_text: str | None = None,
    baseline_summary_path: Path | None = None,
) -> str:
    """Resolve CLI ``--bank`` value to a profile bank id."""
    arg = (bank_arg or "generic").strip().lower()
    if arg in {"", "generic"}:
        return "generic"
    if arg != "auto":
        return arg
    return detect_bank(
        client_name=client_name,
        register_page1_text=register_page1_text,
        baseline_summary_path=baseline_summary_path,
    ).bank_id
