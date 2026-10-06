"""Red cog: text campaign. State hangs off the user id, never the channel."""

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from redbot.core import Config, commands
from redbot.core.utils.chat_formatting import box

from .borders import BANNERS, choice_block
from .engine import Campaign, fresh_state, new_code, snapshot
from .story import load_nodes

log = logging.getLogger("red.witcher")


class ChoiceView(discord.ui.View):
    def __init__(self, cog: "Witcher", user_id: int, count: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id
        for n in range(1, min(count, 10) + 1):
            self.add_item(ChoiceButton(n))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This road belongs to someone else.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        self.stop()


class ChoiceButton(discord.ui.Button):
    def __init__(self, number: int):
        super().__init__(
            label=str(number),
            style=discord.ButtonStyle.secondary,
            custom_id=f"whchoice:{number}",
        )
        self.number = number

    async def callback(self, interaction: discord.Interaction):
        view: ChoiceView = self.view
        await interaction.response.defer()
        await view.cog.resolve_choice(interaction.user, self.number, interaction=interaction)
        view.stop()


class Witcher(commands.Cog):
    """A dark-fantasy text campaign on a witcher's road.

    Progress is stored on your user id, so you can change channel, server, or
    finish in DMs. Staff must enable the cog per channel before server play.
    Romance fades to black and stays PG-13. Those scenes can still move to DMs.

    Start with `[p]witcher play`.
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=450450451, force_registration=True)
        self.config.register_user(
            state=None,
            saves={},
            mode="dm",
            romance_dm=False,
            adult=False,
            bind_channel=None,
            bind_guild=None,
            romance_gate=None,
        )
        self.config.register_guild(channels=[])
        self.campaign = Campaign(load_nodes())
        if self.campaign.problems:
            log.error("Witcher campaign graph: %s", self.campaign.problems[:8])

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        await self.config.user_from_id(user_id).clear()

    async def cog_load(self):
        # Slash romance entry is age-restricted by Discord. Prefix play still works.
        try:
            self.bot.tree.add_command(self.slash_scene)
        except Exception:
            log.warning("Could not register the age-restricted slash command.", exc_info=True)

    async def cog_unload(self):
        try:
            self.bot.tree.remove_command("witcher_scene", type=None)
        except Exception:
            log.debug("slash command already gone", exc_info=True)

    @app_commands.command(name="witcher_scene", description="Continue a fade-to-black scene.", nsfw=True)
    async def slash_scene(self, interaction: discord.Interaction):
        """Age-restricted continue. Discord hides this from accounts that are not adult."""
        await interaction.response.defer(ephemeral=True)
        await self.show(interaction.user, interaction=interaction, force=True)

    def _embed(self, node: dict, footer: str = "") -> discord.Embed:
        body = (node.get("text") or "").strip()
        if len(body) > 3900:
            body = body[:3890].rstrip() + "…"
        embed = discord.Embed(
            title=(node.get("title") or "The road")[:256],
            description=body,
            color=0x6B3A2A if not node.get("romance") else 0x7A3048,
        )
        banner = BANNERS.get(node.get("banner") or "inn", BANNERS["inn"])
        embed.set_author(name=banner.strip()[:256])
        if footer:
            embed.set_footer(text=footer[:2048])
        return embed

    async def _state(self, user: discord.abc.User) -> dict:
        state = await self.config.user(user).state()
        if not state or not state.get("node"):
            state = fresh_state()
            await self.config.user(user).state.set(state)
        state.setdefault("flags", {})
        state.setdefault("items", {})
        state.setdefault("log", [])
        state.setdefault("seen", [])
        return state

    async def _save(self, user: discord.abc.User, state: dict) -> None:
        await self.config.user(user).state.set(state)

    async def _enabled(self, guild: discord.Guild, channel_id: int) -> bool:
        channels = await self.config.guild(guild).channels()
        return channel_id in channels

    async def resolve_choice(self, user: discord.abc.User, number: int, interaction=None, ctx=None):
        try:
            state = await self._state(user)
            result = self.campaign.apply(state, number)
            if not result.get("ok"):
                await self._tell(user, result["error"], interaction=interaction, ctx=ctx)
                return
            if result.get("romance"):
                state["romance_gate"] = None
            await self._save(user, state)
            await self.show(user, interaction=interaction, ctx=ctx)
        except Exception:
            log.exception("choice failed for %s", user.id)
            await self._tell(user, "The page tore. Your place is unchanged if the save failed; try `[p]witcher look`.", interaction=interaction, ctx=ctx)

    async def show(self, user: discord.abc.User, interaction=None, ctx=None, force: bool = False):
        state = await self._state(user)
        try:
            node = self.campaign.get(state["node"])
        except Exception:
            state["node"] = state.get("last_rest") or "crossroads"
            await self._save(user, state)
            node = self.campaign.get(state["node"])
        if node.get("romance") and not force:
            allowed, why = await self._romance_allowed(user, ctx, interaction)
            if not allowed:
                await self._tell(user, why, interaction=interaction, ctx=ctx)
                return
        choices = self.campaign.visible_choices(state)
        footer = node.get("region") or ""
        if node.get("rest"):
            footer = (footer + " · rest point").strip(" ·")
        if node.get("ending"):
            footer = (footer + " · ending").strip(" ·")
        embed = self._embed(node, footer)
        extra = choice_block(choices) if choices else "_The scene is finished. `[p]witcher start` begins again._"
        view = ChoiceView(self, user.id, len(choices)) if choices else None
        await self._send(user, embed, extra, view, interaction=interaction, ctx=ctx, romance=bool(node.get("romance")))

    async def _romance_allowed(self, user, ctx, interaction) -> tuple[bool, str]:
        adult = await self.config.user(user).adult()
        if not adult:
            return False, (
                "This scene fades to black and stays PG-13. Confirm you are 18 or older with "
                "`[p]witcher adult`, or use `/witcher_scene`. Discord still hides that "
                "command from accounts it has not placed in the adult group."
            )
        romance_dm = await self.config.user(user).romance_dm()
        mode = await self.config.user(user).mode()
        gate = await self.config.user(user).romance_gate()
        if romance_dm or mode == "dm" or gate == "dm":
            return True, ""
        channel = None
        if ctx is not None and getattr(ctx, "guild", None):
            channel = ctx.channel
        if interaction is not None and getattr(interaction, "guild", None):
            channel = interaction.channel
        if channel is not None and getattr(channel, "nsfw", False):
            return True, ""
        if gate == "here" and channel is not None and getattr(channel, "nsfw", False):
            return True, ""
        return False, (
            "Romance fades to black. It can go to your DMs or stay in an age-restricted channel.\n"
            "`[p]witcher scene dm` moves this scene to DMs.\n"
            "`[p]witcher scene here` posts it only in an age-restricted channel."
        )

    async def _tell(self, user, text: str, interaction=None, ctx=None):
        try:
            if interaction is not None and not interaction.response.is_done():
                await interaction.response.send_message(text[:1900], ephemeral=True)
                return
            if interaction is not None:
                await interaction.followup.send(text[:1900], ephemeral=True)
                return
            if ctx is not None:
                await ctx.send(text[:1900])
                return
            await user.send(text[:1900])
        except discord.Forbidden:
            if ctx is not None:
                await ctx.send("I can't message you. Open your DMs or play in an enabled channel.")
        except discord.HTTPException:
            log.warning("Discord refused a short message for %s", user.id)

    async def _send(self, user, embed, extra, view, interaction=None, ctx=None, romance=False):
        mode = await self.config.user(user).mode()
        romance_dm = await self.config.user(user).romance_dm()
        gate = await self.config.user(user).romance_gate()
        use_dm = mode == "dm" or (romance and (romance_dm or gate == "dm"))
        try:
            if interaction is not None and not use_dm:
                send = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
                kwargs = {"embed": embed, "ephemeral": True}
                if view is not None:
                    kwargs["view"] = view
                await send(**kwargs)
                if extra:
                    await interaction.followup.send(extra[:1900], ephemeral=True)
                return
            if use_dm or ctx is None or ctx.guild is None:
                message = await user.send(embed=embed, view=view)
                if extra:
                    await user.send(extra[:1900])
                return message
            channel = ctx.channel
            bind_id = await self.config.user(user).bind_channel()
            bind_guild = await self.config.user(user).bind_guild()
            if bind_id and bind_guild and ctx.guild and ctx.guild.id == bind_guild:
                bound = ctx.guild.get_channel(bind_id)
                if bound is not None:
                    channel = bound
            if not await self._enabled(ctx.guild, channel.id):
                await ctx.send(
                    "Staff have not enabled this channel. Ask a mod to run `[p]witcherset enable` here, "
                    "or switch yourself to DMs with `[p]witcher mode dm`."
                )
                return
            await channel.send(embed=embed, view=view)
            if extra:
                await channel.send(extra[:1900])
        except discord.Forbidden:
            await self._tell(
                user,
                "I can't deliver that. Open DMs, or have staff enable this channel and give me permission to speak.",
                interaction=interaction,
                ctx=ctx,
            )
        except discord.HTTPException:
            log.warning("Discord rejected a scene for %s", user.id)
            await self._tell(user, "Discord refused the message. Try `[p]witcher look` once.", interaction=interaction, ctx=ctx)

    @commands.group(name="witcher", invoke_without_command=True)
    async def witcher(self, ctx: commands.Context):
        """Play the campaign. Progress follows your user id.

        Server channels do nothing until staff run `[p]witcherset enable`.
        DMs work without a channel toggle. Use `[p]witcher guide` for the road rules.
        """
        await ctx.send(
            "The road is open.\n"
            "`[p]witcher play` continues your scene.\n"
            "`[p]witcher choose 1` takes the first road.\n"
            "`[p]witcher mode dm` moves the whole game to your DMs.\n"
            "`[p]help witcher` lists every command."
        )

    @witcher.command(name="guide")
    async def guide(self, ctx: commands.Context):
        """Rules of the road, also summarized in `[p]help witcher`."""
        text = (
            "You are on a contract that became a family. Choices set flags on your user id, "
            "so the same game follows you across servers.\n\n"
            "Play: `[p]witcher play` then `[p]witcher choose 2`, or tap the button.\n"
            "Rest points mint a resume code. `[p]witcher rest` saves. `[p]witcher resume WH-XXX-XXX` loads it.\n"
            "Bag and crowns: `[p]witcher bag`.\n"
            "Whole game in DMs: `[p]witcher mode dm`. Back to a staff-enabled channel: `[p]witcher mode here` then `[p]witcher bind`.\n"
            "When a romance scene appears, it fades to black. `[p]witcher scene dm` keeps that page private. "
            "`[p]witcher scene here` only works in an age-restricted channel after `[p]witcher adult`.\n"
            "Staff: `[p]witcherset enable` in each channel that should host public play."
        )
        await ctx.send(text)

    @witcher.command(name="play", aliases=["look", "continue"])
    async def play(self, ctx: commands.Context):
        """Show the current scene and the roads out of it."""
        await self.show(ctx.author, ctx=ctx)

    @witcher.command(name="start")
    async def start(self, ctx: commands.Context):
        """Begin again at White Orchard. Does not delete named resume codes."""
        state = fresh_state()
        await self._save(ctx.author, state)
        await ctx.send("A new road. The old resume codes are still in your pocket.")
        await self.show(ctx.author, ctx=ctx)

    @witcher.command(name="choose", aliases=["c", "pick"])
    async def choose(self, ctx: commands.Context, number: int):
        """Take a numbered road from the current scene."""
        await self.resolve_choice(ctx.author, number, ctx=ctx)

    @witcher.command(name="bag", aliases=["inventory", "inv"])
    async def bag(self, ctx: commands.Context):
        """Crowns, potions, and whatever the road paid."""
        state = await self._state(ctx.author)
        items = state.get("items") or {}
        if not items:
            await ctx.send("Empty pockets. Familiar.")
            return
        lines = [f"{name}: {qty}" for name, qty in sorted(items.items())]
        await ctx.send(box("\n".join(lines)))

    @witcher.command(name="log")
    async def questlog(self, ctx: commands.Context):
        """The last things the road bothered to remember."""
        state = await self._state(ctx.author)
        notes = state.get("log") or ["Nothing written yet."]
        await ctx.send("\n".join(f"· {line}" for line in notes[-12:])[:1900])

    @witcher.command(name="map")
    async def travel_map(self, ctx: commands.Context):
        """List hubs you can ride to, then `[p]witcher ride <id>`."""
        state = await self._state(ctx.author)
        hubs = self.campaign.open_hubs(state)
        if not hubs:
            await ctx.send("No open hubs. Walk.")
            return
        lines = [f"`{node_id}` — {title}" for node_id, title in hubs]
        await ctx.send("Open fires:\n" + "\n".join(lines))

    @witcher.command(name="ride")
    async def ride(self, ctx: commands.Context, node_id: str):
        """Travel to an open hub by its id from `[p]witcher map`."""
        state = await self._state(ctx.author)
        error = self.campaign.travel(state, node_id.lower())
        if error:
            await ctx.send(error)
            return
        await self._save(ctx.author, state)
        await self.show(ctx.author, ctx=ctx)

    @witcher.command(name="rest")
    async def rest(self, ctx: commands.Context):
        """At a rest point, mint a resume code and snapshot the road."""
        state = await self._state(ctx.author)
        node = self.campaign.nodes.get(state.get("node") or "")
        if not node or not node.get("rest"):
            await ctx.send("This is not a rest point. Ride to an inn, a dock, or a keep.")
            return
        code = new_code()
        saves = await self.config.user(ctx.author).saves()
        saves[code] = snapshot(state)
        if len(saves) > 12:
            for old in list(saves)[:-12]:
                saves.pop(old, None)
        await self.config.user(ctx.author).saves.set(saves)
        await ctx.send(f"Rest taken. Resume code: `{code}`\nIt works in any server, and in DMs.")

    @witcher.command(name="resume")
    async def resume(self, ctx: commands.Context, code: str):
        """Load a resume code minted at a rest point."""
        saves = await self.config.user(ctx.author).saves()
        snap = saves.get(code.upper()) or saves.get(code)
        if not snap:
            await ctx.send("No such code in your pocket. Codes belong to the user who rested.")
            return
        await self._save(ctx.author, snap)
        await ctx.send(f"Loaded `{code.upper()}`.")
        await self.show(ctx.author, ctx=ctx)

    @witcher.command(name="saves")
    async def saves(self, ctx: commands.Context):
        """List your resume codes."""
        saves = await self.config.user(ctx.author).saves()
        if not saves:
            await ctx.send("No rest codes yet.")
            return
        await ctx.send("Codes: " + ", ".join(f"`{key}`" for key in saves))

    @witcher.command(name="mode")
    async def mode(self, ctx: commands.Context, where: str):
        """Play in `dm` or `here`. Here still needs a staff-enabled channel."""
        where = where.lower()
        if where not in {"dm", "here", "channel"}:
            await ctx.send("Use `dm` or `here`.")
            return
        await self.config.user(ctx.author).mode.set("dm" if where == "dm" else "channel")
        await ctx.send("The whole game will come to your DMs." if where == "dm" else "The game will post in enabled channels.")

    @witcher.command(name="bind")
    async def bind(self, ctx: commands.Context):
        """Use this channel for your server play, if staff enabled it."""
        if ctx.guild is None:
            await ctx.send("Bind a server channel. DMs need no bind.")
            return
        if not await self._enabled(ctx.guild, ctx.channel.id):
            await ctx.send("Staff have not enabled this channel.")
            return
        await self.config.user(ctx.author).bind_channel.set(ctx.channel.id)
        await self.config.user(ctx.author).bind_guild.set(ctx.guild.id)
        await self.config.user(ctx.author).mode.set("channel")
        await ctx.send("Bound. Your scenes in this server will land here.")

    @witcher.command(name="adult")
    async def adult(self, ctx: commands.Context):
        """Confirm you are 18 or older before romance scenes. A self-attestation, not an id check."""
        await self.config.user(ctx.author).adult.set(True)
        await ctx.send(
            "Noted. Romance scenes fade to black. They still prefer DMs, and Discord's "
            "age-restricted `/witcher_scene` command remains the platform gate."
        )

    @witcher.group(name="scene", invoke_without_command=True)
    async def scene(self, ctx: commands.Context):
        """Choose where a romance scene is delivered."""
        await ctx.send("When romance appears: `[p]witcher scene dm` or `[p]witcher scene here`.")

    @scene.command(name="dm")
    async def scene_dm(self, ctx: commands.Context):
        """Move romance scenes to your DMs."""
        if not await self.config.user(ctx.author).adult():
            await ctx.send("Confirm with `[p]witcher adult` first.")
            return
        await self.config.user(ctx.author).romance_dm.set(True)
        await self.config.user(ctx.author).romance_gate.set("dm")
        await ctx.send("Romance will come to your DMs.")
        await self.show(ctx.author, ctx=ctx, force=True)

    @scene.command(name="here")
    async def scene_here(self, ctx: commands.Context):
        """Post the romance scene here. Age-restricted channels only."""
        if ctx.guild is None:
            await ctx.send("This already is a DM.")
            await self.show(ctx.author, ctx=ctx, force=True)
            return
        if not getattr(ctx.channel, "nsfw", False):
            await ctx.send("Romance stays out of this channel. Use an age-restricted channel, or `[p]witcher scene dm`.")
            return
        if not await self._enabled(ctx.guild, ctx.channel.id):
            await ctx.send("Staff have not enabled this channel.")
            return
        if not await self.config.user(ctx.author).adult():
            await ctx.send("Confirm with `[p]witcher adult` first.")
            return
        await self.config.user(ctx.author).romance_dm.set(False)
        await self.config.user(ctx.author).romance_gate.set("here")
        await self.show(ctx.author, ctx=ctx, force=True)

    @commands.group(name="witcherset")
    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    async def witcherset(self, ctx: commands.Context):
        """Staff switches. Enable the campaign per channel."""

    @witcherset.command(name="enable")
    async def enable(self, ctx: commands.Context):
        """Let this channel host server play. Players can still use DMs without this."""
        async with self.config.guild(ctx.guild).channels() as channels:
            if ctx.channel.id not in channels:
                channels.append(ctx.channel.id)
        await ctx.send("This channel can host the road. Players still choose DMs if they want.")

    @witcherset.command(name="disable")
    async def disable(self, ctx: commands.Context):
        """Stop server play in this channel. Saved games are untouched."""
        async with self.config.guild(ctx.guild).channels() as channels:
            if ctx.channel.id in channels:
                channels.remove(ctx.channel.id)
        await ctx.send("Channel disabled. User saves remain.")

    @witcherset.command(name="list")
    async def list_channels(self, ctx: commands.Context):
        """Show channels where server play is allowed."""
        channels = await self.config.guild(ctx.guild).channels()
        if not channels:
            await ctx.send("No channels enabled.")
            return
        names = []
        for cid in channels:
            channel = ctx.guild.get_channel(cid)
            names.append(channel.mention if channel else str(cid))
        await ctx.send("Enabled: " + ", ".join(names))

    async def cog_command_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("That command needs the missing word. `[p]help witcher` lists them.")
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send("I couldn't read that. Choices are numbers. Resume codes look like `WH-ABC-DEF`.")
            return
        if isinstance(error, commands.CheckFailure):
            await ctx.send("Server staff have to run that.")
            return
        log.exception("witcher command failed", exc_info=error)
