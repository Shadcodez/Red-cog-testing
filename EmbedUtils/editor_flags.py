from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional

import discord
from redbot.core import commands
from redbot.core.commands import ColourConverter, FlagConverter


class EmbedArgsConverter(FlagConverter):
    title: Optional[str] = commands.flag(name="title", default=None)
    description: Optional[str] = commands.flag(name="description", default=None)
    colour: Optional[discord.Colour] = commands.flag(
        name="colour", aliases=["color"], default=None, converter=ColourConverter
    )
    url: Optional[str] = commands.flag(name="url", default=None)

    image: Optional[str] = commands.flag(name="image", default=None)
    thumbnail: Optional[str] = commands.flag(name="thumbnail", default=None)

    author_name: Optional[str] = commands.flag(name="author_name", default=None)
    author_url: Optional[str] = commands.flag(name="author_url", default=None)
    author_icon_url: Optional[str] = commands.flag(name="author_icon_url", default=None)

    footer_text: Optional[str] = commands.flag(name="footer_text", default=None)
    footer_icon_url: Optional[str] = commands.flag(name="footer_icon_url", default=None)

    content: Optional[str] = commands.flag(name="content", default=None)
    builder: Optional[bool] = commands.flag(name="builder", default=True, converter=bool)
    source: Optional[discord.Message] = commands.flag(
        name="source", default=None, converter=commands.MessageConverter
    )

    embed_settable_attributes: tuple[str, ...] = (
        "title",
        "description",
        "colour",
        "url",
    )

    def author_kwargs(self) -> dict[str, str]:
        d = {}
        for attr in ("name", "url", "icon_url"):
            if (gattr := getattr(self, f"author_{attr}")) is not None:
                d[attr] = gattr
        return d

    def footer_kwargs(self) -> dict[str, str]:
        d = {}
        for attr in ("text", "icon_url"):
            if (gattr := getattr(self, f"footer_{attr}")) is not None:
                d[attr] = gattr
        return d

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "rich",
            "title": self.title,
            "description": self.description,
            "colour": self.colour,
            "url": self.url,
            "image": self.image,
            "thumbnail": self.thumbnail,
            "author": {
                "name": self.author_name,
                "url": self.author_url,
                "icon_url": self.author_icon_url,
            },
            "footer": {
                "text": self.footer_text,
                "icon_url": self.footer_icon_url,
            },
        }

    async def convert(self, ctx: commands.Context, argument: str):
        try:
            return await super().convert(ctx, argument)
        except commands.BadFlagArgument as e:
            raise commands.UserFeedbackCheckFailure(
                f"Invalid value for the {e.flag.attribute!r} option."
            )
        except commands.MissingFlagArgument as e:
            raise commands.UserFeedbackCheckFailure(
                f"No value provided for the {e.flag.attribute!r} option."
            )
        except commands.TooManyFlags as e:
            raise commands.UserFeedbackCheckFailure(
                f"Too many values provided for the {e.flag.attribute!r} option."
            )


class ContainerArgsConverter(FlagConverter):
    accent_colour: Optional[discord.Colour] = commands.flag(
        name="accent_colour", aliases=["colour", "color"], default=None, converter=ColourConverter
    )
    spoiler: Optional[bool] = commands.flag(name="spoiler", default=False, converter=bool)
    text: Optional[str] = commands.flag(name="text", default=None)
    image: Optional[str] = commands.flag(name="image", aliases=["media"], default=None)
    thumbnail: Optional[str] = commands.flag(name="thumbnail", default=None)
    content: Optional[str] = commands.flag(name="content", default=None)
    builder: Optional[bool] = commands.flag(name="builder", default=True, converter=bool)
    source: Optional[discord.Message] = commands.flag(
        name="source", default=None, converter=commands.MessageConverter
    )

    async def convert(self, ctx: commands.Context, argument: str):
        try:
            return await super().convert(ctx, argument)
        except commands.BadFlagArgument as e:
            raise commands.UserFeedbackCheckFailure(
                f"Invalid value for the {e.flag.attribute!r} option."
            )
        except commands.MissingFlagArgument as e:
            raise commands.UserFeedbackCheckFailure(
                f"No value provided for the {e.flag.attribute!r} option."
            )
        except commands.TooManyFlags as e:
            raise commands.UserFeedbackCheckFailure(
                f"Too many values provided for the {e.flag.attribute!r} option."
            )


# ==============================================================================
# Transformers: Embed <-> Container
# ==============================================================================


def embed_to_container(embed: discord.Embed) -> discord.ui.Container:
    """Converts a standard discord.Embed into a discord.ui.Container."""
    container = discord.ui.Container(
        accent_colour=embed.colour,
        spoiler=False,
    )

    # 1. Author
    if embed.author and embed.author.name:
        author_text = f"**{embed.author.name}**"
        if embed.author.url:
            author_text = f"[{author_text}]({embed.author.url})"
        container.add_item(discord.ui.TextDisplay(author_text))

    # 2. Title & URL
    if embed.title:
        title_text = f"# {embed.title}"
        if embed.url:
            title_text = f"# [{embed.title}]({embed.url})"
        container.add_item(discord.ui.TextDisplay(title_text))

    # 3. Description
    if embed.description:
        container.add_item(discord.ui.TextDisplay(embed.description))

    # 4. Thumbnail (as a Section with Thumbnail accessory)
    if embed.thumbnail and embed.thumbnail.url:
        container.add_item(
            discord.ui.Section(
                discord.ui.TextDisplay("*Thumbnail Preview*"),
                accessory=discord.ui.Thumbnail(embed.thumbnail.url),
            )
        )

    # 5. Fields
    if embed.fields:
        for field in embed.fields:
            field_text = f"### {field.name}\n{field.value}"
            container.add_item(discord.ui.TextDisplay(field_text))

    # 6. Large Image (as a MediaGallery)
    if embed.image and embed.image.url:
        container.add_item(
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(embed.image.url)
            )
        )

    # 7. Footer
    if embed.footer and embed.footer.text:
        container.add_item(discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small))
        container.add_item(discord.ui.TextDisplay(f"-# {embed.footer.text}"))

    # Fallback if empty
    if not container.children:
        container.add_item(discord.ui.TextDisplay("[Empty Container]"))

    return container


def container_to_embed(container: discord.ui.Container) -> discord.Embed:
    """Converts a discord.ui.Container into a standard discord.Embed."""
    embed = discord.Embed(colour=container.accent_colour)

    title_set = False
    description_lines = []

    for child in container.children:
        if isinstance(child, discord.ui.TextDisplay):
            content = child.content.strip()
            if not title_set and content.startswith("# "):
                # Extract markdown header as title
                embed.title = content.lstrip("# ").strip()
                title_set = True
            elif not description_lines:
                description_lines.append(content)
            else:
                # Subsequent text blocks can be fields or appended
                if len(description_lines) < 3 and len("\n\n".join(description_lines) + content) < 2000:
                    description_lines.append(content)
                else:
                    lines = content.split("\n", 1)
                    field_name = lines[0].lstrip("#* ").strip() or "Note"
                    field_val = lines[1].strip() if len(lines) > 1 else lines[0]
                    embed.add_field(name=field_name[:256], value=field_val[:1024], inline=False)

        elif isinstance(child, discord.ui.Section):
            # Text displays inside section
            sec_text = ""
            for sub in child.children:
                if isinstance(sub, discord.ui.TextDisplay):
                    sec_text += sub.content + "\n"
                elif isinstance(sub, str):
                    sec_text += sub + "\n"

            accessory = child.accessory
            if isinstance(accessory, discord.ui.Thumbnail):
                media_url = getattr(accessory.media, "url", str(accessory.media))
                if media_url:
                    embed.set_thumbnail(url=media_url)
            elif isinstance(accessory, discord.ui.Button):
                sec_text += f"\n[Button: {accessory.label or 'Link'}]({accessory.url})"

            if sec_text.strip():
                embed.add_field(name="Section", value=sec_text.strip()[:1024], inline=False)

        elif isinstance(child, discord.ui.MediaGallery):
            # Take the first image URL if available
            gallery_items = getattr(child, "items", getattr(child, "children", []))
            for item in gallery_items:
                media_obj = getattr(item, "media", None)
                media_url = getattr(media_obj, "url", str(media_obj)) if media_obj else ""
                if media_url:
                    embed.set_image(url=media_url)
                    break

        elif isinstance(child, discord.ui.ActionRow):
            links = []
            for btn in child.children:
                if isinstance(btn, discord.ui.Button) and btn.url:
                    links.append(f"[{btn.label or 'Link'}]({btn.url})")
            if links:
                embed.add_field(name="Links", value=" • ".join(links), inline=False)

    if description_lines:
        embed.description = "\n\n".join(description_lines)[:4000]

    if not embed.title and not embed.description and not embed.fields:
        embed.description = "[Container content]"

    return embed


# ==============================================================================
# JSON Deserialization
# ==============================================================================


def container_from_dict(data: dict[str, Any]) -> discord.ui.Container:
    """Converts a raw Components V2 JSON dictionary into a discord.ui.Container."""
    if not isinstance(data, dict):
        raise ValueError("JSON data must be a dictionary.")

    # If the user passed a list or wrapped structure
    if "type" not in data and "components" in data:
        # Check if first component is container
        first = data["components"][0] if data["components"] else None
        if isinstance(first, dict) and first.get("type") == 17:
            data = first
        else:
            data = {
                "type": 17,
                "accent_color": None,
                "spoiler": False,
                "components": data["components"],
            }

    if data.get("type") != 17:
        raise ValueError(f"Expected Component Type 17 (Container), got type {data.get('type')!r}")

    try:
        from discord.components import _component_factory
        from discord.ui.view import _component_to_item
    except ImportError as exc:
        raise ValueError("This discord.py build cannot import container components.") from exc
    comp = _component_factory(data)
    item = _component_to_item(comp)
    if not isinstance(item, discord.ui.Container):
        raise ValueError("Failed to deserialize container from JSON.")
    return item


def clone_container(container: discord.ui.Container) -> discord.ui.Container:
    """Safely clones a Container by serializing and deserializing its component dictionary.

    This avoids copy.deepcopy() traversing _view -> Context -> asyncio loop -> _contextvars.Context.
    """
    return container_from_dict(container.to_component_dict())


# ==============================================================================
# Python Code Generator
# ==============================================================================


def generate_container_python_code(container: discord.ui.Container, content: Optional[str]) -> str:
    """Generates runnable discord.py 2.6+ code for constructing this container."""
    lines = [
        "import discord",
        "from discord import ui",
        "",
        "view = ui.LayoutView(timeout=None)",
    ]

    colour_arg = ""
    if container.accent_colour is not None:
        val = int(container.accent_colour)
        colour_arg = f"accent_colour=discord.Colour({val}), "

    spoiler_arg = f"spoiler={container.spoiler}" if container.spoiler else ""
    init_args = ", ".join(arg for arg in [colour_arg.rstrip(", "), spoiler_arg] if arg)

    lines.append(f"container = ui.Container({init_args})")
    lines.append("")

    for idx, child in enumerate(container.children):
        if isinstance(child, discord.ui.TextDisplay):
            lines.append(f"container.add_item(ui.TextDisplay({child.content!r}))")

        elif isinstance(child, discord.ui.Separator):
            sp = "discord.SeparatorSpacing.large" if child.spacing == discord.SeparatorSpacing.large else "discord.SeparatorSpacing.small"
            lines.append(f"container.add_item(ui.Separator(visible={child.visible}, spacing={sp}))")

        elif isinstance(child, discord.ui.Section):
            acc = child.accessory
            acc_code = "None"
            if isinstance(acc, discord.ui.Thumbnail):
                media_val = getattr(acc.media, "url", str(acc.media))
                desc_val = f", description={acc.description!r}" if acc.description else ""
                spoil_val = f", spoiler={acc.spoiler}" if acc.spoiler else ""
                acc_code = f"ui.Thumbnail({media_val!r}{desc_val}{spoil_val})"
            elif isinstance(acc, discord.ui.Button):
                label_val = f"label={acc.label!r}, " if acc.label else ""
                url_val = f"url={acc.url!r}, " if acc.url else ""
                acc_code = f"ui.Button({label_val}{url_val}style=discord.ButtonStyle.link)"

            # text displays
            sec_texts = [repr(sub.content) if isinstance(sub, discord.ui.TextDisplay) else repr(str(sub)) for sub in child.children]
            texts_code = ", ".join(f"ui.TextDisplay({t})" for t in sec_texts)
            lines.append(f"container.add_item(ui.Section({texts_code}, accessory={acc_code}))")

        elif isinstance(child, discord.ui.MediaGallery):
            items_code = []
            gallery_items = getattr(child, "items", getattr(child, "children", []))
            for item in gallery_items:
                media_obj = getattr(item, "media", None)
                m = getattr(media_obj, "url", str(media_obj)) if media_obj else ""
                d = f", description={item.description!r}" if item.description else ""
                s = f", spoiler={item.spoiler}" if item.spoiler else ""
                items_code.append(f"discord.MediaGalleryItem({m!r}{d}{s})")
            lines.append(f"container.add_item(ui.MediaGallery({', '.join(items_code)}))")

        elif isinstance(child, discord.ui.File):
            media_val = getattr(child.media, "url", str(child.media))
            lines.append(f"container.add_item(ui.File({media_val!r}, spoiler={child.spoiler}))")

        elif isinstance(child, discord.ui.ActionRow):
            lines.append(f"row_{idx} = ui.ActionRow()")
            for btn in child.children:
                if isinstance(btn, discord.ui.Button):
                    lines.append(f"row_{idx}.add_item(ui.Button(label={btn.label!r}, url={btn.url!r}, style=discord.ButtonStyle.link))")
            lines.append(f"container.add_item(row_{idx})")

    lines.append("")
    lines.append("view.add_item(container)")
    if content:
        lines.append(f"content = {content!r}")
        lines.append("await ctx.send(content, view=view)")
    else:
        lines.append("await ctx.send(view=view)")

    return "\n".join(lines)
