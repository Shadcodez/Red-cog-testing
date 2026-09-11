"""Discord UI views and modals for the Giveaways cog."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, Dict, Optional

import discord
from redbot.core import commands
from redbot.core.commands import ColourConverter, TimedeltaConverter

from .helpers import (
    MAX_DESCRIPTION_LEN,
    MAX_PRIZE_LEN,
    clamp_winners,
    humanize_seconds,
    validate_duration_seconds,
)

if TYPE_CHECKING:
    from .giveaways import Giveaways


async def safe_delete(message: Optional[discord.Message]) -> None:
    if message is None:
        return
    try:
        await message.delete()
    except discord.HTTPException:
        try:
            await message.edit(content="Setup closed.", embed=None, view=None)
        except discord.HTTPException:
            pass


def parse_duration_string(ctx: commands.Context, raw: str):
    converter = TimedeltaConverter(
        default_unit="minutes",
        minimum=timedelta(seconds=10),
        maximum=timedelta(days=60),
    )
    return converter.convert(ctx, raw)


class GiveawayEssentialsModal(discord.ui.Modal, title="New giveaway"):
    """First popup — collect the required fields in one form."""

    prize = discord.ui.TextInput(
        label="Prize",
        placeholder="e.g. 1 month Discord Nitro",
        max_length=MAX_PRIZE_LEN,
        required=True,
    )
    duration = discord.ui.TextInput(
        label="Duration",
        placeholder="30m, 12h, 2d, 1d12h",
        max_length=32,
        required=True,
    )
    winners = discord.ui.TextInput(
        label="Number of winners",
        placeholder="1",
        max_length=2,
        required=True,
        default="1",
    )
    description = discord.ui.TextInput(
        label="Description (optional)",
        style=discord.TextStyle.paragraph,
        placeholder="Anything extra to show on the embed.",
        max_length=MAX_DESCRIPTION_LEN,
        required=False,
    )
    colour = discord.ui.TextInput(
        label="Colour (optional)",
        placeholder="gold, blurple, #ff5a36",
        max_length=32,
        required=False,
    )

    def __init__(
        self,
        cog: "Giveaways",
        ctx: commands.Context,
        draft: Dict[str, Any],
        launch_message: Optional[discord.Message],
        *,
        edit_of: Optional[Dict[str, Any]] = None,
    ):
        super().__init__()
        self.cog = cog
        self.ctx = ctx
        self.draft = dict(draft)
        self.launch_message = launch_message
        self.edit_of = edit_of
        if self.draft.get("prize"):
            self.prize.default = str(self.draft["prize"])[:MAX_PRIZE_LEN]
        if self.draft.get("duration_seconds"):
            self.duration.default = humanize_seconds(int(self.draft["duration_seconds"])).replace(" ", "")
        self.winners.default = str(self.draft.get("winners") or 1)
        if self.draft.get("description"):
            self.description.default = str(self.draft["description"])[:MAX_DESCRIPTION_LEN]
        colour = self.draft.get("color")
        if isinstance(colour, discord.Colour):
            self.colour.default = str(colour)
        elif colour is not None:
            self.colour.default = hex(int(colour))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        prize = str(self.prize.value).strip()[:MAX_PRIZE_LEN]
        if not prize:
            await interaction.response.send_message("A prize is required.", ephemeral=True)
            return
        try:
            delta = await parse_duration_string(self.ctx, str(self.duration.value))
        except commands.BadArgument as exc:
            await interaction.response.send_message(str(exc) or "Invalid duration.", ephemeral=True)
            return
        ok, err = validate_duration_seconds(delta.total_seconds())
        if not ok:
            await interaction.response.send_message(err, ephemeral=True)
            return
        try:
            winners = clamp_winners(int(str(self.winners.value).strip()))
        except ValueError:
            await interaction.response.send_message("Winners must be a number from 1 to 20.", ephemeral=True)
            return
        colour_value = None
        raw_colour = (str(self.colour.value) or "").strip()
        if raw_colour:
            try:
                colour_value = await ColourConverter().convert(self.ctx, raw_colour)
            except commands.BadArgument as exc:
                await interaction.response.send_message(str(exc) or "Invalid colour.", ephemeral=True)
                return

        self.draft["prize"] = prize
        self.draft["duration_seconds"] = int(delta.total_seconds())
        self.draft["winners"] = winners
        self.draft["description"] = (str(self.description.value) or "").strip()[:MAX_DESCRIPTION_LEN]
        if colour_value is not None:
            self.draft["color"] = colour_value

        await safe_delete(self.launch_message)
        await self.cog.forget_setup_message(self.launch_message)

        view = GiveawayBuilderView(self.cog, self.ctx, self.draft, edit_of=self.edit_of, ephemeral=True)
        await interaction.response.send_message(
            content="Only you can see this. Dismiss it anytime, or press **Cancel**.",
            embed=view.preview_embed(),
            view=view,
            ephemeral=True,
        )
        try:
            view.message = await interaction.original_response()
        except discord.HTTPException:
            view.message = None

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        if interaction.response.is_done():
            await interaction.followup.send("Something went wrong with that form.", ephemeral=True)
        else:
            await interaction.response.send_message("Something went wrong with that form.", ephemeral=True)


class GiveawayLaunchView(discord.ui.View):
    """One short-lived public prompt. Deleted as soon as the user continues or cancels."""

    def __init__(
        self,
        cog: "Giveaways",
        ctx: commands.Context,
        draft: Optional[Dict[str, Any]] = None,
        *,
        edit_of: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(timeout=45)
        self.cog = cog
        self.ctx = ctx
        self.author_id = ctx.author.id
        self.draft = draft or {}
        self.edit_of = edit_of
        self.message: Optional[discord.Message] = None
        if edit_of:
            self.btn_setup.label = "Edit giveaway"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This setup isn't yours.", ephemeral=True)
            return False
        return True

    async def cleanup(self) -> None:
        self.stop()
        await safe_delete(self.message)
        await self.cog.forget_setup_message(self.message)
        self.message = None

    async def on_timeout(self) -> None:
        await self.cleanup()

    @discord.ui.button(label="Set up", style=discord.ButtonStyle.success, emoji="🎉")
    async def btn_setup(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(
            GiveawayEssentialsModal(
                self.cog,
                self.ctx,
                self.draft,
                self.message,
                edit_of=self.edit_of,
            )
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def btn_cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cleanup()
        await interaction.response.send_message("Giveaway setup cancelled.", ephemeral=True)


class PrizeModal(discord.ui.Modal, title="Giveaway prize"):
    prize = discord.ui.TextInput(
        label="Prize",
        placeholder="e.g. 1 month Discord Nitro",
        max_length=MAX_PRIZE_LEN,
        required=True,
    )

    def __init__(self, view: "GiveawayBuilderView"):
        super().__init__()
        self.builder = view
        if view.draft.get("prize"):
            self.prize.default = str(view.draft["prize"])[:MAX_PRIZE_LEN]

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.builder.draft["prize"] = str(self.prize.value).strip()[:MAX_PRIZE_LEN]
        await self.builder.refresh(interaction)


class DescriptionModal(discord.ui.Modal, title="Giveaway description"):
    description = discord.ui.TextInput(
        label="Description",
        style=discord.TextStyle.paragraph,
        placeholder="Optional extra details. Leave empty to clear.",
        max_length=MAX_DESCRIPTION_LEN,
        required=False,
    )

    def __init__(self, view: "GiveawayBuilderView"):
        super().__init__()
        self.builder = view
        if view.draft.get("description"):
            self.description.default = str(view.draft["description"])[:MAX_DESCRIPTION_LEN]

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.builder.draft["description"] = (str(self.description.value) or "").strip()[:MAX_DESCRIPTION_LEN]
        await self.builder.refresh(interaction)


class DurationModal(discord.ui.Modal, title="Giveaway duration"):
    duration = discord.ui.TextInput(
        label="How long should it run?",
        placeholder="Examples: 30m, 12h, 2d, 1d12h",
        required=True,
        max_length=32,
    )

    def __init__(self, view: "GiveawayBuilderView"):
        super().__init__()
        self.builder = view
        current = view.draft.get("duration_seconds")
        if current:
            self.duration.default = humanize_seconds(int(current)).replace(" ", "")

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            delta = await parse_duration_string(self.builder.ctx, str(self.duration.value))
        except commands.BadArgument as exc:
            await interaction.response.send_message(str(exc) or "Invalid duration.", ephemeral=True)
            return
        ok, err = validate_duration_seconds(delta.total_seconds())
        if not ok:
            await interaction.response.send_message(err, ephemeral=True)
            return
        self.builder.draft["duration_seconds"] = int(delta.total_seconds())
        await self.builder.refresh(interaction)


class WinnersModal(discord.ui.Modal, title="Number of winners"):
    winners = discord.ui.TextInput(
        label="Winners",
        placeholder="1-20",
        required=True,
        max_length=2,
    )

    def __init__(self, view: "GiveawayBuilderView"):
        super().__init__()
        self.builder = view
        self.winners.default = str(view.draft.get("winners") or 1)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            value = clamp_winners(int(str(self.winners.value).strip()))
        except ValueError:
            await interaction.response.send_message("Winners must be a number from 1 to 20.", ephemeral=True)
            return
        self.builder.draft["winners"] = value
        await self.builder.refresh(interaction)


class ColourModal(discord.ui.Modal, title="Embed colour"):
    colour = discord.ui.TextInput(
        label="Colour",
        placeholder="red, gold, blurple, #ff5a36",
        required=False,
        max_length=32,
    )

    def __init__(self, view: "GiveawayBuilderView"):
        super().__init__()
        self.builder = view
        current = view.draft.get("color")
        if isinstance(current, discord.Colour):
            self.colour.default = str(current)
        elif current is not None:
            self.colour.default = hex(int(current))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw = (str(self.colour.value) or "").strip()
        if not raw:
            self.builder.draft["color"] = None
            await self.builder.refresh(interaction)
            return
        try:
            parsed = await ColourConverter().convert(self.builder.ctx, raw)
        except commands.BadArgument as exc:
            await interaction.response.send_message(str(exc) or "Invalid colour.", ephemeral=True)
            return
        self.builder.draft["color"] = parsed
        await self.builder.refresh(interaction)


class AppearanceModal(discord.ui.Modal, title="Giveaway appearance"):
    image = discord.ui.TextInput(
        label="Image URL",
        placeholder="https://…  (leave empty to clear)",
        required=False,
        max_length=400,
    )
    thumbnail = discord.ui.TextInput(
        label="Thumbnail URL",
        placeholder="https://…  (leave empty to clear)",
        required=False,
        max_length=400,
    )
    button_label = discord.ui.TextInput(
        label="Enter button label",
        placeholder="Enter",
        required=False,
        max_length=80,
    )

    def __init__(self, view: "GiveawayBuilderView"):
        super().__init__()
        self.builder = view
        if view.draft.get("image"):
            self.image.default = str(view.draft["image"])[:400]
        if view.draft.get("thumbnail"):
            self.thumbnail.default = str(view.draft["thumbnail"])[:400]
        self.button_label.default = str(view.draft.get("button_label") or "Enter")[:80]

    async def on_submit(self, interaction: discord.Interaction) -> None:
        image = (str(self.image.value) or "").strip()
        thumb = (str(self.thumbnail.value) or "").strip()
        label = (str(self.button_label.value) or "Enter").strip() or "Enter"
        self.builder.draft["image"] = image or None
        self.builder.draft["thumbnail"] = thumb or None
        self.builder.draft["button_label"] = label[:80]
        await self.builder.refresh(interaction)


class RequirementsModal(discord.ui.Modal, title="Entry requirements"):
    account_days = discord.ui.TextInput(
        label="Minimum account age (days)",
        placeholder="0",
        required=False,
        max_length=4,
    )
    server_days = discord.ui.TextInput(
        label="Minimum server age (days)",
        placeholder="0",
        required=False,
        max_length=4,
    )
    bonus_role = discord.ui.TextInput(
        label="Bonus ticket role (mention or ID)",
        placeholder="Optional — e.g. @Nitro or 123456789012345678",
        required=False,
        max_length=80,
    )
    bonus_tickets = discord.ui.TextInput(
        label="Extra tickets for that bonus role",
        placeholder="1",
        required=False,
        max_length=2,
    )

    def __init__(self, view: "GiveawayBuilderView"):
        super().__init__()
        self.builder = view
        self.account_days.default = str(view.draft.get("min_account_days") or 0)
        self.server_days.default = str(view.draft.get("min_server_days") or 0)
        bonus = view.draft.get("bonus_roles") or {}
        if bonus:
            rid = next(iter(bonus.keys()))
            self.bonus_role.default = rid
            self.bonus_tickets.default = str(bonus.get(rid) or 1)
        else:
            self.bonus_tickets.default = str(view.draft.get("bonus_ticket_count") or 1)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        def parse_int(raw: str, lo: int, hi: int) -> int:
            raw = (raw or "0").strip() or "0"
            return max(lo, min(hi, int(raw)))

        try:
            self.builder.draft["min_account_days"] = parse_int(str(self.account_days.value), 0, 3650)
            self.builder.draft["min_server_days"] = parse_int(str(self.server_days.value), 0, 3650)
            extra = parse_int(str(self.bonus_tickets.value) or "1", 1, 50)
        except ValueError:
            await interaction.response.send_message("Use whole numbers for those fields.", ephemeral=True)
            return

        raw_role = (str(self.bonus_role.value) or "").strip()
        role_id = None
        if raw_role:
            digits = "".join(ch for ch in raw_role if ch.isdigit())
            if digits:
                role_id = int(digits)
            else:
                await interaction.response.send_message(
                    "Could not read that bonus role. Use a mention or ID.",
                    ephemeral=True,
                )
                return

        self.builder.draft["bonus_ticket_count"] = extra
        if role_id:
            self.builder.draft["bonus_roles"] = {str(role_id): extra}
        else:
            self.builder.draft["bonus_roles"] = {}
        await self.builder.refresh(interaction)


class GiveawayBuilderView(discord.ui.View):
    """Private editor shown after the first popup. Mirrors EmbedCreator controls."""

    def __init__(
        self,
        cog: "Giveaways",
        ctx: commands.Context,
        draft: Optional[Dict[str, Any]] = None,
        *,
        edit_of: Optional[Dict[str, Any]] = None,
        ephemeral: bool = True,
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.ctx = ctx
        self.author_id = ctx.author.id
        self.message: Optional[discord.Message] = None
        self.edit_of = edit_of
        self.ephemeral = ephemeral
        self.draft: Dict[str, Any] = {
            "prize": None,
            "description": "",
            "duration_seconds": None,
            "winners": 1,
            "channel_id": ctx.channel.id,
            "required_roles": [],
            "blacklist_roles": [],
            "bonus_roles": {},
            "min_account_days": 0,
            "min_server_days": 0,
            "allow_host": False,
            "dm_winners": True,
            "image": None,
            "thumbnail": None,
            "color": None,
            "button_label": "Enter",
            "button_emoji": "🎉",
            "ping_role": None,
        }
        if draft:
            self.draft.update(draft)
        self._sync_toggle_buttons()

    @property
    def editing(self) -> bool:
        return self.edit_of is not None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the command author can use this editor.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        self._disable()
        if self.message and not self.ephemeral:
            await safe_delete(self.message)

    def _disable(self) -> None:
        for item in self.children:
            item.disabled = True  # type: ignore[attr-defined]

    def _sync_toggle_buttons(self) -> None:
        host_on = bool(self.draft.get("allow_host"))
        dm_on = bool(self.draft.get("dm_winners", True))
        self.btn_host.label = f"Host entry: {'ON' if host_on else 'OFF'}"
        self.btn_host.style = discord.ButtonStyle.success if host_on else discord.ButtonStyle.secondary
        self.btn_dm.label = f"DM winners: {'ON' if dm_on else 'OFF'}"
        self.btn_dm.style = discord.ButtonStyle.success if dm_on else discord.ButtonStyle.secondary
        self.btn_commit.label = "Save changes" if self.editing else "Start giveaway"

    def _colour(self) -> discord.Colour:
        colour = self.draft.get("color")
        if isinstance(colour, discord.Colour):
            return colour
        if colour is not None:
            try:
                return discord.Colour(int(colour))
            except (TypeError, ValueError):
                pass
        return discord.Colour.blurple()

    def preview_embed(self) -> discord.Embed:
        prize = self.draft.get("prize") or "Not set"
        duration = self.draft.get("duration_seconds")
        duration_txt = humanize_seconds(duration) if duration else "Not set"
        channel_id = self.draft.get("channel_id")
        channel_txt = f"<#{channel_id}>" if channel_id else "Here"
        mode = "Editing existing giveaway" if self.editing else "Private giveaway editor"

        embed = discord.Embed(
            title="Giveaway editor",
            description=(
                f"**{mode}**\n"
                "Adjust anything below, then press "
                f"**{self.btn_commit.label}**. Cancel or dismiss this message at any time."
            ),
            colour=self._colour(),
        )
        embed.add_field(name="Prize", value=prize[:256], inline=True)
        embed.add_field(name="Duration", value=duration_txt, inline=True)
        embed.add_field(name="Winners", value=str(self.draft.get("winners") or 1), inline=True)
        embed.add_field(name="Channel", value=channel_txt, inline=True)
        embed.add_field(name="Button", value=self.draft.get("button_label") or "Enter", inline=True)
        embed.add_field(
            name="Toggles",
            value=(
                f"Host can enter: {'yes' if self.draft.get('allow_host') else 'no'}\n"
                f"DM winners: {'yes' if self.draft.get('dm_winners', True) else 'no'}"
            ),
            inline=True,
        )
        desc = (self.draft.get("description") or "").strip() or "None"
        embed.add_field(name="Description", value=desc[:1024], inline=False)
        req = []
        for rid in self.draft.get("required_roles") or []:
            req.append(f"Required: <@&{rid}>")
        if self.draft.get("min_account_days"):
            req.append(f"Account age: {self.draft['min_account_days']}d+")
        if self.draft.get("min_server_days"):
            req.append(f"Server age: {self.draft['min_server_days']}d+")
        bonus = self.draft.get("bonus_roles") or {}
        for rid, extra in bonus.items():
            req.append(f"<@&{rid}> +{extra} ticket(s)")
        embed.add_field(name="Requirements", value="\n".join(req) or "None", inline=False)
        if self.draft.get("image"):
            embed.set_image(url=self.draft["image"])
        if self.draft.get("thumbnail"):
            embed.set_thumbnail(url=self.draft["thumbnail"])
        embed.set_footer(text="This editor is private. It times out after 5 minutes.")
        return embed

    async def refresh(self, interaction: discord.Interaction) -> None:
        self._sync_toggle_buttons()
        kwargs = {"embed": self.preview_embed(), "view": self}
        if interaction.response.is_done():
            await interaction.edit_original_response(**kwargs)
        else:
            await interaction.response.edit_message(**kwargs)

    @discord.ui.button(label="Prize", style=discord.ButtonStyle.secondary, row=0)
    async def btn_prize(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(PrizeModal(self))

    @discord.ui.button(label="Duration", style=discord.ButtonStyle.secondary, row=0)
    async def btn_duration(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(DurationModal(self))

    @discord.ui.button(label="Winners", style=discord.ButtonStyle.secondary, row=0)
    async def btn_winners(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(WinnersModal(self))

    @discord.ui.button(label="Description", style=discord.ButtonStyle.secondary, row=0)
    async def btn_description(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(DescriptionModal(self))

    @discord.ui.button(label="Colour", style=discord.ButtonStyle.secondary, row=0)
    async def btn_colour(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(ColourModal(self))

    @discord.ui.button(label="Appearance", style=discord.ButtonStyle.secondary, row=1)
    async def btn_appearance(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(AppearanceModal(self))

    @discord.ui.button(label="Requirements", style=discord.ButtonStyle.secondary, row=1)
    async def btn_requirements(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(RequirementsModal(self))

    @discord.ui.button(label="Host entry: OFF", style=discord.ButtonStyle.secondary, row=1)
    async def btn_host(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.draft["allow_host"] = not bool(self.draft.get("allow_host"))
        await self.refresh(interaction)

    @discord.ui.button(label="DM winners: ON", style=discord.ButtonStyle.success, row=1)
    async def btn_dm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.draft["dm_winners"] = not bool(self.draft.get("dm_winners", True))
        await self.refresh(interaction)

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Required role (optional)",
        min_values=0,
        max_values=1,
        row=2,
    )
    async def sel_role(self, interaction: discord.Interaction, select: discord.ui.RoleSelect) -> None:
        if not select.values:
            self.draft["required_roles"] = []
        else:
            role = select.values[0]
            role_id = getattr(role, "id", None) or int(role)
            self.draft["required_roles"] = [int(role_id)]
        await self.refresh(interaction)

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text, discord.ChannelType.news],
        placeholder="Channel to post the giveaway in",
        min_values=1,
        max_values=1,
        row=3,
    )
    async def sel_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect) -> None:
        if not select.values:
            await interaction.response.defer()
            return
        channel = select.values[0]
        channel_id = getattr(channel, "id", None) or int(channel)
        self.draft["channel_id"] = int(channel_id)
        await self.refresh(interaction)

    @discord.ui.button(label="Start giveaway", style=discord.ButtonStyle.success, row=4)
    async def btn_commit(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self.draft.get("prize"):
            await interaction.response.send_message("Set a prize first.", ephemeral=True)
            return
        if not self.draft.get("duration_seconds"):
            await interaction.response.send_message("Set a duration first.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        self._disable()
        try:
            if self.editing:
                await self.cog.apply_builder_edit(self.ctx, self.edit_of, self.draft)
                done = "Giveaway updated."
            else:
                message = await self.cog.start_from_draft(self.ctx, self.draft)
                done = f"Giveaway posted in <#{self.draft.get('channel_id')}> (`{message.id}`)."
        except commands.UserFeedbackCheckFailure as exc:
            for item in self.children:
                item.disabled = False  # type: ignore[attr-defined]
            self._sync_toggle_buttons()
            try:
                await interaction.edit_original_response(embed=self.preview_embed(), view=self)
            except discord.HTTPException:
                pass
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        self.stop()
        try:
            await interaction.edit_original_response(content=done, embed=None, view=None)
        except discord.HTTPException:
            await interaction.followup.send(done, ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, row=4)
    async def btn_cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        self._disable()
        await interaction.response.edit_message(
            content="Giveaway setup cancelled.",
            embed=None,
            view=None,
        )


class GiveawayJoinView(discord.ui.View):
    """Persistent enter/leave view. One instance is registered globally."""

    def __init__(self, cog: "Giveaways"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Enter",
        style=discord.ButtonStyle.success,
        emoji="🎉",
        custom_id="shadgw:join",
    )
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.message is None or interaction.guild is None:
            await interaction.response.send_message("This giveaway is no longer available.", ephemeral=True)
            return
        await self.cog.handle_join(interaction, interaction.message.id)

    @discord.ui.button(
        label="Leave",
        style=discord.ButtonStyle.secondary,
        custom_id="shadgw:leave",
    )
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.message is None or interaction.guild is None:
            await interaction.response.send_message("This giveaway is no longer available.", ephemeral=True)
            return
        await self.cog.handle_leave(interaction, interaction.message.id)


class EndedGiveawayView(discord.ui.View):
    """Disabled buttons shown on an ended giveaway."""

    def __init__(self, label: str = "Ended"):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.secondary,
                emoji="🎉",
                disabled=True,
                custom_id="shadgw:ended",
            )
        )
