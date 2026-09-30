"""Optional Red-Web-Dashboard integration. The cog still loads if Dashboard is absent."""

from __future__ import annotations

import os
from typing import Any

import discord
from redbot.core import commands
from redbot.core.bot import Red


def dashboard_page(*args, **kwargs):
    def decorator(func):
        func.__dashboard_decorator_params__ = (args, kwargs)
        return func

    return decorator


class DashboardIntegration:
    bot: Red

    @commands.Cog.listener()
    async def on_dashboard_cog_add(self, dashboard_cog: commands.Cog) -> None:
        rpc = getattr(dashboard_cog, "rpc", None)
        handler = getattr(rpc, "third_parties_handler", None) if rpc else None
        if handler is not None:
            handler.add_third_party(self)

    @dashboard_page(name=None, description="Create rich Embeds!")
    async def dashboard_editor(self, **kwargs) -> dict[str, Any]:
        file_path = os.path.join(os.path.dirname(__file__), "editor.html")
        with open(file_path, encoding="utf-8") as handle:
            source = handle.read()
        return {"status": 0, "web_content": {"source": source, "standalone": True}}

    @dashboard_page(
        name="guild",
        description="Create rich Embeds and send them to a guild!",
        methods=("GET", "POST"),
    )
    async def dashboard_guild(self, member: discord.Member, guild: discord.Guild, **kwargs):
        is_owner = member.id in getattr(self.bot, "owner_ids", ())
        if (
            not is_owner
            and not await self.bot.is_mod(member)
            and not member.guild_permissions.manage_guild
        ):
            return {
                "status": 0,
                "error_code": 403,
                "message": "You don't have permissions to access this page.",
            }
        file_path = os.path.join(os.path.dirname(__file__), "editor.html")
        with open(file_path, encoding="utf-8") as handle:
            source = handle.read()
        return {"status": 0, "web_content": {"source": source, "standalone": True}}
