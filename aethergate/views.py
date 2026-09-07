"""Interactive lattice views for AetherGate."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Sequence

import discord
from discord.ui import Button, ChannelSelect, Modal, Select, TextInput, View, button

from .constants import (
    ACCENT,
    ACCENT_OK,
    ACCENT_WARN,
    PRESET_META,
    PRESETS,
    SIGNAL_ORDER,
    SIGNALS,
    state_glyph,
    state_short,
)

if TYPE_CHECKING:
    from .aethergate import AetherGate


TEXTISH = {
    discord.ChannelType.text,
    discord.ChannelType.news,
    discord.ChannelType.forum,
    discord.ChannelType.news_thread,
    discord.ChannelType.public_thread,
    discord.ChannelType.private_thread,
}
VOICEISH = {
    discord.ChannelType.voice,
    discord.ChannelType.stage_voice,
}


def _scope_ok(channel: discord.abc.GuildChannel, signal_key: str) -> bool:
    scopes = SIGNALS[signal_key].scopes
    if "both" in scopes:
        return True
    if channel.type in VOICEISH:
        return "voice" in scopes
    return "text" in scopes


class ChannelPasteModal(Modal, title="Inject Channel Nodes"):
    raw = TextInput(
        label="Channels",
        style=discord.TextStyle.paragraph,
        placeholder="#general #voice-lab 123456789012345678",
        max_length=1000,
        required=True,
    )

    def __init__(self, parent: "LatticeView"):
        super().__init__()
        self.parent = parent

    async def on_submit(self, interaction: discord.Interaction) -> None:
        parsed = await self.parent.cog.resolve_channel_blob(
            interaction.guild, str(self.raw.value)
        )
        if not parsed:
            await interaction.response.send_message(
                "No usable channels found in that payload.", ephemeral=True
            )
            return
        self.parent.target_ids = {ch.id for ch in parsed}
        await interaction.response.edit_message(embed=self.parent.build_embed(), view=self.parent)


class RenameModal(Modal, title="Rename Access Role"):
    new_name = TextInput(
        label="Role name",
        min_length=1,
        max_length=100,
        required=True,
    )

    def __init__(self, parent: "LatticeView"):
        super().__init__()
        self.parent = parent
        if parent.role:
            self.new_name.default = parent.role.name

    async def on_submit(self, interaction: discord.Interaction) -> None:
        error = await self.parent.cog.rename_managed_role(
            interaction, self.parent.role, str(self.new_name.value)
        )
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        await self.parent.refresh_role()
        await interaction.response.edit_message(embed=self.parent.build_embed(), view=self.parent)


class LatticeView(View):
    """Primary holopanel: pick a role, lock channels, mutate signals, commit."""

    def __init__(
        self,
        cog: "AetherGate",
        author: discord.Member,
        role: Optional[discord.Role],
        template: Dict[str, Optional[bool]],
    ):
        super().__init__(timeout=360)
        self.cog = cog
        self.author_id = author.id
        self.guild_id = author.guild.id
        self.role: Optional[discord.Role] = role
        self.template: Dict[str, Optional[bool]] = dict(template)
        self.selected_signal: str = "view"
        self.target_ids: set[int] = set()
        self.message: Optional[discord.Message] = None
        self._rebuild_selects()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "This lattice is keyed to another operator.", ephemeral=True
        )
        return False

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def refresh_role(self) -> None:
        if not self.role:
            return
        guild = self.cog.bot.get_guild(self.guild_id)
        if guild:
            self.role = guild.get_role(self.role.id)

    def _rebuild_selects(self) -> None:
        # Drop dynamic selects then re-add in a stable order.
        to_remove = [
            child
            for child in self.children
            if isinstance(child, (Select, ChannelSelect)) and getattr(child, "custom_id", None)
            in {"ag_signal", "ag_preset", "ag_channels"}
        ]
        for child in to_remove:
            self.remove_item(child)

        signal_select = Select(
            placeholder="Select a signal to mutate…",
            custom_id="ag_signal",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=f"{SIGNALS[k].label}  {state_short(self.template.get(k))}",
                    value=k,
                    emoji=SIGNALS[k].emoji,
                    description=SIGNALS[k].blurb[:100],
                    default=(k == self.selected_signal),
                )
                for k in SIGNAL_ORDER
            ],
            row=0,
        )
        signal_select.callback = self._on_signal
        self.add_item(signal_select)

        preset_select = Select(
            placeholder="Load a signal preset…",
            custom_id="ag_preset",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=meta[0],
                    value=key,
                    emoji=meta[1],
                    description=meta[2][:100],
                )
                for key, meta in PRESET_META.items()
            ],
            row=1,
        )
        preset_select.callback = self._on_preset
        self.add_item(preset_select)

        channel_select = ChannelSelect(
            placeholder="Lock target channel nodes…",
            custom_id="ag_channels",
            min_values=1,
            max_values=25,
            channel_types=[
                discord.ChannelType.text,
                discord.ChannelType.news,
                discord.ChannelType.forum,
                discord.ChannelType.voice,
                discord.ChannelType.stage_voice,
            ],
            row=2,
        )
        channel_select.callback = self._on_channels
        self.add_item(channel_select)

    async def _on_signal(self, interaction: discord.Interaction) -> None:
        self.selected_signal = interaction.data["values"][0]  # type: ignore[index]
        self._rebuild_selects()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _on_preset(self, interaction: discord.Interaction) -> None:
        key = interaction.data["values"][0]  # type: ignore[index]
        self.template = dict(PRESETS[key])
        self._rebuild_selects()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _on_channels(self, interaction: discord.Interaction) -> None:
        resolved = []
        if interaction.data and "resolved" in interaction.data:
            raw = interaction.data["resolved"].get("channels", {})  # type: ignore[index]
            resolved = [int(cid) for cid in raw.keys()]
        values = interaction.data.get("values", []) if interaction.data else []
        ids = {int(v) for v in values} or set(resolved)
        self.target_ids = ids
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    def build_embed(self) -> discord.Embed:
        role = self.role
        title = "AETHERGATE  //  ACCESS LATTICE"
        embed = discord.Embed(title=title, color=ACCENT)
        if role:
            embed.description = (
                f"**Role node** {role.mention} `{role.id}`\n"
                f"Members `{len(role.members)}` · Position `{role.position}`"
            )
        else:
            embed.description = "No role bound. Create or adopt one first."

        lines = []
        for key in SIGNAL_ORDER:
            sig = SIGNALS[key]
            marker = "▸" if key == self.selected_signal else " "
            lines.append(
                f"`{marker}` {sig.emoji} **{sig.label}** — `{state_glyph(self.template.get(key))}`"
            )
        embed.add_field(name="Signal Matrix", value="\n".join(lines), inline=False)

        if self.target_ids:
            mentions = " ".join(f"<#{cid}>" for cid in list(self.target_ids)[:20])
            extra = "" if len(self.target_ids) <= 20 else f"\n+{len(self.target_ids) - 20} more"
            embed.add_field(
                name=f"Locked Targets  ·  {len(self.target_ids)}",
                value=mentions + extra,
                inline=False,
            )
        else:
            embed.add_field(
                name="Locked Targets",
                value="None. Use the channel picker, or **Paste #channels**.",
                inline=False,
            )

        embed.set_footer(
            text="▲ allow  ·  ▼ deny  ·  ◇ inherit   |   commits write live overwrites"
        )
        return embed

    # --- state buttons -------------------------------------------------
    @button(label="ALLOW", style=discord.ButtonStyle.success, row=3)
    async def btn_allow(self, interaction: discord.Interaction, button: Button) -> None:
        self.template[self.selected_signal] = True
        self._rebuild_selects()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @button(label="DENY", style=discord.ButtonStyle.danger, row=3)
    async def btn_deny(self, interaction: discord.Interaction, button: Button) -> None:
        self.template[self.selected_signal] = False
        self._rebuild_selects()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @button(label="INHERIT", style=discord.ButtonStyle.secondary, row=3)
    async def btn_inherit(self, interaction: discord.Interaction, button: Button) -> None:
        self.template[self.selected_signal] = None
        self._rebuild_selects()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @button(label="Paste #channels", style=discord.ButtonStyle.primary, row=3)
    async def btn_paste(self, interaction: discord.Interaction, button: Button) -> None:
        await interaction.response.send_modal(ChannelPasteModal(self))

    # --- commit / edit buttons ----------------------------------------
    @button(label="Commit Selected", style=discord.ButtonStyle.success, row=4)
    async def btn_commit(self, interaction: discord.Interaction, button: Button) -> None:
        await self._commit(interaction, list(self.target_ids))

    @button(label="All Text", style=discord.ButtonStyle.secondary, row=4)
    async def btn_all_text(self, interaction: discord.Interaction, button: Button) -> None:
        guild = interaction.guild
        ids = [
            ch.id
            for ch in guild.channels
            if ch.type in TEXTISH and not isinstance(ch, discord.Thread)
        ]
        await self._commit(interaction, ids)

    @button(label="All Voice", style=discord.ButtonStyle.secondary, row=4)
    async def btn_all_voice(self, interaction: discord.Interaction, button: Button) -> None:
        guild = interaction.guild
        ids = [ch.id for ch in guild.channels if ch.type in VOICEISH]
        await self._commit(interaction, ids)

    @button(label="Rename", style=discord.ButtonStyle.primary, row=4)
    async def btn_rename(self, interaction: discord.Interaction, button: Button) -> None:
        if not self.role:
            await interaction.response.send_message("No role bound.", ephemeral=True)
            return
        await interaction.response.send_modal(RenameModal(self))

    @button(label="Channel Lab", style=discord.ButtonStyle.primary, row=4)
    async def btn_lab(self, interaction: discord.Interaction, button: Button) -> None:
        if not self.role:
            await interaction.response.send_message("No role bound.", ephemeral=True)
            return
        channels = self._resolve_targets(interaction.guild)
        if not channels:
            await interaction.response.send_message(
                "Lock at least one target channel first.", ephemeral=True
            )
            return
        lab = ChannelLabView(self.cog, interaction.user, self.role, channels)
        await interaction.response.send_message(
            embed=lab.build_embed(), view=lab, ephemeral=True
        )

    def _resolve_targets(self, guild: discord.Guild) -> List[discord.abc.GuildChannel]:
        out = []
        for cid in self.target_ids:
            ch = guild.get_channel(cid)
            if ch is not None:
                out.append(ch)
        return out

    async def _commit(
        self, interaction: discord.Interaction, channel_ids: Sequence[int]
    ) -> None:
        if not self.role:
            await interaction.response.send_message("No role bound.", ephemeral=True)
            return
        if not channel_ids:
            await interaction.response.send_message(
                "No target nodes locked. Pick channels or paste `#channel #channel`.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        ok, skipped, errors = await self.cog.commit_template(
            guild=interaction.guild,
            actor=interaction.user,
            role=self.role,
            template=self.template,
            channel_ids=list(channel_ids),
        )
        await self.cog.store_template(interaction.guild, self.role, self.template)

        color = ACCENT_OK if not errors else ACCENT_WARN
        embed = discord.Embed(
            title="PULSE COMMIT",
            color=color,
            description=(
                f"{self.role.mention} written to **{ok}** channel(s). "
                f"Skipped `{skipped}`. Errors `{errors}`."
            ),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        try:
            await interaction.message.edit(embed=self.build_embed(), view=self)
        except discord.HTTPException:
            pass


class ChannelLabView(View):
    """Walk selected channels one by one and paint live overwrites."""

    def __init__(
        self,
        cog: "AetherGate",
        author: discord.Member,
        role: discord.Role,
        channels: Sequence[discord.abc.GuildChannel],
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.author_id = author.id
        self.role = role
        self.channels = list(channels)
        self.index = 0
        self.selected_signal = "view"
        self._sync_signal_select()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "This lab session is keyed to another operator.", ephemeral=True
        )
        return False

    @property
    def channel(self) -> discord.abc.GuildChannel:
        return self.channels[self.index]

    def live_map(self) -> Dict[str, Optional[bool]]:
        overwrite = self.channel.overwrites_for(self.role)
        out: Dict[str, Optional[bool]] = {}
        for key in SIGNAL_ORDER:
            out[key] = getattr(overwrite, SIGNALS[key].attr)
        return out

    def _sync_signal_select(self) -> None:
        existing = [c for c in self.children if getattr(c, "custom_id", None) == "lab_signal"]
        for item in existing:
            self.remove_item(item)
        live = self.live_map()
        select = Select(
            placeholder="Pick a signal on this channel…",
            custom_id="lab_signal",
            options=[
                discord.SelectOption(
                    label=f"{SIGNALS[k].label}  {state_short(live.get(k))}",
                    value=k,
                    emoji=SIGNALS[k].emoji,
                    default=(k == self.selected_signal),
                )
                for k in SIGNAL_ORDER
            ],
            row=0,
        )
        select.callback = self._on_signal
        self.add_item(select)

    async def _on_signal(self, interaction: discord.Interaction) -> None:
        self.selected_signal = interaction.data["values"][0]  # type: ignore[index]
        self._sync_signal_select()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    def build_embed(self) -> discord.Embed:
        ch = self.channel
        live = self.live_map()
        embed = discord.Embed(
            title="AETHERGATE  //  CHANNEL LAB",
            color=ACCENT,
            description=(
                f"Role {self.role.mention} · Node {ch.mention}\n"
                f"Walk `{self.index + 1}` / `{len(self.channels)}`"
            ),
        )
        lines = []
        for key in SIGNAL_ORDER:
            sig = SIGNALS[key]
            applicable = _scope_ok(ch, key)
            tag = "" if applicable else " *(n/a on this node)*"
            marker = "▸" if key == self.selected_signal else " "
            lines.append(
                f"`{marker}` {sig.emoji} **{sig.label}** — `{state_glyph(live.get(key))}`{tag}"
            )
        embed.add_field(name="Live Overwrite", value="\n".join(lines), inline=False)
        embed.set_footer(text="Edits write immediately to this channel.")
        return embed

    async def _paint(self, interaction: discord.Interaction, value: Optional[bool]) -> None:
        attr = SIGNALS[self.selected_signal].attr
        try:
            await self.cog.paint_single(
                channel=self.channel,
                role=self.role,
                actor=interaction.user,
                updates={attr: value},
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "Missing channel permission to write that overwrite.", ephemeral=True
            )
            return
        except discord.HTTPException as exc:
            await interaction.response.send_message(f"Discord rejected the write: {exc}", ephemeral=True)
            return
        self._sync_signal_select()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @button(label="ALLOW", style=discord.ButtonStyle.success, row=1)
    async def lab_allow(self, interaction: discord.Interaction, button: Button) -> None:
        await self._paint(interaction, True)

    @button(label="DENY", style=discord.ButtonStyle.danger, row=1)
    async def lab_deny(self, interaction: discord.Interaction, button: Button) -> None:
        await self._paint(interaction, False)

    @button(label="INHERIT", style=discord.ButtonStyle.secondary, row=1)
    async def lab_inherit(self, interaction: discord.Interaction, button: Button) -> None:
        await self._paint(interaction, None)

    @button(label="◀ Prev", style=discord.ButtonStyle.primary, row=2)
    async def lab_prev(self, interaction: discord.Interaction, button: Button) -> None:
        self.index = (self.index - 1) % len(self.channels)
        self._sync_signal_select()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @button(label="Next ▶", style=discord.ButtonStyle.primary, row=2)
    async def lab_next(self, interaction: discord.Interaction, button: Button) -> None:
        self.index = (self.index + 1) % len(self.channels)
        self._sync_signal_select()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @button(label="Strip Overwrite", style=discord.ButtonStyle.danger, row=2)
    async def lab_strip(self, interaction: discord.Interaction, button: Button) -> None:
        try:
            await self.channel.set_permissions(
                self.role,
                overwrite=None,
                reason=f"AetherGate strip by {interaction.user} ({interaction.user.id})",
            )
        except discord.Forbidden:
            await interaction.response.send_message("Cannot strip that overwrite.", ephemeral=True)
            return
        self._sync_signal_select()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


class ConfirmView(View):
    def __init__(self, author_id: int):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.value: Optional[bool] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message("Not your confirmation.", ephemeral=True)
        return False

    @button(label="Confirm", style=discord.ButtonStyle.danger)
    async def yes(self, interaction: discord.Interaction, button: Button) -> None:
        self.value = True
        self.stop()
        await interaction.response.defer()

    @button(label="Abort", style=discord.ButtonStyle.secondary)
    async def no(self, interaction: discord.Interaction, button: Button) -> None:
        self.value = False
        self.stop()
        await interaction.response.defer()
