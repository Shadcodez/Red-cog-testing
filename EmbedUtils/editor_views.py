from __future__ import annotations

import contextlib
import json
from copy import deepcopy
from typing import TYPE_CHECKING, Any, Optional

import discord
from redbot.core.commands import Context
from redbot.core.utils.chat_formatting import box, text_to_file

from .editor_constants import (
    DEFAULT_CONTAINER_TEXT,
    DEFAULT_CONTAINER_TITLE,
    DEFAULT_EMBED_DESCRIPTION,
    DEFAULT_EMBED_TITLE,
    JSON_EMOJI,
    shorten_by,
)
from .editor_flags import (
    clone_container,
    container_to_embed,
    embed_to_container,
    generate_container_python_code,
)
from .editor_modals import (
    ContainerAccentColourModal,
    ContainerDictionaryUpdater,
    ContainerFileModal,
    ContainerLinkButtonModal,
    ContainerMediaGalleryModal,
    ContainerMessageContentModal,
    ContainerSectionButtonModal,
    ContainerSectionThumbnailModal,
    ContainerSeparatorModal,
    ContainerTextDisplayModal,
    EmbedAuthorBuilder,
    EmbedColourModal,
    EmbedDescriptionModal,
    EmbedDictionaryUpdater,
    EmbedFieldAdder,
    EmbedFooterBuilder,
    EmbedImageModal,
    EmbedMessageContentModal,
    EmbedThumbnailModal,
    EmbedTitleModal,
    EmbedURLModal,
    ModalBase,
)


# ==============================================================================
# Legacy Embed Views
# ==============================================================================


class EmbedFieldRemoverSelect(discord.ui.Select):
    def __init__(self, view: EmbedEditorView, /):
        options = [
            discord.SelectOption(
                label=shorten_by(field.name, 100),
                description=shorten_by(field.value, 100),
                value=str(index),
            )
            for index, field in enumerate(view.embed.fields)
        ]
        super().__init__(placeholder="Select a field to remove", options=options)
        self.embed_editor_view = view

    async def callback(self, interaction: discord.Interaction):
        self.embed_editor_view.embed.remove_field(int(self.values[0]))
        await self.embed_editor_view.message.edit(embed=self.embed_editor_view.embed)
        await interaction.response.edit_message(
            content="Field removed.",
            view=None,
        )


class EmbedFieldRemoverView(discord.ui.View):
    def __init__(self, view: EmbedEditorView):
        super().__init__(timeout=30)
        self.add_item(EmbedFieldRemoverSelect(view))
        self.message: Optional[discord.Message] = None

    async def on_timeout(self):
        with contextlib.suppress(discord.HTTPException):
            if self.message:
                await self.message.delete()


class EmbedEditorView(discord.ui.View):
    def __init__(self, ctx: Context, *, embed: Optional[discord.Embed] = None, content: Optional[str] = None):
        self.context = ctx
        super().__init__(timeout=600)
        self.embed = embed or discord.Embed(
            title=DEFAULT_EMBED_TITLE,
            description=DEFAULT_EMBED_DESCRIPTION.replace("[p]", ctx.clean_prefix),
            colour=discord.Colour.greyple(),
        )
        self.content: Optional[str] = content
        self.message: Optional[discord.Message] = None

    # Row 0: Basic Text & Meta
    @discord.ui.button(label="Title", style=discord.ButtonStyle.grey, row=0)
    async def edit_title_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedTitleModal(self))

    @discord.ui.button(label="Description", style=discord.ButtonStyle.grey, row=0)
    async def edit_description_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedDescriptionModal(self))

    @discord.ui.button(label="Message content", style=discord.ButtonStyle.grey, row=0)
    async def edit_message_content_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedMessageContentModal(self))

    @discord.ui.button(label="Colour", style=discord.ButtonStyle.grey, row=0)
    async def edit_colour_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedColourModal(self, context=self.context))

    @discord.ui.button(label="URL", style=discord.ButtonStyle.grey, row=0)
    async def edit_url_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedURLModal(self))

    # Row 1: Media, Author, Footer & Clear
    @discord.ui.button(label="Image", row=1, style=discord.ButtonStyle.grey)
    async def edit_image_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedImageModal(self))

    @discord.ui.button(label="Thumbnail", row=1, style=discord.ButtonStyle.grey)
    async def edit_thumbnail_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedThumbnailModal(self))

    @discord.ui.button(label="Author", row=1, style=discord.ButtonStyle.grey)
    async def edit_author_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedAuthorBuilder(self))

    @discord.ui.button(label="Footer", row=1, style=discord.ButtonStyle.grey)
    async def edit_footer_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedFooterBuilder(self))

    @discord.ui.button(label="Clear", row=1, style=discord.ButtonStyle.red)
    async def clear_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.embed = discord.Embed(description="[…]")
        self.content = None
        await interaction.response.edit_message(embed=self.embed, content=self.content)

    # Row 2: Fields & Container Conversion
    @discord.ui.button(label="Add field", style=discord.ButtonStyle.green, emoji="\U00002795", row=2)
    async def add_field_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedFieldAdder(self))

    @discord.ui.button(label="Remove field", style=discord.ButtonStyle.red, emoji="\U00002796", row=2)
    async def remove_field_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.embed.fields:
            await interaction.response.send_message("There are no fields to remove.", ephemeral=True)
        else:
            view = EmbedFieldRemoverView(self)
            await interaction.response.send_message(view=view, ephemeral=True)
            view.message = await interaction.original_response()

    @discord.ui.button(label="To Container", style=discord.ButtonStyle.blurple, emoji="\U0001f4e6", row=2)
    async def to_container_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        container = embed_to_container(self.embed)
        container_view = ContainerEditorView(self.context, container=container, content=self.content)
        await interaction.response.defer()
        with contextlib.suppress(discord.HTTPException):
            await interaction.message.delete()
        container_view.message = await self.context.send(view=container_view, content=self.content)

    # Row 3: Python & JSON Exports
    @discord.ui.button(label="Get Python", style=discord.ButtonStyle.blurple, emoji="\U0001f40d", row=3)
    async def get_python(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = self.embed
        text = "embed = discord.Embed("
        if embed.title:
            text += f"\n\ttitle={embed.title!r},"
        if embed.description:
            text += f"\n\tdescription={embed.description!r},"
        if embed.colour:
            text += f"\n\tcolour={int(embed.colour)},"
        if embed.url:
            text += f"\n\turl={embed.url!r},"

        if text == "embed = discord.Embed(":
            text += ")"
        else:
            text += "\n)"
        text += "\n\n"

        if embed.image:
            text += f"embed.set_image(url={embed.image.url!r})\n"
        if embed.thumbnail:
            text += f"embed.set_thumbnail(url={embed.thumbnail.url!r})\n"

        if embed.author:
            attrs = {}
            for attr in ["name", "url", "icon_url"]:
                if gattr := getattr(embed.author, attr):
                    attrs[attr] = gattr
            text += f"embed.set_author(" + ", ".join(f"{k}={v!r}" for k, v in attrs.items()) + ")\n"

        if embed.footer:
            attrs = {}
            for attr in ["text", "icon_url"]:
                if gattr := getattr(embed.footer, attr):
                    attrs[attr] = gattr
            text += f"embed.set_footer(" + ", ".join(f"{k}={v!r}" for k, v in attrs.items()) + ")\n"

        if not text.endswith("\n\n"):
            text += "\n"

        if embed.fields:
            for field in embed.fields:
                text += f"embed.add_field(name={field.name!r}, value={field.value!r}, inline={field.inline!r})\n"
            text += "\n\n"

        if self.content:
            text += f"content = {self.content!r}\n"

        text += "await ctx.send("
        if self.content:
            text += "content, "
        text += "embed=embed)"

        if len(text) > 1990:
            await interaction.response.send_message(
                file=text_to_file(text, filename="embed.py"),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                box(text.replace("```", "~~~"), lang="py"),
                ephemeral=True,
            )

    @discord.ui.button(label="Get JSON", style=discord.ButtonStyle.blurple, emoji=JSON_EMOJI, row=3)
    async def get_json(self, interaction: discord.Interaction, button: discord.ui.Button):
        text = json.dumps(self.embed.to_dict(), indent=4)
        if len(text) > 1990:
            await interaction.response.send_message(
                file=text_to_file(text, filename="embed.json"),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                box(text.replace("```", "~~~"), lang="json"),
                ephemeral=True,
            )

    @discord.ui.button(label="Replace JSON", style=discord.ButtonStyle.grey, emoji=JSON_EMOJI, row=3)
    async def replace_json(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedDictionaryUpdater(self, replace=True))

    @discord.ui.button(label="Update JSON", style=discord.ButtonStyle.grey, emoji=JSON_EMOJI, row=3)
    async def update_json(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedDictionaryUpdater(self, replace=False))

    # Row 4: Channel Dispatch
    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[
            discord.ChannelType.text,
            discord.ChannelType.news,
            discord.ChannelType.news_thread,
            discord.ChannelType.public_thread,
            discord.ChannelType.private_thread,
            discord.ChannelType.forum,
        ],
        placeholder="Send your embed",
        row=4,
    )
    async def send(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        channel = interaction.guild.get_channel(select.values[0].id)
        if not channel.permissions_for(interaction.guild.me).send_messages:
            return await interaction.response.send_message(
                f"I do not have permissions to post in {channel.mention}.", ephemeral=True
            )
        if not channel.permissions_for(interaction.user).send_messages:
            return await interaction.response.send_message(
                f"You do not have permissions to post in {channel.mention}.", ephemeral=True
            )
        try:
            await channel.send(
                embed=self.embed,
                content=self.content,
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
        except discord.HTTPException:
            return await interaction.response.send_message(
                "Something went wrong whilst sending the embed."
            )
        else:
            await interaction.response.send_message(
                f"Embed sent to {channel.mention}.", ephemeral=True
            )

    async def on_timeout(self):
        if self.message:
            with contextlib.suppress(discord.HTTPException):
                await self.message.edit(view=None, embed=self.embed, content=self.content)

    async def modify_target(self, modal: ModalBase, interaction: discord.Interaction):
        if interaction.message:
            self.message = interaction.message
        previous_embed = deepcopy(self.embed)
        try:
            await modal.edit_target(self.embed)
        except ValueError as exc:
            return await interaction.response.send_message(f"An error occurred: {exc}", ephemeral=True)

        try:
            await interaction.message.edit(embed=self.embed, content=self.content)
        except discord.HTTPException as exc:
            exc_text = exc.text.replace("embeds.0.", "embed ")
            if "maximum size of 6000" in exc_text:
                return await interaction.response.send_message(
                    "Sorry, the embed limit has exceeded 6000 characters, which is the maximum size. Your change could not be made.",
                    ephemeral=True,
                )
            await interaction.response.send_message(
                f"A HTTP error occurred whilst updating the embed:\n{box(exc_text)}\n",
                ephemeral=True,
            )
            self.embed = previous_embed
        else:
            if not interaction.response.is_done():
                await interaction.response.defer()

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.message:
            self.message = interaction.message
        if interaction.user != self.context.author:
            await interaction.response.send_message(
                "You cannot interact with this embed.",
                ephemeral=True,
            )
            return False
        return True


# ==============================================================================
# Components V2 Container Views
# ==============================================================================


class ContainerItemRemoverSelect(discord.ui.Select):
    def __init__(self, view: ContainerEditorView, /):
        options = []
        for index, child in enumerate(view.container.children):
            type_name = child.__class__.__name__
            desc = ""
            if isinstance(child, discord.ui.TextDisplay):
                desc = child.content
            elif isinstance(child, discord.ui.Separator):
                desc = f"Visible: {child.visible}, Spacing: {child.spacing.name}"
            elif isinstance(child, discord.ui.Section):
                acc_name = child.accessory.__class__.__name__ if child.accessory else "None"
                desc = f"Section with {acc_name}"
            elif isinstance(child, discord.ui.MediaGallery):
                items = getattr(child, "items", getattr(child, "children", []))
                desc = f"{len(items)} media item(s)"
            elif isinstance(child, discord.ui.ActionRow):
                desc = f"{len(child.children)} item(s) in action row"
            elif isinstance(child, discord.ui.File):
                desc = f"File: {child.media}"

            options.append(
                discord.SelectOption(
                    label=f"[{index + 1}] {type_name}",
                    description=shorten_by(desc, 100) if desc else "Component",
                    value=str(index),
                )
            )

        super().__init__(placeholder="Select a component to remove", options=options)
        self.editor_view = view

    async def callback(self, interaction: discord.Interaction):
        idx = int(self.values[0])
        if 0 <= idx < len(self.editor_view.container.children):
            target_child = self.editor_view.container.children[idx]
            self.editor_view.container.remove_item(target_child)
            await self.editor_view.message.edit(view=self.editor_view, content=self.editor_view.content)
            await interaction.response.edit_message(content="Component removed.", view=None)


class ContainerItemRemoverView(discord.ui.View):
    def __init__(self, view: ContainerEditorView):
        super().__init__(timeout=30)
        self.add_item(ContainerItemRemoverSelect(view))
        self.message: Optional[discord.Message] = None

    async def on_timeout(self):
        with contextlib.suppress(discord.HTTPException):
            if self.message:
                await self.message.delete()


class ContainerTextEditorSelect(discord.ui.Select):
    def __init__(self, view: ContainerEditorView, /):
        options = []
        self.text_displays: list[discord.ui.TextDisplay] = []

        for child in view.container.children:
            if isinstance(child, discord.ui.TextDisplay):
                self.text_displays.append(child)
                idx = len(self.text_displays) - 1
                options.append(
                    discord.SelectOption(
                        label=f"Text #{idx + 1}",
                        description=shorten_by(child.content, 100),
                        value=str(idx),
                    )
                )

        super().__init__(placeholder="Select a text display to edit", options=options)
        self.editor_view = view

    async def callback(self, interaction: discord.Interaction):
        idx = int(self.values[0])
        if 0 <= idx < len(self.text_displays):
            item = self.text_displays[idx]
            await interaction.response.send_modal(ContainerTextDisplayModal(self.editor_view, item_to_edit=item))


class ContainerTextEditorSelectView(discord.ui.View):
    def __init__(self, view: ContainerEditorView):
        super().__init__(timeout=30)
        self.add_item(ContainerTextEditorSelect(view))
        self.message: Optional[discord.Message] = None

    async def on_timeout(self):
        with contextlib.suppress(discord.HTTPException):
            if self.message:
                await self.message.delete()


class ContainerEditorView(discord.ui.LayoutView):
    def __init__(
        self,
        ctx: Context,
        *,
        container: Optional[discord.ui.Container] = None,
        content: Optional[str] = None,
    ):
        self.context = ctx
        super().__init__(timeout=600)

        # 1. Root Container Preview
        if container is not None:
            self.container = container
        else:
            self.container = discord.ui.Container(accent_colour=discord.Colour.blurple(), spoiler=False)
            self.container.add_item(discord.ui.TextDisplay(f"# {DEFAULT_CONTAINER_TITLE}"))
            self.container.add_item(
                discord.ui.TextDisplay(DEFAULT_CONTAINER_TEXT.replace("[p]", ctx.clean_prefix))
            )

        self.content: Optional[str] = content
        self.message: Optional[discord.Message] = None

        self.add_item(self.container)
        self._build_control_rows()

    def _build_control_rows(self):
        # ActionRow 1: Container Settings & Switch
        row1 = discord.ui.ActionRow()

        btn_accent = discord.ui.Button(label="Accent", style=discord.ButtonStyle.grey, emoji="\U0001f3a8")
        btn_accent.callback = self._on_accent_button
        row1.add_item(btn_accent)

        spoiler_lbl = "Unmask" if self.container.spoiler else "Spoiler"
        btn_spoiler = discord.ui.Button(label=spoiler_lbl, style=discord.ButtonStyle.grey, emoji="\U0001f648")
        btn_spoiler.callback = self._on_spoiler_button
        row1.add_item(btn_spoiler)

        btn_content = discord.ui.Button(label="Content", style=discord.ButtonStyle.grey, emoji="\U0001f4dd")
        btn_content.callback = self._on_content_button
        row1.add_item(btn_content)

        btn_clear = discord.ui.Button(label="Clear", style=discord.ButtonStyle.red, emoji="\U0001f5d1\ufe0f")
        btn_clear.callback = self._on_clear_button
        row1.add_item(btn_clear)

        btn_to_embed = discord.ui.Button(label="To Embed", style=discord.ButtonStyle.green, emoji="\U0001f5c3\ufe0f")
        btn_to_embed.callback = self._on_to_embed_button
        row1.add_item(btn_to_embed)

        self.add_item(row1)

        # ActionRow 2: Content Additions
        row2 = discord.ui.ActionRow()

        btn_add_text = discord.ui.Button(label="+ Text", style=discord.ButtonStyle.grey, emoji="\U0001f4c4")
        btn_add_text.callback = self._on_add_text_button
        row2.add_item(btn_add_text)

        btn_add_sec_thumb = discord.ui.Button(label="+ Thumb Sec", style=discord.ButtonStyle.grey, emoji="\U0001f5bc\ufe0f")
        btn_add_sec_thumb.callback = self._on_add_sec_thumb_button
        row2.add_item(btn_add_sec_thumb)

        btn_add_sec_btn = discord.ui.Button(label="+ Btn Sec", style=discord.ButtonStyle.grey, emoji="\U0001f517")
        btn_add_sec_btn.callback = self._on_add_sec_btn_button
        row2.add_item(btn_add_sec_btn)

        btn_add_sep = discord.ui.Button(label="+ Divider", style=discord.ButtonStyle.grey, emoji="\u2796")
        btn_add_sep.callback = self._on_add_sep_button
        row2.add_item(btn_add_sep)

        btn_add_media = discord.ui.Button(label="+ Media", style=discord.ButtonStyle.grey, emoji="\U0001f304")
        btn_add_media.callback = self._on_add_media_button
        row2.add_item(btn_add_media)

        self.add_item(row2)

        # ActionRow 3: Interactive & Management
        row3 = discord.ui.ActionRow()

        btn_add_link = discord.ui.Button(label="+ Link Btn", style=discord.ButtonStyle.grey, emoji="\U0001f518")
        btn_add_link.callback = self._on_add_link_button
        row3.add_item(btn_add_link)

        btn_add_file = discord.ui.Button(label="+ File", style=discord.ButtonStyle.grey, emoji="\U0001f4c1")
        btn_add_file.callback = self._on_add_file_button
        row3.add_item(btn_add_file)

        btn_remove = discord.ui.Button(label="- Remove", style=discord.ButtonStyle.red, emoji="\U00002796")
        btn_remove.callback = self._on_remove_item_button
        row3.add_item(btn_remove)

        btn_edit_text = discord.ui.Button(label="Edit Text", style=discord.ButtonStyle.blurple, emoji="\u270f\ufe0f")
        btn_edit_text.callback = self._on_edit_text_button
        row3.add_item(btn_edit_text)

        btn_export = discord.ui.Button(label="Export", style=discord.ButtonStyle.blurple, emoji="\U0001f4e4")
        btn_export.callback = self._on_export_menu_button
        row3.add_item(btn_export)

        self.add_item(row3)

        # ActionRow 4: Channel Select Dispatch
        row4 = discord.ui.ActionRow()
        channel_select = discord.ui.ChannelSelect(
            channel_types=[
                discord.ChannelType.text,
                discord.ChannelType.news,
                discord.ChannelType.news_thread,
                discord.ChannelType.public_thread,
                discord.ChannelType.private_thread,
                discord.ChannelType.forum,
            ],
            placeholder="Send your container to a channel",
        )
        channel_select.callback = self._on_send_channel
        row4.add_item(channel_select)
        self.add_item(row4)

    def replace_container(self, new_container: discord.ui.Container):
        self.remove_item(self.container)
        self.container = new_container
        self._children.insert(0, new_container)
        new_container._update_view(self)
        new_container._parent = None

    # Callbacks
    async def _on_accent_button(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ContainerAccentColourModal(self, context=self.context))

    async def _on_spoiler_button(self, interaction: discord.Interaction):
        self.container.spoiler = not self.container.spoiler
        await interaction.response.edit_message(view=self, content=self.content)

    async def _on_content_button(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EmbedMessageContentModal(self))

    async def _on_clear_button(self, interaction: discord.Interaction):
        self.container.clear_items()
        self.container.add_item(discord.ui.TextDisplay("[Empty Container]"))
        self.content = None
        await interaction.response.edit_message(view=self, content=self.content)

    async def _on_to_embed_button(self, interaction: discord.Interaction):
        self.stop()
        embed = container_to_embed(self.container)
        embed_view = EmbedEditorView(self.context, embed=embed, content=self.content)
        await interaction.response.defer()
        with contextlib.suppress(discord.HTTPException):
            await interaction.message.delete()
        embed_view.message = await self.context.send(embed=embed, content=self.content, view=embed_view)

    async def _on_add_text_button(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ContainerTextDisplayModal(self))

    async def _on_add_sec_thumb_button(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ContainerSectionThumbnailModal(self))

    async def _on_add_sec_btn_button(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ContainerSectionButtonModal(self))

    async def _on_add_sep_button(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ContainerSeparatorModal(self))

    async def _on_add_media_button(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ContainerMediaGalleryModal(self))

    async def _on_add_link_button(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ContainerLinkButtonModal(self))

    async def _on_add_file_button(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ContainerFileModal(self))

    async def _on_remove_item_button(self, interaction: discord.Interaction):
        if not self.container.children:
            return await interaction.response.send_message("The container has no items to remove.", ephemeral=True)
        view = ContainerItemRemoverView(self)
        await interaction.response.send_message(view=view, ephemeral=True)
        view.message = await interaction.original_response()

    async def _on_edit_text_button(self, interaction: discord.Interaction):
        has_text = any(isinstance(c, discord.ui.TextDisplay) for c in self.container.children)
        if not has_text:
            return await interaction.response.send_message("There are no text displays to edit.", ephemeral=True)
        view = ContainerTextEditorSelectView(self)
        await interaction.response.send_message(view=view, ephemeral=True)
        view.message = await interaction.original_response()

    async def _on_export_menu_button(self, interaction: discord.Interaction):
        export_view = discord.ui.View(timeout=60)

        btn_py = discord.ui.Button(label="Python Code", style=discord.ButtonStyle.blurple, emoji="\U0001f40d")
        async def _py_cb(btn_inter: discord.Interaction):
            await self._on_get_python_button(btn_inter)
        btn_py.callback = _py_cb
        export_view.add_item(btn_py)

        btn_js = discord.ui.Button(label="JSON", style=discord.ButtonStyle.blurple, emoji=JSON_EMOJI)
        async def _js_cb(btn_inter: discord.Interaction):
            await self._on_json_menu_button(btn_inter)
        btn_js.callback = _js_cb
        export_view.add_item(btn_js)

        btn_upload = discord.ui.Button(label="Replace JSON", style=discord.ButtonStyle.grey, emoji=JSON_EMOJI)
        async def _upload_cb(btn_inter: discord.Interaction):
            await btn_inter.response.send_modal(ContainerDictionaryUpdater(self))
        btn_upload.callback = _upload_cb
        export_view.add_item(btn_upload)

        await interaction.response.send_message(
            content="### Container Export & Import Options\nChoose an option below to view Python/JSON code or upload JSON:",
            view=export_view,
            ephemeral=True,
        )

    async def _on_get_python_button(self, interaction: discord.Interaction):
        code = generate_container_python_code(self.container, self.content)
        if len(code) > 1990:
            await interaction.response.send_message(
                file=text_to_file(code, filename="container.py"),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                box(code.replace("```", "~~~"), lang="py"),
                ephemeral=True,
            )

    async def _on_json_menu_button(self, interaction: discord.Interaction):
        # Create ephemeral menu with JSON preview and upload button
        data = self.container.to_component_dict()
        text = json.dumps(data, indent=4)

        json_view = discord.ui.View(timeout=60)
        btn_upload = discord.ui.Button(label="Upload / Replace JSON", style=discord.ButtonStyle.grey, emoji=JSON_EMOJI)

        async def _upload_cb(btn_inter: discord.Interaction):
            await btn_inter.response.send_modal(ContainerDictionaryUpdater(self))

        btn_upload.callback = _upload_cb
        json_view.add_item(btn_upload)

        if len(text) > 1900:
            await interaction.response.send_message(
                content="Here is your container JSON:",
                file=text_to_file(text, filename="container.json"),
                view=json_view,
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                content=box(text.replace("```", "~~~"), lang="json"),
                view=json_view,
                ephemeral=True,
            )

    async def _on_send_channel(self, interaction: discord.Interaction):
        select: discord.ui.ChannelSelect = interaction.data["values"]  # type: ignore
        channel_id = int(select[0]) if isinstance(select, list) else int(interaction.data.get("values", [0])[0])
        channel = interaction.guild.get_channel(channel_id)

        if not channel:
            return await interaction.response.send_message("Could not find the target channel.", ephemeral=True)
        if not channel.permissions_for(interaction.guild.me).send_messages:
            return await interaction.response.send_message(
                f"I do not have permissions to post in {channel.mention}.", ephemeral=True
            )
        if not channel.permissions_for(interaction.user).send_messages:
            return await interaction.response.send_message(
                f"You do not have permissions to post in {channel.mention}.", ephemeral=True
            )

        # Clean standalone view without control ActionRows
        clean_view = discord.ui.LayoutView(timeout=None)
        clean_view.add_item(clone_container(self.container))

        try:
            await channel.send(
                content=self.content,
                view=clean_view,
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
        except discord.HTTPException as exc:
            return await interaction.response.send_message(
                f"Failed to send container:\n{box(exc.text)}", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"Container sent to {channel.mention}.", ephemeral=True
            )

    async def modify_target(self, modal: ModalBase, interaction: discord.Interaction):
        if interaction.message:
            self.message = interaction.message
        previous_container = clone_container(self.container)
        try:
            await modal.edit_target(self.container)
        except ValueError as exc:
            return await interaction.response.send_message(f"An error occurred: {exc}", ephemeral=True)

        try:
            await interaction.message.edit(view=self, content=self.content)
        except discord.HTTPException as exc:
            self.replace_container(previous_container)
            await interaction.response.send_message(
                f"A Discord HTTP error occurred whilst updating the container:\n{box(exc.text)}\n",
                ephemeral=True,
            )
        else:
            if not interaction.response.is_done():
                await interaction.response.defer()

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.message:
            self.message = interaction.message
        if interaction.user != self.context.author:
            await interaction.response.send_message(
                "You cannot interact with this container.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self):
        if self.message:
            with contextlib.suppress(discord.HTTPException):
                clean_view = discord.ui.LayoutView(timeout=None)
                container_copy = clone_container(self.container)
                if not container_copy.children:
                    container_copy.add_item(discord.ui.TextDisplay("[Empty Container]"))
                clean_view.add_item(container_copy)
                await self.message.edit(view=clean_view, content=self.content)
