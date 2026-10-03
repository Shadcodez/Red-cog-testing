"""Felt board for the Connect Four cog. No Discord imports."""

from __future__ import annotations

import os
from io import BytesIO
from typing import List, Optional, Sequence, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

NAVY = (12, 28, 58)
FELT = (18, 72, 122)
FELT_DEEP = (10, 46, 86)
CREAM = (236, 226, 206)
BRASS = (212, 175, 98)
RED = (214, 54, 48)
RED_HI = (255, 168, 150)
YELLOW = (242, 196, 48)
YELLOW_HI = (255, 236, 170)
HOLE = (8, 22, 40)
WIN = (255, 255, 255)

Cell = Tuple[int, int]


def _font(size: int, bold: bool = False) -> "ImageFont.ImageFont":
    names = (
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
        ]
        if bold
        else [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
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


def render_board(
    columns: Sequence[Sequence[int]],
    last: Optional[Cell] = None,
    win: Optional[Sequence[Cell]] = None,
    title: str = "Connect Four",
    subtitle: str = "",
) -> BytesIO:
    cell = 92
    pad_x = 54
    pad_top = 108
    pad_bot = 78
    width = pad_x * 2 + 7 * cell
    height = pad_top + pad_bot + 6 * cell
    img = Image.new("RGB", (width, height), NAVY)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((18, 18, width - 18, height - 18), radius=28, fill=FELT_DEEP, outline=BRASS, width=3)
    frame = (pad_x - 16, pad_top - 16, pad_x + 7 * cell + 16, pad_top + 6 * cell + 16)
    draw.rounded_rectangle(frame, radius=22, fill=FELT, outline=BRASS, width=4)
    win_set = set(win or [])
    title_font = _font(36, True)
    sub_font = _font(20)
    num_font = _font(22, True)
    draw.text((width / 2, 46), title, fill=CREAM, font=title_font, anchor="mm")
    if subtitle:
        draw.text((width / 2, 80), subtitle, fill=BRASS, font=sub_font, anchor="mm")
    for col in range(7):
        cx = pad_x + col * cell + cell // 2
        draw.text((cx, height - 40), str(col + 1), fill=BRASS, font=num_font, anchor="mm")
        for row in range(6):
            # row 5 is the top of the picture; column lists grow upward from 0.
            stored = 5 - row
            cy = pad_top + row * cell + cell // 2
            disc = columns[col][stored] if stored < len(columns[col]) else 0
            box = (cx - 34, cy - 34, cx + 34, cy + 34)
            draw.ellipse(box, fill=HOLE)
            if not disc:
                continue
            fill = RED if disc == 1 else YELLOW
            hi = RED_HI if disc == 1 else YELLOW_HI
            draw.ellipse((cx - 30, cy - 30, cx + 30, cy + 30), fill=fill)
            draw.ellipse((cx - 16, cy - 20, cx - 2, cy - 8), fill=hi)
            if (col, stored) in win_set:
                draw.ellipse(box, outline=WIN, width=4)
            elif last == (col, stored):
                draw.ellipse(box, outline=CREAM, width=3)
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
