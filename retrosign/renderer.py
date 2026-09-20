"""Local Photofunia-style retro-wave renderer.

Composites bundled background artwork with three-line 80s type.
No network calls.
"""

from __future__ import annotations

import random
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

DATA = Path(__file__).resolve().parent / "data"
FONTS = DATA / "fonts"
BACKGROUNDS = DATA / "backgrounds"

BACKGROUND_IDS = (1, 2, 3, 4, 5)
STYLE_IDS = (1, 2, 3, 4)

BACKGROUND_NAMES = {
    1: "Wire triangles",
    2: "Sun and palms",
    3: "Sunset chevron",
    4: "Crystal prism",
    5: "Magenta sunburst",
}

STYLE_NAMES = {
    1: "Pink chrome",
    2: "Ice chrome",
    3: "Sunset chrome",
    4: "Violet chrome",
}

TEXT_STYLES: Dict[int, dict] = {
    1: {
        "outline": (255, 70, 180),
        "glow": (255, 40, 160),
        "chrome": [(0.0, (255, 255, 255)), (0.35, (230, 210, 255)), (0.55, (200, 90, 180)), (1.0, (90, 40, 120))],
        "bottom_outline": (90, 220, 255),
        "script_fill": (255, 90, 200),
        "script_outline": (255, 255, 255),
    },
    2: {
        "outline": (70, 220, 255),
        "glow": (40, 180, 255),
        "chrome": [(0.0, (255, 255, 255)), (0.38, (180, 230, 255)), (0.62, (80, 140, 220)), (1.0, (30, 50, 120))],
        "bottom_outline": (255, 90, 210),
        "script_fill": (120, 230, 255),
        "script_outline": (255, 255, 255),
    },
    3: {
        "outline": (255, 120, 80),
        "glow": (255, 80, 40),
        "chrome": [(0.0, (255, 255, 240)), (0.35, (255, 210, 160)), (0.6, (255, 90, 110)), (1.0, (120, 30, 70))],
        "bottom_outline": (255, 230, 120),
        "script_fill": (255, 140, 90),
        "script_outline": (255, 255, 255),
    },
    4: {
        "outline": (180, 90, 255),
        "glow": (140, 60, 255),
        "chrome": [(0.0, (255, 255, 255)), (0.32, (220, 200, 255)), (0.58, (140, 80, 220)), (1.0, (40, 20, 90))],
        "bottom_outline": (80, 255, 200),
        "script_fill": (210, 120, 255),
        "script_outline": (255, 255, 255),
    },
}


def _load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size=size)


@lru_cache(maxsize=8)
def load_background(bg_id: int) -> Image.Image:
    path = BACKGROUNDS / f"{bg_id}.jpg"
    if not path.exists():
        path = BACKGROUNDS / f"{bg_id}.png"
    return Image.open(path).convert("RGB")


def _vertical_gradient(
    size: Tuple[int, int],
    stops: Sequence[Tuple[float, Tuple[int, int, int]]],
) -> Image.Image:
    w, h = size
    stops = sorted(stops, key=lambda s: s[0])
    ys = np.linspace(0.0, 1.0, max(h, 1))
    cols = np.zeros((max(h, 1), 3), dtype=np.float32)
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        mask = (ys >= t0) & (ys <= (t1 if i < len(stops) - 2 else 1.0))
        span = (t1 - t0) or 1.0
        local = ((ys - t0) / span).clip(0, 1)
        for ch in range(3):
            cols[:, ch] = np.where(mask, c0[ch] + (c1[ch] - c0[ch]) * local, cols[:, ch])
    img = np.repeat(cols.astype(np.uint8)[:, None, :], max(w, 1), axis=1)
    return Image.fromarray(img, "RGB")


def _circle_offsets(radius: int):
    pts = []
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            if dx * dx + dy * dy <= radius * radius and (dx or dy):
                pts.append((dx, dy))
    return pts


def _fit_font(name: str, text: str, max_width: int, start: int, min_size: int = 18) -> ImageFont.FreeTypeFont:
    size = start
    font = _load_font(name, size)
    while size > min_size and font.getlength(text) > max_width:
        size -= 2
        font = _load_font(name, size)
    return font


def _text_mask(text: str, font: ImageFont.FreeTypeFont) -> Image.Image:
    dummy = Image.new("L", (4, 4), 0)
    d = ImageDraw.Draw(dummy)
    bbox = d.textbbox((0, 0), text, font=font)
    w, h = max(1, bbox[2] - bbox[0] + 8), max(1, bbox[3] - bbox[1] + 8)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((4 - bbox[0], 4 - bbox[1]), text, font=font, fill=255)
    return mask


def _chrome_text(text: str, font: ImageFont.FreeTypeFont, style: dict) -> Image.Image:
    mask = _text_mask(text, font)
    w, h = mask.size
    pad = 28
    canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    mpad = Image.new("L", canvas.size, 0)
    mpad.paste(mask, (pad, pad))

    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    glow.paste(Image.new("RGBA", canvas.size, (*style["glow"], 180)), mask=mpad)
    canvas = Image.alpha_composite(canvas, glow.filter(ImageFilter.GaussianBlur(12)))
    canvas = Image.alpha_composite(canvas, glow.filter(ImageFilter.GaussianBlur(18)))

    outline_col = Image.new("RGBA", canvas.size, (*style["outline"], 255))
    for dx, dy in _circle_offsets(7):
        shifted = Image.new("L", canvas.size, 0)
        shifted.paste(mpad, (dx, dy))
        canvas.paste(outline_col, mask=shifted)

    bevel = Image.new("RGBA", canvas.size, (*style["bottom_outline"], 220))
    for dx, dy in ((-3, 2), (-4, 3), (3, 2), (4, 3)):
        shifted = Image.new("L", canvas.size, 0)
        shifted.paste(mpad, (dx, dy))
        canvas.paste(bevel, mask=shifted)

    inner = Image.new("RGBA", canvas.size, (30, 10, 40, 255))
    for dx, dy in _circle_offsets(2):
        shifted = Image.new("L", canvas.size, 0)
        shifted.paste(mpad, (dx, dy))
        canvas.paste(inner, mask=shifted)

    grad = _vertical_gradient((w, h), style["chrome"]).convert("RGBA")
    gpad = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    gpad.paste(grad, (pad, pad))
    canvas.paste(gpad, mask=mpad)

    spec = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    spx = spec.load()
    for y in range(canvas.size[1]):
        ty = (y - pad) / max(h, 1)
        if 0.08 < ty < 0.28:
            a = int(160 * (1 - abs(ty - 0.16) / 0.12))
            for x in range(canvas.size[0]):
                spx[x, y] = (255, 255, 255, max(0, a))
    canvas = Image.alpha_composite(
        canvas,
        Image.composite(spec, Image.new("RGBA", canvas.size, (0, 0, 0, 0)), mpad),
    )
    return canvas


def _script_text(text: str, font: ImageFont.FreeTypeFont, style: dict, angle: float = -11.0) -> Image.Image:
    mask = _text_mask(text, font)
    w, h = mask.size
    pad = 24
    canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    mpad = Image.new("L", canvas.size, 0)
    mpad.paste(mask, (pad, pad))

    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    glow.paste(Image.new("RGBA", canvas.size, (*style["glow"], 140)), mask=mpad)
    canvas = Image.alpha_composite(canvas, glow.filter(ImageFilter.GaussianBlur(10)))

    outline = Image.new("RGBA", canvas.size, (*style["script_outline"], 255))
    for dx, dy in _circle_offsets(4):
        shifted = Image.new("L", canvas.size, 0)
        shifted.paste(mpad, (dx, dy))
        canvas.paste(outline, mask=shifted)

    fill = Image.new("RGBA", canvas.size, (*style["script_fill"], 255))
    canvas.paste(fill, mask=mpad)
    hi = Image.new("RGBA", canvas.size, (255, 255, 255, 90))
    canvas = Image.alpha_composite(
        canvas, Image.composite(hi, Image.new("RGBA", canvas.size, (0, 0, 0, 0)), mpad)
    )
    if angle:
        canvas = canvas.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    return canvas


def _bottom_text(text: str, font: ImageFont.FreeTypeFont, style: dict) -> Image.Image:
    mask = _text_mask(text, font)
    w, h = mask.size
    pad = 20
    canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    mpad = Image.new("L", canvas.size, 0)
    mpad.paste(mask, (pad, pad))

    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    glow.paste(Image.new("RGBA", canvas.size, (*style["bottom_outline"], 160)), mask=mpad)
    canvas = Image.alpha_composite(canvas, glow.filter(ImageFilter.GaussianBlur(8)))

    outline = Image.new("RGBA", canvas.size, (*style["bottom_outline"], 255))
    for dx, dy in _circle_offsets(4):
        shifted = Image.new("L", canvas.size, 0)
        shifted.paste(mpad, (dx, dy))
        canvas.paste(outline, mask=shifted)

    fill = _vertical_gradient((w, h), [(0.0, (255, 255, 255)), (1.0, (210, 230, 255))]).convert("RGBA")
    gpad = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    gpad.paste(fill, (pad, pad))
    canvas.paste(gpad, mask=mpad)
    return canvas


def resolve_ids(
    background: Optional[int],
    text_style: Optional[int],
    seed: Optional[int] = None,
) -> Tuple[int, int]:
    rng = random.Random(seed)
    bcg = background if background in BACKGROUND_IDS else rng.choice(list(BACKGROUND_IDS))
    txt = text_style if text_style in STYLE_IDS else rng.choice(list(STYLE_IDS))
    return bcg, txt


def render_retrosign(
    text1: str,
    text2: str,
    text3: str,
    background: Optional[int] = None,
    text_style: Optional[int] = None,
    seed: Optional[int] = None,
) -> BytesIO:
    bcg, txt = resolve_ids(background, text_style, seed)
    style = TEXT_STYLES[txt]
    base = load_background(bcg).copy()
    W, H = base.size
    sky = base.convert("RGBA")

    chrome = script = bottom = None
    if text1:
        f1 = _fit_font("Pacifico-Regular.ttf", text1, int(W * 0.72), 110, 36)
        script = _script_text(text1, f1, style, -11)
    if text2:
        f2 = _fit_font("PassionOne-Bold.ttf", text2.upper(), int(W * 0.90), 196, 48)
        chrome = _chrome_text(text2.upper(), f2, style)
    if text3:
        f3 = _fit_font("Montserrat-BlackItalic.ttf", text3.upper(), int(W * 0.76), 72, 28)
        bottom = _bottom_text(text3.upper(), f3, style)

    cy = int(H * 0.38)
    if chrome:
        x = (W - chrome.width) // 2
        y = cy - chrome.height // 2
        sky.alpha_composite(chrome, (x, max(0, y)))
        chrome_box = (x, max(0, y), x + chrome.width, max(0, y) + chrome.height)
    else:
        chrome_box = (W // 2, cy, W // 2, cy)

    if script:
        x = max(0, (W - script.width) // 2 - 36)
        y = max(0, chrome_box[1] - script.height // 2 + 28)
        sky.alpha_composite(script, (x, y))

    if bottom:
        x = min(W - bottom.width, max(0, (W - bottom.width) // 2 + 80))
        y = min(H - bottom.height, max(0, chrome_box[3] - int(bottom.height * 0.70)))
        sky.alpha_composite(bottom, (x, y))

    buf = BytesIO()
    sky.convert("RGB").save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


def render_gallery_sheet(sample: Tuple[str, str, str] = ("Retro", "SIGN", "LOCAL")) -> BytesIO:
    thumbs: List[Image.Image] = []
    label_font = _load_font("Montserrat-Black.ttf", 22)
    for bcg in BACKGROUND_IDS:
        img = Image.open(render_retrosign(*sample, background=bcg, text_style=1, seed=1)).convert("RGB")
        img = img.resize((400, 267), Image.Resampling.LANCZOS)
        d = ImageDraw.Draw(img)
        tag = f"{bcg}  {BACKGROUND_NAMES[bcg]}"
        d.rectangle((8, 8, 8 + d.textlength(tag, font=label_font) + 16, 40), fill=(20, 8, 40))
        d.text((16, 12), tag, font=label_font, fill=(255, 210, 255))
        thumbs.append(img)
    pad = 12
    sheet = Image.new("RGB", (400 * 5 + pad * 6, 267 + pad * 2), (18, 8, 36))
    for i, th in enumerate(thumbs):
        sheet.paste(th, (pad + i * (400 + pad), pad))
    buf = BytesIO()
    sheet.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


def render_style_sheet(sample: Tuple[str, str, str] = ("Retro", "SIGN", "LOCAL")) -> BytesIO:
    thumbs: List[Image.Image] = []
    label_font = _load_font("Montserrat-Black.ttf", 22)
    for st in STYLE_IDS:
        img = Image.open(render_retrosign(*sample, background=1, text_style=st, seed=1)).convert("RGB")
        img = img.resize((480, 320), Image.Resampling.LANCZOS)
        d = ImageDraw.Draw(img)
        tag = f"{st}  {STYLE_NAMES[st]}"
        d.rectangle((8, 8, 8 + d.textlength(tag, font=label_font) + 16, 40), fill=(20, 8, 40))
        d.text((16, 12), tag, font=label_font, fill=(255, 210, 255))
        thumbs.append(img)
    pad = 12
    sheet = Image.new("RGB", (480 * 2 + pad * 3, 320 * 2 + pad * 3), (18, 8, 36))
    for i, th in enumerate(thumbs):
        sheet.paste(th, (pad + (i % 2) * (480 + pad), pad + (i // 2) * (320 + pad)))
    buf = BytesIO()
    sheet.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf
