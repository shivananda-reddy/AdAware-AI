
from typing import Optional, Dict, Any
import base64
import logging
import traceback
import numpy as np

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
from backend.schemas import HoverPayload
from backend.core.logging_config import setup_logging

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

    # numpy scalars
    if isinstance(obj, (np.generic,)):
        try:
            return obj.item()
        except Exception:
            return float(obj)

    # numpy arrays
    if isinstance(obj, (np.ndarray,)):
        return sanitize(obj.tolist())

    # dicts
    if isinstance(obj, dict):
        new = {}
        for k, v in obj.items():
            try:
                key = str(k)
            except Exception:
                key = repr(k)
            new[key] = sanitize(v)
        return new

    # list / tuple / set
    if isinstance(obj, (list, tuple, set)):
        return [sanitize(x) for x in obj]

    # objects with __dict__
    if hasattr(obj, "__dict__"):
        try:
            return sanitize(vars(obj))
        except Exception:
            return str(obj)

    # fallback
    try:
        return float(obj)
    except Exception:
        try:
            return int(obj)
        except Exception:
            return str(obj)

async def run_analysis_pipeline(payload: HoverPayload) -> Dict[str, Any]:
    try:
        key = to_hash(
            payload.image_base64,
            payload.image_url,
            payload.caption_text,
            payload.page_origin,
        )
        if key in CACHE:
            safe_cached = sanitize(CACHE[key])
            return {"cached": True, "result": safe_cached}

        # 1) Load image (base64 > url)
        pil_image = None
        if payload.image_base64:
            try:
                img_b = base64.b64decode(payload.image_base64)
                pil_image = pil_from_bytes(img_b)
            except Exception as e:
                LOG.warning("Failed to decode base64 image: %s", e)
                pil_image = None
        elif payload.image_url:
            try:
                b = download_image(payload.image_url)
                pil_image = pil_from_bytes(b)
            except Exception as e:
                LOG.warning("Failed to download image: %s", e)
                pil_image = None

        # 1.2) Image blur / quality
        blur_info: Dict[str, Any] = {}
        if pil_image is not None:
            try:
                blur_info = estimate_blur(pil_image)
                LOG.info("Blur info: %s", blur_info)
            except Exception as e:
                LOG.warning("Blur estimation failed: %s", e)
                blur_info = {}

        # 2) Vision analysis (OpenAI Vision)
        vision_info: Dict[str, Any] = {}
        if pil_image is not None:
            try:
                vision_info = analyze_image(pil_image) or {}
                LOG.info("Vision info: %s", vision_info)
            except Exception as e:
                LOG.warning("Vision analysis failed: %s", e)
                vision_info = {}

        # 3) OCR
        ocr_text, ocr_conf = "", 0.0
        if pil_image is not None:
            try:
                ocr_text, ocr_conf = extract_text_with_conf(
                    pil_image,
                    languages="eng+hin+kan+tel+tam",
                )
            except Exception as e:
                LOG.warning("OCR failed: %s", e)
                ocr_text, ocr_conf = "", 0.0

        # 4) Combined text (OCR + caption + vision text)
        vision_desc = ""
        vision_brand = ""
        vision_prod = ""
        vision_cat = ""

        if vision_info:
            vision_desc = vision_info.get("visual_description") or ""
            vision_brand = vision_info.get("brand") or ""
            vision_prod = vision_info.get("product_name") or ""
            vision_cat = vision_info.get("category") or ""

        combined_text_sources = [
            ocr_text,
            payload.caption_text or "",
            vision_desc,
            vision_brand,
            vision_prod,
            vision_cat,
        ]
        combined_text = " ".join(filter(None, combined_text_sources)).strip()

        # 5) NLP
        nlp_res = analyze_text(combined_text if combined_text else " ")
        if not isinstance(nlp_res, dict):
            LOG.warning("analyze_text returned non-dict: %s", type(nlp_res))
            nlp_res = {
                "language": "unknown",
                "entities": [],
                "sentiment": {"label": "NEUTRAL", "score": 0.0},
            }

        # 6) Vision-text similarity (if we have both image + text)
        sim = 0.0
        try:
            if pil_image is not None and combined_text:
                sim = compute_image_text_similarity(pil_image, combined_text)
        except Exception as e:
            LOG.warning("Similarity computation failed: %s", e)
            sim = 0.0

        # 7) Classification + credibility
        label, conf = predict_label(combined_text or " ")

        credibility = compute_credibility_score(
            float(conf) if isinstance(conf, (int, float, np.generic)) else conf,
            entity_reputation=0.5,  # can later tune per brand
            sentiment_score=nlp_res.get("sentiment", {}).get("score", 0),
            image_text_sim=sim,
            strong_phrases=nlp_res.get("strong_phrases") or [],
            has_clear_brand=bool(
                [
                    e
                    for e in (nlp_res.get("entities") or [])
                    if e.get("type") == "BRAND"
                ]
            ),
        )

        # 8) Classic explanation (before LLM)
        highlights = highlight_keywords(combined_text)
        explain = generate_explanation(
            label,
            conf,
            highlights,
            ocr_text,
            nlp_res,
            sim,
        )

        # 9) Build base report (classic pipeline)
        report = build_full_report(
            label=label,
            confidence=conf,
            credibility=credibility,
            ocr_text=ocr_text,
            nlp_res=nlp_res,
            image_text_sim=sim,
            explanation=explain,
        )
        report["ad_hash"] = key[:12]

        # 9.5) Merge vision info into product_info (AFTER report is created)
        if vision_info:
            pinfo = report.get("product_info") or {}
            vision_brand = vision_info.get("brand")
            vision_prod = vision_info.get("product_name")
            vision_cat = vision_info.get("category")
            vision_desc = vision_info.get("visual_description")

            if vision_brand:
                pinfo["brand_name"] = vision_brand
            if vision_prod:
                pinfo["product_name"] = vision_prod
            if vision_cat:
                pinfo["category"] = vision_cat
            if vision_desc:
                pinfo["visual_description"] = vision_desc

            report["product_info"] = pinfo

        # 9.6) Attach blur info
        if blur_info:
            report["image_quality"] = blur_info

        # 9.7) Attach raw vision info
        report["vision"] = vision_info

        # 10) OPTIONAL LLM enhancement (Hybrid Option C, gated by consent)
        try:
            if payload.consent:
                # IMPORTANT: maybe_enhance_with_llm needs schema/call update for new location or just works if imported 
                report = await maybe_enhance_with_llm(report)
        except Exception as e:
            LOG.warning("LLM enhancement failed: %s", e)

        # 11) Hybrid views: final explanation, fusion consistency, risk profile
        try:
            # Final LLM-aware explanation
            final_expl = build_final_explanation(report)
            report["explanation_final"] = final_expl

            # Fusion consistency view (image-text + blur + fusion_llm)
            fusion_view = get_fusion_consistency_view(report)
            report["fusion_consistency"] = fusion_view

            # Risk profile (classic + LLM classification/credibility)
            risk_profile = get_effective_risk_profile(report)
            report["risk_profile"] = risk_profile
        except Exception as e:
            LOG.warning("Hybrid explain/fusion enrichment failed: %s", e)

        # 12) Sanitize before caching/returning
        safe_report = sanitize(report)
        CACHE[key] = safe_report
        return {"cached": False, "result": safe_report}

    except Exception as exc:
        tb = traceback.format_exc()
        LOG.error("analyze_hover failed: %s", tb)
        raise HTTPException(status_code=500, detail={"error": str(exc), "trace": tb})
