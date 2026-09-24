from __future__ import annotations

import logging
import random
import re
import time
from typing import Dict, List, Optional

import discord
from redbot.core import Config, checks, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, escape, humanize_list, pagify
from redbot.core.utils.views import SimpleMenu

log = logging.getLogger("red.usershammer.usershammer")

__version__ = "1.3.0"

# Internal action keys. These are never registered as top-level command names
# so they cannot collide with Red's real Mod / Mutes commands.
ACTIONS = ("ban", "kick", "mute", "timeout")

DEFAULT_COMMAND_NAMES = {
    "ban": "banish",
    "kick": "remove",
    "mute": "silence",
    "timeout": "chatmute",
}

DEFAULT_UNDO_NAMES = {
    "ban": "unbanish",
    "kick": "unremove",
    "mute": "unsilence",
    "timeout": "unchatmute",
}

DEFAULT_LABELS = {
    "ban": "Ban",
    "kick": "Kick",
    "mute": "Mute",
    "timeout": "Timeout",
}

PAST_TENSE = {
    "ban": "banned",
    "kick": "kicked",
    "mute": "muted",
    "timeout": "timed out",
}

UNDO_PAST = {
    "ban": "unbanned",
    "kick": "unkicked",
    "mute": "unmuted",
    "timeout": "removed from timeout",
}

# Names that must never be claimed by this cog.
RESERVED_COMMANDS = {
    "ban",
    "kick",
    "mute",
    "timeout",
    "softban",
    "tempban",
    "hackban",
    "massban",
    "unban",
    "unmute",
    "untimeout",
    "voicekick",
    "voicemute",
    "voiceunmute",
    "voiceunban",
    "warn",
    "warning",
    "warnings",
    "purge",
    "cleanup",
    "mod",
    "modset",
    "muteset",
    "slowmode",
    "rename",
    "load",
    "unload",
    "reload",
    "help",
    "settings",
    "set",
    "permissions",
}

COMMAND_NAME_RE = re.compile(r"^[a-z][a-z0-9]{0,31}$")

DEFAULT_RESPONSES = {
    "ban": [
        "🔨 **{action} issued.** {target} is banned from {server}. Reason: {reason}",
        "Case #{case} — {target} (`{target.id}`) has been banned by {moderator}. Reason: {reason}",
        "{target} caught the ban hammer. They are no longer welcome in {server}. Reason: {reason}",
        "Permanently banned {target}. Staff notes: {reason}",
        "The hammer has spoken. {moderator} banned {target} from {server}.",
    ],
    "kick": [
        "👢 **{action} issued.** {target} has been kicked from {server}. Reason: {reason}",
        "Case #{case} — {target} was kicked by {moderator}. Reason: {reason}",
        "{target} has been removed from the server. Door's that way. Reason: {reason}",
        "Kicked {target} (`{target.id}`). They may rejoin if they promise to behave. Reason: {reason}",
        "{moderator} showed {target} the exit. Reason: {reason}",
    ],
    "mute": [
        "🤐 **{action} issued.** {target} has been muted in {server}. Reason: {reason}",
        "Case #{case} — {target} can look, but they cannot type. Muted by {moderator}. Reason: {reason}",
        "Muted {target}. Enjoy the quiet, {server}. Reason: {reason}",
        "{target} has been silenced. Staff notes: {reason}",
        "{moderator} hit mute on {target}. Reason: {reason}",
    ],
    "timeout": [
        "⏳ **{action} issued.** {target} has been timed out. Reason: {reason}",
        "Case #{case} — {target} is taking a little break. Applied by {moderator}. Reason: {reason}",
        "{target} has been sent to sit in the corner. Duration: spiritually 28 days. Reason: {reason}",
        "Timed out {target} (`{target.id}`). They can come back when the timer says so. Reason: {reason}",
        "{moderator} put {target} on a timeout. Reason: {reason}",
    ],
}

DEFAULT_UNDO_RESPONSES = {
    "ban": [
        "✅ {target} has been unbanned from {server}. Welcome back… probably.",
        "Case #{case} — {moderator} lifted the ban on {target}. Reason: {reason}",
        "The hammer has been put away. {target} may return to {server}.",
    ],
    "kick": [
        "✅ {target} has been unkicked (spiritually). The door is open again.",
        "Case #{case} — {moderator} reversed the kick on {target}. Reason: {reason}",
        "{target} has been invited back after that kick. Reason: {reason}",
    ],
    "mute": [
        "✅ {target} has been unmuted. Use this power wisely.",
        "Case #{case} — {moderator} restored {target}'s voice. Reason: {reason}",
        "Mute lifted for {target}. Reason: {reason}",
    ],
    "timeout": [
        "✅ {target} is no longer timed out. Recess is over.",
        "Case #{case} — {moderator} ended {target}'s timeout. Reason: {reason}",
        "{target} may speak again. Reason: {reason}",
    ],
}

DEFAULT_REASON = "No reason provided"
DEFAULT_DISCLAIMER = (
    "This does not actually ban, kick, mute, or timeout users."
)


class UsersHammer(commands.Cog):
    """Playful mock-moderation. Nobody is actually punished.

    Open the tabbed help menu with `[p]uh` or `[p]uh cmds`.
    """

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=0x5553484D, force_registration=True
        )
        self.config.register_global(
            command_names=dict(DEFAULT_COMMAND_NAMES),
            undo_names=dict(DEFAULT_UNDO_NAMES),
        )
        self.config.register_guild(
            enabled=True,
            random=True,
            disclaimer=True,
            disclaimer_text=DEFAULT_DISCLAIMER,
            disclaimers={action: "" for action in ACTIONS},
            dm_target=True,
            embeds=True,
            respect_hierarchy=False,
            allow_self=True,
            allow_bots=True,
            include_defaults=True,
            cooldown=15,
            backfire=False,
            modlog_enabled=False,
            modlog_channel=None,
            labels=dict(DEFAULT_LABELS),
            aliases={action: [] for action in ACTIONS},
            undo_aliases={action: [] for action in ACTIONS},
            responses={action: [] for action in ACTIONS},
            undo_responses={action: [] for action in ACTIONS},
            case_count=0,
        )
        self._user_buckets: Dict[int, Dict[int, float]] = {}

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre = super().format_help_for_context(ctx)
        return f"{pre}\n\nCog Version: {__version__}"

    async def red_delete_data_for_user(self, **kwargs) -> None:
        # This cog does not store user IDs.
        return

    async def cog_load(self) -> None:
        log.debug("UsersHammer loaded")

    async def cog_unload(self) -> None:
        log.debug("UsersHammer unloaded")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_name(name: str) -> str:
        return name.strip().lower()

    def _validate_command_name(self, name: str) -> Optional[str]:
        name = self._clean_name(name)
        if not COMMAND_NAME_RE.match(name):
            return (
                "Command words must be lowercase letters first, then letters or "
                "digits, max 32 characters."
            )
        if name in RESERVED_COMMANDS:
            return (
                f"`{name}` is reserved so this cog never shadows a real "
                "moderation command."
            )
        if name in {"usershammer", "uh", "uhset", "usershammerset", "uhammer"}:
            return f"`{name}` is already used by this cog."
        return None

    async def _is_staff(self, ctx: commands.Context) -> bool:
        if await self.bot.is_owner(ctx.author):
            return True
        if ctx.guild is None:
            return False
        if await self.bot.is_mod(ctx.author):
            return True
        if isinstance(ctx.author, discord.Member):
            return ctx.author.guild_permissions.manage_guild
        return False

    def _disclaimer_text(self, conf: dict, action: str) -> str:
        per_action = (conf.get("disclaimers") or {}).get(action) or ""
        if per_action.strip():
            return per_action.strip()
        shared = (conf.get("disclaimer_text") or "").strip()
        return shared or DEFAULT_DISCLAIMER

    async def _guild_conf(self, guild: discord.Guild) -> dict:
        return await self.config.guild(guild).all()

    async def _command_names(self) -> Dict[str, str]:
        stored = await self.config.command_names()
        merged = dict(DEFAULT_COMMAND_NAMES)
        merged.update({k: v for k, v in stored.items() if k in ACTIONS})
        return merged

    async def _undo_names(self) -> Dict[str, str]:
        stored = await self.config.undo_names()
        merged = dict(DEFAULT_UNDO_NAMES)
        merged.update({k: v for k, v in stored.items() if k in ACTIONS})
        return merged

    def _action_from_word(
        self,
        word: str,
        command_names: Dict[str, str],
        undo_names: Dict[str, str],
        aliases: Dict[str, List[str]],
        undo_aliases: Dict[str, List[str]],
    ) -> Optional[tuple]:
        word = self._clean_name(word)
        for action in ACTIONS:
            if word == command_names.get(action):
                return action, False
            if word == undo_names.get(action):
                return action, True
            if word in {self._clean_name(a) for a in aliases.get(action, [])}:
                return action, False
            if word in {self._clean_name(a) for a in undo_aliases.get(action, [])}:
                return action, True
        return None

    def _pick_response(
        self,
        action: str,
        conf: dict,
        *,
        undo: bool,
    ) -> str:
        key = "undo_responses" if undo else "responses"
        defaults = DEFAULT_UNDO_RESPONSES if undo else DEFAULT_RESPONSES
        pool: List[str] = list(conf.get(key, {}).get(action, []) or [])
        if conf.get("include_defaults", True) or not pool:
            pool = list(defaults.get(action, [])) + pool
        if not pool:
            verb = UNDO_PAST[action] if undo else PAST_TENSE[action]
            return f"{{target}} has been {verb}. Reason: {{reason}}"
        if conf.get("random", True):
            return random.choice(pool)
        return pool[-1] if conf.get(key, {}).get(action) else pool[0]

    def _format_response(
        self,
        template: str,
        *,
        action: str,
        label: str,
        target: discord.Member,
        moderator: discord.Member,
        reason: str,
        case: int,
        guild: discord.Guild,
        undo: bool,
    ) -> str:
        past = UNDO_PAST[action] if undo else PAST_TENSE[action]
        mapping = {
            "target": escape(str(target.display_name), mass_mentions=True),
            "target.mention": target.mention,
            "target.id": str(target.id),
            "target.name": escape(str(target.name), mass_mentions=True),
            "moderator": escape(str(moderator.display_name), mass_mentions=True),
            "moderator.mention": moderator.mention,
            "moderator.id": str(moderator.id),
            "reason": escape(reason, mass_mentions=True),
            "action": escape(label, mass_mentions=True),
            "action_past": past,
            "server": escape(guild.name, mass_mentions=True),
            "guild": escape(guild.name, mass_mentions=True),
            "case": str(case),
        }

        def repl(match: re.Match) -> str:
            key = match.group(1)
            return mapping.get(key, match.group(0))

        text = re.sub(r"\{([a-zA-Z0-9_.]+)\}", repl, template)
        return text[:1900]

    def _hierarchy_blocked(
        self, author: discord.Member, target: discord.Member
    ) -> bool:
        guild = author.guild
        if author.id == guild.owner_id:
            return False
        if target.id == guild.owner_id:
            return True
        if author.top_role <= target.top_role:
            return True
        return False

    async def _do_action(
        self,
        ctx: commands.Context,
        action: str,
        target: discord.Member,
        reason: Optional[str],
        *,
        undo: bool = False,
    ) -> None:
        if ctx.guild is None:
            return
        conf = await self._guild_conf(ctx.guild)
        if not conf.get("enabled", True):
            await ctx.send("UsersHammer is disabled in this server.")
            return

        intended = target
        backfired = False
        if (
            conf.get("backfire")
            and intended.id != ctx.author.id
            and isinstance(ctx.author, discord.Member)
            and random.randint(1, 5) == 1
        ):
            target = ctx.author
            backfired = True

        if (
            not backfired
            and target.id == ctx.author.id
            and not conf.get("allow_self", True)
        ):
            await ctx.send("You cannot use this on yourself here.")
            return
        if target.bot and not conf.get("allow_bots", True):
            await ctx.send("Bots are off-limits for joke actions here.")
            return
        if (
            not backfired
            and conf.get("respect_hierarchy")
            and isinstance(ctx.author, discord.Member)
        ):
            if self._hierarchy_blocked(ctx.author, intended):
                await ctx.send(
                    "Hierarchy is on. You can only joke-moderate members "
                    "below your highest role."
                )
                return

        cooldown = int(conf.get("cooldown", 15) or 0)
        if cooldown > 0 and not await self.bot.is_owner(ctx.author):
            now = time.monotonic()
            bucket = self._user_buckets.setdefault(ctx.guild.id, {})
            ready_at = bucket.get(ctx.author.id, 0.0)
            if now < ready_at:
                wait = int(ready_at - now) + 1
                await ctx.send(f"Easy, hammer-wielder. Try again in {wait}s.")
                return
            bucket[ctx.author.id] = now + cooldown

        reason_text = (reason or "").strip() or DEFAULT_REASON
        try:
            async with self.config.guild(ctx.guild).case_count.get_lock():
                case = int(await self.config.guild(ctx.guild).case_count() or 0) + 1
                await self.config.guild(ctx.guild).case_count.set(case)
        except (AttributeError, TypeError, ValueError):
            case = int(conf.get("case_count") or 0) + 1
            await self.config.guild(ctx.guild).case_count.set(case)

        labels = conf.get("labels") or {}
        label = labels.get(action) or DEFAULT_LABELS[action]
        if undo:
            label = f"Un{label}" if not label.lower().startswith("un") else label

        template = self._pick_response(action, conf, undo=undo)
        body = self._format_response(
            template,
            action=action,
            label=label,
            target=target,
            moderator=ctx.author,
            reason=reason_text,
            case=case,
            guild=ctx.guild,
            undo=undo,
        )

        mentions = discord.AllowedMentions(
            everyone=False, roles=False, users=[target, ctx.author]
        )
        disclaimer = self._format_response(
            self._disclaimer_text(conf, action),
            action=action,
            label=label,
            target=target,
            moderator=ctx.author,
            reason=reason_text,
            case=case,
            guild=ctx.guild,
            undo=undo,
        )[:2048]
        if backfired:
            body = (
                f"The hammer slipped. {ctx.author.mention} meant to hit "
                f"{intended.mention}, but it came back on them.\n\n{body}"
            )
        body = body[:4000]
        reason_field = escape(reason_text, mass_mentions=True)[:1000] or DEFAULT_REASON

        me = ctx.guild.me
        channel_perms = ctx.channel.permissions_for(me) if me else None
        can_embed = bool(
            conf.get("embeds", True)
            and channel_perms
            and channel_perms.embed_links
            and channel_perms.send_messages
        )

        sent = False
        if can_embed:
            try:
                try:
                    color = await ctx.embed_colour()
                except TypeError:
                    color = discord.Color.red()
                title = f"{label} — case #{case}"
                if backfired:
                    title = f"{title} (backfire)"
                embed = discord.Embed(title=title[:256], description=body or "\u200b", color=color)
                embed.add_field(name="Target", value=f"{target.mention}\n`{target.id}`"[:1024])
                embed.add_field(name="Issued by", value=(ctx.author.mention or str(ctx.author))[:1024])
                embed.add_field(name="Reason", value=reason_field, inline=False)
                if conf.get("disclaimer", True) and disclaimer.strip():
                    embed.set_footer(text=disclaimer[:2048])
                await ctx.send(embed=embed, allowed_mentions=mentions)
                sent = True
            except (TypeError, ValueError, discord.Forbidden, discord.HTTPException):
                log.debug("Embed send failed for %s; falling back to text", action, exc_info=True)

        if not sent:
            text = body or "Done."
            if conf.get("disclaimer", True) and disclaimer.strip():
                text = f"{text}\n{disclaimer}"
            try:
                await ctx.send(text[:2000], allowed_mentions=mentions)
            except discord.HTTPException:
                await ctx.send("Could not send that joke action in this channel.")

        try:
            await self._post_fake_modlog(
                ctx,
                conf=conf,
                action=action,
                label=label,
                target=target,
                intended=intended,
                reason=reason_field,
                case=case,
                undo=undo,
                backfired=backfired,
            )
        except (discord.HTTPException, discord.Forbidden, AttributeError):
            log.exception("Fake modlog failed")

        try:
            await self._dm_user(
                target,
                conf=conf,
                action=action,
                label=label,
                body=body,
                disclaimer=disclaimer,
                case=case,
                show_disclaimer=bool(conf.get("disclaimer", True)),
            )
        except (discord.HTTPException, discord.Forbidden):
            log.debug("DM failed for %s", target.id)

    async def _dm_user(
        self,
        target: discord.Member,
        *,
        conf: dict,
        action: str,
        label: str,
        body: str,
        disclaimer: str,
        case: int,
        show_disclaimer: bool,
    ) -> None:
        if not conf.get("dm_target", True):
            return
        if target.bot:
            return
        text = f"**UsersHammer {label} — case #{case}**\n{body}"
        if show_disclaimer:
            text = f"{text}\n\n{disclaimer}"
        try:
            await target.send(text[:1900])
        except (discord.Forbidden, discord.HTTPException):
            log.debug("Could not DM %s for UsersHammer action %s", target.id, action)

    async def _send_pages(
        self,
        ctx: commands.Context,
        pages: List,
        *,
        use_select: bool = True,
    ) -> None:
        if not pages:
            return
        if len(pages) == 1:
            page = pages[0]
            if isinstance(page, discord.Embed):
                await ctx.send(embed=page)
            elif isinstance(page, dict):
                await ctx.send(**page)
            else:
                await ctx.send(str(page))
            return
        await SimpleMenu(
            pages,
            timeout=180.0,
            use_select_menu=use_select,
            disable_after_timeout=True,
        ).start(ctx)

    async def _pagify_embed_pages(
        self,
        ctx: commands.Context,
        *,
        title: str,
        body: str,
        footer: Optional[str] = None,
        page_length: int = 900,
    ) -> List[discord.Embed]:
        chunks = list(pagify(body, delims=["\n"], page_length=page_length, shorten_by=0))
        if not chunks:
            chunks = ["Nothing to show."]
        color = await ctx.embed_colour()
        pages = []
        total = len(chunks)
        for i, chunk in enumerate(chunks, start=1):
            embed = discord.Embed(title=title, description=chunk, color=color)
            extra = f"Page {i}/{total}"
            embed.set_footer(text=f"{footer} • {extra}" if footer else extra)
            pages.append(embed)
        return pages

    async def _help_embeds(self, ctx: commands.Context, *, staff: bool) -> List[discord.Embed]:
        names = await self._command_names()
        undos = await self._undo_names()
        p = ctx.clean_prefix
        color = await ctx.embed_colour()
        note = DEFAULT_DISCLAIMER
        if ctx.guild:
            note = self._disclaimer_text(await self._guild_conf(ctx.guild), "ban")

        members = discord.Embed(
            title="UsersHammer — Members",
            description=(
                "Roleplay only. Nobody is banned, kicked, muted, or timed out.\n"
                f"{note}"
            ),
            color=color,
        )
        members.add_field(
            name="Joke actions",
            value="\n".join(
                [
                    f"`{p}{names['ban']} @user [reason]` — ban",
                    f"`{p}{names['kick']} @user [reason]` — kick",
                    f"`{p}{names['mute']} @user [reason]` — mute",
                    f"`{p}{names['timeout']} @user [reason]` — timeout",
                ]
            ),
            inline=False,
        )
        members.add_field(
            name="Lift the joke",
            value=(
                f"`{p}{undos['ban']}` `{p}{undos['kick']}` "
                f"`{p}{undos['mute']}` `{p}{undos['timeout']}`"
            ),
            inline=False,
        )
        members.add_field(
            name="Also",
            value=(
                f"`{p}uh ban|kick|mute|timeout @user`\n"
                f"`{p}uh actions` — words this server uses\n"
                f"`{p}uh cmds` — this menu"
            ),
            inline=False,
        )
        members.set_footer(text="Use the select menu or buttons to switch tabs.")
        pages = [members]

        if not staff:
            return pages

        staff_embed = discord.Embed(
            title="UsersHammer — Staff",
            description="Mod or Manage Server. These never apply a real punishment.",
            color=color,
        )
        staff_embed.add_field(
            name="Core",
            value="\n".join(
                [
                    f"`{p}uhset settings`",
                    f"`{p}uhset toggle`",
                    f"`{p}uhset random`",
                    f"`{p}uhset defaults`",
                    f"`{p}uhset embeds`",
                    f"`{p}uhset cooldown <seconds>`",
                    f"`{p}uhset hierarchy`",
                    f"`{p}uhset selftarget`",
                    f"`{p}uhset bottarget`",
                    f"`{p}uhset backfire`",
                    f"`{p}uhset dm`",
                ]
            ),
            inline=False,
        )
        staff_embed.set_footer(text="Tab 2 • Staff")
        pages.append(staff_embed)

        text_embed = discord.Embed(
            title="UsersHammer — Text",
            description="Edit joke lines and the footer per command.",
            color=color,
        )
        text_embed.add_field(
            name="Lines",
            value="\n".join(
                [
                    f"`{p}uhset text <ban|kick|mute|timeout> <message>`",
                    f"`{p}uhset response add <action> <text>`",
                    f"`{p}uhset response list <action>`",
                    f"`{p}uhset response remove <action> <index>`",
                    f"`{p}uhset response clear <action>`",
                    f"`{p}uhset label <action> <label>`",
                ]
            ),
            inline=False,
        )
        text_embed.add_field(
            name="Disclaimer",
            value="\n".join(
                [
                    f"`{p}uhset disclaimer`",
                    f"`{p}uhset disclaimer toggle`",
                    f"`{p}uhset disclaimer text <text>`",
                    f"`{p}uhset disclaimer text <action> <text>`",
                    f"`{p}uhset disclaimer reset`",
                ]
            ),
            inline=False,
        )
        text_embed.add_field(
            name="Placeholders",
            value=(
                "`{target}` `{target.mention}` `{target.id}` `{target.name}`\n"
                "`{moderator}` `{moderator.mention}` `{reason}`\n"
                "`{action}` `{action_past}` `{server}` `{case}`"
            ),
            inline=False,
        )
        text_embed.set_footer(text="Tab 3 • Text")
        pages.append(text_embed)

        extra = discord.Embed(
            title="UsersHammer — Modlog & aliases",
            color=color,
        )
        extra.add_field(
            name="Fake modlog",
            value="\n".join(
                [
                    f"`{p}uhset modlog`",
                    f"`{p}uhset modlog channel #channel`",
                    f"`{p}uhset modlog toggle`",
                ]
            ),
            inline=False,
        )
        extra.add_field(
            name="Aliases",
            value="\n".join(
                [
                    f"`{p}uhset alias add <action> <word>`",
                    f"`{p}uhset alias list`",
                    f"`{p}uhset alias remove <action> <word>`",
                    f"`{p}uhset alias undoadd <action> <word>`",
                ]
            ),
            inline=False,
        )
        extra.set_footer(text="Tab 4 • Extra")
        pages.append(extra)
        return pages

    async def _show_help_menu(self, ctx: commands.Context) -> None:
        staff = await self._is_staff(ctx)
        pages = await self._help_embeds(ctx, staff=staff)
        await self._send_pages(ctx, pages)

    async def _command_guide(self, ctx: commands.Context, *, staff: bool) -> str:
        # Kept for compatibility; the menu is the public help UI.
        pages = await self._help_embeds(ctx, staff=staff)
        return "\n".join(p.title or "" for p in pages)

    async def _post_fake_modlog(
        self,
        ctx: commands.Context,
        *,
        conf: dict,
        action: str,
        label: str,
        target: discord.Member,
        intended: discord.Member,
        reason: str,
        case: int,
        undo: bool,
        backfired: bool,
    ) -> None:
        if not conf.get("modlog_enabled"):
            return
        channel_id = conf.get("modlog_channel")
        if not channel_id or ctx.guild is None:
            return
        channel = ctx.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        me = ctx.guild.me
        if me is None:
            return
        perms = channel.permissions_for(me)
        if not perms.send_messages:
            return

        colors = {
            "ban": discord.Color.red(),
            "kick": discord.Color.orange(),
            "mute": discord.Color.dark_grey(),
            "timeout": discord.Color.gold(),
        }
        color = discord.Color.green() if undo else colors.get(action, discord.Color.red())
        verb = UNDO_PAST[action] if undo else PAST_TENSE[action]
        title = f"Case #{case} | {label}"
        embed = discord.Embed(title=title, color=color, timestamp=discord.utils.utcnow())
        embed.add_field(
            name="User",
            value=f"{target} (`{target.id}`)\n{target.mention}",
            inline=False,
        )
        embed.add_field(
            name="Moderator",
            value=f"{ctx.author} (`{ctx.author.id}`)",
            inline=False,
        )
        embed.add_field(name="Reason", value=(reason or DEFAULT_REASON)[:1000], inline=False)
        if backfired:
            embed.add_field(
                name="Note",
                value=(
                    f"Backfire: {ctx.author.mention} aimed at "
                    f"{intended.mention} (`{intended.id}`)."
                ),
                inline=False,
            )
        embed.set_footer(text=f"UsersHammer fake modlog • {verb} • no real action taken")
        mentions = discord.AllowedMentions.none()
        try:
            if perms.embed_links:
                await channel.send(embed=embed, allowed_mentions=mentions)
            else:
                text = (
                    f"**{title}**\n"
                    f"User: {target} (`{target.id}`)\n"
                    f"Moderator: {ctx.author} (`{ctx.author.id}`)\n"
                    f"Reason: {escape(reason, mass_mentions=True)}\n"
                    "UsersHammer fake modlog — no real action taken."
                )
                await channel.send(text, allowed_mentions=mentions)
        except discord.HTTPException:
            log.debug("Could not send fake modlog in guild %s", ctx.guild.id)

    async def _resolve_prefixed_invoke(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        if await self.bot.cog_disabled_in_guild(self, message.guild):
            return
        if not message.content:
            return

        prefixes = await self.bot.get_prefix(message)
        if isinstance(prefixes, str):
            prefixes = [prefixes]
        prefixes = sorted(prefixes, key=len, reverse=True)
        content = message.content
        used = None
        for prefix in prefixes:
            if content.startswith(prefix):
                used = prefix
                break
        if used is None:
            return
        rest = content[len(used) :].lstrip()
        if not rest:
            return
        parts = rest.split(maxsplit=2)
        word = parts[0]
        # Built-in commands already ran through the command parser. This
        # listener only handles extra per-server aliases.
        names = await self._command_names()
        undos = await self._undo_names()
        conf = await self._guild_conf(message.guild)
        if not conf.get("enabled", True):
            return
        # Skip the globally registered command words; those are real commands.
        global_words = set(names.values()) | set(undos.values())
        if self._clean_name(word) in global_words:
            return
        match = self._action_from_word(
            word, names, undos, conf.get("aliases") or {}, conf.get("undo_aliases") or {}
        )
        if match is None:
            return
        action, undo = match
        if len(parts) < 2:
            return
        ctx = await self.bot.get_context(message)
        if not isinstance(ctx.author, discord.Member):
            return
        try:
            target = await commands.MemberConverter().convert(ctx, parts[1])
        except commands.BadArgument:
            await ctx.send("I could not find that member.")
            return
        reason = parts[2] if len(parts) > 2 else None
        await self._do_action(ctx, action, target, reason, undo=undo)

    # ------------------------------------------------------------------
    # Member-facing joke commands (safe names, not core mod names)
    # ------------------------------------------------------------------

    @commands.guild_only()
    @commands.command()
    async def banish(
        self, ctx: commands.Context, member: discord.Member, *, reason: str = ""
    ):
        """Playfully mock-ban a member. Nobody is actually banned."""
        await self._do_action(ctx, "ban", member, reason)

    @commands.guild_only()
    @commands.command()
    async def remove(
        self, ctx: commands.Context, member: discord.Member, *, reason: str = ""
    ):
        """Playfully mock-kick a member. Nobody is actually kicked."""
        await self._do_action(ctx, "kick", member, reason)

    @commands.guild_only()
    @commands.command()
    async def silence(
        self, ctx: commands.Context, member: discord.Member, *, reason: str = ""
    ):
        """Playfully mock-mute a member. Nobody is actually muted."""
        await self._do_action(ctx, "mute", member, reason)

    @commands.guild_only()
    @commands.command()
    async def chatmute(
        self, ctx: commands.Context, member: discord.Member, *, reason: str = ""
    ):
        """Playfully mock-timeout a member. Nobody is actually timed out."""
        await self._do_action(ctx, "timeout", member, reason)

    @commands.guild_only()
    @commands.command()
    async def unbanish(
        self, ctx: commands.Context, member: discord.Member, *, reason: str = ""
    ):
        """Playfully lift a mock-ban. Nothing real is changed."""
        await self._do_action(ctx, "ban", member, reason, undo=True)

    @commands.guild_only()
    @commands.command()
    async def unremove(
        self, ctx: commands.Context, member: discord.Member, *, reason: str = ""
    ):
        """Playfully lift a mock-kick. Nothing real is changed."""
        await self._do_action(ctx, "kick", member, reason, undo=True)

    @commands.guild_only()
    @commands.command()
    async def unsilence(
        self, ctx: commands.Context, member: discord.Member, *, reason: str = ""
    ):
        """Playfully lift a mock-mute. Nothing real is changed."""
        await self._do_action(ctx, "mute", member, reason, undo=True)

    @commands.guild_only()
    @commands.command()
    async def unchatmute(
        self, ctx: commands.Context, member: discord.Member, *, reason: str = ""
    ):
        """Playfully lift a mock-timeout. Nothing real is changed."""
        await self._do_action(ctx, "timeout", member, reason, undo=True)

    # ------------------------------------------------------------------
    # Group that uses the real action words safely as *subcommands*
    # ------------------------------------------------------------------

    @commands.group(name="usershammer", aliases=["uh", "uhammer"])
    @commands.guild_only()
    async def usershammer(self, ctx: commands.Context):
        """Playful mock-moderation. These commands never punish anyone.

        Members see user commands. Staff also see setup commands.
        """
        if ctx.invoked_subcommand is None:
            await self._show_help_menu(ctx)

    @usershammer.command(name="cmds", aliases=["commands", "help"])
    async def uh_cmds(self, ctx: commands.Context):
        """Show the tabbed UsersHammer help menu."""
        await self._show_help_menu(ctx)

    @usershammer.command(name="ban")
    async def uh_ban(
        self, ctx: commands.Context, member: discord.Member, *, reason: str = ""
    ):
        """Joke ban. Does not ban the member."""
        await self._do_action(ctx, "ban", member, reason)

    @usershammer.command(name="kick")
    async def uh_kick(
        self, ctx: commands.Context, member: discord.Member, *, reason: str = ""
    ):
        """Joke kick. Does not kick the member."""
        await self._do_action(ctx, "kick", member, reason)

    @usershammer.command(name="mute")
    async def uh_mute(
        self, ctx: commands.Context, member: discord.Member, *, reason: str = ""
    ):
        """Joke mute. Does not mute the member."""
        await self._do_action(ctx, "mute", member, reason)

    @usershammer.command(name="timeout")
    async def uh_timeout(
        self, ctx: commands.Context, member: discord.Member, *, reason: str = ""
    ):
        """Joke timeout. Does not time the member out."""
        await self._do_action(ctx, "timeout", member, reason)

    @usershammer.command(name="unban")
    async def uh_unban(
        self, ctx: commands.Context, member: discord.Member, *, reason: str = ""
    ):
        """Joke unban. Does not unban the member."""
        await self._do_action(ctx, "ban", member, reason, undo=True)

    @usershammer.command(name="unkick")
    async def uh_unkick(
        self, ctx: commands.Context, member: discord.Member, *, reason: str = ""
    ):
        """Joke unkicked. Does not change membership."""
        await self._do_action(ctx, "kick", member, reason, undo=True)

    @usershammer.command(name="unmute")
    async def uh_unmute(
        self, ctx: commands.Context, member: discord.Member, *, reason: str = ""
    ):
        """Joke unmute. Does not unmute the member."""
        await self._do_action(ctx, "mute", member, reason, undo=True)

    @usershammer.command(name="untimeout")
    async def uh_untimeout(
        self, ctx: commands.Context, member: discord.Member, *, reason: str = ""
    ):
        """Joke end-timeout. Does not remove a real timeout."""
        await self._do_action(ctx, "timeout", member, reason, undo=True)

    @usershammer.command(name="actions")
    async def uh_actions(self, ctx: commands.Context):
        """Show the joke action words configured for this bot and server."""
        names = await self._command_names()
        undos = await self._undo_names()
        conf = await self._guild_conf(ctx.guild)
        lines = [
            "UsersHammer never applies real punishments.",
            "",
            "Built-in commands:",
        ]
        for action in ACTIONS:
            extra = conf.get("aliases", {}).get(action) or []
            extra_u = conf.get("undo_aliases", {}).get(action) or []
            extra_txt = f" + {humanize_list(extra)}" if extra else ""
            extra_u_txt = f" + {humanize_list(extra_u)}" if extra_u else ""
            lines.append(
                f"- {DEFAULT_LABELS[action]}: `{ctx.clean_prefix}{names[action]}` "
                f"or `{ctx.clean_prefix}uh {action}`{extra_txt}"
            )
            lines.append(
                f"  undo: `{ctx.clean_prefix}{undos[action]}` "
                f"or `{ctx.clean_prefix}uh un{action}`{extra_u_txt}"
            )
        body = "\n".join(lines)
        pages = await self._pagify_embed_pages(
            ctx, title="UsersHammer — Actions", body=body, footer="Paginated"
        )
        await self._send_pages(ctx, pages)

    # ------------------------------------------------------------------
    # Staff settings
    # ------------------------------------------------------------------

    @commands.group(name="uhset", aliases=["usershammerset"])
    @commands.guild_only()
    @checks.mod_or_permissions(manage_guild=True)
    async def uhset(self, ctx: commands.Context):
        """Configure UsersHammer for this server."""
        if ctx.invoked_subcommand is None:
            await self._show_help_menu(ctx)

    @uhset.command(name="settings")
    async def uhset_settings(self, ctx: commands.Context):
        """Show the current UsersHammer settings."""
        conf = await self._guild_conf(ctx.guild)
        names = await self._command_names()
        text = "\n".join(
            [
                f"Enabled: {conf['enabled']}",
                f"Random responses: {conf['random']}",
                f"Include built-in responses: {conf['include_defaults']}",
                f"Disclaimer footer: {conf['disclaimer']}",
                f"Disclaimer text: {conf.get('disclaimer_text') or DEFAULT_DISCLAIMER}",
                f"DM target: {conf.get('dm_target', True)}",
                f"Embeds: {conf['embeds']}",
                f"Respect hierarchy: {conf['respect_hierarchy']}",
                f"Allow self targets: {conf['allow_self']}",
                f"Allow bot targets: {conf['allow_bots']}",
                f"1-in-5 backfire: {conf.get('backfire', False)}",
                f"Fake modlog: {conf.get('modlog_enabled', False)}",
                f"Fake modlog channel: {conf.get('modlog_channel')}",
                f"Cooldown: {conf['cooldown']}s",
                f"Cases issued: {conf['case_count']}",
                f"Labels: {', '.join(f'{k}={v}' for k, v in (conf.get('labels') or DEFAULT_LABELS).items())}",
                f"Global command words: {', '.join(f'{k}→{v}' for k, v in names.items())}",
            ]
        )
        pages = await self._pagify_embed_pages(
            ctx,
            title="UsersHammer — Settings",
            body=box(text, lang="ini"),
            footer="Paginated settings",
            page_length=1000,
        )
        await self._send_pages(ctx, pages)

    @uhset.command(name="toggle")
    async def uhset_toggle(self, ctx: commands.Context, enabled: Optional[bool] = None):
        """Enable or disable UsersHammer in this server."""
        if enabled is None:
            enabled = not await self.config.guild(ctx.guild).enabled()
        await self.config.guild(ctx.guild).enabled.set(enabled)
        await ctx.send(f"UsersHammer is now {'enabled' if enabled else 'disabled'}.")

    @uhset.command(name="random")
    async def uhset_random(self, ctx: commands.Context, enabled: Optional[bool] = None):
        """Toggle random response picking.

        When off, the newest custom response is used if any exist,
        otherwise the first built-in line is used.
        """
        if enabled is None:
            enabled = not await self.config.guild(ctx.guild).random()
        await self.config.guild(ctx.guild).random.set(enabled)
        await ctx.send(
            "Responses will be picked at random."
            if enabled
            else "Responses will use a single chosen line instead of random."
        )

    @uhset.command(name="defaults")
    async def uhset_defaults(self, ctx: commands.Context, enabled: Optional[bool] = None):
        """Include built-in moderator-style lines in the random pool."""
        if enabled is None:
            enabled = not await self.config.guild(ctx.guild).include_defaults()
        await self.config.guild(ctx.guild).include_defaults.set(enabled)
        await ctx.send(
            "Built-in lines are included."
            if enabled
            else "Only staff-added lines will be used (built-ins remain as fallback if a pool is empty)."
        )

    @uhset.group(name="disclaimer")
    async def uhset_disclaimer(self, ctx: commands.Context):
        """Toggle or edit the footer shown on joke actions."""
        if ctx.invoked_subcommand is None:
            conf = await self._guild_conf(ctx.guild)
            lines = [
                f"Footer enabled: {conf.get('disclaimer', True)}",
                f"Default text: {self._disclaimer_text(conf, 'ban') if not (conf.get('disclaimers') or {}).get('ban') else conf.get('disclaimer_text') or DEFAULT_DISCLAIMER}",
            ]
            for action in ACTIONS:
                custom = (conf.get("disclaimers") or {}).get(action) or ""
                if custom:
                    lines.append(f"{action}: {custom}")
            pages = await self._pagify_embed_pages(
                ctx,
                title="UsersHammer — Disclaimer",
                body="\n".join(lines),
                footer="Disclaimer",
            )
            await self._send_pages(ctx, pages)

    @uhset_disclaimer.command(name="toggle")
    async def uhset_disclaimer_toggle(
        self, ctx: commands.Context, enabled: Optional[bool] = None
    ):
        """Show or hide the disclaimer footer."""
        if enabled is None:
            enabled = not await self.config.guild(ctx.guild).disclaimer()
        await self.config.guild(ctx.guild).disclaimer.set(enabled)
        await ctx.send(f"Disclaimer footer is now {'on' if enabled else 'off'}.")

    @uhset_disclaimer.command(name="text")
    async def uhset_disclaimer_text(
        self, ctx: commands.Context, action: Optional[str] = None, *, text: str = ""
    ):
        """Set disclaimer text globally or for one command.

        `[p]uhset disclaimer text This does not actually ban, kick, mute, or timeout users.`
        `[p]uhset disclaimer text ban This banish is fake.`
        """
        first = self._clean_name(action or "")
        if first in ACTIONS:
            body = text.strip()
            if not body:
                async with self.config.guild(ctx.guild).disclaimers() as items:
                    items[first] = ""
                await ctx.send(f"Custom {first} disclaimer cleared. The shared text will be used.")
                return
            if len(body) > 200:
                await ctx.send("Disclaimer must be 200 characters or fewer.")
                return
            async with self.config.guild(ctx.guild).disclaimers() as items:
                items[first] = body
            await ctx.send(f"Set the {first} disclaimer.")
            return
        body = " ".join(part for part in (action, text) if part).strip()
        if not body:
            await ctx.send("Provide the new disclaimer text.")
            return
        if len(body) > 200:
            await ctx.send("Disclaimer must be 200 characters or fewer.")
            return
        await self.config.guild(ctx.guild).disclaimer_text.set(body)
        await ctx.send("Updated the shared disclaimer text.")

    @uhset_disclaimer.command(name="reset")
    async def uhset_disclaimer_reset(
        self, ctx: commands.Context, action: Optional[str] = None
    ):
        """Reset disclaimer text to the built-in line."""
        if action:
            key = self._clean_name(action)
            if key not in ACTIONS:
                await ctx.send(f"Action must be one of: {humanize_list(list(ACTIONS))}.")
                return
            async with self.config.guild(ctx.guild).disclaimers() as items:
                items[key] = ""
            await ctx.send(f"Reset the {key} disclaimer override.")
            return
        await self.config.guild(ctx.guild).disclaimer_text.set(DEFAULT_DISCLAIMER)
        await self.config.guild(ctx.guild).disclaimers.set({a: "" for a in ACTIONS})
        await ctx.send("Reset all disclaimer text.")

    @uhset.command(name="text", aliases=["message"])
    async def uhset_text(self, ctx: commands.Context, action: str, *, text: str):
        """Set the joke line used for one command.

        Example:
        `[p]uhset text ban {target} caught the ban hammer. They are no longer welcome in {server}. Reason: {reason}`

        This replaces that action's custom lines. Turn random defaults
        off with `[p]uhset defaults` if you want only this line.
        """
        action = self._clean_name(action)
        if action not in ACTIONS:
            await ctx.send(f"Action must be one of: {humanize_list(list(ACTIONS))}.")
            return
        text = text.strip()
        if len(text) < 3 or len(text) > 1800:
            await ctx.send("Text must be between 3 and 1800 characters.")
            return
        async with self.config.guild(ctx.guild).responses() as responses:
            responses[action] = [text]
        await ctx.send(
            f"Set the {action} line. "
            f"Use `{ctx.clean_prefix}uhset defaults` if you do not want the built-in pool mixed in."
        )

    @uhset.command(name="dm")
    async def uhset_dm(self, ctx: commands.Context, enabled: Optional[bool] = None):
        """Toggle DMing the targeted user when a joke action is used."""
        if enabled is None:
            enabled = not await self.config.guild(ctx.guild).dm_target()
        await self.config.guild(ctx.guild).dm_target.set(enabled)
        await ctx.send(
            "UsersHammer will DM the targeted user."
            if enabled
            else "UsersHammer will not DM the targeted user."
        )

    @uhset.command(name="embeds")
    async def uhset_embeds(self, ctx: commands.Context, enabled: Optional[bool] = None):
        """Toggle embed formatting for joke actions."""
        if enabled is None:
            enabled = not await self.config.guild(ctx.guild).embeds()
        await self.config.guild(ctx.guild).embeds.set(enabled)
        await ctx.send(f"Embeds are now {'on' if enabled else 'off'}.")

    @uhset.command(name="hierarchy")
    async def uhset_hierarchy(self, ctx: commands.Context, enabled: Optional[bool] = None):
        """Toggle role hierarchy checks for joke actions."""
        if enabled is None:
            enabled = not await self.config.guild(ctx.guild).respect_hierarchy()
        await self.config.guild(ctx.guild).respect_hierarchy.set(enabled)
        await ctx.send(
            "Hierarchy is on. Members cannot joke-moderate equal or higher roles."
            if enabled
            else "Hierarchy is off. Anyone can joke-moderate anyone else."
        )

    @uhset.command(name="selftarget")
    async def uhset_selftarget(self, ctx: commands.Context, enabled: Optional[bool] = None):
        """Allow members to use joke actions on themselves."""
        if enabled is None:
            enabled = not await self.config.guild(ctx.guild).allow_self()
        await self.config.guild(ctx.guild).allow_self.set(enabled)
        await ctx.send(f"Self targets are now {'allowed' if enabled else 'blocked'}.")

    @uhset.command(name="bottarget")
    async def uhset_bottarget(self, ctx: commands.Context, enabled: Optional[bool] = None):
        """Allow members to use joke actions on bots."""
        if enabled is None:
            enabled = not await self.config.guild(ctx.guild).allow_bots()
        await self.config.guild(ctx.guild).allow_bots.set(enabled)
        await ctx.send(f"Bot targets are now {'allowed' if enabled else 'blocked'}.")

    @uhset.command(name="cooldown")
    async def uhset_cooldown(self, ctx: commands.Context, seconds: int):
        """Set the per-member cooldown in seconds. Use 0 to disable."""
        if seconds < 0 or seconds > 3600:
            await ctx.send("Cooldown must be between 0 and 3600 seconds.")
            return
        await self.config.guild(ctx.guild).cooldown.set(seconds)
        await ctx.send(f"Cooldown set to {seconds} second(s).")

    @uhset.command(name="backfire")
    async def uhset_backfire(self, ctx: commands.Context, enabled: Optional[bool] = None):
        """Toggle a 1-in-5 chance the joke hits the person who typed it.

        When on, each joke action has a 20% chance of targeting the
        command author instead of the named member.
        """
        if enabled is None:
            enabled = not await self.config.guild(ctx.guild).backfire()
        await self.config.guild(ctx.guild).backfire.set(enabled)
        await ctx.send(
            "Backfire is on. About 1 in 5 joke actions will hit the person who typed the command."
            if enabled
            else "Backfire is off."
        )

    @uhset.group(name="modlog")
    async def uhset_modlog(self, ctx: commands.Context):
        """Set up the fake modlog for joke actions.

        This never writes to Red's real modlog. Staff pick a channel,
        then joke banish/remove/silence/chatmute cases are posted there.
        """
        if ctx.invoked_subcommand is None:
            conf = await self._guild_conf(ctx.guild)
            channel_id = conf.get("modlog_channel")
            channel = ctx.guild.get_channel(channel_id) if channel_id else None
            where = channel.mention if isinstance(channel, discord.abc.GuildChannel) else "not set"
            await ctx.send(
                f"Fake modlog is {'on' if conf.get('modlog_enabled') else 'off'}. "
                f"Channel: {where}."
            )

    @uhset_modlog.command(name="channel")
    async def uhset_modlog_channel(
        self,
        ctx: commands.Context,
        channel: Optional[discord.TextChannel] = None,
    ):
        """Set or clear the fake modlog channel.

        Example: `[p]uhset modlog channel #joke-modlog`
        Omit the channel to clear it.
        """
        if channel is None:
            await self.config.guild(ctx.guild).modlog_channel.set(None)
            await self.config.guild(ctx.guild).modlog_enabled.set(False)
            await ctx.send("Fake modlog channel cleared and fake modlog turned off.")
            return
        me = ctx.guild.me
        if not channel.permissions_for(me).send_messages:
            await ctx.send("I cannot send messages in that channel.")
            return
        await self.config.guild(ctx.guild).modlog_channel.set(channel.id)
        await self.config.guild(ctx.guild).modlog_enabled.set(True)
        await ctx.send(
            f"Fake modlog will post in {channel.mention}. "
            "This is not Red's real modlog and applies no punishments."
        )

    @uhset_modlog.command(name="toggle")
    async def uhset_modlog_toggle(
        self, ctx: commands.Context, enabled: Optional[bool] = None
    ):
        """Enable or disable fake modlog posts."""
        if enabled is None:
            enabled = not await self.config.guild(ctx.guild).modlog_enabled()
        if enabled and not await self.config.guild(ctx.guild).modlog_channel():
            await ctx.send(
                f"Set a channel first with `{ctx.clean_prefix}uhset modlog channel #channel`."
            )
            return
        await self.config.guild(ctx.guild).modlog_enabled.set(enabled)
        await ctx.send(f"Fake modlog is now {'on' if enabled else 'off'}.")

    @uhset.command(name="label")
    async def uhset_label(self, ctx: commands.Context, action: str, *, label: str):
        """Change the display word for an action.

        Action must be one of: ban, kick, mute, timeout
        Example: `[p]uhset label ban Hammer`
        """
        action = self._clean_name(action)
        if action not in ACTIONS:
            await ctx.send(f"Action must be one of: {humanize_list(list(ACTIONS))}.")
            return
        label = label.strip()[:32]
        if not label:
            await ctx.send("Label cannot be empty.")
            return
        async with self.config.guild(ctx.guild).labels() as labels:
            labels[action] = label
        await ctx.send(f"The {action} action will now display as **{label}**.")

    @uhset.group(name="response", aliases=["responses"])
    async def uhset_response(self, ctx: commands.Context):
        """Add or remove joke moderator lines for an action."""
        if ctx.invoked_subcommand is None:
            await self._show_help_menu(ctx)

    @uhset_response.command(name="add")
    async def uhset_response_add(
        self, ctx: commands.Context, action: str, *, text: str
    ):
        """Add a response for an action.

        Action: ban, kick, mute, timeout
        Placeholders: `{target}` `{target.mention}` `{target.id}`
        `{moderator}` `{moderator.mention}` `{reason}` `{action}`
        `{action_past}` `{server}` `{case}`
        """
        action = self._clean_name(action)
        if action not in ACTIONS:
            await ctx.send(f"Action must be one of: {humanize_list(list(ACTIONS))}.")
            return
        text = text.strip()
        if len(text) < 3 or len(text) > 1800:
            await ctx.send("Response must be between 3 and 1800 characters.")
            return
        async with self.config.guild(ctx.guild).responses() as responses:
            responses.setdefault(action, []).append(text)
            index = len(responses[action])
        await ctx.send(f"Added {action} response #{index}.")

    @uhset_response.command(name="remove", aliases=["delete", "del"])
    async def uhset_response_remove(
        self, ctx: commands.Context, action: str, index: int
    ):
        """Remove a custom response by number from `[p]uhset response list`."""
        action = self._clean_name(action)
        if action not in ACTIONS:
            await ctx.send(f"Action must be one of: {humanize_list(list(ACTIONS))}.")
            return
        async with self.config.guild(ctx.guild).responses() as responses:
            pool = responses.get(action) or []
            if index < 1 or index > len(pool):
                await ctx.send("That index is not in the custom list.")
                return
            removed = pool.pop(index - 1)
            responses[action] = pool
        await ctx.send(f"Removed: {escape(removed, mass_mentions=True)[:200]}")

    @uhset_response.command(name="list")
    async def uhset_response_list(self, ctx: commands.Context, action: str):
        """List custom responses for an action."""
        action = self._clean_name(action)
        if action not in ACTIONS:
            await ctx.send(f"Action must be one of: {humanize_list(list(ACTIONS))}.")
            return
        pool = (await self.config.guild(ctx.guild).responses()).get(action) or []
        if not pool:
            await ctx.send(
                f"No custom {action} responses. Built-in lines will be used "
                f"unless you add some with `{ctx.clean_prefix}uhset response add`."
            )
            return
        body = "\n".join(f"{i}. {line}" for i, line in enumerate(pool, start=1))
        pages = await self._pagify_embed_pages(
            ctx,
            title=f"UsersHammer — {action} responses",
            body=body,
            footer="Use the index with response remove",
        )
        await self._send_pages(ctx, pages)

    @uhset_response.command(name="clear")
    async def uhset_response_clear(self, ctx: commands.Context, action: str):
        """Clear all custom responses for an action."""
        action = self._clean_name(action)
        if action not in ACTIONS:
            await ctx.send(f"Action must be one of: {humanize_list(list(ACTIONS))}.")
            return
        async with self.config.guild(ctx.guild).responses() as responses:
            responses[action] = []
        await ctx.send(f"Cleared custom {action} responses.")

    @uhset_response.command(name="undoadd")
    async def uhset_response_undoadd(
        self, ctx: commands.Context, action: str, *, text: str
    ):
        """Add an undo/lift response for an action."""
        action = self._clean_name(action)
        if action not in ACTIONS:
            await ctx.send(f"Action must be one of: {humanize_list(list(ACTIONS))}.")
            return
        text = text.strip()
        if len(text) < 3 or len(text) > 1800:
            await ctx.send("Response must be between 3 and 1800 characters.")
            return
        async with self.config.guild(ctx.guild).undo_responses() as responses:
            responses.setdefault(action, []).append(text)
            index = len(responses[action])
        await ctx.send(f"Added undo {action} response #{index}.")

    @uhset.group(name="alias")
    async def uhset_alias(self, ctx: commands.Context):
        """Add extra per-server command words for joke actions.

        These words work in this server only. They cannot be real
        moderation command names such as ban, kick, mute, or timeout.
        """
        if ctx.invoked_subcommand is None:
            await self._show_help_menu(ctx)

    @uhset_alias.command(name="add")
    async def uhset_alias_add(self, ctx: commands.Context, action: str, name: str):
        """Add a server alias. Example: `[p]uhset alias add ban hammer`"""
        action = self._clean_name(action)
        if action not in ACTIONS:
            await ctx.send(f"Action must be one of: {humanize_list(list(ACTIONS))}.")
            return
        err = self._validate_command_name(name)
        if err:
            await ctx.send(err)
            return
        name = self._clean_name(name)
        existing = self.bot.get_command(name)
        if existing is not None:
            await ctx.send(
                f"`{name}` is already a bot command (`{existing.qualified_name}`). "
                "Pick a different word."
            )
            return
        async with self.config.guild(ctx.guild).aliases() as aliases:
            aliases.setdefault(action, [])
            if name in aliases[action]:
                await ctx.send("That alias is already set.")
                return
            aliases[action].append(name)
        await ctx.send(
            f"Members can now use `{ctx.clean_prefix}{name} @user [reason]` "
            f"as a joke {action} in this server."
        )

    @uhset_alias.command(name="remove", aliases=["delete", "del"])
    async def uhset_alias_remove(self, ctx: commands.Context, action: str, name: str):
        """Remove a server alias."""
        action = self._clean_name(action)
        name = self._clean_name(name)
        if action not in ACTIONS:
            await ctx.send(f"Action must be one of: {humanize_list(list(ACTIONS))}.")
            return
        async with self.config.guild(ctx.guild).aliases() as aliases:
            pool = aliases.get(action) or []
            if name not in pool:
                await ctx.send("That alias is not set.")
                return
            pool.remove(name)
            aliases[action] = pool
        await ctx.send(f"Removed alias `{name}` from {action}.")

    @uhset_alias.command(name="list")
    async def uhset_alias_list(self, ctx: commands.Context):
        """List extra command words for this server."""
        aliases = await self.config.guild(ctx.guild).aliases()
        undo_aliases = await self.config.guild(ctx.guild).undo_aliases()
        names = await self._command_names()
        lines = []
        for action in ACTIONS:
            extra = aliases.get(action) or []
            extra_u = undo_aliases.get(action) or []
            lines.append(
                f"{action}: `{names[action]}`"
                + (f" + {humanize_list([f'`{a}`' for a in extra])}" if extra else "")
            )
            if extra_u:
                lines.append(
                    f"  undo extras: {humanize_list([f'`{a}`' for a in extra_u])}"
                )
        pages = await self._pagify_embed_pages(
            ctx,
            title="UsersHammer — Aliases",
            body="\n".join(lines),
            footer="Server aliases",
        )
        await self._send_pages(ctx, pages)

    @uhset_alias.command(name="undoadd")
    async def uhset_alias_undoadd(self, ctx: commands.Context, action: str, name: str):
        """Add a server alias that lifts a joke action."""
        action = self._clean_name(action)
        if action not in ACTIONS:
            await ctx.send(f"Action must be one of: {humanize_list(list(ACTIONS))}.")
            return
        err = self._validate_command_name(name)
        if err:
            await ctx.send(err)
            return
        name = self._clean_name(name)
        if self.bot.get_command(name) is not None:
            await ctx.send(f"`{name}` is already a bot command.")
            return
        async with self.config.guild(ctx.guild).undo_aliases() as aliases:
            aliases.setdefault(action, [])
            if name in aliases[action]:
                await ctx.send("That alias is already set.")
                return
            aliases[action].append(name)
        await ctx.send(f"Added undo alias `{name}` for {action}.")

    @uhset.command(name="name")
    @checks.is_owner()
    async def uhset_name(self, ctx: commands.Context, action: str, new_name: str):
        """Owner only: remember a preferred global word for an action.

        The built-in commands stay as banish, remove, silence, and
        chatmute so they never replace Red core commands. Use this plus
        a server alias (or Red's Alias cog) if you want a different word.

        This stores the preferred word shown in `[p]uh actions`.
        To actually invoke a custom word in a server, add it with
        `[p]uhset alias add`.
        """
        action = self._clean_name(action)
        if action not in ACTIONS:
            await ctx.send(f"Action must be one of: {humanize_list(list(ACTIONS))}.")
            return
        err = self._validate_command_name(new_name)
        if err:
            await ctx.send(err)
            return
        new_name = self._clean_name(new_name)
        async with self.config.command_names() as names:
            names[action] = new_name
        await ctx.send(
            f"Preferred public word for {action} is now `{new_name}`. "
            f"Add it in each server with `{ctx.clean_prefix}uhset alias add {action} {new_name}` "
            f"if it is not already one of the built-in commands."
        )

    @uhset.command(name="resetcases")
    async def uhset_resetcases(self, ctx: commands.Context):
        """Reset the joke case counter for this server."""
        await self.config.guild(ctx.guild).case_count.set(0)
        await ctx.send("Case counter reset to 0.")

    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message) -> None:
        try:
            await self._resolve_prefixed_invoke(message)
        except Exception:
            log.exception("Error handling UsersHammer alias invoke")
