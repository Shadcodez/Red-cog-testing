from __future__ import annotations

import typing
from dataclasses import dataclass

import discord
from AAA3A_utils import CogsUtils
from redbot.core import commands
from redbot.core.commands.converter import parse_timedelta
from redbot.core.i18n import Translator
from redbot.core.utils.predicates import MessagePredicate

from .constants import DELETE_MESSAGE_DAYS_LIMIT, GIF_CLEANUP_SECONDS, MENU_TIMEOUT_SECONDS
from .purge import clamp_delete_days, purge_member_messages
from .views import DeleteDaysView

_: Translator = Translator("VoidSanction", __file__)


VOID_COG_NAMES = ("Void", "void", "NullVoid", "nullvoid", "VoidCog", "VoidTools")


@dataclass(frozen=True)
class Action:
    key: str
    cog: commands.Cog

    label: str
    emoji: str

    cog_required: str | None
    command: str
    warn_system_command: str | None

    duration_ask_message: str | None
    reason_ask_message: str | None
    confirmation_ask_message: str | None
    finish_message: str | None

    ask_delete_days: bool = False
    void_command: bool = False
    purge_before: bool = False
    fallback_command: str | None = None
    skip_gif: bool = False
    use_native: bool = False

    def to_json(self) -> dict[str, typing.Any]:
        return {
            v: getattr(self, v)
            for v in dir(self)
            if not v.startswith("_") and v not in ("to_json", "process", "send_action_gif")
        }

    def _format_template(self, template: str, **kwargs: typing.Any) -> str:
        return template.format(**kwargs)

    @staticmethod
    def _is_skip(value: str | None) -> bool:
        if value is None:
            return False
        return value.strip().lower() in {"skip", "not", "none", "default", ""}

    async def _wants_delete_days(self, ctx: commands.Context) -> bool:
        """Per-action toggle: kick/ban use the master switch; mute/softban have their own."""
        conf = self.cog.config.guild(ctx.guild)
        if self.key == "softban":
            return bool(await conf.ask_delete_days_softban())
        if self.key in {"mute", "mutechannel", "tempmute", "tempmutechannel"}:
            return bool(await conf.ask_delete_days_mute())
        if self.ask_delete_days:
            return bool(await conf.ask_delete_days())
        return False

    async def _ask_delete_days(
        self,
        ctx: commands.Context,
        interaction: discord.Interaction | None,
        member: discord.Member,
    ) -> int | None:
        """
        Ask how many days of messages to clean. Returns None if cancelled/timed out.
        """
        if not await self._wants_delete_days(ctx):
            return clamp_delete_days(await self.cog.config.guild(ctx.guild).default_delete_days()) if self.ask_delete_days else 0

        view = DeleteDaysView(author_id=ctx.author.id, member=member)
        content = _(
            "Clean messages from {member.mention}?\n"
            "Choose how many days worth to delete (0–{limit}). Discord's ban API max is {limit} days.",
        ).format(member=member, limit=DELETE_MESSAGE_DAYS_LIMIT)

        if interaction is not None and not interaction.response.is_done():
            await interaction.response.send_message(content, view=view)
            view._message = await interaction.original_response()
        else:
            view._message = await ctx.send(content, view=view)

        timed_out = await view.wait()
        if timed_out or view.cancelled or view.days is None:
            await ctx.send(_("Message cleanup prompt cancelled or timed out."), delete_after=10)
            return None
        return clamp_delete_days(view.days)

    async def _ask_text(
        self,
        ctx: commands.Context,
        prompt: str,
    ) -> str | None:
        message = await ctx.send(prompt)
        try:
            pred = MessagePredicate.same_context(ctx)
            msg = await ctx.bot.wait_for("message", timeout=MENU_TIMEOUT_SECONDS, check=pred)
            await CogsUtils.delete_message(message)
            await CogsUtils.delete_message(msg)
            if msg.content.lower() == "cancel":
                return None
            return msg.content
        except TimeoutError:
            await CogsUtils.delete_message(message)
            await ctx.send(_("Timed out, please try again."), delete_after=10)
            return None

    def _void_cog_loaded(self, bot: commands.Bot) -> bool:
        return any(bot.get_cog(name) is not None for name in VOID_COG_NAMES) or any(
            bot.get_command(name) is not None for name in ("void", "nullvoid")
        )

    async def _invoke(self, ctx: commands.Context, command_string: str) -> bool:
        context = await CogsUtils.invoke_command(
            bot=ctx.bot,
            author=ctx.author,
            channel=ctx.channel,
            command=command_string,
            prefix=ctx.prefix,
            message=ctx.message,
        )
        if not context.valid:
            return False
        if not await discord.utils.async_all([check(context) for check in context.command.checks]):
            raise commands.UserFeedbackCheckFailure(
                _("You can't execute this command, in this context."),
            )
        return True

    async def process(
        self,
        ctx: commands.Context,
        interaction: discord.Interaction | None,
        member: discord.Member,
        duration: str | None = None,
        reason: str | None = "The reason was not given.",
        finish_message_enabled: bool | None = True,
        reason_required: bool | None = True,
        confirmation: bool | None = False,
        show_author: bool | None = True,
        fake_action: bool | None = False,
    ) -> bool | None:
        if (
            (await self.cog.config.guild(ctx.guild).use_warn_system())
            and self.warn_system_command is not None
            and ctx.bot.get_cog("WarnSystem") is not None
        ):
            use_warn_system = True
        else:
            use_warn_system = False
            if self.cog_required is not None and not ctx.bot.get_cog(self.cog_required):
                if interaction is not None and not interaction.response.is_done():
                    await interaction.response.defer()
                await ctx.send(
                    _(
                        "The cog `{cog_required}` is not loaded. Please load it with `{prefix}load {cog_required_lowered}`.",
                    ).format(
                        prefix=ctx.prefix,
                        cog_required=self.cog_required,
                        cog_required_lowered=self.cog_required.lower(),
                    ),
                )
                return False
            if self.void_command and not self._void_cog_loaded(ctx.bot):
                if interaction is not None and not interaction.response.is_done():
                    await interaction.response.defer()
                await ctx.send(
                    _(
                        "Your Void cog does not appear to be loaded, and I cannot find the `{command}` command.\n"
                        "Load the Void cog first, then try again.",
                    ).format(command=self.key),
                )
                return False

        extra_params_inputs: dict[str, discord.ui.TextInput] = {}
        used_modal = False
        if interaction is not None and not interaction.response.is_done():
            if duration is None and self.duration_ask_message is not None:
                extra_params_inputs["duration"] = discord.ui.TextInput(
                    label="Duration",
                    style=discord.TextStyle.short,
                    required=self.key not in {"void"},
                    placeholder=_("3d, 12h, or skip for Void default."),
                )
            if reason is None and self.reason_ask_message is not None:
                extra_params_inputs["reason"] = discord.ui.TextInput(
                    label="Reason",
                    style=discord.TextStyle.paragraph,
                    required=False,
                    placeholder=_("The reason was not given."),
                )
            if extra_params_inputs:
                modal = discord.ui.Modal(
                    title=f"{self.emoji} {self.label}"[:45],
                    custom_id="VoidSanction",
                )
                modal.on_submit = lambda modal_interaction: modal_interaction.response.defer()
                for text_input in extra_params_inputs.values():
                    modal.add_item(text_input)
                await interaction.response.send_modal(modal)
                used_modal = True
                if await modal.wait():
                    return None
                if duration is None and self.duration_ask_message is not None:
                    raw_duration = extra_params_inputs["duration"].value
                    duration = None if self._is_skip(raw_duration) else raw_duration
                if reason is None and self.reason_ask_message is not None:
                    reason = extra_params_inputs["reason"].value or _("The reason was not given.")
            # Defer only when we still own the interaction and we will not
            # send a days-select follow-up through response.send_message.
            elif not self.ask_delete_days:
                await interaction.response.defer()
        else:
            if duration is None and self.duration_ask_message is not None:
                duration = await self._ask_text(
                    ctx,
                    _(self.duration_ask_message).format(
                        member=member,
                        duration=None,
                        reason=reason,
                        channel=ctx.channel,
                    ),
                )
                if duration is None:
                    return None
                if self._is_skip(duration):
                    duration = None
            if reason is None:
                if self.reason_ask_message is not None and reason_required:
                    raw = await self._ask_text(
                        ctx,
                        _(self.reason_ask_message).format(
                            member=member,
                            duration=str(parse_timedelta(duration)) if duration is not None else None,
                            reason=reason,
                            channel=ctx.channel,
                        ),
                    )
                    if raw is None:
                        return None
                    reason = _("The reason was not given.") if raw.lower() == "not" else raw
                else:
                    reason = _("The reason was not given.")

        if duration is not None and self._is_skip(str(duration)):
            duration = None

        days = 0
        wants_days = await self._wants_delete_days(ctx)
        if wants_days:
            # After a modal the original interaction is consumed; pass None
            # so the days prompt is a new message that we can delete later.
            days_interaction = None if used_modal else interaction
            days = await self._ask_delete_days(ctx, days_interaction, member)
            if days is None:
                return None
        elif self.ask_delete_days:
            days = clamp_delete_days(await self.cog.config.guild(ctx.guild).default_delete_days())
            if interaction is not None and not interaction.response.is_done():
                await interaction.response.defer()
        elif interaction is not None and not interaction.response.is_done():
            await interaction.response.defer()

        duration_reason_parts: list[str] = []
        if duration:
            duration_reason_parts.append(str(duration))
        if reason and reason != _("The reason was not given."):
            duration_reason_parts.append(str(reason))
        format_kwargs = {
            "member": member,
            "duration": str(parse_timedelta(duration)) if duration is not None else None,
            "reason": reason,
            "channel": ctx.channel,
            "days": days,
            "duration_reason": " ".join(duration_reason_parts).strip(),
        }

        if (
            not confirmation
            and self.confirmation_ask_message is not None
            and not await CogsUtils.ConfirmationAsk(
                ctx,
                content=_(self.confirmation_ask_message).format(**format_kwargs),
            )
            and not ctx.assume_yes
        ):
            try:
                await CogsUtils.delete_message(ctx.message)
            except Exception:
                pass
            return None

        gif_message = None
        if not self.skip_gif and not self.use_native:
            gif_message = await self.cog.send_action_gif(ctx, self.key)

        finish_message = None
        if finish_message_enabled and self.finish_message is not None and not self.use_native:
            embed = discord.Embed()
            embed.title = f"Void Sanction — {self.emoji} {self.label}"
            embed.description = _(
                "Member: {member.mention} (`{member.id}`)",
            ).format(member=member)
            thumbnail = await self.cog.config.guild(ctx.guild).thumbnail()
            if thumbnail:
                embed.set_thumbnail(url=thumbnail)
            embed.color = await ctx.embed_color()
            embed.set_author(
                name=member.display_name,
                url=member.display_avatar,
                icon_url=member.display_avatar,
            )
            if show_author:
                embed.set_footer(
                    text=str(ctx.author),
                    icon_url=ctx.author.display_avatar,
                )
            embed.add_field(
                name="\u200b",
                value=(
                    _(self.finish_message).format(**format_kwargs)
                    + _("\n*If the command failed, an error will appear below.*")
                ),
                inline=False,
            )
            embed.add_field(name=_("Reason:"), value=f"{reason}")
            if wants_days or self.ask_delete_days or self.key in {"softban", "mute", "mutechannel", "tempmute", "tempmutechannel"}:
                embed.add_field(name=_("Messages cleaned:"), value=_("{days} day(s)").format(days=days))
            if duration is not None:
                parsed = parse_timedelta(duration)
                embed.add_field(
                    inline=False,
                    name=_("Duration:"),
                    value=str(parsed) if parsed is not None else str(duration),
                )
            finish_message = await ctx.send(embed=embed)

        if not fake_action:
            use_native_softban = self.key == "softban" and (not wants_days or days == 1)
            should_purge = self.purge_before and days > 0 and not use_native_softban
            if should_purge:
                status = await ctx.send(
                    _("Cleaning up to {days} day(s) of messages from {member.mention}. This respects Discord rate limits…").format(
                        days=days,
                        member=member,
                    ),
                )
                deleted, scanned = await purge_member_messages(
                    guild=ctx.guild,
                    member=member,
                    days=days,
                    reason=reason,
                )
                try:
                    await status.edit(
                        content=_(
                            "Cleaned {deleted} message(s) across {scanned} channel(s) before the kick.",
                        ).format(deleted=deleted, scanned=scanned),
                    )
                except discord.HTTPException:
                    pass

            if self.key == "softban" and not use_native_softban:
                command_template = "kick {member.id} {reason}"
            elif self.fallback_command and self.key == "void" and not format_kwargs.get("duration_reason"):
                command_template = self.fallback_command
            elif (
                self.fallback_command
                and self.key == "nullvoid"
                and (not reason or reason == _("The reason was not given."))
            ):
                command_template = self.fallback_command
            else:
                command_template = self.warn_system_command if use_warn_system else self.command
            command_string = self._format_template(command_template, **format_kwargs).strip()
            invoked = await self._invoke(ctx, command_string)
            if not invoked and self.fallback_command:
                invoked = await self._invoke(
                    ctx,
                    self._format_template(self.fallback_command, **format_kwargs),
                )
            if not invoked:
                raise commands.UserFeedbackCheckFailure(
                    _("This command doesn't exist: `{command}`").format(command=command_string),
                )

        if finish_message is not None:
            try:
                await finish_message.add_reaction("✅")
            except discord.HTTPException:
                pass
        if gif_message is not None:
            self.cog.schedule_message_delete([gif_message], GIF_CLEANUP_SECONDS)
        return True
