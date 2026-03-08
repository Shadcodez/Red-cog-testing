"""
PixelArt Cog for Red Discord Bot
Converts images into pixel art with interactive palette and effect controls.

Processing pipeline (inspired by giventofly/pixelit):
  1. Downscale image by a configurable scale factor (BOX resampling)
  2. Optionally convert to grayscale
  3. Optionally map every pixel to the nearest colour in a chosen palette
  4. Upscale back to display size with NEAREST resampling (blocky pixel look)
"""

import asyncio
import io
import re
from typing import Dict, List, Optional, Tuple

import aiohttp
import discord
from PIL import Image
from redbot.core import commands

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_DIM = 2048          # max width/height after initial resize
MAX_FILE_BYTES = 8_388_608  # 8 MB download limit

URL_REGEX = re.compile(
    r"(https?://[^\s<>\"']+\.(?:png|jpg|jpeg|gif|webp|bmp)(?:[?#][^\s<>\"']*)?)",
    re.IGNORECASE,
)

# Pillow resampling compat (Pillow >=9.1 moved enums)
try:
    _NEAREST = Image.Resampling.NEAREST
    _LANCZOS = Image.Resampling.LANCZOS
    _BOX = Image.Resampling.BOX
except AttributeError:
    _NEAREST = Image.NEAREST
    _LANCZOS = Image.LANCZOS
    _BOX = Image.BOX

# ---------------------------------------------------------------------------
# Colour palettes  (each entry is an (R, G, B) tuple)
# ---------------------------------------------------------------------------

PALETTES: Dict[str, Optional[List[Tuple[int, int, int]]]] = {
    "None": None,
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
    "Game Boy": [
        (15, 56, 15), (48, 98, 48), (139, 172, 15), (155, 188, 15),
    ],
    "Commodore 64": [
        (0, 0, 0), (255, 255, 255), (136, 0, 0), (170, 255, 238),
        (204, 68, 204), (0, 204, 85), (0, 0, 170), (238, 238, 119),
        (221, 136, 85), (102, 68, 0), (255, 119, 119), (51, 51, 51),
        (119, 119, 119), (170, 255, 102), (0, 136, 255), (187, 187, 187),
    ],
    "CGA": [
        (0, 0, 0), (0, 170, 170), (170, 0, 170), (170, 170, 170),
    ],
    "Grayscale": [
        (0, 0, 0), (85, 85, 85), (170, 170, 170), (255, 255, 255),
    ],
    "Sepia": [
        (44, 33, 24), (90, 65, 42), (138, 109, 72), (183, 155, 110),
        (224, 202, 162), (250, 237, 210),
    ],
    "Neon": [
        (0, 0, 0), (255, 0, 102), (0, 255, 102), (0, 102, 255),
        (255, 255, 0), (255, 0, 255), (0, 255, 255), (255, 255, 255),
    ],
    "Pastel": [
        (255, 179, 186), (255, 223, 186), (255, 255, 186),
        (186, 255, 201), (186, 225, 255), (219, 186, 255),
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

PALETTE_DESCRIPTIONS: Dict[str, str] = {
    "None": "Keep original colours",
    "16-Bit": "Classic 16-colour retro palette",
    "PICO-8": "Fantasy console palette",
    "Game Boy": "4-shade green monochrome",
    "Commodore 64": "Classic C64 colours",
    "CGA": "4-colour CGA palette",
    "Grayscale": "4-shade black & white",
    "Sepia": "Warm vintage tones",
    "Neon": "Bright vibrant colours",
    "Pastel": "Soft pastel shades",
    "Autumn": "Warm fall colours",
    "Ocean": "Cool blue-green tones",
}

PALETTE_NAMES: List[str] = list(PALETTES.keys())

# ---------------------------------------------------------------------------
# Image processing helpers
# ---------------------------------------------------------------------------


def _process_image(
    img: Image.Image,
    scale: int,
    palette_name: str,
    grayscale: bool,
) -> Image.Image:
    """Pixelate *img*, optionally mapping colours to a palette."""
    img = img.convert("RGB")
    orig_w, orig_h = img.size

    scale = max(2, min(50, scale))
    small_w = max(1, orig_w // scale)
    small_h = max(1, orig_h // scale)

    # Down-sample (BOX averages every block → better colour representation)
    small = img.resize((small_w, small_h), _BOX)

    if grayscale:
        small = small.convert("L").convert("RGB")

    palette = PALETTES.get(palette_name)
    if palette is not None:
        pixels = small.load()
        for y in range(small_h):
            for x in range(small_w):
                r, g, b = pixels[x, y][:3]
                best = palette[0]
                best_d = float("inf")
                for pr, pg, pb in palette:
                    d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
                    if d < best_d:
                        best_d = d
                        best = (pr, pg, pb)
                pixels[x, y] = best

    # Up-sample with nearest-neighbour for the crisp pixel-art look
    return small.resize((orig_w, orig_h), _NEAREST)


def _image_to_file(img: Image.Image, filename: str = "pixelart.png") -> discord.File:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return discord.File(buf, filename=filename)


# ---------------------------------------------------------------------------
# Discord UI components
# ---------------------------------------------------------------------------


class PaletteSelect(discord.ui.Select):
    """Drop-down for choosing a colour palette."""

    def __init__(self) -> None:
        options = [
            discord.SelectOption(
                label=name,
                description=PALETTE_DESCRIPTIONS.get(name, ""),
                default=(name == "None"),
            )
            for name in PALETTE_NAMES
        ]
        super().__init__(
            placeholder="\U0001f3a8 Select a colour palette\u2026",
            options=options,
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: PixelArtView = self.view  # type: ignore[assignment]
        view.palette_name = self.values[0]
        for opt in self.options:
            opt.default = opt.label == self.values[0]
        await view.refresh(interaction)


class PixelArtView(discord.ui.View):
    """Interactive control panel attached to the pixel-art embed."""

    def __init__(
        self,
        ctx: commands.Context,
        original: Image.Image,
        *,
        timeout: float = 180.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.original = original
        self.scale: int = 8
        self.palette_name: str = "None"
        self.grayscale: bool = False
        self.message: Optional[discord.Message] = None

        self.add_item(PaletteSelect())

    # -- guards & lifecycle --------------------------------------------------

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "Only the command author can use these controls.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True  # type: ignore[union-attr]
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    # -- helpers -------------------------------------------------------------

    def _build_embed(self) -> discord.Embed:
        embed = discord.Embed(title="\U0001f7ea Pixel Art Studio", color=discord.Color.purple())
        lines = (
            f"**Scale:** {self.scale}",
            f"**Palette:** {self.palette_name}",
            f"**Grayscale:** {'\u2705 On' if self.grayscale else '\u274c Off'}",
        )
        embed.description = "  \u2022  ".join(lines)
        embed.set_image(url="attachment://pixelart.png")
        embed.set_footer(text=f"Requested by {self.ctx.author.display_name}")
        return embed

    def _render(self) -> discord.File:
        result = _process_image(self.original, self.scale, self.palette_name, self.grayscale)
        return _image_to_file(result)

    async def refresh(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        loop = asyncio.get_running_loop()
        file = await loop.run_in_executor(None, self._render)
        embed = self._build_embed()
        await interaction.message.edit(embed=embed, attachments=[file], view=self)

    # -- row 1: scale & grayscale -------------------------------------------

    @discord.ui.button(label="Scale \u2212", style=discord.ButtonStyle.secondary, emoji="\u2796", row=1)
    async def scale_down(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.scale = max(2, self.scale - 2)
        await self.refresh(interaction)

    @discord.ui.button(label="Scale +", style=discord.ButtonStyle.secondary, emoji="\u2795", row=1)
    async def scale_up(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.scale = min(50, self.scale + 2)
        await self.refresh(interaction)

    @discord.ui.button(label="Grayscale", style=discord.ButtonStyle.primary, emoji="\U0001f532", row=1)
    async def toggle_grayscale(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.grayscale = not self.grayscale
        button.style = discord.ButtonStyle.success if self.grayscale else discord.ButtonStyle.primary
        await self.refresh(interaction)

    # -- row 2: save & cancel -----------------------------------------------

    @discord.ui.button(label="Save", style=discord.ButtonStyle.success, emoji="\U0001f4be", row=2)
    async def save_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        for child in self.children:
            child.disabled = True  # type: ignore[union-attr]
        await interaction.response.defer()
        loop = asyncio.get_running_loop()
        file = await loop.run_in_executor(None, self._render)
        embed = self._build_embed()
        embed.title = "\U0001f7ea Pixel Art (Saved)"
        await interaction.message.edit(embed=embed, attachments=[file], view=self)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="\u2716\ufe0f", row=2)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer()
        try:
            await interaction.message.delete()
        except discord.HTTPException:
            pass
        self.stop()


# ---------------------------------------------------------------------------
# The cog
# ---------------------------------------------------------------------------


class PixelArt(commands.Cog):
    """Convert images into pixel art with customisable palettes and effects."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None

    async def cog_unload(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()

    # -- internal helpers ----------------------------------------------------

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    @staticmethod
    def _is_image_attachment(att: discord.Attachment) -> bool:
        if att.content_type and att.content_type.startswith("image/"):
            return True
        name = (att.filename or "").lower()
        return name.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"))

    def _resolve_image_url(self, ctx: commands.Context, url: Optional[str]) -> Optional[str]:
        """Try every reasonable source to find an image URL."""
        # 1 – explicit argument
        if url:
            return url

        # 2 – attachments on the invoking message
        for att in ctx.message.attachments:
            if self._is_image_attachment(att):
                return att.url

        # 3 – bare URL typed in the message body
        match = URL_REGEX.search(ctx.message.content)
        if match:
            return match.group(1)

        # 4 – embeds on the invoking message (auto-embeds from pasted URLs)
        for emb in ctx.message.embeds:
            if emb.image and emb.image.url:
                return emb.image.url
            if emb.thumbnail and emb.thumbnail.url:
                return emb.thumbnail.url

        # 5 – replied-to message
        ref = ctx.message.reference
        if ref and isinstance(ref.resolved, discord.Message):
            msg: discord.Message = ref.resolved
            for att in msg.attachments:
                if self._is_image_attachment(att):
                    return att.url
            for emb in msg.embeds:
                if emb.image and emb.image.url:
                    return emb.image.url
                if emb.thumbnail and emb.thumbnail.url:
                    return emb.thumbnail.url
            match = URL_REGEX.search(msg.content or "")
            if match:
                return match.group(1)

        return None

    async def _fetch_image(self, url: str) -> Optional[Image.Image]:
        """Download an image and return it as a PIL Image (RGB, clamped to MAX_DIM)."""
        try:
            session = await self._get_session()
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                if resp.content_length and resp.content_length > MAX_FILE_BYTES:
                    return None
                data = await resp.read()
                if len(data) > MAX_FILE_BYTES:
                    return None

            img = Image.open(io.BytesIO(data))
            img = img.convert("RGB")

            w, h = img.size
            if w > MAX_DIM or h > MAX_DIM:
                ratio = min(MAX_DIM / w, MAX_DIM / h)
                img = img.resize((int(w * ratio), int(h * ratio)), _LANCZOS)
            return img
        except Exception:
            return None

    # -- command -------------------------------------------------------------

    @commands.command(name="pixel")
    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.max_concurrency(3, commands.BucketType.guild, wait=False)
    async def pixel(self, ctx: commands.Context, url: Optional[str] = None) -> None:
        """Convert an image to pixel art.

        **Ways to provide an image:**
        • Upload an image alongside the command
        • Paste an image URL after the command
        • Reply to a message that contains an image
        """
        image_url = self._resolve_image_url(ctx, url)
        if not image_url:
            await ctx.send(
                "\u274c No image found. Attach an image, provide a URL, "
                "or reply to a message containing an image."
            )
            return

        async with ctx.typing():
            img = await self._fetch_image(image_url)
            if img is None:
                await ctx.send(
                    "\u274c Could not download or open that image. "
                    "Make sure the URL is valid and the file is under 8 MB."
                )
                return

            view = PixelArtView(ctx, img)
            loop = asyncio.get_running_loop()
            file = await loop.run_in_executor(None, view._render)
            embed = view._build_embed()

        msg = await ctx.send(embed=embed, file=file, view=view)
        view.message = msg
