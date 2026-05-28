"""Boilerplate / bank-token denylist for photo-leg payee extraction."""

from __future__ import annotations

import re
from collections.abc import Iterable

# Shared across all banks — security lines, truncated anchors, generic check stock text.
GLOBAL_DENY_SUBSTRINGS: tuple[str, ...] = (
    "counterfeit",
    "inkcrypt",
    "goinkcrypt",
    "goink",
    "inkory",
    "inkcypt",
    "inkorypt",
    "security item",
    "security iten",
    "security inn",
    "security tref",
    "security features",
    "bio-marker",
    "uv tag",
    "powered by",
    "authorized signature",
    "authorized sign",
    "authorized sionature",
    "sionature",
    "signalill",
    "details on back",
    "not valid",
    "void",
    "ty to the",
    "order ofe",
    "asper of",
    "to vill",
    "to the order",
    "pay to the",
    "pay to",
    "order of",
    "payee",
    "visit goink",
    "visit golf",
    "golf-ng",
    "protected by",
    "pretected",
    "pretect",
    "protectis",
    "protector by",
    "protec ",
    "proled",
    "protest",
    "protestel",
    "proledad",
    "prolachd",
    "prouced by",
    "produced by",
    "pinkcryph",
    "pinkcry",
    "by @",
    "by &",
    "by -pink",
    "by -p",
    "deposit may not",
    "deposit ticket",
    "immediate withdrawal",
    "day to the",
    "building bridges",
    "this document is",
    "dollars",
    "and 00/100",
    "and no/",
    "xx/100",
    "birmingham, al",
    "p.o. box",
    "p.o. dox",
    "r.o. box",
    "ro. bok",
    "memo:",
    "kemo:",
    "mimo:",
    "cash >",
    "cash>",
    "gid:",
    "gid,",
    "birkiry",
    "ikdy",
    "quetent",
    "orstarcie",
    "ic he o",
    "⑈",
    "⑆",
)

GLOBAL_DENY_EXACT: frozenset[str] = frozenset(
    {
        "pay",
        "order",
        "the",
        "of",
        "to",
        "-",
        "$",
        "cash >",
        "cash>",
    }
)

# Regex patterns for OCR-noisy security / courtesy lines (case-insensitive).
_GLOBAL_DENY_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bcash\s*>\s*$", re.IGNORECASE),
    re.compile(r"protect\w*\s+by\b", re.IGNORECASE),
    re.compile(r"pretect\w*\s+by\b", re.IGNORECASE),
    re.compile(r"authorized\s+sign", re.IGNORECASE),
    re.compile(r"prouc\w+\s+by\b", re.IGNORECASE),
    re.compile(r"prol\w+\s+by\b", re.IGNORECASE),
    re.compile(r"^gid\s*[:,.]", re.IGNORECASE),
    re.compile(r"security\s+inn", re.IGNORECASE),
    re.compile(r"visit\s+golf", re.IGNORECASE),
)

BANK_DENY_SUBSTRINGS: dict[str, tuple[str, ...]] = {
    "regions": (
        "regions bank",
        "regions",
    ),
    "traditions": (
        "traditions bank",
        "traditions",
    ),
}

_BANK_TOKEN_RE = re.compile(
    r"\b(regions|traditions)\s+bank\b|\b(regions|traditions)\b",
    re.IGNORECASE,
)


def is_bank_token(text: str) -> bool:
    """True when text is primarily a bank name token (spike-local clean gate extension)."""
    t = (text or "").strip()
    if not t:
        return False
    if _BANK_TOKEN_RE.fullmatch(t):
        return True
    low = t.lower()
    return low in {"regions bank", "traditions bank", "regions", "traditions"}


def _matches_deny_regex(text: str) -> bool:
    for pat in _GLOBAL_DENY_RES:
        if pat.search(text):
            return True
    return False


def is_boilerplate(text: str, bank_id: str | None = None) -> bool:
    """Return True when ``text`` should never be selected as a payee candidate."""
    t = (text or "").strip()
    if not t:
        return True
    low = t.lower()
    if low in GLOBAL_DENY_EXACT:
        return True
    if _matches_deny_regex(t):
        return True
    if any(frag in low for frag in GLOBAL_DENY_SUBSTRINGS):
        return True
    if bank_id:
        for frag in BANK_DENY_SUBSTRINGS.get(bank_id, ()):
            if frag in low:
                return True
    return is_bank_token(t)


def merged_deny_substrings(bank_id: str | None = None) -> tuple[str, ...]:
    """All deny substrings for a bank profile (global + bank-specific)."""
    extra: list[str] = []
    if bank_id:
        extra.extend(BANK_DENY_SUBSTRINGS.get(bank_id, ()))
    return GLOBAL_DENY_SUBSTRINGS + tuple(extra)


def extra_clean_rejects(text: str, bank_tokens: Iterable[str] | None = None) -> bool:
    """Spike-local extensions on top of production ``_is_clean_payee``."""
    t = (text or "").strip()
    if not t:
        return False
    if is_bank_token(t):
        return True
    if _matches_deny_regex(t):
        return True
    # Vertical security-line garbage often has high symbol density.
    sym = sum(1 for c in t if c in "@!|:\\/-")
    if sym >= 2 and len(t) <= 40:
        return True
    if bank_tokens:
        low = t.lower()
        for tok in bank_tokens:
            if tok.lower() in low and len(low) <= len(tok) + 4:
                return True
    return False
