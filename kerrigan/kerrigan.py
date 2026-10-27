import asyncio
import re
from datetime import timedelta
from typing import Optional

import discord
from redbot.core import Config, commands
from redbot.core.commands.converter import parse_timedelta
from redbot.core.utils.chat_formatting import humanize_timedelta

ACTION_KEYWORDS = {
    "nullvoid": "nullvoid",
    "null void": "nullvoid",
    "softban": "softban",
    "soft ban": "softban",
    "tempban": "tempban",
    "temp ban": "tempban",
    "tempmute": "tempmute",
    "temp mute": "tempmute",
    "tempmutechannel": "tempmutechannel",
    "temp mute channel": "tempmutechannel",
    "mutechannel": "mutechannel",
    "mute channel": "mutechannel",
    "userinfo": "userinfo",
    "user info": "userinfo",
    "void": "void",
    "ban": "ban",
    "kick": "kick",
    "mute": "mute",
    "warn": "warn",
}

DURATION_PATTERN = re.compile(
    r"\b(\d+\s*(?:weeks?|w|days?|d|hours?|hrs?|hr?|h|minutes?|mins?|m|seconds?|secs?|s))\b",
    re.IGNORECASE,
)


class Kerrigan(commands.Cog):
    """Casual staff moderation assistant.

    Staff can ping the bot with a casual sentence containing a moderation
    action and a user. The bot extracts the request and executes it through
    VoidSanction (and the Void cog for void/nullvoid actions).

    Requires VoidSanction to be loaded. Void is recommended for full void
    and nullvoid support.
    """

    def format_help_for_context(self, ctx: commands.Context) -> str:
        bot_name = ctx.bot.user.name if ctx.bot.user else "the bot"
        return (
            f"Casual staff moderation assistant for {bot_name}.\n\n"
            f"Staff can ping {bot_name} with a casual sentence containing a moderation "
            "action and a user. The bot extracts the request and executes it through "
            "VoidSanction (and the Void cog for void/nullvoid actions).\n\n"
            "Requires VoidSanction to be loaded. Void is recommended for full void "
            "and nullvoid support."
        )

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x4B4552524947414E, force_registration=True)
        self.config.register_guild(
            enabled=True,
            require_confirmation=True,
            soft_theme=False,
            cleanup_enabled=True,
            cleanup_delay=30,
            staff_role_ids=[],
            reason_timeout=60,
            confirm_timeout=30,
            # Flavor texts (placeholders: {bot}, {action}, {user}, {reason}, {duration})
            flavor_reason_prompt="What reason should I record?",
            flavor_reason_prompt_soft="Reason?",
            flavor_confirm_duration="Would you like me to **{action}** {user} for **{duration}** with reason: *{reason}*?",
            flavor_confirm_no_duration="Would you like me to **{action}** {user} with reason: *{reason}*?",
            flavor_confirm_soft="Confirm: {action} {user} — {reason}?",
            flavor_executing="Executing: {action} {user}",
            flavor_cancelled="Cancelled.",
            flavor_timeout="Timed out waiting for reason.",
        )
        self._cleanup_tasks = {}

    def cog_unload(self):
        for task in list(self._cleanup_tasks.values()):
            task.cancel()

    async def _is_staff(self, member: discord.Member) -> bool:
        if member.guild_permissions.manage_messages or member.guild_permissions.ban_members:
            return True
        staff_roles = await self.config.guild(member.guild).staff_role_ids()
        if staff_roles:
            return any(r.id in staff_roles for r in member.roles)
        # Fall back to Red's mod/admin roles
        mod_roles = await self.bot.get_mod_roles(member.guild)
        admin_roles = await self.bot.get_admin_roles(member.guild)
        return any(r in mod_roles or r in admin_roles for r in member.roles)

    def _parse_action(self, content: str) -> Optional[str]:
        content_lower = content.lower()
        # Prefer longer matches first
        for keyword in sorted(ACTION_KEYWORDS.keys(), key=len, reverse=True):
            if keyword in content_lower:
                return ACTION_KEYWORDS[keyword]
        return None

    def _parse_duration(self, content: str) -> Optional[str]:
        """Return the raw duration string (e.g. '2h', '1d') or None. VoidSanction expects a string."""
        matches = DURATION_PATTERN.findall(content)
        for match in matches:
            try:
                delta = parse_timedelta(match)
                if delta and delta.total_seconds() > 0:
                    return match.strip()
            except Exception:
                continue
        return None

    def _extract_target(self, message: discord.Message) -> Optional[discord.Member]:
        # Prefer non-bot mentions
        for mention in message.mentions:
            if mention != self.bot.user and isinstance(mention, discord.Member):
                return mention
        # Look for snowflake IDs
        ids = re.findall(r"\b(\d{17,20})\b", message.content)
        for uid in ids:
            member = message.guild.get_member(int(uid))
            if member and member != self.bot.user:
                return member
        return None

    def _strip_bot_mention(self, content: str) -> str:
        return re.sub(rf"<@!?{self.bot.user.id}>", "", content).strip()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if self.bot.user not in message.mentions:
            return

        settings = await self.config.guild(message.guild).all()
        if not settings["enabled"]:
            return

        if not await self._is_staff(message.author):
            return

        content = self._strip_bot_mention(message.content)
        if not content:
            return

        action_key = self._parse_action(content)
        if not action_key:
            return

        target = self._extract_target(message)
        if not target:
            return

        vs_cog = self.bot.get_cog("VoidSanction")
        if not vs_cog:
            await message.channel.send("VoidSanction cog is not loaded.", delete_after=10)
            return

        if action_key not in getattr(vs_cog, "actions", {}):
            return

        duration = self._parse_duration(content)

        # Collect messages for cleanup
        conversation = [message]

        # userinfo is informational — skip reason and confirmation, execute immediately
        if action_key == "userinfo":
            try:
                ctx = await self.bot.get_context(message)
                action = vs_cog.actions[action_key]
                await vs_cog.call_sanction(
                    ctx,
                    action=action,
                    member=target,
                    duration=None,
                    reason="User info request",
                    confirmation=False,
                    finish_message=False,
                )
            except Exception as e:
                await message.channel.send(f"Failed to get user info: {e}", delete_after=10)
            if settings["cleanup_enabled"]:
                self._schedule_cleanup(message.channel, conversation, settings["cleanup_delay"])
            return

        # Prefer everything after the first "for" as the reason
        reason = None
        # Work on a cleaned version of the content for extraction
        clean = re.sub(r"<@!?\d+>", "", content)  # strip all mentions
        clean = re.sub(r"\b\d{17,20}\b", "", clean)
        for_match = re.search(r"\bfor\b", clean, re.IGNORECASE)
        if for_match:
            after_for = clean[for_match.end():].strip()
            after_for = re.sub(DURATION_PATTERN, "", after_for)
            after_for = " ".join(after_for.split()).strip()
            if after_for:
                reason = after_for

        if not reason:
            # No usable reason after "for" — ask for one
            if settings["soft_theme"]:
                prompt = settings.get("flavor_reason_prompt_soft") or "Reason?"
            else:
                prompt = settings.get("flavor_reason_prompt") or "What reason should I record?"
            bot_msg = await message.channel.send(prompt)
            conversation.append(bot_msg)

            def check(m):
                return m.author == message.author and m.channel == message.channel and not m.author.bot

            try:
                reason_msg = await self.bot.wait_for(
                    "message", check=check, timeout=settings["reason_timeout"]
                )
                conversation.append(reason_msg)
                reason = reason_msg.content.strip() or "No reason given."
                # If no duration was found yet, check the reason reply for one
                if not duration:
                    duration = self._parse_duration(reason_msg.content)
                    if duration:
                        # Strip the duration out of the reason text
                        reason = re.sub(DURATION_PATTERN, "", reason).strip() or "No reason given."
            except asyncio.TimeoutError:
                msg = settings.get("flavor_timeout") or "Timed out waiting for reason."
                await message.channel.send(msg, delete_after=5)
                return

        # Build confirmation text — only mention duration if one was actually given
        duration_str = ""
        if duration:
            try:
                parsed = parse_timedelta(duration)
                duration_str = humanize_timedelta(timedelta=parsed) if parsed else duration
            except Exception:
                duration_str = duration

        fmt = {
            "bot": self.bot.user.name,
            "action": action_key,
            "user": target.mention,
            "reason": reason or "No reason given.",
            "duration": duration_str,
        }
        if settings["soft_theme"]:
            confirm_text = (settings.get("flavor_confirm_soft") or "Confirm: {action} {user} — {reason}?").format(**fmt)
        elif duration:
            confirm_text = (settings.get("flavor_confirm_duration") or "Would you like me to **{action}** {user} for **{duration}** with reason: *{reason}*?").format(**fmt)
        else:
            confirm_text = (settings.get("flavor_confirm_no_duration") or "Would you like me to **{action}** {user} with reason: *{reason}*?").format(**fmt)

        if settings["require_confirmation"]:
            bot_msg = await message.channel.send(confirm_text)
            conversation.append(bot_msg)

            def yes_no_check(m):
                return (
                    m.author == message.author
                    and m.channel == message.channel
                    and m.content.lower().strip() in ("yes", "y", "no", "n")
                )

            try:
                reply = await self.bot.wait_for(
                    "message", check=yes_no_check, timeout=settings["confirm_timeout"]
                )
                conversation.append(reply)
                if reply.content.lower().strip() not in ("yes", "y"):
                    msg = settings.get("flavor_cancelled") or "Cancelled."
                    await message.channel.send(msg, delete_after=5)
                    if settings["cleanup_enabled"]:
                        self._schedule_cleanup(message.channel, conversation, settings["cleanup_delay"])
                    return
            except asyncio.TimeoutError:
                await message.channel.send("Confirmation timed out.", delete_after=5)
                if settings["cleanup_enabled"]:
                    self._schedule_cleanup(message.channel, conversation, settings["cleanup_delay"])
                return
        else:
            # Auto proceed, still send a brief note
            note = (settings.get("flavor_executing") or "Executing: {action} {user}").format(
                action=action_key, user=target.display_name, bot=self.bot.user.name
            )
            if settings["soft_theme"]:
                note = f"Proceeding with {action_key}."
            bot_msg = await message.channel.send(note)
            conversation.append(bot_msg)

        # Execute
        try:
            ctx = await self.bot.get_context(message)
            action = vs_cog.actions[action_key]
            # VoidSanction expects duration as a string (or None) and reason as a string
            safe_reason = reason if isinstance(reason, str) and reason.strip() else "No reason given."
            await vs_cog.call_sanction(
                ctx,
                action=action,
                member=target,
                duration=duration,  # already a string or None
                reason=safe_reason,
                confirmation=False,
                finish_message=False,
            )
        except Exception as e:
            await message.channel.send(f"Failed to execute action: {e}", delete_after=10)

        if settings["cleanup_enabled"]:
            self._schedule_cleanup(message.channel, conversation, settings["cleanup_delay"])

    def _schedule_cleanup(self, channel: discord.TextChannel, messages: list, delay: int):
        async def _cleanup():
            await asyncio.sleep(delay)
            for msg in messages:
                try:
                    if msg and not msg.deleted:
                        await msg.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass

        task = asyncio.create_task(_cleanup())
        self._cleanup_tasks[id(task)] = task

        def _done(t):
            self._cleanup_tasks.pop(id(t), None)

        task.add_done_callback(_done)

    @commands.group(name="kerriganset", aliases=["kset"])
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def kerriganset(self, ctx: commands.Context):
        """Configure the casual moderation assistant for this server."""
        if ctx.invoked_subcommand is None:
            settings = await self.config.guild(ctx.guild).all()
            embed = discord.Embed(
                title=f"{ctx.bot.user.name} Settings", color=await ctx.embed_color()
            )
            embed.add_field(name="Enabled", value=str(settings["enabled"]))
            embed.add_field(name="Require Confirmation", value=str(settings["require_confirmation"]))
            embed.add_field(name="Soft Theme", value=str(settings["soft_theme"]))
            embed.add_field(name="Cleanup Enabled", value=str(settings["cleanup_enabled"]))
            embed.add_field(name="Cleanup Delay", value=f"{settings['cleanup_delay']}s")
            embed.add_field(name="Staff Roles", value=str(len(settings["staff_role_ids"])) + " set")
            await ctx.send(embed=embed)

    @kerriganset.command(name="toggle")
    async def set_toggle(self, ctx: commands.Context, enabled: bool = None):
        """Toggle the cog on or off for this server."""
        if enabled is None:
            enabled = not await self.config.guild(ctx.guild).enabled()
        await self.config.guild(ctx.guild).enabled.set(enabled)
        await ctx.send(f"{ctx.bot.user.name} is now {'enabled' if enabled else 'disabled'}.")

    @kerriganset.command(name="confirm")
    async def set_confirm(self, ctx: commands.Context, require: bool = None):
        """Toggle whether a yes/no confirmation is required before acting."""
        if require is None:
            require = not await self.config.guild(ctx.guild).require_confirmation()
        await self.config.guild(ctx.guild).require_confirmation.set(require)
        await ctx.send(f"Confirmation required: {require}")

    @kerriganset.command(name="theme")
    async def set_theme(self, ctx: commands.Context, soft: bool = None):
        """Toggle a soft amount of theming in responses."""
        if soft is None:
            soft = not await self.config.guild(ctx.guild).soft_theme()
        await self.config.guild(ctx.guild).soft_theme.set(soft)
        await ctx.send(f"Soft theme: {soft}")

    @kerriganset.command(name="cleanup")
    async def set_cleanup(self, ctx: commands.Context, enabled: bool = None, delay: int = None):
        """Toggle cleanup and optionally set the delay in seconds."""
        guild_conf = self.config.guild(ctx.guild)
        if enabled is None:
            enabled = not await guild_conf.cleanup_enabled()
        await guild_conf.cleanup_enabled.set(enabled)
        if delay is not None and delay >= 0:
            await guild_conf.cleanup_delay.set(delay)
        current_delay = await guild_conf.cleanup_delay()
        await ctx.send(
            f"Cleanup {'enabled' if enabled else 'disabled'}. Delay: {current_delay}s"
        )

    @kerriganset.command(name="staffrole")
    async def set_staffrole(self, ctx: commands.Context, role: discord.Role = None):
        """Add or remove a staff role (or show current)."""
        async with self.config.guild(ctx.guild).staff_role_ids() as roles:
            if role is None:
                if not roles:
                    await ctx.send("No custom staff roles set. Using mod/admin or manage_messages.")
                    return
                mentions = [ctx.guild.get_role(r).mention for r in roles if ctx.guild.get_role(r)]
                await ctx.send("Staff roles: " + ", ".join(mentions))
                return
            if role.id in roles:
                roles.remove(role.id)
                await ctx.send(f"Removed {role.mention} from staff roles.")
            else:
                roles.append(role.id)
                await ctx.send(f"Added {role.mention} as a staff role.")

    @kerriganset.command(name="flavor")
    async def set_flavor(self, ctx: commands.Context, key: str = None, *, text: str = None):
        """View or edit flavor text.

        Available keys:
        reason_prompt, reason_prompt_soft,
        confirm_duration, confirm_no_duration, confirm_soft,
        executing, cancelled, timeout

        Placeholders: {bot} {action} {user} {reason} {duration}

        Examples:
        [p]kerriganset flavor
        [p]kerriganset flavor reason_prompt What is the reason?
        [p]kerriganset flavor confirm_duration Confirm {action} on {user} for {duration}?
        """
        flavor_keys = {
            "reason_prompt": "flavor_reason_prompt",
            "reason_prompt_soft": "flavor_reason_prompt_soft",
            "confirm_duration": "flavor_confirm_duration",
            "confirm_no_duration": "flavor_confirm_no_duration",
            "confirm_soft": "flavor_confirm_soft",
            "executing": "flavor_executing",
            "cancelled": "flavor_cancelled",
            "timeout": "flavor_timeout",
        }

        if key is None:
            settings = await self.config.guild(ctx.guild).all()
            lines = ["**Current flavor texts**\n"]
            for short, full in flavor_keys.items():
                val = settings.get(full, "")
                lines.append(f"`{short}`: {val}")
            lines.append("\nUse `[p]kerriganset flavor <key> <text>` to change one.")
            await ctx.send("\n".join(lines))
            return

        key = key.lower()
        if key not in flavor_keys:
            await ctx.send(f"Unknown key. Available: {', '.join(flavor_keys)}")
            return

        if text is None:
            await ctx.send("Please provide the new text.")
            return

        await getattr(self.config.guild(ctx.guild), flavor_keys[key]).set(text)
        await ctx.send(f"Updated `{key}` to: {text}")

    @kerriganset.command(name="example")
    async def set_example(self, ctx: commands.Context):
        """Show usage examples and requirements."""
        bot_name = self.bot.user.name
        vs_loaded = self.bot.get_cog("VoidSanction") is not None
        void_loaded = self.bot.get_cog("Void") is not None
        vs_status = "loaded" if vs_loaded else "**not loaded**"
        void_status = "loaded" if void_loaded else "not loaded (recommended)"
        text = (
            f"**{bot_name} requires the VoidSanction cog to be installed and loaded.**\n"
            f"Void cog is recommended for void and nullvoid actions.\n\n"
            f"Current status:\n"
            f"- VoidSanction: {vs_status}\n"
            f"- Void: {void_status}\n\n"
            "**How it works**\n"
            f"Staff ping {bot_name} with a casual sentence containing an action and a user.\n"
            "If the message contains `for`, everything after it is used as the reason.\n"
            "Otherwise the bot asks for a reason. Duration is optional.\n\n"
            "**Examples**\n"
            f"`@{bot_name} kick @user for being inactive`\n"
            f"`@{bot_name} mute @user 2h for spamming`\n"
            f"`@{bot_name} void 123456789012345678`\n"
            f"`@{bot_name} nullvoid @user for repeated violations`\n"
            f"`@{bot_name} could you give me the userinfo of @user`\n\n"
            "**Supported actions**\n"
            "ban, kick, mute, void, nullvoid, softban, tempban, tempmute, "
            "mutechannel, tempmutechannel, warn, userinfo"
        )
        await ctx.send(text)
