"""Check + deposit slip cropper — OpenCV geometry only (no EasyOCR).

Designed to capture both personal/business checks and deposit slips from statement
imaging pages for downstream Azure analysis and income stream metrics.

Uses DPI-scaled size/aspect bands + two-stage dedup. Aspect range widened to support
deposit slips (typically squarer than checks). Text extraction happens via Azure
Content Understanding / prebuilt-check.us (or equivalent analyzer), never EasyOCR on crops.

Dependencies: ``opencv-python-headless``, ``pdf2image`` (+ Poppler), ``pillow``, ``numpy``.
"""

from __future__ import annotations

import base64
import hashlib
import io
import os
from dataclasses import dataclass
from typing import Any

from app_logging import format_pipeline_log as _log

_DEFAULT_DPI = int(os.environ.get("SLAM_CROP_DPI", "400"))
_DPI_SCALE = _DEFAULT_DPI / 300.0   # Base tuning was done around 300 DPI

_MIN_WIDTH = int(os.environ.get("SLAM_CROP_MIN_WIDTH", str(int(120 * _DPI_SCALE))))
_MAX_WIDTH = int(os.environ.get("SLAM_CROP_MAX_WIDTH", str(int(1700 * _DPI_SCALE))))
_MIN_HEIGHT = int(os.environ.get("SLAM_CROP_MIN_HEIGHT", str(int(500 * _DPI_SCALE))))
_MAX_HEIGHT = int(os.environ.get("SLAM_CROP_MAX_HEIGHT", str(int(1100 * _DPI_SCALE))))
_MIN_ASPECT = float(os.environ.get("SLAM_CROP_MIN_ASPECT", "1.4"))
_MAX_ASPECT = float(os.environ.get("SLAM_CROP_MAX_ASPECT", "3.2"))
_CONTRAST = float(os.environ.get("SLAM_CROP_CONTRAST", "3.5"))
_MAX_CROPS = int(os.environ.get("SLAM_LOCAL_OCR_MAX_CHECKS", "70"))
# Drop flat blank rectangles (borders / gutters) without OCR. Scale roughly with area.
_MIN_VARIANCE = float(os.environ.get("SLAM_CROP_MIN_VARIANCE", str(120.0 * (_DPI_SCALE ** 2))))

_HASH_SIZE = 12
_MIN_CENTER_DIST = int(os.environ.get("SLAM_CROP_MIN_CENTER_DIST", str(round(45 * _DPI_SCALE))))


@dataclass
class _Candidate:
    page: int
    x: int
    y: int
    w: int
    h: int
    aspect: float
    area: int
    var_brightness: float
    hash: str = ""


def _enhanced_hash(crop_rgb: Any, size: int = _HASH_SIZE) -> str:
    from PIL import Image, ImageEnhance  # noqa: PLC0415

    gray = Image.fromarray(crop_rgb).convert("L")
    enh = ImageEnhance.Contrast(gray).enhance(3.0)
    small = enh.resize((size, size))
    arr = __import__("numpy").array(small)
    pixels = arr.flatten().tolist()
    avg = float(__import__("numpy").mean(pixels)) if pixels else 0.0
    bits = "".join("1" if p > avg else "0" for p in pixels)
    return hashlib.md5(bits.encode()).hexdigest()


def _two_stage_dedup(candidates: list[_Candidate], page_img: Any) -> list[_Candidate]:
    if not candidates:
        return []

    import numpy as np  # noqa: PLC0415

    img = np.array(page_img)
    for c in candidates:
        crop = img[c.y : c.y + c.h, c.x : c.x + c.w]
        c.hash = _enhanced_hash(crop)

    seen: set[str] = set()
    hash_survivors: list[_Candidate] = []
    for c in candidates:
        if c.hash in seen:
            continue
        seen.add(c.hash)
        hash_survivors.append(c)

    hash_survivors.sort(key=lambda c: c.var_brightness * c.area, reverse=True)
    final: list[_Candidate] = []
    kept_centers: list[tuple[int, int]] = []

    for c in hash_survivors:
        cx, cy = c.x + c.w // 2, c.y + c.h // 2
        too_close = False
        for kx, ky in kept_centers:
            if abs(cx - kx) + abs(cy - ky) < _MIN_CENTER_DIST:
                too_close = True
                break
        if too_close:
            continue
        kept_centers.append((cx, cy))
        final.append(c)

    return final


def _imaging_page_bounds() -> tuple[int, int | None]:
    try:
        from hybrid_cv_check_leg import imaging_page_range

        first, last = imaging_page_range()
    except Exception:
        first, last = 5, 9
    if not isinstance(last, int):
        last = None
    return int(first), last


def crop_pdf_checks(pdf_bytes: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Crop check and deposit-slip photos from statement imaging pages.

    Returns ``(crops, logs)`` where each crop dict has ``check_id``, ``page``,
    ``image_b64``, dimensions, and ``notes``.
    """
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    from pdf2image import convert_from_bytes  # noqa: PLC0415
    from PIL import Image, ImageEnhance  # noqa: PLC0415

    logs: list[str] = []
    if not pdf_bytes:
        logs.append(_log("warn", "Empty PDF — cropper skipped."))
        return [], logs

    imaging_first, imaging_last = _imaging_page_bounds()
    span = f"{imaging_first}-{imaging_last}" if imaging_last else f"{imaging_first}+"
    logs.append(
        _log(
            "info",
            f"Check cropper (geometry, DPI={_DEFAULT_DPI}, pages {span}, max={_MAX_CROPS})…",
        )
    )
    logs.append(
        _log(
            "info",
            f"Effective thresholds (DPI-scaled): min_size=({_MIN_WIDTH}x{_MIN_HEIGHT}), "
            f"variance>={_MIN_VARIANCE:.0f}, aspect {_MIN_ASPECT:.1f}-{_MAX_ASPECT:.1f}",
        )
    )

    pages = convert_from_bytes(pdf_bytes, dpi=_DEFAULT_DPI)
    if not pages:
        logs.append(_log("warn", "pdf2image returned 0 pages."))
        return [], logs

    all_crops: list[dict[str, Any]] = []
    check_counter = 0
    rejections: dict[str, int] = {"size": 0, "aspect": 0, "variance": 0, "rough_dup": 0}

    for page_idx, page in enumerate(pages):
        if len(all_crops) >= _MAX_CROPS:
            logs.append(_log("warn", f"Hit SLAM_LOCAL_OCR_MAX_CHECKS={_MAX_CROPS}; stopping."))
            break

        page_num = page_idx + 1
        if page_num < imaging_first:
            continue
        if imaging_last is not None and page_num > imaging_last:
            continue

        img = np.array(page)
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        thresholds = [
            cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 9, 3
            ),
            cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 11, 2
            ),
            cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY_INV)[1],
        ]

        geometry: list[_Candidate] = []
        rough_seen: set[str] = set()

        for thresh in thresholds:
            kernel = np.ones((3, 3), np.uint8)
            dilated = cv2.dilate(thresh, kernel, iterations=2)
            contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                if not (_MIN_WIDTH < w < _MAX_WIDTH and _MIN_HEIGHT < h < _MAX_HEIGHT):
                    rejections["size"] += 1
                    continue
                aspect = w / h if h else 0.0
                if not (_MIN_ASPECT < aspect < _MAX_ASPECT):
                    rejections["aspect"] += 1
                    continue
                patch = gray[y : y + h, x : x + w]
                var_b = float(np.var(patch)) if patch.size else 0.0
                if var_b < _MIN_VARIANCE:
                    rejections["variance"] += 1
                    continue
                rough = hashlib.md5(patch.tobytes()[:4096]).hexdigest()
                if rough in rough_seen:
                    rejections["rough_dup"] += 1
                    continue
                rough_seen.add(rough)
                geometry.append(
                    _Candidate(
                        page=page_num,
                        x=x,
                        y=y,
                        w=w,
                        h=h,
                        aspect=round(aspect, 3),
                        area=w * h,
                        var_brightness=var_b,
                    )
                )

        survivors = _two_stage_dedup(geometry, page)
        page_kept = 0

        for cand in survivors:
            if len(all_crops) >= _MAX_CROPS:
                break

            crop_rgb = img[cand.y : cand.y + cand.h, cand.x : cand.x + cand.w]
            enhanced_pil = (
                ImageEnhance.Contrast(Image.fromarray(crop_rgb).convert("L"))
                .enhance(_CONTRAST)
                .convert("RGB")
            )

            buf = io.BytesIO()
            enhanced_pil.save(buf, format="PNG", optimize=True)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            # Use the real 1-based PDF page number in the ID for clarity (e.g. P05C00 instead of P04C00)
            check_id = f"P{page_num:02d}C{check_counter:02d}"
            # Basic heuristic to help future income stream analysis:
            # Deposit slips tend to be relatively squarer (lower aspect) than personal checks.
            is_likely_deposit = cand.aspect < 2.1

            all_crops.append(
                {
                    "check_id": check_id,
                    "page": page_num,
                    "width": cand.w,
                    "height": cand.h,
                    "aspect_ratio": cand.aspect,
                    "image_b64": b64,
                    "notes": "geometry+v5_dedup",
                    "likely_deposit_slip": is_likely_deposit,
                    "likely_check": not is_likely_deposit,
                }
            )
            check_counter += 1
            page_kept += 1

        if page_kept:
            logs.append(_log("info", f"Check cropper page {page_num}: {page_kept} crop(s)."))

    total_rej = sum(rejections.values())
    if total_rej:
        logs.append(
            _log(
                "info",
                f"[DIAG] Cropper rejections this run: {total_rej} "
                f"(size={rejections['size']}, aspect={rejections['aspect']}, "
                f"variance={rejections['variance']}, rough_dup={rejections['rough_dup']}). "
                f"Effective thresholds at {_DEFAULT_DPI} DPI shown above. "
                "Set SLAM_CROP_MIN_HEIGHT / SLAM_CROP_MIN_VARIANCE etc. to tune.",
            )
        )
    logs.append(_log("info", f"Check cropper extracted {len(all_crops)} unique crop(s)."))
    return all_crops, logs
