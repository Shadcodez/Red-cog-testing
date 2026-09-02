from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import discord
from redbot.core import Config, commands, modlog
from redbot.core.bot import Red
from redbot.core.commands.converter import parse_timedelta
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils import bounded_gather
from redbot.core.utils.chat_formatting import box, humanize_list, humanize_timedelta, pagify

log = logging.getLogger("red.void.void")
_ = Translator("Void", __file__)

__version__ = "1.0.1"

CASETYPES = [
    {
        "name": "void",
        "default_setting": True,
        "image": "\N{BLACK CIRCLE FOR RECORD}",
        "case_str": "Void",
    },
    {
        "name": "unvoid",
        "default_setting": True,
        "image": "\N{WHITE HEAVY CHECK MARK}",
        "case_str": "Unvoid",
    },
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time_and_reason(text: Optional[str]) -> Tuple[Optional[timedelta], Optional[str]]:
    """Extract an optional duration and leftover reason from a free-form string."""
    if not text:
        return None, None
    text = text.strip()
    if not text:
        return None, None

    try:
        whole = parse_timedelta(text)
    except commands.BadArgument:
        whole = None
    if whole is not None:
        return whole, None

    parts = text.split()

    def _try(chunk: str) -> Optional[timedelta]:
        try:
            return parse_timedelta(chunk)
        except commands.BadArgument:
            return None

    # Duration at the start: "2h spam" / "1 day 2 hours raid"
    for end in range(len(parts), 0, -1):
        parsed = _try(" ".join(parts[:end]))
        if parsed is not None:
            reason = " ".join(parts[end:]).strip() or None
            return parsed, reason
    # Duration at the end: "spam 2h" / "raid 1 day"
    for start in range(len(parts)):
        parsed = _try(" ".join(parts[start:]))
        if parsed is not None:
            reason = " ".join(parts[:start]).strip() or None
            return parsed, reason
    return None, text


def _void_overwrite() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(
        view_channel=False,
        read_messages=False,
        read_message_history=False,
        connect=False,
        speak=False,
        send_messages=False,
        send_messages_in_threads=False,
        create_public_threads=False,
        create_private_threads=False,
        send_tts_messages=False,
        add_reactions=False,
        use_application_commands=False,
        embed_links=False,
        attach_files=False,
        mention_everyone=False,
        stream=False,
        use_voice_activation=False,
        priority_speaker=False,
        request_to_speak=False,
    )


class ReasonModal(discord.ui.Modal):
    def __init__(self, member: discord.Member, guild: discord.Guild, prefill: Optional[str] = None):
        super().__init__(title=_("Message to {name}").format(name=member.display_name)[:45])
        self.member = member
        self.guild = guild
        self.body = discord.ui.TextInput(
            label=_("Message"),
            style=discord.TextStyle.paragraph,
            placeholder=_("Explain the Void punishment. This is sent only to the member."),
            default=(prefill or "")[:1900],
            required=True,
            max_length=1900,
        )
        self.add_item(self.body)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title=_("You were Voided in {guild}").format(guild=self.guild.name),
            description=str(self.body.value),
            colour=discord.Colour.dark_gray(),
            timestamp=_utc_now(),
        )
        if self.guild.icon:
            embed.set_thumbnail(url=self.guild.icon.url)
        try:
            await self.member.send(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message(
                _("I could not DM {member}. Their DMs are closed or they blocked the bot.").format(
                    member=self.member.mention
                ),
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.response.send_message(
                _("Failed to deliver the DM to {member}.").format(member=self.member.mention),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            _("Sent the explanation to {member}.").format(member=self.member.mention),
            ephemeral=True,
        )


class StaffDMPrompt(discord.ui.View):
    """Private Yes/No prompt sent to the invoking moderator."""

    def __init__(
        self,
        author: discord.abc.User,
        member: discord.Member,
        guild: discord.Guild,
        prefill: Optional[str],
        timeout: float = 30.0,
    ):
        super().__init__(timeout=timeout)
        self.author_id = author.id
        self.member = member
        self.guild = guild
        self.prefill = prefill
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(_("This prompt is not for you."), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.success)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(ReasonModal(self.member, self.guild, self.prefill))
        self.stop()
        if self.message:
            try:
                await self.message.edit(
                    content=_("Opening a popup so you can type the message to send."),
                    view=None,
                )
            except discord.HTTPException:
                pass

    @discord.ui.button(label="No", style=discord.ButtonStyle.secondary)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            content=_("No extra message will be sent to {member}.").format(member=self.member.mention),
            view=None,
        )
        self.stop()

    async def on_timeout(self) -> None:
        if self.message:
            try:
                await self.message.edit(
                    content=_("Timed out after 30 seconds. No extra message was sent."),
                    view=None,
                )
            except discord.HTTPException:
                pass


@cog_i18n(_)
class Void(commands.Cog):
    """Hide a member from every channel with a timed isolation role.

    Void strips assignable roles, caches them, and applies a server-configured
    role whose channel overwrites deny viewing text, forum, voice, stage, and
    category channels. Duration works like core Mutes. Actions are written to
    Red's modlog as `void` and `unvoid` cases.

    Run `[p]voidset setup` once per server before using `[p]void`.
    See `[p]help void`, `[p]help unvoid`, and `[p]help voidset`.
    """

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre = super().format_help_for_context(ctx)
        return f"{pre}\n\nVersion: {__version__}"

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1447385412, force_registration=True)
        self.config.register_guild(
            role_id=None,
            role_name="void",
            default_duration=None,
            respect_hierarchy=True,
        )
        self.config.register_member(
            active=False,
            roles=[],
            until=None,
            moderator=None,
            reason=None,
            applied_at=None,
        )
        self._unvoid_tasks: Dict[Tuple[int, int], asyncio.Task] = {}
        self._enforcing: set[Tuple[int, int]] = set()
        self._ready = asyncio.Event()
        self._loop_task: Optional[asyncio.Task] = None

    async def cog_load(self) -> None:
        try:
            await modlog.register_casetypes(CASETYPES)
        except RuntimeError:
            log.debug("Void casetypes already registered.")
        except Exception:
            log.exception("Failed to register Void casetypes.")
        self._loop_task = asyncio.create_task(self._restore_and_watch())

    async def cog_unload(self) -> None:
        if self._loop_task:
            self._loop_task.cancel()
        for task in list(self._unvoid_tasks.values()):
            task.cancel()
        self._unvoid_tasks.clear()

    async def red_delete_data_for_user(self, *, requester: str, user_id: int) -> None:
        all_members = await self.config.all_members()
        for guild_id, members in all_members.items():
            if user_id in members:
                await self.config.member_from_ids(guild_id, user_id).clear()

    async def _restore_and_watch(self) -> None:
        await self.bot.wait_until_red_ready()
        await self._schedule_existing_voids()
        self._ready.set()

    async def _schedule_existing_voids(self) -> None:
        all_members = await self.config.all_members()
        now = _utc_now().timestamp()
        for guild_id, members in all_members.items():
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            for user_id, data in members.items():
                if not data.get("active"):
                    continue
                until = data.get("until")
                if until is None:
                    continue
                remaining = until - now
                if remaining <= 0:
                    member = guild.get_member(user_id)
                    if member is not None:
                        asyncio.create_task(self._finish_void(member, moderator=guild.me, reason=_("Automatic unvoid"), automatic=True))
                    else:
                        await self.config.member_from_ids(guild_id, user_id).active.set(False)
                else:
                    self._arm_unvoid(guild_id, user_id, remaining)

    def _arm_unvoid(self, guild_id: int, user_id: int, delay: float) -> None:
        key = (guild_id, user_id)
        old = self._unvoid_tasks.pop(key, None)
        if old and not old.done():
            old.cancel()
        self._unvoid_tasks[key] = asyncio.create_task(self._unvoid_after(guild_id, user_id, delay))

    async def _unvoid_after(self, guild_id: int, user_id: int, delay: float) -> None:
        try:
            await asyncio.sleep(max(delay, 0))
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                return
            member = guild.get_member(user_id)
            if member is None:
                await self.config.member_from_ids(guild_id, user_id).active.set(False)
                return
            await self._finish_void(member, moderator=guild.me, reason=_("Automatic unvoid"), automatic=True)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Automatic unvoid failed for %s in %s", user_id, guild_id)
        finally:
            self._unvoid_tasks.pop((guild_id, user_id), None)

    # ---------------------------------------------------------------------
    # Role + overwrite helpers
    # ---------------------------------------------------------------------

    async def _get_void_role(self, guild: discord.Guild) -> Optional[discord.Role]:
        role_id = await self.config.guild(guild).role_id()
        if role_id:
            role = guild.get_role(role_id)
            if role is not None:
                return role
        name = await self.config.guild(guild).role_name()
        for role in guild.roles:
            if role.name.lower() == (name or "void").lower() and role != guild.default_role:
                await self.config.guild(guild).role_id.set(role.id)
                return role
        return None

    async def _ensure_void_role(self, guild: discord.Guild, reason: str) -> discord.Role:
        role = await self._get_void_role(guild)
        if role is not None:
            return role
        name = await self.config.guild(guild).role_name() or "void"
        if not guild.me.guild_permissions.manage_roles:
            raise commands.BotMissingPermissions(["manage_roles"])
        role = await guild.create_role(
            name=name,
            permissions=discord.Permissions.none(),
            colour=discord.Colour.dark_gray(),
            hoist=False,
            mentionable=False,
            reason=reason,
        )
        await self.config.guild(guild).role_id.set(role.id)
        return role

    async def _apply_overwrites(
        self, guild: discord.Guild, role: discord.Role, reason: str
    ) -> List[discord.abc.GuildChannel]:
        overwrite = _void_overwrite()
        channels = list(guild.channels)

        async def apply(channel: discord.abc.GuildChannel) -> Optional[discord.abc.GuildChannel]:
            try:
                current = channel.overwrites_for(role)
                if (
                    current.view_channel is False
                    and current.connect is False
                    and current.send_messages is False
                ):
                    return None
                await channel.set_permissions(role, overwrite=overwrite, reason=reason)
                return None
            except (discord.Forbidden, discord.HTTPException):
                return channel

        results = await bounded_gather(*(apply(ch) for ch in channels), limit=4)
        return [ch for ch in results if ch is not None]

    def _assignable_roles(self, member: discord.Member) -> List[discord.Role]:
        me = member.guild.me
        out: List[discord.Role] = []
        for role in member.roles:
            if role.is_default() or role.managed:
                continue
            if me.top_role <= role:
                continue
            out.append(role)
        return out

    async def _hierarchy_ok(self, guild: discord.Guild, mod: discord.Member, target: discord.Member) -> bool:
        if not await self.config.guild(guild).respect_hierarchy():
            return True
        if mod == guild.owner or await self.bot.is_owner(mod):
            return True
        return mod.top_role > target.top_role

    # ---------------------------------------------------------------------
    # Core void / unvoid
    # ---------------------------------------------------------------------

    async def _apply_void(
        self,
        *,
        guild: discord.Guild,
        member: discord.Member,
        moderator: discord.Member,
        reason: Optional[str],
        duration: Optional[timedelta],
        created_at: datetime,
    ) -> Tuple[bool, str, Optional[datetime]]:
        if member.bot:
            return False, _("I will not Void a bot."), None
        if member == guild.owner:
            return False, _("I cannot Void the server owner."), None
        if member == guild.me:
            return False, _("I cannot Void myself."), None
        if member == moderator:
            return False, _("You cannot Void yourself."), None
        if not await self._hierarchy_ok(guild, moderator, member):
            return False, _("You cannot Void someone with an equal or higher top role."), None
        if member.guild_permissions.administrator and member != guild.owner:
            # Administrator bypasses channel overwrites; stripping the role is the only path.
            if member.top_role >= guild.me.top_role:
                return False, _("That member has Administrator and I cannot manage their roles."), None

        role = await self._get_void_role(guild)
        if role is None:
            return False, _("The Void role is not set up. Have an admin run `[p]voidset setup`."), None

        if role >= guild.me.top_role:
            return False, _("My highest role must be above the Void role so I can assign it."), None
        if moderator != guild.owner and role >= moderator.top_role and not await self.bot.is_owner(moderator):
            return False, _("The Void role is above your highest role, so you cannot assign it."), None
        if not guild.me.guild_permissions.manage_roles:
            return False, _("I need the Manage Roles permission."), None

        cached = await self.config.member(member).all()
        already = bool(cached.get("active"))
        stored_roles = list(cached.get("roles") or [])
        removable = self._assignable_roles(member)
        removable_ids = [r.id for r in removable if r.id != role.id]
        if not already:
            stored_roles = removable_ids
        else:
            merged = list(dict.fromkeys(stored_roles + removable_ids))
            stored_roles = [rid for rid in merged if rid != role.id]

        until_dt: Optional[datetime] = None
        if duration is not None:
            until_dt = created_at + duration
        elif not already:
            default = await self.config.guild(guild).default_duration()
            if default:
                duration = timedelta(seconds=int(default))
                until_dt = created_at + duration
        elif cached.get("until"):
            until_dt = datetime.fromtimestamp(float(cached["until"]), tz=timezone.utc)
        if already and not reason:
            reason = cached.get("reason")

        key = (guild.id, member.id)
        self._enforcing.add(key)
        try:
            new_roles = [r for r in member.roles if (r.managed or r.id == role.id) and not r.is_default()]
            if role not in new_roles:
                new_roles.append(role)
            await member.edit(roles=new_roles, reason=reason or _("Void"))
        except discord.Forbidden:
            self._enforcing.discard(key)
            return False, _("I am not allowed to edit that member's roles."), None
        except discord.HTTPException:
            self._enforcing.discard(key)
            return False, _("Discord rejected the role update for that member."), None
        finally:
            self._enforcing.discard(key)

        await self.config.member(member).set(
            {
                "active": True,
                "roles": stored_roles,
                "until": until_dt.timestamp() if until_dt else None,
                "moderator": moderator.id,
                "reason": reason,
                "applied_at": created_at.timestamp(),
            }
        )

        if until_dt is not None:
            self._arm_unvoid(guild.id, member.id, max((until_dt - _utc_now()).total_seconds(), 0))
        else:
            old = self._unvoid_tasks.pop((guild.id, member.id), None)
            if old and not old.done():
                old.cancel()

        try:
            await modlog.create_case(
                self.bot,
                guild,
                created_at,
                "void",
                member,
                moderator,
                reason,
                until=until_dt,
            )
        except Exception:
            log.exception("Failed to create void modlog case in %s", guild.id)

        verb = _("updated") if already else _("applied")
        if until_dt:
            length = humanize_timedelta(timedelta=until_dt - created_at)
            msg = _("Void {verb} for {member} for {length} (until {stamp}).").format(
                verb=verb,
                member=member.mention,
                length=length,
                stamp=discord.utils.format_dt(until_dt, "F"),
            )
        else:
            msg = _("Void {verb} for {member} indefinitely.").format(verb=verb, member=member.mention)
        return True, msg, until_dt

    async def _finish_void(
        self,
        member: discord.Member,
        *,
        moderator: Optional[discord.Member],
        reason: Optional[str],
        automatic: bool = False,
        created_at: Optional[datetime] = None,
    ) -> Tuple[bool, str]:
        guild = member.guild
        data = await self.config.member(member).all()
        if not data.get("active"):
            role = await self._get_void_role(guild)
            if role is None or role not in member.roles:
                return False, _("{member} is not Voided.").format(member=member.mention)

        role = await self._get_void_role(guild)
        stored_ids: List[int] = list(data.get("roles") or [])
        restore: List[discord.Role] = []
        for rid in stored_ids:
            found = guild.get_role(rid)
            if found is None or found.managed or found.is_default():
                continue
            if guild.me.top_role <= found:
                continue
            restore.append(found)

        current = [r for r in member.roles if r != role and not r.is_default()]
        combined = list({r.id: r for r in current + restore}.values())

        key = (guild.id, member.id)
        self._enforcing.add(key)
        try:
            await member.edit(roles=combined, reason=reason or _("Unvoid"))
        except discord.Forbidden:
            return False, _("I am not allowed to restore roles for {member}.").format(member=member.mention)
        except discord.HTTPException:
            return False, _("Discord rejected the role restore for {member}.").format(member=member.mention)
        finally:
            self._enforcing.discard(key)

        await self.config.member(member).set(
            {
                "active": False,
                "roles": [],
                "until": None,
                "moderator": None,
                "reason": None,
                "applied_at": None,
            }
        )
        old = self._unvoid_tasks.pop((guild.id, member.id), None)
        if old and not old.done():
            old.cancel()

        stamp = created_at or _utc_now()
        try:
            await modlog.create_case(
                self.bot,
                guild,
                stamp,
                "unvoid",
                member,
                moderator or guild.me,
                reason,
                until=None,
            )
        except Exception:
            log.exception("Failed to create unvoid modlog case in %s", guild.id)

        if automatic:
            return True, _("Automatically unvoided {member}.").format(member=member.mention)
        return True, _("Unvoided {member} and restored cached roles.").format(member=member.mention)

    async def _offer_staff_dm(
        self, ctx: commands.Context, member: discord.Member, reason: Optional[str]
    ) -> None:
        view = StaffDMPrompt(ctx.author, member, ctx.guild, reason, timeout=30)
        content = _(
            "Voided {member} in **{guild}**.\n"
            "Would you like to send them a private explanation?\n"
            "Click **Yes** to open a popup, or **No** to skip. This expires in 30 seconds."
        ).format(member=str(member), guild=ctx.guild.name)
        try:
            dm = await ctx.author.send(content, view=view)
            view.message = dm
        except (discord.Forbidden, discord.HTTPException):
            if ctx.interaction is not None:
                try:
                    msg = await ctx.send(content, view=view, ephemeral=True)
                    view.message = msg
                except discord.HTTPException:
                    return
            # Prefix commands cannot send a hidden channel message if DMs are closed.

    # ---------------------------------------------------------------------
    # Listeners
    # ---------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        guild = channel.guild
        role = await self._get_void_role(guild)
        if role is None:
            return
        try:
            await channel.set_permissions(
                role,
                overwrite=_void_overwrite(),
                reason=_("Void role overwrite for new channel"),
            )
        except (discord.Forbidden, discord.HTTPException):
            log.debug("Could not apply Void overwrite on %s in %s", channel.id, guild.id)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        data = await self.config.member(member).all()
        if not data.get("active"):
            return
        until = data.get("until")
        if until and until <= _utc_now().timestamp():
            await self.config.member(member).active.set(False)
            return
        role = await self._get_void_role(member.guild)
        if role is None:
            return
        key = (member.guild.id, member.id)
        self._enforcing.add(key)
        try:
            await member.add_roles(role, reason=_("Re-applied Void after rejoin"))
        except (discord.Forbidden, discord.HTTPException):
            log.debug("Could not re-apply Void role to %s", member.id)
        finally:
            self._enforcing.discard(key)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.roles == after.roles:
            return
        key = (after.guild.id, after.id)
        if key in self._enforcing:
            return
        data = await self.config.member(after).all()
        if not data.get("active"):
            return
        role = await self._get_void_role(after.guild)
        if role is None:
            return
        allowed = {r.id for r in after.roles if (r.managed or r.id == role.id) and not r.is_default()}
        extras = [r for r in after.roles if not r.is_default() and r.id not in allowed]
        need_add = role not in after.roles
        if not extras and not need_add:
            return
        new_roles = [r for r in after.roles if not r.is_default() and r.id in allowed]
        if need_add:
            new_roles.append(role)
        self._enforcing.add(key)
        try:
            await after.edit(roles=new_roles, reason=_("Void enforcement"))
        except (discord.Forbidden, discord.HTTPException):
            pass
        finally:
            self._enforcing.discard(key)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        stored = await self.config.guild(role.guild).role_id()
        if stored == role.id:
            await self.config.guild(role.guild).role_id.clear()
            log.info("Void role deleted in guild %s", role.guild.id)

    # ---------------------------------------------------------------------
    # Commands
    # ---------------------------------------------------------------------

    @commands.hybrid_command(name="void", usage="<member> [duration] [reason]")
    @commands.guild_only()
    @commands.mod_or_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @discord.app_commands.describe(
        member="The member to isolate from every channel",
        time_and_reason="Optional duration and/or reason, e.g. 2h spam",
    )
    async def void_member(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        time_and_reason: Optional[str] = None,
    ) -> None:
        """Strip a member's roles and hide every channel from them.

        Duration is optional and parsed like core Mutes (`1h`, `2 days`, `1w2d`).
        Anything that is not a duration is stored as the reason and sent to Red's
        modlog. If no duration is given, the server default from `[p]voidset defaulttime`
        is used. If that is unset, the Void lasts until `[p]unvoid`.

        After a successful Void the bot DMs you (the staff member) asking whether
        to send the user a private explanation. That prompt expires in 30 seconds.

        Examples:
        `[p]void @User`
        `[p]void @User 2h`
        `[p]void @User 1d spam in general`
        `[p]void 123456789012345678 30m`

        This command is locked to the mod role or Manage Roles.
        """
        if ctx.guild is None:
            return
        role = await self._get_void_role(ctx.guild)
        if role is None:
            await ctx.send(_("The Void role is not set up. An admin needs to run `{prefix}voidset setup`.").format(prefix=ctx.clean_prefix))
            return

        duration, reason = _parse_time_and_reason(time_and_reason)
        ok, message, _until = await self._apply_void(
            guild=ctx.guild,
            member=member,
            moderator=ctx.author,
            reason=reason,
            duration=duration,
            created_at=ctx.message.created_at.replace(tzinfo=timezone.utc)
            if ctx.message.created_at.tzinfo is None
            else ctx.message.created_at,
        )
        if not ok:
            await ctx.send(message)
            return

        embed = discord.Embed(
            title=_("Void"),
            description=message,
            colour=discord.Colour.dark_gray(),
            timestamp=_utc_now(),
        )
        embed.add_field(name=_("Member"), value=f"{member.mention}\n`{member.id}`", inline=True)
        embed.add_field(name=_("Moderator"), value=ctx.author.mention, inline=True)
        if reason:
            embed.add_field(name=_("Reason"), value=reason[:1024], inline=False)
        await ctx.send(embed=embed)
        await self._offer_staff_dm(ctx, member, reason)

    @commands.hybrid_command(name="unvoid", usage="<member> [reason]")
    @commands.guild_only()
    @commands.mod_or_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @discord.app_commands.describe(
        member="The member to restore",
        reason="Optional reason recorded in the modlog",
    )
    async def unvoid_member(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: Optional[str] = None,
    ) -> None:
        """Remove Void from a member and restore their cached roles.

        Roles that no longer exist, are managed, or sit above the bot are skipped.
        The action is logged as an `unvoid` modlog case.

        Examples:
        `[p]unvoid @User`
        `[p]unvoid @User appeal accepted`

        This command is locked to the mod role or Manage Roles.
        """
        ok, message = await self._finish_void(
            member,
            moderator=ctx.author,
            reason=reason,
            automatic=False,
            created_at=ctx.message.created_at.replace(tzinfo=timezone.utc)
            if ctx.message.created_at.tzinfo is None
            else ctx.message.created_at,
        )
        if ok:
            await ctx.send(message)
        else:
            await ctx.send(message)

    @commands.hybrid_command(name="activevoids")
    @commands.guild_only()
    @commands.mod_or_permissions(manage_roles=True)
    async def active_voids(self, ctx: commands.Context) -> None:
        """List members currently Voided in this server.

        Shows each target, whether the Void is timed or indefinite, and the
        stored reason.

        Example:
        `[p]activevoids`

        This command is locked to the mod role or Manage Roles.
        """
        assert ctx.guild is not None
        members_data = await self.config.all_members(ctx.guild)
        lines: List[str] = []
        now = _utc_now()
        for user_id, data in members_data.items():
            if not data.get("active"):
                continue
            member = ctx.guild.get_member(user_id)
            name = str(member) if member else f"{user_id}"
            until = data.get("until")
            if until:
                until_dt = datetime.fromtimestamp(until, tz=timezone.utc)
                if until_dt <= now:
                    length = _("expired, pending cleanup")
                else:
                    length = _("until {stamp}").format(stamp=discord.utils.format_dt(until_dt, "R"))
            else:
                length = _("indefinite")
            reason = data.get("reason") or _("no reason")
            lines.append(f"{name} ({user_id}) — {length} — {reason}")
        if not lines:
            await ctx.send(_("There are no active Voids in this server."))
            return
        output = _("Active Voids:\n") + "\n".join(lines)
        for page in pagify(output, delims=["\n"]):
            await ctx.send(box(page, lang="md"))

    @commands.group(name="voidset")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def voidset(self, ctx: commands.Context) -> None:
        """Configure Void for this server.

        Create the isolation role, rename it, set a default duration, and
        refresh channel overwrites. Calling this group with no subcommand
        shows this help page.

        Subcommands:
        `[p]voidset setup`
        `[p]voidset settings`
        `[p]voidset rolename <name>`
        `[p]voidset role <role>`
        `[p]voidset applyoverwrites`
        `[p]voidset defaulttime [duration]`
        `[p]voidset hierarchy [true|false]`

        This command is locked to the admin role or Manage Server.
        """

    @voidset.command(name="setup")
    async def voidset_setup(self, ctx: commands.Context) -> None:
        """Create the Void role and hide every channel from it.

        Creates the role when missing, then denies view and connect on text,
        voice, stage, forum, category, and other guild channel types.

        Example:
        `[p]voidset setup`
        """
        assert ctx.guild is not None
        if not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.send(_("I need Manage Roles to create and assign the Void role."))
            return
        if not ctx.guild.me.guild_permissions.manage_channels:
            await ctx.send(_("I need Manage Channels to set Void overwrites on every channel."))
            return

        async with ctx.typing():
            role = await self._ensure_void_role(ctx.guild, reason=_("Void role setup by {mod}").format(mod=ctx.author))
            failed = await self._apply_overwrites(
                ctx.guild, role, reason=_("Void role setup by {mod}").format(mod=ctx.author)
            )

        extra = ""
        if failed:
            names = humanize_list([ch.mention if hasattr(ch, "mention") else ch.name for ch in failed[:15]])
            extra = _("\nI could not edit permissions in: {channels}").format(channels=names)
            if len(failed) > 15:
                extra += _(" and {count} more.").format(count=len(failed) - 15)
        await ctx.send(
            _("Void is ready. Role: {role} (`{id}`). Overwrites applied on visible channels.{extra}").format(
                role=role.mention, id=role.id, extra=extra
            )
        )

    @voidset.command(name="rolename", usage="<name>")
    async def voidset_rolename(self, ctx: commands.Context, *, name: str) -> None:
        """Rename the Void role in settings and in Discord.

        Example:
        `[p]voidset rolename Isolated`
        """
        assert ctx.guild is not None
        name = name.strip()
        if not name or len(name) > 100:
            await ctx.send(_("Provide a role name between 1 and 100 characters."))
            return
        await self.config.guild(ctx.guild).role_name.set(name)
        role = await self._get_void_role(ctx.guild)
        renamed = False
        if role is not None:
            try:
                await role.edit(name=name, reason=_("Void role renamed by {mod}").format(mod=ctx.author))
                renamed = True
            except discord.Forbidden:
                await ctx.send(_("Saved the name, but I could not rename the existing role."))
                return
            except discord.HTTPException:
                await ctx.send(_("Saved the name, but Discord rejected the role rename."))
                return
        if renamed:
            await ctx.send(_("Void role renamed to `{name}`.").format(name=name))
        else:
            await ctx.send(
                _("Saved `{name}` as the Void role name. Run `{prefix}voidset setup` to create it.").format(
                    name=name, prefix=ctx.clean_prefix
                )
            )

    @voidset.command(name="role", usage="<role>")
    async def voidset_role(self, ctx: commands.Context, role: discord.Role) -> None:
        """Use an existing role as the Void role instead of creating one.

        Example:
        `[p]voidset role @void`
        """
        assert ctx.guild is not None
        if role.is_default() or role.is_premium_subscriber() or role.managed:
            await ctx.send(_("That role cannot be used as the Void role."))
            return
        if role >= ctx.guild.me.top_role and ctx.guild.owner != ctx.guild.me:
            await ctx.send(_("I cannot manage that role because it is above me."))
            return
        await self.config.guild(ctx.guild).role_id.set(role.id)
        await self.config.guild(ctx.guild).role_name.set(role.name)
        await ctx.send(_("Void will now use {role}. Run `{prefix}voidset applyoverwrites` if needed.").format(
            role=role.mention, prefix=ctx.clean_prefix
        ))

    @voidset.command(name="applyoverwrites")
    async def voidset_applyoverwrites(self, ctx: commands.Context) -> None:
        """Re-apply view-deny overwrites for the Void role on every channel.

        Example:
        `[p]voidset applyoverwrites`
        """
        assert ctx.guild is not None
        role = await self._get_void_role(ctx.guild)
        if role is None:
            await ctx.send(_("No Void role is configured. Run `{prefix}voidset setup` first.").format(prefix=ctx.clean_prefix))
            return
        async with ctx.typing():
            failed = await self._apply_overwrites(ctx.guild, role, reason=_("Void overwrite refresh by {mod}").format(mod=ctx.author))
        if failed:
            await ctx.send(_("Applied overwrites, but {count} channel(s) could not be updated.").format(count=len(failed)))
        else:
            await ctx.send(_("Overwrites refreshed on every channel I can edit."))

    @voidset.command(name="defaulttime", aliases=["time"], usage="[duration]")
    async def voidset_defaulttime(self, ctx: commands.Context, *, duration: Optional[str] = None) -> None:
        """Set the default Void duration when `[p]void` has no time.

        Omit the duration to clear it and make Voids indefinite by default.

        Examples:
        `[p]voidset defaulttime 2h`
        `[p]voidset defaulttime`
        """
        assert ctx.guild is not None
        if duration is None:
            await self.config.guild(ctx.guild).default_duration.clear()
            await ctx.send(_("Default Void duration cleared. Voids are indefinite unless a time is given."))
            return
        try:
            parsed = parse_timedelta(duration)
        except commands.BadArgument as exc:
            await ctx.send(str(exc))
            return
        if parsed is None or parsed.total_seconds() <= 0:
            await ctx.send(_("I could not understand that duration. Try `2h`, `1d`, or `1w2d`."))
            return
        await self.config.guild(ctx.guild).default_duration.set(int(parsed.total_seconds()))
        await ctx.send(
            _("Default Void duration set to {length}.").format(length=humanize_timedelta(timedelta=parsed))
        )

    @voidset.command(name="hierarchy", usage="[true_or_false]")
    async def voidset_hierarchy(self, ctx: commands.Context, enabled: Optional[bool] = None) -> None:
        """Toggle whether Void respects role hierarchy.

        Defaults to true. Omit the value to see the current setting.

        Examples:
        `[p]voidset hierarchy`
        `[p]voidset hierarchy true`
        `[p]voidset hierarchy false`
        """
        assert ctx.guild is not None
        if enabled is None:
            current = await self.config.guild(ctx.guild).respect_hierarchy()
            await ctx.send(
                _("Role hierarchy is currently {state}.").format(state=_("respected") if current else _("ignored"))
            )
            return
        await self.config.guild(ctx.guild).respect_hierarchy.set(enabled)
        await ctx.send(_("Void will {state} role hierarchy.").format(state=_("respect") if enabled else _("ignore")))

    @voidset.command(name="settings")
    async def voidset_settings(self, ctx: commands.Context) -> None:
        """Show Void settings for this server.

        Example:
        `[p]voidset settings`
        """
        assert ctx.guild is not None
        conf = await self.config.guild(ctx.guild).all()
        role = await self._get_void_role(ctx.guild)
        default = conf.get("default_duration")
        if default:
            default_str = humanize_timedelta(seconds=default)
        else:
            default_str = _("indefinite")
        embed = discord.Embed(title=_("Void settings"), colour=await ctx.embed_colour())
        embed.add_field(
            name=_("Role"),
            value=f"{role.mention} (`{role.id}`)" if role else _("not created"),
            inline=False,
        )
        embed.add_field(name=_("Stored role name"), value=conf.get("role_name") or "void", inline=True)
        embed.add_field(name=_("Default duration"), value=default_str, inline=True)
        embed.add_field(
            name=_("Respect hierarchy"),
            value=_("yes") if conf.get("respect_hierarchy", True) else _("no"),
            inline=True,
        )
        await ctx.send(embed=embed)
