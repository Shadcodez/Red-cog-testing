import discord
from redbot.core import commands
from redbot.core.bot import Red
import aiohttp
import io
from PIL import Image
import numpy as np

# ── Palettes inspired by pixelit.js ──────────────────────────────────────────
THEMES = {
    "blackwhite": {
        "label": "⬛ Black & White",
        "palette": [
            (0, 0, 0), (255, 255, 255),
            (64, 64, 64), (128, 128, 128), (192, 192, 192),
        ],
    },
    "gameboy": {
        "label": "🎮 Game Boy",
        "palette": [
            (15, 56, 15), (48, 98, 48),
            (139, 172, 15), (155, 188, 15),
        ],
    },
    "retro": {
        "label": "📺 Retro",
        "palette": [
            (44, 33, 55), (118, 68, 98), (237, 180, 161),
            (169, 104, 104), (84, 51, 68), (255, 220, 177),
            (220, 140, 100), (140, 80, 58),
        ],
    },
    "neon": {
        "label": "🌈 Neon",
        "palette": [
            (0, 0, 0), (255, 0, 128), (0, 255, 200),
            (128, 0, 255), (255, 255, 0), (0, 200, 255),
            (255, 80, 0), (0, 255, 80),
        ],
    },
    "pastel": {
        "label": "🌸 Pastel",
        "palette": [
            (255, 179, 186), (255, 223, 186), (255, 255, 186),
            (186, 255, 201), (186, 225, 255), (218, 186, 255),
            (255, 186, 255), (255, 255, 255),
        ],
    },
    "c64": {
        "label": "💾 C64",
        "palette": [
            (0, 0, 0), (255, 255, 255), (136, 0, 0), (170, 255, 238),
            (204, 68, 204), (0, 204, 85), (0, 0, 170), (238, 238, 119),
            (221, 136, 85), (102, 68, 0), (255, 119, 119), (51, 51, 51),
            (119, 119, 119), (170, 255, 102), (0, 136, 255), (187, 187, 187),
        ],
    },
    "nes": {
        "label": "🕹️ NES",
        "palette": [
            (124, 124, 124), (0, 0, 252), (0, 0, 188), (68, 40, 188),
            (148, 0, 132), (168, 0, 32), (168, 16, 0), (136, 20, 0),
            (80, 48, 0), (0, 120, 0), (0, 104, 0), (0, 88, 0),
            (0, 64, 88), (0, 0, 0), (255, 255, 255), (252, 188, 176),
        ],
    },
    "msx": {
        "label": "🖥️ MSX",
        "palette": [
            (0, 0, 0), (1, 1, 1), (62, 184, 73), (116, 208, 125),
            (89, 85, 224), (128, 118, 241), (185, 94, 81), (101, 219, 239),
            (219, 101, 89), (255, 137, 125), (204, 195, 94), (222, 208, 135),
            (58, 162, 65), (183, 102, 181), (204, 204, 204), (255, 255, 255),
        ],
    },
    "pico8": {
        "label": "🐱 PICO-8",
        "palette": [
            (0, 0, 0), (29, 43, 83), (126, 37, 83), (0, 135, 81),
            (171, 82, 54), (95, 87, 79), (194, 195, 199), (255, 241, 232),
            (255, 0, 77), (255, 163, 0), (255, 236, 39), (0, 228, 54),
            (41, 173, 255), (131, 118, 156), (255, 119, 168), (255, 204, 170),
        ],
    },
    "apple2": {
        "label": "🍎 Apple II",
        "palette": [
            (0, 0, 0), (114, 38, 64), (64, 51, 127), (228, 52, 254),
            (14, 89, 64), (128, 128, 128), (27, 154, 254), (191, 179, 255),
            (64, 76, 0), (228, 101, 1), (128, 128, 128), (241, 166, 191),
            (27, 203, 1), (191, 204, 128), (141, 217, 191), (255, 255, 255),
        ],
    },
}

PIXEL_SIZES = [4, 8, 12, 16, 24, 32]


# ── Helpers ───────────────────────────────────────────────────────────────────

def closest_color(pixel: tuple, palette: list[tuple]) -> tuple:
    """Return the palette colour closest to `pixel` using squared Euclidean distance."""
    r, g, b = pixel[:3]
    palette_arr = np.array(palette, dtype=np.int32)
    diffs = palette_arr - np.array([r, g, b], dtype=np.int32)
    distances = np.einsum("ij,ij->i", diffs, diffs)
    return tuple(palette[int(np.argmin(distances))])


def pixelate(image: Image.Image, pixel_size: int, palette: list[tuple]) -> Image.Image:
    """
    1. Downscale the image by `pixel_size`.
    2. Map every pixel to the nearest palette colour.
    3. Upscale back to the original size (nearest-neighbour) for the blocky look.
    """
    orig_w, orig_h = image.size
    small_w = max(1, orig_w // pixel_size)
    small_h = max(1, orig_h // pixel_size)

    # Downscale
    small = image.resize((small_w, small_h), Image.LANCZOS).convert("RGB")
    pixels = np.array(small, dtype=np.uint8)

    # Palette-map
    flat = pixels.reshape(-1, 3)
    palette_arr = np.array(palette, dtype=np.int32)
    mapped = np.empty_like(flat)
    for i, px in enumerate(flat):
        diffs = palette_arr - px.astype(np.int32)
        distances = np.einsum("ij,ij->i", diffs, diffs)
        mapped[i] = palette[int(np.argmin(distances))]
    mapped_img = Image.fromarray(mapped.reshape(small_h, small_w, 3), "RGB")

    # Upscale (nearest-neighbour keeps hard pixel edges)
    result = mapped_img.resize((orig_w, orig_h), Image.NEAREST)
    return result


def image_to_bytes(image: Image.Image) -> io.BytesIO:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ── Discord UI ────────────────────────────────────────────────────────────────

class ThemeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=data["label"],
                value=key,
                default=(key == "retro"),
            )
            for key, data in THEMES.items()
        ]
        super().__init__(
            placeholder="🎨 Choose a colour theme…",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_theme = self.values
        # Update default marker
        for opt in self.options:
            opt.default = opt.value == self.values
        await interaction.response.edit_message(
            content=self.view.status_text(), view=self.view
        )


class PixelSizeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=f"{size}px  {'(fine)' if size <= 8 else '(chunky)' if size >= 24 else ''}",
                value=str(size),
                default=(size == 8),
            )
            for size in PIXEL_SIZES
        ]
        super().__init__(
            placeholder="🔲 Choose pixel size…",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_pixel_size = int(self.values)
        for opt in self.options:
            opt.default = opt.value == self.values
        await interaction.response.edit_message(
            content=self.view.status_text(), view=self.view
        )


class PixelArtView(discord.ui.View):
    def __init__(self, image_bytes: bytes, filename: str, author_id: int):
        super().__init__(timeout=120)
        self.image_bytes = image_bytes
        self.filename = filename
        self.author_id = author_id
        self.selected_theme = "retro"
        self.selected_pixel_size = 8

        self.add_item(ThemeSelect())
        self.add_item(PixelSizeSelect())

    # ── Guard: only the command invoker may use the controls ──────────────────
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "These controls belong to someone else!", ephemeral=True
            )
            return False
        return True

    def status_text(self) -> str:
        theme_label = THEMES[self.selected_theme] ["label"]
        return (
            f"**Pixel Art Converter** 🎨\n"
            f"Theme: **{theme_label}** | Pixel size: **{self.selected_pixel_size}px**\n"
            f"Press **Convert** when you're ready!"
        )

    # ── Convert button ────────────────────────────────────────────────────────
    @discord.ui.button(label="✨ Convert", style=discord.ButtonStyle.success, row=2)
    async def convert_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer(thinking=True)

        palette = THEMES[self.selected_theme] ["palette"]
        pixel_size = self.selected_pixel_size

        try:
            img = Image.open(io.BytesIO(self.image_bytes)).convert("RGB")
            result = pixelate(img, pixel_size, palette)
            buf = image_to_bytes(result)

            theme_label = THEMES[self.selected_theme] ["label"]
            await interaction.followup.send(
                content=f"🖼️ Here's your **{theme_label}** pixel art! (`{pixel_size}px` blocks)",
                file=discord.File(buf, filename=f"pixelart_{self.filename}"),
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Something went wrong while converting: `{e}`", ephemeral=True
            )

    # ── Cancel button ─────────────────────────────────────────────────────────
    @discord.ui.button(label="✖ Cancel", style=discord.ButtonStyle.danger, row=2)
    async def cancel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.stop()
        await interaction.response.edit_message(
            content="❌ Pixel art conversion cancelled.", view=None
        )

    async def on_timeout(self):
        # Called when the view times out; silently disable all items
        for item in self.children:
            item.disabled = True


# ── Cog ───────────────────────────────────────────────────────────────────────

class PixelArt(commands.Cog):
    """Convert images to pixel art with selectable colour palettes."""

    def __init__(self, bot: Red):
        self.bot = bot

    @commands.command(name="pixelart", aliases=["pixel", "px"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def pixelart(self, ctx: commands.Context):
        """
        Upload an image and convert it to pixel art.

        Attach an image to your message, or reply to a message that contains one.
        You'll get a menu to pick a colour theme and pixel size before converting.

        **Themes:** Black & White, Game Boy, Retro, Neon, Pastel, C64, NES, MSX, PICO-8, Apple II
        """
        # ── 1. Find the attachment ────────────────────────────────────────────
        attachment = None

        if ctx.message.attachments:
            attachment = ctx.message.attachments
        elif ctx.message.reference:
            ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            if ref_msg.attachments:
                attachment = ref_msg.attachments

        if attachment is None:
            await ctx.send(
                "📎 Please attach an image to your message, "
                "or reply to a message that contains one."
            )
            return

        if not attachment.content_type or not attachment.content_type.startswith("image/"):
            await ctx.send("❌ That file doesn't look like an image.")
            return

        if attachment.size > 8_000_000:  # 8 MB guard
            await ctx.send("❌ Image is too large (max 8 MB).")
            return

        # ── 2. Download the image ─────────────────────────────────────────────
        async with aiohttp.ClientSession() as session:
            async with session.get(attachment.url) as resp:
                if resp.status != 200:
                    await ctx.send("❌ Could not download the image.")
                    return
                image_bytes = await resp.read()

        # ── 3. Send the control panel ─────────────────────────────────────────
        view = PixelArtView(image_bytes, attachment.filename, ctx.author.id)
        embed = discord.Embed(
            title="🎨 Pixel Art Converter",
            description=view.status_text(),
            color=discord.Color.purple(),
        )
        embed.set_footer(text="Select a theme and pixel size, then click Convert!")
        await ctx.send(embed=embed, view=view)


def setup(bot):
    bot.add_cog(PixelArt(bot))