# Local rewrite of aikaterna/Anismash Retrosign.
# Original posted to Photofunia and was removed for TOS reasons.
# This version renders offline from bundled artwork + Pillow type.

from __future__ import annotations

import asyncio
import re
import unicodedata
from io import BytesIO
from typing import Optional

import discord
from redbot.core import Config, checks, commands

from .renderer import (
    BACKGROUND_IDS,
    BACKGROUND_NAMES,
    STYLE_IDS,
    STYLE_NAMES,
    render_gallery_sheet,
    render_retrosign,
    render_style_sheet,
)


def _parse_choice(value: str, valid: tuple, random_aliases=("random", "rand", "any", "0")):
    raw = value.strip().lower()
    if raw in random_aliases:
        return 0
    if raw.isdigit():
        n = int(raw)
        if n == 0:
            return 0
        if n in valid:
            return n
    return None


class Retrosign(commands.Cog):
    """Make an 80s retro sign from bundled artwork. Originally by Anismash."""

    __red_end_user_data_statement__ = (
        "This cog does not persistently store data or metadata about users."
    )

    async def red_delete_data_for_user(self, **kwargs):
        return

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1381257043, force_registration=True)
        self.config.register_guild(background=0, style=0)
        self.config.register_global(background=0, style=0)

    async def _resolved(self, guild):
        if guild is not None:
            bg = await self.config.guild(guild).background()
            st = await self.config.guild(guild).style()
        else:
            bg = await self.config.background()
            st = await self.config.style()
        return (bg or None), (st or None)

    @staticmethod
    def _parse_lines(content: str):
        texts = [t.strip() for t in content.split(";")]
        if len(texts) == 1:
            if len(texts[0]) <= 15:
                return "", texts[0], ""
            return "\N{CROSS MARK} Your line is too long (14 character limit)"
        if len(texts) == 3:
            texts[0] = unicodedata.normalize("NFD", texts[0]).encode("ascii", "ignore").decode("UTF-8")
            texts[0] = re.sub(r"[^A-Za-z0-9 ]", "", texts[0])
            if len(texts[0]) >= 15:
                return "\N{CROSS MARK} Your first line is too long (14 character limit)"
            if len(texts[1]) >= 13:
                return "\N{CROSS MARK} Your second line is too long (12 character limit)"
            if len(texts[2]) >= 26:
                return "\N{CROSS MARK} Your third line is too long (25 character limit)"
            return texts[0], texts[1], texts[2]
        return "\N{CROSS MARK} please provide three words seperated by ';' or one word"

    async def _send_sign(self, ctx, line1, line2, line3, bg, style):
        async with ctx.typing():
            try:
                buf: BytesIO = await asyncio.to_thread(render_retrosign, line1, line2, line3, bg, style)
            except Exception:
                return await ctx.send("\N{CROSS MARK} Couldn't render that sign. Try shorter text.")
            await ctx.send(file=discord.File(fp=buf, filename="retrosign.png"))

    @commands.cooldown(1, 8, commands.BucketType.guild)
    @commands.command(name="retrosign")
    async def retrosign(self, ctx: commands.Context, *, content: str):
        """Make a retrosign with 3 lines separated by ';' or one word in the middle.

        Examples
        --------
        `[p]retrosign NIGHT`
        `[p]retrosign Electric; Night; Ride`

        Background and type style follow `[p]retrosignset`.
        """
        parsed = self._parse_lines(content)
        if isinstance(parsed, str):
            return await ctx.send(parsed)
        bg, style = await self._resolved(ctx.guild)
        await self._send_sign(ctx, *parsed, bg, style)

    @commands.group(name="retrosignset", invoke_without_command=True)
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def retrosignset(self, ctx: commands.Context):
        """Configure Retrosign artwork for this server.

        Subcommands: `background`, `style`, `show`, `preview`, `styles`, `reset`
        """
        await ctx.send_help()

    @retrosignset.command(name="background", aliases=["bg", "art"])
    async def retrosignset_background(self, ctx: commands.Context, choice: str):
        """Pin a background (1-5) or use `random`.

        1 Wire triangles · 2 Sun and palms · 3 Sunset chevron
        4 Crystal prism · 5 Magenta sunburst
        """
        parsed = _parse_choice(choice, BACKGROUND_IDS)
        if parsed is None:
            listing = ", ".join(f"`{i}` {BACKGROUND_NAMES[i]}" for i in BACKGROUND_IDS)
            return await ctx.send(f"Use `random` or one of: {listing}")
        await self.config.guild(ctx.guild).background.set(parsed)
        if parsed == 0:
            await ctx.send("Background set to **random** (one of the five artworks each render).")
        else:
            await ctx.send(f"Background pinned to **{parsed} — {BACKGROUND_NAMES[parsed]}**.")

    @retrosignset.command(name="style", aliases=["txt", "type"])
    async def retrosignset_style(self, ctx: commands.Context, choice: str):
        """Pin a type style (1-4) or use `random`.

        1 Pink chrome · 2 Ice chrome · 3 Sunset chrome · 4 Violet chrome
        """
        parsed = _parse_choice(choice, STYLE_IDS)
        if parsed is None:
            listing = ", ".join(f"`{i}` {STYLE_NAMES[i]}" for i in STYLE_IDS)
            return await ctx.send(f"Use `random` or one of: {listing}")
        await self.config.guild(ctx.guild).style.set(parsed)
        if parsed == 0:
            await ctx.send("Type style set to **random**.")
        else:
            await ctx.send(f"Type style pinned to **{parsed} — {STYLE_NAMES[parsed]}**.")

    @retrosignset.command(name="show")
    async def retrosignset_show(self, ctx: commands.Context):
        """Show the current background and style settings."""
        bg = await self.config.guild(ctx.guild).background()
        st = await self.config.guild(ctx.guild).style()
        bg_s = "random" if not bg else f"{bg} — {BACKGROUND_NAMES.get(bg, bg)}"
        st_s = "random" if not st else f"{st} — {STYLE_NAMES.get(st, st)}"
        await ctx.send(f"**Retrosign settings for this server**\nBackground: `{bg_s}`\nStyle: `{st_s}`")

    @retrosignset.command(name="preview")
    async def retrosignset_preview(self, ctx: commands.Context):
        """Send a sheet of all five bundled backgrounds."""
        async with ctx.typing():
            buf = await asyncio.to_thread(render_gallery_sheet)
            await ctx.send(
                "Bundled backgrounds (left to right, 1–5).",
                file=discord.File(fp=buf, filename="retrosign-backgrounds.png"),
            )

    @retrosignset.command(name="styles")
    async def retrosignset_styles(self, ctx: commands.Context):
        """Send a sheet of all four type styles."""
        async with ctx.typing():
            buf = await asyncio.to_thread(render_style_sheet)
            await ctx.send(
                "Type styles (1 pink, 2 ice, 3 sunset, 4 violet).",
                file=discord.File(fp=buf, filename="retrosign-styles.png"),
            )

    @retrosignset.command(name="reset")
    async def retrosignset_reset(self, ctx: commands.Context):
        """Reset this server to random background and random style."""
        await self.config.guild(ctx.guild).background.set(0)
        await self.config.guild(ctx.guild).style.set(0)
        await ctx.send("Retrosign settings reset to random background and random style.")

    @commands.command(name="retrosigncustom")
    @commands.cooldown(1, 8, commands.BucketType.guild)
    async def retrosigncustom(self, ctx: commands.Context, background: int, style: int, *, content: str):
        """Render once with a specific background and style, ignoring server pins.

        `[p]retrosigncustom 2 1 I really; LOVE; YOU!`
        """
        if background not in BACKGROUND_IDS:
            return await ctx.send("Background must be 1–5. See `[p]retrosignset preview`.")
        if style not in STYLE_IDS:
            return await ctx.send("Style must be 1–4. See `[p]retrosignset styles`.")
        parsed = self._parse_lines(content)
        if isinstance(parsed, str):
            return await ctx.send(parsed)
        await self._send_sign(ctx, *parsed, background, style)
