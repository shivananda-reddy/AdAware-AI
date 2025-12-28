# backend/ocr.py
"""
Robust OCR module for AdAware AI.

This version handles:
- Preprocessing (resize, grayscale, contrast)
- Tesseract data extraction
- Fallback OCR
- Safe handling of unsupported formats
- Debug print output

HYBRID OPTION C (LLM integration, indirect):
- This module itself does NOT call the LLM (to avoid circular imports).
- It writes classic OCR fields:
    - ocr_text
    - avg_confidence (usually stored in debug or alongside OCR)
- The LLM module can later attach:
    - ocr_text_llm: cleaned / de-duplicated text
    - ocr_enhanced: { ocr_text_clean, issues, language, ... }

Downstream modules (NLP, fusion, explain, etc.) should use:
    - get_effective_ocr_text(report)
which prefers LLM-cleaned OCR when present.
"""

from typing import Tuple, Dict, Any
from PIL import Image, ImageOps, ImageEnhance
import pytesseract


def preprocess(img: Image.Image) -> Image.Image:
    """Improve image quality for OCR."""
    if img.mode != "RGB":
        img = img.convert("RGB")

    # convert to grayscale
    img = ImageOps.grayscale(img)

    # normalize contrast
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.8)

    # upscale small images
    w, h = img.size
    if min(w, h) < 500:
        scale = 500 / float(min(w, h))
        img = img.resize((int(w * scale), int(h * scale)), Image.BICUBIC)

    return img


def extract_text_with_conf(image: Image.Image, languages: str = "eng") -> Tuple[str, float]:
    """
    Extract text using Tesseract with confidence scores.

    Returns:
        (ocr_text, avg_confidence)
    """

    # Step 1 — preprocess
    try:
        img = preprocess(image)
    except Exception as e:
        print("[OCR] Preprocess failed:", e)
        return "", 0.0

    # Step 2 — try detailed OCR with word-level confidence
    try:
        data = pytesseract.image_to_data(
            img,
            lang=languages,
            output_type=pytesseract.Output.DICT
        )
    except Exception as e:
        print("[OCR] image_to_data failed:", e)
        # fallback to plain OCR
        try:
            text = pytesseract.image_to_string(img, lang=languages).strip()
            print("[OCR] Fallback OCR text:", repr(text[:300]))
            return text, 0.0
        except Exception as e2:
            print("[OCR] OCR failed completely:", e2)
            return "", 0.0

    texts = data.get("text", [])
    confs = data.get("conf", [])

    clean_words = []
    numeric_conf = []

    for t, c in zip(texts, confs):
        if t and t.strip():
            clean_words.append(t.strip())

        try:
            c = float(c)
            if c >= 0:
                numeric_conf.append(c)
        except Exception:
            pass

    ocr_text = " ".join(clean_words).strip()
    avg_conf = sum(numeric_conf) / len(numeric_conf) if numeric_conf else 0.0

    # Step 3 — fallback if nothing detected
    if not ocr_text:
        try:
            fallback = pytesseract.image_to_string(img, lang=languages).strip()
            if fallback:
                ocr_text = fallback
        except Exception:
            pass

    # Debug output (disabled for production noise reduction)
    # print("\n[OCR DEBUG]")
    # print("Avg confidence:", round(avg_conf, 2))
    # print("Extracted text:", repr(ocr_text[:300]))

    return ocr_text, avg_conf


# ─────────────────────────────────────────────────────────────
# HYBRID OPTION C HELPER (LLM-aware OCR consumer)
# ─────────────────────────────────────────────────────────────

def get_effective_ocr_text(report: Dict[str, Any]) -> str:
    """
    Hybrid helper for other modules (NLP, fusion, explain, etc.).

    It chooses the best OCR text to use:
    - If LLM-enhanced text exists (report["ocr_text_llm"]), use that.
    - Otherwise, fall back to raw report["ocr_text"].
    - If neither exists, return empty string.

    This keeps OCR pure (no LLM calls) but makes LLM influence
    *mandatory* for consumers that care about best-quality text.
    """
    if not isinstance(report, dict):
        return ""

    # Prefer LLM-cleaned OCR text when available
    text_llm = report.get("ocr_text_llm")
    if isinstance(text_llm, str) and text_llm.strip():
        return text_llm.strip()

    # Fallback to classic OCR text
    raw = report.get("ocr_text")
    if isinstance(raw, str):
        return raw.strip()

    return ""
