# backend/classifier.py
"""
Classification and credibility scoring for AdAware AI.

Provides:
- predict_label(text) -> (label: str, confidence: float)
- compute_credibility_score(...) -> float in [0, 100]
- build_full_report(...) -> Dict[str, Any]

This module combines:
- model-style label + confidence (heuristics for now),
- image–text similarity,
- sentiment,
- simple entity / URL / price info from NLP,
into a single report used by the API + web dashboard.

Hybrid Option C (LLM-aware view):

The classic functions above do NOT call the LLM and are safe even when
no OpenAI key is present.

The llm module may later attach:
    - report["label_llm"]
    - report["credibility_llm"]
    - report["trust"]["risk_level_llm"]
    - report["trust"]["risk_signals"] (extended)
    - report["fusion_llm"], report["llm_explanation"], etc.

This file exposes helpers that make those LLM-enhanced fields the
*default view* for other backend modules:

    - get_effective_label(report)
    - get_effective_credibility(report)
    - get_effective_risk_profile(report)

So consumers (explain.py, fusion.py, UI) can treat LLM as “mandatory”
for decisions when available, while still working if LLM is disabled.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple, Optional
import re


# ---------------------------------------------------------------------
# 1) Label prediction (simple heuristics for now)
# ---------------------------------------------------------------------
RISKY_KEYWORDS = [
    "win cash", "winner", "congratulations", "earn money fast", "get rich quick",
    "double your money", "crypto scheme", "guaranteed returns",
    "lottery", "jackpot", "free iphone", "free phone",
]

PROMO_KEYWORDS = [
    "sale", "discount", "% off", "offer", "deal", "limited time",
    "buy now", "shop now", "order now", "flash sale",
]


def _contains_any(text_lower: str, phrases: List[str]) -> bool:
    return any(p in text_lower for p in phrases)


def predict_label(text: str) -> Tuple[str, float]:
    """
    Very lightweight label classifier.

    Returns:
        label: one of ["scam_like", "risky_promo", "promotion", "generic"]
        confidence: float in [0, 1]
    """
    if not text:
        return "generic", 0.3

    t = text.lower()

    # Strongly scam-like patterns
    if _contains_any(t, RISKY_KEYWORDS):
        return "scam_like", 0.9

    # Suspiciously aggressive promo patterns
    risky_triggers = 0
    if "100% free" in t or "free money" in t:
        risky_triggers += 1
    if "no risk" in t or "guaranteed" in t:
        risky_triggers += 1
    if re.search(r"\b\d{2,}\s*% off\b", t):
        # Very large discounts can be suspicious
        risky_triggers += 1

    if risky_triggers >= 2:
        return "risky_promo", 0.8

    # Normal promotion / sponsored ad
    if _contains_any(t, PROMO_KEYWORDS):
        return "promotion", 0.7

    # fallback
    return "generic", 0.5


# ---------------------------------------------------------------------
# 2) Credibility / trust score
# ---------------------------------------------------------------------
def compute_credibility_score(
    base_conf: float,
    entity_reputation: float = 0.5,
    sentiment_score: float = 0.0,
    image_text_sim: float = 0.0,
    strong_phrases: Optional[List[str]] = None,
    has_clear_brand: Optional[bool] = None,
) -> float:
    """
    Compute a single trust / credibility score in [0, 100].

    Inputs:
        base_conf:         model confidence for the label (0..1)
        entity_reputation: heuristic 0..1 (0.5 = unknown brand, 1.0 = very reputable)
        sentiment_score:   -1..+1 from NLP
        image_text_sim:    0..1 similarity between vision & text
        strong_phrases:    list of urgency / strong-sell phrases from NLP
        has_clear_brand:   whether we detected a reasonable brand (NLP or vision)

    Strategy:
        Start from a weighted average and then add penalties/bonuses
        based on aggressive selling and missing brand.
    """
    if strong_phrases is None:
        strong_phrases = []

    # Clamp helper
    def clip01(x: float) -> float:
        return max(0.0, min(1.0, x))

    base_conf = clip01(float(base_conf))
    entity_reputation = clip01(float(entity_reputation))
    image_text_sim = clip01(float(image_text_sim))

    # Normalize sentiment magnitude (we prefer more neutral or mildly positive)
    sent_mag = abs(float(sentiment_score))
    # 1.0 when very neutral, 0.0 when extremely pos/neg
    sentiment_stability = 1.0 - min(sent_mag, 1.0)

    # Base score as weighted sum
    score = (
        0.45 * base_conf +
        0.20 * image_text_sim +
        0.20 * entity_reputation +
        0.15 * sentiment_stability
    )  # 0..1

    # Penalties for very aggressive marketing language
    n_strong = len(strong_phrases)
    if n_strong >= 6:
        score -= 0.20
    elif n_strong >= 3:
        score -= 0.10

    # Penalty if there is no clear brand
    if has_clear_brand is False:
        score -= 0.10
    elif has_clear_brand is True:
        score += 0.05  # a clear brand is slightly reassuring

    score = clip01(score)
    return round(score * 100.0, 2)


# ---------------------------------------------------------------------
# 3) Full report builder
# ---------------------------------------------------------------------
def _extract_basic_product_info(
    nlp_res: Dict[str, Any],
    explanation: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Combine product/brand/category from NLP + explanation.
    Explanation may already infer product_name / brand_name / category.
    """
    entities = nlp_res.get("entities") or []
    brand_entities = [e["text"] for e in entities if e.get("type") == "BRAND"]
    product_entities = [e["text"] for e in entities if e.get("type") == "PRODUCT"]
    price_entities = [e["text"] for e in entities if e.get("type") == "PRICE"]
    url_entities = [e["text"] for e in entities if e.get("type") == "URL"]

    # Explanation might have already figured out product / brand / category
    exp_brand = explanation.get("brand_name")
    exp_product = explanation.get("product_name")
    exp_category = explanation.get("category")

    product_name = exp_product or (product_entities[0] if product_entities else None)
    brand_name = exp_brand or (brand_entities[0] if brand_entities else None)
    category = exp_category or "Unclassified"

    detected_price = price_entities[0] if price_entities else "Not found"

    # Raw candidates we saw across NLP
    raw_candidates: List[str] = []
    for v in brand_entities + product_entities:
        if v not in raw_candidates:
            raw_candidates.append(v)

    return {
        "product_name": product_name or "Unknown",
        "brand_name": brand_name or "Unknown",
        "category": category,
        "detected_price": detected_price,
        "raw_candidates": raw_candidates,
        "urls": url_entities,
    }


def _build_risk_signals(
    label: str,
    credibility: float,
    nlp_res: Dict[str, Any],
) -> List[str]:
    """
    Heuristic scam / risk signals based on NLP and trust score.

    Note:
        LLM may later extend these risk signals and risk level
        via llm.maybe_enhance_with_llm(report), which adds fields
        under report["trust"]. This function only provides the
        classic, non-LLM signals.
    """
    signals: List[str] = []
    text = nlp_res.get("raw_text") or ""
    lower = text.lower()

    strong_phrases = nlp_res.get("strong_phrases") or []
    n_strong = len(strong_phrases)

    if n_strong >= 6:
        signals.append("Contains many urgency / strong-sell phrases.")
    elif n_strong >= 3:
        signals.append("Contains several urgency / strong-sell phrases.")

    # Large discount detection
    for m in re.finditer(r"\b(\d{2,})\s*% off\b", lower):
        try:
            pct = int(m.group(1))
            if pct >= 70:
                signals.append(f"Unusually large discount mentioned ({pct}% off).")
        except Exception:
            continue

    # Free + reward style patterns
    if "free" in lower and ("gift" in lower or "reward" in lower or "bonus" in lower):
        signals.append("Mentions 'free' together with gifts/rewards (check details carefully).")

    if "no risk" in lower or "guaranteed returns" in lower:
        signals.append("Promises 'no risk' or guaranteed returns (potential red flag).")

    if label == "scam_like":
        signals.append("Overall pattern of text looks similar to scam-style messages.")

    if credibility < 40:
        signals.append("Low overall trust score from combined signals.")

    return signals


def build_full_report(
    label: str,
    confidence: float,
    credibility: float,
    ocr_text: str,
    nlp_res: Dict[str, Any],
    image_text_sim: float,
    explanation: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Combine core pieces into a final report JSON.

    Note:
        - Vision info (brand/category/visual description) is already
          baked into `nlp_res` because main.py feeds combined text
          (OCR + caption + vision description) into analyze_text().
        - Image quality (blur) is added later in main.py (as image_quality)
          and shown in the UI.
        - LLM-based enhancements (llm_summary, label_llm, credibility_llm,
          trust.risk_level_llm, etc.) are added later by llm.maybe_enhance_with_llm().
    """
    # Base fields
    report: Dict[str, Any] = {
        "label": label,
        "confidence": float(confidence),
        "credibility": float(credibility),
        "ocr_text": ocr_text,
        "image_text_similarity": float(image_text_sim),
        "nlp": nlp_res or {},
    }

    # Explanation (already contains its own trust/alternatives structure)
    report["explanation"] = explanation or {}

    # Product info from NLP + explanation
    product_info = _extract_basic_product_info(nlp_res, explanation)
    # If explanation had product_name/brand_name/category explicitly, prefer those
    if explanation.get("product_name"):
        product_info["product_name"] = explanation["product_name"]
    if explanation.get("brand_name"):
        product_info["brand_name"] = explanation["brand_name"]
    if explanation.get("category"):
        product_info["category"] = explanation["category"]

    report["product_info"] = product_info

    # Trust and risk signals
    base_trust = explanation.get("trust") or {}
    trust = {
        "ad_authenticity": base_trust.get("ad_authenticity", "unknown"),
        "url_trust": base_trust.get("url_trust", "unknown"),
        "url_examples": base_trust.get("url_examples", []),
        "reasons": base_trust.get("reasons", []),
    }

    risk_signals = _build_risk_signals(label, credibility, nlp_res)
    if risk_signals:
        # Extend reasons with risk signals for visibility in the UI
        trust["reasons"] = trust.get("reasons", []) + risk_signals
        trust["risk_signals"] = risk_signals

    report["trust"] = trust

    # Value judgement (worth it / alternatives) from explanation
    value_judgement = {
        "worth_it": explanation.get("worth_it", "maybe"),
        "reason": explanation.get("worth_reason", ""),
        "alternatives": explanation.get("alternatives", []),
    }
    report["value_judgement"] = value_judgement

    return report


# ---------------------------------------------------------------------
# 4) HYBRID OPTION C HELPERS (LLM-aware classification view)
# ---------------------------------------------------------------------

def _infer_risk_level_from_classic(label: str, credibility: float) -> str:
    """
    Infer a coarse risk level from classic label + credibility.

    Used when LLM did not provide risk_level_llm.
    """
    try:
        cred = float(credibility)
    except Exception:
        cred = 50.0

    label = (label or "").lower()

    # Very low credibility or explicit scam-like label => high
    if label == "scam_like" or cred < 40:
        return "high"

    # Risky promo or low-medium credibility => medium
    if label in {"risky_promo", "promotion"} or cred < 70:
        return "medium"

    # Otherwise treat as low
    return "low"


def get_effective_label(report: Dict[str, Any]) -> str:
    """
    Return the best available classification label for this ad.

    Priority:
        1) LLM label if present: report["label_llm"]
        2) Classic label: report["label"]

    Consumers (UI, explain.py, etc.) should use this helper when they
    want the final label that includes LLM assistance.
    """
    if not isinstance(report, dict):
        return "unknown"

    label_llm = report.get("label_llm")
    if isinstance(label_llm, str) and label_llm.strip():
        return label_llm.strip()

    label = report.get("label")
    if isinstance(label, str) and label.strip():
        return label.strip()

    return "unknown"


def get_effective_credibility(report: Dict[str, Any]) -> float:
    """
    Return the best available credibility score in [0, 100].

    Priority:
        1) LLM credibility if present: report["credibility_llm"]
        2) Classic credibility: report["credibility"]

    If both exist, we slightly favor the LLM but do NOT discard the
    classic score: we take an average biased towards the LLM.
    """
    if not isinstance(report, dict):
        return 0.0

    cred_classic = report.get("credibility")
    cred_llm = report.get("credibility_llm")

    def _to_float(x: Any) -> Optional[float]:
        try:
            if x is None:
                return None
            return float(x)
        except Exception:
            return None

    c_classic = _to_float(cred_classic)
    c_llm = _to_float(cred_llm)

    if c_llm is not None and c_classic is not None:
        # Weighted average: 70% LLM, 30% classic
        return round(0.7 * c_llm + 0.3 * c_classic, 2)
    if c_llm is not None:
        return round(c_llm, 2)
    if c_classic is not None:
        return round(c_classic, 2)

    return 0.0


def get_effective_risk_profile(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a unified risk profile for the ad, merging classic classifier
    outputs with LLM-based trust reasoning.

    Output structure:
    {
        "label_classic": "...",
        "label_llm": "...",
        "label_final": "...",            # what to show as main label
        "credibility_classic": float,
        "credibility_llm": float or None,
        "credibility_final": float,      # what to show as main score
        "risk_level_llm": "low/medium/high" or None,
        "risk_level_inferred": "low/medium/high",
        "risk_level_final": "low/medium/high",
        "risk_signals": [...],           # merged + deduped risk signals
        "reasons": [...],                # trust reasons including risk_signals
    }

    This is how Hybrid Option C makes LLM help with label detection
    and risk perception, while still respecting your classic pipeline.
    """
    if not isinstance(report, dict):
        return {
            "label_classic": "unknown",
            "label_llm": None,
            "label_final": "unknown",
            "credibility_classic": 0.0,
            "credibility_llm": None,
            "credibility_final": 0.0,
            "risk_level_llm": None,
            "risk_level_inferred": "low",
            "risk_level_final": "low",
            "risk_signals": [],
            "reasons": [],
        }

    label_classic = report.get("label", "unknown")
    label_llm = report.get("label_llm")

    cred_classic = report.get("credibility")
    cred_llm = report.get("credibility_llm")

    # Normalize credibility
    try:
        cred_classic_f = float(cred_classic) if cred_classic is not None else 0.0
    except Exception:
        cred_classic_f = 0.0

    try:
        cred_llm_f = float(cred_llm) if cred_llm is not None else None
    except Exception:
        cred_llm_f = None

    cred_final = get_effective_credibility(report)

    trust = report.get("trust") or {}
    if not isinstance(trust, dict):
        trust = {}

    risk_level_llm = trust.get("risk_level_llm")
    if isinstance(risk_level_llm, str) and risk_level_llm.strip():
        risk_level_llm = risk_level_llm.strip().lower()
    else:
        risk_level_llm = None

    # Inferred risk level from classic info
    risk_level_inferred = _infer_risk_level_from_classic(label_classic, cred_classic_f)

    # Choose final risk level: prefer LLM when available
    risk_level_final = risk_level_llm or risk_level_inferred

    # Merge risk_signals and reasons (classic + LLM-extended)
    reasons = trust.get("reasons") or []
    if not isinstance(reasons, list):
        reasons = []

    risk_signals = trust.get("risk_signals") or []
    if not isinstance(risk_signals, list):
        risk_signals = []

    # Deduplicate risk_signals
    seen = set()
    risk_signals_dedup: List[str] = []
    for s in risk_signals:
        if not isinstance(s, str):
            continue
        key = s.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        risk_signals_dedup.append(key)

    # Ensure all risk_signals are present in reasons (for UI)
    all_reasons = list(reasons)
    existing = {str(r) for r in reasons}
    for s in risk_signals_dedup:
        if s not in existing:
            all_reasons.append(s)
            existing.add(s)

    return {
        "label_classic": label_classic,
        "label_llm": label_llm,
        "label_final": get_effective_label(report),
        "credibility_classic": round(cred_classic_f, 2),
        "credibility_llm": round(cred_llm_f, 2) if cred_llm_f is not None else None,
        "credibility_final": cred_final,
        "risk_level_llm": risk_level_llm,
        "risk_level_inferred": risk_level_inferred,
        "risk_level_final": risk_level_final,
        "risk_signals": risk_signals_dedup,
        "reasons": all_reasons,
    }
    # backend/classifier.py

def get_final_risk_profile(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns a unified risk profile, merging classic and LLM-based risk levels.
    """
    label_classic = report.get("label", "generic").lower()
    label_llm = report.get("label_llm", label_classic).lower()
    credibility_classic = report.get("credibility", 50.0)  # Default to 50 if not available
    credibility_llm = report.get("credibility_llm", credibility_classic)
    
    # Risk level determination: infer from classic or LLM data
    if "scam" in label_llm or "scam_like" in label_classic:
        risk_level = "high"
    elif "risky" in label_llm or "promotion" in label_classic:
        risk_level = "medium"
    else:
        risk_level = "low"
    
    # Combine the credibility scores (favor LLM but average them)
    credibility = (credibility_classic + credibility_llm) / 2.0
    
    return {
        "label": label_llm,
        "credibility": round(credibility, 2),
        "risk_level": risk_level,
    }

