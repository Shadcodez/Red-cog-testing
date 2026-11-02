import asyncio
import logging
from typing import Optional

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red

log = logging.getLogger("red.voidrooms")


class DismissView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=300)
        self.author_id = author_id

    @discord.ui.button(label="Dismiss", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def dismiss(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the room creator can dismiss this.", ephemeral=True)
            return
        try:
            await interaction.message.delete()
        except discord.HTTPException:
            pass
        self.stop()


class VoidRooms(commands.Cog):
    """Automatic personal voice rooms (VoidRooms).

    Join a configured source channel to create a room named after you
    or the game you are playing. Rooms auto-delete when empty.
    """

    __author__ = "SHADOW6six + Grok"
    __version__ = "1.0.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x564F4944, force_registration=True)
        self.config.register_guild(
            source_channel=None,
            dest_category=None,
            default_mode="normal",  # normal / locked / private
        )
        self.config.register_channel(
            owner=None,
            mode=None,
            source=None,
        )
        self.create_cooldown = commands.CooldownMapping.from_cooldown(2, 60, commands.BucketType.member)

    async def cog_unload(self):
        pass

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _get_room_name(self, member: discord.Member) -> str:
        activity = member.activity
        if activity and activity.type == discord.ActivityType.playing and activity.name:
            name = activity.name[:90]
            return f"{name}"
        return f"{member.display_name}'s Room"[:100]

    async def _get_overwrites(self, guild: discord.Guild, owner: discord.Member, mode: str) -> dict:
        bot_member = guild.me
        everyone = guild.default_role
        overwrites = {
            bot_member: discord.PermissionOverwrite(
                view_channel=True, connect=True, manage_channels=True, move_members=True, manage_permissions=True
            ),
            owner: discord.PermissionOverwrite(
                view_channel=True, connect=True, speak=True, stream=True,
                manage_channels=True, manage_permissions=True, mute_members=True, deafen_members=True, move_members=True
            ),
        }
        if mode == "private":
            overwrites[everyone] = discord.PermissionOverwrite(view_channel=False, connect=False)
        elif mode == "locked":
            overwrites[everyone] = discord.PermissionOverwrite(view_channel=True, connect=False)
        else:  # normal
            overwrites[everyone] = discord.PermissionOverwrite(view_channel=True, connect=True, speak=True)
        return overwrites

    async def _notify_creator(self, member: discord.Member, channel: discord.VoiceChannel, mode: str):
        prefixes = await self.bot.get_valid_prefixes(member.guild)
        prefix = prefixes[0] if prefixes else "!"
        embed = discord.Embed(
            title="Your Void Room is ready",
            description=(
                f"**Channel:** {channel.mention}\n"
                f"**Mode:** `{mode}`\n"
                f"**Owner:** {member.mention}\n\n"
                f"Use `{prefix}allow @user` to grant access (locked/private).\n"
                f"Use `{prefix}transfer @user` to pass ownership.\n"
                f"Use `{prefix}eject @user` to discreetly deny access."
            ),
            color=discord.Color.dark_theme()
        )
        embed.set_footer(text="VoidRooms • SHADOW6six + Grok")
        view = DismissView(member.id)

        # Prefer voice channel chat
        try:
            await channel.send(embed=embed, view=view, content=member.mention)
        except discord.HTTPException as e:
            log.warning("Could not send in VC chat: %s", e)

        # Also try DM
        try:
            await member.send(embed=embed, view=DismissView(member.id))
        except discord.HTTPException:
            pass

    # -------------------------------------------------------------------------
    # Events
    # -------------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot or not member.guild:
            return

        # Leave → check for empty room deletion
        if before.channel and before.channel != after.channel:
            await self._check_delete(before.channel)

        # Join source → create room
        if after.channel:
            source_id = await self.config.guild(member.guild).source_channel()
            if source_id and after.channel.id == source_id:
                await self._create_room(member, after.channel)

    async def _check_delete(self, channel: discord.VoiceChannel):
        data = await self.config.channel(channel).all()
        if not data.get("owner"):
            return
        await asyncio.sleep(1.5)
        try:
            ch = self.bot.get_channel(channel.id) or await self.bot.fetch_channel(channel.id)
            if isinstance(ch, discord.VoiceChannel) and len(ch.members) == 0:
                await ch.delete(reason="VoidRooms: room empty")
                await self.config.channel(channel).clear()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
            log.debug("Delete failed for %s: %s", channel.id, e)

    async def _create_room(self, member: discord.Member, source: discord.VoiceChannel):
        guild = member.guild
        # Cooldown
        bucket = self.create_cooldown.get_bucket(member)
        retry = bucket.update_rate_limit()
        if retry:
            try:
                await member.send(f"You're creating rooms too quickly. Try again in {retry:.0f}s.")
            except discord.HTTPException:
                pass
            return

        dest_id = await self.config.guild(guild).dest_category()
        mode = await self.config.guild(guild).default_mode()
        if not dest_id:
            try:
                await member.send("VoidRooms is not fully configured (no destination category set). Ask an admin to run `[p]voidroomsset source`.")
            except discord.HTTPException:
                pass
            return

        category = guild.get_channel(dest_id)
        if not category or not isinstance(category, discord.CategoryChannel):
            try:
                await member.send("VoidRooms destination category is invalid. Ask an admin to reconfigure it.")
            except discord.HTTPException:
                pass
            return

        # Check bot permissions
        me = guild.me
        if not me.guild_permissions.manage_channels or not me.guild_permissions.move_members:
            try:
                await member.send("I don't have the required permissions (Manage Channels + Move Members) to create Void Rooms.")
            except discord.HTTPException:
                pass
            log.error("Missing permissions in guild %s", guild.id)
            return

        name = self._get_room_name(member)
        overwrites = await self._get_overwrites(guild, member, mode)

        try:
            new_channel = await guild.create_voice_channel(
                name=name,
                category=category,
                overwrites=overwrites,
                reason=f"VoidRooms created by {member}"
            )
            # Move the user
            await member.move_to(new_channel, reason="VoidRooms: move to new room")
            # Store ownership
            await self.config.channel(new_channel).owner.set(member.id)
            await self.config.channel(new_channel).mode.set(mode)
            await self.config.channel(new_channel).source.set(source.id)
            # Notify
            await self._notify_creator(member, new_channel, mode)
            log.info("Created VoidRoom %s for %s in %s", new_channel.id, member.id, guild.id)
        except discord.Forbidden as e:
            log.error("Forbidden while creating VoidRoom in %s: %s", guild.id, e)
            try:
                await member.send("I couldn't create or move you to the Void Room (permission error).")
            except discord.HTTPException:
                pass
        except discord.HTTPException as e:
            log.exception("Failed to create VoidRoom: %s", e)
            try:
                await member.send("Something went wrong while creating your Void Room. Please try again.")
            except discord.HTTPException:
                pass

    # -------------------------------------------------------------------------
    # Commands
    # -------------------------------------------------------------------------
    @commands.group(name="voidroomsset", aliases=["vrset"])
    @commands.guild_only()
    @commands.admin_or_permissions(manage_channels=True)
    async def voidroomsset(self, ctx: commands.Context):
        """Configure VoidRooms."""

    @voidroomsset.command(name="source")
    async def set_source(self, ctx: commands.Context, source: discord.VoiceChannel, category: discord.CategoryChannel):
        """Set the source voice channel and destination category."""
        await self.config.guild(ctx.guild).source_channel.set(source.id)
        await self.config.guild(ctx.guild).dest_category.set(category.id)
        await ctx.send(f"Source set to {source.mention}, rooms will be created in **{category.name}**.")

    @voidroomsset.command(name="mode")
    async def set_mode(self, ctx: commands.Context, mode: str):
        """Set default room mode: normal, locked, or private."""
        mode = mode.lower()
        if mode not in ("normal", "locked", "private"):
            return await ctx.send("Mode must be `normal`, `locked`, or `private`.")
        await self.config.guild(ctx.guild).default_mode.set(mode)
        await ctx.send(f"Default mode set to **{mode}**.")

    @voidroomsset.command(name="settings")
    async def show_settings(self, ctx: commands.Context):
        """Show current VoidRooms configuration."""
        data = await self.config.guild(ctx.guild).all()
        src = ctx.guild.get_channel(data["source_channel"]) if data["source_channel"] else None
        cat = ctx.guild.get_channel(data["dest_category"]) if data["dest_category"] else None
        await ctx.send(
            f"**Source:** {src.mention if src else 'Not set'}\n"
            f"**Category:** {cat.name if cat else 'Not set'}\n"
            f"**Default mode:** `{data['default_mode']}`"
        )

    # Room owner commands
    async def _get_owned_room(self, member: discord.Member) -> Optional[discord.VoiceChannel]:
        if not member.voice or not member.voice.channel:
            return None
        ch = member.voice.channel
        owner_id = await self.config.channel(ch).owner()
        if owner_id == member.id:
            return ch
        return None

    @commands.command(name="allow")
    @commands.guild_only()
    async def allow_user(self, ctx: commands.Context, user: discord.Member):
        """Allow a user to join your locked/private Void Room."""
        room = await self._get_owned_room(ctx.author)
        if not room:
            return await ctx.send("You must be in a Void Room you own.", delete_after=10)
        await room.set_permissions(user, view_channel=True, connect=True, speak=True)
        await ctx.send(f"{user.mention} can now join your room.", delete_after=15)

    @commands.command(name="eject", aliases=["voideject", "deny"])
    @commands.guild_only()
    async def eject_user(self, ctx: commands.Context, user: discord.Member):
        """Discreetly remove a user from your Void Room (sets deny connect)."""
        room = await self._get_owned_room(ctx.author)
        if not room:
            return await ctx.send("You must be in a Void Room you own.", delete_after=10)
        if user == ctx.author:
            return await ctx.send("You can't remove yourself.", delete_after=10)
        await room.set_permissions(user, connect=False, view_channel=False)
        if user.voice and user.voice.channel == room:
            try:
                await user.move_to(None, reason="VoidRooms: removed by owner")
            except discord.HTTPException:
                pass
        await ctx.send(f"{user.mention} has been removed from the room.", delete_after=10)

    @commands.command(name="transfer")
    @commands.guild_only()
    async def transfer_ownership(self, ctx: commands.Context, user: discord.Member):
        """Transfer ownership of your Void Room to another user."""
        room = await self._get_owned_room(ctx.author)
        if not room:
            return await ctx.send("You must be in a Void Room you own.", delete_after=10)
        if user.bot or user == ctx.author:
            return await ctx.send("Invalid target.", delete_after=10)

        mode = await self.config.channel(room).mode()
        await room.set_permissions(ctx.author, overwrite=None)
        overwrites = await self._get_overwrites(ctx.guild, user, mode or "normal")
        await room.edit(overwrites=overwrites, reason=f"VoidRooms ownership transfer to {user}")
        await self.config.channel(room).owner.set(user.id)
        await ctx.send(f"Ownership transferred to {user.mention}.")

    @commands.command(name="voidmode", aliases=["vrmode"])
    @commands.guild_only()
    async def change_mode(self, ctx: commands.Context, mode: str):
        """Change the mode of your current Void Room (normal/locked/private)."""
        room = await self._get_owned_room(ctx.author)
        if not room:
            return await ctx.send("You must be in a Void Room you own.", delete_after=10)
        mode = mode.lower()
        if mode not in ("normal", "locked", "private"):
            return await ctx.send("Mode must be `normal`, `locked`, or `private`.")
        overwrites = await self._get_overwrites(ctx.guild, ctx.author, mode)
        await room.edit(overwrites=overwrites)
        await self.config.channel(room).mode.set(mode)
        await ctx.send(f"Room mode changed to **{mode}**.")
