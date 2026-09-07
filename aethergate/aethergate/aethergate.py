"""AetherGate — futuristic per-channel role access control for Red."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_list, pagify

from .constants import (
    ACCENT,
    ACCENT_OK,
    ACCENT_WARN,
    AUDIT_PREFIX,
    PRESET_META,
    PRESETS,
    SIGNAL_ORDER,
    SIGNALS,
    empty_template,
    state_glyph,
)
from .views import ConfirmView, LatticeView

log = logging.getLogger("red.aethergate.aethergate")

__red_end_user_data_statement__ = (
    "This cog stores the Discord user ID of whoever created or adopted a managed "
    "role, plus the role ID, optional colour, and the last permission template "
    "applied to channels. No message content is stored. Requested deletions clear "
    "the stored creator ID; role and channel overwrite records remain because they "
    "are server configuration, not end-user data."
)

CHANNEL_TOKEN_RE = re.compile(
    r"<#(?P<mention>\d{15,25})>|(?P<raw>\d{15,25})|#(?P<name>[^\s#]{1,100})"
)


class AetherGate(commands.Cog):
    """Forge access roles and paint per-channel View / Speak / Embed / Pics overwrites.

    AetherGate keeps a lattice of managed roles. Each role has a signal matrix
    (allow / deny / inherit) that operators commit onto selected channels —
    either by picking them, pasting `#channel #channel #channel`, or walking
    channel-by-channel in the Channel Lab.
    """

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=20260907133742, force_registration=True
        )
        self.config.register_guild(roles={})

    async def red_delete_data_for_user(self, *, requester: str, user_id: int) -> None:
        all_guilds = await self.config.all_guilds()
        for gid, data in all_guilds.items():
            roles = data.get("roles", {})
            changed = False
            for payload in roles.values():
                if payload.get("created_by") == user_id:
                    payload["created_by"] = None
                    changed = True
            if changed:
                await self.config.guild_from_id(gid).roles.set(roles)

    # ------------------------------------------------------------------
    # Hierarchy / safety
    # ------------------------------------------------------------------
    @staticmethod
    def bot_outranks(guild: discord.Guild, role: discord.Role) -> bool:
        return guild.me.top_role > role

    @staticmethod
    def user_outranks(member: discord.Member, role: discord.Role) -> bool:
        return member == member.guild.owner or member.top_role > role

    async def guard_role(
        self, ctx: commands.Context, role: discord.Role, *, creating: bool = False
    ) -> bool:
        if role.is_default() or role.managed:
            await ctx.send("That role is owned by Discord or an integration. Leave it alone.")
            return False
        if not creating and not self.user_outranks(ctx.author, role):
            await ctx.send("Your highest role does not outrank that node. Hierarchy holds.")
            return False
        if not self.bot_outranks(ctx.guild, role) and not creating:
            await ctx.send("My highest role does not outrank that node. Move me up the stack.")
            return False
        if not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.send("I need **Manage Roles**.")
            return False
        return True

    async def is_managed(self, guild: discord.Guild, role: discord.Role) -> bool:
        roles = await self.config.guild(guild).roles()
        return str(role.id) in roles

    async def require_managed(self, ctx: commands.Context, role: discord.Role) -> bool:
        if await self.is_managed(ctx.guild, role):
            return True
        await ctx.send(
            f"{role.mention} is not on the lattice. Use `{ctx.clean_prefix}agate adopt` first."
        )
        return False

    # ------------------------------------------------------------------
    # Config helpers
    # ------------------------------------------------------------------
    async def role_payload(self, guild: discord.Guild, role: discord.Role) -> dict:
        roles = await self.config.guild(guild).roles()
        return roles.get(str(role.id), {})

    async def upsert_role(
        self,
        guild: discord.Guild,
        role: discord.Role,
        *,
        created_by: Optional[int],
        template: Optional[dict] = None,
    ) -> None:
        async with self.config.guild(guild).roles() as roles:
            current = roles.get(str(role.id), {})
            current.update(
                {
                    "name": role.name,
                    "created_by": current.get("created_by") or created_by,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "template": template if template is not None else current.get("template", empty_template()),
                }
            )
            if "created_at" not in current:
                current["created_at"] = datetime.now(timezone.utc).isoformat()
            roles[str(role.id)] = current

    async def store_template(
        self, guild: discord.Guild, role: discord.Role, template: Dict[str, Optional[bool]]
    ) -> None:
        await self.upsert_role(guild, role, created_by=None, template=template)

    async def drop_role(self, guild: discord.Guild, role_id: int) -> None:
        async with self.config.guild(guild).roles() as roles:
            roles.pop(str(role_id), None)

    async def load_template(self, guild: discord.Guild, role: discord.Role) -> Dict[str, Optional[bool]]:
        payload = await self.role_payload(guild, role)
        stored = payload.get("template") or empty_template()
        merged = empty_template()
        merged.update({k: stored.get(k) for k in SIGNAL_ORDER})
        return merged

    # ------------------------------------------------------------------
    # Channel parsing + overwrite writes
    # ------------------------------------------------------------------
    async def resolve_channel_blob(
        self, guild: discord.Guild, blob: str
    ) -> List[discord.abc.GuildChannel]:
        found: Dict[int, discord.abc.GuildChannel] = {}
        lowered = {ch.name.lower(): ch for ch in guild.channels}

        for match in CHANNEL_TOKEN_RE.finditer(blob):
            mention = match.group("mention")
            raw = match.group("raw")
            name = match.group("name")
            channel = None
            if mention or raw:
                channel = guild.get_channel(int(mention or raw))
            elif name:
                channel = lowered.get(name.lower())
            if channel is not None:
                found[channel.id] = channel

        # Also accept bare names that the regex might miss after commas
        for token in re.split(r"[\s,;]+", blob):
            token = token.strip().lstrip("#")
            if token and token.lower() in lowered:
                ch = lowered[token.lower()]
                found[ch.id] = ch

        return list(found.values())

    def template_to_overwrite(
        self, template: Dict[str, Optional[bool]]
    ) -> discord.PermissionOverwrite:
        overwrite = discord.PermissionOverwrite()
        payload = {}
        for key, value in template.items():
            if key not in SIGNALS:
                continue
            payload[SIGNALS[key].attr] = value
        overwrite.update(**payload)
        return overwrite

    async def paint_single(
        self,
        *,
        channel: discord.abc.GuildChannel,
        role: discord.Role,
        actor: discord.abc.User,
        updates: Dict[str, Optional[bool]],
    ) -> None:
        current = channel.overwrites_for(role)
        current.update(**updates)
        reason = f"{AUDIT_PREFIX} edit by {actor} ({actor.id})"
        if current.is_empty():
            await channel.set_permissions(role, overwrite=None, reason=reason)
        else:
            await channel.set_permissions(role, overwrite=current, reason=reason)

    async def commit_template(
        self,
        *,
        guild: discord.Guild,
        actor: discord.Member,
        role: discord.Role,
        template: Dict[str, Optional[bool]],
        channel_ids: Sequence[int],
    ) -> Tuple[int, int, int]:
        overwrite = self.template_to_overwrite(template)
        reason = f"{AUDIT_PREFIX} commit by {actor} ({actor.id})"
        ok = skipped = errors = 0

        me = guild.me
        for index, cid in enumerate(channel_ids):
            channel = guild.get_channel(cid)
            if channel is None:
                skipped += 1
                continue
            perms = channel.permissions_for(me)
            if not (perms.manage_roles or perms.administrator):
                skipped += 1
                continue
            try:
                if overwrite.is_empty():
                    await channel.set_permissions(role, overwrite=None, reason=reason)
                else:
                    await channel.set_permissions(role, overwrite=overwrite, reason=reason)
                ok += 1
            except (discord.Forbidden, discord.HTTPException) as exc:
                errors += 1
                log.warning("Failed overwrite on %s (%s): %s", channel.id, guild.id, exc)
            if index and index % 8 == 0:
                await asyncio.sleep(1.1)
        return ok, skipped, errors

    async def rename_managed_role(
        self, interaction: discord.Interaction, role: discord.Role, new_name: str
    ) -> Optional[str]:
        """Rename a lattice role. Returns an error string, or None on success."""
        new_name = new_name.strip()
        if not new_name:
            return "Name cannot be empty."
        member = interaction.user
        if not isinstance(member, discord.Member) or interaction.guild is None:
            return "Rename is guild-only."
        if not self.user_outranks(member, role) or not self.bot_outranks(interaction.guild, role):
            return "Hierarchy rejected the rename."
        try:
            await role.edit(
                name=new_name,
                reason=f"{AUDIT_PREFIX} rename by {member} ({member.id})",
            )
        except discord.Forbidden:
            return "I cannot edit that role."
        except discord.HTTPException as exc:
            return f"Rename failed: {exc}"
        await self.upsert_role(interaction.guild, role, created_by=member.id)
        return None

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    @commands.group(name="aethergate", aliases=("agate", "lattice"), invoke_without_command=True)
    @commands.guild_only()
    @commands.admin_or_permissions(manage_roles=True, manage_channels=True)
    @commands.bot_has_permissions(manage_roles=True, manage_channels=True, embed_links=True)
    async def aethergate(self, ctx: commands.Context) -> None:
        """Open the AetherGate holopanel, or run a subcommand.

        Use `[p]agate create <name>` first if the lattice is empty.
        """
        roles = await self.config.guild(ctx.guild).roles()
        live = []
        for rid in roles:
            role = ctx.guild.get_role(int(rid))
            if role:
                live.append(role)
        if not live:
            await ctx.send(
                f"Lattice is empty. Forge a node with `{ctx.clean_prefix}agate create <name>`."
            )
            return
        role = live[0] if len(live) == 1 else None
        if role is None:
            listing = "\n".join(f"• {r.mention} `{r.id}`" for r in live[:20])
            await ctx.send(
                f"Multiple nodes on the lattice. Open one with "
                f"`{ctx.clean_prefix}agate panel @Role`.\n{listing}"
            )
            return
        await self._open_panel(ctx, role)

    @aethergate.command(name="create")
    async def agate_create(self, ctx: commands.Context, *, name: str) -> None:
        """Forge a new access role and bind it to the lattice.

        The role is created with no extra guild permissions. Channel power
        is painted later through the panel.
        """
        name = name.strip()
        if not name or len(name) > 100:
            await ctx.send("Give the node a name between 1 and 100 characters.")
            return
        if not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.send("I need **Manage Roles** to forge a node.")
            return
        if any(r.name.lower() == name.lower() for r in ctx.guild.roles):
            await ctx.send("A role with that name already exists. Adopt it or pick another name.")
            return
        try:
            role = await ctx.guild.create_role(
                name=name,
                colour=discord.Colour(ACCENT),
                mentionable=False,
                hoist=False,
                permissions=discord.Permissions.none(),
                reason=f"{AUDIT_PREFIX} forge by {ctx.author} ({ctx.author.id})",
            )
        except discord.Forbidden:
            await ctx.send("Discord forbade the create. Check my role position.")
            return
        except discord.HTTPException as exc:
            await ctx.send(f"Create failed: {exc}")
            return

        await self.upsert_role(
            ctx.guild, role, created_by=ctx.author.id, template=empty_template()
        )
        embed = discord.Embed(
            title="NODE FORGED",
            colour=ACCENT_OK,
            description=(
                f"{role.mention} is on the lattice.\n"
                f"Open the holopanel with `{ctx.clean_prefix}agate panel {role.name}`."
            ),
        )
        await ctx.send(embed=embed)
        await self._open_panel(ctx, role)

    @aethergate.command(name="adopt")
    async def agate_adopt(self, ctx: commands.Context, role: discord.Role) -> None:
        """Bind an existing role to the lattice so it can be edited here."""
        if not await self.guard_role(ctx, role):
            return
        await self.upsert_role(ctx.guild, role, created_by=ctx.author.id)
        await ctx.send(f"Adopted {role.mention}. Opening lattice…")
        await self._open_panel(ctx, role)

    @aethergate.command(name="panel", aliases=("edit", "holo"))
    async def agate_panel(self, ctx: commands.Context, role: discord.Role) -> None:
        """Open the interactive lattice for a managed role."""
        if not await self.guard_role(ctx, role):
            return
        if not await self.is_managed(ctx.guild, role):
            await self.upsert_role(ctx.guild, role, created_by=ctx.author.id)
        await self._open_panel(ctx, role)

    async def _open_panel(self, ctx: commands.Context, role: discord.Role) -> None:
        template = await self.load_template(ctx.guild, role)
        view = LatticeView(self, ctx.author, role, template)
        message = await ctx.send(embed=view.build_embed(), view=view)
        view.message = message

    @aethergate.command(name="rename")
    async def agate_rename(
        self, ctx: commands.Context, role: discord.Role, *, new_name: str
    ) -> None:
        """Rename a managed role."""
        if not await self.guard_role(ctx, role):
            return
        if not await self.require_managed(ctx, role):
            return
        new_name = new_name.strip()
        if not new_name or len(new_name) > 100:
            await ctx.send("Name must be 1–100 characters.")
            return
        try:
            await role.edit(
                name=new_name,
                reason=f"{AUDIT_PREFIX} rename by {ctx.author} ({ctx.author.id})",
            )
        except discord.HTTPException as exc:
            await ctx.send(f"Rename failed: {exc}")
            return
        await self.upsert_role(ctx.guild, role, created_by=ctx.author.id)
        await ctx.send(f"Node retitled to **{role.name}**.")

    @aethergate.command(name="apply")
    async def agate_apply(
        self, ctx: commands.Context, role: discord.Role, *, channels: str
    ) -> None:
        """Commit the stored template onto typed channels.

        Accepts mentions, raw IDs, or names:
        `[p]agate apply @Guests #general #media #voice-lab`
        """
        if not await self.guard_role(ctx, role):
            return
        if not await self.require_managed(ctx, role):
            return
        parsed = await self.resolve_channel_blob(ctx.guild, channels)
        # Mentions on the invocation message are authoritative extras
        for ch in ctx.message.channel_mentions:
            if ch.id not in {c.id for c in parsed}:
                parsed.append(ch)
        if not parsed:
            await ctx.send("No channels resolved from that input.")
            return
        template = await self.load_template(ctx.guild, role)
        async with ctx.typing():
            ok, skipped, errors = await self.commit_template(
                guild=ctx.guild,
                actor=ctx.author,
                role=role,
                template=template,
                channel_ids=[c.id for c in parsed],
            )
        await ctx.send(
            f"Pulse complete for {role.mention}: wrote **{ok}**, skipped `{skipped}`, errors `{errors}`."
        )

    @aethergate.command(name="preset")
    async def agate_preset(
        self, ctx: commands.Context, role: discord.Role, preset: str, *, channels: str = ""
    ) -> None:
        """Load a named preset onto the role template, optionally committing it.

        Presets: `observer`, `talker`, `media`, `voice`, `ghost`, `clear`

        Example:
        `[p]agate preset @Guests media #general #clips #art`
        """
        if not await self.guard_role(ctx, role):
            return
        if not await self.require_managed(ctx, role):
            return
        key = preset.lower().strip()
        if key not in PRESETS:
            names = humanize_list(list(PRESETS))
            await ctx.send(f"Unknown preset. Choose from {names}.")
            return
        template = dict(PRESETS[key])
        await self.store_template(ctx.guild, role, template)
        label = PRESET_META[key][0]
        if not channels.strip() and not ctx.message.channel_mentions:
            await ctx.send(
                f"Loaded **{label}** onto {role.mention}. "
                f"Commit it with `{ctx.clean_prefix}agate apply` or the panel."
            )
            return
        parsed = await self.resolve_channel_blob(ctx.guild, channels)
        for ch in ctx.message.channel_mentions:
            if ch.id not in {c.id for c in parsed}:
                parsed.append(ch)
        async with ctx.typing():
            ok, skipped, errors = await self.commit_template(
                guild=ctx.guild,
                actor=ctx.author,
                role=role,
                template=template,
                channel_ids=[c.id for c in parsed],
            )
        await ctx.send(
            f"**{label}** written through {role.mention}: **{ok}** ok, `{skipped}` skipped, `{errors}` errors."
        )

    @aethergate.command(name="scan")
    async def agate_scan(self, ctx: commands.Context, role: discord.Role) -> None:
        """Read live overwrites for a role across the guild."""
        if not await self.guard_role(ctx, role):
            return
        lines = []
        for channel in sorted(ctx.guild.channels, key=lambda c: (c.position, c.id)):
            if role not in channel.overwrites:
                continue
            ow = channel.overwrites_for(role)
            bits = []
            for key in SIGNAL_ORDER:
                value = getattr(ow, SIGNALS[key].attr)
                if value is None:
                    continue
                bits.append(f"{SIGNALS[key].emoji}{state_glyph(value).split()[0]}")
            if not bits and ow.is_empty():
                continue
            detail = " ".join(bits) if bits else "empty-custom"
            lines.append(f"{channel.mention} — {detail}")
        if not lines:
            await ctx.send(f"No channel overwrites exist for {role.mention}.")
            return
        header = f"LIVE SCAN  //  {role.name}\n"
        text = header + "\n".join(lines)
        for page in pagify(text, delims=["\n"], page_length=1800):
            await ctx.send(page)

    @aethergate.command(name="list")
    async def agate_list(self, ctx: commands.Context) -> None:
        """List roles currently bound to the lattice."""
        stored = await self.config.guild(ctx.guild).roles()
        if not stored:
            await ctx.send("Lattice is empty.")
            return
        lines = []
        stale = []
        for rid, payload in stored.items():
            role = ctx.guild.get_role(int(rid))
            if role is None:
                stale.append(rid)
                lines.append(f"• `{rid}` — *ghost record* (`{payload.get('name', '?')}`)")
                continue
            lines.append(f"• {role.mention} `{role.id}` — {len(role.members)} members")
        embed = discord.Embed(
            title="AETHERGATE  //  BOUND NODES",
            colour=ACCENT,
            description="\n".join(lines)[:4000],
        )
        await ctx.send(embed=embed)
        if stale:
            async with self.config.guild(ctx.guild).roles() as roles:
                for rid in stale:
                    roles.pop(rid, None)

    @aethergate.command(name="untrack")
    async def agate_untrack(self, ctx: commands.Context, role: discord.Role) -> None:
        """Remove a role from the lattice without deleting it from Discord."""
        if not await self.require_managed(ctx, role):
            return
        await self.drop_role(ctx.guild, role.id)
        await ctx.send(f"{role.mention} released from the lattice. Discord role left intact.")

    @aethergate.command(name="delete")
    async def agate_delete(self, ctx: commands.Context, role: discord.Role) -> None:
        """Delete a managed role from Discord after confirmation."""
        if not await self.guard_role(ctx, role):
            return
        if not await self.require_managed(ctx, role):
            return
        view = ConfirmView(ctx.author.id)
        prompt = await ctx.send(
            embed=discord.Embed(
                title="IRREVERSIBLE PULSE",
                colour=ACCENT_WARN,
                description=f"Delete {role.mention} from Discord and drop it from the lattice?",
            ),
            view=view,
        )
        await view.wait()
        for child in view.children:
            child.disabled = True
        if not view.value:
            await prompt.edit(content="Aborted.", embed=None, view=view)
            return
        try:
            await role.delete(reason=f"{AUDIT_PREFIX} delete by {ctx.author} ({ctx.author.id})")
        except discord.HTTPException as exc:
            await prompt.edit(content=f"Delete failed: {exc}", embed=None, view=view)
            return
        await self.drop_role(ctx.guild, role.id)
        await prompt.edit(content="Node destroyed.", embed=None, view=view)

    @aethergate.command(name="signals")
    async def agate_signals(self, ctx: commands.Context) -> None:
        """Show the permission signals this cog can paint."""
        lines = [
            f"{SIGNALS[k].emoji} **{SIGNALS[k].label}** `{SIGNALS[k].attr}` — {SIGNALS[k].blurb}"
            for k in SIGNAL_ORDER
        ]
        embed = discord.Embed(
            title="SIGNAL CATALOGUE",
            colour=ACCENT,
            description="\n".join(lines),
        )
        embed.add_field(
            name="Presets",
            value="\n".join(
                f"{meta[1]} `{key}` — {meta[0]}: {meta[2]}" for key, meta in PRESET_META.items()
            ),
            inline=False,
        )
        await ctx.send(embed=embed)
