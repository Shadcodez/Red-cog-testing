"""Channel battleship for Red. One game per channel, one edited message.

Text chart by default. Image chart is optional and needs Pillow.
Hulls stay hidden on the public board until that ship is sunk.
"""

from __future__ import annotations

import asyncio
import io
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red

from .art import HAS_PIL, render_boards

Cell = Tuple[int, int]
COLS = "ABCDEFGHIJ"
SPECS = (
    ("Carrier", "C", 5),
    ("Battleship", "B", 4),
    ("Cruiser", "R", 3),
    ("Submarine", "S", 3),
    ("Destroyer", "D", 2),
)
IDLE = 45 * 60
BOT_NAME = "Cog-800"


def parse_coord(text: str) -> Optional[Cell]:
    raw = text.strip().upper().replace(" ", "")
    if len(raw) < 2:
        return None
    if raw[0] in COLS and raw[1:].isdigit():
        col, row = COLS.index(raw[0]), int(raw[1:]) - 1
    elif raw[-1] in COLS and raw[:-1].isdigit():
        col, row = COLS.index(raw[-1]), int(raw[:-1]) - 1
    else:
        return None
    if 0 <= col < 10 and 0 <= row < 10:
        return col, row
    return None


def label(cell: Cell) -> str:
    return f"{COLS[cell[0]]}{cell[1] + 1}"


@dataclass
class Ship:
    name: str
    mark: str
    length: int
    cells: List[Cell] = field(default_factory=list)

    @property
    def placed(self) -> bool:
        return len(self.cells) == self.length


@dataclass
class Fleet:
    ships: List[Ship] = field(default_factory=list)
    hits: set = field(default_factory=set)

    @classmethod
    def empty(cls) -> "Fleet":
        return cls([Ship(n, m, length) for n, m, length in SPECS])

    def occupied(self, skip: Optional[int] = None) -> set:
        taken = set()
        for i, ship in enumerate(self.ships):
            if i == skip:
                continue
            taken.update(ship.cells)
        return taken

    def place(self, index: int, col: int, row: int, horizontal: bool) -> Optional[str]:
        ship = self.ships[index]
        cells = []
        for step in range(ship.length):
            c = col + step if horizontal else col
            r = row if horizontal else row + step
            if not (0 <= c < 10 and 0 <= r < 10):
                return f"{ship.name} runs off the chart."
            cells.append((c, r))
        clash = self.occupied(skip=index)
        if any(cell in clash for cell in cells):
            return f"{ship.name} overlaps another hull."
        ship.cells = cells
        return None

    def clear(self, index: int) -> None:
        self.ships[index].cells = []

    def _origin(self, index: int) -> Optional[Tuple[int, int, bool]]:
        ship = self.ships[index]
        if not ship.placed:
            return None
        cols = [c for c, _ in ship.cells]
        rows = [r for _, r in ship.cells]
        return min(cols), min(rows), max(cols) != min(cols)

    def nudge(self, index: int, dc: int, dr: int) -> Optional[str]:
        origin = self._origin(index)
        if origin is None:
            return f"{self.ships[index].name} is not on the chart yet. Place it first."
        col, row, horizontal = origin
        return self.place(index, col + dc, row + dr, horizontal)

    def spin(self, index: int) -> Optional[str]:
        origin = self._origin(index)
        if origin is None:
            return None
        col, row, horizontal = origin
        return self.place(index, col, row, not horizontal)

    def ready(self) -> bool:
        return all(ship.placed for ship in self.ships)

    def roll(self, rng: random.Random) -> None:
        for ship in self.ships:
            ship.cells = []
        for index, ship in enumerate(self.ships):
            for _ in range(80):
                horizontal = rng.choice((True, False))
                col = rng.randrange(10 - ship.length + 1) if horizontal else rng.randrange(10)
                row = rng.randrange(10) if horizontal else rng.randrange(10 - ship.length + 1)
                if self.place(index, col, row, horizontal) is None:
                    break

    def ship_at(self, cell: Cell) -> Optional[Ship]:
        for ship in self.ships:
            if cell in ship.cells:
                return ship
        return None

    def receive(self, cell: Cell) -> str:
        """Return miss, hit, or sunk. Caller must reject repeats."""
        ship = self.ship_at(cell)
        if ship is None:
            return "miss"
        self.hits.add(cell)
        if all(part in self.hits for part in ship.cells):
            return "sunk"
        return "hit"

    def sunk_names(self) -> List[str]:
        return [ship.name for ship in self.ships if ship.placed and all(c in self.hits for c in ship.cells)]

    def afloat(self) -> int:
        return sum(1 for ship in self.ships if ship.placed and not all(c in self.hits for c in ship.cells))

    def lost(self) -> bool:
        return self.ready() and self.afloat() == 0


@dataclass
class Session:
    channel_id: int
    guild_id: int
    players: List[int]
    names: Dict[int, str]
    bot_id: Optional[int] = None
    strength: str = "normal"
    phase: str = "challenge"
    fleets: Dict[int, Fleet] = field(default_factory=dict)
    locked: set = field(default_factory=set)
    shots: Dict[int, List[dict]] = field(default_factory=dict)
    turn: int = 0
    message: Optional[discord.Message] = None
    view: Optional[discord.ui.View] = None
    log: List[str] = field(default_factory=list)
    aim_col: Dict[int, int] = field(default_factory=dict)
    aim_row: Dict[int, int] = field(default_factory=dict)
    horizontal: Dict[int, bool] = field(default_factory=dict)
    ship_pick: Dict[int, int] = field(default_factory=dict)
    last: float = field(default_factory=time.time)
    winner: Optional[int] = None
    image: Optional[bool] = None
    ping: bool = True
    dms: Dict[int, discord.Message] = field(default_factory=dict)

    def touch(self) -> None:
        self.last = time.time()

    def opponent(self, uid: int) -> int:
        return self.players[1] if uid == self.players[0] else self.players[0]

    def name(self, uid: int) -> str:
        return self.names.get(uid, "Unknown")


class Battleship(commands.Cog):
    """Channel battleship against a member or Cog-800."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=8844220617, force_registration=True)
        self.config.register_guild(ping=True)
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
                    if now - session.last > IDLE:
                        self.games.pop(channel_id, None)
                        if session.view:
                            session.view.stop()
                        if session.message:
                            try:
                                await session.message.edit(content="This battle expired after 45 minutes idle.", view=None, attachments=[])
                            except discord.HTTPException:
                                pass
        except asyncio.CancelledError:
            return

    def bind(self, session: Session, view: discord.ui.View) -> discord.ui.View:
        if session.view:
            session.view.stop()
        session.view = view
        return view

    @commands.hybrid_group(name="battleship", aliases=["sbs"])
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True, send_messages=True, attach_files=True)
    async def battleship(self, ctx: commands.Context) -> None:
        """Play battleship in this channel."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @battleship.command(name="bot")
    @discord.app_commands.describe(strength="How hard Cog-800 hunts")
    async def vs_bot(self, ctx: commands.Context, strength: str = "normal") -> None:
        """Fight Cog-800. Strength: easy, normal, or hard."""
        strength = strength.lower()
        if strength not in ("easy", "normal", "hard"):
            await ctx.send("Strength is easy, normal, or hard.")
            return
        if not HAS_PIL:
            await ctx.send("Battleship needs Pillow. Update the repo and run cog install again, or install Pillow in the bot venv.")
            return
        if not await self._occupy(ctx):
            return
        bot_id = self.bot.user.id
        session = Session(
            channel_id=ctx.channel.id,
            guild_id=ctx.guild.id,
            players=[ctx.author.id, bot_id],
            names={ctx.author.id: ctx.author.display_name, bot_id: BOT_NAME},
            bot_id=bot_id,
            strength=strength,
            phase="deploy",
            turn=ctx.author.id,
            ping=await self.config.guild(ctx.guild).ping(),
        )
        rng = random.Random()
        human = Fleet.empty()
        human.roll(rng)
        machine = Fleet.empty()
        machine.roll(rng)
        session.fleets = {ctx.author.id: human, bot_id: machine}
        session.locked.add(bot_id)
        session.shots = {ctx.author.id: [], bot_id: []}
        self.games[ctx.channel.id] = session
        await self.publish(ctx, session, f"{ctx.author.display_name} vs {BOT_NAME} ({strength}). Place or move ships in your DMs, then lock in.")
        await self.mail_setup(session)

    @battleship.command(name="challenge")
    @discord.app_commands.describe(opponent="Member to invite")
    async def challenge(self, ctx: commands.Context, opponent: discord.Member) -> None:
        """Challenge another member."""
        if opponent.bot or opponent.id == ctx.author.id:
            await ctx.send("Challenge a member, or use `battleship bot` for Cog-800.")
            return
        if not HAS_PIL:
            await ctx.send("Battleship needs Pillow. Update the repo and run cog install again, or install Pillow in the bot venv.")
            return
        if not await self._occupy(ctx):
            return
        session = Session(
            channel_id=ctx.channel.id,
            guild_id=ctx.guild.id,
            players=[ctx.author.id, opponent.id],
            names={ctx.author.id: ctx.author.display_name, opponent.id: opponent.display_name},
            phase="challenge",
            ping=await self.config.guild(ctx.guild).ping(),
        )
        self.games[ctx.channel.id] = session
        view = self.bind(session, AcceptView(self, session))
        content = f"{opponent.mention}, {ctx.author.display_name} challenged you to battleship."
        session.message = await ctx.send(content, view=view)

    @battleship.command(name="surrender", aliases=["resign"])
    async def surrender_cmd(self, ctx: commands.Context) -> None:
        """Surrender the battle in this channel."""
        session = self.games.get(ctx.channel.id)
        if not session or ctx.author.id not in session.players:
            await ctx.send("You have no battle in this channel.")
            return
        await self.surrender(session, ctx.author.id)

    @battleship.command(name="ping")
    @commands.admin_or_permissions(manage_guild=True)
    async def ping(self, ctx: commands.Context, enabled: bool) -> None:
        """Ping the player whose shot it is."""
        await self.config.guild(ctx.guild).ping.set(enabled)
        await ctx.send("Turn pings on." if enabled else "Turn pings off.")

    async def _occupy(self, ctx: commands.Context) -> bool:
        if ctx.channel.id in self.games:
            await ctx.send("This channel already has a game or a pending challenge.")
            return False
        return True

    async def begin_human(self, interaction: discord.Interaction, session: Session) -> None:
        rng = random.Random()
        for uid in session.players:
            fleet = Fleet.empty()
            fleet.roll(rng)
            session.fleets[uid] = fleet
            session.shots[uid] = []
        session.phase = "deploy"
        session.turn = session.players[0]
        await self.publish(interaction, session, "Both fleets are pre-deployed. Place or move ships in your DMs, then lock in.")
        await self.mail_setup(session)

    def _panel(self, session: Session, owner: int, show_hulls: bool) -> dict:
        fleet = session.fleets.get(owner)
        shots = []
        for uid in session.players:
            if uid == owner:
                continue
            shots = session.shots.get(uid, [])
        ships = []
        afloat = ""
        if fleet:
            for ship in fleet.ships:
                sunk = ship.placed and all(c in fleet.hits for c in ship.cells)
                ships.append({
                    "cells": list(ship.cells),
                    "sunk": sunk,
                    "show": show_hulls or sunk,
                    "mark": ship.mark,
                })
            sunk = [ship.name for ship in fleet.ships if ship.placed and all(c in fleet.hits for c in ship.cells)]
            afloat = "Sunk: " + (", ".join(sunk) if sunk else "none")
        accent = (212, 175, 98) if owner == session.players[0] else (176, 92, 74)
        return {
            "heading": f"{session.name(owner).upper()}  ·  OCEAN",
            "ships": ships,
            "shots": shots,
            "show_hulls": show_hulls,
            "accent": accent,
            "afloat": afloat,
        }

    def _embed(self, session: Session, notice: str) -> discord.Embed:
        color = 0xC9A227 if session.winner else 0x14344E
        title = "Battleship"
        if session.winner:
            title = f"{session.name(session.winner)} wins"
        embed = discord.Embed(title=title, description=notice[:300], color=color)
        if session.phase == "battle":
            embed.add_field(name="To fire", value=session.name(session.turn), inline=True)
        elif session.phase == "deploy":
            waiting = [session.name(uid) for uid in session.players if uid not in session.locked]
            embed.add_field(name="Locking in", value=", ".join(waiting) or "ready", inline=True)
        if session.log:
            embed.add_field(name="Last shots", value="\n".join(session.log[-4:])[:1000], inline=False)
        embed.set_footer(text="A hit shoots again. Sunk hulls stay on the chart. My fleet is private.")
        return embed

    async def _chart(self, session: Session, notice: str, reveal: bool) -> discord.File:
        panels = [self._panel(session, uid, show_hulls=reveal) for uid in session.players]
        subtitle = notice if session.phase == "done" else f"To fire: {session.name(session.turn)}"
        png = await asyncio.to_thread(
            render_boards, panels, "BATTLESHIP", subtitle,
            "Public chart. Hulls appear only when sunk." if not reveal else "Action complete. Hulls revealed.",
        )
        return discord.File(io.BytesIO(png), filename="battleship.png")

    async def publish(self, source, session: Session, notice: str) -> None:
        session.touch()
        view = None
        if session.phase == "deploy":
            view = self.bind(session, DeployChannelView(self, session))
        elif session.phase == "battle":
            view = self.bind(session, BattleView(self, session))
        content = ""
        if session.ping and session.phase == "battle":
            content = f"<@{session.turn}> your shot."
        embed = self._embed(session, notice)
        file = None
        if session.phase in ("battle", "done"):
            file = await self._chart(session, notice, reveal=session.phase == "done")
            embed.set_image(url="attachment://battleship.png")
        await self._send(source, session, content, embed, view, file)

    async def _send(self, source, session: Session, content: str, embed: discord.Embed, view, file) -> None:
        kwargs = {"content": content or None, "embed": embed, "view": view}
        if file:
            kwargs["attachments"] = [file]
        else:
            kwargs["attachments"] = []
        if session.message:
            try:
                await session.message.edit(**kwargs)
                return
            except discord.HTTPException:
                session.message = None
        channel = source.channel if hasattr(source, "channel") else getattr(source, "channel", None)
        if channel is None and isinstance(source, discord.Interaction):
            channel = source.channel
        if file:
            session.message = await channel.send(content=content or None, embed=embed, view=view, file=file)
        else:
            session.message = await channel.send(content=content or None, embed=embed, view=view)

    async def finish(self, session: Session, reason: str, winner: Optional[int]) -> None:
        session.phase = "done"
        session.winner = winner
        session.log.append(reason)
        self.games.pop(session.channel_id, None)
        if session.view:
            session.view.stop()
            session.view = None
        embed = self._embed(session, reason)
        file = await self._chart(session, reason, reveal=True)
        embed.set_image(url="attachment://battleship.png")
        if session.message:
            try:
                await session.message.edit(
                    content=reason,
                    embed=embed,
                    view=None,
                    attachments=[file] if file else [],
                )
            except discord.HTTPException:
                pass

    def _ai_shot(self, session: Session) -> Cell:
        bot_id = session.bot_id
        target = session.fleets[session.opponent(bot_id)]
        fired = {tuple(s["cell"]) for s in session.shots[bot_id]}
        open_cells = [(c, r) for r in range(10) for c in range(10) if (c, r) not in fired]
        rng = random.Random()
        if session.strength == "easy" or not open_cells:
            return rng.choice(open_cells)
        unsunk_hits = [
            cell for cell in target.hits
            if (ship := target.ship_at(cell)) and not all(part in target.hits for part in ship.cells)
        ]
        neighbors = []
        for c, r in unsunk_hits:
            for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nxt = (c + dc, r + dr)
                if nxt in open_cells:
                    neighbors.append(nxt)
        if neighbors and session.strength != "hard":
            return rng.choice(neighbors)
        if session.strength == "hard":
            return self._density(target, fired, unsunk_hits)
        parity = [cell for cell in open_cells if (cell[0] + cell[1]) % 2 == 0]
        return rng.choice(parity or open_cells)

    def _density(self, fleet: Fleet, fired: set, unsunk_hits: Sequence[Cell]) -> Cell:
        scores = [[0] * 10 for _ in range(10)]
        misses = fired - fleet.hits
        remaining = [ship.length for ship in fleet.ships if not all(c in fleet.hits for c in ship.cells)]
        for length in remaining:
            for horizontal in (True, False):
                for row in range(10):
                    for col in range(10):
                        cells = []
                        ok = True
                        for step in range(length):
                            c = col + step if horizontal else col
                            r = row if horizontal else row + step
                            if not (0 <= c < 10 and 0 <= r < 10) or (c, r) in misses:
                                ok = False
                                break
                            cells.append((c, r))
                        if not ok:
                            continue
                        for c, r in cells:
                            if (c, r) not in fired:
                                scores[r][c] += 1
        best = None
        best_score = -1
        for r in range(10):
            for c in range(10):
                if (c, r) in fired:
                    continue
                score = scores[r][c]
                if any(abs(c - hc) + abs(r - hr) == 1 for hc, hr in unsunk_hits):
                    score += 40
                if score > best_score:
                    best_score = score
                    best = (c, r)
        return best or next(iter((c, r) for r in range(10) for c in range(10) if (c, r) not in fired))

    async def fire(self, interaction: discord.Interaction, session: Session, cell: Cell) -> None:
        if session.phase != "battle" or interaction.user.id != session.turn:
            await interaction.response.send_message("It is not your shot.", ephemeral=True)
            return
        attacker = interaction.user.id
        if any(tuple(s["cell"]) == cell for s in session.shots[attacker]):
            await interaction.response.send_message(f"{label(cell)} was already fired.", ephemeral=True)
            return
        await interaction.response.defer()
        await self._resolve(session, attacker, cell)
        if session.phase == "done":
            return
        if session.bot_id and session.turn == session.bot_id:
            await self.publish(interaction, session, session.log[-1])
            shots = 0
            while session.channel_id in self.games and session.phase == "battle" and session.turn == session.bot_id and shots < 16:
                await asyncio.sleep(1.1)
                if session.channel_id not in self.games:
                    return
                await self._resolve(session, session.bot_id, self._ai_shot(session))
                shots += 1
                if session.channel_id in self.games or session.phase == "done":
                    await self.publish(interaction, session, session.log[-1])
            return
        await self.publish(interaction, session, session.log[-1])

    async def _resolve(self, session: Session, attacker: int, cell: Cell) -> None:
        defender = session.opponent(attacker)
        result = session.fleets[defender].receive(cell)
        session.shots[attacker].append({"cell": cell, "kind": "sunk" if result == "sunk" else result})
        ship = session.fleets[defender].ship_at(cell)
        if result == "miss":
            line = f"{session.name(attacker)} missed at {label(cell)}."
            session.turn = defender
        elif result == "sunk":
            line = f"{session.name(attacker)} sunk the {ship.name} at {label(cell)}. Shoot again."
        else:
            line = f"{session.name(attacker)} hit at {label(cell)}. Shoot again."
        session.log.append(line)
        session.touch()
        if session.fleets[defender].lost():
            await self.finish(session, f"{session.name(attacker)} sunk the fleet.", winner=attacker)

    async def private_chart(self, interaction: discord.Interaction, session: Session) -> None:
        uid = interaction.user.id
        if uid not in session.players or uid == session.bot_id:
            await interaction.response.send_message("You are not in this battle.", ephemeral=True)
            return
        fleet = session.fleets.get(uid)
        if not fleet:
            await interaction.response.send_message("Your fleet is not deployed yet.", ephemeral=True)
            return
        tracking = session.shots.get(uid, [])
        enemy = self._panel(session, session.opponent(uid), show_hulls=False)
        enemy["heading"] = "ENEMY WATERS"
        panels = [
            self._panel(session, uid, show_hulls=True),
            enemy,
        ]
        panels[0]["heading"] = "YOUR FLEET"
        png = await asyncio.to_thread(
            render_boards, panels, "BATTLESHIP",
            f"Private chart · {session.name(uid)}", "Only you can see this.",
        )
        file = discord.File(io.BytesIO(png), filename="fleet.png")
        await interaction.response.send_message(file=file, ephemeral=True)

    async def _setup_payload(self, session: Session, uid: int):
        fleet = session.fleets[uid]
        ships = [{"cells": s.cells, "sunk": False, "mark": s.mark, "show": True} for s in fleet.ships if s.placed]
        panel = self._panel(session, uid, show_hulls=True)
        panel["heading"] = "YOUR FLEET"
        panel["ships"] = ships or panel["ships"]
        png = await asyncio.to_thread(
            render_boards, [panel], "BATTLESHIP",
            f"Setup · {session.name(uid)}", "Lock in when the fleet looks right. This DM is private.",
        )
        return "Arrange the fleet, then lock in.", discord.File(io.BytesIO(png), filename="fleet.png")

    async def surrender(self, session: Session, uid: int) -> None:
        await self.finish(session, f"{session.name(uid)} surrendered.", winner=session.opponent(uid))

    async def mail_setup(self, session: Session) -> None:
        failed = []
        for uid in session.players:
            if uid == session.bot_id or uid in session.locked:
                continue
            user = self.bot.get_user(uid)
            if user is None:
                try:
                    user = await self.bot.fetch_user(uid)
                except discord.HTTPException:
                    failed.append(session.name(uid))
                    continue
            content, file = await self._setup_payload(session, uid)
            view = PlaceView(self, session, uid)
            try:
                kwargs = {"content": content, "view": view}
                if file:
                    kwargs["file"] = file
                session.dms[uid] = await user.send(**kwargs)
            except discord.HTTPException:
                view.stop()
                failed.append(session.name(uid))
        if failed and session.message:
            try:
                await session.message.edit(
                    content=f"{', '.join(failed)} must allow DMs from this server before the fleet can be placed. There is no channel setup."
                )
            except discord.HTTPException:
                pass

    async def refresh_setup(self, interaction: discord.Interaction, session: Session, uid: int) -> None:
        content, file = await self._setup_payload(session, uid)
        if interaction.guild is None:
            kwargs = {"content": content}
            if file:
                kwargs["attachments"] = [file]
            await interaction.response.edit_message(**kwargs)
            return
        dm = session.dms.get(uid)
        if dm:
            try:
                await dm.edit(content=content, attachments=[file] if file else [])
            except discord.HTTPException:
                dm = None
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "Fleet updated in your DMs." if dm else "Open DMs from this server. Setup is not available in the channel.",
                ephemeral=True,
            )


class AcceptView(discord.ui.View):
    def __init__(self, cog: Battleship, session: Session):
        super().__init__(timeout=300)
        self.cog = cog
        self.session = session

    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.session.players[1]:
            await interaction.response.send_message("Only the challenged player can accept.", ephemeral=True)
            return
        await interaction.response.defer()
        await self.cog.begin_human(interaction, self.session)

    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.session.players:
            await interaction.response.send_message("You are not part of this challenge.", ephemeral=True)
            return
        self.cog.games.pop(self.session.channel_id, None)
        self.stop()
        await interaction.response.edit_message(content="Challenge declined.", view=None)

    async def on_timeout(self) -> None:
        self.cog.games.pop(self.session.channel_id, None)
        if self.session.message:
            try:
                await self.session.message.edit(content="Challenge expired.", view=None)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def _accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.accept(interaction, button)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.secondary)
    async def _decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.decline(interaction, button)


class DeployChannelView(discord.ui.View):
    def __init__(self, cog: Battleship, session: Session):
        super().__init__(timeout=None)
        self.cog = cog
        self.session = session

    def _player(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id in self.session.players and interaction.user.id != self.session.bot_id

    @discord.ui.button(label="Resend DM", style=discord.ButtonStyle.primary)
    async def resend(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._player(interaction):
            await interaction.response.send_message("You are not deploying in this battle.", ephemeral=True)
            return
        if interaction.user.id in self.session.locked:
            await interaction.response.send_message("Your fleet is already locked.", ephemeral=True)
            return
        self.session.dms.pop(interaction.user.id, None)
        await self.cog.mail_setup(self.session)
        if self.session.dms.get(interaction.user.id):
            await interaction.response.send_message("Setup chart sent to your DMs.", ephemeral=True)
            return
        await interaction.response.send_message("DM failed. Allow DMs from this server, then press Resend DM.", ephemeral=True)

    @discord.ui.button(label="Lock pre-rolled fleet", style=discord.ButtonStyle.success)
    async def lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._player(interaction):
            await interaction.response.send_message("You are not deploying in this battle.", ephemeral=True)
            return
        await self.cog.lock_fleet(interaction, self.session, interaction.user.id)

    @discord.ui.button(label="Surrender", style=discord.ButtonStyle.danger)
    async def surrender(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._player(interaction):
            await interaction.response.send_message("You are not in this battle.", ephemeral=True)
            return
        await interaction.response.defer()
        await self.cog.surrender(self.session, interaction.user.id)


class PlaceView(discord.ui.View):
    def __init__(self, cog: Battleship, session: Session, uid: int):
        super().__init__(timeout=600)
        self.cog = cog
        self.session = session
        self.uid = uid
        ships = session.fleets[uid].ships
        self.ship.options = [
            discord.SelectOption(label=f"{ship.name} ({ship.length})", value=str(i), default=(i == 0))
            for i, ship in enumerate(ships)
        ]
        self.col.options = [discord.SelectOption(label=ch, value=str(i)) for i, ch in enumerate(COLS)]
        self.row.options = [discord.SelectOption(label=str(i + 1), value=str(i)) for i in range(10)]

    @discord.ui.select(placeholder="Ship", row=0)
    async def ship(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.session.ship_pick[self.uid] = int(select.values[0])
        await interaction.response.defer(ephemeral=True)

    @discord.ui.select(placeholder="Column", row=1)
    async def col(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.session.aim_col[self.uid] = int(select.values[0])
        await interaction.response.defer(ephemeral=True)

    @discord.ui.select(placeholder="Row", row=2)
    async def row(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.session.aim_row[self.uid] = int(select.values[0])
        await interaction.response.defer(ephemeral=True)

    @discord.ui.button(label="Rotate", style=discord.ButtonStyle.secondary, row=3)
    async def rotate(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.uid in self.session.locked:
            await interaction.response.send_message("Fleet already locked.", ephemeral=True)
            return
        index = self.session.ship_pick.get(self.uid, 0)
        self.session.horizontal[self.uid] = not self.session.horizontal.get(self.uid, True)
        err = self.session.fleets[self.uid].spin(index)
        if err:
            self.session.horizontal[self.uid] = not self.session.horizontal[self.uid]
            await interaction.response.send_message(err, ephemeral=True)
            return
        await self.cog.refresh_setup(interaction, self.session, self.uid)

    @discord.ui.button(label="Place", style=discord.ButtonStyle.primary, row=3)
    async def place(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.uid in self.session.locked:
            await interaction.response.send_message("Fleet already locked.", ephemeral=True)
            return
        index = self.session.ship_pick.get(self.uid, 0)
        if self.uid not in self.session.aim_col or self.uid not in self.session.aim_row:
            await interaction.response.send_message("Pick a column and a row first.", ephemeral=True)
            return
        col = self.session.aim_col[self.uid]
        row = self.session.aim_row[self.uid]
        err = self.session.fleets[self.uid].place(index, col, row, self.session.horizontal.get(self.uid, True))
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return
        await self.cog.refresh_setup(interaction, self.session, self.uid)

    @discord.ui.button(label="Reroll", style=discord.ButtonStyle.secondary, row=3)
    async def reroll(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.uid in self.session.locked:
            await interaction.response.send_message("Fleet already locked.", ephemeral=True)
            return
        self.session.fleets[self.uid].roll(random.Random())
        await self.cog.refresh_setup(interaction, self.session, self.uid)

    @discord.ui.button(label="West", style=discord.ButtonStyle.secondary, row=4)
    async def west(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._nudge(interaction, -1, 0)

    @discord.ui.button(label="North", style=discord.ButtonStyle.secondary, row=4)
    async def north(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._nudge(interaction, 0, -1)

    @discord.ui.button(label="South", style=discord.ButtonStyle.secondary, row=4)
    async def south(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._nudge(interaction, 0, 1)

    @discord.ui.button(label="East", style=discord.ButtonStyle.secondary, row=4)
    async def east(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._nudge(interaction, 1, 0)

    async def _nudge(self, interaction: discord.Interaction, dc: int, dr: int) -> None:
        if self.uid in self.session.locked:
            await interaction.response.send_message("Fleet already locked.", ephemeral=True)
            return
        index = self.session.ship_pick.get(self.uid, 0)
        err = self.session.fleets[self.uid].nudge(index, dc, dr)
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return
        await self.cog.refresh_setup(interaction, self.session, self.uid)

    @discord.ui.button(label="Lock in", style=discord.ButtonStyle.success, row=3)
    async def lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.lock_fleet(interaction, self.session, self.uid)


class BattleView(discord.ui.View):
    def __init__(self, cog: Battleship, session: Session):
        super().__init__(timeout=None)
        self.cog = cog
        self.session = session
        self.col.options = [discord.SelectOption(label=ch, value=str(i)) for i, ch in enumerate(COLS)]
        self.row.options = [discord.SelectOption(label=str(i + 1), value=str(i)) for i in range(10)]

    @discord.ui.select(placeholder="Column", row=0)
    async def col(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user.id != self.session.turn:
            await interaction.response.send_message("It is not your shot.", ephemeral=True)
            return
        self.session.aim_col[interaction.user.id] = int(select.values[0])
        await interaction.response.defer(ephemeral=True)

    @discord.ui.select(placeholder="Row", row=1)
    async def row(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user.id != self.session.turn:
            await interaction.response.send_message("It is not your shot.", ephemeral=True)
            return
        self.session.aim_row[interaction.user.id] = int(select.values[0])
        await interaction.response.defer(ephemeral=True)

    @discord.ui.button(label="Fire", style=discord.ButtonStyle.danger, row=2)
    async def fire(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.session.aim_col or interaction.user.id not in self.session.aim_row:
            await interaction.response.send_message("Pick a column and a row first.", ephemeral=True)
            return
        cell = (self.session.aim_col[interaction.user.id], self.session.aim_row[interaction.user.id])
        await self.cog.fire(interaction, self.session, cell)

    @discord.ui.button(label="Type coordinate", style=discord.ButtonStyle.primary, row=2)
    async def typed(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.session.turn:
            await interaction.response.send_message("It is not your shot.", ephemeral=True)
            return
        await interaction.response.send_modal(CoordModal(self.cog, self.session))

    @discord.ui.button(label="My fleet", style=discord.ButtonStyle.secondary, row=2)
    async def mine(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.private_chart(interaction, self.session)

    @discord.ui.button(label="Surrender", style=discord.ButtonStyle.danger, row=3)
    async def surrender(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.session.players or interaction.user.id == self.session.bot_id:
            await interaction.response.send_message("You are not in this battle.", ephemeral=True)
            return
        await interaction.response.defer()
        await self.cog.surrender(self.session, interaction.user.id)


class CoordModal(discord.ui.Modal, title="Fire a coordinate"):
    coord = discord.ui.TextInput(label="Coordinate", placeholder="B7", max_length=3)

    def __init__(self, cog: Battleship, session: Session):
        super().__init__()
        self.cog = cog
        self.session = session

    async def on_submit(self, interaction: discord.Interaction) -> None:
        cell = parse_coord(self.coord.value)
        if cell is None:
            await interaction.response.send_message("Use a coordinate like B7 or 7B.", ephemeral=True)
            return
        await self.cog.fire(interaction, self.session, cell)


# lock helper attached after class body so views can call it
async def _lock_fleet(self: Battleship, interaction: discord.Interaction, session: Session, uid: int) -> None:
    fleet = session.fleets.get(uid)
    if not fleet or not fleet.ready():
        await interaction.response.send_message("Place all five ships first.", ephemeral=True)
        return
    if uid in session.locked:
        await interaction.response.send_message("Already locked.", ephemeral=True)
        return
    session.locked.add(uid)
    session.touch()
    dm = session.dms.get(uid)
    if dm:
        try:
            await dm.edit(content="Fleet locked. Head back to the channel.", view=None, attachments=[])
        except discord.HTTPException:
            pass
    if all(player in session.locked for player in session.players):
        session.phase = "battle"
        session.turn = session.players[0]
        if interaction.response.is_done():
            await self.publish(interaction, session, "Both fleets locked. First shot is yours." if uid == session.players[0] else "Both fleets locked.")
        else:
            await interaction.response.defer()
            notice = f"{session.name(session.players[0])} has the first shot."
            await self.publish(interaction, session, notice)
        return
    if not interaction.response.is_done():
        await interaction.response.send_message("Fleet locked. Waiting on the other admiral.", ephemeral=True)
    await self.publish(interaction, session, f"{session.name(uid)} locked their fleet.")


Battleship.lock_fleet = _lock_fleet  # type: ignore
