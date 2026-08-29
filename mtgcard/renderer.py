"""High-quality Magic-style card compositor.

Renders at 750×1050 (2.5\"×3.5\" @ 300 DPI). Two frame engines:

* painted — original M15-inspired procedural chrome (default, consistent)
* scan    — user's PNG templates, with art-window auto-detection

Fan-made unofficial cards. Not affiliated with Wizards of the Coast.
"""

from __future__ import annotations

import io
import math
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

CARD_W, CARD_H = 750, 1050

# Layout in pixels at the output resolution (M15-ish proportions).
MARGIN = 28
NAME_TOP = 38
NAME_H = 52
ART_TOP = 98
ART_H = 470
TYPE_TOP = 578
TYPE_H = 42
TEXT_TOP = 632
TEXT_BOTTOM = 968
PT_W, PT_H = 118, 46
STAMP_R = 16

ASSETS = Path(__file__).resolve().parent
FONTS_DIR = ASSETS / "fonts"
TEMPLATES_DIR = ASSETS / "templates"
MANA_DIR = ASSETS / "mana"
_PIP_CACHE: Dict[Tuple[str, int], Image.Image] = {}

_FONT_CACHE: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}

# ── Frame palettes ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FramePalette:
    key: str
    label: str
    emoji: str
    description: str
    frame_dark: Tuple[int, int, int]
    frame_mid: Tuple[int, int, int]
    frame_light: Tuple[int, int, int]
    plate: Tuple[int, int, int]
    plate_edge: Tuple[int, int, int]
    text_box: Tuple[int, int, int]
    title: Tuple[int, int, int]
    body: Tuple[int, int, int]
    accent: Tuple[int, int, int]
    pt_fill: Tuple[int, int, int]


PALETTES: Dict[str, FramePalette] = {
    "white": FramePalette(
        "white", "White", "⬜", "Plains / white frame",
        (168, 150, 110), (214, 198, 152), (236, 226, 190),
        (244, 236, 210), (196, 176, 128), (236, 226, 196),
        (28, 22, 12), (32, 26, 16), (196, 168, 72), (236, 220, 170),
    ),
    "blue": FramePalette(
        "blue", "Blue", "🟦", "Island / blue frame",
        (46, 88, 132), (92, 148, 188), (154, 196, 222),
        (198, 220, 232), (110, 150, 184), (210, 226, 234),
        (16, 24, 36), (20, 28, 40), (72, 140, 188), (186, 214, 230),
    ),
    "black": FramePalette(
        "black", "Black", "⬛", "Swamp / black frame",
        (28, 24, 28), (58, 50, 56), (92, 80, 86),
        (78, 70, 74), (40, 34, 36), (86, 78, 80),
        (236, 228, 214), (228, 220, 206), (140, 108, 72), (64, 56, 58),
    ),
    "red": FramePalette(
        "red", "Red", "🟥", "Mountain / red frame",
        (112, 42, 28), (176, 78, 48), (214, 126, 86),
        (232, 196, 168), (168, 92, 62), (236, 210, 186),
        (28, 14, 10), (32, 16, 12), (196, 86, 42), (224, 176, 140),
    ),
    "green": FramePalette(
        "green", "Green", "🟩", "Forest / green frame",
        (36, 68, 32), (74, 118, 58), (126, 164, 86),
        (198, 210, 164), (96, 128, 72), (214, 220, 180),
        (16, 24, 12), (20, 28, 14), (86, 140, 58), (186, 200, 150),
    ),
    "gold": FramePalette(
        "gold", "Gold", "🟨", "Multicolor / gold frame",
        (128, 92, 28), (196, 150, 48), (232, 198, 86),
        (236, 214, 150), (176, 136, 52), (236, 220, 168),
        (28, 20, 8), (32, 22, 10), (196, 148, 36), (228, 196, 110),
    ),
    "artifact": FramePalette(
        "artifact", "Artifact", "⚙️", "Colorless / artifact frame",
        (86, 82, 74), (150, 144, 132), (198, 192, 178),
        (210, 204, 190), (128, 122, 110), (216, 210, 196),
        (24, 22, 18), (28, 26, 22), (168, 156, 120), (196, 190, 176),
    ),
    "land": FramePalette(
        "land", "Land", "🟫", "Nonbasic land frame",
        (78, 58, 36), (132, 102, 64), (176, 140, 92),
        (210, 188, 150), (128, 98, 60), (216, 198, 164),
        (28, 20, 12), (32, 22, 14), (160, 120, 64), (196, 170, 126),
    ),
}

# Keep the original six scan-template keys working.
SCAN_TEMPLATES = {
    "artifact": "Artifact.png",
    "blue": "Blue.png",
    "dark": "Dark.png",
    "green": "Green.png",
    "light": "Light.png",
    "red": "Red.png",
}

SCAN_TEXT_COLORS = {
    "artifact": ((20, 20, 20), (30, 30, 30)),
    "blue": ((12, 16, 24), (20, 24, 32)),
    "dark": ((236, 232, 224), (220, 216, 208)),
    "green": ((16, 22, 12), (24, 30, 18)),
    "light": ((20, 20, 20), (30, 30, 30)),
    "red": ((24, 12, 10), (32, 16, 12)),
}

RARITY_COLORS = {
    "common": (28, 28, 28),
    "uncommon": (192, 204, 214),
    "rare": (214, 176, 64),
    "mythic": (214, 86, 36),
}

MANA_COLORS = {
    "W": ((255, 251, 214), (214, 190, 110), (40, 32, 12), "W"),
    "U": ((186, 220, 242), (54, 112, 168), (12, 28, 48), "U"),
    "B": ((92, 82, 92), (28, 22, 26), (236, 228, 214), "B"),
    "R": ((242, 168, 122), (176, 52, 28), (40, 12, 8), "R"),
    "G": ((170, 214, 132), (40, 96, 40), (12, 28, 10), "G"),
    "C": ((214, 210, 202), (120, 116, 108), (28, 26, 22), "C"),
    "X": ((214, 210, 202), (120, 116, 108), (28, 26, 22), "X"),
    "S": ((186, 220, 236), (90, 140, 170), (16, 28, 40), "S"),
}

MANA_TOKEN_RE = re.compile(r"\{([^}]+)\}")


@dataclass
class CardSpec:
    name: str = "Unnamed Card"
    mana_cost: str = ""
    type_line: str = ""
    oracle_text: str = ""
    flavor_text: str = ""
    power_toughness: str = ""
    artist: str = ""
    rarity: str = "rare"
    frame: str = "gold"
    engine: str = "painted"  # painted | scan
    set_code: str = "CUS"


# ── Fonts ───────────────────────────────────────────────────────────────────


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    key = (name, size)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    mapping = {
        "title": FONTS_DIR / "Cinzel-Bold.ttf",
        "title_reg": FONTS_DIR / "Cinzel-Regular.ttf",
        "display": FONTS_DIR / "CinzelDecorative-Regular.ttf",
        "serif": FONTS_DIR / "CrimsonPro-Regular.ttf",
        "serif_it": FONTS_DIR / "CrimsonPro-Italic.ttf",
        "body": FONTS_DIR / "SourceSans3-Regular.ttf",
        "body_bold": FONTS_DIR / "SourceSans3-Bold.ttf",
        "body_it": FONTS_DIR / "SourceSans3-It.ttf",
    }
    path = mapping.get(name)
    font: ImageFont.FreeTypeFont
    if path and path.exists():
        try:
            font = ImageFont.truetype(str(path), size)
            _FONT_CACHE[key] = font
            return font
        except OSError:
            pass
    for fallback in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ):
        try:
            font = ImageFont.truetype(fallback, size)
            _FONT_CACHE[key] = font
            return font
        except OSError:
            continue
    font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


def _text_size(draw: ImageDraw.ImageDraw, text: str, font) -> Tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _fit_font(draw, text: str, family: str, max_size: int, min_size: int, max_width: int):
    for size in range(max_size, min_size - 1, -1):
        font = _font(family, size)
        w, _ = _text_size(draw, text, font)
        if w <= max_width:
            return font
    return _font(family, min_size)


# ── Color / paint helpers ───────────────────────────────────────────────────


def _mix(a: Sequence[int], b: Sequence[int], t: float) -> Tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


def _rgba(rgb: Sequence[int], a: int = 255) -> Tuple[int, int, int, int]:
    return int(rgb[0]), int(rgb[1]), int(rgb[2]), a


def _vertical_gradient(
    size: Tuple[int, int],
    top: Sequence[int],
    bottom: Sequence[int],
    alpha: int = 255,
) -> Image.Image:
    w, h = size
    img = Image.new("RGBA", size)
    px = img.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        col = _rgba(_mix(top, bottom, t), alpha)
        for x in range(w):
            px[x, y] = col
    return img


def _noise_layer(size: Tuple[int, int], amount: int = 18, seed: int = 7) -> Image.Image:
    rng = random.Random(seed)
    w, h = size
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    px = img.load()
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            v = rng.randint(-amount, amount)
            a = rng.randint(10, 28)
            px[x, y] = (v + 128, v + 128, v + 128, a)
    return img.filter(ImageFilter.GaussianBlur(0.8))


def _rounded_mask(size: Tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def _cover_resize(im: Image.Image, box: Tuple[int, int]) -> Image.Image:
    tw, th = box
    iw, ih = im.size
    if iw == 0 or ih == 0:
        return Image.new("RGBA", box, (20, 20, 20, 255))
    scale = max(tw / iw, th / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left = max(0, (nw - tw) // 2)
    top = max(0, (nh - th) // 2)
    return im.crop((left, top, left + tw, top + th))


def _round_rect(draw, xy, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


# ── Mana pips ───────────────────────────────────────────────────────────────


def parse_mana_cost(raw: str) -> List[str]:
    raw = (raw or "").strip()
    if not raw:
        return []
    tokens = MANA_TOKEN_RE.findall(raw)
    if tokens:
        return [t.upper() for t in tokens]
    # Allow loose input like 3WW or 2UR
    out: List[str] = []
    i = 0
    s = raw.upper().replace("{", "").replace("}", "").replace(" ", "")
    while i < len(s):
        if s[i].isdigit():
            j = i
            while j < len(s) and s[j].isdigit():
                j += 1
            out.append(s[i:j])
            i = j
        elif s[i] in "WUBRGCSX":
            out.append(s[i])
            i += 1
        else:
            i += 1
    return out


def _symbol_file_stem(symbol: str) -> str:
    key = symbol.upper().strip().replace("{", "").replace("}", "")
    return key.replace("/", "")


def _pip_image(symbol: str, diameter: int) -> Optional[Image.Image]:
    stem = _symbol_file_stem(symbol)
    cache_key = (stem, diameter)
    cached = _PIP_CACHE.get(cache_key)
    if cached is not None:
        return cached
    path = MANA_DIR / f"{stem}.png"
    if not path.exists():
        return None
    im = Image.open(path).convert("RGBA").resize((diameter, diameter), Image.Resampling.LANCZOS)
    _PIP_CACHE[cache_key] = im
    return im


def format_cost(tokens: Sequence[str]) -> str:
    return "".join(f"{{{t}}}" for t in tokens)


def _draw_pip(canvas: Image.Image, cx: int, cy: int, r: int, symbol: str) -> None:
    size = max(12, r * 2)
    pip = _pip_image(symbol, size)
    if pip is not None:
        x = int(cx - pip.width / 2)
        y = int(cy - pip.height / 2)
        shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        sd.ellipse((x + 1, y + 2, x + pip.width, y + pip.height + 1), fill=(0, 0, 0, 70))
        canvas.alpha_composite(shadow)
        canvas.alpha_composite(pip, (x, y))
        return

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    key = symbol.upper()
    if "/" in key:
        left, right = key.split("/", 1)
        _draw_split_pip(d, cx, cy, r, left, right)
    elif key.isdigit() or key == "X":
        fill, edge, ink, label = MANA_COLORS.get("X" if key == "X" else "C", MANA_COLORS["C"])
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=_rgba(edge, 255))
        d.ellipse((cx - r + 2, cy - r + 2, cx + r - 2, cy + r - 2), fill=_rgba(fill, 255))
        # highlight
        d.ellipse((cx - r // 2, cy - r + 3, cx + r // 5, cy - r // 5), fill=(255, 255, 255, 70))
        font = _font("body_bold", max(10, int(r * 1.35)))
        tw, th = _text_size(d, key, font)
        d.text((cx - tw / 2, cy - th / 2 - 1), key, font=font, fill=_rgba(ink))
    else:
        fill, edge, ink, label = MANA_COLORS.get(key[:1], MANA_COLORS["C"])
        d.ellipse((cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1), fill=(0, 0, 0, 90))
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=_rgba(edge, 255))
        d.ellipse((cx - r + 2, cy - r + 2, cx + r - 2, cy + r - 2), fill=_rgba(fill, 255))
        d.ellipse((cx - r // 2, cy - r + 3, cx + r // 6, cy - r // 4), fill=(255, 255, 255, 80))
        font = _font("body_bold", max(10, int(r * 1.15)))
        tw, th = _text_size(d, label, font)
        d.text((cx - tw / 2, cy - th / 2 - 1), label, font=font, fill=_rgba(ink))
    canvas.alpha_composite(overlay)


def _draw_split_pip(d: ImageDraw.ImageDraw, cx: int, cy: int, r: int, left: str, right: str) -> None:
    lf = MANA_COLORS.get(left[:1], MANA_COLORS["C"])
    rf = MANA_COLORS.get(right[:1], MANA_COLORS["C"])
    d.pieslice((cx - r, cy - r, cx + r, cy + r), 45, 225, fill=_rgba(lf[0]))
    d.pieslice((cx - r, cy - r, cx + r, cy + r), 225, 405, fill=_rgba(rf[0]))
    d.arc((cx - r, cy - r, cx + r, cy + r), 0, 360, fill=_rgba(lf[1]), width=2)
    font = _font("body_bold", max(9, int(r * 0.7)))
    d.text((cx - r + 3, cy - 2), left[:1], font=font, fill=_rgba(lf[2]))
    d.text((cx + 1, cy - r + 4), right[:1], font=font, fill=_rgba(rf[2]))


def draw_mana_row(canvas: Image.Image, tokens: Sequence[str], right: int, cy: int, pip: int) -> int:
    """Draw mana right-aligned. Returns the leftmost x used."""
    if not tokens:
        return right
    gap = 3
    total = len(tokens) * (pip * 2) + (len(tokens) - 1) * gap
    x = right - total + pip
    for tok in tokens:
        _draw_pip(canvas, x, cy, pip, tok)
        x += pip * 2 + gap
    return right - total


# ── Art window detection for scan templates ─────────────────────────────────


def detect_art_window(template: Image.Image) -> Tuple[int, int, int, int]:
    """Largest mostly-transparent axis-aligned band, used as the art hole."""
    alpha = template.split()[-1]
    w, h = template.size
    # Downsample for speed
    scale = 4
    small = alpha.resize((max(1, w // scale), max(1, h // scale)), Image.Resampling.NEAREST)
    sw, sh = small.size
    px = small.load()
    # Score each row for transparency density
    rows = []
    for y in range(sh):
        t = 0
        for x in range(sw):
            if px[x, y] < 40:
                t += 1
        rows.append(t / sw)
    # Find the longest run of rows that are mostly transparent in the upper half
    best = (0, 0, 0.0)  # start, end, score
    y = 0
    while y < sh:
        if rows[y] < 0.35:
            y += 1
            continue
        y0 = y
        while y < sh and rows[y] >= 0.35:
            y += 1
        y1 = y
        score = (y1 - y0) * sum(rows[y0:y1])
        # Prefer the upper/mid card (art box), not full-card transparency
        mid = (y0 + y1) / 2 / sh
        if 0.08 < mid < 0.62 and (y1 - y0) > best[1] - best[0]:
            best = (y0, y1, score)
    if best[1] <= best[0]:
        # fallback classic proportions
        return int(w * 0.086), int(h * 0.118), int(w * 0.828), int(h * 0.434)

    y0, y1, _ = best
    # column bounds inside that band
    x_hits = []
    for x in range(sw):
        t = 0
        for yy in range(y0, y1):
            if px[x, yy] < 40:
                t += 1
        x_hits.append(t / max(y1 - y0, 1))
    xs = [i for i, v in enumerate(x_hits) if v >= 0.4]
    if not xs:
        x0, x1 = int(sw * 0.08), int(sw * 0.92)
    else:
        x0, x1 = xs[0], xs[-1]
    min_x = int(sw * 0.07)
    max_x = int(sw * 0.93)
    x0 = max(x0, min_x)
    x1 = min(x1, max_x)
    return x0 * scale, y0 * scale, (x1 - x0 + 1) * scale, (y1 - y0 + 1) * scale


# ── Painted frame ───────────────────────────────────────────────────────────


def _draw_bevel(draw: ImageDraw.ImageDraw, box, radius=6, light=(255, 255, 255, 70), dark=(0, 0, 0, 80)):
    x0, y0, x1, y1 = box
    draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, outline=light, width=1)
    draw.line((x0 + radius, y1, x1 - radius, y1), fill=dark)
    draw.line((x1, y0 + radius, x1, y1 - radius), fill=dark)


def paint_frame(canvas: Image.Image, pal: FramePalette, legendary: bool = False) -> None:
    w, h = canvas.size
    # Outer void
    ImageDraw.Draw(canvas).rectangle((0, 0, w, h), fill=(8, 8, 8, 255))

    # Colored metallic frame
    frame = _vertical_gradient((w, h), pal.frame_light, pal.frame_dark)
    frame = Image.alpha_composite(frame, _noise_layer((w, h), 14, seed=hash(pal.key) & 0xFFFF))
    canvas.alpha_composite(frame)

    # Inner field
    inner = (MARGIN + 6, NAME_TOP + NAME_H + 4, w - MARGIN - 6, h - 36)
    field = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    fd = ImageDraw.Draw(field)
    _round_rect(fd, inner, 10, fill=_rgba(pal.text_box))
    canvas.alpha_composite(field)

    # Name plate
    nd = ImageDraw.Draw(canvas)
    name_box = (MARGIN + 8, NAME_TOP, w - MARGIN - 8, NAME_TOP + NAME_H)
    plate = _vertical_gradient((w, NAME_H + 4), pal.plate, _mix(pal.plate, pal.plate_edge, 0.45))
    plate_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    plate_layer.paste(plate, (0, NAME_TOP - 2))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle(name_box, radius=10, fill=255)
    canvas.paste(Image.composite(plate_layer, canvas, mask), (0, 0))
    _draw_bevel(nd, name_box, radius=10, light=_rgba(pal.frame_light, 160), dark=(0, 0, 0, 90))

    # Type plate
    type_box = (MARGIN + 8, TYPE_TOP, w - MARGIN - 8, TYPE_TOP + TYPE_H)
    tplate = _vertical_gradient((w, TYPE_H + 4), pal.plate, _mix(pal.plate, pal.plate_edge, 0.4))
    tlayer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    tlayer.paste(tplate, (0, TYPE_TOP - 2))
    tmask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(tmask).rounded_rectangle(type_box, radius=8, fill=255)
    canvas.paste(Image.composite(tlayer, canvas, tmask), (0, 0))
    _draw_bevel(nd, type_box, radius=8, light=_rgba(pal.frame_light, 150), dark=(0, 0, 0, 80))

    # Text box parchment
    text_box = (MARGIN + 10, TEXT_TOP, w - MARGIN - 10, TEXT_BOTTOM)
    parchment = _vertical_gradient(
        (w, TEXT_BOTTOM - TEXT_TOP),
        _mix(pal.text_box, (255, 255, 255), 0.08),
        _mix(pal.text_box, pal.plate_edge, 0.18),
    )
    parchment = Image.alpha_composite(parchment, _noise_layer(parchment.size, 12, seed=99))
    player = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    player.paste(parchment, (0, TEXT_TOP))
    pmask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(pmask).rounded_rectangle(text_box, radius=8, fill=255)
    canvas.paste(Image.composite(player, canvas, pmask), (0, 0))
    nd.rounded_rectangle(text_box, radius=8, outline=_rgba(pal.plate_edge, 180), width=1)

    # Outer gold/dark rail
    nd.rounded_rectangle(
        (MARGIN - 6, 22, w - MARGIN + 6, h - 22),
        radius=22,
        outline=_rgba(pal.accent, 220),
        width=3,
    )
    nd.rounded_rectangle(
        (8, 8, w - 9, h - 9),
        radius=28,
        outline=(12, 12, 12, 255),
        width=10,
    )
    # Fine inner hairline
    nd.rounded_rectangle(
        (18, 18, w - 19, h - 19),
        radius=24,
        outline=_rgba(pal.frame_light, 90),
        width=1,
    )

    if legendary:
        cd = ImageDraw.Draw(canvas)
        y = NAME_TOP - 8
        x0, x1 = MARGIN + 16, w - MARGIN - 16
        cd.line((x0, y, x1, y), fill=_rgba(pal.accent, 230), width=3)
        for i in range(7):
            x = x0 + 18 + i * ((x1 - x0 - 36) / 6)
            cd.polygon(
                [(x - 7, y), (x, y - 11), (x + 7, y)],
                fill=_rgba(pal.accent, 230),
            )


def paste_art(canvas: Image.Image, art: Image.Image, box: Tuple[int, int, int, int]) -> None:
    x, y, bw, bh = box
    fitted = _cover_resize(art.convert("RGBA"), (bw, bh))
    canvas.paste(fitted, (x, y))
    # Inner shadow around the art window
    shadow = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    for i in range(14):
        a = int(70 * (1 - i / 14))
        sd.rectangle((i, i, bw - 1 - i, bh - 1 - i), outline=(0, 0, 0, a))
    canvas.alpha_composite(shadow, (x, y))
    ImageDraw.Draw(canvas).rectangle((x, y, x + bw - 1, y + bh - 1), outline=(0, 0, 0, 160), width=2)


def draw_pt_box(canvas: Image.Image, pal: FramePalette, text: str) -> None:
    if not text:
        return
    w, h = canvas.size
    box = (w - MARGIN - PT_W - 4, h - 36 - PT_H - 8, w - MARGIN - 4, h - 36 - 8)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    _round_rect(d, box, 8, fill=_rgba(pal.pt_fill), outline=_rgba(pal.accent), width=2)
    _draw_bevel(d, box, radius=8, light=(255, 255, 255, 70), dark=(0, 0, 0, 80))
    font = _font("title", 28)
    tw, th = _text_size(d, text, font)
    cx = (box[0] + box[2]) / 2
    cy = (box[1] + box[3]) / 2
    d.text((cx - tw / 2, cy - th / 2 - 2), text, font=font, fill=_rgba(pal.title))
    canvas.alpha_composite(layer)


def draw_rarity_stamp(canvas: Image.Image, rarity: str, set_code: str, pal: FramePalette) -> None:
    w, _ = canvas.size
    cx = w - MARGIN - 28
    cy = TYPE_TOP + TYPE_H // 2
    color = RARITY_COLORS.get(rarity, RARITY_COLORS["rare"])
    d = ImageDraw.Draw(canvas)
    d.ellipse((cx - STAMP_R - 1, cy - STAMP_R - 1, cx + STAMP_R + 1, cy + STAMP_R + 1), fill=(0, 0, 0, 160))
    d.ellipse((cx - STAMP_R, cy - STAMP_R, cx + STAMP_R, cy + STAMP_R), fill=_rgba(color))
    d.ellipse((cx - STAMP_R + 3, cy - STAMP_R + 3, cx + STAMP_R - 3, cy + STAMP_R - 3), fill=_rgba(_mix(color, (255, 255, 255), 0.25)))
    font = _font("body_bold", 11)
    code = (set_code or "CUS")[:3].upper()
    tw, th = _text_size(d, code, font)
    ink = (20, 16, 10, 230) if rarity != "common" else (230, 230, 230, 230)
    d.text((cx - tw / 2, cy - th / 2 - 1), code, font=font, fill=ink)


def _wrap_tokens(draw, tokens: List[str], font, max_width: int) -> List[List[str]]:
    lines: List[List[str]] = []
    current: List[str] = []

    def width_of(parts: List[str]) -> int:
        text = " ".join(p for p in parts if not p.startswith("{"))
        extra = sum(22 for p in parts if p.startswith("{"))
        w, _ = _text_size(draw, text, font) if text else (0, 0)
        spaces = max(len([p for p in parts if not p.startswith("{")]) - 1, 0) * 4
        return w + extra + spaces

    for tok in tokens:
        if tok == "\n":
            lines.append(current)
            current = []
            continue
        trial = current + [tok]
        if current and width_of(trial) > max_width:
            lines.append(current)
            current = [tok]
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def _tokenize_oracle(text: str) -> List[str]:
    if not text:
        return []
    tokens: List[str] = []
    for raw_line in text.splitlines():
        if tokens:
            tokens.append("\n")
        i = 0
        line = raw_line
        while i < len(line):
            m = MANA_TOKEN_RE.search(line, i)
            if not m:
                rest = line[i:].split()
                tokens.extend(rest)
                break
            before = line[i:m.start()].split()
            tokens.extend(before)
            tokens.append("{" + m.group(1) + "}")
            i = m.end()
    return tokens


def draw_oracle_and_flavor(
    canvas: Image.Image,
    spec: CardSpec,
    pal: FramePalette,
    box: Tuple[int, int, int, int],
) -> None:
    x0, y0, x1, y1 = box
    d = ImageDraw.Draw(canvas)
    font = _font("body", 22)
    italic = _font("serif_it", 21)
    max_w = x1 - x0
    y = y0
    tokens = _tokenize_oracle(spec.oracle_text.replace("~", spec.name))
    lines = _wrap_tokens(d, tokens, font, max_w)
    line_h = 28
    for line in lines:
        if y + line_h > y1 - 8:
            break
        x = x0
        for tok in line:
            if tok.startswith("{") and tok.endswith("}"):
                _draw_pip(canvas, x + 10, y + 12, 10, tok[1:-1])
                x += 24
            else:
                d.text((x, y), tok + " ", font=font, fill=_rgba(pal.body))
                tw, _ = _text_size(d, tok + " ", font)
                x += tw
        y += line_h

    flavor = (spec.flavor_text or "").strip()
    if flavor and y + 36 < y1:
        y += 8
        d.line((x0 + 40, y, x1 - 40, y), fill=_rgba(pal.plate_edge, 160), width=1)
        y += 8
        # wrap flavor
        words = flavor.split()
        flines: List[str] = []
        cur = ""
        for word in words:
            trial = (cur + " " + word).strip()
            tw, _ = _text_size(d, trial, italic)
            if tw > max_w and cur:
                flines.append(cur)
                cur = word
            else:
                cur = trial
        if cur:
            flines.append(cur)
        for line in flines:
            if y + 26 > y1:
                break
            d.text((x0, y), line, font=italic, fill=_rgba(pal.body, 220))
            y += 26


def draw_footer(canvas: Image.Image, spec: CardSpec, pal: FramePalette) -> None:
    d = ImageDraw.Draw(canvas)
    font = _font("body", 12)
    artist = spec.artist.strip() if spec.artist else ""
    left = f"Illus. {artist}" if artist else "Unofficial fan-made card"
    d.text((MARGIN + 10, CARD_H - 28), left, font=font, fill=(200, 196, 186, 230))


# ── Public render ───────────────────────────────────────────────────────────


def render_card(art_bytes: bytes, spec: CardSpec) -> bytes:
    art = Image.open(io.BytesIO(art_bytes)).convert("RGBA")
    if spec.engine == "scan" and spec.frame in SCAN_TEMPLATES:
        canvas = _render_scan(art, spec)
    else:
        canvas = _render_painted(art, spec)

    mask = _rounded_mask(canvas.size, 36)
    out = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    out.paste(canvas, (0, 0))
    out.putalpha(mask)

    # Composite onto a dark slate so Discord previews look clean
    bg = Image.new("RGBA", canvas.size, (18, 18, 20, 255))
    bg.putalpha(mask)
    final = Image.alpha_composite(bg, out)

    buf = io.BytesIO()
    final.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _render_painted(art: Image.Image, spec: CardSpec) -> Image.Image:
    pal = PALETTES.get(spec.frame, PALETTES["gold"])
    canvas = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 255))
    legendary = "legendary" in (spec.type_line or "").lower()
    paint_frame(canvas, pal, legendary=legendary)

    art_box = (MARGIN + 12, ART_TOP, CARD_W - 2 * (MARGIN + 12), ART_H)
    paste_art(canvas, art, art_box)

    d = ImageDraw.Draw(canvas)
    tokens = parse_mana_cost(spec.mana_cost)
    pip = 16
    mana_right = CARD_W - MARGIN - 18
    used_left = draw_mana_row(canvas, tokens, mana_right, NAME_TOP + NAME_H // 2, pip)

    name = spec.name or "Unnamed Card"
    name_font = _fit_font(d, name, "title", 30, 16, used_left - (MARGIN + 28) - 8)
    d.text((MARGIN + 22, NAME_TOP + 10), name, font=name_font, fill=_rgba(pal.title))

    type_line = spec.type_line or ""
    type_font = _fit_font(d, type_line, "serif", 24, 14, CARD_W - 2 * MARGIN - 70)
    d.text((MARGIN + 22, TYPE_TOP + 8), type_line, font=type_font, fill=_rgba(pal.title))

    draw_rarity_stamp(canvas, spec.rarity, spec.set_code, pal)
    draw_oracle_and_flavor(
        canvas,
        spec,
        pal,
        (MARGIN + 22, TEXT_TOP + 12, CARD_W - MARGIN - 22, TEXT_BOTTOM - 10),
    )
    draw_pt_box(canvas, pal, spec.power_toughness)
    draw_footer(canvas, spec, pal)
    return canvas


def _render_scan(art: Image.Image, spec: CardSpec) -> Image.Image:
    path = TEMPLATES_DIR / SCAN_TEMPLATES[spec.frame]
    if not path.exists():
        # fall back to painted equivalent
        mapped = {
            "light": "white",
            "dark": "black",
            "artifact": "artifact",
            "blue": "blue",
            "green": "green",
            "red": "red",
        }.get(spec.frame, "gold")
        spec = CardSpec(**{**spec.__dict__, "frame": mapped, "engine": "painted"})
        return _render_painted(art, spec)

    raw = Image.open(path).convert("RGBA")
    template = raw.resize((CARD_W, CARD_H), Image.Resampling.LANCZOS)
    ax, ay, aw, ah = detect_art_window(template)
    # Clamp
    ax = max(0, min(ax, CARD_W - 10))
    ay = max(0, min(ay, CARD_H - 10))
    aw = max(40, min(aw, CARD_W - ax))
    ah = max(40, min(ah, CARD_H - ay))

    canvas = Image.new("RGBA", (CARD_W, CARD_H), (228, 222, 210, 255))
    paste_art(canvas, art, (ax, ay, aw, ah))
    canvas.alpha_composite(template)

    # The bundled scans are full cards, not blank frames. Cover the original
    # name, type, text and artist so our typography is the only text.
    def _sample(box):
        crop = canvas.crop(box).resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
        return crop[:3] if isinstance(crop, tuple) else (200, 200, 200)

    cover = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    cd = ImageDraw.Draw(cover)
    name_col = _sample((50, max(8, ay - 50), CARD_W - 50, max(10, ay - 8)))
    type_col = _sample((50, ay + ah + 2, CARD_W - 80, ay + ah + 36))
    text_col = _sample((60, min(CARD_H - 80, ay + ah + 50), CARD_W - 60, CARD_H - 90))
    cd.rounded_rectangle((36, 26, CARD_W - 36, max(70, ay - 6)), 8, fill=_rgba(name_col, 245))
    cd.rounded_rectangle((36, ay + ah + 4, CARD_W - 36, ay + ah + 42), 8, fill=_rgba(type_col, 245))
    cd.rounded_rectangle((40, ay + ah + 46, CARD_W - 40, CARD_H - 58), 8, fill=_rgba(text_col, 250))
    canvas.alpha_composite(cover)

    title_c, body_c = SCAN_TEXT_COLORS.get(spec.frame, ((20, 20, 20), (30, 30, 30)))
    # Auto-contrast from the name-bar strip
    sample = canvas.crop((40, 24, CARD_W - 40, max(25, ay - 8)))
    avg = sample.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
    if isinstance(avg, int):
        lum = avg
    else:
        lum = 0.2126 * avg[0] + 0.7152 * avg[1] + 0.0722 * avg[2]
    if lum < 110:
        title_c, body_c = (236, 230, 220), (220, 214, 204)

    d = ImageDraw.Draw(canvas)
    tokens = parse_mana_cost(spec.mana_cost)
    pip = 15
    name_cy = max(28, ay // 2)
    used_left = draw_mana_row(canvas, tokens, CARD_W - 40, name_cy, pip)
    name = spec.name or "Unnamed Card"
    name_font = _fit_font(d, name, "title", 28, 14, used_left - 50)
    d.text((40, name_cy - 14), name, font=name_font, fill=_rgba(title_c))

    type_y = ay + ah + 10
    type_font = _fit_font(d, spec.type_line, "serif", 22, 13, CARD_W - 100)
    d.text((42, type_y), spec.type_line or "", font=type_font, fill=_rgba(title_c))

    text_top = type_y + 36
    text_bottom = CARD_H - 70
    pal = FramePalette(
        spec.frame, spec.frame, "", "",
        (0, 0, 0), (0, 0, 0), (0, 0, 0),
        (0, 0, 0), (120, 110, 90), (0, 0, 0),
        title_c, body_c, (160, 130, 60), (200, 190, 170),
    )
    draw_oracle_and_flavor(canvas, spec, pal, (44, text_top, CARD_W - 44, text_bottom))
    if spec.power_toughness:
        draw_pt_box(canvas, pal, spec.power_toughness)
    draw_footer(canvas, spec, pal)
    return canvas


def placeholder_art(seed: str = "mtg") -> bytes:
    """Generate a moody procedural art plate so the cog still works with no upload."""
    rng = random.Random(seed)
    img = Image.new("RGB", (900, 640))
    top = (rng.randint(10, 60), rng.randint(10, 50), rng.randint(20, 80))
    bot = (rng.randint(80, 160), rng.randint(40, 100), rng.randint(20, 70))
    grad = _vertical_gradient((900, 640), top, bot).convert("RGB")
    img.paste(grad)
    d = ImageDraw.Draw(img, "RGBA")
    for _ in range(18):
        x, y = rng.randint(-40, 860), rng.randint(-40, 600)
        r = rng.randint(40, 220)
        col = (rng.randint(20, 200), rng.randint(20, 180), rng.randint(20, 160), rng.randint(30, 90))
        d.ellipse((x, y, x + r, y + r), fill=col)
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
