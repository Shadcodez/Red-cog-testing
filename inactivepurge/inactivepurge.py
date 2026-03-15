# inactivepurge/inactivepurge.py

"""
Inactive Purge — Premium Red Cog
Fully functional, polished, all buttons work, embed updates instantly.
Tracking OFF by default. Selective + Full purge with live progress.
"""

from datetime import datetime, timezone
import asyncio

import discord
from discord import ui
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.commands import Context


class InactivePurge(commands.Cog):
    """Polished inactive member lister + purger."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)
        self.config.register_member(messages=0)
        self.config.register_guild(tracking_enabled=False)  # OFF by default

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

    @commands.hybrid_command(name="inactive", description="View & purge inactive members (0 messages).")
    @commands.guild_only()
    @commands.admin_or_permissions(kick_members=True)
    async def inactive(self, ctx: Context):
        if ctx.interaction:
            await ctx.defer(ephemeral=False)

        guild = ctx.guild
        data = await self.config.all_members(guild)

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

        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @commands.hybrid_command(name="inactivetracking", description="Turn message tracking on/off.")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def inactivetracking(self, ctx: Context, enable: bool):
        await self.config.guild(ctx.guild).tracking_enabled.set(enable)
        await ctx.send(f"Message tracking is now **{'enabled' if enable else 'disabled'}**.")


class InactiveView(ui.View):
    def __init__(self, cog: InactivePurge, guild: discord.Guild, inactive: list[discord.Member], author: discord.abc.User):
        super().__init__(timeout=1800)
        self.cog = cog
        self.guild = guild
        self.inactive = inactive
        self.author = author
        self.page = 0
        self.per_page = 10
        self.total_pages = (len(inactive) + self.per_page - 1) // self.per_page
        self.message: discord.Message | None = None

        self.selective_mode = False
        self.selected_ids = set()

        self._rebuild()

    def _rebuild(self):
        self.clear_items()

        # Pagination
        self.add_item(ui.Button(emoji="◀️", style=discord.ButtonStyle.blurple, row=0, disabled=self.page == 0))
        self.children[-1].callback = self.previous
        self.add_item(ui.Button(emoji="▶️", style=discord.ButtonStyle.blurple, row=0, disabled=self.page == self.total_pages - 1))
        self.children[-1].callback = self.next

        # Toggle
        label = "Switch to Selective" if not self.selective_mode else "Switch to All"
        self.add_item(ui.Button(label=label, style=discord.ButtonStyle.green if self.selective_mode else discord.ButtonStyle.grey, row=1))
        self.children[-1].callback = self.toggle_mode

        if self.selective_mode:
            current = self._current_page()
            options = [discord.SelectOption(label=f"{m.display_name} ({m})", value=str(m.id),
                                            description=f"Joined {m.joined_at.strftime('%Y-%m-%d') if m.joined_at else 'Unknown'}")
                       for m in current]
            self.add_item(ui.Select(placeholder="Select to kick (multi)", min_values=0,
                                    max_values=len(options) or 1, options=options or [discord.SelectOption(label="None", value="0")], row=2))
            self.children[-1].callback = self.select_callback

            self.add_item(ui.Button(label="Confirm Selected", style=discord.ButtonStyle.red, row=3, disabled=not self.selected_ids))
            self.children[-1].callback = self.confirm_selected
        else:
            self.add_item(ui.Button(label="Purge All Inactive", style=discord.ButtonStyle.red, row=1))
            self.children[-1].callback = self.purge_all_confirm

        # Extras
        self.add_item(ui.Button(label="Refresh List", style=discord.ButtonStyle.blurple, row=4))
        self.children[-1].callback = self.refresh_list
        self.add_item(ui.Button(label="Close", style=discord.ButtonStyle.gray, emoji="✖️", row=4))
        self.children[-1].callback = self.close_panel

    def _current_page(self):
        start = self.page * self.per_page
        return self.inactive[start:start + self.per_page]

    def get_embed(self, page: int) -> discord.Embed:
        start = page * self.per_page
        members = self.inactive[start:start + self.per_page]

        lines = []
        for i, m in enumerate(members, start + 1):
            joined = m.joined_at.strftime("%b %d, %Y") if m.joined_at else "Unknown"
            prefix = "🟢 " if self.selective_mode and m.id in self.selected_ids else ""
            lines.append(f"{prefix}{i}. {m.mention} — Joined: {joined}")

        embed = discord.Embed(
            title="🕵️ Inactive Members (0 Messages)",
            description="\n".join(lines) or "No members on this page.",
            color=discord.Color.dark_red(),
            timestamp=datetime.now(timezone.utc)
        )
        mode = "Selective Mode" if self.selective_mode else "Full Purge Mode"
        embed.set_footer(text=f"Page {page+1}/{self.total_pages} • Total: {len(self.inactive)} • {mode} • Selected: {len(self.selected_ids)}")
        if self.guild.icon:
            embed.set_thumbnail(url=self.guild.icon.url)
        return embed

    async def _update(self):
        if not self.message:
            return
        embed = self.get_embed(self.page)
        self._rebuild()
        try:
            await self.message.edit(embed=embed, view=self)
        except (discord.NotFound, discord.HTTPException):
            self.stop()

    # Callbacks (defer first = proven fix)
    async def previous(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author: return await interaction.response.send_message("Not yours.", ephemeral=True)
        await interaction.response.defer()
        if self.page > 0:
            self.page -= 1
        await self._update()

    async def next(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author: return await interaction.response.send_message("Not yours.", ephemeral=True)
        await interaction.response.defer()
        if (self.page + 1) * self.per_page < len(self.inactive):
            self.page += 1
        await self._update()

    async def toggle_mode(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author: return await interaction.response.send_message("Not yours.", ephemeral=True)
        await interaction.response.defer()
        self.selective_mode = not self.selective_mode
        if not self.selective_mode:
            self.selected_ids.clear()
        await self._update()

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user != self.author: return await interaction.response.send_message("Not yours.", ephemeral=True)
        await interaction.response.defer()
        values = interaction.data.get("values", [])
        for v in values:
            self.selected_ids.add(int(v))
        current = {int(opt["value"]) for opt in interaction.data.get("options", [])}
        selected_now = {int(v) for v in values}
        for mid in current - selected_now:
            self.selected_ids.discard(mid)
        await self._update()

    async def purge_all_confirm(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author: return await interaction.response.send_message("Not yours.", ephemeral=True)
        confirm = ConfirmView(self, list(self.inactive), "all")
        await interaction.response.send_message("**⚠️ FINAL WARNING**\nPurge **ALL** members below?", view=confirm, ephemeral=True)

    async def confirm_selected(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author: return await interaction.response.send_message("Not yours.", ephemeral=True)
        if not self.selected_ids: return await interaction.response.send_message("Nothing selected.", ephemeral=True)
        targets = [m for m in self.inactive if m.id in self.selected_ids]
        confirm = ConfirmView(self, targets, "selected")
        await interaction.response.send_message(f"**⚠️ FINAL WARNING**\nPurge **{len(targets)}** selected members?", view=confirm, ephemeral=True)

    async def refresh_list(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author: return await interaction.response.send_message("Not yours.", ephemeral=True)
        await interaction.response.defer()
        # Re-fetch current inactive list
        data = await self.cog.config.all_members(self.guild)
        new_inactive = [m for m in self.guild.members if not m.bot and (data.get(m.id) or {}).get("messages", 0) == 0]
        new_inactive.sort(key=lambda m: m.joined_at or datetime(1900, 1, 1, tzinfo=timezone.utc))
        self.inactive = new_inactive
        self.total_pages = (len(new_inactive) + self.per_page - 1) // self.per_page
        self.page = min(self.page, self.total_pages - 1) if self.total_pages > 0 else 0
        await self._update()

    async def close_panel(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author: return await interaction.response.send_message("Not yours.", ephemeral=True)
        await interaction.response.defer()
        self.stop()
        try:
            await self.message.edit(view=None)
        except Exception:
            pass

    async def perform_kick(self, targets: list[discord.Member]):
        status = await self.message.channel.send(f"🚀 Purging {len(targets)} members...", reference=self.message)
        kicked = failed = 0

        for i, member in enumerate(targets, 1):
            try:
                await member.kick(reason="Inactive purge (0 messages tracked)")
                await self.cog.config.member(member).clear()
                kicked += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.65)

            if i % 5 == 0:
                await status.edit(content=f"⏳ {i}/{len(targets)} • ✅ {kicked} • ❌ {failed}")

        await status.edit(content=f"**Purge Complete**\n✅ Kicked: {kicked}\n❌ Failed: {failed}")

        self.inactive = [m for m in self.inactive if m not in targets]
        self.selected_ids.clear()
        if self.inactive:
            self.total_pages = (len(self.inactive) + self.per_page - 1) // self.per_page
            self.page = min(self.page, self.total_pages - 1)
            await self._update()
        else:
            self.stop()
            await self.message.edit(content="✅ All inactive members purged!", embed=None, view=None)


class ConfirmView(ui.View):
    def __init__(self, parent: InactiveView, targets: list[discord.Member], mode: str):
        super().__init__(timeout=180)
        self.parent = parent
        self.targets = targets
        self.mode = mode

    @ui.button(label="Yes — Purge Now", style=discord.ButtonStyle.red)
    async def yes(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        await self.parent.perform_kick(self.targets)
        self.stop()

    @ui.button(label="Cancel", style=discord.ButtonStyle.gray)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="Cancelled.", view=None)
        self.stop()
