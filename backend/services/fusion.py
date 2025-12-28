# backend/fusion.py
"""
Fusion utilities: compute similarity between image content and text.

Provides:
- compute_image_text_similarity(pil_image, text) -> float in [0, 1]

Implementation strategy:
- Try to use CLIP (via HuggingFace transformers + torch) for a real
  vision-text similarity score.
- If CLIP or its dependencies are not available, fall back to a
  simple heuristic based on text length and presence of typical ad words,
  so the pipeline never fully breaks.

This function is called from main.py and its output is used in:
- explanation (to judge consistency),
- credibility scoring,
- trust hints.

Hybrid Option C (LLM-aware fusion view):

The llm module may later attach a block:

    report["fusion_llm"] = {
        "overall_consistency": "consistent" | "partially_consistent" | "inconsistent",
        "consistency_score": 0..1,
        "reasoning": "..."
    }

This file exposes a helper:

    get_fusion_consistency_view(report) -> Dict[str, Any]

which merges:
    - classic image_text_similarity,
    - optional image_quality blur info,
    - fusion_llm (if present)

into a final fused consistency view used by explain.py / UI.
"""

from __future__ import annotations

from typing import Optional, Dict, Any
import logging

from PIL import Image

LOG = logging.getLogger("adaware.fusion")

import os
ADAWARE_HF_OFFLINE = os.environ.get("ADAWARE_HF_OFFLINE", "0") == "1"
ADAWARE_DISABLE_CLIP = os.environ.get("ADAWARE_DISABLE_CLIP", "0") == "1"

# ---------------------------------------------------------------------
# Try to load CLIP model via transformers
# ---------------------------------------------------------------------
_HAS_CLIP = False
_CLIP_MODEL = None
_CLIP_PROCESSOR = None

try:
    from transformers import CLIPModel, CLIPProcessor  # type: ignore
    import torch  # type: ignore

    _HAS_CLIP = True
    LOG.info("Transformers & torch found; CLIP-based similarity will be used.")
except Exception as e:  # pragma: no cover
    LOG.warning(
        "CLIP / transformers / torch not available. "
        "Image-text similarity will fall back to a simple heuristic. Error: %s",
        e,
    )
    _HAS_CLIP = False


_CLIP_MODEL = None
_CLIP_PROCESSOR = None
_CLIP_LOAD_FAILED = False

def get_clip_model():
    global _CLIP_MODEL, _CLIP_LOAD_FAILED
    if ADAWARE_DISABLE_CLIP:
        return None
    if _CLIP_LOAD_FAILED:
        return None
    if _CLIP_MODEL:
        return _CLIP_MODEL
    
    try:
        LOG.info("Loading CLIP model...")
        kwargs = {"local_files_only": True} if ADAWARE_HF_OFFLINE else {}
        _CLIP_MODEL = CLIPModel.from_pretrained("openai/clip-vit-base-patch32", **kwargs)
        LOG.info("✓ CLIP model loaded successfully")
        return _CLIP_MODEL
    except Exception as e:
        LOG.warning(f"✗ Failed to load CLIP model (Offline={ADAWARE_HF_OFFLINE}): {e}")
        LOG.info("Image-text similarity will be unavailable")
        _CLIP_LOAD_FAILED = True
        return None

def get_clip_processor():
    global _CLIP_PROCESSOR, _CLIP_LOAD_FAILED
    if ADAWARE_DISABLE_CLIP or _CLIP_LOAD_FAILED:
        return None
    if _CLIP_PROCESSOR:
        return _CLIP_PROCESSOR

    try:
        kwargs = {"local_files_only": True} if ADAWARE_HF_OFFLINE else {}
        _CLIP_PROCESSOR = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32", **kwargs)
        return _CLIP_PROCESSOR
    except Exception as e:
        LOG.warning(f"Failed to load CLIP processor: {e}")
        _CLIP_LOAD_FAILED = TrueOR = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32", **kwargs)
        return _CLIP_PROCESSOR
    except Exception:
        return None

def _clip_similarity(pil_image: Image.Image, text: str) -> Optional[float]:
    """
    Compute similarity using CLIP, normalized to [0, 1].

    Returns:
        float in [0,1] or None on failure.
    """
    if not _HAS_CLIP:
        return None

    model = get_clip_model()
    processor = _CLIP_PROCESSOR
    if model is None or processor is None:
        return None

    if not isinstance(pil_image, Image.Image):
        return None

    if pil_image.mode not in ("RGB", "RGBA"):
        pil_image = pil_image.convert("RGB")

    text = (text or "").strip()
    if not text:
        return 0.0

    try:
        inputs = processor(
            text=[text],
            images=[pil_image],
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=77,
        )
        with torch.no_grad():
            outputs = model(**inputs)
            # logits_per_image shape: [batch_size, num_texts]
            logits_per_image = outputs.logits_per_image
            # For single image-text pair, take [0,0]
            logit = logits_per_image[0, 0].item()
            # Map logit to [0, 1] using sigmoid
            sim = float(torch.sigmoid(torch.tensor(logit)).item())
            # clip just in case
            sim = max(0.0, min(1.0, sim))
            return sim
    except Exception as e:
        LOG.error("CLIP similarity computation failed: %s", e)
        return None


# ---------------------------------------------------------------------
# Heuristic fallback
# ---------------------------------------------------------------------
_AD_WORDS = [
    "sale", "discount", "offer", "deal", "limited", "buy", "shop",
    "order", "now", "free", "gift", "bonus", "exclusive",
]


def _heuristic_similarity(text: str) -> float:
    """
    Simple text-only heuristic used when CLIP is unavailable.

    - If text is empty -> 0.0
    - If text is very short (< 10 chars) -> 0.15
    - If contains many ad words -> up to ~0.7
    - Otherwise moderate ~0.4
    """
    t = (text or "").strip().lower()
    if not t:
        return 0.0

    length = len(t)
    if length < 10:
        base = 0.15
    elif length < 40:
        base = 0.3
    else:
        base = 0.4

    # Count ad words
    hits = sum(1 for w in _AD_WORDS if w in t)
    bonus = min(hits * 0.05, 0.3)  # up to +0.3

    score = base + bonus
    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------
def compute_image_text_similarity(pil_image: Optional[Image.Image], text: str) -> float:
    """
    Main function used by main.py.

    Returns:
        similarity score in [0, 1]

    Logic:
        - If CLIP is available and image+text exist -> CLIP-based score.
        - Otherwise -> heuristic score based only on text.
    """
    if pil_image is None:
        # We still return a heuristic score from text only
        return _heuristic_similarity(text)

    # Try CLIP first
    sim = _clip_similarity(pil_image, text)
    if sim is not None:
        return sim

    # Fallback
    # If CLIP/Visual analysis failed but we have an image, return None 
    # to indicate "Unavailable" rather than a weak heuristic guess.
    return None


# ---------------------------------------------------------------------
# Hybrid Option C: LLM-aware fusion consistency view
# ---------------------------------------------------------------------

def _infer_consistency_from_similarity(image_text_sim: float) -> str:
    """
    Infer a coarse consistency label from the raw similarity score.

    Used when LLM did not provide fusion_llm or consistency_score.
    """
    try:
        s = float(image_text_sim)
    except Exception:
        s = 0.0

    if s >= 0.7:
        return "consistent"
    if s >= 0.35:
        return "partially_consistent"
    return "inconsistent"


def get_fusion_consistency_view(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a unified, LLM-aware view of image-text consistency.

    This is where Hybrid Option C makes LLM help with fusion:

    - Uses classic `image_text_similarity` from this module.
    - Incorporates `image_quality.blur_score` (if present) to slightly
      downweight confidence when the image is very blurry.
    - If `report["fusion_llm"]` exists (added by llm.maybe_enhance_with_llm),
      it uses its `consistency_score` and `overall_consistency` as the
      primary signal, blended with the classic similarity.

    Output structure:
    {
        "image_text_similarity": float,          # raw 0..1
        "blur_score": float or None,            # optional
        "consistency_score_llm": float or None, # 0..1 or None
        "consistency_score_final": float,       # 0..1 fused
        "overall_consistency_llm": str or None, # "consistent" etc
        "overall_consistency_inferred": str,    # from image_text_similarity
        "overall_consistency_final": str,       # final label we recommend
        "reasoning": str,                       # LLM reasoning if present, else heuristic
    }
    """
    if not isinstance(report, dict):
        return {
            "image_text_similarity": 0.0,
            "blur_score": None,
            "consistency_score_llm": None,
            "consistency_score_final": 0.0,
            "overall_consistency_llm": None,
            "overall_consistency_inferred": "inconsistent",
            "overall_consistency_final": "inconsistent",
            "reasoning": "",
        }

    # Raw similarity
    image_text_sim = report.get("image_text_similarity", 0.0)
    try:
        image_text_sim_f = float(image_text_sim)
    except Exception:
        image_text_sim_f = 0.0

    # Blur info (optional)
    image_quality = report.get("image_quality") or {}
    if not isinstance(image_quality, dict):
        image_quality = {}
    blur_score = image_quality.get("blur_score")
    try:
        blur_score_f = float(blur_score) if blur_score is not None else None
    except Exception:
        blur_score_f = None

    # LLM fusion block
    fusion_llm = report.get("fusion_llm") or {}
    if not isinstance(fusion_llm, dict):
        fusion_llm = {}

    consistency_score_llm = fusion_llm.get("consistency_score")
    try:
        consistency_score_llm_f = float(consistency_score_llm) if consistency_score_llm is not None else None
    except Exception:
        consistency_score_llm_f = None

    overall_consistency_llm = fusion_llm.get("overall_consistency")
    if isinstance(overall_consistency_llm, str) and overall_consistency_llm.strip():
        overall_consistency_llm = overall_consistency_llm.strip().lower()
    else:
        overall_consistency_llm = None

    reasoning_llm = fusion_llm.get("reasoning")
    if not isinstance(reasoning_llm, str):
        reasoning_llm = None

    # Inferred consistency from classic similarity
    inferred_consistency = _infer_consistency_from_similarity(image_text_sim_f)

    # Blend LLM score with classic similarity when available
    if consistency_score_llm_f is not None:
        # If image is very blurry, downweight both a bit
        blur_penalty = 0.0
        if blur_score_f is not None and blur_score_f > 0.7:
            blur_penalty = 0.1

        fused_score = max(
            0.0,
            min(
                1.0,
                0.7 * consistency_score_llm_f + 0.3 * image_text_sim_f - blur_penalty,
            ),
        )
    else:
        # No LLM -> just use similarity, maybe penalize if blurry
        fused_score = image_text_sim_f
        if blur_score_f is not None and blur_score_f > 0.7:
            fused_score = max(0.0, fused_score - 0.1)

    # Decide final consistency label
    fused_consistency_label = overall_consistency_llm or _infer_consistency_from_similarity(fused_score)

    # Reasoning: prefer LLM if provided, otherwise generate a short heuristic explanation
    if reasoning_llm:
        reasoning = reasoning_llm
    else:
        parts = []
        parts.append(f"Image–text similarity is about {image_text_sim_f:.2f}.")
        if blur_score_f is not None:
            parts.append(f"Image blur score is {blur_score_f:.2f}, which affects how reliable visual matching is.")
        parts.append(f"Overall this suggests the ad is {fused_consistency_label.replace('_', ' ')}.")
        reasoning = " ".join(parts)

    return {
        "image_text_similarity": image_text_sim_f,
        "blur_score": blur_score_f,
        "consistency_score_llm": consistency_score_llm_f,
        "consistency_score_final": fused_score,
        "overall_consistency_llm": overall_consistency_llm,
        "overall_consistency_inferred": inferred_consistency,
        "overall_consistency_final": fused_consistency_label,
        "reasoning": reasoning,
    }
