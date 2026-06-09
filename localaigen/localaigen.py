import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import io
import base64
import logging
from typing import Optional

log = logging.getLogger("red.localaigen")

class LocalAIImageGen(commands.Cog):
    """Local AI Image Generation using techjarves/Local-AI-Image-Generator backend."""

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.config = bot.get_cog("Config").get_conf(self, identifier=9876543210, force_registration=True)

        default_global = {
            "host": "http://127.0.0.1",
            "port": 8080,
            "default_steps": 20,
            "default_cfg": 7.0,
            "default_width": 512,
            "default_height": 512,
            "default_sampler": "euler_a",
        }
        self.config.register_global(**default_global)
        self.config.register_guild(enabled=False)
        self.config.register_channel(enabled=False)

        self._context_menu = None

    async def cog_load(self):
        # Register context menu properly (fixes decorator issues in cogs)
        self._context_menu = app_commands.ContextMenu(
            name="Generate Image",
            callback=self.generate_from_message,
        )
        self.bot.tree.add_command(self._context_menu)

    async def cog_unload(self):
        if self._context_menu:
            self.bot.tree.remove_command(self._context_menu.name, type=self._context_menu.type)
        await self.session.close()

    # ====================== PERMISSIONS CHECK ======================
    async def is_enabled(self, guild: Optional[discord.Guild], channel: discord.abc.Messageable) -> bool:
        if guild is None:  # DMs
            return True
        guild_enabled = await self.config.guild(guild).enabled()
        if not guild_enabled:
            return False
        channel_enabled = await self.config.channel(channel).enabled()
        return channel_enabled

    # ====================== CONFIG COMMANDS ======================
    @commands.group(name="drawset", invoke_without_command=True)
    @commands.is_owner()
    async def drawset(self, ctx: commands.Context):
        """Configure Local AI Image Generator settings."""
        await ctx.send_help()

    @drawset.command()
    @commands.is_owner()
    async def host(self, ctx: commands.Context, host: str):
        """Set backend host (e.g. http://192.168.1.100)."""
        await self.config.host.set(host.rstrip('/'))
        await ctx.send(f"✅ Backend host set to `{host}`.")

    @drawset.command()
    @commands.is_owner()
    async def port(self, ctx: commands.Context, port: int):
        """Set backend port (default 8080)."""
        await self.config.port.set(port)
        await ctx.send(f"✅ Backend port set to `{port}`.")

    @drawset.command()
    @commands.is_owner()
    async def steps(self, ctx: commands.Context, steps: int):
        """Default inference steps (1-100)."""
        if not 1 <= steps <= 100:
            return await ctx.send("❌ Steps must be between 1 and 100.")
        await self.config.default_steps.set(steps)
        await ctx.send(f"✅ Default steps set to `{steps}`.")

    @drawset.command(name="guild")
    @commands.is_owner()
    async def guild_toggle(self, ctx: commands.Context, state: str):
        """Enable or disable the cog for this server."""
        if ctx.guild is None:
            return await ctx.send("❌ This command can only be used in a server.")
        enabled = state.lower() in ("enable", "on", "true", "yes")
        await self.config.guild(ctx.guild).enabled.set(enabled)
        status = "enabled" if enabled else "disabled"
        await ctx.send(f"✅ Image generation has been **{status}** for this server.")

    @drawset.command(name="channel")
    @commands.has_guild_permissions(manage_channels=True)
    async def channel_toggle(self, ctx: commands.Context, state: str):
        """Enable or disable the cog in this channel."""
        if ctx.guild is None:
            return await ctx.send("❌ This command can only be used in a server.")
        enabled = state.lower() in ("enable", "on", "true", "yes")
        await self.config.channel(ctx.channel).enabled.set(enabled)
        status = "enabled" if enabled else "disabled"
        await ctx.send(f"✅ Image generation has been **{status}** in this channel.")

    # ====================== IMAGE GENERATION ======================
    async def generate_image(self, prompt: str, negative: str = "") -> Optional[bytes]:
        host = await self.config.host()
        port = await self.config.port()
        steps = await self.config.default_steps()
        cfg = await self.config.default_cfg()
        width = await self.config.default_width()
        height = await self.config.default_height()
        sampler = await self.config.default_sampler()

        url = f"{host}:{port}/v1/images/generations"
        payload = {
            "prompt": prompt,
            "negative_prompt": negative,
            "n": 1,
            "size": f"{width}x{height}",
            "response_format": "b64_json",
            "steps": steps,
            "cfg_scale": cfg,
            "sample_method": sampler,
        }

        try:
            async with self.session.post(url, json=payload, timeout=180) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    log.error(f"Backend returned {resp.status}: {error_text[:500]}")
                    return None
                data = await resp.json()
                b64 = None
                if "data" in data and isinstance(data["data"], list):
                    b64 = data["data"][0].get("b64_json")
                elif "images" in data and isinstance(data["images"], list):
                    b64 = data["images"][0]
                if b64:
                    return base64.b64decode(b64)
        except asyncio.TimeoutError:
            log.error("Backend request timed out")
        except Exception as e:
            log.exception("Image generation error")
        return None

    # ====================== LISTENER ======================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        is_mention = self.bot.user in message.mentions
        is_reply = (message.reference and message.reference.resolved and 
                   message.reference.resolved.author == self.bot.user)

        if not (is_mention or is_reply):
            return

        content_lower = message.content.strip().lower()
        if not (content_lower.startswith("draw ") or content_lower.startswith("generate ")):
            return

        if not await self.is_enabled(message.guild, message.channel):
            return

        prompt = message.content.split(maxsplit=1)[1].strip()
        if not prompt:
            return

        async with message.channel.typing():
            status_msg = await message.channel.send(f"🎨 Generating image for: **{prompt[:100]}**...")

            image_bytes = await self.generate_image(prompt)
            if image_bytes:
                file = discord.File(io.BytesIO(image_bytes), filename="generated.png")
                await status_msg.edit(content=None, attachments=[file])
            else:
                await status_msg.edit(content="❌ Failed to generate image. Please check backend and logs.")

    # ====================== HYBRID COMMAND ======================
    @commands.hybrid_command(name="draw")
    @app_commands.describe(prompt="The image generation prompt")
    async def draw(self, ctx: commands.Context, *, prompt: str):
        """Generate an image from a text prompt."""
        if not await self.is_enabled(ctx.guild, ctx.channel):
            return await ctx.send("❌ Image generation is disabled in this server or channel.")

        async with ctx.typing():
            image_bytes = await self.generate_image(prompt)
            if image_bytes:
                file = discord.File(io.BytesIO(image_bytes), filename="generated.png")
                await ctx.send(file=file)
            else:
                await ctx.send("❌ Failed to generate image. Please check backend and logs.")

    # ====================== CONTEXT MENU CALLBACK ======================
    async def generate_from_message(self, interaction: discord.Interaction, message: discord.Message):
        """Context menu callback for generating image from a message."""
        if not await self.is_enabled(interaction.guild, interaction.channel):
            return await interaction.response.send_message(
                "❌ Image generation is disabled in this server or channel.", ephemeral=True)

        await interaction.response.defer()
        prompt = message.content[:500] or "A beautiful scene inspired by this message"
        image_bytes = await self.generate_image(prompt)
        if image_bytes:
            file = discord.File(io.BytesIO(image_bytes), filename="generated.png")
            await interaction.followup.send(file=file)
        else:
            await interaction.followup.send("❌ Failed to generate image.")

async def setup(bot):
    await bot.add_cog(LocalAIImageGen(bot))
