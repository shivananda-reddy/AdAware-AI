# backend/utils.py
"""
Utility helpers for AdAware AI backend.

Provides:
- to_hash(*parts) -> str           : stable short hash for caching.
- pil_from_bytes(b: bytes) -> Image: safe Pillow loader.
- download_image(url: str) -> bytes: robust HTTP download with checks.

LLM-friendly helpers (no direct OpenAI calls):
- safe_json_for_llm(obj, max_chars=4000) -> str
- shorten_text(text, max_chars=1000) -> str
- clean_url_for_llm(url) -> str
- build_llm_context_snippet(report: dict, max_chars=5000) -> str

These utilities are used in:
- main.py
- llm.py
- other backend modules
"""

from __future__ import annotations

from typing import Any, Optional, Dict
import hashlib
import logging
import io
import re
import json

import requests
from PIL import Image, UnidentifiedImageError

LOG = logging.getLogger("adaware.utils")


# ---------------------------------------------------------------------
# Hash helper
# ---------------------------------------------------------------------
def to_hash(*parts: Any, algo: str = "sha256") -> str:
    """
    Build a stable hash string from multiple parts (for cache keys).

    Each part is converted to string with repr() and separated by '||'.
    Only the first 16 hex characters are returned for brevity.
    """
    h = hashlib.new(algo)
    for p in parts:
        if p is None:
            s = "None"
        else:
            try:
                s = repr(p)
            except Exception:
                s = str(p)
        h.update(s.encode("utf-8", errors="ignore"))
        h.update(b"||")
    full = h.hexdigest()
    short = full[:16]
    return short


# ---------------------------------------------------------------------
# Image loading
# ---------------------------------------------------------------------
def pil_from_bytes(b: bytes) -> Image.Image:
    """
    Safely load a Pillow Image from raw bytes.

    - Uses BytesIO
    - Forces conversion to RGB
    - Raises a clear error if image cannot be identified
    """
    if not isinstance(b, (bytes, bytearray)):
        raise TypeError("pil_from_bytes expects bytes or bytearray")

    bio = io.BytesIO(b)
    try:
        img = Image.open(bio)
        img.load()  # force loading to catch any issues early
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        return img
    except UnidentifiedImageError as e:
        LOG.error("PIL cannot identify image file: %s", e)
        raise
    except Exception as e:
        LOG.error("Failed to open image from bytes: %s", e)
        raise


# ---------------------------------------------------------------------
# Image downloading
# ---------------------------------------------------------------------
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; AdAwareAI/1.0; +https://example.com/adaware)"
    )
}


def _looks_like_image_url(url: str) -> bool:
    if not url:
        return False
    lower = url.lower()
    return any(lower.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif"])


def download_image(url: str, timeout: float = 10.0) -> bytes:
    """
    Download an image from a URL and return raw bytes.

    - Adds a browser-like User-Agent
    - Checks HTTP status
    - Checks basic Content-Type for images (if present)
    - Raises exceptions with useful messages when something goes wrong
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError("download_image: URL is empty or not a string")

    url = url.strip()
    LOG.info("Downloading image from URL: %s", url)

    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout, stream=True)
    except Exception as e:
        LOG.error("Failed to fetch URL %s: %s", url, e)
        raise RuntimeError(f"Failed to fetch image URL: {e}")

    if resp.status_code != 200:
        LOG.error("Non-200 status for %s: %s", url, resp.status_code)
        raise RuntimeError(f"HTTP {resp.status_code} when fetching image")

    content_type = resp.headers.get("Content-Type", "").lower()
    if content_type and "image" not in content_type:
        # It's still possible that it's an image, but warn for debugging:
        LOG.warning(
            "URL %s returned non-image Content-Type: %s", url, content_type
        )

    try:
        data = resp.content
    finally:
        resp.close()

    if not data:
        raise RuntimeError("Downloaded image is empty")

    return data


# ---------------------------------------------------------------------
# LLM-friendly helpers (no OpenAI dependency here)
# ---------------------------------------------------------------------
def shorten_text(text: str, max_chars: int = 1000) -> str:
    """
    Safely shorten a block of text for LLM prompts.

    - Guarantees len(text) <= max_chars
    - Keeps the beginning and end if truncation is needed
    """
    if text is None:
        return ""
    text = str(text)
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + " ... " + text[-half:]


def safe_json_for_llm(obj: Any, max_chars: int = 4000) -> str:
    """
    Dump any object to JSON for LLM prompts, truncating if needed.

    Always returns a string. Any serialization errors are logged and
    a fallback string is returned.
    """
    try:
        raw = json.dumps(obj, ensure_ascii=False)
    except Exception as e:
        LOG.warning("safe_json_for_llm: json.dumps failed: %s", e)
        raw = repr(obj)

    if len(raw) > max_chars:
        raw = raw[: max_chars - 20] + "... [truncated]"
    return raw


def clean_url_for_llm(url: Optional[str]) -> str:
    """
    Clean tracking parameters from URLs before sending to the LLM,
    so prompts stay shorter and clearer.

    Examples:
    - Remove common tracking query params like utm_source, fbclid, etc.
    """
    if not url:
        return ""
    url = url.strip()

    # Split into base + query
    if "?" not in url:
        return url

    base, query = url.split("?", 1)
    parts = query.split("&")

    keep_params = []
    drop_keys = {"utm_source", "utm_medium", "utm_campaign", "utm_term",
                 "utm_content", "fbclid", "gclid", "igshid"}

    for p in parts:
        if "=" not in p:
            continue
        k, v = p.split("=", 1)
        if k.lower() in drop_keys:
            continue
        keep_params.append(f"{k}={v}")

    if not keep_params:
        return base
    return base + "?" + "&".join(keep_params)


def build_llm_context_snippet(report: Dict[str, Any], max_chars: int = 5000) -> str:
    """
    Build a compact JSON snippet from a full analysis report,
    optimized for use inside llm.py prompts.

    - Keeps only the most important keys.
    - Uses safe_json_for_llm for truncation.

    NOTE: This is aligned with the core fields used in llm._build_context:
        - classification-style info (label, credibility)
        - OCR text
        - NLP block
        - product_info
        - trust
        - value_judgement
        - image_quality
        - vision
        - image_text_similarity
    """
    if not isinstance(report, dict):
        return safe_json_for_llm(report, max_chars=max_chars)

    core = {
        "label": report.get("label"),
        "credibility": report.get("credibility"),
        "image_text_similarity": report.get("image_text_similarity"),
        "ocr_text": shorten_text(report.get("ocr_text", ""), max_chars=800),
        "nlp": report.get("nlp"),
        "product_info": report.get("product_info"),
        "trust": report.get("trust"),
        "value_judgement": report.get("value_judgement"),
        "image_quality": report.get("image_quality"),
        "vision": report.get("vision"),          # 🔹 ADDED: align with llm & vision pipeline
        "ad_hash": report.get("ad_hash"),
    }

    return safe_json_for_llm(core, max_chars=max_chars)
