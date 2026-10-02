from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Optional

import discord
from redbot.core.commands import BadArgument, ColourConverter, Context

if TYPE_CHECKING:
    from .editor_views import ContainerEditorView, EmbedEditorView


class ModalBase(discord.ui.Modal):
    def __init__(self, view: Any, /, *, title: str):
        self.view = view
        super().__init__(title=title)

    def __setattr__(self, name: str, value: Any):
        if isinstance(value, discord.ui.Item):
            self.add_item(value)
        super().__setattr__(name, value)

    async def edit_target(self, target: Any):
        pass

    async def on_submit(self, interaction: discord.Interaction):
        await self.view.modify_target(self, interaction)


class SingularEmbedComponentModal(ModalBase):
    def __init__(
        self,
        view: EmbedEditorView,
        /,
        *,
        title: str,
        label: str,
        style: discord.TextStyle = discord.TextStyle.short,
        placeholder: Optional[str] = None,
        default: Optional[str] = None,
        required: bool = True,
        max_length: Optional[int] = None,
    ):
        super().__init__(view, title=title)

        self.component = discord.ui.TextInput(
            label=label,
            style=style,
            placeholder=placeholder,
            default=default,
            required=required,
            max_length=max_length,
        )


# ==============================================================================
# Legacy Embed Modals
# ==============================================================================


class EmbedTitleModal(SingularEmbedComponentModal):
    def __init__(self, view: EmbedEditorView):
        super().__init__(
            view,
            title="Set embed title",
            label="Text for the embed title",
            style=discord.TextStyle.short,
            default=view.embed.title,
            required=False,
            max_length=256,
        )

    async def edit_target(self, embed: discord.Embed):
        embed.title = self.component.value or None


class EmbedDescriptionModal(SingularEmbedComponentModal):
    def __init__(self, view: EmbedEditorView):
        super().__init__(
            view,
            title="Set embed description",
            label="Text for the embed description",
            style=discord.TextStyle.long,
            default=view.embed.description,
            required=False,
            max_length=4000,
        )

    async def edit_target(self, embed: discord.Embed):
        embed.description = self.component.value or None


class EmbedMessageContentModal(SingularEmbedComponentModal):
    def __init__(self, view: Any):
        super().__init__(
            view,
            title="Set message content",
            label="Text for the message content",
            style=discord.TextStyle.long,
            default=view.content,
            required=False,
            max_length=2000,
        )

    async def edit_target(self, target: Any):
        self.view.content = self.component.value or None


ContainerMessageContentModal = EmbedMessageContentModal


class EmbedColourModal(SingularEmbedComponentModal):
    def __init__(self, view: EmbedEditorView, *, context: Context):
        super().__init__(
            view,
            title="Set embed colour",
            label="Enter integer, hex code, or colour name",
            style=discord.TextStyle.short,
            default=str(view.embed.colour or ""),
            required=False,
        )
        self.context = context

    async def edit_target(self, embed: discord.Embed):
        colour = self.component.value or None
        if colour:
            try:
                embed.colour = await ColourConverter().convert(self.context, colour)
            except BadArgument:
                raise ValueError(f"Invalid colour {colour!r}")
        else:
            embed.colour = None


class EmbedImageModal(SingularEmbedComponentModal):
    def __init__(self, view: EmbedEditorView):
        super().__init__(
            view,
            title="Set embed image",
            label="Image URL",
            style=discord.TextStyle.short,
            default=view.embed.image.url or "",
            required=False,
        )

    async def edit_target(self, embed: discord.Embed):
        embed.set_image(url=self.component.value or None)


class EmbedThumbnailModal(SingularEmbedComponentModal):
    def __init__(self, view: EmbedEditorView):
        super().__init__(
            view,
            title="Set embed thumbnail",
            label="Thumbnail URL",
            style=discord.TextStyle.short,
            default=view.embed.thumbnail.url or "",
            required=False,
        )

    async def edit_target(self, embed: discord.Embed):
        embed.set_thumbnail(url=self.component.value or None)


class EmbedURLModal(SingularEmbedComponentModal):
    def __init__(self, view: EmbedEditorView):
        super().__init__(
            view,
            title="Set embed URL",
            label="URL",
            style=discord.TextStyle.short,
            default=view.embed.url or "",
            required=False,
        )

    async def edit_target(self, embed: discord.Embed):
        embed.url = self.component.value or None


class EmbedDictionaryUpdater(SingularEmbedComponentModal):
    def __init__(self, view: EmbedEditorView, *, replace: bool):
        super().__init__(
            view,
            title="Upload JSON data",
            label="JSON data",
            style=discord.TextStyle.long,
            default=None,
            required=False,
        )
        self.replace = replace

    async def edit_target(self, embed: discord.Embed):
        try:
            data = json.loads(self.component.value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON (`{exc}`)")
        else:
            data["type"] = "rich"
            if self.replace:
                new = data
            else:
                new = embed.to_dict()
                new.update(data)
            try:
                self.view.embed = discord.Embed.from_dict(new)
            except Exception as exc:
                raise ValueError(exc)


class EmbedFooterBuilder(ModalBase):
    def __init__(self, view: EmbedEditorView):
        super().__init__(view, title="Footer details")

        self.embed_footer_text = discord.ui.TextInput(
            label="Footer text",
            style=discord.TextStyle.long,
            max_length=2048,
            default=view.embed.footer.text,
            required=False,
        )

        self.embed_footer_icon_url = discord.ui.TextInput(
            label="Footer icon URL",
            style=discord.TextStyle.short,
            default=view.embed.footer.icon_url,
            required=False,
        )

    async def edit_target(self, embed: discord.Embed):
        text = (self.embed_footer_text.value or "").strip()
        icon = (self.embed_footer_icon_url.value or "").strip() or None
        if not text:
            embed.remove_footer()
            return
        embed.set_footer(text=text[:2048], icon_url=icon)


class EmbedAuthorBuilder(ModalBase):
    def __init__(self, view: EmbedEditorView):
        super().__init__(view, title="Author details")

        self.embed_author_name = discord.ui.TextInput(
            label="Author name",
            style=discord.TextStyle.short,
            max_length=256,
            default=self.view.embed.author.name,
            required=False,
        )

        self.embed_author_url = discord.ui.TextInput(
            label="Author URL",
            style=discord.TextStyle.short,
            default=self.view.embed.author.url,
            required=False,
        )

        self.embed_author_icon_url = discord.ui.TextInput(
            label="Author icon URL",
            style=discord.TextStyle.short,
            default=self.view.embed.author.icon_url,
            required=False,
        )

    async def edit_target(self, embed: discord.Embed):
        name = (self.embed_author_name.value or "").strip()
        if not name:
            embed.remove_author()
            return
        embed.set_author(
            name=name[:256],
            url=(self.embed_author_url.value or "").strip() or None,
            icon_url=(self.embed_author_icon_url.value or "").strip() or None,
        )


class EmbedFieldAdder(ModalBase):
    def __init__(self, view: EmbedEditorView):
        super().__init__(view, title="Field adder")

        self.embed_field_name = discord.ui.TextInput(
            label="Name",
            style=discord.TextStyle.short,
            max_length=256,
        )

        self.embed_field_value = discord.ui.TextInput(
            label="Value",
            style=discord.TextStyle.long,
            max_length=1024,
        )

        self.embed_field_inline = discord.ui.TextInput(
            label="Inline (true/false)",
            style=discord.TextStyle.short,
            max_length=5,
            default="true",
        )

    async def edit_target(self, embed: discord.Embed):
        inline = self.embed_field_inline.value.lower()
        if inline == "true":
            inline = True
        elif inline == "false":
            inline = False
        else:
            raise ValueError("Embed field inline must be 'true' or 'false'.")
        embed.add_field(
            name=self.embed_field_name.value,
            value=self.embed_field_value.value,
            inline=inline,
        )


# ==============================================================================
# Components V2 Container Modals
# ==============================================================================


class ContainerAccentColourModal(ModalBase):
    def __init__(self, view: ContainerEditorView, *, context: Context):
        super().__init__(view, title="Set Container Accent Colour")
        current_colour = ""
        if view.container.accent_colour is not None:
            if isinstance(view.container.accent_colour, discord.Colour):
                current_colour = str(view.container.accent_colour)
            else:
                current_colour = hex(view.container.accent_colour)

        self.colour_input = discord.ui.TextInput(
            label="Accent colour (name, hex, or integer)",
            style=discord.TextStyle.short,
            placeholder="e.g. blurple, #5865F2, or 5793266",
            default=current_colour,
            required=False,
        )
        self.context = context

    async def edit_target(self, container: discord.ui.Container):
        raw_val = self.colour_input.value.strip()
        if not raw_val:
            container.accent_colour = None
            return

        try:
            converted = await ColourConverter().convert(self.context, raw_val)
            container.accent_colour = converted
        except BadArgument:
            # Fallback to integer or hex parse
            try:
                if raw_val.startswith("#"):
                    val = int(raw_val[1:], 16)
                elif raw_val.startswith("0x"):
                    val = int(raw_val, 16)
                else:
                    val = int(raw_val)
                container.accent_colour = discord.Colour(val)
            except ValueError:
                raise ValueError(f"Invalid colour {raw_val!r}. Please provide a valid hex, integer, or colour name.")


class ContainerTextDisplayModal(ModalBase):
    def __init__(
        self,
        view: ContainerEditorView,
        *,
        item_to_edit: Optional[discord.ui.TextDisplay] = None,
    ):
        title = "Edit Text Display" if item_to_edit is not None else "Add Text Display"
        super().__init__(view, title=title)
        self.item_to_edit = item_to_edit

        default_val = item_to_edit.content if item_to_edit is not None else ""
        self.content_input = discord.ui.TextInput(
            label="Markdown Text Content",
            style=discord.TextStyle.long,
            placeholder="Supports Markdown headers (#), bold, code blocks, lists...",
            default=default_val,
            required=True,
            max_length=4000,
        )

    async def edit_target(self, container: discord.ui.Container):
        content = self.content_input.value
        if self.item_to_edit is not None:
            self.item_to_edit.content = content
        else:
            container.add_item(discord.ui.TextDisplay(content))


class ContainerSectionThumbnailModal(ModalBase):
    def __init__(self, view: ContainerEditorView):
        super().__init__(view, title="Add Section with Thumbnail")

        self.section_text = discord.ui.TextInput(
            label="Section Text",
            style=discord.TextStyle.long,
            placeholder="Accompanying text displayed beside the thumbnail...",
            required=True,
            max_length=2000,
        )
        self.thumb_url = discord.ui.TextInput(
            label="Thumbnail URL or attachment",
            style=discord.TextStyle.short,
            placeholder="https://... or attachment://filename.png",
            required=True,
        )
        self.thumb_desc = discord.ui.TextInput(
            label="Thumbnail Alt Text Description",
            style=discord.TextStyle.short,
            placeholder="Optional alt text description",
            required=False,
            max_length=256,
        )
        self.thumb_spoiler = discord.ui.TextInput(
            label="Thumbnail Spoiler (true/false)",
            style=discord.TextStyle.short,
            default="false",
            required=False,
            max_length=5,
        )

    async def edit_target(self, container: discord.ui.Container):
        spoiler_val = self.thumb_spoiler.value.strip().lower() == "true"
        thumb = discord.ui.Thumbnail(
            media=self.thumb_url.value.strip(),
            description=self.thumb_desc.value.strip() or None,
            spoiler=spoiler_val,
        )
        section = discord.ui.Section(
            discord.ui.TextDisplay(self.section_text.value),
            accessory=thumb,
        )
        container.add_item(section)


class ContainerSectionButtonModal(ModalBase):
    def __init__(self, view: ContainerEditorView):
        super().__init__(view, title="Add Section with Button")

        self.section_text = discord.ui.TextInput(
            label="Section Text",
            style=discord.TextStyle.long,
            placeholder="Text displayed beside the button...",
            required=True,
            max_length=2000,
        )
        self.btn_label = discord.ui.TextInput(
            label="Button Label",
            style=discord.TextStyle.short,
            placeholder="Click Here",
            required=True,
            max_length=80,
        )
        self.btn_url = discord.ui.TextInput(
            label="Button Destination URL",
            style=discord.TextStyle.short,
            placeholder="https://example.com",
            required=True,
        )

    async def edit_target(self, container: discord.ui.Container):
        btn = discord.ui.Button(
            label=self.btn_label.value.strip(),
            url=self.btn_url.value.strip(),
            style=discord.ButtonStyle.link,
        )
        section = discord.ui.Section(
            discord.ui.TextDisplay(self.section_text.value),
            accessory=btn,
        )
        container.add_item(section)


class ContainerSeparatorModal(ModalBase):
    def __init__(self, view: ContainerEditorView):
        super().__init__(view, title="Add Separator Divider")

        self.visible_input = discord.ui.TextInput(
            label="Visible Divider Line (true/false)",
            style=discord.TextStyle.short,
            default="true",
            required=True,
            max_length=5,
        )
        self.spacing_input = discord.ui.TextInput(
            label="Spacing (small/large)",
            style=discord.TextStyle.short,
            default="small",
            required=True,
            max_length=5,
        )

    async def edit_target(self, container: discord.ui.Container):
        visible = self.visible_input.value.strip().lower() != "false"
        spacing_str = self.spacing_input.value.strip().lower()
        spacing = (
            discord.SeparatorSpacing.large
            if spacing_str == "large"
            else discord.SeparatorSpacing.small
        )
        try:
            container.add_item(discord.ui.Separator(divider=visible, spacing=spacing))
        except TypeError:
            container.add_item(discord.ui.Separator(visible=visible, spacing=spacing))


class ContainerMediaGalleryModal(ModalBase):
    def __init__(self, view: ContainerEditorView):
        super().__init__(view, title="Add Image to Media Gallery")

        self.media_url = discord.ui.TextInput(
            label="Image / Media URL",
            style=discord.TextStyle.short,
            placeholder="https://example.com/image.png",
            required=True,
        )
        self.media_desc = discord.ui.TextInput(
            label="Description (Alt Text)",
            style=discord.TextStyle.short,
            placeholder="Optional description",
            required=False,
            max_length=256,
        )
        self.media_spoiler = discord.ui.TextInput(
            label="Spoiler (true/false)",
            style=discord.TextStyle.short,
            default="false",
            required=False,
            max_length=5,
        )

    async def edit_target(self, container: discord.ui.Container):
        spoiler = self.media_spoiler.value.strip().lower() == "true"
        desc = self.media_desc.value.strip() or None
        item = discord.MediaGalleryItem(
            media=self.media_url.value.strip(),
            description=desc,
            spoiler=spoiler,
        )

        # Check if the last item is a MediaGallery that has room (< 10 items)
        existing_gallery = None
        for child in reversed(container.children):
            if isinstance(child, discord.ui.MediaGallery):
                items = getattr(child, "items", getattr(child, "children", []))
                if len(items) < 10:
                    existing_gallery = child
                break

        if existing_gallery is not None:
            existing_gallery.add_item(item)
        else:
            gallery = discord.ui.MediaGallery(item)
            container.add_item(gallery)


class ContainerFileModal(ModalBase):
    def __init__(self, view: ContainerEditorView):
        super().__init__(view, title="Add File Component")

        self.file_media = discord.ui.TextInput(
            label="File Media Reference",
            style=discord.TextStyle.short,
            default="attachment://",
            placeholder="attachment://filename.ext or URL",
            required=True,
        )
        self.file_spoiler = discord.ui.TextInput(
            label="File Spoiler (true/false)",
            style=discord.TextStyle.short,
            default="false",
            required=False,
            max_length=5,
        )

    async def edit_target(self, container: discord.ui.Container):
        spoiler = self.file_spoiler.value.strip().lower() == "true"
        container.add_item(
            discord.ui.File(
                media=self.file_media.value.strip(),
                spoiler=spoiler,
            )
        )


class ContainerLinkButtonModal(ModalBase):
    def __init__(self, view: ContainerEditorView):
        super().__init__(view, title="Add Link Button inside Container")

        self.btn_label = discord.ui.TextInput(
            label="Button Label",
            style=discord.TextStyle.short,
            placeholder="Visit Website",
            required=True,
            max_length=80,
        )
        self.btn_url = discord.ui.TextInput(
            label="Button Destination URL",
            style=discord.TextStyle.short,
            placeholder="https://example.com",
            required=True,
        )

    async def edit_target(self, container: discord.ui.Container):
        btn = discord.ui.Button(
            label=self.btn_label.value.strip(),
            url=self.btn_url.value.strip(),
            style=discord.ButtonStyle.link,
        )

        # Find existing ActionRow inside container with < 5 buttons, or add new ActionRow
        target_row = None
        for child in reversed(container.children):
            if isinstance(child, discord.ui.ActionRow):
                if len(child.children) < 5:
                    target_row = child
                break

        if target_row is not None:
            target_row.add_item(btn)
        else:
            row = discord.ui.ActionRow()
            row.add_item(btn)
            container.add_item(row)


class ContainerDictionaryUpdater(ModalBase):
    def __init__(self, view: ContainerEditorView):
        super().__init__(view, title="Upload Components V2 JSON")

        self.json_input = discord.ui.TextInput(
            label="Components V2 JSON Data",
            style=discord.TextStyle.long,
            placeholder="Paste raw container or component dictionary JSON here...",
            required=True,
        )

    async def edit_target(self, container: discord.ui.Container):
        try:
            data = json.loads(self.json_input.value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON (`{exc}`)")

        from .editor_flags import container_from_dict

        new_container = container_from_dict(data)
        self.view.replace_container(new_container)
