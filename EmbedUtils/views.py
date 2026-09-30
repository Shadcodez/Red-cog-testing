"""Interactive Discord UI: buttons, modals, and dropdowns for EmbedUtils."""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

import discord
from redbot.core.utils.chat_formatting import box, text_to_file

MAX_MODAL = 4000


class EmbedFieldModal(discord.ui.Modal):
    def __init__(self, view: "EmbedBuilderView", *, index: Optional[int] = None):
        title = "Edit Field" if index is not None else "Add Field"
        super().__init__(title=title)
        self.view_ref = view
        self.index = index
        existing = None
        if index is not None and 0 <= index < len(view.embed.fields):
            existing = view.embed.fields[index]
        self.name_input = discord.ui.TextInput(
            label="Field name",
            max_length=256,
            required=True,
            default=(existing.name if existing else None),
        )
        self.value_input = discord.ui.TextInput(
            label="Field value",
            style=discord.TextStyle.paragraph,
            max_length=1024,
            required=True,
            default=(existing.value if existing else None),
        )
        self.inline_input = discord.ui.TextInput(
            label="Inline? (yes/no)",
            max_length=5,
            required=False,
            default=("yes" if existing and existing.inline else "no"),
        )
        self.add_item(self.name_input)
        self.add_item(self.value_input)
        self.add_item(self.inline_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        inline = self.inline_input.value.strip().lower() in {"1", "true", "yes", "y", "on"}
        if self.index is None:
            if len(self.view_ref.embed.fields) >= 25:
                await interaction.response.send_message("Embeds can have at most 25 fields.", ephemeral=True)
                return
            self.view_ref.embed.add_field(
                name=str(self.name_input.value),
                value=str(self.value_input.value),
                inline=inline,
            )
        else:
            self.view_ref.embed.set_field_at(
                self.index,
                name=str(self.name_input.value),
                value=str(self.value_input.value),
                inline=inline,
            )
        await self.view_ref.refresh(interaction)


class SimpleModal(discord.ui.Modal):
    def __init__(self, title: str, inputs: List[discord.ui.TextInput], callback: Callable):
        super().__init__(title=title)
        self.callback = callback
        self.inputs = inputs
        for item in inputs:
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        values = {item.label: str(item.value) if item.value is not None else "" for item in self.inputs}
        await self.callback(interaction, values)


class PopupCreateModal(discord.ui.Modal, title="Create embed"):
    title_input = discord.ui.TextInput(label="Title", max_length=256, required=False)
    description_input = discord.ui.TextInput(
        label="Description",
        style=discord.TextStyle.paragraph,
        max_length=4000,
        required=False,
    )
    color_input = discord.ui.TextInput(
        label="Color (hex like #5865F2)",
        max_length=16,
        required=False,
        placeholder="#5865F2",
    )
    footer_input = discord.ui.TextInput(label="Footer", max_length=2048, required=False)
    image_input = discord.ui.TextInput(label="Image URL", max_length=512, required=False)

    def __init__(self, cog, channel: discord.abc.Messageable, author: discord.abc.User):
        super().__init__()
        self.cog = cog
        self.channel = channel
        self.author = author

    async def on_submit(self, interaction: discord.Interaction) -> None:
        color = None
        raw = str(self.color_input.value or "").strip()
        if raw:
            try:
                color = discord.Color.from_str(raw)
            except (ValueError, TypeError):
                color = None
        embed = discord.Embed(
            title=str(self.title_input.value) or None,
            description=str(self.description_input.value) or None,
            color=color,
        )
        if self.footer_input.value:
            embed.set_footer(text=str(self.footer_input.value))
        if self.image_input.value:
            embed.set_image(url=str(self.image_input.value))
        if embed.title is None and embed.description is None and not embed.fields:
            await interaction.response.send_message("Provide at least a title or description.", ephemeral=True)
            return
        try:
            await self.channel.send(embed=embed)
        except discord.HTTPException as error:
            await interaction.response.send_message(f"Could not send embed: {error}", ephemeral=True)
            return
        await interaction.response.send_message("Embed posted.", ephemeral=True)


class EmbedBuilderView(discord.ui.View):
    """Button + dropdown editor that keeps the original command-based workflow available."""

    def __init__(
        self,
        *,
        cog,
        author: discord.abc.User,
        embed: Optional[discord.Embed] = None,
        content: str = "",
        target: Optional[discord.abc.Messageable] = None,
        timeout: float = 300,
    ):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.author_id = author.id
        self.embed = embed or discord.Embed(title="New embed", description="Use the controls below.")
        self.content = content or ""
        self.target = target
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This editor is not for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def refresh(self, interaction: discord.Interaction) -> None:
        kwargs: Dict[str, Any] = {"embed": self.embed, "view": self}
        if self.content:
            kwargs["content"] = self.content
        else:
            kwargs["content"] = None
        if interaction.response.is_done():
            if self.message:
                await self.message.edit(**kwargs)
        else:
            await interaction.response.edit_message(**kwargs)

    def _text(self, label: str, *, default: str = "", paragraph: bool = False, required: bool = False, max_length: int = 4000):
        return discord.ui.TextInput(
            label=label,
            default=default or None,
            required=required,
            max_length=min(max_length, MAX_MODAL),
            style=discord.TextStyle.paragraph if paragraph else discord.TextStyle.short,
        )

    @discord.ui.select(
        placeholder="Choose what to edit…",
        options=[
            discord.SelectOption(label="Title & URL", value="title", emoji="📝"),
            discord.SelectOption(label="Description", value="description", emoji="📄"),
            discord.SelectOption(label="Color", value="color", emoji="🎨"),
            discord.SelectOption(label="Author", value="author", emoji="👤"),
            discord.SelectOption(label="Footer", value="footer", emoji="🔻"),
            discord.SelectOption(label="Image", value="image", emoji="🖼️"),
            discord.SelectOption(label="Thumbnail", value="thumbnail", emoji="📌"),
            discord.SelectOption(label="Timestamp", value="timestamp", emoji="⏰"),
            discord.SelectOption(label="Message content", value="content", emoji="💬"),
        ],
        min_values=1,
        max_values=1,
        row=0,
    )
    async def edit_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        choice = select.values[0]
        if choice == "title":
            modal = SimpleModal(
                "Edit title",
                [
                    self._text("Title", default=self.embed.title or "", max_length=256),
                    self._text("URL", default=self.embed.url or "", max_length=512),
                ],
                self._apply_title,
            )
        elif choice == "description":
            modal = SimpleModal(
                "Edit description",
                [self._text("Description", default=self.embed.description or "", paragraph=True, max_length=4000)],
                self._apply_description,
            )
        elif choice == "color":
            current = f"#{self.embed.color.value:06X}" if self.embed.color else ""
            modal = SimpleModal(
                "Edit color",
                [self._text("Color", default=current, max_length=16)],
                self._apply_color,
            )
        elif choice == "author":
            modal = SimpleModal(
                "Edit author",
                [
                    self._text("Author name", default=(self.embed.author.name if self.embed.author else "") or "", max_length=256),
                    self._text("Author URL", default=(self.embed.author.url if self.embed.author else "") or "", max_length=512),
                    self._text("Author icon URL", default=(self.embed.author.icon_url if self.embed.author else "") or "", max_length=512),
                ],
                self._apply_author,
            )
        elif choice == "footer":
            modal = SimpleModal(
                "Edit footer",
                [
                    self._text("Footer text", default=(self.embed.footer.text if self.embed.footer else "") or "", max_length=2048),
                    self._text("Footer icon URL", default=(self.embed.footer.icon_url if self.embed.footer else "") or "", max_length=512),
                ],
                self._apply_footer,
            )
        elif choice == "image":
            modal = SimpleModal(
                "Edit image",
                [self._text("Image URL", default=(self.embed.image.url if self.embed.image else "") or "", max_length=512)],
                self._apply_image,
            )
        elif choice == "thumbnail":
            modal = SimpleModal(
                "Edit thumbnail",
                [self._text("Thumbnail URL", default=(self.embed.thumbnail.url if self.embed.thumbnail else "") or "", max_length=512)],
                self._apply_thumbnail,
            )
        elif choice == "timestamp":
            modal = SimpleModal(
                "Edit timestamp",
                [self._text("Timestamp", default="now", max_length=64)],
                self._apply_timestamp,
            )
        else:
            modal = SimpleModal(
                "Edit content",
                [self._text("Content", default=self.content, paragraph=True, max_length=2000)],
                self._apply_content,
            )
        await interaction.response.send_modal(modal)

    async def _apply_title(self, interaction: discord.Interaction, values: dict) -> None:
        self.embed.title = values.get("Title") or None
        self.embed.url = values.get("URL") or None
        await self.refresh(interaction)

    async def _apply_description(self, interaction: discord.Interaction, values: dict) -> None:
        self.embed.description = values.get("Description") or None
        await self.refresh(interaction)

    async def _apply_color(self, interaction: discord.Interaction, values: dict) -> None:
        raw = (values.get("Color") or "").strip()
        if not raw:
            self.embed.color = None
        else:
            try:
                self.embed.color = discord.Color.from_str(raw)
            except (ValueError, TypeError):
                await interaction.response.send_message("Invalid color. Use `#RRGGBB` or `0xRRGGBB`.", ephemeral=True)
                return
        await self.refresh(interaction)

    async def _apply_author(self, interaction: discord.Interaction, values: dict) -> None:
        name = values.get("Author name") or ""
        if not name:
            self.embed.remove_author()
        else:
            self.embed.set_author(
                name=name,
                url=values.get("Author URL") or None,
                icon_url=values.get("Author icon URL") or None,
            )
        await self.refresh(interaction)

    async def _apply_footer(self, interaction: discord.Interaction, values: dict) -> None:
        text = values.get("Footer text") or ""
        if not text:
            self.embed.remove_footer()
        else:
            self.embed.set_footer(text=text, icon_url=values.get("Footer icon URL") or None)
        await self.refresh(interaction)

    async def _apply_image(self, interaction: discord.Interaction, values: dict) -> None:
        url = values.get("Image URL") or ""
        if url:
            self.embed.set_image(url=url)
        else:
            self.embed.set_image(url=None)
        await self.refresh(interaction)

    async def _apply_thumbnail(self, interaction: discord.Interaction, values: dict) -> None:
        url = values.get("Thumbnail URL") or ""
        if url:
            self.embed.set_thumbnail(url=url)
        else:
            self.embed.set_thumbnail(url=None)
        await self.refresh(interaction)

    async def _apply_timestamp(self, interaction: discord.Interaction, values: dict) -> None:
        raw = (values.get("Timestamp") or "").strip().lower()
        if raw in {"", "clear", "none", "remove"}:
            self.embed.timestamp = None
        else:
            from datetime import datetime, timezone

            if raw in {"now", "utc", "current"}:
                self.embed.timestamp = datetime.now(timezone.utc)
            else:
                try:
                    self.embed.timestamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                except ValueError:
                    await interaction.response.send_message(
                        "Use `now` or an ISO-8601 timestamp such as `2026-09-29T23:00:00+00:00`.",
                        ephemeral=True,
                    )
                    return
        await self.refresh(interaction)

    async def _apply_content(self, interaction: discord.Interaction, values: dict) -> None:
        self.content = values.get("Content") or ""
        await self.refresh(interaction)

    @discord.ui.button(label="Add field", style=discord.ButtonStyle.secondary, emoji="➕", row=1)
    async def add_field(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedFieldModal(self))

    @discord.ui.button(label="Edit field", style=discord.ButtonStyle.secondary, emoji="✏️", row=1)
    async def edit_field(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.embed.fields:
            await interaction.response.send_message("This embed has no fields yet.", ephemeral=True)
            return
        options = [
            discord.SelectOption(label=f"{i}: {(field.name or 'field')[:80]}", value=str(i))
            for i, field in enumerate(self.embed.fields)
        ]
        view = FieldPickView(self, options, mode="edit")
        await interaction.response.send_message("Select a field to edit.", view=view, ephemeral=True)

    @discord.ui.button(label="Remove field", style=discord.ButtonStyle.secondary, emoji="➖", row=1)
    async def remove_field(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.embed.fields:
            await interaction.response.send_message("This embed has no fields yet.", ephemeral=True)
            return
        options = [
            discord.SelectOption(label=f"{i}: {(field.name or 'field')[:80]}", value=str(i))
            for i, field in enumerate(self.embed.fields)
        ]
        view = FieldPickView(self, options, mode="remove")
        await interaction.response.send_message("Select a field to remove.", view=view, ephemeral=True)

    @discord.ui.button(label="JSON", style=discord.ButtonStyle.primary, emoji="📦", row=1)
    async def export_json(self, interaction: discord.Interaction, button: discord.ui.Button):
        payload: Dict[str, Any] = {"embed": self.embed.to_dict()}
        if self.content:
            payload["content"] = self.content
        raw = json.dumps(payload, indent=4)
        if len(raw) < 1900:
            await interaction.response.send_message(box(raw, lang="json"), ephemeral=True)
        else:
            await interaction.response.send_message(
                file=text_to_file(raw, filename="embed.json"),
                ephemeral=True,
            )

    @discord.ui.button(label="Send", style=discord.ButtonStyle.success, emoji="📤", row=2)
    async def send_embed(self, interaction: discord.Interaction, button: discord.ui.Button):
        destination = self.target or interaction.channel
        try:
            await destination.send(content=self.content or None, embed=self.embed)
        except discord.HTTPException as error:
            await interaction.response.send_message(f"Could not send embed: {error}", ephemeral=True)
            return
        await interaction.response.send_message("Embed posted.", ephemeral=True)

    @discord.ui.button(label="Store", style=discord.ButtonStyle.success, emoji="💾", row=2)
    async def store_embed(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SimpleModal(
            "Store embed",
            [
                self._text("Name", required=True, max_length=50),
                self._text("Global? (yes/no)", default="no", max_length=5),
            ],
            self._apply_store,
        )
        await interaction.response.send_modal(modal)

    async def _apply_store(self, interaction: discord.Interaction, values: dict) -> None:
        name = (values.get("Name") or "").strip()
        if not name:
            await interaction.response.send_message("A name is required.", ephemeral=True)
            return
        global_level = (values.get("Global? (yes/no)") or "").strip().lower() in {"1", "true", "yes", "y"}
        if global_level and not await self.cog.bot.is_owner(interaction.user):
            await interaction.response.send_message("Only the bot owner can store global embeds.", ephemeral=True)
            return
        try:
            await self.cog.save_stored_embed(
                guild=interaction.guild,
                name=name,
                embed=self.embed,
                author_id=interaction.user.id,
                global_level=global_level,
                content=self.content or None,
            )
        except Exception as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        scope = "global" if global_level else "server"
        await interaction.response.send_message(f"Stored `{name}` as a {scope} embed.", ephemeral=True)

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.danger, emoji="♻️", row=2)
    async def reset_embed(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.embed = discord.Embed(title="New embed", description="Use the controls below.")
        self.content = ""
        await self.refresh(interaction)

    @discord.ui.button(label="Done", style=discord.ButtonStyle.danger, emoji="✅", row=2)
    async def done(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await self.refresh(interaction)
        self.stop()


class FieldPickView(discord.ui.View):
    def __init__(self, parent: EmbedBuilderView, options: List[discord.SelectOption], mode: str):
        super().__init__(timeout=60)
        self.parent = parent
        self.mode = mode
        select = discord.ui.Select(placeholder="Choose a field", options=options[:25])
        select.callback = self._picked
        self.add_item(select)

    async def _picked(self, interaction: discord.Interaction):
        index = int(interaction.data["values"][0])
        if self.mode == "remove":
            try:
                self.parent.embed.remove_field(index)
            except IndexError:
                await interaction.response.send_message("That field no longer exists.", ephemeral=True)
                return
            await interaction.response.edit_message(content="Field removed.", view=None)
            if self.parent.message:
                await self.parent.message.edit(embed=self.parent.embed, view=self.parent)
        else:
            await interaction.response.send_modal(EmbedFieldModal(self.parent, index=index))


class StoredEmbedDropdown(discord.ui.View):
    def __init__(
        self,
        *,
        cog,
        author: discord.abc.User,
        entries: List[dict],
        channel: discord.abc.Messageable,
        timeout: float = 120,
    ):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.author_id = author.id
        self.channel = channel
        self.entries = {entry["name"]: entry for entry in entries}
        options = [
            discord.SelectOption(
                label=entry["name"][:100],
                description=f"uses: {entry.get('uses', 0)}"[:100],
                value=entry["name"],
            )
            for entry in entries[:25]
        ]
        select = discord.ui.Select(placeholder="Pick a stored embed to post", options=options, min_values=1, max_values=min(10, len(options)))
        select.callback = self._post
        self.add_item(select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return False
        return True

    async def _post(self, interaction: discord.Interaction):
        names = interaction.data.get("values") or []
        embeds = []
        for name in names:
            entry = self.entries.get(name)
            if not entry:
                continue
            embeds.append(discord.Embed.from_dict(entry["embed"]))
            await self.cog.increment_uses(interaction.guild, name, global_level=entry.get("_global", False))
        if not embeds:
            await interaction.response.send_message("No valid embeds selected.", ephemeral=True)
            return
        try:
            await self.channel.send(embeds=embeds)
        except discord.HTTPException as error:
            await interaction.response.send_message(f"Could not send: {error}", ephemeral=True)
            return
        await interaction.response.send_message(f"Posted {len(embeds)} embed(s).", ephemeral=True)


class ConfirmView(discord.ui.View):
    def __init__(self, author_id: int, timeout: float = 30):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.value: Optional[bool] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        await interaction.response.edit_message(content="Confirmed.", view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        await interaction.response.edit_message(content="Cancelled.", view=None)
        self.stop()


class PaginatorView(discord.ui.View):
    def __init__(self, pages: List[discord.Embed], author_id: int, timeout: float = 120):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.index = 0
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    async def _edit(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(emoji="⬅️", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = (self.index - 1) % len(self.pages)
        await self._edit(interaction)

    @discord.ui.button(emoji="➡️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = (self.index + 1) % len(self.pages)
        await self._edit(interaction)

    @discord.ui.button(emoji="❌", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(view=None)
        self.stop()
