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

DISCORD_CDN_PATTERN = re.compile(
    r"(https?://(?:cdn|media)\.discordapp\.(?:com|net)/attachments/[^\s<>\"']+)",
    re.IGNORECASE,
)

# Pillow resampling handling (compatible with Pillow < 10 and >= 10)
try:
    Resampling = Image.Resampling
    NEAREST = Resampling.NEAREST
    BOX = Resampling.BOX
    LANCZOS = Resampling.LANCZOS
except AttributeError:
    # Older Pillow versions
    NEAREST = Image.NEAREST
    BOX = Image.BOX
    LANCZOS = Image.LANCZOS

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
    # ... (your other palettes remain unchanged)
    "Cyberpunk": [
        (10, 10, 18), (25, 10, 45), (50, 20, 70), (75, 0, 130),
        (255, 0, 110), (255, 50, 180), (0, 255, 255), (0, 180, 255),
        (0, 110, 255), (255, 255, 0), (70, 70, 90), (200, 200, 220),
    ],
}

PALETTE_NAMES: List[str] = list(PALETTES.keys())

PALETTE_DESCRIPTIONS: Dict[str, str] = {
    "None": "Keep original colours",
    "16-Bit": "Classic 16-colour retro look",
    # ... (keep your descriptions)
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

    small = img.resize((small_w, small_h), resample=BOX)

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
                pixels[x, y] = best + (255,)  # ensure RGBA if needed

    return small.resize((orig_w, orig_h), resample=NEAREST)


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
            placeholder="\U0001f3a8 Select palette…",
            options=options,
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: PixelArtView = self.view  # type: ignore
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

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
            await interaction.response.send_message(
                "Only the command author can use these controls.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    def build_embed(self) -> discord.Embed:
        grayscale_text = "On 🟢" if self.grayscale else "Off ⚪"
        lines = [
            f"**Scale:** 1/{self.scale}",
            f"**Palette:** {self.palette_name}",
            f"**Grayscale:** {grayscale_text}",
        ]
        embed = discord.Embed(
            title="\U0001f5bc\ufe0f Pixel Art Editor",
            color=0x2F3136,
            description=" • ".join(lines),
        )
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

    # ── Buttons ─────────────────────────────────────────────────────────────

    @discord.ui.button(
        label="Scale −", style=discord.ButtonStyle.secondary, emoji="➖", row=1
    )
    async def scale_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.scale = max(2, self.scale - 2)
        await self.refresh(interaction)

    @discord.ui.button(
        label="Scale +", style=discord.ButtonStyle.secondary, emoji="➕", row=1
    )
    async def scale_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.scale = min(50, self.scale + 2)
        await self.refresh(interaction)

    @discord.ui.button(
        label="Grayscale Off", style=discord.ButtonStyle.secondary, row=1
    )
    async def toggle_grayscale(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.grayscale = not self.grayscale
        button.label = f"Grayscale {'On' if self.grayscale else 'Off'}"
        button.style = (
            discord.ButtonStyle.success if self.grayscale else discord.ButtonStyle.secondary
        )
        await self.refresh(interaction)

    @discord.ui.button(label="Save", style=discord.ButtonStyle.green, emoji="💾", row=2)
    async def save(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.defer()
        loop = asyncio.get_running_loop()
        file = await loop.run_in_executor(None, self.render)
        embed = self.build_embed()
        embed.title = "\U0001f5bc\ufe0f Pixel Art (Saved)"
        embed.color = discord.Color.green()
        await interaction.message.edit(embed=embed, attachments=[file], view=self)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, emoji="✖", row=2)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
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

    def __init__(self, bot: Red):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None

    async def cog_unload(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    # (the rest of your cog methods — find_image_url, download_image, pixel command —
    #  remain unchanged unless you want further improvements)

    @commands.command(name="pixel")
    @commands.cooldown(1, 12, commands.BucketType.user)
    @commands.max_concurrency(4, commands.BucketType.guild)
    async def pixel(self, ctx: commands.Context, *, url: Optional[str] = None):
        # ... your existing command logic ...
        pass
