#!/usr/bin/env python3
"""Unit smoke for App/hybrid_cv_check_leg (G1 Sprint 3.2)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "App"))

from hybrid_cv_check_leg import (  # noqa: E402
    CheckLegMode,
    classify_from_text,
    cv_lines_to_easyocr_detections,
    is_hybrid_cv_enabled,
    load_cv_cache,
    resolve_check_leg_mode,
    run_hybrid_check_leg,
    save_cv_cache,
)


def test_resolve_strict_by_default() -> None:
    assert resolve_check_leg_mode(None) is CheckLegMode.STRICT
    assert resolve_check_leg_mode("hybrid_cv") is CheckLegMode.STRICT or is_hybrid_cv_enabled()


def test_imaging_page_filter() -> None:
    crops = [
        {"check_id": "P04C00", "page": 4, "image_b64": "e30="},
        {"check_id": "P05C00", "page": 5, "image_b64": "e30="},
        {"check_id": "P10C00", "page": 10, "image_b64": "e30="},
    ]
    dets = {"P04C00": [("x",)], "P05C00": [("y",)], "P10C00": [("z",)]}
    _, out_dets, logs = run_hybrid_check_leg(
        crops,
        dets,
        first_page=5,
        last_page=9,
        cache_dir=None,
    )
    assert out_dets["P04C00"] == [("x",)]
    assert any("0/3" in line or "imaging" in line.lower() for line in logs)


def test_cv_cache_round_trip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp)
        payload = {
            "status": "succeeded",
            "raw_text": "pay to the order of\nACME LLC",
            "lines": [{"text": "ACME LLC", "confidence": 0.9, "bbox": [0, 0, 10, 0, 10, 5, 0, 5]}],
        }
        save_cv_cache(cache, "P05C00", payload)
        loaded = load_cv_cache(cache, "P05C00")
        assert loaded is not None
        assert loaded["lines"] == payload["lines"]
        dets = cv_lines_to_easyocr_detections(loaded["lines"])
        assert len(dets) == 1


def test_cv_cache_pipeline_alias() -> None:
    """Pipeline P04C00 on physical page 5 maps to spike P05_K00_*.json cache."""
    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp)
        payload = {
            "status": "succeeded",
            "raw_text": "pay to the order of\nHallmark Hyundai",
            "lines": [{"text": "Hallmark Hyundai", "confidence": 0.9, "bbox": []}],
        }
        save_cv_cache(cache, "P05_K00_w100_h200_a1.0", payload)
        loaded = load_cv_cache(cache, "P04C00", page=5)
        assert loaded is not None
        assert "Hallmark" in (loaded.get("raw_text") or "")


def test_classify_check() -> None:
    cls, conf, _ = classify_from_text("pay to the order of\nmemo\nvoid after 90 days")
    assert cls == "check"
    assert conf > 0.5


def main() -> int:
    tests = [
        test_resolve_strict_by_default,
        test_imaging_page_filter,
        test_cv_cache_round_trip,
        test_cv_cache_pipeline_alias,
        test_classify_check,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
