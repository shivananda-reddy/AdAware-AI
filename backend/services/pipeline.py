
from typing import Optional, Dict, Any, List
import base64
import logging
import traceback
import numpy as np
import uuid
from datetime import datetime

from fastapi import HTTPException

# Adjusted imports for new structure
from backend.services.utils import to_hash, pil_from_bytes, download_image
from backend.services.ocr import extract_text_with_conf
from backend.services.nlp import analyze_text
from backend.services.fusion import compute_image_text_similarity, get_fusion_consistency_view
from backend.services.explain import highlight_keywords, generate_explanation, build_final_explanation
from backend.services.classifier import (
    predict_label,
    compute_credibility_score,
    build_full_report,
    get_effective_risk_profile,
)
from backend.services.llm import maybe_enhance_with_llm
from backend.services.quality import estimate_blur
from backend.services.vision import analyze_image
from backend.core.logging_config import setup_logging

# New imports
from backend.schemas import (
    HoverPayload, AnalysisResult, RiskLabel, RiskSubcategory, 
    Evidence, EvidenceSpan, RuleTrigger, SourceReputation
)
from backend.services import policy_rules
from backend.services import reputation
from backend.services import storage

LOG = setup_logging()

CACHE: Dict[str, Any] = {}

# ---------- Sanitizer: convert numpy types/arrays to plain Python ----------
def sanitize(obj: Any) -> Any:
    """
    Recursively convert numpy types and other non-JSON-serializable objects
    into plain Python types (int, float, str, list, dict, None).
    """
    if obj is None or isinstance(obj, (bool, str, int, float)):
        return obj
    if isinstance(obj, (np.generic,)):
        try: return obj.item()
        except: return float(obj)
    if isinstance(obj, (np.ndarray,)):
        return sanitize(obj.tolist())
    if isinstance(obj, dict):
        return {str(k): sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [sanitize(x) for x in obj]
    if hasattr(obj, "__dict__"):
        try: return sanitize(vars(obj))
        except: return str(obj)
    try: return float(obj)
    except: return str(obj)


def map_legacy_label_to_enum(legacy_label: str) -> RiskLabel:
    l = legacy_label.lower()
    if "scam" in l: return RiskLabel.SCAM_SUSPECTED
    if "risky" in l or "high" in l: return RiskLabel.HIGH_RISK
    if "promotion" in l: return RiskLabel.LOW_RISK
    return RiskLabel.SAFE # default

def extract_evidence(nlp_res: Dict, text: str) -> Evidence:
    ev = Evidence()
    # map strong phrases to risky phrases
    phrases = nlp_res.get("strong_phrases", [])
    for p in phrases:
        try:
            idx = text.lower().find(p.lower())
            start = idx
            end = idx + len(p) if idx != -1 else -1
            ev.risky_phrases.append(EvidenceSpan(
                text=p, start=start, end=end, reason="Strong urgency/sales language", kind="risky_phrase"
            ))
        except Exception:
            pass
            
    # emotion triggers
    emo = nlp_res.get("emotion", {}).get("label")
    if emo and emo != "NEUTRAL":
        ev.emotional_triggers.append(emo)
        
    return ev


async def run_analysis_pipeline(payload: HoverPayload) -> AnalysisResult:
    request_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat()
    
    try:
        # 0) Hashing for Cache
        key = to_hash(
            payload.image_base64,
            payload.image_url,
            payload.ad_text,
            payload.page_url,
            payload.use_llm # Include settings in hash
        )
        
        if key in CACHE:
            LOG.info("Cache hit for %s", key)
            cached_dict = CACHE[key]
            # Resurrect Pydantic model from dict, ensure new request_id/ts
            res = AnalysisResult(**cached_dict)
            res.request_id = request_id
            res.timestamp = timestamp
            res.cache_hit = True
            return res

        # 1) Image Load
        pil_image = None
        if payload.image_base64:
            try:
                img_b = base64.b64decode(payload.image_base64)
                pil_image = pil_from_bytes(img_b)
            except Exception as e:
                LOG.warning("base64 decode fail: %s", e)
        elif payload.image_url:
            try:
                b = download_image(payload.image_url)
                pil_image = pil_from_bytes(b)
            except Exception as e:
                LOG.warning("download fail: %s", e)

        # 1.5) Reputation Check
        rep = reputation.check_reputation(payload.image_url, payload.page_url)

        # 2) Vision & OCR
        vision_info = {}
        ocr_text = ""
        blur_info = {}
        
        if pil_image:
            # Blur
            try: blur_info = estimate_blur(pil_image)
            except: pass
            
            # OCR
            try: ocr_text, _ = extract_text_with_conf(pil_image)
            except: pass
            
            # Vision (only if explicitly enabled or needed? keeping generic for now)
            # Actually, to save cost/time we might skip analyze_image unless requested?
            # Existing logic ran it always. We'll stick to that but handle errors.
            try: vision_info = analyze_image(pil_image) or {}
            except: pass
            
        # 3) Text Construction
        vision_desc = vision_info.get("visual_description", "")
        vision_brand = vision_info.get("brand", "")
        
        combined_text_sources = [
            ocr_text,
            payload.ad_text or "",
            vision_desc,
            vision_info.get("product_name", ""),
            vision_brand
        ]
        combined_text = " ".join(filter(None, combined_text_sources)).strip()
        
        # 4) NLP & Classification (Legacy pipeline)
        nlp_res = analyze_text(combined_text)
        label_legacy, conf_legacy = predict_label(combined_text)
        
        sim = 0.0
        if pil_image and combined_text:
             try: sim = compute_image_text_similarity(pil_image, combined_text)
             except: pass

        # 5) Rules Engine (New)
        rule_triggers = policy_rules.evaluate_rules(combined_text)
        
        # 6) Construct Result
        final_label = map_legacy_label_to_enum(label_legacy)
        risk_score = 1.0 - float(conf_legacy) if final_label == RiskLabel.SAFE else float(conf_legacy)
        
        # Adjust risk based on rules
        for r in rule_triggers:
            if r.severity == "high":
                final_label = RiskLabel.HIGH_RISK
                risk_score = max(risk_score, 0.9)
            elif r.severity == "medium" and final_label in [RiskLabel.SAFE, RiskLabel.LOW_RISK]:
                final_label = RiskLabel.MODERATE_RISK
                risk_score = max(risk_score, 0.6)
                
        # 7) Legacy Report Construction (for explanation generator)
        # We construct this mainly to feed into legacy explainers and LLM
        legacy_report = build_full_report(
            label=label_legacy,
            confidence=conf_legacy,
            credibility=100.0 if final_label == RiskLabel.SAFE else (1.0-risk_score)*100,
            ocr_text=ocr_text,
            nlp_res=nlp_res,
            image_text_sim=sim,
            explanation={} # placeholder
        )
        legacy_report["vision"] = vision_info
        legacy_report["product_info"] = {"brand_name": vision_brand} # simplified

        # 8) LLM Enhancement (Optional)
        llm_used = False
        if payload.use_llm or (payload.consent and risk_score > 0.4 and risk_score < 0.8): 
            # Auto-trigger LLM if "ambiguous" risk and consent given, OR if explicitly requested
            try:
                legacy_report = await maybe_enhance_with_llm(legacy_report)
                llm_used = True
                # If LLM updated label, map it
                if "label_llm" in legacy_report:
                    # simplistic mapping back
                    # TODO: refine logic using the new fields in report
                    pass
            except Exception as e:
                LOG.warning("LLM fail: %s", e)
        
        # 9) Final Explanation
        final_expl = build_final_explanation(legacy_report)
        explanation_text = final_expl.get("explanation_text", "")

        # 10) Assembly
        result = AnalysisResult(
            request_id=request_id,
            timestamp=timestamp,
            final_label=final_label,
            risk_score=risk_score,
            subcategories=[], # TODO: map logic
            brand_entities=nlp_res.get("entities", []), # simplified
            sentiment=nlp_res.get("sentiment", {}).get("label", "neutral"),
            evidence=extract_evidence(nlp_res, combined_text),
            rule_triggers=rule_triggers,
            source_reputation=rep,
            ocr_text=ocr_text,
            llm_used=llm_used,
            explanation_text=explanation_text,
            confidence=conf_legacy
        )
        
        # 11) Cache & Storage
        sanitized_dict =  sanitize(result.model_dump())
        CACHE[key] = sanitized_dict
        
        # Async save to DB (we call the sync storage fn)
        storage.save_analysis(result, url=payload.image_url, domain=rep.domain)
        
        return result

    except Exception as exc:
        tb = traceback.format_exc()
        LOG.error("Pipeline failed: %s", tb)
        # Return error object instead of raising generic 500 if possible, 
        # but Schema expects strict return. We'll return a safe error object or raise HTTPException.
        # Constructing a valid AnalysisResult for error state is hard without mandatory fields.
        # Fallback to raising exception but maybe logging it cleanly
        raise HTTPException(status_code=500, detail={"error": str(exc), "trace": tb})
