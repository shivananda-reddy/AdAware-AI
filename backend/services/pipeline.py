
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
from backend.services import classifier
from backend.services.classifier import (
    predict_scam_label,
    compute_legitimacy_score,
    compute_model_confidence,
    locate_health_advisories,
    extract_evidence_spans,
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
            try: 
                blur_info = estimate_blur(pil_image)
            except Exception as e: 
                LOG.warning(f"Blur estimation failed: {e}")
            
            # OCR
            try: 
                ocr_text, _ = extract_text_with_conf(pil_image)
                LOG.info(f"OCR Success: Extracted {len(ocr_text)} chars")
            except Exception as e:
                LOG.warning(f"OCR failed: {e}")
            
            # Vision
            try: 
                vision_info = analyze_image(pil_image) or {}
            except Exception as e:
                LOG.warning(f"Vision analysis failed: {e}")
            
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
        
        sim = None  # Default to None (unavailable) not 0.0
        if pil_image and combined_text:
             try: 
                 sim = compute_image_text_similarity(pil_image, combined_text)
                 if sim is not None:
                     LOG.info(f"Image-text similarity: {sim:.3f}")
                 else:
                     LOG.info("Image-text similarity: unavailable (CLIP not loaded)")
             except Exception as e: 
                 LOG.warning(f"Fusion similarity failed: {e}")
                 sim = None

        # 5) Rules Engine (New)
        rule_triggers = policy_rules.evaluate_rules(combined_text)
        
        # 5b) Basic Classification (Scam Focus)
        label_legacy, _ = predict_scam_label(combined_text)
        
        # 6) Catalog Lookup & Enrichment
        # Move up NLP entities to help here
        raw_entities = nlp_res.get("entities", [])
        brand_entity_names = [e.get("text", "") if isinstance(e, dict) else str(e) for e in raw_entities if isinstance(e, dict) and e.get("type") == "BRAND"]
        
        from backend.services.catalog import get_catalog
        catalog = get_catalog()
        p_info = {} 
        
        # Fix: Use combined_text (includes ad_text) and ALL potential brand candidates (Vision + NLP)
        candidates = []
        if vision_brand: candidates.append(vision_brand)
        candidates.extend(brand_entity_names)
        
        known_brand = catalog.lookup(combined_text, candidates)
        
        # 6.5) Compute new Metrics
        
        # Health Advisories (Catalog + Heuristics)
        health_advisories = []
        if known_brand:
            health_advisories.extend(known_brand.get("health_advisory", []))
            
        # Add heuristic advisories (unique)
        heuristic_advisories = locate_health_advisories(combined_text)
        for h in heuristic_advisories:
            if h not in health_advisories: health_advisories.append(h)
            
        # Product Info Population (FIXED: populate earlier, handle catalog properly)
        if known_brand:
            # Catalog-matched brand - use catalog data as authoritative
            p_info["brand_name"] = known_brand.get("names", ["Unknown"])[0]
            p_info["category"] = known_brand.get("category", "Unclassified")
            p_info["product_name"] = vision_info.get("product_name") or known_brand.get("names", ["Unknown"])[0]
            p_info["formatted_price"] = known_brand.get("price_range", "Not found")
            category_source = "Catalog"
            LOG.info(f"✓ Brand matched in catalog: {p_info['brand_name']} ({p_info['category']})")
        else:
            # No catalog match - use vision/OCR inference
            p_info["brand_name"] = vision_brand or (brand_entity_names[0] if brand_entity_names else "Unknown brand")
            p_info["product_name"] = vision_info.get("product_name") or "Unknown product"
            
            # Infer category from keywords
            category_source = "Inferred"
            t_lower = combined_text.lower()
            if any(w in t_lower for w in ["energy drink", "caffeine", "energy"]):
                p_info["category"] = "Energy Drink"
            elif any(w in t_lower for w in ["supplement", "vitamin", "protein"]):
                p_info["category"] = "Supplements"
            elif any(w in t_lower for w in ["shoes", "sneakers", "footwear"]):
                p_info["category"] = "Footwear"
            elif any(w in t_lower for w in ["phone", "smartphone", "mobile"]):
                p_info["category"] = "Electronics"
            elif vision_info.get("category"):
                p_info["category"] = vision_info.get("category")
            else:
                p_info["category"] = "Unclassified"
            
            # Price detection from OCR entities
            price_entities = [e.get("text") for e in raw_entities if e.get("type") == "PRICE"]
            p_info["formatted_price"] = price_entities[0] if price_entities else "Not detected"
        
        # 7) Legitimacy Scoring
        # Start with catalog trust
        catalog_trust_level = known_brand.get("trust_baseline") if known_brand else None
        
        # Domain check - don't penalize local/extension/dashboard origins
        domain_trust = "neutral"
        if payload.page_url and payload.page_url not in ["WebDashboard", "Extension", "localhost", "127.0.0.1"]:
            # Only apply reputation checks for real external URLs
            if rep.flags and len(rep.flags) > 0:
                # Check if flags are serious (not just "Not HTTPS")
                serious_flags = [f for f in rep.flags if "Not HTTPS" not in f]
                if serious_flags:
                    domain_trust = "suspicious"
                    LOG.warning(f"Domain trust: suspicious due to {serious_flags}")
            elif rep.https and rep.domain:
                domain_trust = "trusted"
        else:
            # Local/extension - consider neutral to trusted
            domain_trust = "neutral"
            LOG.info(f"Domain trust: neutral (local/extension origin)")
        
        legitimacy_score = compute_legitimacy_score(
            scam_label=label_legacy,
            catalog_trust=catalog_trust_level,
            domain_trust=domain_trust,
            sentiment_score=nlp_res.get("sentiment", {}).get("score", 0.0),
            urgency_count=len(classifier._locate_spans(combined_text.lower(), classifier.SCAM_KEYWORDS, "risky_phrase"))
        )
        
        # 8) Computed Confidence
        # How sure are we about this result?
        ocr_quality = 1.0 if len(ocr_text) > 50 else (len(ocr_text)/50.0)
        computed_conf = compute_model_confidence(
            vision_success=bool(vision_info),
            ocr_quality_score=ocr_quality,
            catalog_match=bool(known_brand),
            image_text_sim=sim if sim is not None else None
        )

        # 9) Final Risk Label Determination
        # High legitimacy = SAFE or LOW_RISK regardless of health
        if legitimacy_score >= 80:
            final_label = RiskLabel.SAFE if not health_advisories else RiskLabel.LOW_RISK
            risk_score = 0.1
        elif legitimacy_score >= 50:
             final_label = RiskLabel.MODERATE_RISK
             risk_score = 0.5
        else:
             final_label = RiskLabel.HIGH_RISK
             risk_score = 0.9

        # 10) Legacy Report Construction (for explanation/LLM)
        legacy_report = build_full_report(
            label=label_legacy,
            confidence=computed_conf,
            credibility=legitimacy_score,
            ocr_text=ocr_text,
            nlp_res=nlp_res,
            image_text_sim=sim if sim is not None else 0.0,
            explanation={} 
        )
        legacy_report["vision"] = vision_info
        legacy_report["product_info"] = p_info

        # 11) LLM Enhancement
        llm_used = False
        if payload.use_llm: 
            try:
                legacy_report = await maybe_enhance_with_llm(legacy_report)
                llm_used = True
            except Exception as e:
                LOG.warning("LLM fail: %s", e)
        
        # 12) Final Explanation
        final_expl = build_final_explanation(legacy_report)
        explanation_text = final_expl.get("explanation_text", "")
        llm_summary = legacy_report.get("llm_summary") if payload.use_llm else None
        # Refresh product info in case LLM suggested updates
        p_info = legacy_report.get("product_info", p_info)
        
        # 13) Assembly
        # Extract refined signals
        evidence_spans, subcats = extract_evidence_spans(combined_text)
        
        raw_entities = nlp_res.get("entities", [])
        brand_entity_names = [e.get("text", "") if isinstance(e, dict) else str(e) for e in raw_entities if isinstance(e, dict) and e.get("type") == "BRAND"]
        if known_brand:
             brand_entity_names.insert(0, known_brand["names"][0])
        
        # Ensure sim is float or None for schema
        sim_value = sim if sim is not None else None
        
        result = AnalysisResult(
            request_id=request_id,
            timestamp=timestamp,
            final_label=final_label,
            risk_score=risk_score,
            legitimacy_score=legitimacy_score/100.0, # Convert 0-100 to 0-1
            health_advisory=health_advisories,
            subcategories=list(set(subcats)), 
            brand_entities=list(set(brand_entity_names)),
            sentiment=nlp_res.get("sentiment", {}).get("label", "neutral"),
            evidence=extract_evidence(nlp_res, combined_text),
            rule_triggers=rule_triggers,
            source_reputation=rep,
            ocr_text=ocr_text,
            llm_used=llm_used,
            explanation_text=explanation_text,
            llm_summary=llm_summary,
            confidence=computed_conf,
            image_text_similarity=sim_value,
            image_quality=blur_info,  # Use blur_info not vision_info
            product_info=p_info 
        )
        
        # 14) Cache & Storage
        sanitized_dict =  sanitize(result.model_dump())
        CACHE[key] = sanitized_dict
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
