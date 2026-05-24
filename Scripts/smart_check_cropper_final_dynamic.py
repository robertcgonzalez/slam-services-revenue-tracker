import os
import shutil
from pathlib import Path
import cv2
import numpy as np
from pdf2image import convert_from_path
from PIL import Image, ImageEnhance
import easyocr
import pandas as pd
from tqdm import tqdm
import hashlib

# ================== CONFIG v5 ==================
PDF_DPI = 400
MIN_WIDTH = 120
MAX_WIDTH = 1700
MIN_HEIGHT = 500          # exclude short footer blocks
MAX_HEIGHT = 1100
MIN_ASPECT = 2.0
MAX_ASPECT = 3.0
OCR_TEXT_THRESHOLD = 0.25
CONTRAST_FACTOR = 3.5
# ===============================================

def simple_image_hash(img_array):
    """Simple perceptual hash for deduplication"""
    pil_img = Image.fromarray(img_array).resize((8, 8)).convert('L')
    pixels = list(pil_img.getdata())
    avg = sum(pixels) / len(pixels)
    bits = ''.join('1' if p > avg else '0' for p in pixels)
    return hashlib.md5(bits.encode()).hexdigest()

def process_pdf(pdf_path: str):
    pdf_path = Path(pdf_path)
    out_dir = Path("cropped_checks_final_dynamic")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(exist_ok=True)

    print(f"🔧 Dynamic cropper v5 — GRID + DEDUP + JUNK FILTER")
    print(f"Processing: {pdf_path.name}")

    pages = convert_from_path(str(pdf_path), dpi=PDF_DPI)
    reader = easyocr.Reader(['en'], gpu=False)

    all_checks = []
    seen_hashes = set()
    check_counter = 0

    for page_num, page in enumerate(tqdm(pages, desc="Scanning pages")):
        img = np.array(page)
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

        thresholds = [
            cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 9, 3),
            cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 11, 2),
            cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY_INV)[1]
        ]

        page_checks = 0
        for thresh_idx, thresh in enumerate(thresholds):
            kernel = np.ones((3,3), np.uint8)
            dilated = cv2.dilate(thresh, kernel, iterations=2)
            contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                if not (MIN_WIDTH < w < MAX_WIDTH and MIN_HEIGHT < h < MAX_HEIGHT):
                    continue
                aspect = w / h
                if not (MIN_ASPECT < aspect < MAX_ASPECT):
                    continue

                cropped = img[y:y+h, x:x+w]
                cropped_pil = Image.fromarray(cropped).convert('RGB')
                enhancer = ImageEnhance.Contrast(cropped_pil.convert('L'))
                enhanced = enhancer.enhance(CONTRAST_FACTOR).convert('RGB')
                enhanced_np = np.array(enhanced)

                # OCR
                result = reader.readtext(enhanced_np, detail=0, paragraph=True, text_threshold=OCR_TEXT_THRESHOLD)
                full_text = " ".join(result).lower()

                # JUNK FILTER - bank contact block
                junk_keywords = ["telephone us at", "p.o. box 1125", "in case of errors", "cullman, al 35056"]
                if any(kw in full_text for kw in junk_keywords):
                    continue

                # MUST contain strong check keywords
                check_keywords = ["pay to", "order of", "memo", "dollars"]
                if not any(kw in full_text for kw in check_keywords) and len(full_text) < 20:
                    continue

                # Deduplication via simple image hash
                img_hash = simple_image_hash(enhanced_np)
                if img_hash in seen_hashes:
                    continue
                seen_hashes.add(img_hash)

                check_id = f"P{page_num:02d}C{check_counter:02d}"
                cropped_path = out_dir / f"check_{check_id}.png"
                enhanced.save(cropped_path)

                all_checks.append({
                    "page": page_num + 1,
                    "check_id": check_id,
                    "width": w,
                    "height": h,
                    "aspect_ratio": round(aspect, 3),
                    "cropped_image_path": str(cropped_path),
                    "notes": f"v5 grid+dedup (thresh {thresh_idx})"
                })
                check_counter += 1
                page_checks += 1

        print(f"  Page {page_num+1}: {page_checks} candidates")

    if all_checks:
        df = pd.DataFrame(all_checks)
        csv_path = out_dir / "checks_metadata.csv"
        df.to_csv(csv_path, index=False)
        print(f"\n✅ DYNAMIC CROP COMPLETE!")
        print(f"   Extracted {len(all_checks)} unique high-quality checks")
        print(f"   📁 Folder: {out_dir}/")
        print(f"   📊 Metadata: {csv_path}")
    else:
        print("\n⚠️  No checks detected — let me know the count and we'll iterate.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        process_pdf(sys.argv[1])
    else:
        print("Drag & drop the PDF onto this script or run via PowerShell wrapper.")