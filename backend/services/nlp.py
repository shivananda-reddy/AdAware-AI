# backend/nlp.py
"""
Advanced NLP utilities for AdAware AI.

Uses HuggingFace transformers (if available) for:
- Sentiment analysis (DistilBERT SST-2)
- Named entity recognition (BERT-based NER)

Plus:
- Keyword/regex based entity detection (brands, products, URLs, prices)
- Strong marketing / urgency phrase detection

Public API:
    STRONG_SELL_PHRASES: List[str]
    analyze_text(text: str) -> Dict[str, Any]

Hybrid Option C (LLM-aware):
- The LLM module can optionally attach an `nlp["llm"]` block to the
  main report with fields like:
    - enhanced_summary
    - manipulative_phrases
    - claims
    - call_to_action_strength

- This file exposes helpers that make LLM-enhanced NLP effectively
  “mandatory” for consumers:
    - get_effective_nlp_summary(report)
    - get_persuasion_signals(report)

If transformers or models are not available, it falls back to
a lightweight lexicon-based implementation so the backend
never completely breaks.
"""

from __future__ import annotations

from typing import List, Dict, Any
import re
import logging

LOG = logging.getLogger("adaware.nlp")

# ---------------------------------------------------------------------
# Strong sell / urgency phrases (used by explain.py + UI)
# ---------------------------------------------------------------------
STRONG_SELL_PHRASES: List[str] = [
    "limited time",
    "hurry up",
    "act now",
    "only today",
    "offer ends soon",
    "don’t miss",
    "don't miss",
    "last chance",
    "guaranteed results",
    "100% safe",
    "no risk",
    "money back guarantee",
    "free trial",
    "exclusive deal",
    "flash sale",
    "today only",
    "instant access",
    "earn money fast",
    "get rich quick",
    "lifetime access",
    "best price",
    "lowest price",
    "big discount",
    "massive discount",
    "buy now",
    "shop now",
    "order now",
    "signup now",
    "sign up now",
    "join now",
]

# ---------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------
URL_REGEX = re.compile(r"https?://[^\s]+", re.IGNORECASE)
PRICE_REGEX = re.compile(
    r"(₹|rs\.?|rs|inr|\$|usd)\s*[\d,]+(\.\d+)?|\b[\d,]+\s*(rs|₹|usd|\$)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------
# Lexicons for fallback sentiment
# ---------------------------------------------------------------------
POSITIVE_WORDS = {
    "amazing", "awesome", "best", "premium", "luxury", "exclusive",
    "guaranteed", "safe", "trusted", "official", "original", "genuine",
    "fast", "instant", "easy", "simple", "powerful", "advanced",
    "free", "discount", "offer", "deal", "sale", "save", "secure",
}

NEGATIVE_WORDS = {
    "scam", "fake", "fraud", "danger", "dangerous", "risk", "risky",
    "spam", "unsafe", "problem", "issue", "warning", "alert",
    "loss", "lose", "debt", "penalty",
}

FEAR_WORDS = {
    "limited", "only today", "last chance", "hurry", "urgent", "now",
    "before it’s too late", "don't miss", "don’t miss", "ends soon",
}

# Simple brand and product hints (rule-based layer)
KNOWN_BRANDS = {
    "red bull", "coca cola", "pepsi", "apple", "samsung", "nike",
    "adidas", "puma", "amazon", "flipkart", "myntra", "ajio",
    "spotify", "netflix", "swiggy", "zomato", "ola", "uber",
}

PRODUCT_KEYWORDS = {
    "shoes", "sneakers", "sandals", "heels", "boots",
    "watch", "smartwatch", "phone", "smartphone", "laptop", "earbuds",
    "headphones", "earphones", "tv", "tablet",
    "energy drink", "soft drink", "coffee", "tea",
    "course", "class", "training", "workshop", "coaching",
    "subscription", "membership", "plan", "offer", "bundle",
    "cream", "serum", "lotion", "shampoo", "conditioner",
}

# ---------------------------------------------------------------------
# Transformers integration
# ---------------------------------------------------------------------
_TRANSFORMERS_AVAILABLE = False
_sentiment_pipe = None
_ner_pipe = None

try:
    from transformers import pipeline  # type: ignore

    _TRANSFORMERS_AVAILABLE = True
    LOG.info("Transformers found, will use advanced NLP models.")

except Exception as e:  # pragma: no cover
    LOG.warning("Transformers not available, using fallback NLP. Error: %s", e)
    _TRANSFORMERS_AVAILABLE = False


def _get_sentiment_pipe():
    global _sentiment_pipe
    if _sentiment_pipe is None and _TRANSFORMERS_AVAILABLE:
        try:
            _sentiment_pipe = pipeline(
                "sentiment-analysis",
                model="distilbert-base-uncased-finetuned-sst-2-english",
            )
            LOG.info("Loaded sentiment model: distilbert-base-uncased-finetuned-sst-2-english")
        except Exception as e:
            LOG.error("Failed to load sentiment model, falling back: %s", e)
    return _sentiment_pipe


def _get_ner_pipe():
    global _ner_pipe
    if _ner_pipe is None and _TRANSFORMERS_AVAILABLE:
        try:
            _ner_pipe = pipeline(
                "ner",
                model="dslim/bert-base-NER",
                aggregation_strategy="simple",
            )
            LOG.info("Loaded NER model: dslim/bert-base-NER")
        except Exception as e:
            LOG.error("Failed to load NER model, falling back: %s", e)
    return _ner_pipe


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _detect_language(text: str) -> str:
    """
    Extremely lightweight "language" detection:
    - if Devanagari chars present -> "hi" (Hindi/Indic)
    - else default to "en"
    """
    if not text:
        return "unknown"

    # Devanagari Unicode range
    if re.search(r"[\u0900-\u097F]", text):
        return "hi"  # or "hi-mixed"
    return "en"


def _tokenize_simple(text: str) -> List[str]:
    raw_tokens = re.split(r"\s+", text.strip())
    tokens = [re.sub(r"[^\w@#₹$%\.]", "", t) for t in raw_tokens]
    return [t for t in tokens if t]


# ---------------------------------------------------------------------
# Sentiment
# ---------------------------------------------------------------------
def _sentiment_fallback(text: str) -> Dict[str, Any]:
    text_lower = text.lower()
    tokens = _tokenize_simple(text_lower)

    pos = sum(1 for t in tokens if t in POSITIVE_WORDS)
    neg = sum(1 for t in tokens if t in NEGATIVE_WORDS)

    total = pos + neg
    if total == 0:
        score = 0.0
    else:
        score = (pos - neg) / float(total)  # -1..+1

    if score > 0.2:
        label = "POSITIVE"
    elif score < -0.2:
        label = "NEGATIVE"
    else:
        label = "NEUTRAL"

    return {"label": label, "score": score}


def _compute_sentiment(text: str) -> Dict[str, Any]:
    """
    Use transformer sentiment model if available; otherwise lexicon fallback.
    """
    pipe = _get_sentiment_pipe()
    if pipe is not None:
        try:
            result = pipe(text[:512])  # avoid huge text
            if result:
                r = result[0]
                label_raw = r.get("label", "").upper()
                score_raw = float(r.get("score", 0.0))

                # Map to +/- score
                if "NEG" in label_raw:
                    label = "NEGATIVE"
                    score = -score_raw
                else:
                    label = "POSITIVE"
                    score = score_raw

                return {"label": label, "score": score}
        except Exception as e:
            LOG.error("Sentiment model failed, using fallback: %s", e)

    # Fallback
    return _sentiment_fallback(text)


def _derive_emotion(text: str, sentiment: Dict[str, Any]) -> Dict[str, Any]:
    """
    Very rough "emotion" label mainly for UI flavour.
    """
    text_lower = text.lower()
    sent_label = sentiment.get("label", "NEUTRAL")
    score = float(sentiment.get("score", 0.0))

    has_urgency = any(p in text_lower for p in STRONG_SELL_PHRASES) or any(
        f in text_lower for f in FEAR_WORDS
    )

    if sent_label == "POSITIVE" and has_urgency:
        emo_label = "EXCITED"
    elif sent_label == "NEGATIVE" and has_urgency:
        emo_label = "ANXIOUS"
    elif abs(score) < 0.15:
        emo_label = "CALM"
    else:
        emo_label = "NEUTRAL"

    return {"label": emo_label, "score": score}


# ---------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------
def _extract_urls(text: str) -> List[str]:
    return URL_REGEX.findall(text) or []


def _extract_prices(text: str) -> List[str]:
    return [m.group(0) for m in PRICE_REGEX.finditer(text)]


def _entities_rule_based(text: str) -> List[Dict[str, Any]]:
    """
    Rule-based entities: URLs, prices, known brands, product keywords, etc.
    """
    entities: List[Dict[str, Any]] = []
    text_stripped = text.strip()
    if not text_stripped:
        return entities

    lower = text_stripped.lower()

    # 1) URLs
    for url in _extract_urls(text_stripped):
        entities.append({"text": url, "type": "URL"})

    # 2) Prices
    for p in _extract_prices(text_stripped):
        entities.append({"text": p, "type": "PRICE"})

    # 3) Known brands (phrase-based)
    for brand in KNOWN_BRANDS:
        if brand in lower:
            entities.append({"text": brand.title(), "type": "BRAND"})

    # 4) Product keywords (simple)
    for kw in PRODUCT_KEYWORDS:
        if kw in lower:
            entities.append({"text": kw, "type": "PRODUCT"})

    return entities


def _entities_from_ner(text: str) -> List[Dict[str, Any]]:
    """
    Use transformer NER model if available. Map NER labels to our types.
    """
    pipe = _get_ner_pipe()
    if pipe is None:
        return []

    entities: List[Dict[str, Any]] = []
    try:
        # truncate to avoid crazy long texts
        ner_results = pipe(text[:512])
    except Exception as e:
        LOG.error("NER model failed, ignoring NER: %s", e)
        return []

    for r in ner_results:
        ent_text = r.get("word", "") or r.get("entity_group", "")
        ent_label = r.get("entity_group", "MISC").upper()
        if not ent_text:
            continue

        # Map NER label -> our simpler types
        # ORG, MISC -> BRAND
        # PRODUCT we approximate via heuristics
        if ent_label in {"ORG", "MISC"}:
            mapped_type = "BRAND"
        elif ent_label in {"PER", "PERSON"}:
            mapped_type = "PERSON"
        elif ent_label in {"LOC", "GPE"}:
            mapped_type = "LOCATION"
        else:
            mapped_type = "MISC"

        entities.append(
            {
                "text": ent_text,
                "type": mapped_type,
                "source": "NER",
            }
        )

    return entities


def _merge_entities(*lists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    merged: List[Dict[str, Any]] = []
    for lst in lists:
        for e in lst:
            key = (e.get("text", "").lower(), e.get("type", ""))
            if not key[0]:
                continue
            if key in seen:
                continue
            seen.add(key)
            merged.append(e)
    return merged


def _detect_strong_phrases(text: str) -> List[str]:
    if not text:
        return []
    lower = text.lower()
    found: List[str] = []
    for phrase in STRONG_SELL_PHRASES:
        if phrase in lower:
            found.append(phrase)
    # keep unique order
    seen = set()
    result: List[str] = []
    for p in found:
        if p not in seen:
            seen.add(p)
            result.append(p)
    return result


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------
def analyze_text(text: str) -> Dict[str, Any]:
    """
    Main function used by the backend.

    Input:
        text: combined text (OCR + caption + vision description) from main.py

    Returns a dict like:
    {
      "language": "en" | "hi" | "unknown",
      "sentiment": { "label": "POSITIVE/NEGATIVE/NEUTRAL", "score": float },
      "emotion":   { "label": "EXCITED/CALM/ANXIOUS/NEUTRAL", "score": float },
      "entities":  [
          {"text": "...", "type": "BRAND"|"PRODUCT"|"URL"|"PRICE"|...},
          ...
      ],
      "strong_phrases": [...],
      "raw_text": "..."
    }

    NOTE (Hybrid Option C):
        The LLM module may later attach additional fields under `nlp["llm"]`
        to enrich this analysis. This function itself does NOT call the LLM,
        so it is safe even when no OpenAI key is present.
    """
    if text is None:
        text = ""
    text = str(text).strip()

    language = _detect_language(text)
    sentiment = _compute_sentiment(text)
    emotion = _derive_emotion(text, sentiment)

    # Entities from NER + rule-based
    rb_entities = _entities_rule_based(text)
    ner_entities = _entities_from_ner(text) if _TRANSFORMERS_AVAILABLE else []
    entities = _merge_entities(rb_entities, ner_entities)

    strong_phrases = _detect_strong_phrases(text)

    return {
        "language": language,
        "sentiment": sentiment,
        "emotion": emotion,
        "entities": entities,
        "strong_phrases": strong_phrases,
        "raw_text": text,
    }


# ---------------------------------------------------------------------
# HYBRID OPTION C HELPERS (LLM-aware, no direct LLM calls here)
# ---------------------------------------------------------------------

def _get_nlp_block(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Internal helper: returns a normalized NLP block from the report.
    """
    if not isinstance(report, dict):
        return {}
    nlp = report.get("nlp") or {}
    if not isinstance(nlp, dict):
        return {}
    return nlp


def get_effective_nlp_summary(report: Dict[str, Any]) -> str:
    """
    Return the best available textual summary of the ad's *text content*.

    Priority:
    1) If LLM-enhanced summary exists: report["nlp"]["llm"]["enhanced_summary"]
    2) Else, fall back to a simple summary based on raw_text (first ~250 chars)

    This makes LLM enhancements effectively mandatory for any consumer
    that wants a summary: they will automatically use the LLM one when
    present, but the function still works if LLM is disabled.
    """
    nlp = _get_nlp_block(report)
    nlp_llm = nlp.get("llm") or {}
    if isinstance(nlp_llm, dict):
        enhanced = nlp_llm.get("enhanced_summary")
        if isinstance(enhanced, str) and enhanced.strip():
            return enhanced.strip()

    # Fallback: truncate raw_text
    raw = nlp.get("raw_text") or ""
    raw = str(raw)
    if len(raw) > 250:
        return raw[:250].rstrip() + "..."
    return raw.strip()


def get_persuasion_signals(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a merged view of persuasion / selling pressure indicators.

    Output structure:
    {
        "strong_phrases": [...],           # from classic NLP
        "manipulative_phrases": [...],     # from LLM if available
        "all_phrases": [...],              # deduped union of both
        "call_to_action_strength": "low"|"medium"|"high"|"unknown"
    }

    This is how we make LLM input *mandatory* for persuasion logic:
    - When LLM has added `manipulative_phrases` and
      `call_to_action_strength`, they dominate this view.
    - When not available, we still return something meaningful
      using only classical NLP.
    """
    nlp = _get_nlp_block(report)
    nlp_llm = nlp.get("llm") or {}

    strong_phrases = nlp.get("strong_phrases") or []
    if not isinstance(strong_phrases, list):
        strong_phrases = []

    manipulative = nlp_llm.get("manipulative_phrases") or []
    if not isinstance(manipulative, list):
        manipulative = []

    # Union with deduplication, preserve order: LLM phrases first
    all_phrases: List[str] = []
    seen = set()

    for p in manipulative + strong_phrases:
        if not isinstance(p, str):
            continue
        key = p.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        all_phrases.append(p.strip())

    cta_strength = nlp_llm.get("call_to_action_strength")
    if not isinstance(cta_strength, str) or not cta_strength.strip():
        # If LLM did not provide a strength, derive a rough one
        # from how many strong phrases we detected.
        count = len(strong_phrases)
        if count == 0:
            cta_strength = "unknown"
        elif count == 1:
            cta_strength = "low"
        elif count <= 3:
            cta_strength = "medium"
        else:
            cta_strength = "high"
    else:
        cta_strength = cta_strength.strip().lower()

    return {
        "strong_phrases": strong_phrases,
        "manipulative_phrases": manipulative,
        "all_phrases": all_phrases,
        "call_to_action_strength": cta_strength,
    }
# backend/nlp.py

def get_nlp_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract NLP insights (sentiment, emotion, strong phrases) from the report.
    """
    nlp_res = report.get("nlp", {})
    sentiment_label = nlp_res.get("sentiment", {}).get("label", "neutral")
    emotion_label = nlp_res.get("emotion", {}).get("label", "neutral")
    strong_phrases = nlp_res.get("strong_phrases", [])
    
    return {
        "sentiment": sentiment_label,
        "emotion": emotion_label,
        "strong_phrases": strong_phrases,
    }
