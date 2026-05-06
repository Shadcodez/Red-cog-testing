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
    """MTGC — Magic: The Gathering Card Creator (Realistic Gradient Edition)"""

    __author__ = "SHADOW6six"
    __version__ = "1.0.0"

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
        for style, palette in BORDER_PALETTES.items():
            path = self.borders_path / f"{style}.png"
            if path.exists():
                continue
            try:
                await asyncio.to_thread(self._save_border_file, path, palette)
                generated += 1
            except Exception as exc:
                self.logger.error("MTGC: Failed to generate '%s' border: %s", style, exc)
        if generated:
            self.logger.info("MTGC: Generated %d border frame(s).", generated)

    @staticmethod
    def _save_border_file(path: Path, palette: dict):
        img = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        draw.rectangle([(0, 0), (CARD_W - 1, CARD_H - 1)], fill=palette["outer"])

        frame_box = (8, 8, CARD_W - 9, CARD_H - 9)
        _draw_vertical_gradient(draw, frame_box, palette["frame"], _lighten_color(palette["frame"]))

        draw.rectangle(frame_box, outline=palette["accent"], width=2)

        _rounded_rect(draw, [(18, 16), (CARD_W - 19, 56)], radius=5, fill=palette["name_bg"], outline=palette["accent"], width=1)
        _rounded_rect(draw, [(18, 366), (CARD_W - 19, 398)], radius=5, fill=palette["name_bg"], outline=palette["accent"], width=1)
        _rounded_rect(draw, [(24, 406), (CARD_W - 25, 614)], radius=5, fill=palette["text_bg"], outline=palette["accent"], width=1)
        _rounded_rect(draw, [(CARD_W - 128, 620), (CARD_W - 20, 656)], radius=6, fill=palette["name_bg"], outline=palette["accent"], width=2)
        draw.rectangle([(18, 660), (CARD_W - 19, CARD_H - 10)], fill=palette["name_bg"])

        transparent_art = Image.new("RGBA", (ART_W, ART_H), (0, 0, 0, 0))
        img.paste(transparent_art, (ART_X, ART_Y))

        draw.rectangle([(ART_X - 3, ART_Y - 3), (ART_X + ART_W + 2, ART_Y + ART_H + 2)], outline=palette["accent"], width=2)
        draw.rectangle([(ART_X - 1, ART_Y - 1), (ART_X + ART_W, ART_Y + ART_H)], outline=palette["outer"], width=1)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        path.write_bytes(buf.getvalue())

    async def cog_unload(self):
        if self._init_task and not self._init_task.done():
            self._init_task.cancel()
        self._sessions.clear()

    async def red_delete_data_for_user(self, *, requester: str, user_id: int):
        self._sessions.pop(user_id, None)

    def _render_card(self, art_bytes: bytes, border_style: str, params: dict) -> bytes:
        palette = BORDER_PALETTES.get(border_style, BORDER_PALETTES["light"])

        art = Image.open(io.BytesIO(art_bytes)).convert("RGBA")
        art = art.resize((ART_W, ART_H), Image.LANCZOS)

        card = Image.new("RGBA", (CARD_W, CARD_H), (235, 235, 235, 255))
        card.paste(art, (ART_X, ART_Y), art)

        border_path = self.borders_path / f"{border_style}.png"
        if border_path.exists():
            border_img = Image.open(border_path).convert("RGBA")
        else:
            border_img = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
            fallback_draw = ImageDraw.Draw(border_img)
            fallback_draw.rectangle([(0, 0), (CARD_W - 1, CARD_H - 1)], outline="#1A1A1A", width=10)

        card = Image.alpha_composite(card, border_img)
        card_rgb = card.convert("RGB")
        draw = ImageDraw.Draw(card_rgb)

        title_font = _get_font(20)
        type_font = _get_font(16)
        body_font = _get_font(15)
        small_font = _get_font(10)

        title_color = palette["title_color"]
        body_color = palette["body_color"]
        shadow_color = "#1A1A1A"

        def _shadow_text(x, y, text, font, color):
            draw.text((x + 1, y + 1), text, fill=shadow_color, font=font)
            draw.text((x, y), text, fill=color, font=font)

        name = params.get("name", "Unnamed Card")
        _shadow_text(28, 26, name, title_font, title_color)

        mana = params.get("mana_cost", "")
        if mana:
            mana_w = _text_width(draw, mana, title_font)
            _shadow_text(CARD_W - 28 - mana_w, 26, mana, title_font, title_color)

        type_line = params.get("type_line", "")
        if type_line:
            _shadow_text(28, 374, type_line, type_font, title_color)

        oracle = params.get("oracle_text", "")
        if oracle:
            wrapped_lines = textwrap.wrap(oracle, width=46)
            y_pos = 416
            for line in wrapped_lines[:10]:
                _shadow_text(34, y_pos, line, body_font, body_color)
                y_pos += 20

        pt = params.get("power_toughness", "")
        if pt:
            pt_w = _text_width(draw, pt, title_font)
            pt_box_center = CARD_W - 128 + 54
            _shadow_text(pt_box_center - pt_w // 2, 629, pt, title_font, title_color)

        draw.text((24, 663), "Custom MTG Card • MTGC", fill="#888888", font=small_font)

        output = io.BytesIO()
        card_rgb.save(output, format="JPEG", quality=98)
        output.seek(0)
        return output.getvalue()

    async def _get_embed_color(self, destination) -> discord.Color:
        try:
            return await self.bot.get_embed_color(destination)
        except (AttributeError, TypeError):
            pass
        try:
            return await self.bot.get_embed_colour(destination)
        except (AttributeError, TypeError):
            return discord.Color(0x2B2D31)

    def _build_creator_view(self) -> View:
        view = View(timeout=600)
        view.add_item(_BorderDropdown(self))
        view.add_item(_ParamsButton(self))
        view.add_item(_GenerateButton(self))
        view.add_item(_CancelButton(self))
        return view

    # ─── Commands ───────────────────────────────────────────────────────

    @commands.group(name="mtgc", invoke_without_command=True)
    async def mtgc(self, ctx: commands.Context):
        """MTGC — Magic: The Gathering Card Creator

        Running this command without a subcommand launches the interactive creator.
        """
        await self.mtgc_create(ctx)

    @mtgc.command(name="create")
    async def mtgc_create(self, ctx: commands.Context):
        """Launch the interactive MTG card creator."""
        self._sessions.pop(ctx.author.id, None)

        embed = discord.Embed(
            title="🃏 MTG Card Creator",
            description=(
                "Create a custom Magic: The Gathering card in three easy steps:\n\n"
                "🎨 **Step 1** — Select a frame style from the dropdown\n"
                "📝 **Step 2** — Click **Set Parameters** to fill in card details\n"
                "🖼️ **Step 3** — Click **Upload Art** and send your image\n\n"
                "**Output:** 488×680 JPEG • Gradient borders + shadows"
            ),
            color=await ctx.embed_color(),
        )
        embed.set_footer(text="Session expires in 10 minutes • MTGC v2.3.0")
        view = self._build_creator_view()

        creator_msg = await ctx.send(embed=embed, view=view)
        self._sessions[ctx.author.id] = {"creator_msg_id": creator_msg.id}

    @mtgc.command(name="borders")
    async def mtgc_borders(self, ctx: commands.Context):
        """List all available frame styles."""
        lines = [f"{palette['emoji']} **{style.capitalize()}** — {palette['desc']}" for style, palette in BORDER_PALETTES.items()]
        embed = discord.Embed(
            title="🎨 Available Frame Styles",
            description="\n".join(lines),
            color=await ctx.embed_color(),
        )
        embed.set_footer(text="Use [p]mtgc create to start building your card")
        await ctx.send(embed=embed)

    # ─── Message Listener ───────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        uid = message.author.id
        session = self._sessions.get(uid)
        if not session or not session.get("awaiting"):
            return
        if session.get("channel") and message.channel.id != session["channel"]:
            return
        if not message.attachments:
            return

        attachment = next((att for att in message.attachments if att.content_type and att.content_type.startswith("image/")), None)
        if not attachment:
            return

        creator_msg_id = session.get("creator_msg_id")
        border_style = session.get("border", "light")
        params = session.get("params", {})
        self._sessions.pop(uid, None)

        if not params:
            await message.reply("⚠️ No card parameters found. Please click **Set Parameters** first.", mention_author=False)
            return

        progress_msg = await message.channel.send("🃏 Rendering your realistic card…")

        try:
            art_bytes = await attachment.read()
            card_bytes = await asyncio.to_thread(self._render_card, art_bytes, border_style, params)

            safe_name = "".join(c for c in params.get("name", "card") if c.isalnum() or c in " _-").strip()
            filename = (safe_name.replace(" ", "_") or "mtgc_card") + ".jpg"

            file = discord.File(io.BytesIO(card_bytes), filename=filename)

            color = await self._get_embed_color(message.channel)
            embed = discord.Embed(
                title=f"🃏 {params.get('name', 'Custom Card')}",
                description=f"**Frame:** {border_style.capitalize()}\n**Type:** {params.get('type_line', '—')}",
                color=color,
            )
            embed.set_image(url=f"attachment://{filename}")
            embed.set_footer(text="MTGC • 488×680 JPEG • Gradient + Shadows")

            await progress_msg.edit(content=None, embed=embed, attachments=[file])

            # Clean up the interactive creator embed
            if creator_msg_id:
                try:
                    creator_msg = await message.channel.fetch_message(creator_msg_id)
                    await creator_msg.delete()
                except (discord.NotFound, discord.HTTPException):
                    pass

        except Exception as exc:
            self.logger.error("MTGC: Card render failed", exc_info=True)
            await progress_msg.edit(content="⚠️ An error occurred while rendering your card.")

    # ─── UI Components ──────────────────────────────────────────────────────────

class _BorderDropdown(Select):
    def __init__(self, cog: MTGCCog):
        self.cog = cog
        options = [discord.SelectOption(label=style.capitalize(), value=style, description=palette["desc"], emoji=palette["emoji"]) for style, palette in BORDER_PALETTES.items()]
        super().__init__(placeholder="🎨 Step 1: Select frame style…", options=options, min_values=1, max_values=1, row=0)

    async def callback(self, interaction: discord.Interaction):
        uid = interaction.user.id
        if uid not in self.cog._sessions:
            self.cog._sessions[uid] = {}
        self.cog._sessions[uid]["border"] = self.values[0]
        await interaction.response.send_message(f"✅ Frame set to **{self.values[0].capitalize()}**. Proceed to Step 2!", ephemeral=True)


class _ParamsButton(Button):
    def __init__(self, cog: MTGCCog):
        super().__init__(label="Step 2: Set Parameters", style=discord.ButtonStyle.primary, emoji="📝", row=1)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        modal = _ParamsModal(self.cog, interaction.user.id)
        await interaction.response.send_modal(modal)


class _GenerateButton(Button):
    def __init__(self, cog: MTGCCog):
        super().__init__(label="Step 3: Upload Art", style=discord.ButtonStyle.success, emoji="🖼️", row=1)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        uid = interaction.user.id
        session = self.cog._sessions.get(uid)

        if not session or "params" not in session:
            await interaction.response.send_message("⚠️ Please complete **Step 2** first (Set Parameters).", ephemeral=True)
            return

        if "border" not in session:
            session["border"] = "light"

        session["awaiting"] = True
        session["channel"] = interaction.channel_id

        await interaction.response.send_message("🖼️ **Upload your art image now!**\nSend a message with an attached image in this channel.", ephemeral=True)


class _CancelButton(Button):
    def __init__(self, cog: MTGCCog):
        super().__init__(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌", row=2)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        self.cog._sessions.pop(interaction.user.id, None)
        await interaction.response.send_message("❌ Session cancelled.", ephemeral=True)

        try:
            await interaction.message.delete()
        except (discord.NotFound, discord.HTTPException):
            pass


class _ParamsModal(Modal, title="📝 Card Parameters"):
    def __init__(self, cog: MTGCCog, user_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.uid = user_id

    name_field = TextInput(label="Card Name", placeholder="e.g. Serra Angel", max_length=40, required=True)
    mana_field = TextInput(label="Mana Cost (blank for lands)", placeholder="e.g. {3}{W}{W}", max_length=25, required=False)
    type_field = TextInput(label="Type Line", placeholder="e.g. Creature — Angel", max_length=55, required=True)
    oracle_field = TextInput(label="Rules Text (optional)", style=discord.TextStyle.paragraph, placeholder="e.g. Flying, vigilance...", max_length=500, required=False)
    pt_field = TextInput(label="Power/Toughness (blank if not creature)", placeholder="e.g. 4/4", max_length=10, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        if self.uid not in self.cog._sessions:
            self.cog._sessions[self.uid] = {}
        self.cog._sessions[self.uid]["params"] = {
            "name": self.name_field.value.strip(),
            "mana_cost": self.mana_field.value.strip(),
            "type_line": self.type_field.value.strip(),
            "oracle_text": self.oracle_field.value.strip(),
            "power_toughness": self.pt_field.value.strip(),
        }
        await interaction.response.send_message("✅ **Parameters saved!** Proceed to **Step 3: Upload Art**.", ephemeral=True)


# ─── Setup ──────────────────────────────────────────────────────────────────

async def setup(bot):
    """Required by Red Discord Bot."""
    cog = MTGCCog(bot)
    await bot.add_cog(cog)
