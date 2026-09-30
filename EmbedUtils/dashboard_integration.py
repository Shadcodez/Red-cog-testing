"""Optional Red-Web-Dashboard integration. The cog still loads if Dashboard is absent."""

from __future__ import annotations

import os
from typing import Any

import discord
from redbot.core import commands
from redbot.core.bot import Red

from .converters import ListStringToEmbed


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
        is_owner = member.id in self.bot.owner_ids
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
        get_sorted = kwargs.get("get_sorted_channels")
        channels = get_sorted(guild) if callable(get_sorted) else []
        if not channels:
            return {
                "status": 0,
                "error_code": 403,
                "message": "No sendable embed channels were found in this guild.",
            }

        file_path = os.path.join(os.path.dirname(__file__), "editor.html")
        with open(file_path, encoding="utf-8") as handle:
            source = handle.read()

        try:
            import wtforms
        except ImportError:
            return {"status": 0, "web_content": {"source": source, "standalone": True}}

        form_cls = kwargs.get("Form")
        if form_cls is None:
            return {"status": 0, "web_content": {"source": source, "standalone": True}}

        class SendForm(form_cls):
            def __init__(self) -> None:
                super().__init__(prefix="send_form_")

            username = wtforms.HiddenField(
                "Username:",
                validators=[wtforms.validators.Optional(), wtforms.validators.Length(max=80)],
            )
            avatar = wtforms.HiddenField(
                "Avatar URL:",
                validators=[wtforms.validators.Optional()],
            )
            data = wtforms.HiddenField(
                "Data",
                validators=[wtforms.validators.DataRequired()],
            )
            channels = wtforms.SelectMultipleField(
                "Channels:",
                choices=[],
                validators=[wtforms.validators.DataRequired()],
            )
            submit = wtforms.SubmitField("Send Message(s)")

        send_form = SendForm()
        send_form.channels.choices = channels
        if send_form.validate_on_submit():
            notifications = []
            raw = send_form.data.data
            try:
                payload = await ListStringToEmbed().convert(
                    type("Ctx", (), {"command": None, "clean_prefix": "[", "channel": guild.system_channel, "embed_color": lambda: discord.Color.blue()})(),
                    raw,
                )
            except Exception as error:
                return {
                    "status": 0,
                    "notifications": [{"message": f"Invalid embed data: {error}", "category": "error"}],
                    "web_content": {"source": source, "standalone": True},
                }
            channel_objects = []
            for value in send_form.channels.data:
                channel = guild.get_channel(int(value)) if str(value).isdigit() else None
                if channel is not None:
                    channel_objects.append(channel)
            for channel in channel_objects:
                try:
                    if send_form.username.data or send_form.avatar.data:
                        webhook = await channel.create_webhook(
                            name=send_form.username.data or guild.me.display_name,
                            reason="EmbedUtils dashboard send",
                        )
                        try:
                            await webhook.send(
                                username=send_form.username.data or None,
                                avatar_url=send_form.avatar.data or None,
                                **payload,
                            )
                        finally:
                            await webhook.delete()
                    else:
                        await channel.send(**payload)
                    notifications.append({"message": f"Sent to {channel.mention}", "category": "success"})
                except discord.HTTPException as error:
                    notifications.append({"message": f"{channel}: {error}", "category": "error"})
            return {
                "status": 0,
                "notifications": notifications,
                "web_content": {"source": source, "standalone": True},
            }
        return {"status": 0, "web_content": {"source": source, "standalone": True}}
