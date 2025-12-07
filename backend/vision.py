# backend/vision.py
"""
AI Vision module for AdAware AI using OpenAI GPT-4o Vision model.

Extracts:
- visual_description
- brand
- product_name
- category
- objects
- logo_detected
- confidence score

Hybrid Option C (LLM-aware vision usage):

This module itself:
- Calls GPT-4o Vision once via `analyze_image(pil_image)` to get the core
  vision fields (visual_description, brand, etc.).
- Does NOT call the text LLM directly (no circular imports).

The LLM text module (llm.py) may later attach:
    report["vision"]["llm"] = {
        "visual_facts": [...],
        "suspicious_visual_cues": [...],
        "brand_consistency_notes": "..."
    }
and also refine:
    report["product_info"] = {
        "product_name", "brand_name", "category", "detected_price", ...
    }

To make those refinements effectively mandatory for consumers, this file
exposes helpers:

    get_effective_vision_block(report) -> Dict[str, Any]
        Returns a merged view combining:
            - classic vision fields,
            - LLM-enhanced visual cues,
            - refined product_info brand/category/name
"""

from __future__ import annotations

import os
import io
import json
import base64
import re
from typing import Dict, Any, List

from openai import OpenAI

# Allow override via env, default gpt-4o
MODEL = os.getenv("AD_AWARE_VISION_MODEL", "gpt-4o")


def _client() -> OpenAI:
    """Return OpenAI client. Reads OPENAI_API_KEY from environment."""
    return OpenAI()


def _pil_to_data_url(pil_image) -> str:
    """
    Convert a PIL image to a PNG data URL string suitable for the
    `image_url` field in the Responses API.
    """
    buf = io.BytesIO()
    pil_image.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _extract_response_text(resp: Any) -> str:
    """
    Best-effort extraction of text from Responses API result.

    Kept as a helper so we can adjust without touching the main logic.
    """
    # Newer SDKs may expose `output_text`
    out_text = None
    try:
        out_text = getattr(resp, "output_text", None)
    except Exception:
        out_text = None

    if isinstance(out_text, str) and out_text.strip():
        return out_text

    # Fallback: manual walk through `output` -> `content` -> `text`
    parts: List[str] = []
    try:
        for item in getattr(resp, "output", []) or []:
            for c in getattr(item, "content", []) or []:
                t = getattr(c, "text", None)
                if not t:
                    continue
                if isinstance(t, str):
                    parts.append(t)
                else:
                    val = getattr(t, "value", None)
                    if isinstance(val, str):
                        parts.append(val)
    except Exception:
        pass

    return "".join(parts)


def analyze_image(pil_image) -> Dict[str, Any]:
    """
    Sends an image to OpenAI GPT-4o Vision to extract:
      - visual_description
      - brand
      - product_name
      - category
      - objects
      - logo_detected
      - confidence (0–1)

    ALWAYS returns a dict.
    NEVER crashes the backend.
    """

    if not os.getenv("OPENAI_API_KEY"):
        return {
            "visual_description": "",
            "brand": "",
            "product_name": "",
            "category": "",
            "objects": [],
            "logo_detected": False,
            "confidence": 0.0,
            "vision_error": "Missing OPENAI_API_KEY environment variable",
        }

    try:
        data_url = _pil_to_data_url(pil_image)

        prompt = """
You are an AI vision system helping users understand online advertisements.

Analyze the image and return ONLY a single JSON object with this exact shape:

{
  "visual_description": "...",
  "brand": "...",
  "product_name": "...",
  "category": "...",
  "objects": ["...", "..."],
  "logo_detected": true,
  "confidence": 0.0
}

Rules:
- Keep brand names EXACT (e.g. "Red Bull", "Nike", "Samsung").
- If unsure about brand or product, use "" for that field.
- Category should be short, like: "Energy Drink", "Shoes", "Smartphone".
- "objects" is a short list of key visual elements.
- logo_detected = true if a brand logo is clearly visible.
- confidence = your confidence (0–1).
- Do NOT write anything outside the JSON.
"""

        client = _client()

        # Use the new OpenAI Responses API format
        resp = client.responses.create(
            model=MODEL,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": data_url},
                    ],
                }
            ],
        )

        # Extract raw text from response
        out_text = _extract_response_text(resp)

        # Try strict JSON parsing
        parsed: Dict[str, Any] = {}
        try:
            parsed = json.loads(out_text)
        except Exception:
            # Try to salvage JSON-like portion
            m = re.search(r"\{.*\}", out_text, flags=re.S)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                except Exception:
                    parsed = {}
            else:
                parsed = {}

        if not isinstance(parsed, dict):
            parsed = {}

        # Normalize fields
        visual_description = str(parsed.get("visual_description", "")).strip()
        brand = str(parsed.get("brand", "")).strip()
        product_name = str(parsed.get("product_name", "")).strip()
        category = str(parsed.get("category", "")).strip()

        objects = parsed.get("objects", [])
        if not isinstance(objects, list):
            objects = []

        logo_detected = bool(parsed.get("logo_detected", False))

        try:
            confidence = float(parsed.get("confidence", 0.0))
        except Exception:
            confidence = 0.0

        return {
            "visual_description": visual_description,
            "brand": brand,
            "product_name": product_name,
            "category": category,
            "objects": objects,
            "logo_detected": logo_detected,
            "confidence": confidence,
        }

    except Exception as e:
        return {
            "visual_description": "",
            "brand": "",
            "product_name": "",
            "category": "",
            "objects": [],
            "logo_detected": False,
            "confidence": 0.0,
            "vision_error": f"{type(e).__name__}: {e}",
        }


# ─────────────────────────────────────────────────────────────
# HYBRID OPTION C HELPERS (LLM-aware, no direct LLM calls here)
# ─────────────────────────────────────────────────────────────

def get_effective_vision_block(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a merged, LLM-aware view of the vision data for this ad.

    This is where LLM refinements become *mandatory* for any consumer
    that wants a "best guess" of what the ad visually shows.

    It combines:
      - report["vision"]         (raw GPT-4o Vision fields from this module)
      - report["vision"]["llm"]  (extra cues added by llm.maybe_enhance_with_llm)
      - report["product_info"]   (brand/product/category refined by LLM)

    Returned dict shape:

    {
      "visual_description": str,
      "brand": str,              # prefers product_info.brand_name if present
      "product_name": str,       # prefers product_info.product_name if present
      "category": str,           # prefers product_info.category if present
      "objects": [...],          # original objects
      "logo_detected": bool,
      "confidence": float,
      "visual_facts": [...],     # from vision.llm.visual_facts if any
      "suspicious_visual_cues": [...],
      "brand_consistency_notes": str or "",
    }
    """
    if not isinstance(report, dict):
        return {
            "visual_description": "",
            "brand": "",
            "product_name": "",
            "category": "",
            "objects": [],
            "logo_detected": False,
            "confidence": 0.0,
            "visual_facts": [],
            "suspicious_visual_cues": [],
            "brand_consistency_notes": "",
        }

    vision = report.get("vision") or {}
    if not isinstance(vision, dict):
        vision = {}

    vision_llm = vision.get("llm") or {}
    if not isinstance(vision_llm, dict):
        vision_llm = {}

    product_info = report.get("product_info") or {}
    if not isinstance(product_info, dict):
        product_info = {}

    # Base fields from classic vision
    visual_description = str(vision.get("visual_description") or "").strip()
    brand_raw = str(vision.get("brand") or "").strip()
    product_name_raw = str(vision.get("product_name") or "").strip()
    category_raw = str(vision.get("category") or "").strip()

    objects = vision.get("objects") or []
    if not isinstance(objects, list):
        objects = []

    logo_detected = bool(vision.get("logo_detected", False))

    try:
        confidence = float(vision.get("confidence", 0.0))
    except Exception:
        confidence = 0.0

    # LLM-refined product info takes priority for brand/product/category
    brand_eff = str(product_info.get("brand_name") or brand_raw).strip()
    product_eff = str(product_info.get("product_name") or product_name_raw).strip()
    category_eff = str(product_info.get("category") or category_raw).strip()

    # Additional cues from vision.llm (if set by llm.maybe_enhance_with_llm)
    visual_facts = vision_llm.get("visual_facts") or []
    if not isinstance(visual_facts, list):
        visual_facts = []

    suspicious_visual_cues = vision_llm.get("suspicious_visual_cues") or []
    if not isinstance(suspicious_visual_cues, list):
        suspicious_visual_cues = []

    brand_consistency_notes = str(
        vision_llm.get("brand_consistency_notes") or ""
    ).strip()

    return {
        "visual_description": visual_description,
        "brand": brand_eff,
        "product_name": product_eff,
        "category": category_eff,
        "objects": objects,
        "logo_detected": logo_detected,
        "confidence": confidence,
        "visual_facts": visual_facts,
        "suspicious_visual_cues": suspicious_visual_cues,
        "brand_consistency_notes": brand_consistency_notes,
    }
