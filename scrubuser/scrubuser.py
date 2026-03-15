import asyncio
from datetime import timedelta
from typing import Optional

import discord
from discord.ui import Modal, TextInput, View, button
from redbot.core import commands
from redbot.core.bot import Red


class CustomDaysModal(Modal, title="🔥 CUSTOM NUCLEAR DAYS INPUT 🔥"):
    def __init__(self, cog: "ScrubUser", ctx: commands.Context, user_id: int, user_name: str):
        super().__init__()
        self.cog = cog
        self.ctx = ctx
        self.user_id = user_id
        self.user_name = user_name

        self.days_input = TextInput(
            label="Days to scrub (or 'all')",
            placeholder="Example: 7 or all (admin only)",
            style=discord.TextStyle.short,
            required=True,
            max_length=10,
        )
        self.add_item(self.days_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        value = self.days_input.value.strip().lower()

        if value == "all":
            if not await self.cog.bot.is_admin(self.ctx.author):
                await interaction.followup.send("❌ Admin permission required for ALL.", ephemeral=True)
                return
            days = None
        else:
            try:
                days = int(value)
                if days < 1 or days > 365:
                    await interaction.followup.send("❌ Days must be 1-365.", ephemeral=True)
                    return
            except ValueError:
                await interaction.followup.send("❌ Invalid input. Use a number or 'all'.", ephemeral=True)
                return

        await self.cog.perform_scrub(interaction, self.ctx, self.user_id, self.user_name, days)


class ScrubView(View):
    def __init__(self, cog: "ScrubUser", ctx: commands.Context, user_id: int, user_name: str, is_admin: bool):
        super().__init__(timeout=600)
        self.cog = cog
        self.ctx = ctx
        self.user_id = user_id
        self.user_name = user_name
        self.is_admin = is_admin

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ Only the invoking moderator can use this panel.", ephemeral=True)
            return False
        return True

    @button(label="1 Day", style=discord.ButtonStyle.red, emoji="☢️")
    async def day_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.cog.perform_scrub(interaction, self.ctx, self.user_id, self.user_name, days=1)
        self.stop()

    @button(label="3 Days", style=discord.ButtonStyle.red, emoji="☢️")
    async def day_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.cog.perform_scrub(interaction, self.ctx, self.user_id, self.user_name, days=3)
        self.stop()

    @button(label="7 Days", style=discord.ButtonStyle.red, emoji="☢️")
    async def day_7(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.cog.perform_scrub(interaction, self.ctx, self.user_id, self.user_name, days=7)
        self.stop()

    @button(label="14 Days", style=discord.ButtonStyle.red, emoji="☢️")
    async def day_14(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.cog.perform_scrub(interaction, self.ctx, self.user_id, self.user_name, days=14)
        self.stop()

    @button(label="30 Days", style=discord.ButtonStyle.red, emoji="☢️")
    async def day_30(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.cog.perform_scrub(interaction, self.ctx, self.user_id, self.user_name, days=30)
        self.stop()

    @button(label="ALL", style=discord.ButtonStyle.red, emoji="💥", disabled=False)
    async def all_messages(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_admin:
            await interaction.response.send_message("❌ Admin only for full scrub.", ephemeral=True)
            return
        await interaction.response.defer()
        await self.cog.perform_scrub(interaction, self.ctx, self.user_id, self.user_name, days=None)
        self.stop()

    @button(label="Custom", style=discord.ButtonStyle.blurple, emoji="🔧")
    async def custom_days(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CustomDaysModal(self.cog, self.ctx, self.user_id, self.user_name))
        self.stop()

    @button(label="Cancel", style=discord.ButtonStyle.gray, emoji="🚫")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="🚫 Scrub protocol aborted by moderator.", embed=None, view=None)
        self.stop()


class ScrubUser(commands.Cog):
    """Nuclear-grade user message scrubber for moderators/admins."""

    def __init__(self, bot: Red):
        self.bot = bot

    @commands.command(name="scrub")
    @commands.guild_only()
    async def scrub(self, ctx: commands.Context, *, target: str = None):
        """Scrub a user's messages server-wide.
        
        Usage: [p]scrub @user | [p]scrub UserID
        No arguments shows this help menu (Red native).
        """
        if target is None:
            await ctx.send_help(ctx.command)
            return

        if not await self.bot.is_mod(ctx.author):
            embed = discord.Embed(description="❌ Moderator (or higher) permissions required.", color=0xff0000)
            await ctx.send(embed=embed)
            return

        # Parse target (mention, username, or raw ID)
        user_id: int
        user_name: str
        try:
            member = await commands.MemberConverter().convert(ctx, target)
            user_id = member.id
            user_name = str(member)
        except commands.BadArgument:
            try:
                user = await commands.UserConverter().convert(ctx, target)
                user_id = user.id
                user_name = str(user)
            except commands.BadArgument:
                try:
                    user_id = int(target)
                    try:
                        user = await self.bot.fetch_user(user_id)
                        user_name = str(user)
                    except discord.NotFound:
                        user_name = f"Unknown User ({user_id})"
                except ValueError:
                    await ctx.send("❌ Invalid user mention, username, or ID.")
                    return

        is_admin = await self.bot.is_admin(ctx.author)

        embed = discord.Embed(
            title="☢️ **NUCLEAR SCRUB LAUNCH PANEL** ☢️",
            description=(
                f"**Target:** {user_name} (`{user_id}`)\n\n"
                "This will delete the chosen number of days' worth of messages "
                "by this user **across the entire server**.\n"
                "Irreversible. Discord rate limits apply."
            ),
            color=0xffa500,
        )
        embed.set_footer(text="ScrubUser • Orange Nuclear Protocol • Use at your own risk")
        view = ScrubView(self, ctx, user_id, user_name, is_admin)
        await ctx.send(embed=embed, view=view)

    async def perform_scrub(
        self,
        interaction: discord.Interaction,
        ctx: commands.Context,
        user_id: int,
        user_name: str,
        days: Optional[int],
    ):
        """Core scrub logic with progress updates and rate-limit safety."""
        note = ""
        if days is None or days > 14:
            note = "⚠️ **Slower single-delete mode** (Discord 14-day bulk limit). This may take a long time."

        # Build list of purgeable channels + active threads
        purge_channels = []
        for ch in ctx.guild.text_channels:
            if ch.permissions_for(ctx.guild.me).manage_messages:
                purge_channels.append(ch)
        for thread in ctx.guild.threads:
            if thread.parent and thread.parent.permissions_for(ctx.guild.me).manage_messages:
                purge_channels.append(thread)

        total_ch = len(purge_channels)
        use_bulk = days is not None and days <= 14
        sleep_duration = 5 if use_bulk else 2

        progress_embed = discord.Embed(
            title="☢️ **SCRUB PROTOCOL ENGAGED** ☢️",
            description=(
                f"**Target:** {user_name} (`{user_id}`)\n"
                f"**Scope:** {'ALL TIME' if days is None else f'Last {days} days'}\n"
                f"{note}\n\n"
                "**Status:** Initializing...\n"
                f"**Channels:** 0/{total_ch}\n"
                "**Messages deleted:** 0"
            ),
            color=0xffa500,
        )

        # Edit the original panel into progress view
        try:
            await interaction.message.edit(embed=progress_embed, view=None)
        except (discord.NotFound, discord.HTTPException):
            await interaction.followup.send("❌ Could not update panel. Aborting.")
            return

        deleted_total = 0
        processed = 0

        for idx, channel in enumerate(purge_channels, start=1):
            processed += 1
            ch_name = getattr(channel, "name", str(channel))
            status_line = f"**Processing:** {ch_name} ({idx}/{total_ch})\n**Deleted so far:** {deleted_total}"

            progress_embed.description = (
                f"**Target:** {user_name} (`{user_id}`)\n"
                f"**Scope:** {'ALL TIME' if days is None else f'Last {days} days'}\n"
                f"{note}\n\n"
                f"{status_line}"
            )
            await interaction.message.edit(embed=progress_embed)

            after_dt = None
            if days is not None:
                after_dt = discord.utils.utcnow() - timedelta(days=days)

            channel_deleted = 0
            while True:
                try:
                    deleted_list = await channel.purge(
                        limit=100,
                        check=lambda m, uid=user_id: m.author.id == uid and not m.pinned,
                        after=after_dt,
                        bulk=use_bulk,
                    )
                    if not deleted_list:
                        break
                    channel_deleted += len(deleted_list)
                    deleted_total += len(deleted_list)
                    if len(deleted_list) < 100:
                        break
                    await asyncio.sleep(sleep_duration)
                except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                    await asyncio.sleep(1)
                    break

            await asyncio.sleep(1)  # extra safety between channels

        # Final success embed
        final_embed = discord.Embed(
            title="☢️ **SCRUB PROTOCOL COMPLETE** ☢️",
            description=(
                f"**Target:** {user_name} (`{user_id}`)\n"
                f"**Messages deleted:** {deleted_total}\n"
                f"**Channels processed:** {processed}\n\n"
                "Nuclear scrub executed. All done."
            ),
            color=0x00ff00,
        )
        try:
            await interaction.message.edit(embed=final_embed)
        except (discord.NotFound, discord.HTTPException):
            pass  # message may have been deleted manually