"""Modern giveaway cog for Red-DiscordBot."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Union

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_list, pagify

from .converters import GiveawayEditFlags, GiveawayFlags
from .helpers import (
    MAX_ACTIVE_PER_GUILD,
    MAX_DESCRIPTION_LEN,
    apply_edit,
    can_enter,
    clamp_winners,
    default_giveaway_payload,
    discord_absolute,
    discord_relative,
    entry_count,
    is_active,
    pick_winners,
    should_cleanup,
    ticket_count,
    tickets_for_member,
    ts_now,
    validate_duration_seconds,
)
from .views import EndedGiveawayView, GiveawayJoinView, GiveawayLaunchView, safe_delete

log = logging.getLogger("red.shad.giveaways")

MessageableGuildChannel = Union[discord.TextChannel, discord.Thread, discord.VoiceChannel]


class Giveaways(commands.Cog):
    """Create and manage button-based giveaways with timers, edits, and rerolls."""

    __author__ = "shad"
    __version__ = "1.0.0"

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x53484144, force_registration=True)
        self.config.register_guild(
            giveaways={},
            manager_role=None,
            default_winners=1,
            dm_winners=True,
            ping_role=None,
            max_active=MAX_ACTIVE_PER_GUILD,
        )
        self._tasks: Dict[str, asyncio.Task] = {}
        self._join_view: Optional[GiveawayJoinView] = None
        self._ready = asyncio.Event()
        self._lock = asyncio.Lock()
        self._setup_messages: Dict[int, discord.Message] = {}

    def format_help_for_context(self, ctx: commands.Context) -> str:
        base = super().format_help_for_context(ctx)
        return f"{base}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}"

    async def red_delete_data_for_user(self, *, requester: str, user_id: int) -> None:
        """Remove a user's entries from stored giveaways."""
        all_guilds = await self.config.all_guilds()
        for guild_id, data in all_guilds.items():
            giveaways = data.get("giveaways") or {}
            changed = False
            uid = str(user_id)
            for gw in giveaways.values():
                entries = gw.get("entries") or {}
                if uid in entries:
                    entries.pop(uid, None)
                    gw["entries"] = entries
                    changed = True
            if changed:
                await self.config.guild_from_id(guild_id).giveaways.set(giveaways)

    async def cog_load(self) -> None:
        self._join_view = GiveawayJoinView(self)
        self.bot.add_view(self._join_view)
        self.bot.loop.create_task(self._resume_giveaways())

    async def cog_unload(self) -> None:
        if self._join_view:
            self._join_view.stop()
        for task in list(self._tasks.values()):
            task.cancel()
        self._tasks.clear()
        for message in list(self._setup_messages.values()):
            self.bot.loop.create_task(safe_delete(message))
        self._setup_messages.clear()

    async def _resume_giveaways(self) -> None:
        await self.bot.wait_until_red_ready()
        try:
            all_guilds = await self.config.all_guilds()
            now = ts_now()
            for guild_id, data in all_guilds.items():
                giveaways = data.get("giveaways") or {}
                dirty = False
                for key, gw in list(giveaways.items()):
                    if should_cleanup(gw, now):
                        giveaways.pop(key, None)
                        dirty = True
                        continue
                    if is_active(gw):
                        self._schedule(int(guild_id), int(gw["message_id"]))
                if dirty:
                    await self.config.guild_from_id(guild_id).giveaways.set(giveaways)
        except Exception:
            log.exception("Failed to resume giveaways")
        finally:
            self._ready.set()

    def _task_key(self, guild_id: int, message_id: int) -> str:
        return f"{guild_id}:{message_id}"

    def _schedule(self, guild_id: int, message_id: int) -> None:
        key = self._task_key(guild_id, message_id)
        old = self._tasks.pop(key, None)
        if old and not old.done():
            old.cancel()
        task = self.bot.loop.create_task(self._timer(guild_id, message_id))
        self._tasks[key] = task

        def _clear(done: asyncio.Task, stored_key: str = key) -> None:
            current = self._tasks.get(stored_key)
            if current is done:
                self._tasks.pop(stored_key, None)
            exc = None
            try:
                exc = done.exception()
            except (asyncio.CancelledError, asyncio.InvalidStateError):
                return
            if exc:
                log.exception("Giveaway timer crashed for %s", stored_key, exc_info=exc)

        task.add_done_callback(_clear)

    def _cancel_timer(self, guild_id: int, message_id: int) -> None:
        key = self._task_key(guild_id, message_id)
        task = self._tasks.pop(key, None)
        if task and not task.done():
            task.cancel()

    async def _timer(self, guild_id: int, message_id: int) -> None:
        """Sleep until end time in short chunks so cancel/edit apply quickly."""
        try:
            while True:
                gw = await self._get(guild_id, message_id)
                if not gw or not is_active(gw):
                    return
                remaining = float(gw["end_ts"]) - ts_now()
                if remaining <= 0:
                    await self.finish_giveaway(guild_id, message_id, cancelled=False)
                    return
                await asyncio.sleep(min(remaining, 30.0))
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Timer error for %s/%s", guild_id, message_id)

    async def _get(self, guild_id: int, message_id: int) -> Optional[Dict[str, Any]]:
        giveaways = await self.config.guild_from_id(guild_id).giveaways()
        data = giveaways.get(str(message_id))
        return data

    async def _save(self, guild_id: int, message_id: int, payload: Dict[str, Any]) -> None:
        async with self.config.guild_from_id(guild_id).giveaways() as giveaways:
            giveaways[str(message_id)] = payload

    async def _delete(self, guild_id: int, message_id: int) -> None:
        async with self.config.guild_from_id(guild_id).giveaways() as giveaways:
            giveaways.pop(str(message_id), None)

    async def _active_count(self, guild_id: int) -> int:
        giveaways = await self.config.guild_from_id(guild_id).giveaways()
        return sum(1 for gw in giveaways.values() if is_active(gw))

    def _join_view_for_send(self, label: Optional[str] = None) -> GiveawayJoinView:
        view = GiveawayJoinView(self)
        if label:
            for item in view.children:
                if isinstance(item, discord.ui.Button) and item.custom_id == "shadgw:join":
                    item.label = label[:80]
        return view

    def build_embed(
        self,
        gw: Dict[str, Any],
        *,
        ended: bool = False,
        cancelled: bool = False,
        winners: Optional[List[int]] = None,
        colour: Optional[discord.Colour] = None,
    ) -> discord.Embed:
        prize = gw.get("prize") or "Giveaway"
        if cancelled:
            title = f"Giveaway cancelled — {prize}"
        elif ended:
            title = f"Giveaway ended — {prize}"
        else:
            title = f"{prize}"

        color_value = gw.get("color")
        if colour is None and color_value is not None:
            try:
                colour = discord.Colour(int(color_value))
            except (TypeError, ValueError):
                colour = None
        if colour is None:
            colour = discord.Colour.gold() if not ended else discord.Colour.dark_grey()

        desc_parts: List[str] = []
        extra = (gw.get("description") or "").strip()
        if extra:
            desc_parts.append(extra)
        if not ended and not cancelled:
            desc_parts.append("Press **Enter** to join this giveaway.")
        embed = discord.Embed(title=title[:256], description="\n\n".join(desc_parts)[:4096], colour=colour)

        host_id = gw.get("host_id")
        if host_id:
            embed.add_field(name="Hosted by", value=f"<@{host_id}>", inline=True)
        embed.add_field(name="Winners", value=str(gw.get("winners") or 1), inline=True)
        embed.add_field(
            name="Entries",
            value=str(entry_count(gw)),
            inline=True,
        )

        if cancelled:
            embed.add_field(name="Status", value="Cancelled", inline=True)
        elif ended:
            mentions = [f"<@{uid}>" for uid in (winners or gw.get("winner_ids") or [])]
            embed.add_field(
                name="Winner(s)",
                value=humanize_list(mentions) if mentions else "No valid entries",
                inline=False,
            )
        else:
            end_ts = float(gw.get("end_ts") or ts_now())
            embed.add_field(
                name="Ends",
                value=f"{discord_relative(end_ts)} ({discord_absolute(end_ts)})",
                inline=False,
            )

        req_bits = []
        for rid in gw.get("required_roles") or []:
            req_bits.append(f"Required: <@&{rid}>")
        for rid in gw.get("blacklist_roles") or []:
            req_bits.append(f"Blocked: <@&{rid}>")
        if gw.get("min_account_days"):
            req_bits.append(f"Account age: {gw['min_account_days']}d+")
        if gw.get("min_server_days"):
            req_bits.append(f"Server age: {gw['min_server_days']}d+")
        bonus = gw.get("bonus_roles") or {}
        for rid, extra_tickets in bonus.items():
            req_bits.append(f"<@&{rid}> +{extra_tickets} ticket(s)")
        if req_bits:
            embed.add_field(name="Requirements", value="\n".join(req_bits)[:1024], inline=False)

        if gw.get("image"):
            embed.set_image(url=gw["image"])
        if gw.get("thumbnail"):
            embed.set_thumbnail(url=gw["thumbnail"])
        embed.set_footer(text=f"ID: {gw.get('message_id', '')} • {ticket_count(gw)} ticket(s)")
        return embed

    async def start_from_draft(self, ctx: commands.Context, draft: Dict[str, Any]) -> discord.Message:
        if ctx.guild is None:
            raise commands.UserFeedbackCheckFailure("Giveaways can only be started in a server.")

        prize = (draft.get("prize") or "").strip()
        if not prize:
            raise commands.UserFeedbackCheckFailure("A prize is required.")

        duration_seconds = draft.get("duration_seconds")
        if not duration_seconds:
            raise commands.UserFeedbackCheckFailure("A duration is required.")
        ok, err = validate_duration_seconds(float(duration_seconds))
        if not ok:
            raise commands.UserFeedbackCheckFailure(err)

        max_active = await self.config.guild(ctx.guild).max_active()
        if await self._active_count(ctx.guild.id) >= int(max_active or MAX_ACTIVE_PER_GUILD):
            raise commands.UserFeedbackCheckFailure(
                "This server already has the maximum number of active giveaways."
            )

        channel_id = int(draft.get("channel_id") or ctx.channel.id)
        channel = ctx.guild.get_channel(channel_id) or ctx.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            raise commands.UserFeedbackCheckFailure("I cannot post a giveaway in that channel.")

        me = ctx.guild.me
        perms = channel.permissions_for(me)
        if not perms.send_messages or not perms.embed_links:
            raise commands.UserFeedbackCheckFailure(
                f"I need Send Messages and Embed Links in {channel.mention}."
            )

        end_ts = ts_now() + float(duration_seconds)
        winners = clamp_winners(draft.get("winners") or 1)
        colour = draft.get("color")
        colour_int = int(colour) if isinstance(colour, discord.Colour) else colour

        payload = default_giveaway_payload(
            guild_id=ctx.guild.id,
            channel_id=channel.id,
            message_id=0,
            host_id=ctx.author.id,
            prize=prize,
            end_ts=end_ts,
            winners=winners,
            description=draft.get("description") or "",
            extra={
                "required_roles": [int(r) for r in (draft.get("required_roles") or [])],
                "blacklist_roles": [int(r) for r in (draft.get("blacklist_roles") or [])],
                "bonus_roles": draft.get("bonus_roles") or {},
                "min_account_days": int(draft.get("min_account_days") or 0),
                "min_server_days": int(draft.get("min_server_days") or 0),
                "allow_host": bool(draft.get("allow_host")),
                "dm_winners": bool(draft.get("dm_winners", True)),
                "image": draft.get("image"),
                "thumbnail": draft.get("thumbnail"),
                "color": colour_int,
                "button_label": (draft.get("button_label") or "Enter")[:80],
                "button_emoji": draft.get("button_emoji") or "🎉",
                "ping_role": draft.get("ping_role"),
            },
        )

        ping_role = draft.get("ping_role")
        content = None
        if ping_role:
            content = f"<@&{int(ping_role)}>"

        embed = self.build_embed(payload, colour=colour if isinstance(colour, discord.Colour) else None)
        view = self._join_view_for_send(payload.get("button_label"))
        try:
            message = await channel.send(content=content, embed=embed, view=view)
        except discord.Forbidden as exc:
            raise commands.UserFeedbackCheckFailure("I could not send the giveaway message.") from exc
        except discord.HTTPException as exc:
            raise commands.UserFeedbackCheckFailure(f"Discord rejected the giveaway message: {exc}") from exc

        payload["message_id"] = message.id
        payload["channel_id"] = channel.id
        embed = self.build_embed(payload, colour=colour if isinstance(colour, discord.Colour) else None)
        try:
            await message.edit(embed=embed)
        except discord.HTTPException:
            pass

        await self._save(ctx.guild.id, message.id, payload)
        self._schedule(ctx.guild.id, message.id)
        return message

    async def _fetch_message(self, gw: Dict[str, Any]) -> Optional[discord.Message]:
        channel_id = gw.get("channel_id")
        message_id = gw.get("message_id")
        if not channel_id or not message_id:
            return None
        channel = self.bot.get_channel(int(channel_id))
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(int(channel_id))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return None
        if not hasattr(channel, "fetch_message"):
            return None
        try:
            return await channel.fetch_message(int(message_id))  # type: ignore[union-attr]
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

    async def _update_message(
        self,
        gw: Dict[str, Any],
        *,
        ended: bool = False,
        cancelled: bool = False,
        winners: Optional[List[int]] = None,
        disable: bool = False,
    ) -> None:
        message = await self._fetch_message(gw)
        if message is None:
            return
        embed = self.build_embed(gw, ended=ended, cancelled=cancelled, winners=winners)
        view: discord.ui.View
        if disable or ended or cancelled:
            label = "Cancelled" if cancelled else "Ended"
            view = EndedGiveawayView(label=label)
        else:
            view = self._join_view_for_send(gw.get("button_label"))
        try:
            await message.edit(embed=embed, view=view)
        except discord.HTTPException:
            log.debug("Failed to edit giveaway message %s", gw.get("message_id"))

    async def finish_giveaway(
        self,
        guild_id: int,
        message_id: int,
        *,
        cancelled: bool = False,
        announce: bool = True,
    ) -> Optional[List[int]]:
        async with self._lock:
            gw = await self._get(guild_id, message_id)
            if not gw or not is_active(gw):
                return None
            gw["ended"] = True
            gw["cancelled"] = bool(cancelled)
            gw["ended_ts"] = ts_now()
            winners: List[int] = []
            if not cancelled:
                winners = pick_winners(gw.get("entries") or {}, gw.get("winners") or 1)
            gw["winner_ids"] = winners
            await self._save(guild_id, message_id, gw)

        self._cancel_timer(guild_id, message_id)
        await self._update_message(gw, ended=True, cancelled=cancelled, winners=winners, disable=True)

        if not announce:
            return winners

        channel = self.bot.get_channel(int(gw["channel_id"]))
        if channel is None:
            return winners
        if not hasattr(channel, "send"):
            return winners

        prize = gw.get("prize") or "the prize"
        try:
            if cancelled:
                await channel.send(f"The giveaway for **{prize}** was cancelled.")
            elif winners:
                mentions = humanize_list([f"<@{uid}>" for uid in winners])
                await channel.send(f"Congratulations {mentions}! You won **{prize}**.")
                if gw.get("dm_winners"):
                    await self._dm_winners(winners, prize, guild_id)
            else:
                await channel.send(f"The giveaway for **{prize}** ended with no valid entries.")
        except discord.HTTPException:
            log.debug("Could not announce giveaway result in %s", gw.get("channel_id"))
        return winners

    async def _dm_winners(self, winners: List[int], prize: str, guild_id: int) -> None:
        guild = self.bot.get_guild(guild_id)
        guild_name = guild.name if guild else "a server"
        for uid in winners:
            user = self.bot.get_user(uid)
            if user is None:
                try:
                    user = await self.bot.fetch_user(uid)
                except (discord.NotFound, discord.HTTPException):
                    continue
            try:
                await user.send(f"You won **{prize}** in **{guild_name}**!")
            except discord.HTTPException:
                continue

    async def handle_join(self, interaction: discord.Interaction, message_id: int) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Giveaways can only be joined in a server.", ephemeral=True)
            return
        gw = await self._get(interaction.guild.id, message_id)
        if not gw or not is_active(gw):
            await interaction.response.send_message("This giveaway is no longer active.", ephemeral=True)
            return
        if ts_now() >= float(gw.get("end_ts") or 0):
            await self.finish_giveaway(interaction.guild.id, message_id, cancelled=False)
            await interaction.response.send_message("This giveaway just ended.", ephemeral=True)
            return

        member = interaction.user
        allowed, reason = can_enter(
            user_id=member.id,
            is_bot=member.bot,
            host_id=int(gw.get("host_id") or 0),
            allow_host=bool(gw.get("allow_host")),
            member_role_ids=[r.id for r in member.roles],
            required_roles=gw.get("required_roles") or [],
            blacklist_roles=gw.get("blacklist_roles") or [],
            account_created_ts=member.created_at.timestamp() if member.created_at else None,
            joined_ts=member.joined_at.timestamp() if member.joined_at else None,
            min_account_days=int(gw.get("min_account_days") or 0),
            min_server_days=int(gw.get("min_server_days") or 0),
        )
        if not allowed:
            await interaction.response.send_message(reason, ephemeral=True)
            return

        tickets = tickets_for_member(
            [r.id for r in member.roles],
            gw.get("bonus_roles") or {},
        )
        already = False
        async with self.config.guild(interaction.guild).giveaways() as giveaways:
            current = giveaways.get(str(message_id))
            if not current or not is_active(current):
                await interaction.response.send_message("This giveaway is no longer active.", ephemeral=True)
                return
            entries = current.setdefault("entries", {})
            already = str(member.id) in entries
            entries[str(member.id)] = tickets
            gw = current

        await self._update_message(gw)
        if already:
            await interaction.response.send_message(
                f"Your entry was updated. You have **{tickets}** ticket(s).",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"You are entered with **{tickets}** ticket(s). Good luck!",
                ephemeral=True,
            )

    async def handle_leave(self, interaction: discord.Interaction, message_id: int) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Giveaways can only be left in a server.", ephemeral=True)
            return
        removed = False
        gw: Optional[Dict[str, Any]] = None
        async with self.config.guild(interaction.guild).giveaways() as giveaways:
            current = giveaways.get(str(message_id))
            if not current or not is_active(current):
                await interaction.response.send_message("This giveaway is no longer active.", ephemeral=True)
                return
            entries = current.setdefault("entries", {})
            if str(interaction.user.id) in entries:
                entries.pop(str(interaction.user.id), None)
                removed = True
            gw = current
        if gw:
            await self._update_message(gw)
        if removed:
            await interaction.response.send_message("You left the giveaway.", ephemeral=True)
        else:
            await interaction.response.send_message("You were not entered.", ephemeral=True)

    async def _resolve_giveaway(
        self, ctx: commands.Context, message_id: Optional[int]
    ) -> Dict[str, Any]:
        if ctx.guild is None:
            raise commands.UserFeedbackCheckFailure("This command must be used in a server.")
        giveaways = await self.config.guild(ctx.guild).giveaways()
        if message_id is not None:
            gw = giveaways.get(str(message_id))
            if not gw:
                raise commands.UserFeedbackCheckFailure("I could not find a giveaway with that ID.")
            return gw
        active = [g for g in giveaways.values() if is_active(g)]
        if not active:
            raise commands.UserFeedbackCheckFailure("There are no active giveaways in this server.")
        if len(active) == 1:
            return active[0]
        raise commands.UserFeedbackCheckFailure(
            "Multiple giveaways are running. Pass the message ID shown in the embed footer."
        )

    async def _draft_from_flags(self, ctx: commands.Context, options: GiveawayFlags) -> Dict[str, Any]:
        draft: Dict[str, Any] = {}
        if options.prize:
            draft["prize"] = options.prize[:256]
        if options.duration:
            draft["duration_seconds"] = int(options.duration.total_seconds())
        if options.winners:
            draft["winners"] = clamp_winners(options.winners)
        else:
            draft["winners"] = clamp_winners(await self.config.guild(ctx.guild).default_winners())
        if options.description:
            draft["description"] = options.description[:MAX_DESCRIPTION_LEN]
        draft["channel_id"] = options.channel.id if options.channel else ctx.channel.id
        if options.require:
            draft["required_roles"] = [options.require.id]
        if options.blacklist:
            draft["blacklist_roles"] = [options.blacklist.id]
        if options.colour:
            draft["color"] = options.colour
        draft["allow_host"] = bool(options.allow_host)
        draft["dm_winners"] = bool(options.dm_winners)
        draft["min_account_days"] = max(0, int(options.min_account_days or 0))
        draft["min_server_days"] = max(0, int(options.min_server_days or 0))
        if options.button_label:
            draft["button_label"] = options.button_label[:80]
        if options.ping:
            draft["ping_role"] = options.ping.id
        if options.image:
            draft["image"] = options.image
        if options.thumbnail:
            draft["thumbnail"] = options.thumbnail
        return draft

    def track_setup_message(self, message: Optional[discord.Message]) -> None:
        if message is not None:
            self._setup_messages[message.id] = message

    async def forget_setup_message(self, message: Optional[discord.Message]) -> None:
        if message is None:
            return
        self._setup_messages.pop(message.id, None)

    async def _cleanup_invoke(self, ctx: commands.Context) -> None:
        """Remove the invoking command message when the bot is allowed to."""
        if ctx.guild is None:
            return
        me = ctx.guild.me
        if me is None:
            return
        if not ctx.channel.permissions_for(me).manage_messages:
            return
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

    async def _can_create(self, ctx: commands.Context) -> bool:
        if ctx.guild is None:
            return False
        if await self.bot.is_owner(ctx.author):
            return True
        if await self.bot.is_admin(ctx.author):
            return True
        if await self.bot.is_mod(ctx.author):
            return True
        perms = getattr(ctx.author, "guild_permissions", None)
        return bool(perms and perms.manage_messages)

    async def begin_setup(
        self,
        ctx: commands.Context,
        draft: Optional[Dict[str, Any]] = None,
        *,
        edit_of: Optional[Dict[str, Any]] = None,
    ) -> discord.Message:
        await self._cleanup_invoke(ctx)
        view = GiveawayLaunchView(self, ctx, draft or {}, edit_of=edit_of)
        action = "edit" if edit_of else "create"
        message = await ctx.send(
            content=(
                f"{ctx.author.mention} Click **Set up** to {action} a giveaway. "
                "The form is private. This prompt deletes itself when you continue, cancel, or wait."
            ),
            view=view,
            allowed_mentions=discord.AllowedMentions(users=[ctx.author], roles=False, everyone=False),
        )
        view.message = message
        self.track_setup_message(message)
        return message

    async def open_builder(
        self,
        ctx: commands.Context,
        draft: Optional[Dict[str, Any]] = None,
        *,
        edit_of: Optional[Dict[str, Any]] = None,
    ) -> discord.Message:
        return await self.begin_setup(ctx, draft, edit_of=edit_of)

    async def apply_builder_edit(
        self,
        ctx: commands.Context,
        gw: Dict[str, Any],
        draft: Dict[str, Any],
    ) -> None:
        if ctx.guild is None:
            raise commands.UserFeedbackCheckFailure("This command must be used in a server.")
        if not is_active(gw):
            raise commands.UserFeedbackCheckFailure("That giveaway is no longer active.")
        colour = draft.get("color")
        colour_int = int(colour) if isinstance(colour, discord.Colour) else colour
        changes = {
            "prize": draft.get("prize"),
            "description": draft.get("description") or "",
            "winners": draft.get("winners"),
            "end_ts": ts_now() + float(draft.get("duration_seconds") or 0),
            "image": draft.get("image"),
            "thumbnail": draft.get("thumbnail"),
            "color": colour_int,
            "allow_host": bool(draft.get("allow_host")),
            "dm_winners": bool(draft.get("dm_winners", True)),
            "button_label": (draft.get("button_label") or "Enter")[:80],
            "required_roles": [int(r) for r in (draft.get("required_roles") or [])],
            "blacklist_roles": [int(r) for r in (draft.get("blacklist_roles") or [])],
            "bonus_roles": draft.get("bonus_roles") or {},
            "min_account_days": int(draft.get("min_account_days") or 0),
            "min_server_days": int(draft.get("min_server_days") or 0),
            "ping_role": draft.get("ping_role"),
        }
        apply_edit(gw, changes, now_ts=ts_now())
        ok, err = validate_duration_seconds(float(gw["end_ts"]) - ts_now())
        if not ok:
            raise commands.UserFeedbackCheckFailure(err)
        await self._save(ctx.guild.id, int(gw["message_id"]), gw)
        self._schedule(ctx.guild.id, int(gw["message_id"]))
        await self._update_message(gw)

    def _draft_from_giveaway(self, gw: Dict[str, Any]) -> Dict[str, Any]:
        remaining = max(10, int(float(gw.get("end_ts") or ts_now()) - ts_now()))
        colour = gw.get("color")
        if colour is not None:
            try:
                colour = discord.Colour(int(colour))
            except (TypeError, ValueError):
                colour = None
        return {
            "prize": gw.get("prize"),
            "description": gw.get("description") or "",
            "duration_seconds": remaining,
            "winners": clamp_winners(gw.get("winners") or 1),
            "channel_id": gw.get("channel_id"),
            "required_roles": list(gw.get("required_roles") or []),
            "blacklist_roles": list(gw.get("blacklist_roles") or []),
            "bonus_roles": dict(gw.get("bonus_roles") or {}),
            "min_account_days": int(gw.get("min_account_days") or 0),
            "min_server_days": int(gw.get("min_server_days") or 0),
            "allow_host": bool(gw.get("allow_host")),
            "dm_winners": bool(gw.get("dm_winners", True)),
            "image": gw.get("image"),
            "thumbnail": gw.get("thumbnail"),
            "color": colour,
            "button_label": gw.get("button_label") or "Enter",
            "button_emoji": gw.get("button_emoji") or "🎉",
            "ping_role": gw.get("ping_role"),
        }

    @commands.group(name="giveaway", aliases=["gaway", "gw"], invoke_without_command=True)
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True, send_messages=True)
    async def giveaway(self, ctx: commands.Context) -> None:
        """Create a giveaway.

        Running `[p]giveaway` with no subcommand opens a private setup form.
        Use `[p]help giveaway` to see manage commands (`cancel`, `end`, `edit`, `list`).
        """
        if not await self._can_create(ctx):
            await ctx.send_help()
            return
        await self.begin_setup(ctx)

    @giveaway.command(name="start", aliases=["create", "build", "builder"])
    @commands.guild_only()
    @commands.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(embed_links=True, send_messages=True)
    async def giveaway_start(self, ctx: commands.Context, *, options: GiveawayFlags) -> None:
        """Same private setup as `[p]giveaway`. Flags pre-fill the popup.

        Pass `builder: no duration: 1h prize: Nitro` to post immediately.
        """
        draft = await self._draft_from_flags(ctx, options)
        skip_builder = options.builder is False
        if skip_builder:
            if not draft.get("prize") or not draft.get("duration_seconds"):
                raise commands.UserFeedbackCheckFailure(
                    "To skip the form, provide both `duration:` and `prize:`."
                )
            await self._cleanup_invoke(ctx)
            await self.start_from_draft(ctx, draft)
            return
        await self.begin_setup(ctx, draft)

    @giveaway.command(name="cancel", aliases=["stop"])
    @commands.guild_only()
    @commands.mod_or_permissions(manage_messages=True)
    async def giveaway_cancel(
        self, ctx: commands.Context, message_id: Optional[int] = None
    ) -> None:
        """Cancel an active giveaway. Pass the message ID if several are running."""
        gw = await self._resolve_giveaway(ctx, message_id)
        if not is_active(gw):
            await ctx.send("That giveaway is not active.")
            return
        await self.finish_giveaway(ctx.guild.id, int(gw["message_id"]), cancelled=True)
        await ctx.send(f"Cancelled the giveaway for **{gw.get('prize')}**.")

    @giveaway.command(name="end")
    @commands.guild_only()
    @commands.mod_or_permissions(manage_messages=True)
    async def giveaway_end(self, ctx: commands.Context, message_id: Optional[int] = None) -> None:
        """End a giveaway immediately and draw winners."""
        gw = await self._resolve_giveaway(ctx, message_id)
        if not is_active(gw):
            await ctx.send("That giveaway is not active.")
            return
        winners = await self.finish_giveaway(ctx.guild.id, int(gw["message_id"]), cancelled=False)
        if winners:
            await ctx.send("Giveaway ended and winners were drawn.")
        else:
            await ctx.send("Giveaway ended with no valid entries.")

    @giveaway.command(name="edit")
    @commands.guild_only()
    @commands.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(embed_links=True)
    async def giveaway_edit(
        self,
        ctx: commands.Context,
        message_id: int,
        *,
        options: GiveawayEditFlags,
    ) -> None:
        """Edit an active giveaway.

        Run with only an ID to open the interactive editor.
        Pass flags to apply changes immediately.

        **Flags**
        - `prize:` new prize
        - `winners:` new winner count
        - `description:` new description
        - `add:` extra time (`30m`, `2h`)
        - `duration:` reset remaining time
        - `colour:` new colour
        """
        gw = await self._resolve_giveaway(ctx, message_id)
        if not is_active(gw):
            await ctx.send("That giveaway is not active.")
            return

        changes: Dict[str, Any] = {}
        if options.prize:
            changes["prize"] = options.prize
        if options.winners is not None:
            changes["winners"] = options.winners
        if options.description is not None:
            changes["description"] = options.description
        if options.add_time:
            changes["add_seconds"] = options.add_time.total_seconds()
        if options.set_time:
            changes["end_ts"] = ts_now() + options.set_time.total_seconds()
        if options.image is not None:
            changes["image"] = options.image or None
        if options.thumbnail is not None:
            changes["thumbnail"] = options.thumbnail or None
        if options.colour:
            changes["color"] = int(options.colour)
        if options.allow_host is not None:
            changes["allow_host"] = options.allow_host
        if options.dm_winners is not None:
            changes["dm_winners"] = options.dm_winners
        if options.button_label:
            changes["button_label"] = options.button_label[:80]
        if options.min_account_days is not None:
            changes["min_account_days"] = max(0, options.min_account_days)
        if options.min_server_days is not None:
            changes["min_server_days"] = max(0, options.min_server_days)

        if not changes:
            await self.open_builder(ctx, self._draft_from_giveaway(gw), edit_of=gw)
            return

        apply_edit(gw, changes, now_ts=ts_now())
        ok, err = validate_duration_seconds(float(gw["end_ts"]) - ts_now())
        if not ok:
            await ctx.send(err)
            return

        await self._save(ctx.guild.id, int(gw["message_id"]), gw)
        self._schedule(ctx.guild.id, int(gw["message_id"]))
        await self._update_message(gw)
        await ctx.send(f"Updated giveaway `{gw['message_id']}`.")

    @giveaway.command(name="reroll")
    @commands.guild_only()
    @commands.mod_or_permissions(manage_messages=True)
    async def giveaway_reroll(
        self,
        ctx: commands.Context,
        message_id: int,
        winners: Optional[int] = None,
    ) -> None:
        """Reroll winners for an ended giveaway."""
        gw = await self._resolve_giveaway(ctx, message_id)
        if is_active(gw):
            await ctx.send("That giveaway is still running. Use `end` first.")
            return
        if gw.get("cancelled"):
            await ctx.send("Cancelled giveaways cannot be rerolled.")
            return
        count = clamp_winners(winners if winners is not None else gw.get("winners") or 1)
        new_winners = pick_winners(
            gw.get("entries") or {},
            count,
            exclude=gw.get("winner_ids") or [],
        )
        if not new_winners:
            new_winners = pick_winners(gw.get("entries") or {}, count)
        if not new_winners:
            await ctx.send("There are no entries to reroll.")
            return
        gw["winner_ids"] = new_winners
        gw["ended"] = True
        await self._save(ctx.guild.id, int(gw["message_id"]), gw)
        await self._update_message(gw, ended=True, winners=new_winners, disable=True)
        mentions = humanize_list([f"<@{uid}>" for uid in new_winners])
        await ctx.send(f"New winner(s) for **{gw.get('prize')}**: {mentions}")
        if gw.get("dm_winners"):
            await self._dm_winners(new_winners, gw.get("prize") or "the prize", ctx.guild.id)

    @giveaway.command(name="list")
    @commands.guild_only()
    async def giveaway_list(self, ctx: commands.Context) -> None:
        """List active giveaways in this server."""
        giveaways = await self.config.guild(ctx.guild).giveaways()
        active = [g for g in giveaways.values() if is_active(g)]
        if not active:
            await ctx.send("There are no active giveaways.")
            return
        lines = []
        for gw in sorted(active, key=lambda g: float(g.get("end_ts") or 0)):
            lines.append(
                f"`{gw.get('message_id')}` — **{gw.get('prize')}** — "
                f"{entry_count(gw)} entries — ends {discord_relative(float(gw['end_ts']))} "
                f"— <#{gw.get('channel_id')}>"
            )
        for page in pagify("\n".join(lines), delims=["\n"], page_length=1800):
            await ctx.send(page)

    @giveaway.command(name="info")
    @commands.guild_only()
    async def giveaway_info(self, ctx: commands.Context, message_id: int) -> None:
        """Show stored details for a giveaway."""
        gw = await self._resolve_giveaway(ctx, message_id)
        embed = self.build_embed(gw, ended=not is_active(gw), cancelled=bool(gw.get("cancelled")))
        await ctx.send(embed=embed)

    @giveaway.command(name="entries")
    @commands.guild_only()
    @commands.mod_or_permissions(manage_messages=True)
    async def giveaway_entries(self, ctx: commands.Context, message_id: Optional[int] = None) -> None:
        """Show how many people have entered a giveaway."""
        gw = await self._resolve_giveaway(ctx, message_id)
        entries = gw.get("entries") or {}
        if not entries:
            await ctx.send("No entries yet.")
            return
        await ctx.send(
            f"**{gw.get('prize')}** has {len(entries)} entrant(s) and {ticket_count(gw)} ticket(s)."
        )

    @commands.group(name="giveawayset", aliases=["gset"])
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def giveawayset(self, ctx: commands.Context) -> None:
        """Configure default giveaway settings for this server."""
        if ctx.invoked_subcommand is None:
            settings = await self.config.guild(ctx.guild).all()
            role_id = settings.get("manager_role")
            ping_id = settings.get("ping_role")
            embed = discord.Embed(title="Giveaway settings", colour=await ctx.embed_colour())
            embed.add_field(name="Default winners", value=str(settings.get("default_winners") or 1))
            embed.add_field(name="DM winners", value=str(bool(settings.get("dm_winners"))))
            embed.add_field(name="Max active", value=str(settings.get("max_active")))
            embed.add_field(name="Manager role", value=f"<@&{role_id}>" if role_id else "Not set")
            embed.add_field(name="Ping role", value=f"<@&{ping_id}>" if ping_id else "Not set")
            embed.set_footer(
                text="Use Red's Permissions cog to grant extra access to giveaway commands."
            )
            await ctx.send(embed=embed)

    @giveawayset.command(name="winners")
    async def giveawayset_winners(self, ctx: commands.Context, winners: int) -> None:
        """Set the default winner count for the builder."""
        value = clamp_winners(winners)
        await self.config.guild(ctx.guild).default_winners.set(value)
        await ctx.send(f"Default winners set to {value}.")

    @giveawayset.command(name="dm")
    async def giveawayset_dm(self, ctx: commands.Context, toggle: bool) -> None:
        """Enable or disable DMing winners by default."""
        await self.config.guild(ctx.guild).dm_winners.set(bool(toggle))
        await ctx.send(f"DM winners is now `{bool(toggle)}`.")

    @giveawayset.command(name="max")
    async def giveawayset_max(self, ctx: commands.Context, maximum: int) -> None:
        """Set how many giveaways may run at once (1-25)."""
        value = max(1, min(int(maximum), MAX_ACTIVE_PER_GUILD))
        await self.config.guild(ctx.guild).max_active.set(value)
        await ctx.send(f"Maximum active giveaways set to {value}.")

    @giveawayset.command(name="managerrole")
    async def giveawayset_managerrole(
        self, ctx: commands.Context, role: Optional[discord.Role] = None
    ) -> None:
        """Store a suggested manager role (does not bypass Red permissions).

        To actually grant access, use:
        `[p]permissions addrule allow giveaway start RoleName`
        """
        await self.config.guild(ctx.guild).manager_role.set(role.id if role else None)
        if role:
            await ctx.send(
                f"Recorded {role.mention} as the giveaway manager role.\n"
                "This is informational only. Use the Permissions cog to allow that role to run commands."
            )
        else:
            await ctx.send("Cleared the stored manager role.")

    @giveawayset.command(name="pingrole")
    async def giveawayset_pingrole(
        self, ctx: commands.Context, role: Optional[discord.Role] = None
    ) -> None:
        """Set a role to mention when a giveaway starts, or omit to clear."""
        await self.config.guild(ctx.guild).ping_role.set(role.id if role else None)
        if role:
            await ctx.send(f"Giveaway start pings will mention {role.mention} when `ping:` is used.")
        else:
            await ctx.send("Cleared the stored ping role.")

    @giveaway.command(name="bonus")
    @commands.guild_only()
    @commands.mod_or_permissions(manage_messages=True)
    async def giveaway_bonus(
        self,
        ctx: commands.Context,
        message_id: int,
        role: discord.Role,
        extra_tickets: int,
    ) -> None:
        """Give a role extra tickets on an active giveaway.

        Set `extra_tickets` to 0 to remove the bonus.
        """
        gw = await self._resolve_giveaway(ctx, message_id)
        if not is_active(gw):
            await ctx.send("That giveaway is not active.")
            return
        bonus = dict(gw.get("bonus_roles") or {})
        extra_tickets = max(0, min(int(extra_tickets), 50))
        if extra_tickets == 0:
            bonus.pop(str(role.id), None)
            await ctx.send(f"Removed bonus tickets for {role.mention}.")
        else:
            bonus[str(role.id)] = extra_tickets
            await ctx.send(f"{role.mention} now grants +{extra_tickets} extra ticket(s).")
        gw["bonus_roles"] = bonus
        await self._save(ctx.guild.id, int(gw["message_id"]), gw)
        await self._update_message(gw)
