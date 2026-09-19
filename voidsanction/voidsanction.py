from __future__ import annotations

import asyncio
import functools
import typing

import discord
from AAA3A_utils import Cog, CogsUtils, Settings
from redbot.core import Config, app_commands, commands
from redbot.core.bot import Red
from redbot.core.commands.converter import parse_timedelta, timedelta
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.predicates import MessagePredicate

from .constants import ACTIONS_DICT, GIF_CLEANUP_SECONDS, MENU_TIMEOUT_SECONDS
from .dashboard_integration import DashboardIntegration
from .types import Action
from .views import VoidSanctionView

# Credits:
# Forked from AAA3A's SimpleSanction (MIT): https://github.com/AAA3A-AAA3A/AAA3A-cogs
# Thanks to Laggrons-dumb's WarnSystem cog for the grouped-subcommand pattern.
# Thanks to Yami for the interaction-client reload technique used in AAA3A_utils.

_: Translator = Translator("VoidSanction", __file__)


class TimeDeltaConverter(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> timedelta:
        delta = parse_timedelta(argument)
        if delta is not None:
            return argument
        raise commands.BadArgument("Wrong timedelta.")


@app_commands.context_menu(name="Void Sanction")
async def voidsanction_member_context_menu(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=True, thinking=True)
    context = await CogsUtils.invoke_command(
        bot=interaction.client,
        author=interaction.user,
        channel=interaction.channel,
        command=f"voidsanction 00 {member.id}",
        invoke=False,
    )
    if context.command is None or not await discord.utils.async_all(
        [check(context) for check in context.command.checks]
    ):
        await interaction.followup.send(
            _("You're not allowed to execute the `[p]voidsanction` command in this channel."),
            ephemeral=True,
        )
        return
    context.send = functools.partial(interaction.followup.send, ephemeral=True)
    await interaction.client.invoke(context)


@cog_i18n(_)
class VoidSanction(DashboardIntegration, Cog):
    """Sanction members from a button menu. Kick/ban ask how many days of messages to clean. Supports void and nullvoid."""

    def __init__(self, bot: Red) -> None:
        super().__init__(bot=bot)

        self.config: Config = Config.get_conf(
            self,
            identifier=8602192604192026,
            force_registration=True,
        )
        self.config.register_guild(
            use_warn_system=True,
            reason_required=True,
            show_author=True,
            action_confirmation=True,
            finish_message=True,
            ask_delete_days=True,
            ask_delete_days_softban=False,
            ask_delete_days_mute=False,
            default_delete_days=0,
            thumbnail="https://i.imgur.com/Bl62rGd.png",
            action_gifs={},
        )
        self._cleanup_tasks: set[asyncio.Task] = set()

        self.actions: dict[str, Action] = {
            key: Action(cog=self, key=key, **value) for key, value in ACTIONS_DICT.items()
        }

        _settings: dict[str, dict[str, typing.Any]] = {
            "use_warn_system": {
                "converter": bool,
                "description": "Use WarnSystem by Laggron for the sanctions.",
                "aliases": ["warnsystemuse"],
            },
            "reason_required": {
                "converter": bool,
                "description": "Require a reason for each sanction (except userinfo).",
            },
            "show_author": {
                "converter": bool,
                "description": "Show the command author in embeds.",
            },
            "action_confirmation": {
                "converter": bool,
                "description": "Require a confirmation for each sanction (except userinfo).",
            },
            "finish_message": {
                "converter": bool,
                "description": "Send an embed after a sanction command execution.",
            },
            "ask_delete_days": {
                "converter": bool,
                "description": "When kicking or banning, ask how many days of the user's messages to delete (0-7).",
            },
            "ask_delete_days_softban": {
                "converter": bool,
                "description": "Optional. When softbanning, ask how many days of messages to clean (0-7). Off = Red's normal 1-day softban. On + 1 day = native softban. Other values purge then kick.",
            },
            "ask_delete_days_mute": {
                "converter": bool,
                "description": "Optional. When muting (including channel and temp mutes), ask how many days of messages to clean (0-7) before the mute.",
            },
            "default_delete_days": {
                "converter": int,
                "description": "Fallback days (0-7) used if ask_delete_days is disabled for kick/ban.",
            },
            "thumbnail": {
                "converter": str,
                "description": "Set the embed thumbnail.",
            },
        }
        self.settings: Settings = Settings(
            bot=self.bot,
            cog=self,
            config=self.config,
            group=self.config.GUILD,
            settings=_settings,
            global_path=[],
            use_profiles_system=False,
            can_edit=True,
            commands_group=self.configuration,
        )

    async def cog_load(self) -> None:
        await super().cog_load()
        await self.settings.add_commands()
        self.bot.tree.add_command(voidsanction_member_context_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(voidsanction_member_context_menu.name)
        for task in list(self._cleanup_tasks):
            task.cancel()
        self._cleanup_tasks.clear()
        await super().cog_unload()

    def schedule_message_delete(
        self,
        messages: list[discord.Message | None],
        delay: float,
    ) -> None:
        """Delete messages after `delay` seconds. Failures are ignored."""

        async def _run() -> None:
            try:
                await asyncio.sleep(max(delay, 0))
                for message in messages:
                    if message is None:
                        continue
                    try:
                        await message.delete()
                    except (discord.Forbidden, discord.HTTPException, AttributeError):
                        continue
            except asyncio.CancelledError:
                raise

        task = asyncio.create_task(_run())
        self._cleanup_tasks.add(task)
        task.add_done_callback(self._cleanup_tasks.discard)

    async def send_action_gif(
        self,
        ctx: commands.Context,
        action_key: str,
    ) -> discord.Message | None:
        gifs = await self.config.guild(ctx.guild).action_gifs()
        url = (gifs or {}).get(action_key)
        if not url:
            return None
        try:
            return await ctx.send(url)
        except discord.HTTPException:
            return None

    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    @commands.hybrid_group(name="setvoidsanction", aliases=["voidsanctionset"])
    async def configuration(self, ctx: commands.Context) -> None:
        """Configure VoidSanction for your server."""

    @configuration.group(name="gif", aliases=["gifs"])
    async def configuration_gif(self, ctx: commands.Context) -> None:
        """Set a GIF/image URL posted in-channel before each sanction action.

        The GIF is sent first, the moderation command runs next, then the GIF
        is deleted 15 seconds after that command finishes. Nullvoid ignores
        this list and uses the Void cog's own meme (`[p]nullvoidset`).
        """

    @configuration_gif.command(name="set")
    async def configuration_gif_set(
        self,
        ctx: commands.Context,
        action: str,
        url: str,
    ) -> None:
        """Attach a GIF or image URL to one sanction action.

        Example: `[p]setvoidsanction gif set ban https://example.com/ban.gif`
        Valid actions: userinfo, warn, ban, softban, tempban, kick, mute,
        mutechannel, tempmute, tempmutechannel, void, nullvoid.
        """
        key = action.lower().strip()
        if key not in ACTIONS_DICT:
            await ctx.send(
                _("Unknown action `{action}`. Valid: {valid}").format(
                    action=action,
                    valid=", ".join(ACTIONS_DICT),
                )
            )
            return
        if not url.lower().startswith(("http://", "https://")):
            await ctx.send(_("That does not look like an http(s) URL."))
            return
        if key == "nullvoid":
            await ctx.send(
                _(
                    "Saved, but **nullvoid** will not post this GIF. "
                    "Nullvoid uses the Void cog meme from `{prefix}nullvoidset`."
                ).format(prefix=ctx.clean_prefix),
            )
        async with self.config.guild(ctx.guild).action_gifs() as gifs:
            gifs[key] = url
        await ctx.send(_("GIF URL saved for `{action}`.").format(action=key))

    @configuration_gif.command(name="clear", aliases=["remove", "delete", "reset"])
    async def configuration_gif_clear(self, ctx: commands.Context, action: str) -> None:
        """Remove the GIF URL for one action."""
        key = action.lower().strip()
        if key not in ACTIONS_DICT:
            await ctx.send(
                _("Unknown action `{action}`. Valid: {valid}").format(
                    action=action,
                    valid=", ".join(ACTIONS_DICT),
                )
            )
            return
        async with self.config.guild(ctx.guild).action_gifs() as gifs:
            removed = gifs.pop(key, None)
        if removed:
            await ctx.send(_("Cleared the GIF for `{action}`.").format(action=key))
        else:
            await ctx.send(_("No GIF was set for `{action}`.").format(action=key))

    @configuration_gif.command(name="list")
    async def configuration_gif_list(self, ctx: commands.Context) -> None:
        """Show every action and its configured GIF URL."""
        gifs = await self.config.guild(ctx.guild).action_gifs()
        lines = []
        for key, data in ACTIONS_DICT.items():
            url = (gifs or {}).get(key) or _("not set")
            note = _(" — ignored; Void cog meme is used") if key == "nullvoid" else ""
            lines.append(f"{data['emoji']} `{key}`: {url}{note}")
        embed = discord.Embed(
            title=_("VoidSanction action GIFs"),
            description="\n".join(lines)[:4000],
            color=await ctx.embed_color(),
        )
        embed.set_footer(
            text=_("GIFs post before the action and delete {seconds}s after it finishes.").format(
                seconds=GIF_CLEANUP_SECONDS,
            )
        )
        await ctx.send(embed=embed)

    @commands.guild_only()
    @commands.mod_or_permissions(administrator=True)
    @commands.bot_has_permissions(add_reactions=True, embed_links=True)
    @commands.hybrid_group(
        invoke_without_command=True,
        name="voidsanction",
        aliases=["vsanction", "punishmember", "punishuser"],
    )
    async def _voidsanction(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
        confirmation: bool | None = None,
        show_author: bool | None = None,
        finish_message: bool | None = None,
        fake_action: bool | None = False,
        duration_for_mute_or_ban: TimeDeltaConverter | None = None,
        *,
        reason: str = None,
    ) -> None:
        """
        Sanction a member quickly and easily.

        Kick, ban, tempban, void, and nullvoid will ask how many days of
        messages to clean (0–7, Discord's limit). The menu deletes itself
        after an action or after 2.5 minutes.

        All arguments are optional. Specify them in this order.

        Short version: `[p]voidsanction`
        Long version: `[p]voidsanction @member true true true false 3d Spam`
        """
        await self.call_sanction(
            ctx,
            action=None,
            member=member,
            confirmation=confirmation,
            show_author=show_author,
            finish_message=finish_message,
            fake_action=fake_action,
            duration=duration_for_mute_or_ban,
            reason=reason,
        )

    @_voidsanction.command(name="00", aliases=["0", "menu", "sanction"])
    async def sanction_0(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
        confirmation: bool | None = None,
        show_author: bool | None = None,
        finish_message: bool | None = None,
        fake_action: bool | None = False,
        duration_for_mute_or_ban: TimeDeltaConverter | None = None,
        *,
        reason: str = None,
    ) -> None:
        """Open the VoidSanction menu for a member."""
        await self.call_sanction(
            ctx,
            action=None,
            member=member,
            confirmation=confirmation,
            show_author=show_author,
            finish_message=finish_message,
            fake_action=fake_action,
            duration=duration_for_mute_or_ban,
            reason=reason,
        )

    @_voidsanction.command(name="01", aliases=["1", "userinfo", "memberinfo", "info"])
    async def sanction_1(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
        confirmation: bool | None = None,
        show_author: bool | None = None,
        finish_message: bool | None = None,
        fake_action: bool | None = False,
        *,
        reason: str = None,
    ) -> None:
        """ℹ️ Show information about a member."""
        await self.call_sanction(
            ctx,
            action=self.actions["userinfo"],
            member=member,
            confirmation=confirmation,
            show_author=show_author,
            finish_message=finish_message,
            fake_action=fake_action,
            duration=None,
            reason=reason,
        )

    @_voidsanction.command(name="02", aliases=["2", "warn"])
    async def sanction_2(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
        confirmation: bool | None = None,
        show_author: bool | None = None,
        finish_message: bool | None = None,
        fake_action: bool | None = False,
        *,
        reason: str = None,
    ) -> None:
        """⚠️ Add a simple warning on a member."""
        await self.call_sanction(
            ctx,
            action=self.actions["warn"],
            member=member,
            confirmation=confirmation,
            show_author=show_author,
            finish_message=finish_message,
            fake_action=fake_action,
            duration=None,
            reason=reason,
        )

    @_voidsanction.command(name="03", aliases=["3", "ban"])
    async def sanction_3(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
        confirmation: bool | None = None,
        show_author: bool | None = None,
        finish_message: bool | None = None,
        fake_action: bool | None = False,
        *,
        reason: str = None,
    ) -> None:
        """🔨 Ban a member. Asks how many days of messages to delete (0–7)."""
        await self.call_sanction(
            ctx,
            action=self.actions["ban"],
            member=member,
            confirmation=confirmation,
            show_author=show_author,
            finish_message=finish_message,
            fake_action=fake_action,
            duration=None,
            reason=reason,
        )

    @_voidsanction.command(name="04", aliases=["4", "softban"])
    async def sanction_4(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
        confirmation: bool | None = None,
        show_author: bool | None = None,
        finish_message: bool | None = None,
        fake_action: bool | None = False,
        *,
        reason: str = None,
    ) -> None:
        """🔂 SoftBan a member. Enable `[p]setvoidsanction askdeletedayssoftban` to choose 0–7 days."""
        await self.call_sanction(
            ctx,
            action=self.actions["softban"],
            member=member,
            confirmation=confirmation,
            show_author=show_author,
            finish_message=finish_message,
            fake_action=fake_action,
            duration=None,
            reason=reason,
        )

    @_voidsanction.command(name="05", aliases=["5", "tempban"])
    async def sanction_5(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
        confirmation: bool | None = None,
        show_author: bool | None = None,
        finish_message: bool | None = None,
        fake_action: bool | None = False,
        duration_for_mute_or_ban: TimeDeltaConverter | None = None,
        *,
        reason: str = None,
    ) -> None:
        """💨 TempBan a member. Asks how many days of messages to delete (0–7)."""
        await self.call_sanction(
            ctx,
            action=self.actions["tempban"],
            member=member,
            confirmation=confirmation,
            show_author=show_author,
            finish_message=finish_message,
            fake_action=fake_action,
            duration=duration_for_mute_or_ban,
            reason=reason,
        )

    @_voidsanction.command(name="06", aliases=["6", "kick"])
    async def sanction_6(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
        confirmation: bool | None = None,
        show_author: bool | None = None,
        finish_message: bool | None = None,
        fake_action: bool | None = False,
        *,
        reason: str = None,
    ) -> None:
        """👢 Kick a member. Asks how many days of messages to clean (0–7)."""
        await self.call_sanction(
            ctx,
            action=self.actions["kick"],
            member=member,
            confirmation=confirmation,
            show_author=show_author,
            finish_message=finish_message,
            fake_action=fake_action,
            duration=None,
            reason=reason,
        )

    @_voidsanction.command(name="07", aliases=["7", "mute"])
    async def sanction_7(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
        confirmation: bool | None = None,
        show_author: bool | None = None,
        finish_message: bool | None = None,
        fake_action: bool | None = False,
        *,
        reason: str = None,
    ) -> None:
        """🔇 Mute a member. Enable `[p]setvoidsanction askdeletedaysmute` to clean messages first."""
        await self.call_sanction(
            ctx,
            action=self.actions["mute"],
            member=member,
            confirmation=confirmation,
            show_author=show_author,
            finish_message=finish_message,
            fake_action=fake_action,
            duration=None,
            reason=reason,
        )

    @_voidsanction.command(name="08", aliases=["8", "mutechannel"])
    async def sanction_8(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
        confirmation: bool | None = None,
        show_author: bool | None = None,
        finish_message: bool | None = None,
        fake_action: bool | None = False,
        *,
        reason: str = None,
    ) -> None:
        """👊 Mute a member in this channel."""
        await self.call_sanction(
            ctx,
            action=self.actions["mutechannel"],
            member=member,
            confirmation=confirmation,
            show_author=show_author,
            finish_message=finish_message,
            fake_action=fake_action,
            duration=None,
            reason=reason,
        )

    @_voidsanction.command(name="09", aliases=["9", "tempmute"])
    async def sanction_9(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
        confirmation: bool | None = None,
        show_author: bool | None = None,
        finish_message: bool | None = None,
        fake_action: bool | None = False,
        duration_for_mute_or_ban: TimeDeltaConverter | None = None,
        *,
        reason: str = None,
    ) -> None:
        """⏳ TempMute a member in all channels."""
        await self.call_sanction(
            ctx,
            action=self.actions["tempmute"],
            member=member,
            confirmation=confirmation,
            show_author=show_author,
            finish_message=finish_message,
            fake_action=fake_action,
            duration=duration_for_mute_or_ban,
            reason=reason,
        )

    @_voidsanction.command(name="10", aliases=["tempmutechannel"])
    async def sanction_10(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
        confirmation: bool | None = None,
        show_author: bool | None = None,
        finish_message: bool | None = None,
        fake_action: bool | None = False,
        duration_for_mute_or_ban: TimeDeltaConverter | None = None,
        *,
        reason: str = None,
    ) -> None:
        """⌛ TempMute a member in this channel."""
        await self.call_sanction(
            ctx,
            action=self.actions["tempmutechannel"],
            member=member,
            confirmation=confirmation,
            show_author=show_author,
            finish_message=finish_message,
            fake_action=fake_action,
            duration=duration_for_mute_or_ban,
            reason=reason,
        )

    @_voidsanction.command(name="11", aliases=["void"])
    async def sanction_11(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
        confirmation: bool | None = None,
        show_author: bool | None = None,
        finish_message: bool | None = None,
        fake_action: bool | None = False,
        *,
        reason: str = None,
    ) -> None:
        """🕳️ Run the Void cog's `void` command (`void <member> [duration] [reason]`)."""
        await self.call_sanction(
            ctx,
            action=self.actions["void"],
            member=member,
            confirmation=confirmation,
            show_author=show_author,
            finish_message=finish_message,
            fake_action=fake_action,
            duration=None,
            reason=reason,
        )

    @_voidsanction.command(name="12", aliases=["nullvoid"])
    async def sanction_12(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
        confirmation: bool | None = None,
        show_author: bool | None = None,
        finish_message: bool | None = None,
        fake_action: bool | None = False,
        *,
        reason: str = None,
    ) -> None:
        """⬛ Run the Void cog's `nullvoid` meme flow. No extra GIF or purge from this cog."""
        await self.call_sanction(
            ctx,
            action=self.actions["nullvoid"],
            member=member,
            confirmation=confirmation,
            show_author=show_author,
            finish_message=finish_message,
            fake_action=fake_action,
            duration=None,
            reason=reason,
        )

    async def call_sanction(
        self,
        ctx: commands.Context,
        action: Action | None = None,
        member: discord.Member | None = None,
        confirmation: bool | None = None,
        show_author: bool | None = None,
        finish_message: bool | None = None,
        fake_action: bool | None = False,
        duration: typing.Optional[TimeDeltaConverter] = None,
        reason: str = None,
    ) -> None:
        config = await self.config.guild(ctx.guild).all()
        if show_author is None:
            show_author = config["show_author"]
        if confirmation is None:
            confirmation = not config["action_confirmation"]
        if finish_message is None:
            finish_message = config["finish_message"]
        if reason is not None and reason.lower() == "not":
            reason = _("The reason was not given.")

        if member is None:
            embed = discord.Embed()
            embed.title = _("Void Sanction")
            embed.description = _(
                "Which member do you want to sanction? (Type `cancel` to cancel.)",
            )
            embed.color = await ctx.embed_color()
            message = await ctx.send(embed=embed)
            try:
                pred = MessagePredicate.valid_member(ctx)
                msg = await self.bot.wait_for(
                    "message",
                    timeout=MENU_TIMEOUT_SECONDS,
                    check=pred,
                )
                await CogsUtils.delete_message(message)
                await CogsUtils.delete_message(msg)
                if msg.content.lower() == "cancel":
                    return
                member = pred.result
            except TimeoutError:
                await CogsUtils.delete_message(message)
                raise commands.UserFeedbackCheckFailure(_("Timed out, please try again."))

        if action is not None:
            await action.process(
                ctx,
                interaction=None,
                member=member,
                duration=duration,
                reason=reason,
                finish_message_enabled=finish_message,
                reason_required=await self.config.guild(ctx.guild).reason_required(),
                confirmation=confirmation,
                show_author=show_author,
                fake_action=fake_action,
            )
        else:
            await VoidSanctionView(
                cog=self,
                member=member,
                duration=duration,
                reason=reason,
                finish_message_enabled=finish_message,
                reason_required=await self.config.guild(ctx.guild).reason_required(),
                confirmation=confirmation,
                show_author=show_author,
                fake_action=fake_action,
            ).start(ctx)
