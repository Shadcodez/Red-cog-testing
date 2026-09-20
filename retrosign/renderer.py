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
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

DATA = Path(__file__).resolve().parent / "data"
FONTS = DATA / "fonts"
BACKGROUNDS = DATA / "backgrounds"

BACKGROUND_IDS = (1, 2, 3, 4, 5)
STYLE_IDS = (1, 2, 3, 4)

BACKGROUND_NAMES = {
    1: "Inverted neon triangle",
    2: "Crystal pyramid",
    3: "Rainbow prism",
    4: "Sunset palms",
    5: "Sun and palms",
}

STYLE_NAMES = {
    1: "Pink chrome",
    2: "Ice chrome",
    3: "Magenta chrome",
    4: "Steel chrome",
}

# Palettes reverse-engineered from Photofunia's public style thumbs
# (eye191, 1xxre9n, 9ddnhx, dlxine) — our own strokes, not their files.
TEXT_STYLES: Dict[int, dict] = {
    1: {  # pink chrome
        "stroke_a": (255, 64, 168),
        "stroke_b": (255, 110, 200),
        "stroke_off_a": (-2, 2),
        "stroke_off_b": (3, -1),
        "inner": (36, 8, 48),
        "glow": (255, 40, 160),
        "chrome": [
            (0.00, (255, 255, 255)),
            (0.18, (255, 255, 255)),
            (0.34, (236, 214, 255)),
            (0.52, (214, 120, 196)),
            (0.78, (128, 48, 130)),
            (1.00, (62, 18, 78)),
        ],
        "bottom_outline": (80, 220, 255),
        "script_fill": (255, 78, 196),
        "script_outline": (255, 255, 255),
    },
    2: {  # ice chrome
        "stroke_a": (64, 214, 255),
        "stroke_b": (190, 240, 255),
        "stroke_off_a": (-2, 2),
        "stroke_off_b": (3, -1),
        "inner": (16, 36, 64),
        "glow": (50, 180, 255),
        "chrome": [
            (0.00, (255, 255, 255)),
            (0.20, (230, 248, 255)),
            (0.42, (168, 220, 255)),
            (0.64, (186, 168, 255)),
            (0.84, (232, 150, 214)),
            (1.00, (120, 70, 160)),
        ],
        "bottom_outline": (255, 90, 200),
        "script_fill": (110, 230, 255),
        "script_outline": (255, 255, 255),
    },
    3: {  # magenta chrome
        "stroke_a": (255, 70, 170),
        "stroke_b": (255, 140, 210),
        "stroke_off_a": (-2, 2),
        "stroke_off_b": (3, -1),
        "inner": (48, 10, 40),
        "glow": (255, 50, 150),
        "chrome": [
            (0.00, (255, 255, 255)),
            (0.22, (255, 236, 248)),
            (0.48, (236, 176, 214)),
            (0.72, (200, 96, 168)),
            (1.00, (96, 32, 80)),
        ],
        "bottom_outline": (80, 220, 255),
        "script_fill": (255, 86, 186),
        "script_outline": (255, 255, 255),
    },
    4: {  # steel chrome — cyan + magenta bevel, silver to black
        "stroke_a": (64, 220, 255),
        "stroke_b": (255, 78, 196),
        "stroke_off_a": (-3, 2),
        "stroke_off_b": (3, -1),
        "inner": (18, 16, 28),
        "glow": (180, 80, 220),
        "chrome": [
            (0.00, (255, 255, 255)),
            (0.16, (255, 255, 255)),
            (0.30, (214, 214, 224)),
            (0.50, (140, 140, 154)),
            (0.72, (58, 58, 70)),
            (1.00, (12, 12, 18)),
        ],
        "bottom_outline": (80, 220, 255),
        "script_fill": (255, 78, 196),
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


def _dilate(mask: Image.Image, radius: int) -> Image.Image:
    if radius <= 0:
        return mask
    size = radius * 2 + 1
    if size % 2 == 0:
        size += 1
    return mask.filter(ImageFilter.MaxFilter(size))


def _shift(mask: Image.Image, dx: int, dy: int) -> Image.Image:
    out = Image.new("L", mask.size, 0)
    out.paste(mask, (dx, dy))
    return out


def _fit_font(name: str, text: str, max_width: int, start: int, min_size: int = 18) -> ImageFont.FreeTypeFont:
    size = start
    font = _load_font(name, size)
    while size > min_size and font.getlength(text) > max_width:
        size -= 2
        font = _load_font(name, size)
    return font


def _text_mask(text: str, font: ImageFont.FreeTypeFont, tracking: int = 0) -> Image.Image:
    dummy = Image.new("L", (4, 4), 0)
    d = ImageDraw.Draw(dummy)
    if tracking == 0:
        bbox = d.textbbox((0, 0), text, font=font)
        w, h = max(1, bbox[2] - bbox[0] + 8), max(1, bbox[3] - bbox[1] + 8)
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).text((4 - bbox[0], 4 - bbox[1]), text, font=font, fill=255)
        return mask
    x = 4
    glyphs = []
    max_h = 1
    for ch in text:
        bb = d.textbbox((0, 0), ch, font=font)
        gw, gh = bb[2] - bb[0], bb[3] - bb[1]
        glyphs.append((ch, bb, gw, gh))
        max_h = max(max_h, gh + 8)
        x += max(gw, 1) + tracking
    mask = Image.new("L", (max(1, x + 8), max_h), 0)
    md = ImageDraw.Draw(mask)
    x = 4
    for ch, bb, gw, gh in glyphs:
        md.text((x - bb[0], 4 - bb[1]), ch, font=font, fill=255)
        x += max(gw, 1) + tracking
    return mask


def _layer_color(size, color, mask, alpha=255) -> Image.Image:
    layer = Image.new("RGBA", size, (*color, alpha))
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    out.paste(layer, mask=mask)
    return out


def _chrome_text(text: str, font: ImageFont.FreeTypeFont, style: dict) -> Image.Image:
    mask = _text_mask(text, font, tracking=-3)
    w, h = mask.size
    pad = 36
    size = (w + pad * 2, h + pad * 2)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    core = Image.new("L", size, 0)
    core.paste(mask, (pad, pad))

    glow_m = _dilate(core, 10).filter(ImageFilter.GaussianBlur(14))
    canvas = Image.alpha_composite(canvas, _layer_color(size, style["glow"], glow_m, 150))
    glow_m2 = _dilate(core, 4).filter(ImageFilter.GaussianBlur(6))
    canvas = Image.alpha_composite(canvas, _layer_color(size, style["glow"], glow_m2, 90))

    outer = _dilate(core, 8)
    oa_x, oa_y = style["stroke_off_a"]
    ob_x, ob_y = style["stroke_off_b"]
    a_mask = _shift(outer, oa_x, oa_y)
    b_mask = _shift(outer, ob_x, ob_y)
    canvas.paste(_layer_color(size, style["stroke_a"], a_mask), (0, 0), a_mask)
    canvas.paste(_layer_color(size, style["stroke_b"], b_mask), (0, 0), b_mask)

    inner = _dilate(core, 3)
    canvas.paste(_layer_color(size, style["inner"], inner), (0, 0), inner)

    grad = _vertical_gradient((w, h), style["chrome"]).convert("RGBA")
    gpad = Image.new("RGBA", size, (0, 0, 0, 0))
    gpad.paste(grad, (pad, pad))
    canvas.paste(gpad, mask=core)

    # hard specular band across the upper third (Photofunia chrome "shine")
    ys = (np.arange(size[1]) - pad) / max(h, 1)
    alpha = np.zeros(size[1], dtype=np.float32)
    band1 = (ys > 0.06) & (ys < 0.22)
    alpha[band1] = 200.0 * (1.0 - np.abs(ys[band1] - 0.13) / 0.10)
    band2 = (ys > 0.22) & (ys < 0.30)
    alpha[band2] = 70.0 * (1.0 - (ys[band2] - 0.22) / 0.08)
    alpha = np.clip(alpha, 0, 255).astype(np.uint8)
    spec_arr = np.zeros((size[1], size[0], 4), dtype=np.uint8)
    spec_arr[..., 0] = 255
    spec_arr[..., 1] = 255
    spec_arr[..., 2] = 255
    spec_arr[..., 3] = alpha[:, None]
    spec = Image.fromarray(spec_arr, "RGBA")
    canvas = Image.alpha_composite(
        canvas, Image.composite(spec, Image.new("RGBA", size, (0, 0, 0, 0)), core)
    )

    # top-edge bevel highlight
    top_edge = ImageChops.subtract(core, _shift(core, 0, 3))
    canvas = Image.alpha_composite(canvas, _layer_color(size, (255, 255, 255), top_edge, 140))
    return canvas


def _script_text(text: str, font: ImageFont.FreeTypeFont, style: dict, angle: float = -12.0) -> Image.Image:
    mask = _text_mask(text, font)
    w, h = mask.size
    pad = 28
    size = (w + pad * 2, h + pad * 2)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    core = Image.new("L", size, 0)
    core.paste(mask, (pad, pad))

    glow = _dilate(core, 6).filter(ImageFilter.GaussianBlur(8))
    canvas = Image.alpha_composite(canvas, _layer_color(size, style["script_fill"], glow, 120))

    outline = _dilate(core, 5)
    canvas.paste(_layer_color(size, style["script_outline"], outline), (0, 0), outline)
    inner = _dilate(core, 2)
    canvas.paste(_layer_color(size, (255, 220, 240), inner), (0, 0), inner)
    canvas.paste(_layer_color(size, style["script_fill"], core), (0, 0), core)

    hi = ImageChops.subtract(core, _shift(core, 0, 2))
    canvas = Image.alpha_composite(canvas, _layer_color(size, (255, 255, 255), hi, 90))
    if angle:
        canvas = canvas.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    return canvas


def _bottom_text(text: str, font: ImageFont.FreeTypeFont, style: dict) -> Image.Image:
    mask = _text_mask(text, font, tracking=2)
    w, h = mask.size
    pad = 22
    size = (w + pad * 2, h + pad * 2)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    core = Image.new("L", size, 0)
    core.paste(mask, (pad, pad))

    glow = _dilate(core, 5).filter(ImageFilter.GaussianBlur(7))
    canvas = Image.alpha_composite(canvas, _layer_color(size, style["bottom_outline"], glow, 140))

    outline = _dilate(core, 4)
    canvas.paste(_layer_color(size, style["bottom_outline"], outline), (0, 0), outline)
    fill = _vertical_gradient((w, h), [(0.0, (255, 255, 255)), (1.0, (226, 236, 255))]).convert("RGBA")
    gpad = Image.new("RGBA", size, (0, 0, 0, 0))
    gpad.paste(fill, (pad, pad))
    canvas.paste(gpad, mask=core)
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
        f1 = _fit_font("Pacifico-Regular.ttf", text1, int(W * 0.72), 118, 36)
        script = _script_text(text1, f1, style, -12)
    if text2:
        f2 = _fit_font("Anton-Regular.ttf", text2.upper(), int(W * 0.92), 210, 48)
        chrome = _chrome_text(text2.upper(), f2, style)
    if text3:
        f3 = _fit_font("Oswald-Bold.ttf", text3.upper(), int(W * 0.78), 82, 28)
        bottom = _bottom_text(text3.upper(), f3, style)
        # Official bottom line is a slight italic condensed grotesque
        bottom = bottom.transform(
            bottom.size,
            Image.Transform.AFFINE,
            (1, -0.18, 20, 0, 1, 0),
            resample=Image.Resampling.BICUBIC,
        )

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
