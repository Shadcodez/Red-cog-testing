"""YouTube ?si= sanitizer for Red-DiscordBot.

Auto mode listens and retriggers. Manual mode is command-only.
Deleting the original post is a separate guild toggle.
"""

from __future__ import annotations

import logging
import re
from typing import Literal, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n

log = logging.getLogger("red.ytsanitizer")
_ = Translator("YTSanitizer", __file__)

RequestType = Literal["discord_deleted_user", "owner", "user", "user_strict"]

_YOUTUBE_HOSTS = {
    "youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
}
_URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
# si is the share identifier. feature=share is the same kind of baggage.
_DROP_PARAMS = {"si", "feature"}
_MODES = ("auto", "manual", "off")
_TRUE = {"on", "yes", "true", "enable", "enabled", "1"}
_FALSE = {"off", "no", "false", "disable", "disabled", "0"}


def _host(netloc: str) -> str:
    host = netloc.lower().split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def is_youtube(url: str) -> bool:
    host = _host(urlparse(url).netloc)
    return host in _YOUTUBE_HOSTS or host.endswith(".youtube.com")


def _peel_trailing(url: str) -> Tuple[str, str]:
    trimmed = url.rstrip(").,;!?'\"")
    return trimmed, url[len(trimmed) :]


def strip_si(url: str) -> str:
    """Drop YouTube ``si`` / ``feature`` params. Other URLs pass through.

    ``v``, ``t``, ``list``, and ``index`` are kept.
    """
    trimmed, suffix = _peel_trailing(url)
    parsed = urlparse(trimmed)
    if not is_youtube(trimmed):
        return url
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if not any(key.lower() in _DROP_PARAMS for key, _ in pairs):
        return url
    kept = [(key, value) for key, value in pairs if key.lower() not in _DROP_PARAMS]
    cleaned = urlunparse(parsed._replace(query=urlencode(kept)))
    return cleaned + suffix


def sanitize_youtube_urls(text: str) -> Tuple[str, bool]:
    """Replace YouTube URLs in ``text``. Returns ``(new_text, changed)``.

    Angle brackets around a cleaned YouTube URL are removed so Discord embeds it.
    """
    changed = False

    def _sub(match: re.Match) -> str:
        nonlocal changed
        original = match.group(0)
        cleaned = strip_si(original)
        if cleaned != original:
            changed = True
        return cleaned

    new_text = _URL_RE.sub(_sub, text)
    if not changed:
        return text, False
    unwrapped = re.sub(
        r"<\s*(https?://[^\s>]+)\s*>",
        lambda match: match.group(1) if is_youtube(match.group(1)) else match.group(0),
        new_text,
        flags=re.IGNORECASE,
    )
    return unwrapped, True


def _parse_bool(value: str) -> Optional[bool]:
    lowered = value.lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    return None


@cog_i18n(_)
class YTSanitizer(commands.Cog):
    """Strip YouTube ?si= share ids and retrigger the embed.

    Auto mode cleans new posts. Manual mode only runs from the command.
    Deleting the original post is a separate toggle and starts off.
    """

    __author__ = "YTSanitizer"
    __version__ = "1.1.0"

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x51C1EA4E, force_registration=True)
        self.config.register_guild(mode="manual", delete_original=False)

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre = super().format_help_for_context(ctx)
        return f"{pre}\n\n" + _("Version: {version}").format(version=self.__version__)

    async def red_delete_data_for_user(self, *, requester: RequestType, user_id: int) -> None:
        """No end-user data is stored. Guild settings are not user data."""

    @staticmethod
    def sanitize(text: str) -> Tuple[str, bool]:
        """Cleaner. Strips ``?si=`` / ``&si=`` from YouTube URLs in a message body."""
        return sanitize_youtube_urls(text)

    async def cleanup_original(self, message: discord.Message) -> bool:
        """Delete the original post. Returns True if Discord removed it."""
        if message.guild is None:
            return False
        me = message.guild.me
        channel = message.channel
        if me is None or not channel.permissions_for(me).manage_messages:
            log.debug("Missing Manage Messages in #%s; left the original post.", channel.id)
            return False
        try:
            await message.delete()
        except discord.HTTPException:
            log.debug("Failed to delete message %s.", message.id, exc_info=True)
            return False
        return True

    async def retrigger(
        self,
        message: discord.Message,
        cleaned: str,
        *,
        reply: bool,
    ) -> Optional[discord.Message]:
        """Repost the cleaned body so Discord builds a fresh embed."""
        author = message.author
        content = _("**{name}:** {body}").format(
            name=discord.utils.escape_markdown(author.display_name),
            body=cleaned,
        )
        if len(content) > 2000:
            content = content[:1997] + "..."
        kwargs = {
            "allowed_mentions": discord.AllowedMentions.none(),
        }
        try:
            if reply:
                return await message.reply(content, mention_author=False, **kwargs)
            return await message.channel.send(content, **kwargs)
        except discord.HTTPException:
            log.debug("Failed to retrigger message %s.", message.id, exc_info=True)
            return None

    async def _apply(
        self,
        message: discord.Message,
        cleaned: str,
        *,
        delete_original: bool,
    ) -> Tuple[bool, Optional[discord.Message]]:
        """Delete first when asked, then retrigger. Reply only if the original stays."""
        deleted = False
        if delete_original:
            deleted = await self.cleanup_original(message)
        sent = await self.retrigger(message, cleaned, reply=not deleted)
        return deleted, sent

    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot or not message.content:
            return
        if await self.bot.cog_disabled_in_guild(self, message.guild):
            return
        if await self.config.guild(message.guild).mode() != "auto":
            return

        cleaned, changed = self.sanitize(message.content)
        if not changed:
            return

        me = message.guild.me
        if me is None or not message.channel.permissions_for(me).send_messages:
            return

        delete_original = await self.config.guild(message.guild).delete_original()
        await self._apply(message, cleaned, delete_original=delete_original)

    @commands.command(name="ytsanitize")
    @commands.guild_only()
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def ytsanitize(self, ctx: commands.Context, *, text: str = None) -> None:
        """Clean a YouTube link, or reply to a post to clean that post.

        Manual mode uses this command only. Auto mode also listens.
        The original post is deleted only when the delete toggle is on,
        and only when you replied to a message you wrote or can moderate.
        """
        target = await self._replied_message(ctx)
        source = target.content if target is not None else text
        if not source:
            await ctx.send_help()
            return

        cleaned, changed = self.sanitize(source)
        if not changed:
            await ctx.send(_("No YouTube `?si=` parameter found."))
            return

        if target is None:
            await ctx.send(cleaned, allowed_mentions=discord.AllowedMentions.none())
            return

        delete_original = await self.config.guild(ctx.guild).delete_original()
        if delete_original and not self._may_delete(ctx, target):
            delete_original = False
            await ctx.send(
                _(
                    "Delete is on, but you can only remove your own post "
                    "unless you have Manage Messages. Posting the clean link anyway."
                )
            )

        deleted, sent = await self._apply(target, cleaned, delete_original=delete_original)
        if sent is None:
            await ctx.send(_("I couldn't post the cleaned link."))
            return
        if delete_original and not deleted:
            await ctx.send(
                _("Clean link posted. I couldn't delete the original (need Manage Messages).")
            )

    @commands.group(name="ytsanitizeset")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def ytsanitizeset(self, ctx: commands.Context) -> None:
        """Configure auto mode, manual mode, and original-post deletion."""
        if ctx.invoked_subcommand is None:
            await self._send_settings(ctx)

    @ytsanitizeset.command(name="mode")
    async def ytsanitizeset_mode(self, ctx: commands.Context, mode: str) -> None:
        """Set the mode: auto, manual, or off.

        auto — clean new posts as they arrive
        manual — command only (default)
        off — do nothing until turned back on
        """
        mode = mode.lower()
        if mode not in _MODES:
            await ctx.send(_("Mode must be `auto`, `manual`, or `off`."))
            return
        await self.config.guild(ctx.guild).mode.set(mode)
        await ctx.send(_("Mode set to **{mode}**.").format(mode=mode))

    @ytsanitizeset.command(name="delete")
    async def ytsanitizeset_delete(self, ctx: commands.Context, enabled: str = None) -> None:
        """Toggle deleting the original post, or set it on/off.

        Off by default. Needs Manage Messages on the bot when on.
        """
        current = await self.config.guild(ctx.guild).delete_original()
        if enabled is None:
            new_value = not current
        else:
            parsed = _parse_bool(enabled)
            if parsed is None:
                await ctx.send(_("Use `on` or `off`, or run it with no argument to toggle."))
                return
            new_value = parsed
        await self.config.guild(ctx.guild).delete_original.set(new_value)
        state = _("on") if new_value else _("off")
        await ctx.send(_("Delete original post is now **{state}**.").format(state=state))

    @ytsanitizeset.command(name="show")
    async def ytsanitizeset_show(self, ctx: commands.Context) -> None:
        """Show this server's mode and delete toggle."""
        await self._send_settings(ctx)

    async def _send_settings(self, ctx: commands.Context) -> None:
        mode = await self.config.guild(ctx.guild).mode()
        delete_original = await self.config.guild(ctx.guild).delete_original()
        embed = discord.Embed(
            title=_("YouTube sanitizer"),
            colour=await ctx.embed_colour(),
        )
        embed.add_field(name=_("Mode"), value=mode, inline=True)
        embed.add_field(
            name=_("Delete original"),
            value=_("on") if delete_original else _("off"),
            inline=True,
        )
        embed.add_field(
            name=_("Manual"),
            value=_("`{prefix}ytsanitize` on a link, or reply to a post.").format(
                prefix=ctx.clean_prefix
            ),
            inline=False,
        )
        if delete_original:
            me = ctx.guild.me if ctx.guild else None
            missing = me is None or not ctx.channel.permissions_for(me).manage_messages
            if missing:
                embed.set_footer(
                    text=_("Delete is on, but I don't have Manage Messages in this channel.")
                )
        await ctx.send(embed=embed)

    @staticmethod
    async def _replied_message(ctx: commands.Context) -> Optional[discord.Message]:
        reference = ctx.message.reference
        if reference is None:
            return None
        resolved = reference.resolved
        if isinstance(resolved, discord.Message):
            return resolved
        if reference.message_id is None:
            return None
        try:
            return await ctx.channel.fetch_message(reference.message_id)
        except discord.HTTPException:
            return None

    @staticmethod
    def _may_delete(ctx: commands.Context, target: discord.Message) -> bool:
        if target.author.id == ctx.author.id:
            return True
        return ctx.channel.permissions_for(ctx.author).manage_messages
