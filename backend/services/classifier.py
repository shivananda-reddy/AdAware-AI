# backend/classifier.py
"""
Classification, Legitimacy Scoring, and Confidence computation.

Refactored for "Brand Intelligence" update:
- Splits Legitimacy (Scam Risk) from Health Advisories.
- Computes sophisticated Model Confidence.
- Provides Catalog-aware scoring.
"""

from __future__ import annotations
from typing import Any, Dict, List, Tuple, Optional
import re

# ---------------------------------------------------------------------
# 1) Keywords & Signals
# ---------------------------------------------------------------------

# Triggers for SCAM / LEGITIMACY risk
SCAM_KEYWORDS = [
    "win cash", "winner", "congratulations", "earn money fast", "get rich quick",
    "double your money", "crypto scheme", "guaranteed returns",
    "lottery", "jackpot", "free iphone", "free phone",
    "risk free", "no risk", "investment opportunity"
]

# Triggers for HEALTH ADVISORIES (not necessarily scams)
HEALTH_KEYWORDS = [
    "caffeine", "energy drink", "supplement", "weight loss", "diet pill",
    "cure", "remedy", "detox", "fat burner", "testosterone",
    "not for children", "pregnant", "consult a doctor"
]

PROMO_KEYWORDS = [
    "sale", "discount", "% off", "offer", "deal", "limited time",
    "buy now", "shop now", "order now", "flash sale",
]

def _locate_spans(text_lower: str, keywords: List[str], kind: str, category_override: str = None) -> List[Dict[str, Any]]:
    """Locate start/end indices of phrases."""
    spans = []
    if not text_lower:
        return spans
        
    for kw in keywords:
        start = 0
        while True:
            idx = text_lower.find(kw, start)
            if idx == -1:
                break
            spans.append({
                "kind": kind,
                "text": kw,
                "start": idx,
                "end": idx + len(kw),
                "reason": f"Contains phrase '{kw}'",
                "category": category_override or ("urgency" if kind == "risky_phrase" else "other")
            })
            start = idx + len(kw)
    return spans


# ---------------------------------------------------------------------
# 2) Label Prediction (Scam Focus)
# ---------------------------------------------------------------------

def predict_scam_label(text: str) -> Tuple[str, float]:
    """
    Predicts basic label based on SCAM signals only.
    Does NOT flag health terms as risky.
    """
    if not text:
        return "generic", 0.3

    t = text.lower()

    # Scam patterns
    if any(k in t for k in SCAM_KEYWORDS):
        return "scam_like", 0.85

    # Aggressive promo patterns
    risky_triggers = 0
    if "100% free" in t or "free money" in t: risky_triggers += 1
    if re.search(r"\b\d{2,}\s*% off\b", t):
        # Check for 90%+ off or similar unrealistic
        if "90%" in t or "95%" in t or "100%" in t:
            risky_triggers += 1

    if risky_triggers >= 2:
        return "risky_promo", 0.75

    # Normal promo
    if any(k in t for k in PROMO_KEYWORDS):
        return "promotion", 0.7

    return "generic", 0.5


# ---------------------------------------------------------------------
# 3) Health Advisory Detection
# ---------------------------------------------------------------------

def locate_health_advisories(text: str) -> List[str]:
    """Return list of human-readable health warnings based on keywords."""
    if not text:
        return []
    
    t = text.lower()
    advisories = []
    
    if "caffeine" in t or "energy" in t:
        # Refine: only if 'high caffeine' or 'energy drink' context? 
        # For now, simplistic map
        if "high caffeine" in t: advisories.append("High Caffeine Content")
        elif "energy drink" in t: advisories.append("Health Advisory: Energy Drink")
        
    if "supplement" in t or "diet" in t or "weight loss" in t:
        advisories.append("Dietary Supplement Warning")
        
    if "crypto" in t or "bitcoin" in t:
        # Financial warning, separate from scam but often related
        advisories.append("Financial Risk Advisory")
        
    return list(set(advisories))


# ---------------------------------------------------------------------
# 4) Computed Confidence
# ---------------------------------------------------------------------

def compute_model_confidence(
    vision_success: bool,
    ocr_quality_score: float, # inferred from logic (len > 50?)
    catalog_match: bool,
    image_text_sim: Optional[float]
) -> float:
    """
    Compute explicit confidence score (0.0 - 1.0).
    
    Confidence represents how much evidence we have, not quality of evidence.
    High confidence = we have multiple signals
    Low confidence = we're missing key data
    
    Returns value in range [0.1, 0.95]
    """
    score = 0.0
    
    # Baseline: Did we get anything?
    if ocr_quality_score > 0 or vision_success:
        score += 0.3  # Reduced from 0.4 to make room for other signals
    
    # Catalog match is strong ground truth
    if catalog_match:
        score += 0.35
        
    # High quality OCR
    if ocr_quality_score > 0.8:
        score += 0.15
    elif ocr_quality_score > 0.5:
        score += 0.10
        
    # Consistency check (Similarity)
    # Don't penalize if unavailable, but bonus if available AND high
    if image_text_sim is not None:
        if image_text_sim > 0.5:
            score += 0.15
        elif image_text_sim > 0.2: 
            score += 0.10
        # If very low (<0.2), don't add, but don't subtract
    else:
        # Similarity unavailable - give small bonus if we have catalog
        if catalog_match:
            score += 0.10
            
    return min(0.95, max(0.15, score))


# ---------------------------------------------------------------------
# 5) Legitimacy Scoring (0-100)
# ---------------------------------------------------------------------

def compute_legitimacy_score(
    scam_label: str,
    catalog_trust: Optional[str], # 'high', 'medium', 'low', None
    domain_trust: str, # 'trusted', 'neutral', 'suspicious'
    sentiment_score: float,
    urgency_count: int
) -> float:
    """
    Score targeting SCAM RISK only. Health issues do NOT lower this score.
    High score (100) = Very Legitimate / Safe.
    Low score (0) = Scam.
    """
    # 1. Base Score
    score = 50.0 # Neutral start
    
    # 2. Catalog Signal (Strongest)
    if catalog_trust == 'high':
        score = 90.0
    elif catalog_trust == 'medium':
        score = 75.0
    elif catalog_trust == 'low':
        score = 30.0
        
    # 3. Label Impact (if no catalog override)
    if not catalog_trust or catalog_trust == 'medium':
        if scam_label == "scam_like":
            score = min(score, 30.0)
            score -= 20
        elif scam_label == "risky_promo":
            score = min(score, 60.0)
            score -= 10
        elif scam_label == "promotion":
            score += 5
            
    # 4. Domain Trust (External)
    # If explicit high trust in brand/catalog, ignore minor domain flags (e.g. social media redirect)
    # or reduce penalty significantly.
    domain_penalty = 40
    if catalog_trust == 'high':
        domain_penalty = 0 # Known brand is trusted regardless of where it is hosted (usually)
    elif catalog_trust == 'medium':
        domain_penalty = 10
        
    if domain_trust == 'suspicious':
        score -= domain_penalty
    elif domain_trust == 'trusted':
        score += 10
        
    # 5. Urgency Penalties
    if urgency_count > 2:
        score -= 10
    if urgency_count > 5:
        score -= 15
        
    # 6. Sentiment (Minor bonus for positive/neutral, penalty for extreme negative?)
    # Ignored for now as often irrelevant to legitimacy (scams are super positive).
    
    return max(0.0, min(100.0, score))


# ---------------------------------------------------------------------
# 6) Helpers
# ---------------------------------------------------------------------

def extract_evidence_spans(text: str) -> Tuple[List[Dict], List[str]]:
    """Return detailed spans and subcategories list."""
    t = text.lower()
    spans = []
    subcats = []
    
    # Scam Phrases - map to valid RiskSubcategory enum values
    s_spans = _locate_spans(t, SCAM_KEYWORDS, "risky_phrase", "urgency")
    spans.extend(s_spans)
    if s_spans: subcats.append("urgency")  # Changed from "scam_risk" to valid enum
    
    # Health Keywords - map to valid RiskSubcategory enum values
    h_spans = _locate_spans(t, HEALTH_KEYWORDS, "advisory_phrase", "health-claim")
    # We locate them for highlighting, but maybe not 'risky_phrase' kind?
    # Keeping them helps UI highlight source of advisory.
    spans.extend(h_spans)
    if h_spans: subcats.append("health-claim")  # Changed from "health_risk" to valid enum
    
    return spans, list(set(subcats))


# ---------------------------------------------------------------------
# 7) Legacy & Report Building (Restored)
# ---------------------------------------------------------------------

def _extract_basic_product_info(
    nlp_res: Dict[str, Any],
    explanation: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Combine product/brand/category from NLP + explanation.
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
    
    # --- New Logic for Subcategories & Spans ---
    subcategories = []
    evidence_spans = []
    
    # 1. Locate spans in OCR/NLP text
    raw_text = (nlp_res.get("raw_text") or "").lower()
    
    # Urgency / suspicious phrases (SCAM focused)
    # Using new helper
    urgency_spans = _locate_spans(raw_text, SCAM_KEYWORDS + PROMO_KEYWORDS, "risky_phrase")
    evidence_spans.extend(urgency_spans)
    if urgency_spans:
        subcategories.append("urgency")
        
    # Map label/signals to subcategories
    if label == "scam_like":
        subcategories.append("scam-suspected")
    
    # Health/Financial/Crypto heuristics
    if any(w in raw_text for w in ["cure", "remedy", "doctor", "weight loss"]):
        subcategories.append("health-claim")
    if any(w in raw_text for w in ["bitcoin", "crypto", "investment", "double"]):
        subcategories.append("financial-promise")
        if "crypto" in raw_text:
            subcategories.append("crypto")

    # Add to report
    report["subcategories"] = list(set(subcategories))
    report["evidence_spans"] = evidence_spans

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
# 8) HYBRID OPTION C HELPERS (LLM-aware classification view)
# ---------------------------------------------------------------------

def _infer_risk_level_from_classic(label: str, credibility: float) -> str:
    """
    Infer a coarse risk level from classic label + credibility.
    """
    try:
        cred = float(credibility)
    except Exception:
        cred = 50.0

    label = (label or "").lower()

    if label == "scam_like" or cred < 40:
        return "high"

    if label in {"risky_promo", "promotion"} or cred < 70:
        return "medium"

    return "low"


def get_effective_label(report: Dict[str, Any]) -> str:
    """
    Return the best available classification label for this ad.
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
        return round(0.7 * c_llm + 0.3 * c_classic, 2)
    if c_llm is not None:
        return round(c_llm, 2)
    if c_classic is not None:
        return round(c_classic, 2)

    return 0.0


def get_effective_risk_profile(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a unified risk profile for the ad.
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

    risk_level_inferred = _infer_risk_level_from_classic(label_classic, cred_classic_f)
    risk_level_final = risk_level_llm or risk_level_inferred

    reasons = trust.get("reasons") or []
    if not isinstance(reasons, list):
        reasons = []

    risk_signals = trust.get("risk_signals") or []
    if not isinstance(risk_signals, list):
        risk_signals = []

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

def get_final_risk_profile(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns a unified risk profile, merging classic and LLM-based risk levels.
    """
    label_classic = report.get("label", "generic").lower()
    label_llm = report.get("label_llm", label_classic).lower()
    credibility_classic = report.get("credibility", 50.0)
    credibility_llm = report.get("credibility_llm", credibility_classic)
    
    if "scam" in label_llm or "scam_like" in label_classic:
        risk_level = "high"
    elif "risky" in label_llm or "promotion" in label_classic:
        risk_level = "medium"
    else:
        risk_level = "low"
    
    credibility = (credibility_classic + credibility_llm) / 2.0
    
    return {
        "label": label_llm,
        "credibility": round(credibility, 2),
        "risk_level": risk_level,
    }

