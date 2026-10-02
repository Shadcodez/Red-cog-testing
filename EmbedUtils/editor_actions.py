"""Extra maker actions that do not consume the editor's five component rows."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import discord


def parse_when(raw: str) -> datetime:
    text = (raw or "").strip()
    if not text or text.lower() == "now":
        return datetime.now(timezone.utc) + timedelta(minutes=5)
    moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


class StoreNameModal(discord.ui.Modal, title="Save embed"):
    name = discord.ui.TextInput(label="Stored name", max_length=50, required=True)
    scope = discord.ui.TextInput(label="Global? yes/no", max_length=5, default="no", required=False)

    def __init__(self, cog, editor, *, update: bool):
        super().__init__(title="Update stored embed" if update else "Store embed")
        self.cog = cog
        self.editor = editor
        self.update = update

    async def on_submit(self, interaction: discord.Interaction) -> None:
        name = str(self.name.value).strip()
        global_level = str(self.scope.value or "").strip().lower() in {"1", "yes", "y", "true", "on"}
        if global_level and not await self.cog.bot.is_owner(interaction.user):
            await interaction.response.send_message("Only the bot owner can save global embeds.", ephemeral=True)
            return
        if self.update and not await self.cog.store.get(interaction.guild, name, global_level):
            await interaction.response.send_message(f"`{name}` is not stored yet. Use Store instead.", ephemeral=True)
            return
        embed = getattr(self.editor, "embed", None)
        if embed is None:
            await interaction.response.send_message("This builder has no embed to save.", ephemeral=True)
            return
        try:
            await self.cog.store.save(
                guild=interaction.guild,
                name=name,
                embed=embed,
                author_id=interaction.user.id,
                global_level=global_level,
                content=getattr(self.editor, "content", None),
            )
        except Exception as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        verb = "Updated" if self.update else "Stored"
        await interaction.response.send_message(f"{verb} `{name}`.", ephemeral=True)


class ServerEventModal(discord.ui.Modal, title="Create server event"):
    name = discord.ui.TextInput(label="Event name", max_length=100, required=True)
    start = discord.ui.TextInput(label="Start (ISO or now)", max_length=40, default="now", required=True)
    end = discord.ui.TextInput(label="End (ISO, optional)", max_length=40, required=False)
    location = discord.ui.TextInput(label="Location", max_length=100, default="Discord", required=True)

    def __init__(self, cog, embed: discord.Embed, channel: Optional[discord.abc.Messageable]):
        super().__init__()
        self.cog = cog
        self.embed = embed
        self.channel = channel
        if embed.title:
            self.name.default = embed.title[:100]

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            start = parse_when(str(self.start.value))
            end_raw = str(self.end.value or "").strip()
            end = parse_when(end_raw) if end_raw else start + timedelta(hours=1)
        except ValueError:
            await interaction.response.send_message("Use `now` or an ISO-8601 time.", ephemeral=True)
            return
        if end <= start:
            end = start + timedelta(hours=1)
        try:
            event = await self.cog.create_server_event(
                interaction.guild,
                name=str(self.name.value)[:100],
                description=(self.embed.description or "")[:1000] or None,
                start=start,
                end=end,
                location=str(self.location.value)[:100] or "Discord",
            )
        except discord.Forbidden:
            await interaction.response.send_message("I need Manage Events to create a server event.", ephemeral=True)
            return
        except discord.HTTPException as error:
            await interaction.response.send_message(f"Discord rejected the event: {error}", ephemeral=True)
            return
        if self.channel is not None:
            try:
                await self.channel.send(embed=self.embed)
            except discord.HTTPException:
                pass
        await interaction.response.send_message(f"Server event created: {event.url}", ephemeral=True)


class MakerActions(discord.ui.View):
    def __init__(self, cog, editor, channel: Optional[discord.abc.Messageable]):
        super().__init__(timeout=600)
        self.cog = cog
        self.editor = editor
        self.channel = channel

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        author = getattr(self.editor, "context", None)
        expected = getattr(author, "author", None)
        if expected and interaction.user.id != expected.id:
            await interaction.response.send_message("This builder is not yours.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Store", style=discord.ButtonStyle.success)
    async def store(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(StoreNameModal(self.cog, self.editor, update=False))

    @discord.ui.button(label="Update stored", style=discord.ButtonStyle.primary)
    async def update(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(StoreNameModal(self.cog, self.editor, update=True))

    @discord.ui.button(label="Event embed", style=discord.ButtonStyle.secondary)
    async def event_embed(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = getattr(self.editor, "embed", None)
        if embed is None:
            await interaction.response.send_message("No embed to post.", ephemeral=True)
            return
        dest = self.channel or interaction.channel
        try:
            await dest.send(embed=embed, content=getattr(self.editor, "content", None))
        except discord.HTTPException as error:
            await interaction.response.send_message(f"Could not post the event embed: {error}", ephemeral=True)
            return
        await interaction.response.send_message("Event embed posted.", ephemeral=True)

    @discord.ui.button(label="Server event", style=discord.ButtonStyle.secondary)
    async def server_event(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = getattr(self.editor, "embed", None)
        if embed is None or interaction.guild is None:
            await interaction.response.send_message("Server events can only be created in a guild.", ephemeral=True)
            return
        await interaction.response.send_modal(
            ServerEventModal(self.cog, embed, self.channel or interaction.channel)
        )
