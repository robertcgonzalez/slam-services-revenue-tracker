"""Check + deposit slip cropper — OpenCV geometry only (no EasyOCR).

Uses v5 size/aspect bands (400 DPI, height 500–1100) and the two-stage grid dedup
validated in ``Scripts/spike/diagnose_check_deposit_cropper.py`` (~49 checks + 7
deposit slips on the Traditions hard PDF). Text on crops comes from Azure
``prebuilt-check.us``, not local OCR.

Dependencies: ``opencv-python-headless``, ``pdf2image`` (+ Poppler), ``pillow``, ``numpy``.
"""

from __future__ import annotations

import base64
import hashlib
import io
import os
from dataclasses import dataclass
from typing import Any

_DEFAULT_DPI = int(os.environ.get("SLAM_CROP_DPI", "400"))
_MIN_WIDTH = int(os.environ.get("SLAM_CROP_MIN_WIDTH", "120"))
_MAX_WIDTH = int(os.environ.get("SLAM_CROP_MAX_WIDTH", "1700"))
_MIN_HEIGHT = int(os.environ.get("SLAM_CROP_MIN_HEIGHT", "500"))
_MAX_HEIGHT = int(os.environ.get("SLAM_CROP_MAX_HEIGHT", "1100"))
_MIN_ASPECT = float(os.environ.get("SLAM_CROP_MIN_ASPECT", "2.0"))
_MAX_ASPECT = float(os.environ.get("SLAM_CROP_MAX_ASPECT", "3.0"))
_CONTRAST = float(os.environ.get("SLAM_CROP_CONTRAST", "3.5"))
_MAX_CROPS = int(os.environ.get("SLAM_LOCAL_OCR_MAX_CHECKS", "70"))
# Drop flat blank rectangles (borders / gutters) without OCR.
_MIN_VARIANCE = float(os.environ.get("SLAM_CROP_MIN_VARIANCE", "120.0"))

_HASH_SIZE = 12
_MIN_CENTER_DIST = int(os.environ.get("SLAM_CROP_MIN_CENTER_DIST", str(round(45 * _DEFAULT_DPI / 300))))


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


def _log(level: str, message: str) -> str:
    return f"[{level.upper()}] {message}"


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

    pages = convert_from_bytes(pdf_bytes, dpi=_DEFAULT_DPI)
    if not pages:
        logs.append(_log("warn", "pdf2image returned 0 pages."))
        return [], logs

    all_crops: list[dict[str, Any]] = []
    check_counter = 0

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
                    continue
                aspect = w / h if h else 0.0
                if not (_MIN_ASPECT < aspect < _MAX_ASPECT):
                    continue
                patch = gray[y : y + h, x : x + w]
                var_b = float(np.var(patch)) if patch.size else 0.0
                if var_b < _MIN_VARIANCE:
                    continue
                rough = hashlib.md5(patch.tobytes()[:4096]).hexdigest()
                if rough in rough_seen:
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
            check_id = f"P{page_idx:02d}C{check_counter:02d}"
            all_crops.append(
                {
                    "check_id": check_id,
                    "page": page_num,
                    "width": cand.w,
                    "height": cand.h,
                    "aspect_ratio": cand.aspect,
                    "image_b64": b64,
                    "notes": "geometry+v5_dedup",
                }
            )
            check_counter += 1
            page_kept += 1

        if page_kept:
            logs.append(_log("info", f"Check cropper page {page_num}: {page_kept} crop(s)."))

    logs.append(_log("info", f"Check cropper extracted {len(all_crops)} unique crop(s)."))
    return all_crops, logs
