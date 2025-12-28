# backend/llm.py
"""
LLM integration for AdAware AI.

Uses OpenAI Chat Completions API (gpt-4o by default) with JSON mode to:
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
LLM-based fields alongside them.

If OPENAI_API_KEY is missing or any error occurs, we keep the report
and only attach `llm_error`.
"""

from __future__ import annotations

import os
import json
import logging
from typing import Dict, Any, Optional

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None  # type: ignore

DEFAULT_MODEL = os.getenv("AD_AWARE_LLM_MODEL", "gpt-4o")

logger = logging.getLogger(__name__)


def _has_api_key() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def _get_client() -> Optional[AsyncOpenAI]:
    if AsyncOpenAI is None:
        logger.warning("openai package not installed or AsyncOpenAI not available.")
        return None
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    return AsyncOpenAI(api_key=api_key)


def _build_context(report: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the important pieces from the report into a compact dict."""
    label = report.get("label")
    confidence = report.get("confidence")
    credibility = report.get("credibility")

    ocr_text = (report.get("ocr_text") or "")[:1500]  # Increased limit slightly

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


SYSTEM_PROMPT = """You are an expert AI assistant that evaluates online ads and product promotions for safety, truthfulness, and quality.

You will receive a structured JSON analysis of an ad containing OCR text, computer vision labels, sentiment analysis, and trust signals.

Your task is to synthesize this information and return a single, valid JSON object containing a user-facing summary and enhanced analysis fields.

System Prompt:
186: Response Schema (JSON):
187: {
188:   "summary": "string, 180-220 words, plain text, 2-3 short paragraphs talking directly to the user",
189:   "label_llm": "classification label from [safe, low-risk, moderate-risk, high-risk, scam-suspected]",
190:   "sub_labels": ["list of strings, e.g. health-claim, financial-promise, urgency, etc."],
191:   "evidence_spans": [
192:     {
193:       "text": "exact phrase from text",
194:       "kind": "risky_phrase | emotional_trigger | policy_rule",
195:       "reason": "short explanation"
196:     }
197:   ],
198:   "credibility_llm": number (0-100, where 100 is perfectly trustworthy),
199:   "risk_level": "low" | "medium" | "high",
200:   "risk_signals_extra": ["list of additional risk strings"],
201:   "product_info_updates": {
202:       "product_name": "string",
203:       "brand_name": "string",
204:       "category": "string",
205:       "detected_price": "string"
206:   },
207:   "ocr_enhanced": {
208:       "ocr_text_clean": "cleaned version of OCR text",
209:       "issues": ["list of OCR quality issues"],
210:       "language": "ISO code (e.g. en, es)"
211:   },
212:   "nlp_enhanced": {
213:       "enhanced_summary": "1-2 sentence summary of the text content",
214:       "manipulative_phrases": ["list of manipulative or high-pressure phrases found"],
215:       "claims": ["list of key factual claims"],
216:       "call_to_action_strength": "low" | "medium" | "high"
217:   },
218:   "vision_enhanced": {
219:       "visual_facts": ["list of key visual elements confirmed"],
220:       "suspicious_visual_cues": ["list of potential deepfake artifacts or low-quality cues"],
221:       "brand_consistency_notes": "string"
222:   },
223:   "fusion_reasoning": {
224:       "overall_consistency": "consistent" | "partially_consistent" | "inconsistent",
225:       "consistency_score": number (0.0-1.0),
226:       "reasoning": "string explaining the consistency verdict"
227:   },
228:   "explanation_refined": {
229:       "bullets": ["3-5 distinct bullet points explaining the risk level and score"],
230:       "short_takeaway": "One clear actionable sentence for the user"
231:   }
232: }
233: """


async def maybe_enhance_with_llm(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Async call to OpenAI to enhance the report with:
      - Summaries
      - Enhanced metadata (OCR, NLP, Vision)
      - Fused reasoning
      - Trust scores
    
    Returns a COPY of the report with added LLM fields.
    """
    enhanced = dict(report)

    if not _has_api_key():
        enhanced["llm_error"] = "OPENAI_API_KEY not set"
        return enhanced
    
    client = _get_client()
    if not client:
        enhanced["llm_error"] = "Could not initialize OpenAI client"
        return enhanced

    try:
        # Prepare Context
        context_data = _build_context(enhanced)
        user_content = json.dumps(context_data, ensure_ascii=False)
        
        # Safe truncation to Avoid Context Window Errors (approx check)
        if len(user_content) > 15000:
            user_content = user_content[:15000] + "... [TRUNCATED]"

        # Async API Call
        response = await client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Analyze this ad data:\n{user_content}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.0,  # Low temperature for consistent JSON
            max_tokens=1500
        )

        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty response from LLM")

        data = json.loads(content)

        # --- Merge Data Back ---
        
        # 1. Top Level Fields
        if "summary" in data:
            enhanced["llm_summary"] = data["summary"]
        if "label_llm" in data:
            enhanced["label_llm"] = data["label_llm"]
        if "credibility_llm" in data:
            enhanced["credibility_llm"] = data["credibility_llm"]
            
        # New fields: Sub-labels & Evidence Spans
        if "sub_labels" in data:
            enhanced["sub_labels"] = data["sub_labels"]
        if "evidence_spans" in data:
            enhanced["llm_evidence_spans"] = data["evidence_spans"]
        
        # 2. Product Info
        if "product_info_updates" in data:
            current_prod = enhanced.get("product_info") or {}
            updates = data["product_info_updates"]
            # Only update if value is present
            for k, v in updates.items():
                if v and isinstance(v, str):
                    current_prod[k] = v
            enhanced["product_info"] = current_prod

        # 3. Trust & Risk
        trust = enhanced.get("trust") or {}
        if "risk_level" in data:
            trust["risk_level_llm"] = data["risk_level"]
        
        if "risk_signals_extra" in data:
            current_signals = trust.get("risk_signals") or []
            new_signals = data["risk_signals_extra"]
            if isinstance(new_signals, list):
                # Unique merge
                trust["risk_signals"] = list(set(current_signals + new_signals))
        enhanced["trust"] = trust

        # 4. Enhanced Modules
        if "ocr_enhanced" in data:
            enhanced["ocr_enhanced"] = data["ocr_enhanced"]
            # Backward compat convenience
            if "ocr_text_clean" in data["ocr_enhanced"]:
                enhanced["ocr_text_llm"] = data["ocr_enhanced"]["ocr_text_clean"]

        if "nlp_enhanced" in data:
            nlp = enhanced.get("nlp") or {}
            nlp["llm"] = data["nlp_enhanced"]
            enhanced["nlp"] = nlp

        if "vision_enhanced" in data:
            vision = enhanced.get("vision") or {}
            vision["llm"] = data["vision_enhanced"]
            enhanced["vision"] = vision

        # 5. Fusion & Explanation
        if "fusion_reasoning" in data:
            enhanced["fusion_llm"] = data["fusion_reasoning"]
        
        if "explanation_refined" in data:
            enhanced["llm_explanation"] = data["explanation_refined"]

        # Success - clear any old errors
        enhanced.pop("llm_error", None)

    except Exception as e:
        logger.error(f"LLM enhancement failed: {e}", exc_info=True)
        enhanced["llm_error"] = str(e)

    return enhanced

