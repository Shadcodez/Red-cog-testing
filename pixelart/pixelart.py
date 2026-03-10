"""
PixelArt Cog for Red Discord Bot
Converts images into pixel art with interactive controls.
Inspired by giventofly/pixelit.
"""

import asyncio
import io
import re
from typing import Dict, List, Optional, Tuple

import aiohttp
import discord
from PIL import Image
from redbot.core import commands
from redbot.core.bot import Red

# ============================================================================
# Constants
# ============================================================================

MAX_DIMENSION = 2048
MAX_FILE_SIZE = 8_388_608  # 8 MiB

URL_PATTERN = re.compile(
    r"(https?://[^\s<>\"']+\.(?:png|jpg|jpeg|gif|webp|bmp)(?:[?#][^\s<>\"']*)?)",
    re.IGNORECASE,
)

# Fallback pattern for Discord CDN links that may lack a visible extension
DISCORD_CDN_PATTERN = re.compile(
    r"(https?://(?:cdn|media)\.discordapp\.(?:com|net)/attachments/[^\s<>\"']+)",
    re.IGNORECASE,
)

# Pillow resampling (compatible across versions)
try:
    Resampling = Image.Resampling
except AttributeError:
    Resampling = Image

NEAREST = Resampling.NEAREST
BOX = Resampling.BOX
LANCZOS = Resampling.LANCZOS

# ============================================================================
# Color Palettes
# ============================================================================

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
    # Improved Pastel – wider range of soft eggshell / muted tones
    "Pastel": [
        (240, 234, 214),   # eggshell
        (250, 235, 215),   # antique white
        (255, 213, 209),   # pale pink
        (238, 210, 210),   # misty rose
        (255, 218, 193),   # soft peach
        (255, 253, 208),   # cream
        (255, 245, 200),   # pale buttercup
        (200, 235, 210),   # soft mint
        (210, 225, 200),   # pale sage
        (195, 215, 240),   # powder blue
        (215, 200, 235),   # soft lavender
        (225, 205, 230),   # pale lilac
        (235, 220, 200),   # warm linen
        (210, 200, 190),   # soft taupe
    ],
    "Autumn": [
        (43, 24, 11), (97, 49, 24), (164, 74, 30), (204, 119, 34),
        (230, 172, 51), (189, 140, 60), (107, 86, 47), (56, 61, 38),
    ],
    "Ocean": [
        (0, 22, 51), (0, 49, 83), (0, 84, 119), (0, 131, 143),
        (0, 180, 170), (100, 217, 197), (178, 236, 225), (240, 255, 250),
    ],
    # ── New palettes ────────────────────────────────────────────────────────
    "Candy Cane": [
        (255, 255, 255),   # white
        (255, 240, 245),   # lavender blush
        (255, 182, 193),   # light pink
        (255, 105, 120),   # warm pink
        (220, 20, 60),     # crimson
        (178, 34, 34),     # firebrick
        (144, 12, 30),     # deep red
        (152, 224, 173),   # peppermint green
        (240, 248, 240),   # honeydew
    ],
    "Halloween": [
        (0, 0, 0),         # black
        (45, 45, 45),      # dark gray (shadows)
        (101, 67, 33),     # dark brown
        (139, 90, 43),     # medium brown
        (204, 85, 0),      # burnt orange
        (255, 103, 0),     # neon orange
        (255, 204, 0),     # yellow
        (75, 0, 130),      # deep purple accent
    ],
    "Christmas": [
        (0, 80, 0),        # dark green
        (0, 128, 0),       # green
        (34, 139, 34),     # forest green
        (80, 180, 80),     # light green
        (139, 69, 19),     # saddle brown
        (101, 67, 33),     # dark brown
        (178, 34, 34),     # firebrick red
        (220, 20, 60),     # crimson
        (255, 215, 0),     # gold
        (255, 245, 200),   # warm cream
        (255, 255, 255),   # snow white
    ],
    "Cyberpunk": [
        (10, 10, 18),      # void black
        (25, 10, 45),      # deep purple-black
        (50, 20, 70),      # dark violet
        (75, 0, 130),      # indigo
        (255, 0, 110),     # neon pink
        (255, 50, 180),    # hot pink
        (0, 255, 255),     # electric cyan
        (0, 180, 255),     # bright blue
        (0, 110, 255),     # deep neon blue
        (255, 255, 0),     # highlight yellow
        (70, 70, 90),      # steel gray
        (200, 200, 220),   # pale chrome
    ],
}

PALETTE_NAMES: List[str] = list(PALETTES.keys())

PALETTE_DESCRIPTIONS: Dict[str, str] = {
    "None": "Keep original colours",
    "16-Bit": "Classic 16-colour retro look",
    "PICO-8": "Fantasy console palette",
    "Game Boy": "Classic 4-shade green monochrome",
    "Commodore 64": "Authentic C64 colours",
    "CGA": "Original 4-colour CGA mode",
    "Grayscale": "4-shade black & white",
    "Sepia": "Warm vintage photo tones",
    "Neon": "Bright glowing colours",
    "Pastel": "Soft eggshell & muted tones",
    "Autumn": "Warm fall season tones",
    "Ocean": "Cool blue-green aquatic palette",
    "Candy Cane": "Red & white peppermint stripes",
    "Halloween": "Neon orange, brown, yellow & black",
    "Christmas": "Festive greens, reds & gold",
    "Cyberpunk": "Neon pink, cyan & dark violet",
}

# ============================================================================
# Processing
# ============================================================================


def process_image(
    img: Image.Image,
    scale: int,
    palette_name: str,
    grayscale: bool,
) -> Image.Image:
    img = img.convert("RGB")
    orig_w, orig_h = img.size

    scale = max(2, min(50, scale))
    small_w = max(1, orig_w // scale)
    small_h = max(1, orig_h // scale)

    small = img.resize((small_w, small_h), BOX)

    if grayscale:
        small = small.convert("L").convert("RGB")

    palette = PALETTES.get(palette_name)
    if palette:
        pixels = small.load()
        for y in range(small_h):
            for x in range(small_w):
                r, g, b = pixels[x, y][:3]
                best = palette[0]
                best_dist = float("inf")
                for pr, pg, pb in palette:
                    dist = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
                    if dist < best_dist:
                        best_dist = dist
                        best = (pr, pg, pb)
                pixels[x, y] = best

    return small.resize((orig_w, orig_h), NEAREST)


def image_to_file(img: Image.Image, filename: str = "pixelart.png") -> discord.File:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return discord.File(buf, filename=filename)


# ============================================================================
# UI Components
# ============================================================================


class PaletteSelect(discord.ui.Select):
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
            placeholder="\U0001f3a8 Select palette\u2026",
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

    # ── Guards & lifecycle ──────────────────────────────────────────────────

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
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

    # ── Helpers ─────────────────────────────────────────────────────────────

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="\U0001f5bc\ufe0f Pixel Art Editor",
            color=0x2F3136,
        )
        lines = [
            f"**Scale:** 1/{self.scale}",
            f"**Palette:** {self.palette_name}",
            f"**Grayscale:** {'On \U0001f533' if self.grayscale else 'Off \u26aa'}",
        ]
        embed.description = " \u2022 ".join(lines)
        embed.set_image(url="attachment://pixelart.png")
        embed.set_footer(text=f"Requested by {self.ctx.author.display_name}")
        return embed

    def render(self) -> discord.File:
        result = process_image(
            self.original, self.scale, self.palette_name, self.grayscale
        )
        return image_to_file(result)

    async def refresh(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        loop = asyncio.get_running_loop()
        file = await loop.run_in_executor(None, self.render)
        embed = self.build_embed()
        await interaction.message.edit(embed=embed, attachments=[file], view=self)

    # ── Buttons row 1 ──────────────────────────────────────────────────────

    @discord.ui.button(
        label="Scale \u2212",
        style=discord.ButtonStyle.secondary,
        emoji="\u2796",
        row=1,
    )
    async def scale_down(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.scale = max(2, self.scale - 2)
        await self.refresh(interaction)

    @discord.ui.button(
        label="Scale +",
        style=discord.ButtonStyle.secondary,
        emoji="\u2795",
        row=1,
    )
    async def scale_up(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.scale = min(50, self.scale + 2)
        await self.refresh(interaction)

    @discord.ui.button(
        label="Grayscale Off",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def toggle_grayscale(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.grayscale = not self.grayscale
        button.label = f"Grayscale {'On' if self.grayscale else 'Off'}"
        button.style = (
            discord.ButtonStyle.success
            if self.grayscale
            else discord.ButtonStyle.secondary
        )
        await self.refresh(interaction)

    # ── Buttons row 2 ──────────────────────────────────────────────────────

    @discord.ui.button(
        label="Save",
        style=discord.ButtonStyle.green,
        emoji="\U0001f4be",
        row=2,
    )
    async def save(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        for child in self.children:
            child.disabled = True  # type: ignore[union-attr]
        await interaction.response.defer()
        loop = asyncio.get_running_loop()
        file = await loop.run_in_executor(None, self.render)
        embed = self.build_embed()
        embed.title = "\U0001f5bc\ufe0f Pixel Art (Saved)"
        embed.color = discord.Color.green()
        await interaction.message.edit(embed=embed, attachments=[file], view=self)
        self.stop()

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.red,
        emoji="\u2716",
        row=2,
    )
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer()
        try:
            await interaction.message.delete()
        except discord.HTTPException:
            pass
        self.stop()


# ============================================================================
# Cog
# ============================================================================


class PixelArt(commands.Cog):
    """Convert images to pixel art with adjustable scale, palette and grayscale."""

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None

    async def cog_unload(self) -> None:
        if self.session is not None and not self.session.closed:
            await self.session.close()

    # ── Internal helpers ────────────────────────────────────────────────────

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

    @staticmethod
    def _extract_image_from_message(msg: discord.Message, is_image_att) -> Optional[str]:
        """Return the first image URL found in a Message's attachments,
        embeds, or text content.  Shared logic for both the invoking
        message and a referenced (replied-to) message."""
        for att in msg.attachments:
            if is_image_att(att):
                return att.url

        for emb in msg.embeds:
            if emb.image and emb.image.url:
                return emb.image.url
            if emb.thumbnail and emb.thumbnail.url:
                return emb.thumbnail.url

        if msg.content:
            match = URL_PATTERN.search(msg.content)
            if match:
                return match.group(0)
            match = DISCORD_CDN_PATTERN.search(msg.content)
            if match:
                return match.group(0)

        return None

    async def _resolve_replied_message(
        self, ctx: commands.Context
    ) -> Optional[discord.Message]:
        """Retrieve the replied-to message, fetching it from the API when
        the gateway did not populate ``reference.resolved``."""
        ref = ctx.message.reference
        if ref is None or ref.message_id is None:
            return None

        # If the gateway already resolved it, use that
        if isinstance(ref.resolved, discord.Message):
            return ref.resolved

        # Otherwise fetch it ourselves
        try:
            return await ctx.channel.fetch_message(ref.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

    async def find_image_url(
        self, ctx: commands.Context, given_url: Optional[str]
    ) -> Optional[str]:
        """Try every reasonable source to find an image URL."""

        # 1 – explicit argument
        if given_url:
            return given_url

        # 2 – the invoking message itself (attachments / embeds / text)
        found = self._extract_image_from_message(ctx.message, self._is_image_attachment)
        if found:
            return found

        # 3 – replied-to message (fetch if not cached)
        replied = await self._resolve_replied_message(ctx)
        if replied is not None:
            found = self._extract_image_from_message(replied, self._is_image_attachment)
            if found:
                return found

        return None

    async def download_image(self, url: str) -> Optional[Image.Image]:
        try:
            session = await self._get_session()
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    return None
                if resp.content_length and resp.content_length > MAX_FILE_SIZE:
                    return None
                data = await resp.read()
                if len(data) > MAX_FILE_SIZE:
                    return None

            img = Image.open(io.BytesIO(data))
            img = img.convert("RGB")

            w, h = img.size
            if w > MAX_DIMENSION or h > MAX_DIMENSION:
                ratio = min(MAX_DIMENSION / w, MAX_DIMENSION / h)
                img = img.resize((int(w * ratio), int(h * ratio)), LANCZOS)

            return img
        except Exception:
            return None

    # ── Command ─────────────────────────────────────────────────────────────

    @commands.command(name="pixel")
    @commands.cooldown(1, 12, commands.BucketType.user)
    @commands.max_concurrency(4, commands.BucketType.guild)
    async def pixel(self, ctx: commands.Context, *, url: Optional[str] = None) -> None:
        """
        Convert an image to pixel art.

        Ways to provide an image:
        \u2022 Attach it to the message
        \u2022 Paste a direct image URL
        \u2022 Reply to a message containing an image
        """
        image_url = await self.find_image_url(ctx, url)
        if not image_url:
            await ctx.send(
                "\u274c No image detected.\n"
                "Attach an image, paste a direct image URL, "
                "or reply to a message with an image."
            )
            return

        async with ctx.typing():
            img = await self.download_image(image_url)
            if img is None:
                await ctx.send(
                    "\u274c Failed to download or open the image.\n"
                    "\u2022 URL might be invalid\n"
                    "\u2022 File > 8 MB\n"
                    "\u2022 Not a supported image format"
                )
                return

            view = PixelArtView(ctx, img)
            loop = asyncio.get_running_loop()
            file = await loop.run_in_executor(None, view.render)
            embed = view.build_embed()

            message = await ctx.send(embed=embed, file=file, view=view)
            view.message = message
