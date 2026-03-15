from datetime import datetime, timezone
import asyncio

import discord
from discord import ui
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.commands import Context


class InactivePurge(commands.Cog):
    """List and purge members with zero messages."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)
        self.config.register_member(messages=0)
        self.config.register_guild(tracking_enabled=False)  # off by default

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

    @commands.hybrid_command(name="inactive", description="List members with 0 messages + purge options.")
    @commands.guild_only()
    @commands.admin_or_permissions(kick_members=True)
    async def inactive(self, ctx: Context):
        if ctx.interaction:
            await ctx.defer(ephemeral=False)

        guild = ctx.guild
        try:
            data = await self.config.all_members(guild)
        except Exception:
            await ctx.send("Failed to load member data.")
            return

        inactive = [
            m for m in guild.members
            if not m.bot and (data.get(m.id) or {}).get("messages", 0) == 0
        ]

        if not inactive:
            await ctx.send("No inactive members found.")
            return

        inactive.sort(key=lambda m: m.joined_at or datetime(1900, 1, 1, tzinfo=timezone.utc))

        view = InactiveView(self, guild, inactive, ctx.author)
        embed = view.get_embed(0)

        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @commands.hybrid_command(name="inactivetracking", description="Toggle message tracking on/off.")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def inactivetracking(self, ctx: Context, enabled: bool):
        await self.config.guild(ctx.guild).tracking_enabled.set(enabled)
        await ctx.send(f"Message tracking is now **{'enabled' if enabled else 'disabled'}**.")


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

        self._rebuild_components()

    def _rebuild_components(self):
        self.clear_items()

        # Pagination
        self.prev = ui.Button(emoji="◀️", style=discord.ButtonStyle.blurple, row=0)
        self.next_btn = ui.Button(emoji="▶️", style=discord.ButtonStyle.blurple, row=0)
        self.prev.callback = self.previous_page
        self.next_btn.callback = self.next_page
        self.add_item(self.prev)
        self.add_item(self.next_btn)

        # Mode toggle
        label = "Switch to Selective" if not self.selective_mode else "Switch to All"
        style = discord.ButtonStyle.green if self.selective_mode else discord.ButtonStyle.grey
        self.toggle = ui.Button(label=label, style=style, row=1)
        self.toggle.callback = self.toggle_mode
        self.add_item(self.toggle)

        if self.selective_mode:
            current = self._get_current_page_members()
            options = [
                discord.SelectOption(
                    label=f"{m.display_name} ({m})",
                    value=str(m.id),
                    description=f"Joined {m.joined_at.strftime('%Y-%m-%d') if m.joined_at else 'Unknown'}"
                )
                for m in current
            ]
            self.select_menu = ui.Select(
                placeholder="Select members to kick (multi-select)",
                min_values=0,
                max_values=len(options) if options else 1,
                options=options or [discord.SelectOption(label="No members", value="0", default=True)],
                row=2
            )
            self.select_menu.callback = self.on_select_members
            self.add_item(self.select_menu)

            self.confirm_selected = ui.Button(
                label="Confirm Selected Kicks",
                style=discord.ButtonStyle.red,
                row=3,
                disabled=len(self.selected_ids) == 0
            )
            self.confirm_selected.callback = self.confirm_selected_kick
            self.add_item(self.confirm_selected)
        else:
            self.purge_all = ui.Button(
                label="Purge All Inactive",
                style=discord.ButtonStyle.red,
                row=1
            )
            self.purge_all.callback = self.purge_all_confirm
            self.add_item(self.purge_all)

        self.close_btn = ui.Button(label="Close", style=discord.ButtonStyle.gray, emoji="✖️", row=4)
        self.close_btn.callback = self.close_panel
        self.add_item(self.close_btn)

    def _get_current_page_members(self) -> list[discord.Member]:
        start = self.page * self.per_page
        end = min(start + self.per_page, len(self.inactive))
        return self.inactive[start:end]

    def get_embed(self, page: int) -> discord.Embed:
        start = page * self.per_page
        members = self.inactive[start:start + self.per_page]

        lines = []
        for i, m in enumerate(members, start=start + 1):
            joined = m.joined_at.strftime("%b %d, %Y") if m.joined_at else "Unknown"
            prefix = "🟢 " if self.selective_mode and m.id in self.selected_ids else ""
            lines.append(f"{prefix}{i}. {m.mention} — Joined: {joined}")

        embed = discord.Embed(
            title="Inactive Members (0 messages tracked)",
            description="\n".join(lines) or "No members on this page.",
            color=discord.Color.dark_red(),
            timestamp=datetime.now(timezone.utc)
        )

        mode = "Selective Mode" if self.selective_mode else "Full Purge Mode"
        embed.set_footer(
            text=f"Page {page+1}/{self.total_pages} • Total: {len(self.inactive)} • {mode} • Selected: {len(self.selected_ids)}"
        )

        if self.guild.icon:
            embed.set_thumbnail(url=self.guild.icon.url)

        return embed

    async def _safe_update(self):
        if not self.message:
            return

        embed = self.get_embed(self.page)
        self.prev.disabled = self.page == 0
        self.next_btn.disabled = self.page == self.total_pages - 1
        self._rebuild_components()

        try:
            await self.message.edit(embed=embed, view=self)
        except (discord.NotFound, discord.HTTPException):
            self.stop()

    # ────────────────────────────────────────────────
    #                   CALLBACKS
    # ────────────────────────────────────────────────

    async def previous_page(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author:
            await interaction.response.send_message("Not your panel.", ephemeral=True)
            return
        await interaction.response.defer()
        if self.page > 0:
            self.page -= 1
        await self._safe_update()

    async def next_page(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author:
            await interaction.response.send_message("Not your panel.", ephemeral=True)
            return
        await interaction.response.defer()
        if (self.page + 1) * self.per_page < len(self.inactive):
            self.page += 1
        await self._safe_update()

    async def toggle_mode(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author:
            await interaction.response.send_message("Not your panel.", ephemeral=True)
            return
        await interaction.response.defer()
        self.selective_mode = not self.selective_mode
        if not self.selective_mode:
            self.selected_ids.clear()
        await self._safe_update()

    async def on_select_members(self, interaction: discord.Interaction):
        if interaction.user != self.author:
            await interaction.response.send_message("Not your panel.", ephemeral=True)
            return
        await interaction.response.defer()

        values = interaction.data.get("values", [])
        for v in values:
            self.selected_ids.add(int(v))

        current_options = interaction.data.get("options", [])
        current_ids = {int(opt["value"]) for opt in current_options}
        selected_now = {int(v) for v in values}
        for mid in current_ids - selected_now:
            self.selected_ids.discard(mid)

        await self._safe_update()

    async def purge_all_confirm(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author:
            await interaction.response.send_message("Not your panel.", ephemeral=True)
            return
        confirm = ConfirmView(self, list(self.inactive), "all")
        await interaction.response.send_message(
            "**FINAL WARNING**\nKick **ALL** listed members?\nIrreversible!",
            view=confirm,
            ephemeral=True
        )

    async def confirm_selected_kick(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author:
            await interaction.response.send_message("Not your panel.", ephemeral=True)
            return
        if not self.selected_ids:
            await interaction.response.send_message("No members selected.", ephemeral=True)
            return
        targets = [m for m in self.inactive if m.id in self.selected_ids]
        confirm = ConfirmView(self, targets, "selected")
        await interaction.response.send_message(
            f"**FINAL WARNING**\nKick **{len(targets)}** selected members?\nIrreversible!",
            view=confirm,
            ephemeral=True
        )

    async def close_panel(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author:
            await interaction.response.send_message("Not your panel.", ephemeral=True)
            return
        await interaction.response.defer()
        self.stop()
        try:
            await self.message.edit(view=None)
        except Exception:
            pass


class ConfirmView(ui.View):
    def __init__(self, parent: InactiveView, targets: list[discord.Member], mode: str):
        super().__init__(timeout=300)
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


async def perform_kick(self: InactiveView, targets: list[discord.Member]):
    kicked = failed = 0
    total = len(targets)
    status = await self.message.channel.send(f"Starting purge ({total} members)...", reference=self.message)

    for i, member in enumerate(targets, 1):
        try:
            await member.kick(reason="Inactive purge (0 messages)")
            await self.cog.config.member(member).clear()
            kicked += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.65)

        if i % 8 == 0:
            await status.edit(content=f"⏳ {i}/{total} processed • Kicked: {kicked} • Failed: {failed}")

    await status.edit(content=f"**Purge complete**\nKicked: {kicked}\nFailed: {failed}")

    self.inactive = [m for m in self.inactive if m not in targets]
    self.selected_ids.clear()

    if self.inactive:
        self.total_pages = (len(self.inactive) + self.per_page - 1) // self.per_page
        self.page = min(self.page, self.total_pages - 1)
        await self._safe_update()
    else:
        self.stop()
        try:
            await self.message.edit(content="No inactive members remaining.", embed=None, view=None)
        except Exception:
            pass


InactiveView.perform_kick = perform_kick
