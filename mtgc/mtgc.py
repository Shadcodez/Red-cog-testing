import asyncio
import io
import logging
import textwrap
from pathlib import Path
from typing import Dict, Optional

import discord
from discord.ui import Button, Modal, Select, TextInput, View
from PIL import Image, ImageDraw, ImageFont
from redbot.core import commands, data_manager

__red_end_user_data_statement__ = (
    "This cog stores no persistent user data. Card creation parameters are held "
    "in memory only for the duration of the interactive session and are cleared "
    "immediately after card generation or session timeout."
)

# ─── Constants ──────────────────────────────────────────────────────────────

CARD_W, CARD_H = 488, 680
ART_X, ART_Y = 34, 64
ART_W, ART_H = 420, 294

# ─── Font Discovery ─────────────────────────────────────────────────────────

_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-M.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/calibri.ttf",
]

_font_cache: Dict[int, ImageFont.FreeTypeFont] = {}


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    if size in _font_cache:
        return _font_cache[size]
    for path in _FONT_PATHS:
        try:
            font = ImageFont.truetype(path, size)
            _font_cache[size] = font
            return font
        except (OSError, IOError):
            continue
    font = ImageFont.load_default()
    _font_cache[size] = font
    return font


def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]
    except AttributeError:
        try:
            w, _ = draw.textsize(text, font=font)
            return w
        except Exception:
            return len(text) * 10


def _rounded_rect(draw: ImageDraw.ImageDraw, coords, radius: int = 0, **kwargs):
    if radius > 0:
        try:
            draw.rounded_rectangle(coords, radius=radius, **kwargs)
            return
        except (AttributeError, TypeError):
            pass
    draw.rectangle(coords, **kwargs)


# ─── Gradient Helpers ───────────────────────────────────────────────────────

def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def _lighten_color(hex_color: str, factor: float = 0.18) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"


def _draw_vertical_gradient(
    draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], color1: str, color2: str
):
    x1, y1, x2, y2 = box
    rgb1 = _hex_to_rgb(color1)
    rgb2 = _hex_to_rgb(color2)
    height = max(1, y2 - y1)
    for i in range(height):
        ratio = i / height
        r = int(rgb1[0] * (1 - ratio) + rgb2[0] * ratio)
        g = int(rgb1[1] * (1 - ratio) + rgb2[1] * ratio)
        b = int(rgb1[2] * (1 - ratio) + rgb2[2] * ratio)
        draw.line([(x1, y1 + i), (x2, y1 + i)], fill=(r, g, b))


# ─── Border Palettes ────────────────────────────────────────────────────────

BORDER_PALETTES = {
    "white": {"outer": "#2B2B2B", "frame": "#F5ECD7", "accent": "#B8A44C", "name_bg": "#FFFDF3", "text_bg": "#FFFEF8", "title_color": "#1A1A1A", "body_color": "#222222", "desc": "White / Plains frame", "emoji": "\u2b1c"},
    "blue": {"outer": "#1A1A2E", "frame": "#0E4C7A", "accent": "#3B9BD4", "name_bg": "#D0E8F8", "text_bg": "#E4F2FC", "title_color": "#0A0A0A", "body_color": "#1A1A1A", "desc": "Blue / Island frame", "emoji": "\U0001f7e6"},
    "black": {"outer": "#0A0A0A", "frame": "#1C1C1C", "accent": "#5A5A5A", "name_bg": "#2E2E2E", "text_bg": "#383838", "title_color": "#E8E8E8", "body_color": "#D0D0D0", "desc": "Black / Swamp frame", "emoji": "\u2b1b"},
    "red": {"outer": "#1A0A0A", "frame": "#8B1A1A", "accent": "#D4443C", "name_bg": "#FCEAE8", "text_bg": "#FDF2F0", "title_color": "#1A1A1A", "body_color": "#222222", "desc": "Red / Mountain frame", "emoji": "\U0001f7e5"},
    "green": {"outer": "#0A1A0A", "frame": "#1B5E2E", "accent": "#2EA84E", "name_bg": "#D8F5E0", "text_bg": "#E8FAF0", "title_color": "#1A1A1A", "body_color": "#222222", "desc": "Green / Forest frame", "emoji": "\U0001f7e9"},
    "gold": {"outer": "#2B2010", "frame": "#A87B20", "accent": "#E8C840", "name_bg": "#FFF8E0", "text_bg": "#FFFCF0", "title_color": "#1A1A1A", "body_color": "#222222", "desc": "Multicolor / Gold frame", "emoji": "\U0001f7e1"},
    "artifact": {"outer": "#2A2A2A", "frame": "#7A7A7A", "accent": "#A8A8A8", "name_bg": "#EAEAEA", "text_bg": "#F4F4F4", "title_color": "#1A1A1A", "body_color": "#222222", "desc": "Colorless / Artifact frame", "emoji": "\u2699\ufe0f"},
    "land": {"outer": "#2B2010", "frame": "#6B5030", "accent": "#B8943C", "name_bg": "#F5ECDA", "text_bg": "#FAF4E8", "title_color": "#1A1A1A", "body_color": "#222222", "desc": "Generic Land frame", "emoji": "\U0001f3d4\ufe0f"},
    "planeswalker": {"outer": "#10081A", "frame": "#3A1A5A", "accent": "#9A5CC8", "name_bg": "#F0E8FA", "text_bg": "#F6F0FD", "title_color": "#1A1A1A", "body_color": "#222222", "desc": "Planeswalker frame", "emoji": "\U0001f52e"},
    "light": {"outer": "#505050", "frame": "#D8D8D8", "accent": "#909090", "name_bg": "#F8F8F8", "text_bg": "#FDFDFD", "title_color": "#1A1A1A", "body_color": "#222222", "desc": "Light neutral frame", "emoji": "\u2600\ufe0f"},
    "dark": {"outer": "#080808", "frame": "#1A1A1A", "accent": "#444444", "name_bg": "#252525", "text_bg": "#2E2E2E", "title_color": "#E8E8E8", "body_color": "#D0D0D0", "desc": "Dark neutral frame", "emoji": "\U0001f319"},
    "modern": {"outer": "#0C0C0C", "frame": "#1A1A1A", "accent": "#C8A84B", "name_bg": "#141414", "text_bg": "#1E1E1E", "title_color": "#F0F0F0", "body_color": "#D8D8D8", "desc": "Sleek modern frame", "emoji": "\u2728"},
    "classic": {"outer": "#3B2F1E", "frame": "#8B7355", "accent": "#C8A84B", "name_bg": "#F2E8D4", "text_bg": "#F8F0E0", "title_color": "#1A1A1A", "body_color": "#222222", "desc": "Traditional brown frame", "emoji": "\U0001f4dc"},
}


# ─── Cog ────────────────────────────────────────────────────────────────────

class MTGCCog(commands.Cog):
    """MTGC — Magic: The Gathering Card Creator (Debug Edition)"""

    __author__ = "MTGC Community"
    __version__ = "2.3.2"

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("red.mtgc")
        self.data_path: Path = data_manager.cog_data_path(self)
        self.borders_path: Path = self.data_path / "borders"
        self.borders_path.mkdir(parents=True, exist_ok=True)

        self._sessions: Dict[int, dict] = {}
        self._init_task: Optional[asyncio.Task] = asyncio.create_task(self._ensure_borders())

    async def _ensure_borders(self):
        generated = 0
        for style, palette
