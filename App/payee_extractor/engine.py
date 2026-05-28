"""Shared payee extraction engine for the hybrid CV check photo leg."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import boilerplate as bp

try:
    from .. import local_enhanced_ocr as leo
except ImportError:  # App/ on sys.path (spike harnesses)
    import local_enhanced_ocr as leo  # type: ignore[no-redef]

_PROFILES_DIR = Path(__file__).resolve().parent / "profiles"

_HEADER_RE = re.compile(
    r"(pay\s*to\s*(the\s*)?order\s*of[: ]*|pay\s*to[: ]*|order\s*of[: ]*)",
    re.IGNORECASE,
)

_AMOUNT_LINE_BAD = (
    "dollar",
    "dollars",
    " cent",
    "cents",
    "/no",
    "/wo",
    "/100",
    "xx/100",
    "and no/",
)


@dataclass
class SpatialConfig:
    enabled: bool = False
    y_min: float = 0.13
    y_max: float = 0.38
    y_penalty_below: float = 0.12
    y_penalty_above: float = 0.55


@dataclass
class SignatureZoneScoring:
    boost_after: float = 0.0
    boost_immediate_next: float = 0.0


@dataclass
class BusinessBlockPenalty:
    substrings: tuple[str, ...] = ()
    penalty: float = 0.0
    singleton_variants: tuple[str, ...] = ()
    singleton_penalty: float = 0.0


@dataclass
class PayerHeaderPenalty:
    """Penalize account-holder / company header lines ranked over payee (FM-7)."""

    substrings: tuple[str, ...] = ()
    penalty: float = -18.0
    generic_suffix_enabled: bool = False
    generic_suffix_penalty: float = -12.0
    top_band_y_max: float = 0.22
    top_band_extra_penalty: float = -6.0


_BUSINESS_SUFFIX_RE = re.compile(
    r"\b(LLC|L\.L\.C\.|INC\.?|CORP\.?|CORPORATION|LTD\.?|LP|PLLC)\s*$",
    re.IGNORECASE,
)


@dataclass
class ScoringConfig:
    signature_zone: SignatureZoneScoring = field(default_factory=SignatureZoneScoring)
    business_block_penalty: BusinessBlockPenalty = field(default_factory=BusinessBlockPenalty)
    payer_header_penalty: PayerHeaderPenalty = field(default_factory=PayerHeaderPenalty)


@dataclass
class SignatureMarkers:
    primary_substrings: tuple[str, ...] = ("authorized sign",)
    paired_substrings: tuple[tuple[str, ...], ...] = (
        ("authorized", "sionature"),
        ("authorized", "signatur"),
    )


@dataclass
class ExtractorProfile:
    bank_id: str = "generic"
    legacy_mode: bool = False
    anchor_phrases: tuple[str, ...] = ("order of", "pay to")
    post_anchor_scan: int = 3
    whole_crop_scan: bool = True
    fallback_mode: str = "best_ranked"
    ranking_mode: str = "multi_candidate"
    spatial: SpatialConfig = field(default_factory=SpatialConfig)
    denylist_bank_id: str | None = None
    signature_markers: SignatureMarkers = field(default_factory=SignatureMarkers)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)

    @classmethod
    def from_yaml(cls, path: Path) -> ExtractorProfile:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        spatial_raw = data.get("spatial") or {}
        spatial = SpatialConfig(
            enabled=bool(spatial_raw.get("enabled", False)),
            y_min=float(spatial_raw.get("y_min", 0.13)),
            y_max=float(spatial_raw.get("y_max", 0.38)),
            y_penalty_below=float(spatial_raw.get("y_penalty_below", 0.12)),
            y_penalty_above=float(spatial_raw.get("y_penalty_above", 0.55)),
        )
        sig_raw = data.get("signature_markers") or {}
        primary = sig_raw.get("primary_substrings") or ["authorized sign"]
        paired_raw = sig_raw.get("paired_substrings") or [
            ["authorized", "sionature"],
            ["authorized", "signatur"],
        ]
        paired = tuple(tuple(p) for p in paired_raw)
        scoring_raw = data.get("scoring") or {}
        sig_zone_raw = scoring_raw.get("signature_zone") or {}
        biz_raw = scoring_raw.get("business_block_penalty") or {}
        payer_raw = scoring_raw.get("payer_header_penalty") or {}
        scoring = ScoringConfig(
            signature_zone=SignatureZoneScoring(
                boost_after=float(sig_zone_raw.get("boost_after", 0.0)),
                boost_immediate_next=float(sig_zone_raw.get("boost_immediate_next", 0.0)),
            ),
            business_block_penalty=BusinessBlockPenalty(
                substrings=tuple(biz_raw.get("substrings") or ()),
                penalty=float(biz_raw.get("penalty", 0.0)),
                singleton_variants=tuple(biz_raw.get("singleton_variants") or ()),
                singleton_penalty=float(biz_raw.get("singleton_penalty", 0.0)),
            ),
            payer_header_penalty=PayerHeaderPenalty(
                substrings=tuple(payer_raw.get("substrings") or ()),
                penalty=float(payer_raw.get("penalty", -18.0)),
                generic_suffix_enabled=bool(payer_raw.get("generic_suffix_enabled", False)),
                generic_suffix_penalty=float(payer_raw.get("generic_suffix_penalty", -12.0)),
                top_band_y_max=float(payer_raw.get("top_band_y_max", 0.22)),
                top_band_extra_penalty=float(payer_raw.get("top_band_extra_penalty", -6.0)),
            ),
        )
        return cls(
            bank_id=str(data.get("bank_id", "generic")),
            legacy_mode=bool(data.get("legacy_mode", False)),
            anchor_phrases=tuple(data.get("anchor_phrases") or ("order of", "pay to")),
            post_anchor_scan=int(data.get("post_anchor_scan", 3)),
            whole_crop_scan=bool(data.get("whole_crop_scan", True)),
            fallback_mode=str(data.get("fallback_mode", "best_ranked")),
            ranking_mode=str(data.get("ranking_mode", "multi_candidate")),
            spatial=spatial,
            denylist_bank_id=data.get("denylist_bank_id"),
            signature_markers=SignatureMarkers(
                primary_substrings=tuple(primary),
                paired_substrings=paired,
            ),
            scoring=scoring,
        )


@dataclass
class Candidate:
    text: str
    confidence: float
    line_index: int
    reason: str
    score: float = 0.0
    y_norm: float | None = None


_PERSON_NAME_RE = re.compile(r"^[A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,3}$")


@dataclass
class ScoreContext:
    profile: ExtractorProfile
    crop_height: float
    anchor_index: int | None = None
    authorized_sig_index: int | None = None


def load_profile(bank_id: str = "generic") -> ExtractorProfile:
    """Load a YAML profile by bank id; fall back to generic."""
    key = (bank_id or "generic").strip().lower()
    path = _PROFILES_DIR / f"{key}.yaml"
    if not path.is_file():
        path = _PROFILES_DIR / "generic.yaml"
    return ExtractorProfile.from_yaml(path)


def looks_like_amount_line(text: str) -> bool:
    if not text:
        return False
    low = text.lower()
    if any(tok in low for tok in _AMOUNT_LINE_BAD):
        return True
    digits = sum(c.isdigit() for c in text)
    letters = sum(c.isalpha() for c in text)
    return bool(letters and digits / letters > 0.30)


def is_clean_payee(text: str, profile: ExtractorProfile | None = None) -> bool:
    """Spike wrapper around production ``_is_clean_payee`` with optional bank-token rejection."""
    if leo is not None:
        try:
            if not bool(leo._is_clean_payee(text)):  # type: ignore[attr-defined]
                return False
        except Exception:
            pass
    else:
        t = (text or "").strip()
        if len(t) < 4 or "$" in t:
            return False
        bad = {"order of", "pay to", "the order", "payee", "void"}
        if t.lower() in bad:
            return False

    bank_id = profile.denylist_bank_id if profile else None
    if profile is not None:
        if bp.is_boilerplate(text, bank_id):
            return False
        if bp.extra_clean_rejects(text):
            return False
    return True


def _bbox_y_norm(bbox: list[float], crop_height: float) -> float | None:
    if not bbox or crop_height <= 0:
        return None
    ys = [bbox[i] for i in range(1, len(bbox), 2) if i < len(bbox)]
    if not ys:
        return None
    return min(ys) / crop_height


def _crop_height_from_lines(lines: list[dict[str, Any]]) -> float:
    max_y = 0.0
    for ln in lines:
        bbox = ln.get("bbox") or []
        ys = [bbox[i] for i in range(1, len(bbox), 2) if i < len(bbox)]
        if ys:
            max_y = max(max_y, max(ys))
    return max_y or 329.0


def _line_matches_anchor(text: str, phrases: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(p in low for p in phrases)


def _strip_anchor_remainder(text: str) -> str:
    return _HEADER_RE.sub("", text).strip(" -*:_$")


def _line_matches_signature_markers(
    text: str,
    markers: SignatureMarkers,
) -> bool:
    low = (text or "").lower()
    if not low:
        return False
    for primary in markers.primary_substrings:
        if primary.lower() in low:
            return True
    for pair in markers.paired_substrings:
        if len(pair) >= 2 and all(p.lower() in low for p in pair):
            return True
    return False


def _find_authorized_signature_index(
    lines: list[dict[str, Any]],
    profile: ExtractorProfile | None = None,
) -> int | None:
    markers = (profile or load_profile("generic")).signature_markers
    for i, ln in enumerate(lines):
        if _line_matches_signature_markers(ln.get("text") or "", markers):
            return i
    return None


def looks_like_payer_header(text: str) -> bool:
    """
    Heuristic: long business entity line typical of account-holder / payer header print (FM-7).

    Limitations (known as of 2026-05-27):
    - Thresholds (len>=18, upper_ratio>=0.55) are tuned on limited data (mainly QCR + HCC).
    - May produce false negatives on stylized or mixed-case company names.
    - Explicitly rejects anything that already matches _looks_like_person_name().
    - Intended as a fallback when no exact client substring match is configured.
    """
    t = (text or "").strip()
    if len(t) < 18:
        return False
    if _looks_like_person_name(t):
        return False
    if not _BUSINESS_SUFFIX_RE.search(t):
        return False
    letters = [c for c in t if c.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    return upper_ratio >= 0.55


def _looks_like_person_name(text: str) -> bool:
    t = (text or "").strip()
    if not t or len(t) > 48:
        return False
    low = t.lower()
    blocked = (
        "concrete",
        "regions",
        "bank",
        "llc",
        "inc",
        "box",
        "birmingham",
        "document",
        "inkcrypt",
        "visit ",
        "memo",
        "kemo",
    )
    if any(b in low for b in blocked):
        return False
    return bool(_PERSON_NAME_RE.match(t))


def _legacy_extract(lines: list[dict[str, Any]]) -> tuple[str, float, str]:
    """Bit-identical to pre-refactor ``extract_payee_from_cv_lines`` in the harness."""
    if not lines:
        return "", 0.0, "no_lines"

    for i, ln in enumerate(lines):
        text = (ln.get("text") or "").strip()
        if not text:
            continue
        low = text.lower()
        if "order of" in low or "pay to" in low:
            same_line = _strip_anchor_remainder(text)
            if same_line and is_clean_payee(same_line) and not looks_like_amount_line(same_line):
                return same_line, float(ln.get("confidence", 0.9) or 0.9), "same_line"
            for j in range(i + 1, min(i + 4, len(lines))):
                cand = (lines[j].get("text") or "").strip()
                if (
                    cand
                    and "$" not in cand
                    and "order" not in cand.lower()
                    and not looks_like_amount_line(cand)
                    and is_clean_payee(cand)
                ):
                    return (
                        cand,
                        float(lines[j].get("confidence", 0.9) or 0.9),
                        "next_line",
                    )
            return "", 0.0, "anchor_no_clean_candidate"

    for ln in lines:
        cand = (ln.get("text") or "").strip()
        if cand and is_clean_payee(cand) and "$" not in cand and not looks_like_amount_line(cand):
            return cand, float(ln.get("confidence", 0.85) or 0.85), "first_clean"

    return "", 0.0, "no_clean_candidate"


def _score_candidate(cand: Candidate, ctx: ScoreContext) -> float:
    text = cand.text
    score = 0.0
    score += min(len(text), 40) * 0.15
    if " " in text:
        score += 4.0
    score += cand.confidence * 2.0

    if ctx.anchor_index is not None:
        dist = abs(cand.line_index - ctx.anchor_index)
        score += max(0.0, 6.0 - dist * 1.5)

    # Penalize OCR garbage punctuation common on security lines.
    if re.search(r'[@!"\\|]', text):
        score -= 8.0
    if text.count(" ") >= 2 and len(text) >= 12:
        score += 2.0

    y = cand.y_norm
    if y is not None and ctx.profile.spatial.enabled:
        sp = ctx.profile.spatial
        if sp.y_min <= y <= sp.y_max:
            score += 8.0
        elif y < sp.y_penalty_below:
            score -= 12.0
        elif y > sp.y_penalty_above:
            score -= 6.0

    bank_id = ctx.profile.denylist_bank_id or ctx.profile.bank_id
    if bp.is_boilerplate(text, bank_id if bank_id != "generic" else None):
        score -= 100.0

    # Profile-driven business-block penalties and signature-zone boosts.
    # See regions.yaml design note: ranking first; exact-string check rules second.
    biz = ctx.profile.scoring.business_block_penalty
    low = text.lower()
    if biz.substrings and any(s in low for s in biz.substrings):
        score += biz.penalty
    if biz.singleton_variants and low in biz.singleton_variants:
        score += biz.singleton_penalty

    # FM-7: Penalize account-holder / payer header lines that rank above the real payee.
    # Applied *before* signature boost so strong header penalties can demote bad candidates early.
    # Signature boost (below) can still rescue legitimate person names after the signature marker.
    payer = ctx.profile.scoring.payer_header_penalty
    if payer.substrings and any(s in low for s in payer.substrings):
        score += payer.penalty
    elif payer.generic_suffix_enabled and looks_like_payer_header(text):
        score += payer.generic_suffix_penalty
        if y is not None and y <= payer.top_band_y_max:
            score += payer.top_band_extra_penalty

    sig_zone = ctx.profile.scoring.signature_zone
    sig_idx = ctx.authorized_sig_index
    if sig_idx is not None and _looks_like_person_name(text):
        if cand.line_index > sig_idx and sig_zone.boost_after:
            score += sig_zone.boost_after
        elif cand.line_index == sig_idx + 1 and sig_zone.boost_immediate_next:
            score += sig_zone.boost_immediate_next

    return score


def _collect_candidates(
    lines: list[dict[str, Any]],
    ctx: ScoreContext,
) -> list[Candidate]:
    profile = ctx.profile
    bank_id = profile.denylist_bank_id or profile.bank_id
    deny_bank = bank_id if bank_id != "generic" else None
    out: list[Candidate] = []

    anchor_idx: int | None = None
    for i, ln in enumerate(lines):
        text = (ln.get("text") or "").strip()
        if not text:
            continue
        if _line_matches_anchor(text, profile.anchor_phrases):
            anchor_idx = i
            same_line = _strip_anchor_remainder(text)
            if (
                same_line
                and is_clean_payee(same_line, profile)
                and not looks_like_amount_line(same_line)
                and not bp.is_boilerplate(same_line, deny_bank)
            ):
                out.append(
                    Candidate(
                        text=same_line,
                        confidence=float(ln.get("confidence", 0.9) or 0.9),
                        line_index=i,
                        reason="same_line",
                        y_norm=_bbox_y_norm(ln.get("bbox") or [], ctx.crop_height),
                    )
                )
            end = min(i + 1 + profile.post_anchor_scan, len(lines))
            for j in range(i + 1, end):
                cand_text = (lines[j].get("text") or "").strip()
                if not _accept_line(cand_text, profile, deny_bank):
                    continue
                out.append(
                    Candidate(
                        text=cand_text,
                        confidence=float(lines[j].get("confidence", 0.9) or 0.9),
                        line_index=j,
                        reason="next_line",
                        y_norm=_bbox_y_norm(lines[j].get("bbox") or [], ctx.crop_height),
                    )
                )
            break

    ctx.anchor_index = anchor_idx
    ctx.authorized_sig_index = _find_authorized_signature_index(lines, profile)

    if profile.whole_crop_scan:
        for i, ln in enumerate(lines):
            cand_text = (ln.get("text") or "").strip()
            if not _accept_line(cand_text, profile, deny_bank):
                continue
            if any(c.text == cand_text and c.line_index == i for c in out):
                continue
            out.append(
                Candidate(
                    text=cand_text,
                    confidence=float(ln.get("confidence", 0.85) or 0.85),
                    line_index=i,
                    reason="first_clean" if anchor_idx is None else "scan",
                    y_norm=_bbox_y_norm(ln.get("bbox") or [], ctx.crop_height),
                )
            )

    for cand in out:
        cand.score = _score_candidate(cand, ctx)
    return out


def _fallback_first_in_order(
    lines: list[dict[str, Any]],
    profile: ExtractorProfile,
    deny_bank: str | None,
) -> tuple[str, float, str]:
    """Legacy document-order first clean line (Traditions regression guard)."""
    for ln in lines:
        cand = (ln.get("text") or "").strip()
        if (
            cand
            and is_clean_payee(cand, profile)
            and "$" not in cand
            and not looks_like_amount_line(cand)
            and not bp.is_boilerplate(cand, deny_bank)
        ):
            return cand, float(ln.get("confidence", 0.85) or 0.85), "first_clean"
    return "", 0.0, "no_clean_candidate"


def _accept_line(text: str, profile: ExtractorProfile, deny_bank: str | None) -> bool:
    if not text or "$" in text:
        return False
    low = text.lower()
    if "order" in low and _line_matches_anchor(text, profile.anchor_phrases):
        return False
    if looks_like_amount_line(text):
        return False
    if bp.is_boilerplate(text, deny_bank):
        return False
    return is_clean_payee(text, profile)


def rank_candidates(
    lines: list[dict[str, Any]],
    profile: ExtractorProfile | None = None,
) -> Candidate | None:
    profile = profile or load_profile("generic")
    if not lines:
        return None
    crop_h = _crop_height_from_lines(lines)
    ctx = ScoreContext(
        profile=profile,
        crop_height=crop_h,
        authorized_sig_index=_find_authorized_signature_index(lines, profile),
    )
    candidates = _collect_candidates(lines, ctx)
    if not candidates:
        return None
    candidates.sort(key=lambda c: (-c.score, c.line_index))
    return candidates[0]


def extract_payee_from_cv_lines(
    lines: list[dict[str, Any]],
    profile: ExtractorProfile | str | None = None,
) -> tuple[str, float, str]:
    """Pick the best payee candidate from CV Read lines.

    Returns (payee, confidence, reason).
    """
    if isinstance(profile, str):
        prof = load_profile(profile)
    elif profile is None:
        prof = load_profile("generic")
    else:
        prof = profile

    if prof.legacy_mode or prof.ranking_mode == "legacy":
        return _legacy_extract(lines)

    if not lines:
        return "", 0.0, "no_lines"

    deny_bank = prof.denylist_bank_id or prof.bank_id
    deny_bank = deny_bank if deny_bank != "generic" else None

    best = rank_candidates(lines, prof)
    if best is None:
        if prof.fallback_mode == "first_in_order":
            return _fallback_first_in_order(lines, prof, deny_bank)
        if any(_line_matches_anchor((ln.get("text") or ""), prof.anchor_phrases) for ln in lines):
            return "", 0.0, "anchor_no_clean_candidate"
        return "", 0.0, "no_clean_candidate"

    return best.text, best.confidence, best.reason
