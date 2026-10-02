"""Modern EmbedUtils — create, send, store, and interactively edit embeds."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Union

import aiohttp
import discord
from redbot.core import app_commands, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import pagify, text_to_file

from .converters import (
    ListStringToEmbed,
    MessageableChannel,
    MessageableOrMessageConverter,
    MyMessageConverter,
    PastebinListConverter,
    StringToEmbed,
    read_attachment_text,
)
from .dashboard_integration import DashboardIntegration
from .editor_actions import MakerActions
from .editor_constants import DEFAULT_CONTAINER_TEXT, DEFAULT_CONTAINER_TITLE
from .editor_flags import ContainerArgsConverter, EmbedArgsConverter, clone_container, embed_to_container
from .editor_views import ContainerEditorView, EmbedEditorView
from .errors import EmbedConversionError, EmbedFileError, EmbedLimitReached
from .storage import EmbedStore
from .views import PaginatorView, PopupCreateModal, StoredEmbedDropdown

JSON_LIST = ListStringToEmbed()
YAML_LIST = ListStringToEmbed(conversion_type="yaml")
PASTE_LIST = PastebinListConverter(conversion_type="json")


class EmbedUtils(DashboardIntegration, commands.Cog):
    """Create, send, store, and edit rich embeds with slash, buttons, and modals."""

    __author__ = ["PhenoM4n4n", "AAA3A"]
    __version__ = "3.1.2"

    def format_help_for_context(self, ctx: commands.Context) -> str:
        base = super().format_help_for_context(ctx)
        gap = "\n" if "\n\n" not in base else ""
        return f"{base}{gap}\nVersion {self.__version__}"

    def __init__(self, bot: Red) -> None:
        super().__init__()
        self.bot = bot
        self.store = EmbedStore(self)
        self.config = self.store.config
        self.session: Optional[aiohttp.ClientSession] = None
        self._menus = [
            app_commands.ContextMenu(
                name="Build embed",
                callback=self.context_build,
            ),
            app_commands.ContextMenu(
                name="Download embed JSON",
                callback=self.context_download,
            ),
        ]

    async def cog_load(self) -> None:
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20, connect=10))
        try:
            await self.store.import_legacy()
        except Exception:
            pass
        for menu in self._menus:
            try:
                self.bot.tree.add_command(menu, override=True)
            except Exception:
                pass

    async def cog_unload(self) -> None:
        for menu in self._menus:
            self.bot.tree.remove_command(menu.name, type=discord.AppCommandType.message)
        if self.session is not None and not self.session.closed:
            await self.session.close()

    async def red_delete_data_for_user(self, *, requester: str, user_id: int) -> None:
        await self.store.purge_author(user_id)

    async def cog_command_error(self, ctx: commands.Context, error: Exception) -> None:
        original = getattr(error, "original", error)
        if isinstance(original, (EmbedConversionError, EmbedFileError, EmbedLimitReached)):
            message = str(getattr(original, "error", original))
            if message:
                try:
                    await ctx.send(message)
                except discord.HTTPException:
                    pass
            return
        await ctx.bot.on_command_error(ctx, error, unhandled_by_cog=True)

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    async def is_owner_user(self, user: discord.abc.User) -> bool:
        return await self.bot.is_owner(user)

    async def can_use_global(self, user: discord.abc.User, entry: Optional[dict] = None) -> bool:
        if await self.is_owner_user(user):
            return True
        return not (entry and entry.get("locked"))

    async def parse_source(self, ctx: commands.Context, source: str, data: Optional[str]) -> dict[str, Any]:
        kind = source.lower()
        if kind in {"json", "fromjson", "fromdata"}:
            if not data:
                raise commands.BadArgument("Paste JSON after the command.")
            return await JSON_LIST.convert(ctx, data)
        if kind in {"yaml", "fromyaml", "advmake"}:
            if not data:
                raise commands.BadArgument("Paste YAML after the command.")
            return await YAML_LIST.convert(ctx, data)
        if kind in {"file", "fromfile", "jsonfile", "fromjsonfile", "fromdatafile", "upload"}:
            raw = await read_attachment_text(ctx, ("json", "txt"))
            return await JSON_LIST.convert(ctx, raw)
        if kind in {"yamlfile", "fromyamlfile"}:
            raw = await read_attachment_text(ctx, ("yaml", "yml", "txt"))
            return await YAML_LIST.convert(ctx, raw)
        if kind in {"url", "pastebin", "gist", "hastebin", "frompaste", "frompastebin", "fromgist", "fromhastebin"}:
            if not data:
                raise commands.BadArgument("Provide a Pastebin, Gist, Hastebin, or raw GitHub link.")
            return await PASTE_LIST.convert(ctx, data)
        if kind in {"message", "frommessage", "msg", "frommsg"}:
            message = None
            if data:
                message = await commands.MessageConverter().convert(ctx, data)
            elif ctx.message.reference and isinstance(ctx.message.reference.resolved, discord.Message):
                message = ctx.message.reference.resolved
            if message is None:
                raise commands.BadArgument("Reply to a message or pass a message link.")
            payload: dict[str, Any] = {}
            if message.content:
                payload["content"] = message.content
            if message.embeds:
                payload["embeds"] = list(message.embeds)
            if not payload:
                raise commands.BadArgument("That message has no content or embeds.")
            return payload
        raise commands.BadArgument("Source must be json, yaml, file, yamlfile, url, or message.")

    def destination(
        self,
        ctx: commands.Context,
        target: Optional[Union[discord.Message, discord.abc.Messageable]] = None,
    ):
        return target if target is not None else ctx.channel

    async def publish(
        self,
        ctx: commands.Context,
        payload: dict[str, Any],
        target: Optional[Union[discord.Message, discord.abc.Messageable]] = None,
        *,
        username: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ) -> None:
        dest = self.destination(ctx, target)
        payload = {key: value for key, value in payload.items() if value is not None}
        mentions = discord.AllowedMentions.none()
        perms = getattr(ctx, "permissions", None)
        if perms and getattr(perms, "mention_everyone", False):
            mentions = discord.AllowedMentions(everyone=True, users=True, roles=True)
        try:
            if isinstance(dest, discord.Message):
                await dest.edit(**payload)
                return
            if username:
                await self._webhook_send(dest, payload, username=username, avatar_url=avatar_url)
                return
            await dest.send(**payload, allowed_mentions=mentions)
        except discord.HTTPException as error:
            await StringToEmbed.embed_convert_error(ctx, "Embed Sending Error", error)

    async def _webhook_send(
        self,
        channel: discord.abc.Messageable,
        payload: dict[str, Any],
        *,
        username: str,
        avatar_url: Optional[str],
    ) -> None:
        if not hasattr(channel, "webhooks"):
            raise commands.BadArgument("Webhooks are not available in that destination.")
        hook = None
        try:
            existing = await channel.webhooks()
            hook = discord.utils.find(lambda w: w.name == "EmbedUtils" and w.token, existing)
        except discord.HTTPException:
            hook = None
        created = False
        if hook is None:
            hook = await channel.create_webhook(name="EmbedUtils", reason="EmbedUtils send")
            created = True
        try:
            await hook.send(
                username=username[:80],
                avatar_url=avatar_url or discord.utils.MISSING,
                **payload,
            )
        finally:
            if created:
                try:
                    await hook.delete(reason="EmbedUtils temporary webhook")
                except discord.HTTPException:
                    pass

    async def save_stored_embed(self, **kwargs):
        return await self.store.save(**kwargs)

    async def increment_uses(self, guild, name: str, global_level: bool = False) -> None:
        await self.store.bump(guild, name, global_level)

    async def lookup(self, ctx: commands.Context, name: str, global_level: bool) -> dict:
        entry = await self.store.get(ctx.guild, name, global_level)
        if not entry:
            raise commands.BadArgument(f'`{name}` is not stored{" globally" if global_level else ""}.')
        if global_level and not await self.can_use_global(ctx.author, entry):
            raise commands.BadArgument(f"`{name}` is not stored globally.")
        return entry

    async def autocomplete_names(self, interaction: discord.Interaction, current: str, global_level: bool = False):
        guild = interaction.guild
        owner = interaction.user.id in getattr(self.bot, "owner_ids", set())
        store = await self.store.visible(guild, global_level, viewer=interaction.user, is_owner=owner)
        needle = current.lower()
        names = [n for n in store if needle in n.lower()][:25]
        return [app_commands.Choice(name=n[:100], value=n) for n in names]

    # ------------------------------------------------------------------
    # Root
    # ------------------------------------------------------------------

    @commands.guild_only()
    @commands.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(embed_links=True)
    @commands.hybrid_group(invoke_without_command=True, aliases=["embedutils"])
    async def embed(
        self,
        ctx: commands.Context,
        channel_or_message: Optional[MessageableOrMessageConverter] = None,
        color: Optional[discord.Color] = None,
        title: str = None,
        *,
        description: str = None,
    ) -> None:
        """Post a simple embed, or run a subcommand.

        Quote the title if it has spaces. Pass a bot message to edit it.
        """
        if title is None or description is None:
            await ctx.send_help()
            return
        payload = {
            "embed": discord.Embed(
                color=color or await ctx.embed_color(),
                title=title,
                description=description,
            )
        }
        await self.publish(ctx, payload, channel_or_message)

    # ------------------------------------------------------------------
    # Compose / send
    # ------------------------------------------------------------------

    @embed.command(name="send")
    async def embed_send(
        self,
        ctx: commands.Context,
        source: str,
        channel_or_message: Optional[MessageableOrMessageConverter] = None,
        *,
        data: str = None,
    ) -> None:
        """Send embeds from `json`, `yaml`, `file`, `yamlfile`, `url`, or `message`."""
        if source.lower() in {"json", "yaml"} and data is None and ctx.message.attachments:
            source = "yamlfile" if source.lower() == "yaml" else "file"
        await self.publish(ctx, await self.parse_source(ctx, source, data), channel_or_message)

    @embed.command(name="json", aliases=["fromjson", "fromdata"])
    async def embed_json(
        self,
        ctx: commands.Context,
        channel_or_message: Optional[MessageableOrMessageConverter] = None,
        *,
        data: str = None,
    ) -> None:
        """Send embeds from JSON. Attach a file to use that instead."""
        kind = "file" if data is None else "json"
        await self.publish(ctx, await self.parse_source(ctx, kind, data), channel_or_message)

    @embed.command(name="yaml", aliases=["fromyaml", "advmake", "advnostore"])
    async def embed_yaml(
        self,
        ctx: commands.Context,
        channel_or_message: Optional[MessageableOrMessageConverter] = None,
        *,
        data: str = None,
    ) -> None:
        """Send embeds from YAML."""
        kind = "yamlfile" if data is None else "yaml"
        await self.publish(ctx, await self.parse_source(ctx, kind, data), channel_or_message)

    @embed.command(name="fromfile", aliases=["jsonfile", "fromjsonfile", "fromdatafile", "upload", "uploadnostore"])
    async def embed_fromfile(
        self,
        ctx: commands.Context,
        channel_or_message: Optional[MessageableOrMessageConverter] = None,
    ) -> None:
        """Send from an attached JSON file."""
        await self.publish(ctx, await self.parse_source(ctx, "file", None), channel_or_message)

    @embed.command(name="yamlfile", aliases=["fromyamlfile"])
    async def embed_yamlfile(
        self,
        ctx: commands.Context,
        channel_or_message: Optional[MessageableOrMessageConverter] = None,
    ) -> None:
        """Send from an attached YAML file."""
        await self.publish(ctx, await self.parse_source(ctx, "yamlfile", None), channel_or_message)

    @embed.command(name="pastebin", aliases=["frompaste", "frompastebin", "gist", "fromgist", "hastebin", "fromhastebin", "url"])
    async def embed_url(
        self,
        ctx: commands.Context,
        channel_or_message: Optional[MessageableOrMessageConverter] = None,
        *,
        data: str,
    ) -> None:
        """Send from Pastebin, Gist, Hastebin, or a raw GitHub file."""
        await self.publish(ctx, await self.parse_source(ctx, "url", data), channel_or_message)

    @embed.command(name="message", aliases=["frommessage", "msg", "frommsg"])
    async def embed_message(
        self,
        ctx: commands.Context,
        channel_or_message: Optional[MessageableOrMessageConverter] = None,
        message: Optional[discord.Message] = None,
        index: Optional[int] = None,
        include_content: Optional[bool] = None,
    ) -> None:
        """Clone embeds from a message. Reply to skip the ID."""
        if message is None:
            if ctx.message.reference and isinstance(ctx.message.reference.resolved, discord.Message):
                message = ctx.message.reference.resolved
            else:
                raise commands.BadArgument("Reply to a message or pass a link.")
        payload: dict[str, Any] = {}
        if include_content is None:
            include_content = index is None and bool(message.content)
        if include_content and message.content:
            payload["content"] = message.content
        if index is None:
            payload["embeds"] = list(message.embeds)
        else:
            try:
                payload["embeds"] = [message.embeds[index]]
            except IndexError as exc:
                raise commands.BadArgument("That embed index does not exist.") from exc
        if not payload:
            raise commands.BadArgument("That message has no embeds.")
        await self.publish(ctx, payload, channel_or_message)

    @embed.command(name="edit", aliases=["editmsg"])
    async def embed_edit(
        self,
        ctx: commands.Context,
        message: MyMessageConverter,
        source: Optional[str] = None,
        *,
        data: str = None,
    ) -> None:
        """Edit a bot message from json/yaml/file/url/message, or title + description."""
        known = {
            "json", "yaml", "file", "yamlfile", "url", "message",
            "fromjson", "fromdata", "fromyaml", "pastebin", "gist", "hastebin",
            "frommessage", "frommsg", "msg", "jsonfile", "fromfile",
        }
        if source and source.lower() in known:
            payload = await self.parse_source(ctx, source, data)
        elif source:
            payload = {
                "embed": discord.Embed(
                    color=await ctx.embed_color(),
                    title=source,
                    description=data or "",
                )
            }
        else:
            raise commands.BadArgument("Provide a source type or a title and description.")
        await self.publish(ctx, payload, message)

    # ------------------------------------------------------------------
    # Interactive
    # ------------------------------------------------------------------

    @embed.command(name="builder", aliases=["editor", "interactive", "buttons", "make", "create", "embedcreate", "ecreate"])
    async def embed_builder(
        self,
        ctx: commands.Context,
        channel: Optional[MessageableChannel] = None,
        message: Optional[discord.Message] = None,
        *,
        options: str = None,
    ) -> None:
        """Open the button builder. Flags: title:, description:, colour:, source:, content:."""
        from .editor_flags import EmbedArgsConverter
        from .editor_views import EmbedEditorView

        parsed = None
        if options:
            parsed = await EmbedArgsConverter().convert(ctx, options)
        if message is None and parsed is not None and parsed.source is not None:
            message = parsed.source
        if message is None and ctx.message.reference and isinstance(ctx.message.reference.resolved, discord.Message):
            message = ctx.message.reference.resolved
        start = message.embeds[0].copy() if message and message.embeds else None
        content = (parsed.content if parsed and parsed.content else None) or (message.content if message else None)
        view = EmbedEditorView(ctx, embed=start, content=content)
        if parsed is not None:
            if parsed.title:
                view.embed.title = parsed.title
            if parsed.description:
                view.embed.description = parsed.description
            if parsed.colour:
                view.embed.colour = parsed.colour
            if parsed.url:
                view.embed.url = parsed.url
            if parsed.image:
                view.embed.set_image(url=parsed.image)
            if parsed.thumbnail:
                view.embed.set_thumbnail(url=parsed.thumbnail)
            if kwargs := parsed.author_kwargs():
                if kwargs.get("name"):
                    view.embed.set_author(**kwargs)
            if kwargs := parsed.footer_kwargs():
                if kwargs.get("text"):
                    view.embed.set_footer(**kwargs)
        try:
            view.message = await ctx.send(embed=view.embed, content=view.content, view=view)
        except discord.HTTPException as error:
            await ctx.send(f"Could not open the builder: {error}")
            return
        await ctx.send(
            "Store, update, or turn this into a server event:",
            view=MakerActions(self, view, channel or ctx.channel),
        )

    @embed.command(name="container", aliases=["containercreate", "ccreate"])
    async def embed_container(self, ctx: commands.Context, *, options: str = None) -> None:
        """Open the Components V2 container builder when this discord.py build supports it."""
        import contextlib
        from redbot.core.utils.chat_formatting import box

        if not (hasattr(discord.ui, "Container") and hasattr(discord.ui, "LayoutView")):
            await ctx.send(
                "Containers need discord.py 2.6+ with Components V2. "
                f"This bot is on `{discord.__version__}`."
            )
            return
        parsed = (
            await ContainerArgsConverter().convert(ctx, options)
            if options
            else await ContainerArgsConverter._construct_default(ctx)
        )
        container = None
        if parsed.source and parsed.source.components:
            with contextlib.suppress(Exception):
                src_view = discord.ui.LayoutView.from_message(parsed.source)
                for item in src_view.children:
                    if isinstance(item, discord.ui.Container):
                        container = clone_container(item)
                        break
        if container is None and parsed.source and parsed.source.embeds:
            container = embed_to_container(parsed.source.embeds[0])
        if container is None:
            container = discord.ui.Container(
                accent_colour=parsed.accent_colour or discord.Colour.blurple(),
                spoiler=bool(parsed.spoiler),
            )
            container.add_item(discord.ui.TextDisplay(f"# {DEFAULT_CONTAINER_TITLE}"))
            container.add_item(discord.ui.TextDisplay(DEFAULT_CONTAINER_TEXT.replace("[p]", ctx.clean_prefix)))
        if parsed.text:
            container.add_item(discord.ui.TextDisplay(parsed.text))
        try:
            view = ContainerEditorView(ctx, container=container, content=parsed.content)
            view.message = await ctx.send(view=view, content=parsed.content)
        except discord.HTTPException as error:
            await ctx.send(f"Could not open the container builder: {box(getattr(error, 'text', str(error)), lang='py')}")
            return
        await ctx.send("Store or schedule once this is converted back to an embed.", view=MakerActions(self, view, ctx.channel))

    @embed.command(name="popup", aliases=["modal", "popout"])
    async def embed_popup(self, ctx: commands.Context, channel: Optional[MessageableChannel] = None) -> None:
        """Create an embed from a modal popup."""
        dest = channel or ctx.channel
        if ctx.interaction is not None:
            await ctx.interaction.response.send_modal(PopupCreateModal(self, dest, ctx.author))
            return
        view = _ModalLaunch(self, ctx.author.id, dest)
        await ctx.send("Open the popup to create an embed.", view=view)

    @embed.command(name="dropdown", aliases=["pick", "select"])
    async def embed_dropdown(
        self,
        ctx: commands.Context,
        channel: Optional[MessageableChannel] = None,
        global_level: bool = False,
    ) -> None:
        """Pick stored embeds from a dropdown and post them."""
        owner = await self.is_owner_user(ctx.author)
        store = await self.store.visible(ctx.guild, global_level, viewer=ctx.author, is_owner=owner)
        entries = []
        for name, entry in sorted(store.items()):
            item = dict(entry)
            item["name"] = name
            item["_global"] = global_level
            entries.append(item)
        if not entries:
            await ctx.send("Nothing is stored there yet.")
            return
        view = StoredEmbedDropdown(
            cog=self,
            author=ctx.author,
            entries=entries[:25],
            channel=channel or ctx.channel,
        )
        await ctx.send("Select stored embeds to post.", view=view)

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    @embed.command(name="store", aliases=["storeembed"])
    async def embed_store(
        self,
        ctx: commands.Context,
        name: str,
        source: Optional[str] = "json",
        global_level: bool = False,
        locked: bool = False,
        *,
        data: str = None,
    ) -> None:
        """Save an embed. Source: json, yaml, file, yamlfile, url, message."""
        if global_level and not await self.is_owner_user(ctx.author):
            raise commands.BadArgument("Only the bot owner can store global embeds.")
        payload = await self.parse_source(ctx, source or "json", data)
        embeds = payload.get("embeds") or ([payload["embed"]] if payload.get("embed") else [])
        if not embeds:
            raise commands.BadArgument("No embed found in that source.")
        try:
            await self.store.save(
                guild=ctx.guild,
                name=name,
                embed=embeds[0],
                author_id=ctx.author.id,
                global_level=global_level,
                locked=locked,
                content=payload.get("content"),
            )
        except ValueError as error:
            raise commands.BadArgument(str(error)) from error
        await ctx.send(f"Saved `{name}` ({'global' if global_level else 'server'}).")

    @embed.command(name="frommsgstore", aliases=["globalfrommsg"])
    async def embed_frommsgstore(
        self,
        ctx: commands.Context,
        name: str,
        message: Optional[discord.Message] = None,
        global_level: bool = False,
    ) -> None:
        """Store the first embed on a message."""
        if message is None and ctx.message.reference and isinstance(ctx.message.reference.resolved, discord.Message):
            message = ctx.message.reference.resolved
        if message is None or not message.embeds:
            raise commands.BadArgument("Reply to a message that has an embed.")
        if global_level and not await self.is_owner_user(ctx.author):
            raise commands.BadArgument("Only the bot owner can store global embeds.")
        await self.store.save(
            guild=ctx.guild,
            name=name,
            embed=message.embeds[0],
            author_id=ctx.author.id,
            global_level=global_level,
            content=message.content or None,
        )
        await ctx.send(f"Saved `{name}`.")

    @embed.command(name="update", aliases=["updatestored"])
    async def embed_update(
        self,
        ctx: commands.Context,
        name: str,
        source: Optional[str] = "json",
        global_level: bool = False,
        *,
        data: str = None,
    ) -> None:
        """Overwrite an existing stored embed. Uses and original author stay."""
        existing = await self.lookup(ctx, name, global_level)
        if global_level and not await self.is_owner_user(ctx.author):
            raise commands.BadArgument("Only the bot owner can update global embeds.")
        payload = await self.parse_source(ctx, source or "json", data)
        embeds = payload.get("embeds") or ([payload["embed"]] if payload.get("embed") else [])
        if not embeds:
            raise commands.BadArgument("No embed found in that source.")
        await self.store.save(
            guild=ctx.guild,
            name=name,
            embed=embeds[0],
            author_id=existing.get("author") or ctx.author.id,
            global_level=global_level,
            locked=bool(existing.get("locked")),
            content=payload.get("content"),
        )
        await ctx.send(f"Updated `{name}`.")

    @embed_update.autocomplete("name")
    async def _ac_update(self, interaction: discord.Interaction, current: str):
        return await self.autocomplete_names(interaction, current)

    @embed.command(name="unstore", aliases=["unstoreembed", "remove", "delete", "rmglobal"])
    async def embed_unstore(
        self,
        ctx: commands.Context,
        name: str,
        global_level: bool = False,
    ) -> None:
        """Delete a stored embed."""
        if global_level and not await self.is_owner_user(ctx.author):
            raise commands.BadArgument("Only the bot owner can delete global embeds.")
        if not await self.store.delete(ctx.guild, name, global_level):
            raise commands.BadArgument(f"`{name}` was not stored.")
        await ctx.send(f"Deleted `{name}`.")

    @embed_unstore.autocomplete("name")
    async def _ac_unstore(self, interaction: discord.Interaction, current: str):
        return await self.autocomplete_names(interaction, current)

    @embed.command(name="list", aliases=["liststored", "liststoredembeds"])
    async def embed_list(self, ctx: commands.Context, global_level: bool = False) -> None:
        """List stored embeds."""
        owner = await self.is_owner_user(ctx.author)
        store = await self.store.visible(ctx.guild, global_level, viewer=ctx.author, is_owner=owner)
        if not store:
            await ctx.send("Nothing stored there.")
            return
        lines = []
        for name, entry in sorted(store.items()):
            lock = " lock" if entry.get("locked") else ""
            lines.append(f"`{name}`{lock} · {entry.get('uses', 0)} uses · <@{entry.get('author')}>")
        title = "Global embeds" if global_level else "Server embeds"
        pages = [
            discord.Embed(title=title, description=chunk, color=await ctx.embed_color())
            for chunk in pagify("\n".join(lines), page_length=900)
        ]
        if len(pages) == 1:
            await ctx.send(embed=pages[0])
            return
        await ctx.send(embed=pages[0], view=PaginatorView(pages, ctx.author.id))

    @embed.command(name="info", aliases=["infostored", "infostoredembed"])
    async def embed_info(self, ctx: commands.Context, name: str, global_level: bool = False) -> None:
        """Show storage metadata for an embed."""
        entry = await self.lookup(ctx, name, global_level)
        built = discord.Embed.from_dict(entry["embed"])
        info = discord.Embed(
            title=name,
            color=built.color or await ctx.embed_color(),
            description="\n".join(
                [
                    f"Author: <@{entry.get('author')}>",
                    f"Uses: {entry.get('uses', 0)}",
                    f"Locked: {bool(entry.get('locked'))}",
                    f"Characters: {len(built)}",
                    f"Updated: {entry.get('updated_at', 'unknown')}",
                ]
            ),
        )
        await ctx.send(embed=info)

    @embed_info.autocomplete("name")
    async def _ac_info(self, interaction: discord.Interaction, current: str):
        return await self.autocomplete_names(interaction, current)

    @commands.bot_has_permissions(attach_files=True)
    @embed.command(name="download")
    async def embed_download(
        self,
        ctx: commands.Context,
        message: Optional[discord.Message] = None,
        index: Optional[int] = None,
        include_content: Optional[bool] = None,
    ) -> None:
        """Download JSON from a message's embeds."""
        if message is None:
            if ctx.message.reference and isinstance(ctx.message.reference.resolved, discord.Message):
                message = ctx.message.reference.resolved
            else:
                raise commands.BadArgument("Reply to a message or pass a link.")
        payload: dict[str, Any] = {}
        if include_content is None:
            include_content = index is None
        if include_content and message.content:
            payload["content"] = message.content
        if index is None:
            payload["embeds"] = [item.to_dict() for item in message.embeds]
        else:
            try:
                payload["embeds"] = [message.embeds[index].to_dict()]
            except IndexError as exc:
                raise commands.BadArgument("That embed index does not exist.") from exc
        await ctx.send(file=text_to_file(json.dumps(payload, indent=2), filename="embed.json"))

    @commands.bot_has_permissions(attach_files=True)
    @embed.command(name="downloadstored", aliases=["downloadstoredembed"])
    async def embed_download_stored(
        self, ctx: commands.Context, name: str, global_level: bool = False
    ) -> None:
        """Download JSON for a stored embed."""
        entry = await self.lookup(ctx, name, global_level)
        payload = {"embed": entry["embed"]}
        if entry.get("content"):
            payload["content"] = entry["content"]
        await ctx.send(file=text_to_file(json.dumps(payload, indent=2), filename=f"{name}.json"))

    @embed_download_stored.autocomplete("name")
    async def _ac_dl(self, interaction: discord.Interaction, current: str):
        return await self.autocomplete_names(interaction, current)

    @embed.command(name="post", aliases=["poststored", "poststoredembed", "drop", "view", "show", "dropglobal"])
    async def embed_post(
        self,
        ctx: commands.Context,
        names: str,
        channel: Optional[MessageableChannel] = None,
        global_level: bool = False,
    ) -> None:
        """Post stored embeds. Separate names with spaces."""
        embeds = []
        content = None
        for name in names.split():
            entry = await self.lookup(ctx, name, global_level)
            embeds.append(discord.Embed.from_dict(entry["embed"]))
            content = content or entry.get("content")
            await self.store.bump(ctx.guild, name, global_level)
        if not embeds:
            raise commands.BadArgument("No embeds to post.")
        await self.publish(ctx, {"content": content, "embeds": embeds}, channel)

    @embed.command(name="webhook", aliases=["postwebhook"])
    async def embed_webhook(
        self,
        ctx: commands.Context,
        username: str,
        names: str,
        channel: Optional[MessageableChannel] = None,
        avatar_url: Optional[str] = None,
        global_level: bool = False,
    ) -> None:
        """Post stored embeds through a webhook identity."""
        embeds = []
        content = None
        for name in names.split():
            entry = await self.lookup(ctx, name, global_level)
            embeds.append(discord.Embed.from_dict(entry["embed"]))
            content = content or entry.get("content")
            await self.store.bump(ctx.guild, name, global_level)
        await self.publish(
            ctx,
            {"content": content, "embeds": embeds},
            channel,
            username=username,
            avatar_url=avatar_url,
        )

    @embed.command(name="dm", aliases=["dmglobal"])
    async def embed_dm(
        self,
        ctx: commands.Context,
        member: discord.Member,
        name: str,
        global_level: bool = False,
    ) -> None:
        """DM a stored embed."""
        entry = await self.lookup(ctx, name, global_level)
        try:
            await member.send(content=entry.get("content"), embed=discord.Embed.from_dict(entry["embed"]))
        except discord.HTTPException:
            await ctx.send("I could not DM that member.")
            return
        await self.store.bump(ctx.guild, name, global_level)
        await ctx.send(f"Sent `{name}` to {member}.")

    @embed_dm.autocomplete("name")
    async def _ac_dm(self, interaction: discord.Interaction, current: str):
        return await self.autocomplete_names(interaction, current)

    @embed.command(name="dmme", aliases=["dmmeglobal"])
    async def embed_dmme(self, ctx: commands.Context, name: str, global_level: bool = False) -> None:
        """DM a stored embed to yourself."""
        await self.embed_dm(ctx, ctx.author, name, global_level)

    @embed.command(name="event")
    async def embed_event(
        self,
        ctx: commands.Context,
        title: str,
        when: str,
        channel: Optional[MessageableChannel] = None,
        schedule: bool = False,
        location: Optional[str] = None,
        end: Optional[str] = None,
        color: Optional[discord.Color] = None,
        *,
        description: str = "",
    ) -> None:
        """Event embed. Set schedule to true to also create a Discord server event.

        `when` and `end` accept `now` or ISO-8601. External events need a location.
        """
        if when.lower() == "now":
            moment = datetime.now(timezone.utc)
        else:
            try:
                moment = datetime.fromisoformat(when.replace("Z", "+00:00"))
            except ValueError as exc:
                raise commands.BadArgument("Use `now` or an ISO-8601 timestamp.") from exc
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
        unix = int(moment.timestamp())
        body = f"{description}\n\n<t:{unix}:F> (<t:{unix}:R>)" if description else f"<t:{unix}:F> (<t:{unix}:R>)"
        embed = discord.Embed(
            title=title,
            description=body,
            color=color or await ctx.embed_color(),
            timestamp=moment,
        )
        await self.publish(ctx, {"embed": embed}, channel)
        if schedule:
            if end:
                try:
                    end_at = datetime.fromisoformat(end.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise commands.BadArgument("End time must be ISO-8601.") from exc
                if end_at.tzinfo is None:
                    end_at = end_at.replace(tzinfo=timezone.utc)
            else:
                end_at = moment + timedelta(hours=1)
            if end_at <= moment:
                end_at = moment + timedelta(hours=1)
            try:
                event = await self.create_server_event(
                    ctx.guild,
                    name=title[:100],
                    description=(description or "")[:1000] or None,
                    start=moment,
                    end=end_at,
                    location=(location or "Discord")[:100],
                )
            except discord.Forbidden:
                await ctx.send("Embed posted, but I need Manage Events to create the server event.")
                return
            except discord.HTTPException as error:
                await ctx.send(f"Embed posted, but Discord rejected the server event: {error}")
                return
            await ctx.send(f"Server event created: {event.url}")

    async def create_server_event(self, guild, *, name, description, start, end, location):
        return await guild.create_scheduled_event(
            name=name,
            description=description,
            start_time=start,
            end_time=end,
            entity_type=discord.EntityType.external,
            location=location or "Discord",
            privacy_level=discord.PrivacyLevel.guild_only,
        )

    @embed.command(name="dashboard")
    async def embed_dashboard(self, ctx: commands.Context) -> None:
        """Visual editor links."""
        extra = ""
        if ctx.bot.get_cog("Dashboard"):
            extra = "\nRed-Web-Dashboard is loaded; this cog registers an editor page there."
        await ctx.send(f"https://embedutils.com/{extra}")

    @commands.is_owner()
    @embed.command(name="limits")
    async def embed_limits(
        self, ctx: commands.Context, guild_limit: Optional[int] = None, global_limit: Optional[int] = None
    ) -> None:
        """Show or set storage caps."""
        if guild_limit is not None:
            await self.config.guild_limit.set(max(1, min(guild_limit, 200)))
        if global_limit is not None:
            await self.config.global_limit.set(max(1, min(global_limit, 200)))
        await ctx.send(
            f"Guild cap: {await self.config.guild_limit()} · Global cap: {await self.config.global_limit()}"
        )

    # ------------------------------------------------------------------
    # Context menus
    # ------------------------------------------------------------------

    async def context_build(self, interaction: discord.Interaction, message: discord.Message) -> None:
        member = interaction.user
        if interaction.guild and isinstance(member, discord.Member):
            if not (member.guild_permissions.manage_messages or await self.bot.is_mod(member) or await self.is_owner_user(member)):
                await interaction.response.send_message("You need Manage Messages to use this.", ephemeral=True)
                return
        start = message.embeds[0].copy() if message.embeds else None
        from .editor_views import EmbedEditorView

        dummy = type("Ctx", (), {"author": interaction.user, "clean_prefix": "/"})()
        view = EmbedEditorView(dummy, embed=start, content=message.content or None)
        await interaction.response.send_message(embed=view.embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()
        await interaction.followup.send(
            "Store, update, or turn this into a server event:",
            view=MakerActions(self, view, interaction.channel),
            ephemeral=True,
        )

    async def context_download(self, interaction: discord.Interaction, message: discord.Message) -> None:
        payload = {}
        if message.content:
            payload["content"] = message.content
        payload["embeds"] = [item.to_dict() for item in message.embeds]
        raw = json.dumps(payload, indent=2)
        await interaction.response.send_message(
            file=text_to_file(raw, filename="embed.json"),
            ephemeral=True,
        )


class _ModalLaunch(discord.ui.View):
    def __init__(self, cog: EmbedUtils, author_id: int, channel: discord.abc.Messageable):
        super().__init__(timeout=90)
        self.cog = cog
        self.author_id = author_id
        self.channel = channel

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    @discord.ui.button(label="Open popup", style=discord.ButtonStyle.primary)
    async def open_popup(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PopupCreateModal(self.cog, self.channel, interaction.user))
