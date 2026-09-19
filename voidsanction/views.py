from __future__ import annotations

import asyncio
import typing

import discord
from AAA3A_utils import CogsUtils
from redbot.core import commands
from redbot.core.commands.converter import parse_timedelta
from redbot.core.i18n import Translator

from .constants import (
    ACTIONS_DICT,
    DELETE_MESSAGE_DAYS_LIMIT,
    MENU_TIMEOUT_SECONDS,
    POST_ACTION_CLEANUP_SECONDS,
)

if typing.TYPE_CHECKING:
    from .types import Action

_: Translator = Translator("VoidSanction", __file__)


class DeleteDaysView(discord.ui.View):
    """Prompt for 0-7 days of message cleanup. Self-deletes on timeout."""

    def __init__(self, author_id: int, member: discord.Member) -> None:
        super().__init__(timeout=MENU_TIMEOUT_SECONDS)
        self.author_id = author_id
        self.member = member
        self.days: int | None = None
        self.cancelled = False
        self._message: discord.Message | None = None

        options = [
            discord.SelectOption(
                label="0 days — keep their messages",
                value="0",
                description="Do not delete any messages.",
                emoji="💬",
            )
        ]
        for day in range(1, DELETE_MESSAGE_DAYS_LIMIT + 1):
            suffix = "day" if day == 1 else "days"
            extra = " — Discord maximum" if day == DELETE_MESSAGE_DAYS_LIMIT else ""
            options.append(
                discord.SelectOption(
                    label=f"{day} {suffix}{extra}",
                    value=str(day),
                    description=f"Delete messages from the last {day} {suffix}.",
                    emoji="🧹",
                )
            )
        select = discord.ui.Select(
            placeholder="How many days of this user's messages should I clean?",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="voidsanction_days",
        )
        select.callback = self._picked
        self.add_item(select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                _("Only the moderator who opened this menu can use it."),
                ephemeral=True,
            )
            return False
        return True

    async def _picked(self, interaction: discord.Interaction) -> None:
        values = interaction.data.get("values") or ["0"]
        self.days = int(values[0])
        try:
            await interaction.response.defer()
        except discord.HTTPException:
            pass
        self.stop()
        await self._cleanup_message()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.cancelled = True
        try:
            await interaction.response.defer()
        except discord.HTTPException:
            pass
        self.stop()
        await self._cleanup_message()

    async def on_timeout(self) -> None:
        self.cancelled = True
        await self._cleanup_message()

    async def _cleanup_message(self) -> None:
        if self._message is not None:
            try:
                await self._message.delete()
            except discord.HTTPException:
                try:
                    await self._message.edit(view=None)
                except discord.HTTPException:
                    pass


class VoidSanctionView(discord.ui.View):
    def __init__(
        self,
        cog: commands.Cog,
        member: discord.Member,
        duration: str | None = None,
        reason: str | None = "The reason was not given.",
        finish_message_enabled: bool | None = True,
        reason_required: bool | None = True,
        confirmation: bool | None = False,
        show_author: bool | None = True,
        fake_action: bool | None = False,
    ) -> None:
        super().__init__(timeout=MENU_TIMEOUT_SECONDS)
        self.cog: commands.Cog = cog
        self.ctx: commands.Context | None = None

        self.member = member
        self.duration = duration
        self.reason = reason

        self.finish_message_enabled = finish_message_enabled
        self.reason_required = reason_required
        self.confirmation = confirmation
        self.show_author = show_author
        self.fake_action = fake_action

        self._message: discord.Message | None = None
        self._ready: asyncio.Event = asyncio.Event()
        self._busy = False

    def _available_actions(self) -> dict[str, dict[str, object]]:
        available = {}
        for key, value in ACTIONS_DICT.items():
            if value.get("void_command"):
                command_name = key
                if self.ctx is None or self.ctx.bot.get_command(command_name) is None:
                    continue
            available[key] = value
        return available

    async def start(self, ctx: commands.Context) -> discord.Message:
        self.ctx = ctx
        embed = await self.get_embed()
        for key, value in self._available_actions().items():
            button = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label=str(value["label"]),
                emoji=str(value["emoji"]),
                custom_id=key,
            )
            button.callback = self._callback
            self.add_item(button)
        self._message = await self.ctx.send(embed=embed, view=self)
        if hasattr(self.cog, "views"):
            self.cog.views[self._message] = self
        await self._ready.wait()
        return self._message

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.ctx is None:
            return False
        if interaction.user.id not in [self.ctx.author.id] + list(self.ctx.bot.owner_ids):
            await interaction.response.send_message(
                _("You are not allowed to use this interaction."),
                ephemeral=True,
            )
            return False
        return True

    async def _disable_controls(self) -> None:
        for child in self.children:
            if hasattr(child, "disabled"):
                child.disabled = True
        if self._message is not None:
            try:
                await self._message.edit(view=self)
            except discord.HTTPException:
                pass

    async def cleanup(self, delay: float = 0) -> None:
        self.stop()
        await self._disable_controls()
        message = self._message
        self._ready.set()
        if message is None:
            return
        if delay and delay > 0 and hasattr(self.cog, "schedule_message_delete"):
            self.cog.schedule_message_delete([message], delay)
            return
        try:
            await CogsUtils.delete_message(message)
        except Exception:
            try:
                await message.delete()
            except discord.HTTPException:
                try:
                    await message.edit(view=None)
                except discord.HTTPException:
                    pass

    async def on_timeout(self) -> None:
        # Idle for 2.5 minutes — delete immediately.
        await self.cleanup(delay=0)

    @discord.ui.button(style=discord.ButtonStyle.danger, emoji="✖️", custom_id="close_page", row=4)
    async def close_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        try:
            await interaction.response.defer()
        except discord.NotFound:
            pass
        await self.cleanup()

    async def get_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=_("Void Sanction"),
            color=await self.ctx.embed_color(),
        )
        embed.description = _(
            "Pick a sanction for {member.mention} (`{member.id}`).\n"
            "Kick, ban, and tempban ask how many days of messages to clean (0–7).\n"
            "Mute and softban do the same only if their toggles are enabled.\n"
            "Nullvoid uses the Void cog's own black-hole GIF, purge, and isolate flow.\n"
            "This menu deletes itself 10 seconds after an action, or after 2.5 minutes if nobody uses it.",
        ).format(member=self.member)
        thumbnail = await self.cog.config.guild(self.ctx.guild).thumbnail()
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        embed.set_author(
            name=self.member.display_name,
            url=self.member.display_avatar,
            icon_url=self.member.display_avatar,
        )
        if self.show_author:
            embed.set_footer(
                text=str(self.ctx.author),
                icon_url=self.ctx.author.display_avatar,
            )
        embed.add_field(
            inline=False,
            name=_("Possible actions:"),
            value=" — ".join(
                f"{value['emoji']} {value['label']}"
                for value in self._available_actions().values()
            )
            or _("No actions available."),
        )
        if self.reason is not None:
            embed.add_field(inline=False, name=_("Reason:"), value=f"{self.reason}")
        if self.duration is not None:
            parsed = parse_timedelta(str(self.duration))
            embed.add_field(
                inline=False,
                name=_("Duration:"),
                value=str(parsed or self.duration),
            )
        return embed

    async def _callback(self, interaction: discord.Interaction) -> None:
        if self._busy:
            await interaction.response.send_message(
                _("An action is already running on this menu."),
                ephemeral=True,
            )
            return
        self._busy = True
        try:
            if self.fake_action:
                try:
                    await interaction.response.send_message(
                        _(
                            "You are using this command in Fake mode, so no action will be taken, but I will pretend it is the case.",
                        ),
                        ephemeral=True,
                    )
                except discord.HTTPException:
                    pass
            custom_id = interaction.data["custom_id"]
            action: Action = self.cog.actions[custom_id]
            result = await action.process(
                self.ctx,
                interaction=interaction if not self.fake_action else None,
                member=self.member,
                duration=self.duration,
                reason=self.reason,
                finish_message_enabled=self.finish_message_enabled,
                reason_required=await self.cog.config.guild(self.ctx.guild).reason_required(),
                confirmation=self.confirmation,
                show_author=self.show_author,
                fake_action=self.fake_action,
            )
            # Completed or cancelled follow-ups both tear the menu down so
            # leftover buttons cannot be clicked after the fact.
            if result is True:
                await self.cleanup(delay=POST_ACTION_CLEANUP_SECONDS)
            elif result is None:
                # Prompt cancelled — drop the menu after the same 10s grace.
                await self.cleanup(delay=POST_ACTION_CLEANUP_SECONDS)
            else:
                self._busy = False
        except Exception:
            self._busy = False
            if interaction is not None and not interaction.response.is_done():
                try:
                    await interaction.response.send_message(
                        _("That action failed. Check my permissions and try again."),
                        ephemeral=True,
                    )
                except discord.HTTPException:
                    pass
            raise
