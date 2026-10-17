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


def _media_url(item) -> str:
    media = getattr(item, "media", None)
    if isinstance(media, str):
        return media
    return getattr(media, "url", "") or ""


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
    def __init__(self, view: ContainerEditorView, section: Optional[discord.ui.Section] = None):
        super().__init__(view, title="Edit Thumbnail Section" if section else "Add Section with Thumbnail")
        self.section = section
        texts = [child.content for child in getattr(section, "children", []) if isinstance(child, discord.ui.TextDisplay)] if section else []
        accessory = getattr(section, "accessory", None)
        self.section_text = discord.ui.TextInput(
            label="Section text 1",
            style=discord.TextStyle.long,
            default=texts[0] if texts else "",
            required=True,
            max_length=2000,
        )
        self.section_text_2 = discord.ui.TextInput(
            label="Section text 2 (optional)",
            style=discord.TextStyle.short,
            default=texts[1] if len(texts) > 1 else "",
            required=False,
            max_length=2000,
        )
        self.section_text_3 = discord.ui.TextInput(
            label="Section text 3 (optional)",
            style=discord.TextStyle.short,
            default=texts[2] if len(texts) > 2 else "",
            required=False,
            max_length=2000,
        )
        self.thumb_url = discord.ui.TextInput(
            label="Thumbnail URL or attachment",
            style=discord.TextStyle.short,
            default=_media_url(accessory),
            placeholder="https://... or attachment://filename.png",
            required=True,
        )
        self.thumb_spoiler = discord.ui.TextInput(
            label="Spoiler true/false",
            style=discord.TextStyle.short,
            default="true" if getattr(accessory, "spoiler", False) else "false",
            required=False,
            max_length=5,
        )

    async def edit_target(self, container: discord.ui.Container):
        texts = [self.section_text.value, self.section_text_2.value, self.section_text_3.value]
        displays = [discord.ui.TextDisplay(text) for text in texts if text.strip()]
        thumb = discord.ui.Thumbnail(
            media=self.thumb_url.value.strip(),
            description=getattr(getattr(self.section, "accessory", None), "description", None),
            spoiler=self.thumb_spoiler.value.strip().lower() == "true",
        )
        if self.section is not None:
            self.section.clear_items()
            for display in displays:
                self.section.add_item(display)
            self.section.accessory = thumb
            return
        container.add_item(discord.ui.Section(*displays, accessory=thumb))


class ContainerSectionButtonModal(ModalBase):
    def __init__(self, view: ContainerEditorView, section: Optional[discord.ui.Section] = None):
        super().__init__(view, title="Edit Button Section" if section else "Add Section with Button")
        self.section = section
        texts = [child.content for child in getattr(section, "children", []) if isinstance(child, discord.ui.TextDisplay)] if section else []
        button = getattr(section, "accessory", None)
        self.section_text = discord.ui.TextInput(
            label="Section text 1",
            style=discord.TextStyle.long,
            default=texts[0] if texts else "",
            required=True,
            max_length=2000,
        )
        self.section_text_2 = discord.ui.TextInput(
            label="Section text 2 (optional)",
            style=discord.TextStyle.short,
            default=texts[1] if len(texts) > 1 else "",
            required=False,
            max_length=2000,
        )
        self.section_text_3 = discord.ui.TextInput(
            label="Section text 3 (optional)",
            style=discord.TextStyle.short,
            default=texts[2] if len(texts) > 2 else "",
            required=False,
            max_length=2000,
        )
        self.btn_label = discord.ui.TextInput(
            label="Button Label",
            style=discord.TextStyle.short,
            default=getattr(button, "label", "") or "",
            required=True,
            max_length=80,
        )
        self.btn_url = discord.ui.TextInput(
            label="Button Destination URL",
            style=discord.TextStyle.short,
            default=getattr(button, "url", "") or "",
            required=True,
        )

    async def edit_target(self, container: discord.ui.Container):
        texts = [self.section_text.value, self.section_text_2.value, self.section_text_3.value]
        displays = [discord.ui.TextDisplay(text) for text in texts if text.strip()]
        btn = discord.ui.Button(
            label=self.btn_label.value.strip(),
            url=self.btn_url.value.strip(),
            style=discord.ButtonStyle.link,
            emoji=getattr(getattr(self.section, "accessory", None), "emoji", None),
            disabled=getattr(getattr(self.section, "accessory", None), "disabled", False),
        )
        if self.section is not None:
            self.section.clear_items()
            for display in displays:
                self.section.add_item(display)
            self.section.accessory = btn
            return
        container.add_item(discord.ui.Section(*displays, accessory=btn))


class ContainerSeparatorModal(ModalBase):
    def __init__(self, view: ContainerEditorView, item: Optional[discord.ui.Separator] = None):
        super().__init__(view, title="Edit Separator" if item else "Add Separator Divider")
        self.item = item
        self.visible_input = discord.ui.TextInput(
            label="Visible Divider Line (true/false)",
            style=discord.TextStyle.short,
            default="false" if item is not None and not getattr(item, "visible", True) else "true",
            required=True,
            max_length=5,
        )
        spacing = getattr(item, "spacing", None)
        spacing_name = getattr(spacing, "name", "small")
        self.spacing_input = discord.ui.TextInput(
            label="Spacing (small/large)",
            style=discord.TextStyle.short,
            default="large" if str(spacing_name).lower() == "large" else "small",
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
        if self.item is not None:
            try:
                self.item.divider = visible
            except Exception:
                self.item.visible = visible
            self.item.spacing = spacing
            return
        try:
            container.add_item(discord.ui.Separator(divider=visible, spacing=spacing))
        except TypeError:
            container.add_item(discord.ui.Separator(visible=visible, spacing=spacing))


class ContainerMediaGalleryModal(ModalBase):
    def __init__(self, view: ContainerEditorView, item=None):
        super().__init__(view, title="Edit Gallery Image" if item else "Add Image to Media Gallery")
        self.item = item
        self.media_url = discord.ui.TextInput(
            label="Image / Media URL",
            style=discord.TextStyle.short,
            default=_media_url(item),
            placeholder="https://example.com/image.png",
            required=True,
        )
        self.media_desc = discord.ui.TextInput(
            label="Description (Alt Text)",
            style=discord.TextStyle.short,
            default=getattr(item, "description", "") or "",
            required=False,
            max_length=256,
        )
        self.media_spoiler = discord.ui.TextInput(
            label="Spoiler (true/false)",
            style=discord.TextStyle.short,
            default="true" if getattr(item, "spoiler", False) else "false",
            required=False,
            max_length=5,
        )

    async def edit_target(self, container: discord.ui.Container):
        spoiler = self.media_spoiler.value.strip().lower() == "true"
        desc = self.media_desc.value.strip() or None
        if self.item is not None:
            self.item.media = self.media_url.value.strip()
            self.item.description = desc
            self.item.spoiler = spoiler
            return
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
    def __init__(self, view: ContainerEditorView, item: Optional[discord.ui.File] = None):
        super().__init__(view, title="Edit File" if item else "Add File Component")
        self.item = item
        self.file_media = discord.ui.TextInput(
            label="File Media Reference",
            style=discord.TextStyle.short,
            default=_media_url(item) or "attachment://",
            placeholder="attachment://filename.ext or URL",
            required=True,
        )
        self.file_spoiler = discord.ui.TextInput(
            label="File Spoiler (true/false)",
            style=discord.TextStyle.short,
            default="true" if getattr(item, "spoiler", False) else "false",
            required=False,
            max_length=5,
        )

    async def edit_target(self, container: discord.ui.Container):
        spoiler = self.file_spoiler.value.strip().lower() == "true"
        media = self.file_media.value.strip()
        if self.item is not None:
            self.item.media = media
            self.item.spoiler = spoiler
            return
        container.add_item(discord.ui.File(media=media, spoiler=spoiler))


class ContainerLinkButtonModal(ModalBase):
    def __init__(self, view: ContainerEditorView, button: Optional[discord.ui.Button] = None):
        super().__init__(view, title="Edit Link Button" if button else "Add Link Button inside Container")
        self.button = button
        self.btn_label = discord.ui.TextInput(
            label="Button Label",
            style=discord.TextStyle.short,
            default=getattr(button, "label", "") or "",
            placeholder="Visit Website",
            required=True,
            max_length=80,
        )
        self.btn_url = discord.ui.TextInput(
            label="Button Destination URL",
            style=discord.TextStyle.short,
            default=getattr(button, "url", "") or "",
            placeholder="https://example.com",
            required=True,
        )
        self.btn_emoji = discord.ui.TextInput(
            label="Emoji (optional)",
            style=discord.TextStyle.short,
            default=str(getattr(button, "emoji", "") or ""),
            required=False,
            max_length=64,
        )
        self.btn_disabled = discord.ui.TextInput(
            label="Disabled true/false",
            style=discord.TextStyle.short,
            default="true" if getattr(button, "disabled", False) else "false",
            required=False,
            max_length=5,
        )

    async def edit_target(self, container: discord.ui.Container):
        emoji = self.btn_emoji.value.strip() or None
        btn = discord.ui.Button(
            label=self.btn_label.value.strip(),
            url=self.btn_url.value.strip(),
            style=discord.ButtonStyle.link,
            emoji=emoji,
            disabled=self.btn_disabled.value.strip().lower() == "true",
        )
        if self.button is not None:
            self.button.label = btn.label
            self.button.url = btn.url
            self.button.emoji = btn.emoji
            self.button.disabled = btn.disabled
            return
        target_row = None
        for child in reversed(container.children):
            if isinstance(child, discord.ui.ActionRow) and len(child.children) < 5:
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
