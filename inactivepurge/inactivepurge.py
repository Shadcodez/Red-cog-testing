# inactivepurge/inactivepurge.py

"""
Inactive Purge Cog for Red Discord Bot
- Lists members with 0 tracked messages (paginated embed)
- Supports full purge OR selective purge (multi-select dropdown per page)
- Uses hybrid command, discord.ui views + Select menus + buttons
- Safe rate limiting, config cleanup on kick, ownership checks
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
        view.message = msg


class InactiveView(ui.View):
    def __init__(
        self,
        cog: InactivePurge,
        guild: discord.Guild,
        inactive: list[discord.Member],
        author: discord.abc.User,
    ):
        super().__init__(timeout=900)  # 15 minutes
        self.cog = cog
        self.guild = guild
        self.inactive = inactive
        self.author = author
        self.page = 0
        self.per_page = 10
        self.total_pages = (len(inactive) + self.per_page - 1) // self.per_page
        self.message: discord.Message | None = None

        # Selective mode state
        self.selective_mode: bool = False
        self.selected_ids: set[int] = set()  # accumulated selected member IDs

        self._build_ui()

    def _build_ui(self):
        """Rebuild components based on current mode."""
        self.clear_items()

        # Page navigation
        self.prev = ui.Button(
            emoji="◀️", style=discord.ButtonStyle.blurple, row=0, disabled=self.page == 0
        )
        self.next_ = ui.Button(
            emoji="▶️", style=discord.ButtonStyle.blurple, row=0,
            disabled=self.page == self.total_pages - 1
        )
        self.prev.callback = self.previous_page
        self.next_.callback = self.next_page
        self.add_item(self.prev)
        self.add_item(self.next_)

        # Mode toggle
        toggle_label = "Switch to Selective" if not self.selective_mode else "Switch to All"
        self.toggle = ui.Button(
            label=toggle_label,
            style=discord.ButtonStyle.green if self.selective_mode else discord.ButtonStyle.grey,
            row=1
        )
        self.toggle.callback = self.toggle_mode
        self.add_item(self.toggle)

        if self.selective_mode:
            # Multi-select dropdown for current page
            current_members = self._get_current_page_members()
            options = [
                discord.SelectOption(
                    label=f"{m.display_name} ({m})",
                    value=str(m.id),
                    description=f"Joined {m.joined_at.strftime('%
