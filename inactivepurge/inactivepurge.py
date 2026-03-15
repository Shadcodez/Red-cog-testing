# inactivepurge/inactivepurge.py

"""
Inactive Purge Cog for Red Discord Bot (2026)
- Paginated list of members with 0 messages
- Full purge OR selective purge (multi-select dropdown)
- Safe rate limits, config cleanup, ownership protection
"""

from datetime import datetime, timezone
import asyncio

import discord
from discord import ui
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.commands import Context


class InactivePurge(commands.Cog):
    """List & purge inactive members (0 messages tracked)."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)
        self.config.register_member(messages=0)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return
        try:
            count = await self.config.member(message.author).messages()
            await self.config.member(message.author).messages.set(count + 1)
        except Exception:
            pass

    @commands.hybrid_command(
        name="inactive",
        with_app_command=True,
        description="List members with 0 messages + purge (full or selective).",
    )
    @commands.guild_only()
    @commands.admin_or_permissions(kick_members=True)
    async def inactive_command(self, ctx: Context):
        if ctx.interaction:
            await ctx.defer(ephemeral=False)

        guild = ctx.guild
        try:
            data = await self.config.all_members(guild)
        except Exception:
            await ctx.send("❌ Failed to load member data.")
            return

        inactive = [
            m for m in guild.members
            if not m.bot and (data.get(m.id) or {}).get("messages", 0) == 0
        ]

        if not inactive:
            await ctx.send("✅ No inactive members found!")
            return

        inactive.sort(key=lambda m: m.joined_at or datetime(1900, 1, 1, tzinfo=timezone.utc))

        view = InactiveView(self, guild, inactive, ctx.author)
        embed = view.get_embed(0)

        if view.total_pages <= 1:
            view.prev.disabled = True
            view.next_.disabled = True

        msg = await ctx.send(embed=embed, view=view)
        view.message =
