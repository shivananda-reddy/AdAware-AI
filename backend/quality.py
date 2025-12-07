# backend/quality.py
"""
Image quality / blur detection utilities for AdAware AI.

We estimate blur using variance of Laplacian:
- Sharp images -> large variance
- Blurry images -> low variance

Returns:
    {
        "blur_score": float,
        "is_blurry": bool
    }
"""

from typing import Dict
from PIL import Image, ImageOps
import numpy as np


def _laplacian_variance(gray_arr: np.ndarray) -> float:
    """
    Compute variance of Laplacian (simple 3x3 kernel).
    gray_arr: 2D float32 array.
    """
    # 3x3 Laplacian kernel
    kernel = np.array(
        [
            [0.0,  1.0, 0.0],
            [1.0, -4.0, 1.0],
            [0.0,  1.0, 0.0],
        ],
        dtype=np.float32,
    )

    h, w = gray_arr.shape
    # pad by 1 pixel on all sides
    padded = np.pad(gray_arr, 1, mode="edge")

    lap = np.zeros_like(gray_arr, dtype=np.float32)

    # manual convolution (slow but fine for single images)
    for i in range(h):
        for j in range(w):
            region = padded[i:i+3, j:j+3]
            lap[i, j] = np.sum(region * kernel)

    var = float(lap.var())
    return var


def estimate_blur(pil_image: Image.Image) -> Dict[str, float]:
    """
    Estimate how blurry the image is.

    Returns:
        {
            "blur_score": float,   # variance of Laplacian
            "is_blurry": bool      # True if below threshold
        }
    """
    if pil_image is None:
        return {"blur_score": 0.0, "is_blurry": False}

    # Convert to grayscale and downscale a bit for speed
    gray = ImageOps.grayscale(pil_image)

    # Downscale large images to ~800px on the long side to speed up
    w, h = gray.size
    max_side = max(w, h)
    if max_side > 800:
        scale = 800.0 / max_side
        gray = gray.resize((int(w * scale), int(h * scale)), Image.BICUBIC)

    arr = np.array(gray, dtype=np.float32)

    score = _laplacian_variance(arr)

    # Threshold: tune as you like (50–150 range is common)
    # Lower score => more blurry
    BLUR_THRESHOLD = 80.0
    is_blurry = score < BLUR_THRESHOLD

    return {
        "blur_score": score,
        "is_blurry": is_blurry,
    }
