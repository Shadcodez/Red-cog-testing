"""MTGCard — tap-first unofficial Magic-style card studio for Red 3.5+."""

from __future__ import annotations

import asyncio
import io
import logging
import time
from typing import Dict, List, Optional

import aiohttp
import discord
from discord.ui import Button, Modal, Select, TextInput, View
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_list

from .renderer import (
    CARD_H,
    CARD_W,
    PALETTES,
    SCAN_TEMPLATES,
    CardSpec,
    format_cost,
    parse_mana_cost,
    placeholder_art,
    render_card,
)

__red_end_user_data_statement__ = (
    "This cog stores no persistent user data. Card drafts live in memory for "
    "the length of an interactive session and are discarded on generate, cancel, "
    "unload, or timeout."
)

log = logging.getLogger("red.mtgcard")

SESSION_TTL = 600
MAX_ART_BYTES = 12 * 1024 * 1024
PAINTED_FRAMES = list(PALETTES.keys())
SCAN_FRAMES = list(SCAN_TEMPLATES.keys())

COLOR_FRAME = {"W": "white", "U": "blue", "B": "black", "R": "red", "G": "green"}
KIND_TO_TYPE = {
    "creature": "Creature",
    "legendary_creature": "Legendary Creature",
    "instant": "Instant",
    "sorcery": "Sorcery",
    "enchantment": "Enchantment",
    "artifact": "Artifact",
    "legendary_artifact": "Legendary Artifact",
    "land": "Land",
}

FRAME_EMBED_COLOR = {
    "white": 0xE8D9A8,
    "blue": 0x3D7CB5,
    "black": 0x2A2428,
    "red": 0xC14A2C,
    "green": 0x4E8A3A,
    "gold": 0xC9A230,
    "artifact": 0x9A9384,
    "land": 0x8A6A3C,
}


def _blank_session() -> dict:
    return {
        "engine": "painted",
        "frame": "white",
        "rarity": "rare",
        "kind": "creature",
        "cost_tokens": ["2", "W"],
        "name": "",
        "subtype": "",
        "oracle_text": "",
        "flavor_text": "",
        "power_toughness": "",
        "artist": "",
        "art_bytes": None,
        "created": time.time(),
        "channel": None,
        "auto_frame": True,
    }


def _type_line(sess: dict) -> str:
    base = KIND_TO_TYPE.get(sess.get("kind") or "creature", "Creature")
    sub = (sess.get("subtype") or "").strip()
    return f"{base} — {sub}" if sub else base


def _mana_string(sess: dict) -> str:
    return format_cost(sess.get("cost_tokens") or [])


def _pretty_cost(sess: dict) -> str:
    tokens = sess.get("cost_tokens") or []
    if not tokens:
        return "none"
    pretty = []
    for t in tokens:
        pretty.append(
            {
                "W": "☀️",
                "U": "💧",
                "B": "💀",
                "R": "🔥",
                "G": "🌳",
                "C": "◇",
                "X": "X",
                "T": "⟳",
            }.get(t, t)
        )
    return " ".join(pretty) + f"   `{format_cost(tokens)}`"


def _apply_auto_frame(sess: dict) -> None:
    if not sess.get("auto_frame"):
        return
    kind = sess.get("kind") or "creature"
    if kind == "land":
        sess["frame"] = "land"
        return
    if kind in ("artifact", "legendary_artifact"):
        colors = [t for t in sess.get("cost_tokens") or [] if t in COLOR_FRAME]
        sess["frame"] = "gold" if len(set(colors)) > 1 else ("artifact" if not colors else COLOR_FRAME[colors[0]])
        return
    colors = [t for t in sess.get("cost_tokens") or [] if t in COLOR_FRAME]
    uniq = []
    for c in colors:
        if c not in uniq:
            uniq.append(c)
    if len(uniq) == 1:
        sess["frame"] = COLOR_FRAME[uniq[0]]
    elif len(uniq) > 1:
        sess["frame"] = "gold"
    else:
        sess["frame"] = "artifact"


class MTGCard(commands.Cog):
    """Create unofficial Magic-style cards with taps, not typing."""

    __author__ = "SHADOW6six + Grok"
    __version__ = "4.1.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self._sessions: Dict[int, dict] = {}
        self._session: Optional[aiohttp.ClientSession] = None

    async def cog_load(self) -> None:
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=25),
            headers={"User-Agent": "Red-MTGCard/4.1"},
        )

    async def cog_unload(self) -> None:
        self._sessions.clear()
        if self._session and not self._session.closed:
            await self._session.close()

    async def red_delete_data_for_user(self, *, requester: str, user_id: int) -> None:
        self._sessions.pop(user_id, None)

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre = super().format_help_for_context(ctx)
        return f"{pre}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}"

    def _session_for(self, user_id: int) -> dict:
        sess = self._sessions.get(user_id)
        if not sess or time.time() - sess.get("created", 0) > SESSION_TTL:
            sess = _blank_session()
            self._sessions[user_id] = sess
        return sess

    async def _read_attachment(self, att: discord.Attachment) -> bytes:
        if att.size and att.size > MAX_ART_BYTES:
            raise ValueError("Image is too large (max 12 MB).")
        ctype = (att.content_type or "").lower()
        name = (att.filename or "").lower()
        if ctype and not ctype.startswith("image/"):
            raise ValueError("That attachment is not an image.")
        if not ctype and not name.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
            raise ValueError("Please upload a PNG, JPG, WEBP, or GIF.")
        data = await att.read()
        if len(data) < 24:
            raise ValueError("Image file was empty.")
        return data

    def _spec_from_session(self, sess: dict) -> CardSpec:
        return CardSpec(
            name=(sess.get("name") or "Unnamed Card").strip(),
            mana_cost=_mana_string(sess),
            type_line=_type_line(sess),
            oracle_text=sess.get("oracle_text") or "",
            flavor_text=sess.get("flavor_text") or "",
            power_toughness=sess.get("power_toughness") or "",
            artist=sess.get("artist") or "",
            rarity=sess.get("rarity") or "rare",
            frame=sess.get("frame") or "white",
            engine=sess.get("engine") or "painted",
        )

    def draft_embed(self, sess: dict) -> discord.Embed:
        spec_name = sess.get("name") or "*tap Name & text*"
        art = "ready" if sess.get("art_bytes") else "optional — skip to print without it"
        embed = discord.Embed(
            title="Card Studio",
            description=(
                f"**{spec_name}**\n"
                f"{_type_line(sess)}\n"
                f"Cost {_pretty_cost(sess)}\n"
                f"{(sess.get('rarity') or 'rare').title()} · {sess.get('frame', 'white').title()} frame\n"
                f"Art: {art}"
            ),
            color=FRAME_EMBED_COLOR.get(sess.get("frame") or "white", 0xE8D9A8),
        )
        embed.set_footer(text="Tap the menus. Only name/text needs typing. • unofficial")
        return embed

    async def refresh(self, interaction: discord.Interaction, sess: dict) -> None:
        # Rebuild the view so the same mana option can be tapped twice (e.g. WW).
        await interaction.response.edit_message(
            embed=self.draft_embed(sess),
            view=StudioView(self, interaction.user.id),
        )

    async def _render_and_send(
        self,
        destination: discord.abc.Messageable,
        spec: CardSpec,
        art_bytes: bytes,
        *,
        progress: Optional[discord.Message] = None,
        interaction: Optional[discord.Interaction] = None,
    ) -> None:
        try:
            card_bytes = await asyncio.to_thread(render_card, art_bytes, spec)
        except Exception:
            log.exception("MTGCard render failed")
            text = "Render failed. Try a different image or frame."
            if progress:
                await progress.edit(content=f"⚠️ {text}", embed=None, view=None)
            elif interaction:
                await interaction.followup.send(f"⚠️ {text}", ephemeral=True)
            else:
                await destination.send(f"⚠️ {text}")
            return

        safe = "".join(c for c in spec.name if c.isalnum() or c in " _-").strip() or "mtgcard"
        filename = f"{safe.replace(' ', '_')}.png"
        file = discord.File(io.BytesIO(card_bytes), filename=filename)
        embed = discord.Embed(
            title=spec.name,
            description=f"**{spec.type_line or '—'}** · {spec.rarity.title()}",
            color=FRAME_EMBED_COLOR.get(spec.frame, 0xC9A230),
        )
        embed.set_image(url=f"attachment://{filename}")
        embed.set_footer(text=f"MTGCard v{self.__version__} • unofficial fan-made card")
        if progress:
            await progress.edit(content=None, embed=embed, attachments=[file], view=None)
        elif interaction:
            await interaction.followup.send(embed=embed, file=file)
        else:
            await destination.send(embed=embed, file=file)

    @commands.hybrid_group(name="mtgcard", invoke_without_command=True)
    @commands.cooldown(1, 8, commands.BucketType.user)
    async def mtgcard(self, ctx: commands.Context):
        """Open the tap-first card studio."""
        await self.mtgcard_create(ctx)

    @mtgcard.command(name="create")
    @commands.cooldown(1, 8, commands.BucketType.user)
    async def mtgcard_create(self, ctx: commands.Context, art: Optional[discord.Attachment] = None):
        """Open the studio. Attach a picture to use it as art."""
        sess = _blank_session()
        sess["channel"] = ctx.channel.id
        self._sessions[ctx.author.id] = sess
        source = art or (ctx.message.attachments[0] if ctx.message.attachments else None)
        if source:
            try:
                sess["art_bytes"] = await self._read_attachment(source)
            except ValueError as exc:
                await ctx.send(f"⚠️ {exc}")
                return
        view = StudioView(self, ctx.author.id)
        await ctx.send(embed=self.draft_embed(sess), view=view)

    @mtgcard.command(name="make")
    @commands.cooldown(1, 12, commands.BucketType.user)
    @commands.max_concurrency(3, commands.BucketType.guild)
    async def mtgcard_make(
        self,
        ctx: commands.Context,
        name: str,
        mana: str = "",
        type_line: str = "Creature",
        pt: str = "",
        frame: str = "gold",
        art: Optional[discord.Attachment] = None,
        *,
        text: str = "",
    ):
        """One-shot card if you already know the text. Attach art to the message."""
        frame_key = frame.lower().strip()
        engine = "scan" if frame_key.startswith("scan:") or frame_key.startswith("template:") else "painted"
        if engine == "scan":
            frame_key = frame_key.split(":", 1)[-1]
            if frame_key not in SCAN_FRAMES:
                await ctx.send(f"Unknown scan frame. Choose one of: {humanize_list(SCAN_FRAMES)}")
                return
        else:
            aliases = {"w": "white", "u": "blue", "b": "black", "r": "red", "g": "green", "c": "artifact", "m": "gold"}
            frame_key = aliases.get(frame_key, frame_key)
            if frame_key not in PALETTES:
                await ctx.send(f"Unknown frame. Choose one of: {humanize_list(PAINTED_FRAMES)}")
                return
        source = art or (ctx.message.attachments[0] if ctx.message.attachments else None)
        if source:
            try:
                art_bytes = await self._read_attachment(source)
            except ValueError as exc:
                await ctx.send(f"⚠️ {exc}")
                return
        else:
            art_bytes = placeholder_art(name)
        spec = CardSpec(
            name=name.strip()[:40],
            mana_cost=format_cost(parse_mana_cost(mana)),
            type_line=type_line.strip()[:60],
            oracle_text=text.strip()[:800],
            power_toughness=pt.strip()[:12],
            frame=frame_key,
            engine=engine,
        )
        async with ctx.typing():
            await self._render_and_send(ctx, spec, art_bytes)

    @mtgcard.command(name="reset")
    async def mtgcard_reset(self, ctx: commands.Context):
        """Clear your in-progress card draft."""
        if self._sessions.pop(ctx.author.id, None):
            await ctx.send("Draft cleared.")
        else:
            await ctx.send("No active draft.")

    @mtgcard.command(name="info")
    async def mtgcard_info(self, ctx: commands.Context):
        """Show version and credits."""
        embed = discord.Embed(
            title="MTGCard",
            description=(
                "Tap-first unofficial card studio. Real mana symbols on the finished "
                "card. Not affiliated with Wizards of the Coast."
            ),
            color=await ctx.embed_color(),
        )
        embed.add_field(name="Version", value=self.__version__, inline=True)
        embed.add_field(name="Author", value=self.__author__, inline=True)
        await ctx.send(embed=embed)


# ── Studio UI ───────────────────────────────────────────────────────────────


class StudioView(View):
    def __init__(self, cog: MTGCard, owner_id: int):
        super().__init__(timeout=SESSION_TTL)
        self.cog = cog
        self.owner_id = owner_id
        self.add_item(KindSelect(cog, owner_id))
        self.add_item(ManaSelect(cog, owner_id))
        self.add_item(FrameSelect(cog, owner_id))
        self.add_item(TextButton(cog, owner_id))
        self.add_item(ArtButton(cog, owner_id))
        self.add_item(PrintButton(cog, owner_id))
        self.add_item(CancelButton(cog, owner_id))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Someone else's studio.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        self.cog._sessions.pop(self.owner_id, None)
        self.stop()


class KindSelect(Select):
    def __init__(self, cog: MTGCard, owner_id: int):
        self.cog = cog
        self.owner_id = owner_id
        super().__init__(
            placeholder="What kind of card?",
            min_values=1,
            max_values=1,
            row=0,
            options=[
                discord.SelectOption(label="Creature", value="creature", emoji="🐉", default=True),
                discord.SelectOption(label="Legendary Creature", value="legendary_creature", emoji="👑"),
                discord.SelectOption(label="Instant", value="instant", emoji="⚡"),
                discord.SelectOption(label="Sorcery", value="sorcery", emoji="🔥"),
                discord.SelectOption(label="Enchantment", value="enchantment", emoji="✨"),
                discord.SelectOption(label="Artifact", value="artifact", emoji="⚙️"),
                discord.SelectOption(label="Legendary Artifact", value="legendary_artifact", emoji="🏆"),
                discord.SelectOption(label="Land", value="land", emoji="🗺️"),
            ],
        )

    async def callback(self, interaction: discord.Interaction):
        sess = self.cog._session_for(self.owner_id)
        sess["kind"] = self.values[0]
        if sess["kind"] == "land":
            sess["cost_tokens"] = []
        _apply_auto_frame(sess)
        await self.cog.refresh(interaction, sess)


class ManaSelect(Select):
    def __init__(self, cog: MTGCard, owner_id: int):
        self.cog = cog
        self.owner_id = owner_id
        super().__init__(
            placeholder="Tap to build the mana cost",
            min_values=1,
            max_values=1,
            row=1,
            options=[
                discord.SelectOption(label="Generic 0", value="set:0", description="Replace the number pip with 0"),
                discord.SelectOption(label="Generic 1", value="set:1"),
                discord.SelectOption(label="Generic 2", value="set:2"),
                discord.SelectOption(label="Generic 3", value="set:3"),
                discord.SelectOption(label="Generic 4", value="set:4"),
                discord.SelectOption(label="Generic 5", value="set:5"),
                discord.SelectOption(label="Generic 6", value="set:6"),
                discord.SelectOption(label="X", value="set:X"),
                discord.SelectOption(label="Add White", value="add:W", emoji="☀️"),
                discord.SelectOption(label="Add Blue", value="add:U", emoji="💧"),
                discord.SelectOption(label="Add Black", value="add:B", emoji="💀"),
                discord.SelectOption(label="Add Red", value="add:R", emoji="🔥"),
                discord.SelectOption(label="Add Green", value="add:G", emoji="🌳"),
                discord.SelectOption(label="Add Colorless", value="add:C"),
                discord.SelectOption(label="Undo last pip", value="undo"),
                discord.SelectOption(label="Clear cost", value="clear"),
            ],
        )

    async def callback(self, interaction: discord.Interaction):
        sess = self.cog._session_for(self.owner_id)
        tokens: List[str] = list(sess.get("cost_tokens") or [])
        action = self.values[0]
        if action == "clear":
            tokens = []
        elif action == "undo":
            if tokens:
                tokens.pop()
        elif action.startswith("set:"):
            val = action.split(":", 1)[1]
            tokens = [t for t in tokens if t in "WUBRGC" or "/" in t]
            if val != "0":
                tokens = [val] + tokens
        elif action.startswith("add:"):
            tokens.append(action.split(":", 1)[1])
        sess["cost_tokens"] = tokens[:12]
        _apply_auto_frame(sess)
        await self.cog.refresh(interaction, sess)


class FrameSelect(Select):
    def __init__(self, cog: MTGCard, owner_id: int):
        self.cog = cog
        self.owner_id = owner_id
        options = [
            discord.SelectOption(label=p.label, value=p.key, description=p.description, emoji=p.emoji)
            for p in PALETTES.values()
        ]
        options.append(discord.SelectOption(label="Auto (from mana)", value="auto", description="Pick the frame from the cost"))
        super().__init__(
            placeholder="Frame color (auto from mana)",
            min_values=1,
            max_values=1,
            row=2,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        sess = self.cog._session_for(self.owner_id)
        if self.values[0] == "auto":
            sess["auto_frame"] = True
            _apply_auto_frame(sess)
        else:
            sess["auto_frame"] = False
            sess["frame"] = self.values[0]
            sess["engine"] = "painted"
        await self.cog.refresh(interaction, sess)


class TextButton(Button):
    def __init__(self, cog: MTGCard, owner_id: int):
        super().__init__(label="Name & text", style=discord.ButtonStyle.primary, row=3)
        self.cog = cog
        self.owner_id = owner_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TextModal(self.cog, self.owner_id))


class ArtButton(Button):
    def __init__(self, cog: MTGCard, owner_id: int):
        super().__init__(label="Add picture", style=discord.ButtonStyle.secondary, row=3)
        self.cog = cog
        self.owner_id = owner_id

    async def callback(self, interaction: discord.Interaction):
        sess = self.cog._session_for(self.owner_id)
        sess["channel"] = interaction.channel_id
        await interaction.response.send_message(
            "Drop **one image** in this channel in the next 90 seconds.",
            ephemeral=True,
        )

        def check(msg: discord.Message) -> bool:
            return (
                msg.author.id == self.owner_id
                and msg.channel.id == interaction.channel_id
                and bool(msg.attachments)
            )

        try:
            msg = await self.cog.bot.wait_for("message", timeout=90, check=check)
            sess["art_bytes"] = await self.cog._read_attachment(msg.attachments[0])
            try:
                await msg.add_reaction("✅")
            except discord.HTTPException:
                pass
            await interaction.followup.send("Picture saved. Tap **Print card**.", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("No picture arrived — you can still print.", ephemeral=True)
        except ValueError as exc:
            await interaction.followup.send(f"⚠️ {exc}", ephemeral=True)


class PrintButton(Button):
    def __init__(self, cog: MTGCard, owner_id: int):
        super().__init__(label="Print card", style=discord.ButtonStyle.success, row=3)
        self.cog = cog
        self.owner_id = owner_id

    async def callback(self, interaction: discord.Interaction):
        sess = self.cog._session_for(self.owner_id)
        if not (sess.get("name") or "").strip():
            await interaction.response.send_message("Tap **Name & text** first — just the name is enough.", ephemeral=True)
            return
        spec = self.cog._spec_from_session(sess)
        art = sess.get("art_bytes") or placeholder_art(spec.name)
        await interaction.response.defer()
        progress = await interaction.followup.send("Printing…", wait=True)
        await self.cog._render_and_send(interaction.channel, spec, art, progress=progress)


class CancelButton(Button):
    def __init__(self, cog: MTGCard, owner_id: int):
        super().__init__(label="Cancel", style=discord.ButtonStyle.danger, row=4)
        self.cog = cog
        self.owner_id = owner_id

    async def callback(self, interaction: discord.Interaction):
        self.cog._sessions.pop(self.owner_id, None)
        await interaction.response.edit_message(content="Studio closed.", embed=None, view=None)
        self.view.stop()


class TextModal(Modal, title="Name & text"):
    def __init__(self, cog: MTGCard, user_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.uid = user_id
        sess = cog._sessions.get(user_id) or {}
        self.name_field = TextInput(
            label="Name",
            placeholder="Serra Angel",
            max_length=40,
            required=True,
            default=(sess.get("name") or "")[:40],
        )
        self.sub_field = TextInput(
            label="Subtype (optional)",
            placeholder="Angel    or    Goblin Scout",
            max_length=32,
            required=False,
            default=(sess.get("subtype") or "")[:32],
        )
        self.oracle_field = TextInput(
            label="Rules (optional)",
            style=discord.TextStyle.paragraph,
            placeholder="Flying, vigilance\n{T}: Draw a card.",
            max_length=500,
            required=False,
            default=(sess.get("oracle_text") or "")[:500],
        )
        self.flavor_field = TextInput(
            label="Flavor text (optional)",
            max_length=180,
            required=False,
            default=(sess.get("flavor_text") or "")[:180],
        )
        self.pt_field = TextInput(
            label="Power / toughness (creatures)",
            placeholder="4/4",
            max_length=10,
            required=False,
            default=(sess.get("power_toughness") or "")[:10],
        )
        for item in (self.name_field, self.sub_field, self.oracle_field, self.flavor_field, self.pt_field):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        sess = self.cog._session_for(self.uid)
        sess["name"] = self.name_field.value.strip()
        sess["subtype"] = self.sub_field.value.strip()
        sess["oracle_text"] = self.oracle_field.value.strip()
        sess["flavor_text"] = self.flavor_field.value.strip()
        sess["power_toughness"] = self.pt_field.value.strip()
        await interaction.response.edit_message(embed=self.cog.draft_embed(sess))
