# backend/llm.py
"""
LLM integration for AdAware AI.

Uses OpenAI Responses API (gpt-4o by default) to:
- Generate a user-friendly natural language summary.
- Provide its own opinion on:
    - label / risk level
    - credibility score (0–100)
    - extra risk signals
    - refined product info (brand, product_name, category, price)

HYBRID OPTION C EXTENSIONS (LLM as helper for other modules):
The same LLM call also tries to enhance individual pipeline parts:

- OCR enhancement:
    - ocr_enhanced.ocr_text_clean
    - ocr_enhanced.issues
    - ocr_enhanced.language

- NLP enhancement:
    - nlp.llm.enhanced_summary
    - nlp.llm.manipulative_phrases
    - nlp.llm.claims
    - nlp.llm.call_to_action_strength

- Vision enhancement:
    - vision.llm.visual_facts
    - vision.llm.suspicious_visual_cues
    - vision.llm.brand_consistency_notes

- Classifier enhancement (already existed, now made explicit):
    - label_llm
    - credibility_llm
    - trust.risk_level_llm
    - trust.risk_signals (extended)

- Fusion reasoning:
    - fusion_llm: {
          "overall_consistency": "string like: consistent / partially_consistent / inconsistent",
          "consistency_score": float 0–1,
          "reasoning": "short paragraph explaining how text, image, and trust data fit together"
      }

- Explanation refinement:
    - llm_explanation: short 3–6 bullet explanation for the user

- Final summary:
    - llm_summary (main 180–220 word narrative summary for the user)

We do NOT throw away the classic pipeline numbers, we just add
LLM-based fields alongside them:
- llm_summary
- label_llm
- credibility_llm
- trust.risk_level_llm
- trust.risk_signals (extended)
- product_info (optionally refined)
- ocr_enhanced
- nlp.llm
- vision.llm
- fusion_llm
- llm_explanation

If OPENAI_API_KEY is missing or any error occurs, we keep the report
and only attach `llm_error`.
"""

from __future__ import annotations

import os
import json
import re
from typing import Dict, Any

from openai import OpenAI

DEFAULT_MODEL = os.getenv("AD_AWARE_LLM_MODEL", "gpt-4o")


def _has_api_key() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def _get_client() -> OpenAI:
    return OpenAI()


def _build_context(report: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the important pieces from the report into a compact dict."""
    label = report.get("label")
    confidence = report.get("confidence")
    credibility = report.get("credibility")

    ocr_text = (report.get("ocr_text") or "")[:900]

    nlp = report.get("nlp") or {}
    sentiment = nlp.get("sentiment") or {}
    emotion = nlp.get("emotion") or {}
    entities = nlp.get("entities") or []
    strong_phrases = nlp.get("strong_phrases") or []

    vision = report.get("vision") or {}
    vision_desc = vision.get("visual_description") or ""
    vision_brand = vision.get("brand") or ""
    vision_product = vision.get("product_name") or ""
    vision_category = vision.get("category") or ""
    vision_objects = vision.get("objects") or []
    vision_conf = vision.get("confidence", 0.0)

    image_quality = report.get("image_quality") or {}
    blur_score = image_quality.get("blur_score")
    is_blurry = image_quality.get("is_blurry")

    sim = report.get("image_text_similarity", 0.0)

    trust = report.get("trust") or {}
    url_trust = trust.get("url_trust")
    ad_auth = trust.get("ad_authenticity")
    reasons = trust.get("reasons") or []
    risk_signals = trust.get("risk_signals") or []

    value_j = report.get("value_judgement") or {}
    worth_it = value_j.get("worth_it")
    worth_reason = value_j.get("reason") or ""
    alternatives = value_j.get("alternatives") or []

    product_info = report.get("product_info") or {}
    prod_name = product_info.get("product_name") or vision_product
    prod_brand = product_info.get("brand_name") or vision_brand
    prod_cat = product_info.get("category") or vision_category
    prod_price = product_info.get("detected_price")

    return {
        "classification": {
            "label": label,
            "confidence": confidence,
            "credibility": credibility,
        },
        "nlp": {
            "sentiment": sentiment,
            "emotion": emotion,
            "entities": entities,
            "strong_phrases": strong_phrases,
        },
        "vision": {
            "visual_description": vision_desc,
            "brand": vision_brand,
            "product_name": vision_product,
            "category": vision_category,
            "objects": vision_objects,
            "confidence": vision_conf,
        },
        "product_info": {
            "product_name": prod_name,
            "brand_name": prod_brand,
            "category": prod_cat,
            "detected_price": prod_price,
        },
        "image_quality": {
            "blur_score": blur_score,
            "is_blurry": is_blurry,
        },
        "image_text_similarity": sim,
        "trust": {
            "url_trust": url_trust,
            "ad_authenticity": ad_auth,
            "reasons": reasons,
            "risk_signals": risk_signals,
        },
        "value_judgement": {
            "worth_it": worth_it,
            "reason": worth_reason,
            "alternatives": alternatives,
        },
        "ocr_excerpt": ocr_text,
    }


def _build_prompt_json_mode(context: Dict[str, Any]) -> str:
    """
    Ask the LLM to return JSON with:
      - summary (text for the user)
      - label_llm
      - credibility_llm
      - risk_level
      - risk_signals_extra
      - product_info_updates

    HYBRID OPTION C: also return per-module enhancements:
      - ocr_enhanced
      - nlp_enhanced
      - vision_enhanced
      - fusion_reasoning
      - explanation_refined
    """
    raw = json.dumps(context, ensure_ascii=False)
    if len(raw) > 7000:
        raw = raw[:7000] + "... [truncated]"

    prompt = (
        "You are an assistant that evaluates online ads and product promotions.\n"
        "You receive a structured analysis of ONE ad in JSON.\n\n"
        "Use ALL of it: classification, OCR text, sentiment, entities, vision result, "
        "image quality (blur), image-text similarity, trust signals, and value judgement.\n\n"
        "Your job is to return ONE JSON object with this exact shape:\n\n"
        "{\n"
        '  "summary": "string, 180-220 words, plain text, 1-3 short paragraphs",\n'
        '  "label_llm": "your classification label string (e.g. Safe Promotion, Scam Risk, Strongly Promotional, Neutral Info)",\n'
        '  "credibility_llm": number between 0 and 100 (your overall trust score, higher = safer),\n'
        '  "risk_level": "low" | "medium" | "high",\n'
        '  "risk_signals_extra": ["list of extra risk or safety observations as short phrases"],\n'
        '  "product_info_updates": {\n'
        '      "product_name": "string or empty if unknown",\n'
        '      "brand_name": "string or empty if unknown",\n'
        '      "category": "short category like Energy Drink, Shoes, Phone, Service, Cosmetics",\n'
        '      "detected_price": "price string if visible, else empty"\n'
        "  },\n"
        '  "ocr_enhanced": {\n'
        '      "ocr_text_clean": "cleaned and de-duplicated version of the main OCR text",\n'
        '      "issues": ["short bullet points about OCR limitations or missing pieces"],\n'
        '      "language": "language of the ad text if you can guess it (e.g. en, hi, kn, etc.)"\n'
        "  },\n"
        '  "nlp_enhanced": {\n'
        '      "enhanced_summary": "2-4 sentences summarizing the main claim and tone of the text only",\n'
        '      "manipulative_phrases": ["phrases that seem pushy, misleading, or manipulative"],\n'
        '      "claims": ["short bullets of key claims/promises made in the text"],\n'
        '      "call_to_action_strength": "low" | "medium" | "high"\n'
        "  },\n"
        '  "vision_enhanced": {\n'
        '      "visual_facts": ["short bullets describing what is visually shown (logos, products, scenes)"],\n'
        '      "suspicious_visual_cues": ["any visual elements that look low-quality, fake, or inconsistent"],\n'
        '      "brand_consistency_notes": "short sentence on whether image matches the claimed brand/product"\n'
        "  },\n"
        '  "fusion_reasoning": {\n'
        '      "overall_consistency": "consistent" | "partially_consistent" | "inconsistent",\n'
        '      "consistency_score": "number between 0 and 1 where 1 = perfectly consistent",\n'
        '      "reasoning": "short paragraph describing how image, text, trust signals, and value judgement fit together"\n'
        "  },\n"
        '  "explanation_refined": {\n'
        '      "bullets": ["3-6 short user-friendly bullets explaining why you gave this risk level and credibility score"],\n'
        '      "short_takeaway": "one-sentence plain-English advice to the user"\n'
        "  }\n"
        "}\n\n"
        "Rules:\n"
        "- Use the vision info to describe what is visually shown (brand, product, scene).\n"
        "- Use OCR + NLP info to understand claims and tone.\n"
        "- Consider blur_score and is_blurry: if the image is blurry or low-quality, mention it in risk_signals_extra.\n"
        "- Consider image_text_similarity: if very low, treat it as a risk and reflect that in fusion_reasoning.\n"
        "- Consider trust/risk_signals from the input, but you can add your own.\n"
        "- Do NOT mention JSON, fields, or internal names in the summary; talk directly to the user.\n"
        "- Output ONLY the JSON object, no explanation around it.\n\n"
        "Here is the input analysis JSON:\n"
        f"{raw}\n\n"
        "Return ONLY the JSON object now."
    )
    return prompt


def _parse_llm_json(text: str) -> Dict[str, Any]:
    """Robustly parse a JSON object from model output."""
    try:
        return json.loads(text)
    except Exception:
        # try to extract first {...}
        m = re.search(r"\{.*\}", text, flags=re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return {}
        return {}


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
    parts = []
    try:
        for item in getattr(resp, "output", []) or []:
            for c in getattr(item, "content", []) or []:
                t = getattr(c, "text", None)
                if not t:
                    continue
                # Some SDK versions wrap the string in an object
                if isinstance(t, str):
                    parts.append(t)
                else:
                    val = getattr(t, "value", None)
                    if isinstance(val, str):
                        parts.append(val)
    except Exception:
        pass

    return "".join(parts)


def maybe_enhance_with_llm(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call the LLM to:
      - add llm_summary
      - add label_llm, credibility_llm
      - extend trust with risk_level_llm and extra risk_signals
      - refine product_info

    HYBRID OPTION C:
      - add OCR enhancement (ocr_enhanced + ocr_text_llm)
      - add NLP enhancement under nlp["llm"]
      - add Vision enhancement under vision["llm"]
      - add fusion_llm reasoning block
      - add llm_explanation (bullets + short takeaway)

    Never raises; returns enhanced copy of report.
    """
    enhanced = dict(report)

    if not _has_api_key():
        enhanced["llm_error"] = "OPENAI_API_KEY not set in environment"
        return enhanced

    try:
        context = _build_context(report)
        prompt = _build_prompt_json_mode(context)

        client = _get_client()
        resp = client.responses.create(
            model=DEFAULT_MODEL,
            input=prompt,
        )

        out_text = _extract_response_text(resp)
        data = _parse_llm_json(out_text)
        if not isinstance(data, dict):
            data = {}

        # 1) Summary
        summary = data.get("summary")
        if isinstance(summary, str) and summary.strip():
            enhanced["llm_summary"] = summary.strip()

        # 2) LLM label & credibility
        label_llm = data.get("label_llm")
        if isinstance(label_llm, str) and label_llm.strip():
            enhanced["label_llm"] = label_llm.strip()

        cred_llm = data.get("credibility_llm")
        try:
            if cred_llm is not None:
                enhanced["credibility_llm"] = float(cred_llm)
        except Exception:
            pass

        # 3) Product info updates
        p_updates = data.get("product_info_updates") or {}
        if isinstance(p_updates, dict):
            pinfo = dict(enhanced.get("product_info") or {})
            for field in ("product_name", "brand_name", "category", "detected_price"):
                val = p_updates.get(field)
                if isinstance(val, str) and val.strip():
                    pinfo[field] = val.strip()
            enhanced["product_info"] = pinfo

        # 4) Trust / risk level + extra signals
        trust = dict(enhanced.get("trust") or {})
        risk_level = data.get("risk_level")
        if isinstance(risk_level, str) and risk_level.strip():
            trust["risk_level_llm"] = risk_level.strip().lower()

        extra_signals = data.get("risk_signals_extra") or []
        if isinstance(extra_signals, list):
            base = trust.get("risk_signals") or []
            if not isinstance(base, list):
                base = []
            base_extended = base + [s for s in extra_signals if isinstance(s, str)]
            # dedupe while preserving order
            seen = set()
            deduped = []
            for s in base_extended:
                if s not in seen:
                    seen.add(s)
                    deduped.append(s)
            trust["risk_signals"] = deduped

        enhanced["trust"] = trust

        # 5) OCR enhancement
        ocr_enhanced = data.get("ocr_enhanced") or {}
        if isinstance(ocr_enhanced, dict):
            # Store full block for any consumer (e.g., ocr.py / UI)
            enhanced["ocr_enhanced"] = ocr_enhanced

            # Convenience field: cleaned OCR text
            clean = ocr_enhanced.get("ocr_text_clean")
            if isinstance(clean, str) and clean.strip():
                enhanced["ocr_text_llm"] = clean.strip()

        # 6) NLP enhancement (attached under nlp["llm"])
        nlp_enhanced = data.get("nlp_enhanced") or {}
        if isinstance(nlp_enhanced, dict):
            nlp_block = dict(enhanced.get("nlp") or {})
            # Do not overwrite existing fields; just add an "llm" sub-block
            nlp_block["llm"] = nlp_enhanced
            enhanced["nlp"] = nlp_block

        # 7) Vision enhancement (attached under vision["llm"])
        vision_enhanced = data.get("vision_enhanced") or {}
        if isinstance(vision_enhanced, dict):
            vision_block = dict(enhanced.get("vision") or {})
            vision_block["llm"] = vision_enhanced
            enhanced["vision"] = vision_block

        # 8) Fusion reasoning
        fusion_reasoning = data.get("fusion_reasoning") or {}
        if isinstance(fusion_reasoning, dict):
            enhanced["fusion_llm"] = fusion_reasoning

        # 9) Explanation refinement
        explanation_refined = data.get("explanation_refined") or {}
        if isinstance(explanation_refined, dict):
            # Keep full structure for downstream consumers
            enhanced["llm_explanation"] = explanation_refined

        # clear any previous error
        enhanced.pop("llm_error", None)
        return enhanced

    except Exception as e:
        enhanced["llm_error"] = f"LLM call failed: {type(e).__name__}: {e}"
        return enhanced
