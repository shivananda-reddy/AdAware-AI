# backend/explain.py
"""
Explanation utilities for AdAware AI backend.

Provides:
- highlight_keywords(text) -> List[str]
- generate_explanation(...) -> Dict[str, Any]

Hybrid Option C (LLM-aware):

This module itself does NOT call the LLM directly.

The llm module may later attach:
    report["llm_summary"]
    report["llm_explanation"] = {
        "bullets": [...],
        "short_takeaway": "..."
    }

Other modules (classifier, nlp, vision) also provide Hybrid helpers:
    - classifier.get_effective_risk_profile(report)
    - nlp.get_effective_nlp_summary(report)
    - nlp.get_persuasion_signals(report)
    - vision.get_effective_vision_block(report)

Using these, we expose:
    - build_final_explanation(report: Dict[str, Any]) -> Dict[str, Any]

which merges the classic explanation with LLM refinements into a
single, UI-friendly explanation object.
"""

from __future__ import annotations

from typing import List, Dict, Any

from backend import classifier
from backend.nlp import STRONG_SELL_PHRASES, get_persuasion_signals, get_effective_nlp_summary
from backend import vision


def highlight_keywords(text: str) -> List[str]:
    if not text:
        return []
    text_lower = text.lower()
    found = []
    for phrase in STRONG_SELL_PHRASES:
        if phrase in text_lower:
            found.append(phrase)
    # dedupe while preserving order
    seen = set()
    result = []
    for p in found:
        if p not in seen:
            seen.add(p)
            result.append(p)
    return result


def _authenticity_from_scores(confidence: float, image_text_sim: float) -> str:
    if confidence is None:
        confidence = 0.0
    if image_text_sim is None:
        image_text_sim = 0.0
    avg = (confidence + image_text_sim) / 2.0
    if avg >= 0.75:
        return "high"
    if avg >= 0.4:
        return "medium"
    if avg > 0.0:
        return "low"
    return "unknown"


def _url_trust_from_text(text: str) -> str:
    if not text:
        return "unknown"
    t = text.lower()
    if "bit.ly" in t or "tinyurl.com" in t or "freegift" in t:
        return "low"
    if "official" in t or "amazon" in t or "flipkart" in t or "myntra" in t:
        return "medium"
    return "unknown"


def generate_explanation(
    label: str,
    confidence: float,
    highlights: List[str],
    ocr_text: str,
    nlp_res: Dict[str, Any],
    image_text_sim: float,
) -> Dict[str, Any]:
    """
    Classic explanation builder used before LLM enrichment.

    This function does not depend on any LLM fields and is safe even
    when OpenAI is disabled. LLM-based refinements are merged later
    via build_final_explanation(report).
    """
    reasons: List[str] = []
    explanation_parts: List[str] = []

    sentiment = nlp_res.get("sentiment", {}) or {}
    sent_label = sentiment.get("label", "NEUTRAL")
    sent_score = float(sentiment.get("score", 0.0))

    entities = nlp_res.get("entities", []) or []
    brands = [e["text"] for e in entities if e.get("type") == "BRAND"]
    products = [e["text"] for e in entities if e.get("type") == "PRODUCT"]

    explanation_parts.append(f"The ad is classified as **{label}**.")
    explanation_parts.append(
        f"The model confidence for this label is about {confidence:.2f}."
    )

    if sent_label == "POSITIVE":
        explanation_parts.append(
            "The text uses overall positive or promotional sentiment."
        )
        reasons.append("Text has mostly positive/persuasive language.")
    elif sent_label == "NEGATIVE":
        explanation_parts.append(
            "The text contains negative or fear-based sentiment, which may be used to pressure the user."
        )
        reasons.append("Text contains negative or fear-oriented wording.")
    else:
        explanation_parts.append(
            "The sentiment appears relatively neutral overall."
        )

    if abs(sent_score) > 0.4:
        reasons.append(f"Sentiment intensity is relatively strong ({sent_label}).")

    if highlights:
        explanation_parts.append(
            "It includes marketing trigger phrases such as: " + ", ".join(highlights)
        )
        reasons.append("Detected strong marketing or urgency phrases in the text.")

    if ocr_text.strip():
        explanation_parts.append(
            "Some of the text was extracted directly from the image using OCR."
        )
        if len(ocr_text) > 120:
            explanation_parts.append(
                "The image appears to contain a significant amount of textual information."
            )

    product_name = products[0] if products else None
    brand_name = brands[0] if brands else None

    if brand_name:
        explanation_parts.append(f"The ad seems related to the brand **{brand_name}**.")
        reasons.append(f"Detected brand-like entity: {brand_name}.")

    if product_name:
        explanation_parts.append(
            f"It appears to promote a product or service named **{product_name}**."
        )
        reasons.append(f"Detected product-like entity: {product_name}.")

    explanation_parts.append(
        f"The image–text consistency score is about {image_text_sim:.2f}."
    )
    if image_text_sim < 0.2:
        reasons.append(
            "Image–text match is low; what you see may not fully match the written claims."
        )
    elif image_text_sim > 0.6:
        reasons.append(
            "Image–text match is reasonably high, indicating consistent visuals and text."
        )

    authenticity = _authenticity_from_scores(confidence, image_text_sim)

    full_text_for_url = (ocr_text or "") + " " + " ".join(
        e["text"] for e in entities if isinstance(e, dict)
    )
    url_trust = _url_trust_from_text(full_text_for_url)

    if authenticity == "high":
        reasons.append("Overall signals suggest the ad is relatively consistent.")
    elif authenticity == "low":
        reasons.append("Signals suggest possible inconsistency or aggressive persuasion.")

    # infer category (e.g. energy drink)
    category = None
    t_lower = (ocr_text or "").lower()
    if "energy drink" in t_lower:
        category = "Energy drink"
    elif "drink" in t_lower and "energy" in t_lower:
        category = "Energy drink"

    if label.lower() in {"scam", "fraud", "misleading"}:
        worth_it = "no"
        worth_reason = "Classified as potentially misleading or risky; proceed with caution."
    elif label.lower() in {"sponsored", "ad", "promotion"}:
        worth_it = "maybe"
        worth_reason = "Looks like typical sponsored content; double-check brand and price."
    else:
        worth_it = "maybe"
        worth_reason = "No strong red flags, but always review details before purchasing."

    alternatives: List[str] = []
    if brand_name:
        alternatives.append(f"Compare the same product on the official {brand_name} website.")
    alternatives.append("Check price and reviews on a trusted marketplace.")
    alternatives.append("Look for independent reviews or user feedback before buying.")

    explanation_text = " ".join(explanation_parts)

    explanation: Dict[str, Any] = {
        "explanation_text": explanation_text,
        "highlights": highlights,
        "trust": {
            "ad_authenticity": authenticity,
            "url_trust": url_trust,
            "url_examples": [],
            "reasons": reasons,
        },
        "worth_it": worth_it,
        "worth_reason": worth_reason,
        "alternatives": alternatives,
    }

    if product_name:
        explanation["product_name"] = product_name
    if brand_name:
        explanation["brand_name"] = brand_name
    if category:
        explanation["category"] = category

    return explanation


# ---------------------------------------------------------------------
# Hybrid Option C: LLM-aware final explanation
# ---------------------------------------------------------------------

def build_final_explanation(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a final, LLM-aware explanation object for the UI.

    Expected input:
        - `report` is the full report returned by classifier.build_full_report(...)
          and then optionally enhanced by llm.maybe_enhance_with_llm(report).

    This function merges:
        - Classic explanation: report["explanation"]
        - LLM explanation:     report.get("llm_explanation")
        - Hybrid views from:
            - classifier.get_effective_risk_profile(report)
            - nlp.get_effective_nlp_summary(report)
            - nlp.get_persuasion_signals(report)
            - vision.get_effective_vision_block(report)
        - Optional llm_summary if present.

    It does NOT modify the original report; it returns a new dict:

    {
      "label": "...",
      "risk_level": "low/medium/high",
      "credibility": float,
      "explanation_text": "...",       # merged narrative
      "bullets": [...],                # from llm_explanation if available
      "short_takeaway": "...",
      "nlp_summary": "...",
      "persuasion": { ... },
      "vision": { ... },               # effective vision block
      "worth_it": "...",
      "worth_reason": "...",
      "alternatives": [...],
      "trust": { ... }                 # merged reasons + risk_signals
    }
    """
    if not isinstance(report, dict):
        return {}

    base_expl = report.get("explanation") or {}
    if not isinstance(base_expl, dict):
        base_expl = {}

    llm_expl = report.get("llm_explanation") or {}
    if not isinstance(llm_expl, dict):
        llm_expl = {}

    # Hybrid helpers
    risk_profile = classifier.get_effective_risk_profile(report)
    nlp_summary = get_effective_nlp_summary(report)
    persuasion = get_persuasion_signals(report)
    vision_block = vision.get_effective_vision_block(report)

    llm_summary = report.get("llm_summary")
    if not isinstance(llm_summary, str):
        llm_summary = None

    # Build explanation_text by combining classic explanation_text and llm_summary
    expl_text_parts: List[str] = []
    base_text = base_expl.get("explanation_text")
    if isinstance(base_text, str) and base_text.strip():
        expl_text_parts.append(base_text.strip())

    if llm_summary and llm_summary.strip():
        expl_text_parts.append(llm_summary.strip())

    explanation_text = " ".join(expl_text_parts).strip()

    # Bullets / takeaway from LLM explanation if present
    bullets = llm_expl.get("bullets") or []
    if not isinstance(bullets, list):
        bullets = []

    short_takeaway = llm_expl.get("short_takeaway")
    if not isinstance(short_takeaway, str):
        # Fallback: simple one-liner from risk_profile if LLM didn't provide
        short_takeaway = (
            f"This ad is labeled {risk_profile.get('label_final', 'unknown')} "
            f"with a {risk_profile.get('risk_level_final', 'unknown')} overall risk level."
        )

    # Trust merge: use risk_profile.reasons as main trust reasons
    trust = base_expl.get("trust") or {}
    if not isinstance(trust, dict):
        trust = {}

    trust_merged = dict(trust)
    trust_merged["reasons"] = risk_profile.get("reasons", [])
    trust_merged["risk_signals"] = risk_profile.get("risk_signals", [])
    trust_merged["risk_level"] = risk_profile.get("risk_level_final", "unknown")

    # Worth it / alternatives (give LLM room to adjust in future if needed)
    worth_it = base_expl.get("worth_it", "maybe")
    worth_reason = base_expl.get("worth_reason", "")
    alternatives = base_expl.get("alternatives", [])

    return {
        "label": risk_profile.get("label_final", "unknown"),
        "risk_level": risk_profile.get("risk_level_final", "unknown"),
        "credibility": risk_profile.get("credibility_final", 0.0),
        "explanation_text": explanation_text,
        "bullets": bullets,
        "short_takeaway": short_takeaway,
        "nlp_summary": nlp_summary,
        "persuasion": persuasion,
        "vision": vision_block,
        "worth_it": worth_it,
        "worth_reason": worth_reason,
        "alternatives": alternatives,
        "trust": trust_merged,
    }
