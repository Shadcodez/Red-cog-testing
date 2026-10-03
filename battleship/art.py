"""Admiralty-chart boards for the Battleship cog. No Discord imports."""

from __future__ import annotations

import math
import os
from io import BytesIO
from typing import List, Optional, Sequence, Tuple

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

COLS = "ABCDEFGHIJ"
Cell = Tuple[int, int]  # col, row  0..9

NAVY = (8, 22, 42)
INK = (232, 220, 196)
BRASS = (212, 175, 98)
BRASS_DIM = (128, 102, 58)
FOAM = (186, 214, 222)
HIT = (214, 78, 42)
HIT_CORE = (255, 196, 92)
MISS = (210, 228, 236)
HULL = (168, 176, 186)
HULL_EDGE = (232, 220, 188)
SUNK = (122, 52, 46)
WATER_A = (28, 104, 138)
WATER_B = (18, 78, 112)


def _font(size: int, bold: bool = False) -> "ImageFont.ImageFont":
    names = (
        [
            "/usr/share/fonts/truetype/noto/NotoSerif-Bold.ttf",
            "/usr/share/fonts/opentype/inter/Inter-Bold.otf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "C:/Windows/Fonts/georgiab.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
        ]
        if bold
        else [
            "/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf",
            "/usr/share/fonts/opentype/inter/Inter-Regular.otf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/georgia.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]
    )
    for path in names:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _gradient(w: int, h: int, top: Tuple[int, int, int], bot: Tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGB", (w, h), top)
    draw = ImageDraw.Draw(img)
    bands = 96
    for i in range(bands):
        t = i / (bands - 1)
        color = tuple(int(top[c] + (bot[c] - top[c]) * t) for c in range(3))
        y0 = int(h * i / bands)
        y1 = int(h * (i + 1) / bands) + 1
        draw.rectangle((0, y0, w, y1), fill=color)
    return img


def _waves(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    for n in range(7):
        y = y0 + 18 + n * ((y1 - y0) // 8)
        pts = []
        amp = 3 + (n % 3)
        for x in range(x0, x1, 6):
            pts.append((x, y + int(math.sin((x / 28.0) + n) * amp)))
        if len(pts) > 1:
            draw.line(pts, fill=(255, 255, 255, 28), width=1)


def _anchor(draw: ImageDraw.ImageDraw, cx: int, cy: int, s: int, fill: Tuple[int, int, int]) -> None:
    draw.ellipse((cx - s // 5, cy - s, cx + s // 5, cy - s + s // 2.4), outline=fill, width=2)
    draw.line((cx, cy - s + s // 5, cx, cy + s // 2), fill=fill, width=2)
    draw.arc((cx - s // 2, cy, cx + s // 2, cy + s), 20, 160, fill=fill, width=2)
    draw.line((cx - s // 3, cy - s // 5, cx + s // 3, cy - s // 5), fill=fill, width=2)


def _splash(draw: ImageDraw.ImageDraw, cx: int, cy: int, rad: int) -> None:
    draw.ellipse((cx - rad, cy - rad // 2, cx + rad, cy + rad // 2), outline=MISS, width=2)
    draw.ellipse((cx - rad // 2, cy - rad // 3, cx + rad // 2, cy + rad // 3), fill=(236, 244, 248))
    draw.line((cx - rad - 2, cy, cx - rad + 4, cy - 5), fill=FOAM, width=2)
    draw.line((cx + rad - 4, cy - 5, cx + rad + 2, cy), fill=FOAM, width=2)


def _burst(draw: ImageDraw.ImageDraw, cx: int, cy: int, rad: int) -> None:
    draw.ellipse((cx - rad - 2, cy - rad - 2, cx + rad + 2, cy + rad + 2), fill=(70, 18, 14))
    draw.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=HIT)
    draw.ellipse((cx - rad // 2, cy - rad // 2, cx + rad // 2, cy + rad // 2), fill=HIT_CORE)
    draw.line((cx - rad, cy, cx + rad, cy), fill=(255, 236, 200), width=2)
    draw.line((cx, cy - rad, cx, cy + rad), fill=(255, 236, 200), width=2)


def _hull(draw: ImageDraw.ImageDraw, cells: Sequence[Cell], origin: Tuple[int, int], cell: int, sunk: bool) -> None:
    if not cells:
        return
    cols = [c for c, _ in cells]
    rows = [r for _, r in cells]
    horizontal = max(cols) != min(cols)
    pad = 4
    ox, oy = origin
    x0 = ox + min(cols) * cell + pad
    y0 = oy + min(rows) * cell + pad
    x1 = ox + (max(cols) + 1) * cell - pad
    y1 = oy + (max(rows) + 1) * cell - pad
    fill = SUNK if sunk else HULL
    edge = (90, 36, 32) if sunk else (48, 56, 66)
    bow = 14
    if horizontal:
        poly = [(x0 + 4, y0 + 3), (x1 - bow, y0 + 1), (x1 - 1, (y0 + y1) // 2), (x1 - bow, y1 - 1), (x0 + 4, y1 - 3)]
    else:
        poly = [(x0 + 3, y0 + 4), (x1 - 3, y0 + 4), (x1 - 1, y1 - bow), ((x0 + x1) // 2, y1 - 1), (x0 + 1, y1 - bow)]
    draw.polygon(poly, fill=fill)
    draw.line(poly + [poly[0]], fill=edge, width=2)
    n = max(len(cells), 1)
    for i in range(n):
        if horizontal:
            px = x0 + 16 + i * ((x1 - x0 - 28) / max(n, 1))
            py = (y0 + y1) // 2
        else:
            px = (x0 + x1) // 2
            py = y0 + 16 + i * ((y1 - y0 - 28) / max(n, 1))
        draw.ellipse((px - 3, py - 3, px + 3, py + 3), fill=(214, 196, 150) if not sunk else (150, 90, 78), outline=edge)
    if len(cells) >= 3:
        if horizontal:
            hx = x0 + (x1 - x0) * 0.42
            draw.rounded_rectangle((hx, y0 + 5, hx + 16, y1 - 5), 2, fill=(92, 102, 114) if not sunk else (78, 40, 38), outline=edge)
            draw.line((hx + 8, y0 + 5, hx + 8, y0 - 6), fill=edge, width=2)
        else:
            hy = y0 + (y1 - y0) * 0.38
            draw.rounded_rectangle((x0 + 5, hy, x1 - 5, hy + 16), 2, fill=(92, 102, 114) if not sunk else (78, 40, 38), outline=edge)
            draw.line(((x0 + x1) // 2, hy, (x0 + x1) // 2, hy - 6), fill=edge, width=2)


def _grid(
    base: Image.Image,
    origin: Tuple[int, int],
    cell: int,
    ships: Sequence[dict],
    shots: Sequence[dict],
    show_hulls: bool,
) -> None:
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    ox, oy = origin
    side = cell * 10
    draw.rounded_rectangle((ox - 8, oy - 8, ox + side + 8, oy + side + 8), 10, fill=(6, 28, 48, 210))
    _waves(draw, (ox, oy, ox + side, oy + side))
    for r in range(10):
        for c in range(10):
            x = ox + c * cell
            y = oy + r * cell
            shade = WATER_A if (c + r) % 2 == 0 else WATER_B
            draw.rectangle((x + 1, y + 1, x + cell - 2, y + cell - 2), fill=shade + (235,))
            draw.rectangle((x, y, x + cell - 1, y + cell - 1), outline=(232, 214, 170, 160))
    base.paste(Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB"))
    ink = ImageDraw.Draw(base)
    for ship in ships:
        if ship.get("show"):
            _hull(ink, ship["cells"], origin, cell, ship.get("sunk", False))
    for shot in shots:
        c, r = shot["cell"]
        kind = shot["kind"]
        cx = ox + c * cell + cell // 2
        cy = oy + r * cell + cell // 2
        if kind == "miss":
            _splash(ink, cx, cy, cell // 5)
        elif kind in ("hit", "sunk"):
            _burst(ink, cx, cy, cell // 4)
    label = _font(16, bold=True)
    for i, ch in enumerate(COLS):
        ink.text((ox + i * cell + cell // 2, oy - 18), ch, fill=BRASS, font=label, anchor="mm")
    for i in range(10):
        ink.text((ox - 18, oy + i * cell + cell // 2), str(i + 1), fill=BRASS, font=label, anchor="mm")
    ink.rectangle((ox - 1, oy - 1, ox + side, oy + side), outline=BRASS, width=2)
    _ = label


def render_boards(
    panels: Sequence[dict],
    title: str,
    subtitle: str,
    footer: str,
    wide: bool = True,
) -> bytes:
    """panels: {heading, ships, shots, show_hulls, accent}"""
    if not HAS_PIL:
        raise RuntimeError("Pillow is not installed")
    cell = 42
    margin = 54
    gap = 46
    header = 86
    foot = 54
    board = cell * 10
    n = len(panels)
    w = margin * 2 + n * board + (n - 1) * gap + 36
    h = header + 70 + board + 64 + foot
    img = _gradient(w, h, (10, 24, 46), (6, 40, 62))
    draw = ImageDraw.Draw(img)
    draw.rectangle((14, 14, w - 14, h - 14), outline=BRASS, width=2)
    draw.rectangle((18, 18, w - 18, h - 18), outline=BRASS_DIM, width=1)
    _anchor(draw, 42, 48, 22, BRASS)
    draw.text((64, 32), title, fill=INK, font=_font(28, bold=True))
    draw.text((64, 64), subtitle, fill=BRASS, font=_font(16, bold=True))
    for i, panel in enumerate(panels):
        ox = margin + 10 + i * (board + gap)
        oy = header + 72
        _grid(img, (ox, oy), cell, panel.get("ships", []), panel.get("shots", []), panel.get("show_hulls", False))
        d = ImageDraw.Draw(img)
        accent = panel.get("accent", BRASS)
        d.rounded_rectangle((ox, oy - 52, ox + min(280, board), oy - 30), 4, fill=accent)
        d.text((ox + 8, oy - 41), panel.get("heading", "OCEAN")[:32], fill=(12, 18, 28), font=_font(14, bold=True), anchor="lm")
        afloat = panel.get("afloat", "")
        if afloat:
            d.text((ox, oy + board + 16), afloat, fill=FOAM, font=_font(15, bold=True))
    d = ImageDraw.Draw(img)
    d.text((margin, h - 34), footer[:120], fill=(198, 186, 156), font=_font(14, bold=True))
    d.text((w - margin, h - 34), "BATTLESHIP", fill=BRASS, font=_font(14, bold=True), anchor="ra")
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def text_grid(shots: Sequence[dict], ships: Optional[Sequence[dict]] = None, reveal: bool = False) -> str:
    marks = {(s["cell"][0], s["cell"][1]): s["kind"] for s in shots}
    hulls = {}
    if reveal and ships:
        for ship in ships:
            token = ship.get("mark", "#")
            for cell in ship["cells"]:
                hulls[tuple(cell)] = token.lower() if ship.get("sunk") else token
    lines = ["   " + " ".join(COLS)]
    for r in range(10):
        row = [f"{r + 1:2}"]
        for c in range(10):
            kind = marks.get((c, r))
            if kind == "miss":
                row.append("o")
            elif kind in ("hit", "sunk"):
                row.append("X")
            elif (c, r) in hulls:
                row.append(hulls[(c, r)])
            else:
                row.append("·")
        lines.append(" ".join(row))
    return "\n".join(lines)
