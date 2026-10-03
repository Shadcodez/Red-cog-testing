"""Channel Connect Four for Red. One game per channel, one edited message.

Text board by default. Image board is optional and needs Pillow.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red

from .art import HAS_PIL, render_board
from .board import (
    EMPTY,
    HEIGHT,
    RED,
    WIDTH,
    YELLOW,
    choose,
    clone,
    drop,
    is_draw,
    new_board,
    open_cols,
    winning_cells,
)

IDLE = 45 * 60
BOT_NAME = "Cog-800"
ACCENT = 0xE74C3C
GOLD = 0xF1C40F
Cell = Tuple[int, int]
DISC = {RED: "Red", YELLOW: "Yellow"}
GLYPH = {EMPTY: "⬜", RED: "🔴", YELLOW: "🟡"}
LAST = {RED: "🟥", YELLOW: "🟨"}


@dataclass
class Session:
    channel_id: int
    guild_id: int
    red_id: int
    yellow_id: int
    names: Dict[int, str]
    board: list
    turn: int = RED
    strength: str = "normal"
    bot_side: int = 0
    image: bool = False
    ping: bool = True
    last_cell: Optional[Cell] = None
    win: List[Cell] = field(default_factory=list)
    moves: int = 0
    message: Optional[discord.Message] = None
    view: Optional[discord.ui.View] = None
    last: float = field(default_factory=time.time)
    over: str = ""

    def touch(self) -> None:
        self.last = time.time()

    def side_id(self, side: int) -> int:
        return self.red_id if side == RED else self.yellow_id

    def side_name(self, side: int) -> str:
        return self.names.get(self.side_id(side), DISC[side])

    def user_side(self, uid: int) -> int:
        if uid == self.red_id:
            return RED
        if uid == self.yellow_id:
            return YELLOW
        return 0


class ConnectFour(commands.Cog):
    """Channel Connect Four against a member or Cog-800."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=8844220714, force_registration=True)
        self.config.register_guild(image_mode=False, ping=True)
        self.games: Dict[int, Session] = {}
        self.task: Optional[asyncio.Task] = None

    async def cog_load(self) -> None:
        self.task = asyncio.create_task(self._sweep())

    async def cog_unload(self) -> None:
        if self.task:
            self.task.cancel()
        for session in list(self.games.values()):
            if session.view:
                session.view.stop()
        self.games.clear()

    async def _sweep(self) -> None:
        try:
            while True:
                await asyncio.sleep(60)
                now = time.time()
                for channel_id, session in list(self.games.items()):
                    if now - session.last <= IDLE or session.over:
                        continue
                    self._drop(session)
                    if session.message:
                        try:
                            await session.message.edit(
                                content="This game expired after 45 minutes idle.",
                                view=None,
                                attachments=[],
                            )
                        except discord.HTTPException:
                            pass
        except asyncio.CancelledError:
            return

    def bind(self, session: Session, view: Optional[discord.ui.View]) -> Optional[discord.ui.View]:
        if session.view:
            session.view.stop()
        session.view = view
        return view

    def _drop(self, session: Session) -> None:
        if session.view:
            session.view.stop()
        self.games.pop(session.channel_id, None)

    @commands.hybrid_group(name="connectfour", aliases=["c4"])
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True, send_messages=True)
    async def connectfour(self, ctx: commands.Context) -> None:
        """Play Connect Four in this channel."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @connectfour.command(name="bot")
    @discord.app_commands.describe(strength="How hard Cog-800 plays", color="Your disc color")
    @discord.app_commands.choices(
        strength=[
            discord.app_commands.Choice(name="easy", value="easy"),
            discord.app_commands.Choice(name="normal", value="normal"),
            discord.app_commands.Choice(name="hard", value="hard"),
        ],
        color=[
            discord.app_commands.Choice(name="red", value="red"),
            discord.app_commands.Choice(name="yellow", value="yellow"),
            discord.app_commands.Choice(name="random", value="random"),
        ],
    )
    async def vs_bot(self, ctx: commands.Context, strength: str = "normal", color: str = "red") -> None:
        """Play Cog-800. Strength: easy, normal, hard. Color: red, yellow, random."""
        if not await self._occupy(ctx):
            return
        strength = strength.lower()
        color = color.lower()
        if strength not in ("easy", "normal", "hard") or color not in ("red", "yellow", "random"):
            await ctx.send("Use strength easy, normal, or hard, and color red, yellow, or random.")
            return
        want = random.choice(("red", "yellow")) if color == "random" else color
        human = ctx.author.id
        bot_id = self.bot.user.id
        red_id = human if want == "red" else bot_id
        yellow_id = human if want == "yellow" else bot_id
        session = Session(
            channel_id=ctx.channel.id,
            guild_id=ctx.guild.id,
            red_id=red_id,
            yellow_id=yellow_id,
            names={human: ctx.author.display_name, bot_id: BOT_NAME},
            board=new_board(),
            strength=strength,
            bot_side=YELLOW if want == "red" else RED,
            image=await self.config.guild(ctx.guild).image_mode(),
            ping=await self.config.guild(ctx.guild).ping(),
        )
        self.games[ctx.channel.id] = session
        view = self.bind(session, BoardView(self, session)) if session.turn != session.bot_side else None
        await self.send_board(ctx, session, view)
        if session.turn == session.bot_side:
            await self._engine_move(session)

    @connectfour.command(name="challenge")
    @discord.app_commands.describe(opponent="Member to challenge")
    async def challenge(self, ctx: commands.Context, opponent: discord.Member) -> None:
        """Challenge a member. You play Red and drop first."""
        if opponent.bot:
            await ctx.send(f"Use `{ctx.clean_prefix}connectfour bot` to play Cog-800.")
            return
        if opponent.id == ctx.author.id:
            await ctx.send("Pick someone else.")
            return
        if not await self._occupy(ctx):
            return
        session = Session(
            channel_id=ctx.channel.id,
            guild_id=ctx.guild.id,
            red_id=ctx.author.id,
            yellow_id=opponent.id,
            names={ctx.author.id: ctx.author.display_name, opponent.id: opponent.display_name},
            board=new_board(),
            image=await self.config.guild(ctx.guild).image_mode(),
            ping=await self.config.guild(ctx.guild).ping(),
        )
        self.games[ctx.channel.id] = session
        view = self.bind(session, AcceptView(self, session))
        embed = discord.Embed(
            title="Connect Four",
            description=f"{ctx.author.display_name} challenged {opponent.display_name}.\nAccept to play Yellow. Red drops first.",
            color=ACCENT,
        )
        embed.set_footer(text="SHADOW · offer expires in 2 minutes")
        content = f"{opponent.mention} you have been challenged."
        mentions = discord.AllowedMentions(users=[opponent])
        if ctx.interaction:
            await ctx.interaction.response.send_message(content, embed=embed, view=view, allowed_mentions=mentions)
            session.message = await ctx.interaction.original_response()
        else:
            session.message = await ctx.send(content, embed=embed, view=view, allowed_mentions=mentions)

    @connectfour.command(name="surrender", aliases=["resign"])
    async def surrender_cmd(self, ctx: commands.Context) -> None:
        """Give the game to the other side."""
        session = self.games.get(ctx.channel.id)
        if session is None or session.over or not session.user_side(ctx.author.id):
            await ctx.send("You have no Connect Four game here.")
            return
        await self.finish(session, f"{ctx.author.display_name} surrendered. {self._other_name(session, ctx.author.id)} wins.")

    @connectfour.command(name="mode")
    @commands.admin_or_permissions(manage_guild=True)
    async def mode(self, ctx: commands.Context, style: str) -> None:
        """Set the default board: text or image."""
        style = style.lower()
        if style not in ("text", "image"):
            await ctx.send("Mode is text or image.")
            return
        if style == "image" and not HAS_PIL:
            await ctx.send("Image boards need Pillow. Update the repo and run cog install again.")
            return
        await self.config.guild(ctx.guild).image_mode.set(style == "image")
        await ctx.send(f"Connect Four boards default to {style}.")

    @connectfour.command(name="ping")
    @commands.admin_or_permissions(manage_guild=True)
    async def ping(self, ctx: commands.Context, enabled: bool) -> None:
        """Ping the player whose turn it is."""
        await self.config.guild(ctx.guild).ping.set(enabled)
        await ctx.send("Turn pings on." if enabled else "Turn pings off.")

    async def _occupy(self, ctx: commands.Context) -> bool:
        session = self.games.get(ctx.channel.id)
        if session is None:
            return True
        await ctx.send("This channel already has a Connect Four game. Surrender it or wait for it to expire.")
        return False

    async def begin_human(self, interaction: discord.Interaction, session: Session) -> None:
        session.touch()
        view = self.bind(session, BoardView(self, session))
        await self.edit_board(interaction, session, view, notice=True)

    def text_board(self, session: Session) -> str:
        lines = ["1️⃣ 2️⃣ 3️⃣ 4️⃣ 5️⃣ 6️⃣ 7️⃣"]
        win = set(session.win)
        for row in range(HEIGHT - 1, -1, -1):
            cells = []
            for col in range(WIDTH):
                disc = session.board[col][row]
                if (col, row) in win or session.last_cell == (col, row):
                    cells.append(LAST.get(disc, GLYPH[disc]))
                else:
                    cells.append(GLYPH[disc])
            lines.append(" ".join(cells))
        return "\n".join(lines)

    def payload(self, session: Session, over: str = ""):
        side = session.turn
        color = GOLD if side == YELLOW else ACCENT
        if over:
            color = 0x2ECC71
        title = "Connect Four"
        if session.strength and session.bot_side:
            title += f" · {session.strength}"
        embed = discord.Embed(title=title, color=color)
        file = None
        if session.image and HAS_PIL:
            subtitle = over or f"{session.side_name(side)} to drop"
            buf = render_board(
                session.board,
                last=session.last_cell,
                win=session.win,
                title=title,
                subtitle=subtitle[:80],
            )
            file = discord.File(buf, filename="connectfour.png")
            embed.set_image(url="attachment://connectfour.png")
        else:
            embed.description = self.text_board(session)
        red = session.side_name(RED)
        yellow = session.side_name(YELLOW)
        embed.add_field(name="Players", value=f"🔴 {red}\n🟡 {yellow}", inline=False)
        if over:
            embed.add_field(name="Result", value=over[:1024], inline=False)
            embed.set_footer(text="SHADOW · session cleared")
        else:
            mode = "image" if session.image and HAS_PIL else "text"
            embed.set_footer(text=f"{session.side_name(side)} to drop · column buttons · {mode} board · SHADOW")
        return embed, file

    def turn_ping(self, session: Session, enabled: bool):
        if not enabled or not session.ping or session.over:
            return "", discord.AllowedMentions.none()
        uid = session.side_id(session.turn)
        if not uid or uid == session.side_id(session.bot_side):
            return "", discord.AllowedMentions.none()
        return f"<@{uid}> your drop.", discord.AllowedMentions(users=[discord.Object(id=uid)])

    async def send_board(self, ctx: commands.Context, session: Session, view: Optional[discord.ui.View]) -> None:
        embed, file = self.payload(session)
        content, mentions = self.turn_ping(session, True)
        kwargs = {"embed": embed, "view": view, "allowed_mentions": mentions}
        if file:
            kwargs["file"] = file
        if content:
            kwargs["content"] = content
        if ctx.interaction:
            await ctx.interaction.response.send_message(**kwargs)
            session.message = await ctx.interaction.original_response()
        else:
            session.message = await ctx.send(**kwargs)

    async def edit_board(
        self,
        source,
        session: Session,
        view: Optional[discord.ui.View],
        over: str = "",
        notice: bool = False,
    ) -> None:
        embed, file = self.payload(session, over)
        kwargs = {"embed": embed, "view": view, "attachments": [file] if file else []}
        if notice or over:
            content, mentions = self.turn_ping(session, notice and not over)
            kwargs["content"] = content
            kwargs["allowed_mentions"] = mentions
        message = session.message
        interaction = source if isinstance(source, discord.Interaction) else None
        if interaction is not None:
            same = interaction.message is not None and message is not None and interaction.message.id == message.id
            if same and not interaction.response.is_done():
                await interaction.response.edit_message(**kwargs)
                return
            if not interaction.response.is_done():
                await interaction.response.defer()
        if message:
            try:
                await message.edit(**kwargs)
            except discord.HTTPException:
                pass

    async def drop_disc(self, interaction: discord.Interaction, session: Session, col: int) -> None:
        if session.over or session.channel_id not in self.games:
            await interaction.response.send_message("That game is already over.", ephemeral=True)
            return
        side = session.user_side(interaction.user.id)
        if side != session.turn or side == session.bot_side:
            await interaction.response.send_message("Not your drop.", ephemeral=True)
            return
        if col not in open_cols(session.board):
            await interaction.response.send_message("That column is full.", ephemeral=True)
            return
        await interaction.response.defer()
        self._apply(session, col, side)
        reason = self._result(session)
        if reason:
            await self.finish(session, reason, interaction)
            return
        view = self.bind(session, BoardView(self, session))
        if session.turn == session.bot_side:
            view = self.bind(session, None)
        await self.edit_board(interaction, session, view, notice=True)
        if session.turn == session.bot_side:
            await self._engine_move(session)

    def _apply(self, session: Session, col: int, side: int) -> None:
        row = drop(session.board, col, side)
        session.last_cell = (col, row)
        session.moves += 1
        session.turn = YELLOW if side == RED else RED
        session.touch()
        cells = winning_cells(session.board, col, row)
        if cells:
            session.win = cells

    def _result(self, session: Session) -> str:
        if session.win:
            winner = session.board[session.win[0][0]][session.win[0][1]]
            return f"Four in a row. {session.side_name(winner)} wins."
        if is_draw(session.board):
            return "Board full. Draw."
        return ""

    async def _engine_move(self, session: Session) -> None:
        if session.over or session.turn != session.bot_side:
            return
        board = clone(session.board)
        side = session.bot_side
        strength = session.strength
        try:
            col = await asyncio.to_thread(choose, board, side, strength, random.Random())
        except Exception:
            legal = open_cols(session.board)
            col = legal[0] if legal else 0
        if session.channel_id not in self.games or session.over:
            return
        self._apply(session, col, side)
        reason = self._result(session)
        if reason:
            await self.finish(session, reason)
            return
        view = self.bind(session, BoardView(self, session))
        await self.edit_board(session.message, session, view, notice=True)

    async def finish(self, session: Session, reason: str, interaction: Optional[discord.Interaction] = None) -> None:
        session.over = reason
        self._drop(session)
        await self.edit_board(interaction or session.message, session, None, over=reason)

    def _other_name(self, session: Session, uid: int) -> str:
        other = session.yellow_id if uid == session.red_id else session.red_id
        return session.names.get(other, "the other side")

    async def decline(self, interaction: discord.Interaction, session: Session) -> None:
        self._drop(session)
        embed = discord.Embed(title="Connect Four", description="Challenge declined.", color=ACCENT)
        if not interaction.response.is_done():
            await interaction.response.edit_message(content="", embed=embed, view=None, attachments=[])
        elif session.message:
            await session.message.edit(content="", embed=embed, view=None, attachments=[])


class DropButton(discord.ui.Button):
    def __init__(self, col: int, disabled: bool):
        super().__init__(
            label=str(col + 1),
            style=discord.ButtonStyle.primary,
            row=0 if col < 4 else 1,
            disabled=disabled,
        )
        self.col = col

    async def callback(self, interaction: discord.Interaction) -> None:
        view: BoardView = self.view
        await view.cog.drop_disc(interaction, view.session, self.col)


class BoardView(discord.ui.View):
    def __init__(self, cog: ConnectFour, session: Session):
        super().__init__(timeout=None)
        self.cog = cog
        self.session = session
        legal = set(open_cols(session.board))
        for col in range(WIDTH):
            self.add_item(DropButton(col, col not in legal))

    @discord.ui.button(label="Board style", style=discord.ButtonStyle.secondary, row=2)
    async def style(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.session.user_side(interaction.user.id):
            await interaction.response.send_message("You are not in this game.", ephemeral=True)
            return
        if not self.session.image and not HAS_PIL:
            await interaction.response.send_message("Image boards need Pillow.", ephemeral=True)
            return
        self.session.image = not self.session.image
        self.session.touch()
        await self.cog.edit_board(interaction, self.session, self, notice=False)

    @discord.ui.button(label="Surrender", style=discord.ButtonStyle.danger, row=2)
    async def surrender(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.session.user_side(interaction.user.id):
            await interaction.response.send_message("You are not in this game.", ephemeral=True)
            return
        name = interaction.user.display_name
        other = self.cog._other_name(self.session, interaction.user.id)
        await self.cog.finish(self.session, f"{name} surrendered. {other} wins.", interaction)


class AcceptView(discord.ui.View):
    def __init__(self, cog: ConnectFour, session: Session):
        super().__init__(timeout=120)
        self.cog = cog
        self.session = session

    async def on_timeout(self) -> None:
        if self.session.channel_id not in self.cog.games or self.session.moves:
            return
        self.cog._drop(self.session)
        if self.session.message:
            try:
                await self.session.message.edit(content="Challenge expired.", embed=None, view=None, attachments=[])
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.session.yellow_id:
            await interaction.response.send_message("This challenge is not for you.", ephemeral=True)
            return
        await self.cog.begin_human(interaction, self.session)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in (self.session.red_id, self.session.yellow_id):
            await interaction.response.send_message("This challenge is not for you.", ephemeral=True)
            return
        await self.cog.decline(interaction, self.session)
