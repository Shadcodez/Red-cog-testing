"""
PixelArt Cog for Red Discord Bot
Converts images into pixel art with interactive controls.
"""

import asyncio
import io
import re
from typing import Dict, List, Optional, Tuple

import aiohttp
import discord
from PIL import Image, ImageOps
from redbot.core import commands
from redbot.core.bot import Red

# ============================================================================
# Constants
# ============================================================================

MAX_DIM = 2048
MAX_FILE_BYTES = 8_388_608  # 8 MiB

URL_REGEX = re.compile(
    r"(https?://[^\s<>\"']+\.(?:png|jpg|jpeg|gif|webp|bmp)(?:[?#][^\s<>\"']*)?)",
    re.IGNORECASE,
)

# ============================================================================
# Palettes
# ============================================================================

PALETTES: Dict[str, Optional[List[Tuple[int, int, int]]]] = {
    "None": None,
    "Adaptive 32": None,
    "Adaptive 64": None,
    "Adaptive 128": None,
    "16-Bit": [
        (26, 28, 44), (93, 39, 93), (177, 62, 83), (239, 125, 87),
        (255, 205, 117), (167, 240, 112), (56, 183, 100), (37, 113, 121),
        (41, 54, 111), (59, 93, 201), (65, 166, 246), (115, 239, 247),
        (244, 244, 244), (148, 176, 194), (86, 108, 134), (51, 60, 87),
    ],
    "PICO-8": [
        (0, 0, 0), (29, 43, 83), (126, 37, 83), (0, 135, 81),
        (171, 82, 54), (95, 87, 79), (194, 195, 199), (255, 241, 232),
        (255, 0, 77), (255, 163, 0), (255, 236, 39), (0, 228, 54),
        (41, 173, 255), (131, 118, 156), (255, 119, 168), (255, 204, 170),
    ],
    "Game Boy": [(15, 56, 15), (48, 98, 48), (139, 172, 15), (155, 188, 15)],
    "Commodore 64": [
        (0, 0, 0), (255, 255, 255), (136, 0, 0), (170, 255, 238),
        (204, 68, 204), (0, 204, 85), (0, 0, 170), (238, 238, 119),
        (221, 136, 85), (102, 68, 0), (255, 119, 119), (51, 51, 51),
        (119, 119, 119), (170, 255, 102), (0, 136, 255), (187, 187, 187),
    ],
    "CGA": [(0, 0, 0), (0, 170, 170), (170, 0, 170), (170, 170, 170)],
    "Grayscale": [(0, 0, 0), (85, 85, 85), (170, 170, 170), (255, 255, 255)],
    "Sepia": [
        (44, 33, 24), (90, 65, 42), (138, 109, 72), (183, 155, 110),
        (224, 202, 162), (250, 237, 210),
    ],
    "Neon": [
        (0, 0, 0), (255, 0, 102), (0, 255, 102), (0, 102, 255),
        (255, 255, 0), (255, 0, 255), (0, 255, 255), (255, 255, 255),
    ],
    "Pastel": [
        (249, 206, 238), (224, 205, 255), (193, 240, 251),
        (220, 249, 168), (255, 235, 175),
    ],
    "Autumn": [
        (43, 24, 11), (97, 49, 24), (164, 74, 30), (204, 119, 34),
        (230, 172, 51), (189, 140, 60), (107, 86, 47), (56, 61, 38),
    ],
    "Ocean": [
        (0, 22, 51), (0, 49, 83), (0, 84, 119), (0, 131, 143),
        (0, 180, 170), (100, 217, 197), (178, 236, 225), (240, 255, 250),
    ],
}

PALETTE_DESCRIPTIONS = {
    "None": "Keep original colours (widest range)",
    "Adaptive 32": "Image chooses best 32 colors + dither (rich look)",
    "Adaptive 64": "Image chooses best 64 colors + dither (good detail)",
    "Adaptive 128": "Image chooses best 128 colors + dither (very colorful)",
    "16-Bit": "Classic 16-colour retro look",
    "PICO-8": "Fantasy console palette",
    "Game Boy": "Classic 4-shade green monochrome",
    "Commodore 64": "Authentic C64 colours",
    "CGA": "Original 4-colour CGA mode",
    "Grayscale": "4-shade black & white",
    "Sepia": "Warm vintage photo tones",
    "Neon": "Bright glowing colours",
    "Pastel": "Soft Easter/spring pastels",
    "Autumn": "Warm fall season tones",
    "Ocean": "Cool blue-green aquatic palette",
}

# ============================================================================
# Image Processing
# ============================================================================

def process_image(img: Image.Image, scale: int, palette_name: str, grayscale: bool) -> Image.Image:
    img = img.convert("RGB")
    orig_w, orig_h = img.size

    scale = max(2, min(50, scale))
    small_w, small_h = max(1, orig_w // scale), max(1, orig_h // scale)

    small = img.resize((small_w, small_h), Image.BOX)

    if grayscale:
        small = ImageOps.grayscale(small).convert("RGB")

    if palette_name == "None":
        pass

    elif palette_name.startswith("Adaptive"):
        try:
            n_colors = int(palette_name.split()[-1])
            n_colors = max(8, min(256, n_colors))
        except:
            n_colors = 64

        small = small.quantize(
            colors=n_colors,
            method=0,  # MEDIANCUT
            dither=1   # FLOYDSTEINBERG
        ).convert("RGB")

    else:
        palette = PALETTES.get(palette_name)
        if palette:
            pixels = small.load()
            for y in range(small_h):
                for x in range(small_w):
                    r, g, b = pixels[x, y]
                    best = min(palette, key=lambda c: (r-c[0])**2 + (g-c[1])**2 + (b-c[2])**2)
                    pixels[x, y] = best

    return small.resize((orig_w, orig_h), Image.NEAREST)


def to_discord_file(img: Image.Image, filename: str = "pixelart.png") -> discord.File:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return discord.File(buf, filename=filename)

# ============================================================================
# UI
# ============================================================================

class PaletteSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=k, description=v, default=(k == "None"))
            for k, v in PALETTE_DESCRIPTIONS.items()
            if not k.startswith("Adaptive")
        ]
        super().__init__(
            placeholder="🎨 Select fixed palette…",
            options=options,
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        view: PixelArtView = self.view
        view.palette_name = self.values[0]
        view.adaptive_mode = None
        for o in self.options:
            o.default = o.label == self.values[0]
        await view.refresh(interaction)


class PixelArtView(discord.ui.View):
    def __init__(self, ctx: commands.Context, original: Image.Image, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.original = original
        self.scale = 8
        self.palette_name = "None"
        self.adaptive_mode: Optional[str] = None
        self.grayscale = False
        self.message: Optional[discord.Message] = None

        self.add_item(PaletteSelect())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("Only the command author can use this.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass

    def build_embed(self) -> discord.Embed:
        current = self.adaptive_mode or self.palette_name
        embed = discord.Embed(title="🖼️ Pixel Art Editor", color=0x2F3136)
        embed.description = f"**Scale:** 1/{self.scale} • **Mode:** {current} • **Grayscale:** {'On' if self.grayscale else 'Off'}"
        embed.set_image(url="attachment://pixelart.png")
        embed.set_footer(text=f"By {self.ctx.author.display_name}")
        return embed

    def render(self) -> discord.File:
        mode = self.adaptive_mode or self.palette_name
        result = process_image(self.original, self.scale, mode, self.grayscale)
        return to_discord_file(result)

    async def refresh(self, interaction: discord.Interaction):
        await interaction.response.defer()

        for child in self.children:
            if isinstance(child, discord.ui.Button):
                cid = getattr(child, "custom_id", None)
                if cid == "adaptive_32":
                    child.style = discord.ButtonStyle.success if self.adaptive_mode == "32" else discord.ButtonStyle.secondary
                elif cid == "adaptive_64":
                    child.style = discord.ButtonStyle.success if self.adaptive_mode == "64" else discord.ButtonStyle.secondary
                elif cid == "adaptive_128":
                    child.style = discord.ButtonStyle.success if self.adaptive_mode == "128" else discord.ButtonStyle.secondary
                elif child.label.startswith("Grayscale"):
                    child.label = f"Grayscale {'On' if self.grayscale else 'Off'}"
                    child.style = discord.ButtonStyle.success if self.grayscale else discord.ButtonStyle.secondary

        for child in self.children:
            if isinstance(child, discord.ui.Select):
                child.disabled = bool(self.adaptive_mode)

        file = await asyncio.to_thread(self.render)
        embed = self.build_embed()
        await interaction.message.edit(embed=embed, attachments=[file], view=self)

    # Buttons
    @discord.ui.button(label="Scale −", style=discord.ButtonStyle.secondary, emoji="➖", row=1)
    async def scale_down(self, i: discord.Interaction, _):
        self.scale = max(2, self.scale - 2)
        await self.refresh(i)

    @discord.ui.button(label="Scale +", style=discord.ButtonStyle.secondary, emoji="➕", row=1)
    async def scale_up(self, i: discord.Interaction, _):
        self.scale = min(50, self.scale + 2)
        await self.refresh(i)

    @discord.ui.button(label="Grayscale Off", style=discord.ButtonStyle.secondary, row=1)
    async def toggle_grayscale(self, i: discord.Interaction, btn: discord.ui.Button):
        self.grayscale = not self.grayscale
        await self.refresh(i)

    @discord.ui.button(label="Adaptive 32", style=discord.ButtonStyle.secondary, row=1, custom_id="adaptive_32")
    async def adaptive_32(self, i: discord.Interaction, _):
        self.adaptive_mode = "32"
        self.palette_name = "None"
        await self.refresh(i)

    @discord.ui.button(label="Adaptive 64", style=discord.ButtonStyle.secondary, row=1, custom_id="adaptive_64")
    async def adaptive_64(self, i: discord.Interaction, _):
        self.adaptive_mode = "64"
        self.palette_name = "None"
        await self.refresh(i)

    @discord.ui.button(label="Adaptive 128", style=discord.ButtonStyle.secondary, row=1, custom_id="adaptive_128")
    async def adaptive_128(self, i: discord.Interaction, _):
        self.adaptive_mode = "128"
        self.palette_name = "None"
        await self.refresh(i)

    @discord.ui.button(label="Save", style=discord.ButtonStyle.green, emoji="💾", row=2)
    async def save(self, i: discord.Interaction, _):
        for child in self.children:
            child.disabled = True
        await i.response.defer()
        file = await asyncio.to_thread(self.render)
        embed = self.build_embed()
        embed.title = "🖼️ Pixel Art (Saved)"
        embed.color = discord.Color.green()
        await i.message.edit(embed=embed, attachments=[file], view=self)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, emoji="✖", row=2)
    async def cancel(self, i: discord.Interaction, _):
        await i.response.defer()
        try:
            await i.message.delete()
        except:
            pass
        self.stop()

# ============================================================================
# Cog
# ============================================================================

class PixelArt(commands.Cog):
    """Convert images to pixel art."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None

    async def cog_unload(self):
        if self.session:
            await self.session.close()

    async def _session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    @staticmethod
    def is_image(att: discord.Attachment) -> bool:
        if att.content_type and att.content_type.startswith("image/"):
            return True
        return (att.filename or "").lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"))

    async def find_image_url(self, ctx: commands.Context, given: Optional[str]) -> Optional[str]:
        if given:
            return given

        for att in ctx.message.attachments:
            if self.is_image(att):
                return att.url

        m = URL_REGEX.search(ctx.message.content)
        if m:
            return m.group(0)

        for e in ctx.message.embeds:
            if e.image and e.image.url:
                return e.image.url
            if e.thumbnail and e.thumbnail.url:
                return e.thumbnail.url

        ref = ctx.message.reference
        if ref and ref.message_id:
            try:
                if ref.resolved and isinstance(ref.resolved, discord.Message):
                    msg = ref.resolved
                else:
                    ch = ref.channel or ctx.channel
                    msg = await ch.fetch_message(ref.message_id)

                for att in msg.attachments:
                    if self.is_image(att):
                        return att.url

                for e in msg.embeds:
                    if e.image and e.image.url:
                        return e.image.url
                    if e.thumbnail and e.thumbnail.url:
                        return e.thumbnail.url

                if msg.content:
                    m = URL_REGEX.search(msg.content)
                    if m:
                        return m.group(0)
            except:
                pass  # failed to fetch / no access / deleted → no image

        return None

    async def download_image(self, url: str) -> Optional[Image.Image]:
        try:
            session = await self._session()
            async with session.get(url, timeout=15) as r:
                if r.status != 200:
                    return None
                if r.content_length and r.content_length > MAX_FILE_BYTES:
                    return None
                data = await r.read()
                if len(data) > MAX_FILE_BYTES:
                    return None

            img = Image.open(io.BytesIO(data)).convert("RGB")

            w, h = img.size
            if w > MAX_DIM or h > MAX_DIM:
                r = min(MAX_DIM / w, MAX_DIM / h)
                img = img.resize((int(w * r), int(h * r)), Image.LANCZOS)

            return img
        except:
            return None

    @commands.command(name="pixel")
    @commands.cooldown(1, 12, commands.BucketType.user)
    @commands.max_concurrency(4, commands.BucketType.guild)
    async def pixel(self, ctx: commands.Context, *, url: Optional[str] = None):
        """
        Convert an image to pixel art.
        Reply to / attach / link an image, or use [p]pixel alone for help.
        """
        image_url = await self.find_image_url(ctx, url)

        if not image_url:
            if not url and not ctx.message.attachments and not ctx.message.reference:
                await ctx.send_help()
                return
            await ctx.send("Sorry, I was unable to process this request.")
            return

        async with ctx.typing():
            img = await self.download_image(image_url)
            if not img:
                await ctx.send("Sorry, I was unable to process this request.")
                return

            view = PixelArtView(ctx, img)
            file = await asyncio.to_thread(view.render)
            embed = view.build_embed()

            msg = await ctx.send(embed=embed, file=file, view=view)
            view.message = msg
