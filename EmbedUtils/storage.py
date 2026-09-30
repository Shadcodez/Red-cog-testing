"""Isolated Config + one-time import from Phen and AAA3A EmbedUtils."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import discord
from redbot.core import Config

# Fresh identity — this cog does not share a Config namespace with either parent.
IDENTIFIER = 0xE4B3D01115

PHEN_IDENTIFIER = 43248937299564234735284
AAA3A_IDENTIFIER = 205192943327321000143939875896557571750

DEFAULT_GUILD_LIMIT = 100
DEFAULT_GLOBAL_LIMIT = 100


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_entry(raw: Any, *, fallback_author: Optional[int] = None) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    embed = raw.get("embed", raw)
    if isinstance(embed, discord.Embed):
        embed = embed.to_dict()
    if not isinstance(embed, dict):
        return None
    entry = {
        "author": raw.get("author", fallback_author),
        "uses": int(raw.get("uses") or 0),
        "locked": bool(raw.get("locked")),
        "embed": embed,
        "updated_at": raw.get("updated_at") or utcnow_iso(),
    }
    if raw.get("content"):
        entry["content"] = raw["content"]
    if raw.get("created_at"):
        entry["created_at"] = raw["created_at"]
    else:
        entry["created_at"] = entry["updated_at"]
    return entry


class EmbedStore:
    def __init__(self, cog_instance) -> None:
        self.config = Config.get_conf(cog_instance, identifier=IDENTIFIER, force_registration=True)
        self.config.register_global(
            embeds={},
            schema=1,
            migrated={"phen": False, "aaa3a": False},
            guild_limit=DEFAULT_GUILD_LIMIT,
            global_limit=DEFAULT_GLOBAL_LIMIT,
        )
        self.config.register_guild(embeds={})

    def group(self, guild: Optional[discord.Guild], global_level: bool):
        if global_level:
            return self.config
        if guild is None:
            raise RuntimeError("Guild storage requires a guild.")
        return self.config.guild(guild)

    async def all_embeds(self, guild: Optional[discord.Guild], global_level: bool) -> dict:
        return await self.group(guild, global_level).embeds()

    async def get(self, guild: Optional[discord.Guild], name: str, global_level: bool) -> Optional[dict]:
        return (await self.all_embeds(guild, global_level)).get(name)

    async def visible(
        self,
        guild: Optional[discord.Guild],
        global_level: bool,
        *,
        viewer: Optional[discord.abc.User] = None,
        is_owner: bool = False,
    ) -> dict[str, dict]:
        store = await self.all_embeds(guild, global_level)
        if not global_level or is_owner:
            return store
        return {name: entry for name, entry in store.items() if not entry.get("locked")}

    async def limit(self, global_level: bool) -> int:
        if global_level:
            return int(await self.config.global_limit())
        return int(await self.config.guild_limit())

    async def save(
        self,
        *,
        guild: Optional[discord.Guild],
        name: str,
        embed: discord.Embed,
        author_id: int,
        global_level: bool = False,
        locked: bool = False,
        content: Optional[str] = None,
    ) -> dict:
        store = await self.all_embeds(guild, global_level)
        cap = await self.limit(global_level)
        if name not in store and len(store) >= cap:
            raise ValueError(
                f"Storage is full ({cap}). Delete an embed before saving another."
            )
        existing = store.get(name) or {}
        entry = {
            "author": author_id,
            "uses": int(existing.get("uses") or 0),
            "locked": bool(locked),
            "embed": embed.to_dict(),
            "created_at": existing.get("created_at") or utcnow_iso(),
            "updated_at": utcnow_iso(),
        }
        if content:
            entry["content"] = content
        async with self.group(guild, global_level).embeds() as stored:
            stored[name] = entry
        return entry

    async def delete(self, guild: Optional[discord.Guild], name: str, global_level: bool) -> bool:
        async with self.group(guild, global_level).embeds() as stored:
            return stored.pop(name, None) is not None

    async def bump(self, guild: Optional[discord.Guild], name: str, global_level: bool) -> None:
        async with self.group(guild, global_level).embeds() as stored:
            if name in stored:
                stored[name]["uses"] = int(stored[name].get("uses") or 0) + 1

    async def purge_author(self, user_id: int) -> None:
        async with self.config.embeds() as stored:
            for name in [n for n, e in stored.items() if e.get("author") == user_id]:
                stored.pop(name, None)
        all_guilds = await self.config.all_guilds()
        for guild_id, data in all_guilds.items():
            embeds = data.get("embeds") or {}
            doomed = [n for n, e in embeds.items() if e.get("author") == user_id]
            if not doomed:
                continue
            async with self.config.guild_from_id(guild_id).embeds() as stored:
                for name in doomed:
                    stored.pop(name, None)

    async def import_legacy(self) -> dict[str, int]:
        """Copy missing names from Phen and AAA3A. Never overwrites local data."""
        flags = await self.config.migrated()
        stats = {"phen_guild": 0, "phen_global": 0, "aaa3a_guild": 0, "aaa3a_global": 0}
        if not flags.get("phen"):
            stats.update(await self._import_phen())
            flags["phen"] = True
        if not flags.get("aaa3a"):
            extra = await self._import_aaa3a()
            stats["aaa3a_guild"] = extra["aaa3a_guild"]
            stats["aaa3a_global"] = extra["aaa3a_global"]
            flags["aaa3a"] = True
        await self.config.migrated.set(flags)
        return stats

    async def _merge(self, dest_group, incoming: dict) -> int:
        if not incoming:
            return 0
        copied = 0
        async with dest_group.embeds() as dest:
            for name, raw in incoming.items():
                if name in dest:
                    continue
                entry = normalize_entry(raw)
                if entry is None:
                    continue
                dest[name] = entry
                copied += 1
        return copied

    async def _import_phen(self) -> dict[str, int]:
        foreign = Config.get_conf(None, identifier=PHEN_IDENTIFIER, cog_name="EmbedUtils", force_registration=True)
        foreign.register_global(embeds={})
        foreign.register_guild(embeds={})
        global_copied = await self._merge(self.config, await foreign.embeds())
        guild_copied = 0
        for guild_id, data in (await foreign.all_guilds()).items():
            guild_copied += await self._merge(self.config.guild_from_id(guild_id), data.get("embeds") or {})
        return {"phen_guild": guild_copied, "phen_global": global_copied}

    async def _import_aaa3a(self) -> dict[str, int]:
        foreign = Config.get_conf(None, identifier=AAA3A_IDENTIFIER, cog_name="EmbedUtils", force_registration=True)
        foreign.register_global(stored_embeds={})
        foreign.register_guild(stored_embeds={})
        global_copied = await self._merge(self.config, await foreign.stored_embeds())
        guild_copied = 0
        for guild_id, data in (await foreign.all_guilds()).items():
            guild_copied += await self._merge(
                self.config.guild_from_id(guild_id), data.get("stored_embeds") or {}
            )
        return {"aaa3a_guild": guild_copied, "aaa3a_global": global_copied}
