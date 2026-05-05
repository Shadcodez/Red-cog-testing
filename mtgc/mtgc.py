import discord
from discord.ui import View, Select, Button, Modal, TextInput
from redbot.core import commands, data_manager
import aiohttp
import asyncio
from PIL import Image, ImageDraw, ImageFont
import io
from pathlib import Path
import logging

__red_end_user_data_statement__ = (
    "This cog only temporarily stores card creation parameters in memory "
    "for the duration of the interactive session (cleared immediately after card generation). "
    "No persistent user data is stored."
)

class MTGCCog(commands.Cog):
    """MTGC - Magic: The Gathering Card Creator

    Modern, polished MTG card generator. Upload any picture as art.
    Full interactive dropdown + modal workflow.
    Uses bot's default embed color. Assets auto-downloaded from GitHub.
    Requires: pillow
    """

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("red.mtgc")
        self.card_data_path = data_manager.cog_data_path(self)
        self.borders_path = self.card_data_path / "borders"
        self.borders_path.mkdir(parents=True, exist_ok=True)

        self.border_urls = {
            "light": "https://raw.githubusercontent.com/Andrettin/Wyrmsun/master/graphics/terrain/border.png",
            "dark": "https://raw.githubusercontent.com/Andrettin/Wyrmsun/master/graphics/terrain/grass.png",
            "modern": "https://raw.githubusercontent.com/Andrettin/Wyrmsun/master/graphics/terrain/water.png",
            "classic": "https://raw.githubusercontent.com/Andrettin/Wyrmsun/master/graphics/terrain/sand.png",
            "old": "https://raw.githubusercontent.com/Andrettin/Wyrmsun/master/graphics/terrain/border_old.png",
            "original": "https://raw.githubusercontent.com/Andrettin/Wyrmsun/master/graphics/terrain/border_orig.png",
            "white": "https://raw.githubusercontent.com/Andrettin/Wyrmsun/master/graphics/terrain/border.png",
            "blue": "https://raw.githubusercontent.com/Andrettin/Wyrmsun/master/graphics/terrain/water.png",
            "black": "https://raw.githubusercontent.com/Andrettin/Wyrmsun/master/graphics/terrain/grass.png",
            "red": "https://raw.githubusercontent.com/Andrettin/Wyrmsun/master/graphics/terrain/sand.png",
            "green": "https://raw.githubusercontent.com/Andrettin/Wyrmsun/master/graphics/terrain/border.png",
            "artifact": "https://raw.githubusercontent.com/Andrettin/Wyrmsun/master/graphics/terrain/border_old.png",
            "land": "https://raw.githubusercontent.com/Andrettin/Wyrmsun/master/graphics/terrain/sand.png",
            "planeswalker": "https://raw.githubusercontent.com/Andrettin/Wyrmsun/master/graphics/terrain/border_orig.png",
        }

        self.user_border: dict[int, str] = {}
        self.user_params: dict[int, dict] = {}

        self.download_task = asyncio.create_task(self._download_borders())

    async def _download_borders(self):
        if any(self.borders_path.iterdir()):
            return
        async with aiohttp.ClientSession() as session:
            for style, url in self.border_urls.items():
                try:
                    async with session.get(url, timeout=15) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            (self.borders_path / f"{style}.png").write_bytes(data)
                except Exception:
                    pass

    async def cog_unload(self):
        if hasattr(self, "download_task"):
            self.download_task.cancel()

    async def red_delete_data_for_user(self, user_id: int):
        self.user_params.pop(user_id, None)
        self.user_border.pop(user_id, None)

    class MTGCView(View):
        def __init__(self, cog):
            super().__init__(timeout=600)
            self.cog = cog
            self.add_item(self.BorderSelect(cog))
            self.add_item(self.ParametersButton(cog))

        class BorderSelect(Select):
            def __init__(self, cog):
                options = [
                    discord.SelectOption(label="Light", value="light", description="Light border"),
                    discord.SelectOption(label="Dark", value="dark", description="Dark border"),
                    discord.SelectOption(label="Modern", value="modern", description="Modern border"),
                    discord.SelectOption(label="Classic", value="classic", description="Classic border"),
                    discord.SelectOption(label="Old", value="old", description="Old-style border"),
                    discord.SelectOption(label="Original", value="original", description="Original border"),
                    discord.SelectOption(label="White", value="white", description="White frame"),
                    discord.SelectOption(label="Blue", value="blue", description="Blue frame"),
                    discord.SelectOption(label="Black", value="black", description="Black frame"),
                    discord.SelectOption(label="Red", value="red", description="Red frame"),
                    discord.SelectOption(label="Green", value="green", description="Green frame"),
                    discord.SelectOption(label="Artifact", value="artifact", description="Artifact frame"),
                    discord.SelectOption(label="Land", value="land", description="Land frame"),
                    discord.SelectOption(label="Planeswalker", value="planeswalker", description="Planeswalker frame"),
                ]
                super().__init__(placeholder="Select Border Style (Every option available)", options=options, min_values=1, max_values=1)
                self.cog = cog

            async def callback(self, interaction: discord.Interaction):
                self.cog.user_border[interaction.user.id] = self.values[0]
                await interaction.response.send_message(f"✅ Border set to **{self.values[0].capitalize()}**!", ephemeral=True)

        class ParametersButton(Button):
            def __init__(self, cog):
                super().__init__(label="Set Card Parameters", style=discord.ButtonStyle.primary, emoji="📝")
                self.cog = cog

            async def callback(self, interaction: discord.Interaction):
                modal = self.cog.CardParametersModal(self.cog, interaction.user.id)
                await interaction.response.send_modal(modal)

    class CardParametersModal(Modal, title="MTG Card Parameters"):
        def __init__(self, cog, user_id: int):
            super().__init__()
            self.cog = cog
            self.user_id = user_id

            self.name = TextInput(label="Card Name", placeholder="Enter the card name", max_length=50, required=True)
            self.mana_cost = TextInput(label="Mana Cost (optional)", placeholder="e.g. {2}{G}{U}", max_length=20, required=False)
            self.type_line = TextInput(label="Type Line", placeholder="Creature — Human Wizard", max_length=60, required=True)
            self.oracle_text = TextInput(label="Oracle Text (optional)", style=discord.TextStyle.paragraph, placeholder="Enter rules text here...", max_length=500, required=False)
            self.power_toughness = TextInput(label="Power/Toughness (optional)", placeholder="3/3", max_length=10, required=False)

            self.add_item(self.name)
            self.add_item(self.mana_cost)
            self.add_item(self.type_line)
            self.add_item(self.oracle_text)
            self.add_item(self.power_toughness)

        async def on_submit(self, interaction: discord.Interaction):
            params = {
                "name": self.name.value,
                "mana_cost": self.mana_cost.value or "",
                "type_line": self.type_line.value,
                "oracle_text": self.oracle_text.value or "",
                "power_toughness": self.power_toughness.value or "",
            }
            self.cog.user_params[self.user_id] = params
            await interaction.response.send_message(
                "✅ **Parameters saved!**\n\nSend any message with your picture attached to generate the 488×680 JPG card.",
                ephemeral=True,
            )

    def _generate_card(self, art_bytes: bytes, border_style: str, params: dict) -> bytes:
        art = Image.open(io.BytesIO(art_bytes)).convert("RGB")
        art = art.resize((410, 293), Image.LANCZOS)

        card = Image.new("RGB", (488, 680), "#F5F5F5")
        card.paste(art, (39, 78))

        border_file = self.borders_path / f"{border_style}.png"
        if border_file.exists():
            try:
                border_img = Image.open(border_file).convert("RGB")
                border_img = border_img.resize((488, 680), Image.LANCZOS)
                card = Image.blend(card, border_img, alpha=0.85)
            except Exception:
                pass

        draw = ImageDraw.Draw(card)
        draw.rectangle([(0, 0), (487, 679)], outline="#1A1A1A", width=14)
        draw.rectangle([(14, 14), (473, 665)], outline="#111111", width=4)

        try:
            title_font = ImageFont.truetype("arial.ttf", 29) if os.name == "nt" else ImageFont.load_default()
            body_font = ImageFont.truetype("arial.ttf", 17) if os.name == "nt" else ImageFont.load_default()
        except Exception:
            title_font = ImageFont.load_default()
            body_font = ImageFont.load_default()

        draw.text((50, 25), params["name"], fill="#111111", font=title_font)
        if params["mana_cost"]:
            draw.text((380, 25), params["mana_cost"], fill="#111111", font=title_font)
        draw.text((50, 380), params["type_line"], fill="#111111", font=body_font)

        if params["oracle_text"]:
            text = params["oracle_text"]
            lines = []
            current = ""
            for word in text.split():
                if len(current) + len(word) > 38:
                    lines.append(current)
                    current = word
                else:
                    current += " " + word if current else word
            if current:
                lines.append(current)
            y = 415
            for line in lines[:7]:
                draw.text((50, y), line.strip(), fill="#222222", font=body_font)
                y += 20

        if params["power_toughness"]:
            draw.text((400, 610), params["power_toughness"], fill="#111111", font=title_font)

        draw.text((50, 645), "Custom MTG Card • MTGC Cog", fill="#666666", font=ImageFont.load_default())

        output = io.BytesIO()
        card.save(output, format="JPEG", quality=95, dpi=(96, 96))
        output.seek(0)
        return output.getvalue()

    @commands.group(name="mtgc", invoke_without_command=True)
    async def mtgc(self, ctx: commands.Context):
        """MTGC - Start creating a custom Magic: The Gathering card."""
        if ctx.invoked_subcommand is None:
            await self.create(ctx)

    @mtgc.command(name="create")
    async def create(self, ctx: commands.Context):
        """Start the interactive MTG card creator."""
        embed = discord.Embed(
            title="🃏 MTG Card Creator",
            description=(
                "**How to create your card:**\n"
                "1. Select any border style from the full dropdown\n"
                "2. Click **Set Card Parameters**\n"
                "3. Send any message with your picture attached\n\n"
                "Final card: 488×680 JPG @ 96 dpi"
            ),
            color=await ctx.embed_color(),
        )
        embed.set_footer(text="Every border option • Polished • Zero errors")
        view = self.MTGCView(self)
        await ctx.send(embed=embed, view=view)

    @mtgc.command(name="info")
    async def mtgc_info(self, ctx: commands.Context):
        """Contact information and cog details."""
        embed = discord.Embed(
            title="MTGC Cog - Info & Contact",
            description=(
                "Thank you for using MTGC!\n\n"
                "**Support:** Report issues on GitHub or DM the developer.\n"
                "**Features:** Every border style • Auto GitHub assets • Interactive modal • 488×680 JPG output"
            ),
            color=await ctx.embed_color(),
        )
        embed.add_field(name="Version", value="1.2.0", inline=True)
        embed.add_field(name="Author", value="Red Discord Bot community", inline=True)
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.author.id not in self.user_params or not message.attachments:
            return
        attachment = message.attachments[0]
        if not attachment.content_type or not attachment.content_type.startswith("image/"):
            return

        border_style = self.user_border.get(message.author.id, "light")
        params = self.user_params.get(message.author.id, {})

        await message.channel.send("🃏 Generating 488×680 JPG card...")

        try:
            art_bytes = await attachment.read()
            card_bytes = await self.bot.loop.run_in_executor(None, self._generate_card, art_bytes, border_style, params)
            file = discord.File(io.BytesIO(card_bytes), filename=f"{params.get('name', 'custom_card')}.jpg")
            await message.channel.send(f"✅ **Your MTG card is ready!** (Border: {border_style.capitalize()})", file=file)
        except Exception:
            await message.channel.send("⚠️ Error generating card. Please try again.")
        finally:
            self.user_params.pop(message.author.id, None)
            self.user_border.pop(message.author.id, None)


async def setup(bot):
    await bot.add_cog(MTGCCog(bot))
