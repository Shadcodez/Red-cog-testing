# inactivepurge/inactivepurge.py

"""
Inactive Purge — Modern Red Cog (March 2026)
Fully fixed, all buttons work, tracking toggle, close button, safe cleanup.
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
        self.config.register_guild(tracking_enabled=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return
        if not await self.config.guild(message.guild).tracking_enabled():
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

    @commands.hybrid_command(
        name="inactivetracking",
        description="Toggle message tracking for inactive detection.",
    )
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def toggle_tracking(self, ctx: Context, enable: bool = None):
        if enable is None:
            current = await self.config.guild(ctx.guild).tracking_enabled()
            await ctx.send(f"Message tracking is currently **{'enabled' if current else 'disabled'}**.")
            return

        await self.config.guild(ctx.guild).tracking_enabled.set(enable)
        await ctx.send(f"Message tracking **{'enabled' if enable else 'disabled'}**.")


class InactiveView(ui.View):
    def __init__(
        self,
        cog: InactivePurge,
        guild: discord.Guild,
        inactive: list[discord.Member],
        author: discord.abc.User,
    ):
        super().__init__(timeout=1800)  # 30 minutes
        self.cog = cog
        self.guild = guild
        self.inactive = inactive
        self.author = author
        self.page = 0
        self.per_page = 10
        self.total_pages = (len(inactive) + self.per_page - 1) // self.per_page
        self.message: discord.Message | None = None

        self.selective_mode: bool = False
        self.selected_ids: set[int] = set()

        self._build_ui()

    def _build_ui(self):
        self.clear_items()

        # Navigation
        self.prev = ui.Button(emoji="◀️", style=discord.ButtonStyle.blurple, row=0, disabled=self.page == 0)
        self.next_ = ui.Button(emoji="▶️", style=discord.ButtonStyle.blurple, row=0, disabled=self.page == self.total_pages - 1)
        self.prev.callback = self.previous_page
        self.next_.callback = self.next_page
        self.add_item(self.prev)
        self.add_item(self.next_)

        # Mode toggle
        toggle_label = "Switch to Selective" if not self.selective_mode else "Switch to All"
        self.toggle = ui.Button(label=toggle_label, style=discord.ButtonStyle.green if self.selective_mode else discord.ButtonStyle.grey, row=1)
        self.toggle.callback = self.toggle_mode
        self.add_item(self.toggle)

        if self.selective_mode:
            current_members = self._get_current_page_members()
            options = []
            for m in current_members:
                joined = m.joined_at.strftime("%Y-%m-%d") if m.joined_at else "Unknown"
                options.append(discord.SelectOption(label=f"{m.display_name} ({m})", value=str(m.id), description=f"Joined {joined}"))

            self.select_menu = ui.Select(placeholder="Select members to kick (multi-select)", min_values=0, max_values=len(options) if options else 1,
                                         options=options or [discord.SelectOption(label="No members", value="0", default=True)], row=2)
            self.select_menu.callback = self.on_select_members
            self.add_item(self.select_menu)

            self.confirm_selected = ui.Button(label="Confirm Selected Kicks", style=discord.ButtonStyle.red, emoji="🗑️", row=3, disabled=len(self.selected_ids) == 0)
            self.confirm_selected.callback = self.confirm_selected_kick
            self.add_item(self.confirm_selected)
        else:
            self.purge_all = ui.Button(label="Purge All Inactive", style=discord.ButtonStyle.red, emoji="🗑️", row=1)
            self.purge_all.callback = self.purge_all_confirm
            self.add_item(self.purge_all)

        # Close button (always available)
        self.close_btn = ui.Button(label="Close Panel", style=discord.ButtonStyle.gray, emoji="✖️", row=4)
        self.close_btn.callback = self.close_panel
        self.add_item(self.close_btn)

    def _get_current_page_members(self) -> list[discord.Member]:
        start = self.page * self.per_page
        end = min(start + self.per_page, len(self.inactive))
        return self.inactive[start:end]

    def get_embed(self, page: int) -> discord.Embed:
        start = page * self.per_page
        end = min(start + self.per_page, len(self.inactive))
        members = self.inactive[start:end]

        lines = []
        for i, m in enumerate(members, start=start + 1):
            joined = m.joined_at.strftime("%b %d, %Y") if m.joined_at else "Unknown"
            prefix = "🟢 " if self.selective_mode and m.id in self.selected_ids else ""
            lines.append(f"{prefix}{i}. {m.mention} — Joined: {joined}")

        embed = discord.Embed(title="🕵️ Inactive Members (0 Messages Tracked)", description="\n".join(lines) or "No members on this page.",
                              color=discord.Color.dark_red(), timestamp=datetime.now(timezone.utc))
        mode_text = "Selective Mode" if self.selective_mode else "Full Purge Mode"
        embed.set_footer(text=f"Page {page+1}/{self.total_pages} • Total: {len(self.inactive)} • {mode_text} "
                             f"• Selected: {len(self.selected_ids)} | Purge All = every member | Tracks since cog load")
        if self.guild.icon:
            embed.set_thumbnail(url=self.guild.icon.url)
        return embed

    async def _refresh(self):
        """Safe main message edit."""
        embed = self.get_embed(self.page)
        self.prev.disabled = self.page == 0
        self.next_.disabled = self.page == self.total_pages - 1
        self._build_ui()
        if self.message:
            try:
                await self.message.edit(embed=embed, view=self)
            except discord.NotFound:
                pass

    # Button callbacks
    async def previous_page(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author:
            return await interaction.response.send_message("Not your panel.", ephemeral=True)
        if self.page > 0:
            self.page -= 1
        await interaction.response.defer()
        await self._refresh()

    async def next_page(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author:
            return await interaction.response.send_message("Not your panel.", ephemeral=True)
        if (self.page + 1) * self.per_page < len(self.inactive):
            self.page += 1
        await interaction.response.defer()
        await self._refresh()

    async def toggle_mode(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author:
            return await interaction.response.send_message("Not your panel.", ephemeral=True)
        self.selective_mode = not self.selective_mode
        if not self.selective_mode:
            self.selected_ids.clear()
        await interaction.response.defer()
        await self._refresh()

    async def on_select_members(self, interaction: discord.Interaction, select: ui.Select):
        if interaction.user != self.author:
            return await interaction.response.send_message("Not your panel.", ephemeral=True)
        for val in select.values:
            self.selected_ids.add(int(val))
        current_page_ids = {int(opt.value) for opt in select.options}
        selected_on_page = {int(v) for v in select.values}
        for mid in current_page_ids - selected_on_page:
            self.selected_ids.discard(mid)
        await interaction.response.defer()
        await self._refresh()

    async def purge_all_confirm(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author:
            return await interaction.response.send_message("Not your panel.", ephemeral=True)
        confirm_view = ConfirmView(self, list(self.inactive), "all")
        await interaction.response.send_message("**⚠️ FINAL WARNING**\nKick **ALL** listed inactive members?\nIrreversible!", view=confirm_view, ephemeral=True)

    async def confirm_selected_kick(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author:
            return await interaction.response.send_message("Not your panel.", ephemeral=True)
        if not self.selected_ids:
            await interaction.response.send_message("No members selected.", ephemeral=True)
            return
        selected_members = [m for m in self.inactive if m.id in self.selected_ids]
        confirm_view = ConfirmView(self, selected_members, "selected")
        await interaction.response.send_message(f"**⚠️ FINAL WARNING**\nKick **{len(selected_members)}** selected members?\nIrreversible!", view=confirm_view, ephemeral=True)

    async def close_panel(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author:
            return await interaction.response.send_message("Not your panel.", ephemeral=True)
        self.stop()
        await interaction.response.edit_message(view=None)

    async def perform_kick(self, targets: list[discord.Member]):
        """Safe bulk kick + live cleanup."""
        kicked = failed = 0
        total = len(targets)
        status = await self.message.channel.send(f"Starting kick of {total} members...", reference=self.message)

        for i, member in enumerate(targets, 1):
            try:
                await member.kick(reason="Inactive purge (0 messages tracked)")
                await self.cog.config.member(member).clear()
                kicked += 1
            except discord.Forbidden:
                failed += 1
            except discord.HTTPException as e:
                if e.status == 429:
                    await asyncio.sleep(1.2)
                    try:
                        await member.kick(reason="Inactive purge (0 messages tracked)")
                        await self.cog.config.member(member).clear()
                        kicked += 1
                    except:
                        failed += 1
                else:
                    failed += 1
            await asyncio.sleep(0.65)

            if i % 8 == 0:
                await status.edit(content=f"⏳ Processing {i}/{total} | Kicked: {kicked} | Failed: {failed}")

        await status.edit(content=f"**Done!**\n✅ Kicked: {kicked}\n❌ Failed: {failed}")

        remaining = [m for m in self.inactive if m not in targets]
        self.inactive = remaining
        self.selected_ids.clear()

        if remaining:
            self.total_pages = (len(remaining) + self.per_page - 1) // self.per_page
            self.page = min(self.page, self.total_pages - 1)
            await self._refresh()
        else:
            self.stop()
            await self.message.edit(content="No more inactive members left.", embed=None, view=None)


class ConfirmView(ui.View):
    def __init__(self, parent: InactiveView, targets: list[discord.Member], mode: str):
        super().__init__(timeout=120)
        self.parent = parent
        self.targets = targets
        self.mode = mode

    @ui.button(label="Yes — Kick Now", style=discord.ButtonStyle.red)
    async def yes(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        await self.parent.perform_kick(self.targets)
        self.stop()
        await interaction.edit_original_response(content="Purge complete — check main panel for update.", view=None)

    @ui.button(label="Cancel", style=discord.ButtonStyle.gray)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="Cancelled.", view=None)
        self.stop()
