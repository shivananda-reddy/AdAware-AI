#!/usr/bin/env python3
"""
make_icons.py

Generate simple extension icons for AdAware AI.

Outputs:
  icons/icon16.png
  icons/icon32.png
  icons/icon48.png
  icons/icon128.png
"""

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


# ------------ Config ------------
SIZES = [16, 32, 48, 128]

BG_START = (31, 41, 91)   # dark indigo
BG_END   = (79, 70, 229)  # indigo 600
TEXT_COLOR = (248, 250, 252)  # white-ish

TEXT = "A"   # icon glyph

FONT_NAME_CANDIDATES = [
    "Inter-Bold.ttf",
    "Inter.ttf",
    "Segoe UI Bold.ttf",
    "Segoe UI.ttf",
    "Arial Bold.ttf",
    "Arial.ttf",
]


def find_font(size: int) -> ImageFont.FreeTypeFont:
    """Try to load a decent font; fallback if none found."""
    for name in FONT_NAME_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def gradient_bg(size: int) -> Image.Image:
    """Vertical gradient background."""
    img = Image.new("RGB", (size, size), BG_START)
    draw = ImageDraw.Draw(img)
    for y in range(size):
        t = y / max(1, size - 1)
        r = int(BG_START[0] + t * (BG_END[0] - BG_START[0]))
        g = int(BG_START[1] + t * (BG_END[1] - BG_START[1]))
        b = int(BG_START[2] + t * (BG_END[2] - BG_START[2]))
        draw.line([(0, y), (size, y)], fill=(r, g, b))
    return img


def get_text_size(draw, text, font):
    """Compatible text measurement across Pillow versions."""
    try:
        # New method (Pillow ≥ 8.0)
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        return w, h
    except Exception:
        try:
            # Old fallback
            return draw.textsize(text, font=font)
        except Exception:
            return (font.getsize(text)[0], font.getsize(text)[1])


def draw_icon(size: int) -> Image.Image:
    img = gradient_bg(size).convert("RGBA")
    draw = ImageDraw.Draw(img)

    # Rounded border
    padding = max(1, size // 16)
    radius = max(3, size // 4)
    border_color = (255, 255, 255, 40)

    try:
        draw.rounded_rectangle(
            [padding, padding, size - padding, size - padding],
            radius=radius,
            outline=border_color,
            width=max(1, size // 32)
        )
    except:
        pass

    # Text
    font_size = int(size * 0.65)
    font = find_font(font_size)
        # text_w, text_h = draw.textsize(TEXT, font=font)
    # Replacement for Pillow >= 10:
    left, top, right, bottom = draw.textbbox((0, 0), TEXT, font=font)
    text_w = right - left
    text_h = bottom - top

    x = (size - text_w) / 2
    y = (size - text_h) / 2 - size * 0.05

    draw.text((x, y), TEXT, fill=TEXT_COLOR, font=font)

    return img


def main():
    root = Path(__file__).resolve().parent
    icons_dir = root / "icons"
    icons_dir.mkdir(exist_ok=True)

    for s in SIZES:
        img = draw_icon(s)
        out_path = icons_dir / f"icon{s}.png"
        img.save(out_path, format="PNG")
        print(f"Created: {out_path}")

    print("\nAll icons generated successfully!")


if __name__ == "__main__":
    main()
