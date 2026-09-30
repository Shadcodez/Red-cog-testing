"""Converters for JSON/YAML embeds, stored names, channels, and paste hosts."""

from __future__ import annotations

import json
import re
import textwrap
from typing import Any, Dict, List, Optional, Union

import discord
import yaml
from redbot.core import commands
from redbot.core.utils.chat_formatting import box

from .errors import EmbedConversionError

PASTEBIN_RE = re.compile(r"(?:https?://(?:www\.)?)?pastebin\.com/(?:raw/)?([a-zA-Z0-9]+)")
GIST_RE = re.compile(
    r"(?:https?://)?gist\.github\.com/([^/]+)/([a-zA-Z0-9]+)(?:#file-.*)?"
)
GIST_RAW_RE = re.compile(
    r"(?:https?://)?gist\.githubusercontent\.com/([^/]+)/([a-zA-Z0-9]+)/raw(?:/.*)?"
)
HASTE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(hastebin\.com|hastebin\.skyra\.pw|hst\.sh)/([a-zA-Z0-9]+)"
)
GITHUB_RE = re.compile(
    r"(?:https?://)?github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)"
)


def cleanup_code(code: str) -> str:
    code = textwrap.dedent(code).strip()
    if code.startswith("```") and code.endswith("```"):
        code = code[3:-3]
        if "\n" in code:
            first, rest = code.split("\n", 1)
            if first.strip() in {"json", "yaml", "yml", "py", "python"}:
                code = rest
    code = code.strip("` \n")
    if code.lower().startswith("json\n"):
        code = code[5:]
    return code


class StringToEmbed(commands.Converter):
    def __init__(
        self,
        *,
        conversion_type: str = "json",
        validate: bool = False,
        content: bool = False,
        allow_content: Optional[bool] = None,
    ) -> None:
        self.conversion_type = conversion_type.lower()
        self.validate = validate
        self.allow_content = content if allow_content is None else allow_content
        self.CONVERSION_TYPES = {
            "json": self.load_from_json,
            "yaml": self.load_from_yaml,
        }
        try:
            self.converter = self.CONVERSION_TYPES[self.conversion_type]
        except KeyError as exc:
            raise ValueError(f"{conversion_type} is not a valid conversion type.") from exc

    async def convert(self, ctx: commands.Context, argument: str) -> discord.Embed:
        data = await self.converter(ctx, cleanup_code(argument))
        content = self.get_content(data) if isinstance(data, dict) else None
        if isinstance(data, list):
            data = data[0] if data else {}
        elif isinstance(data, dict):
            if data.get("embed"):
                data = data["embed"]
            elif data.get("embeds"):
                embeds = data.get("embeds")
                data = embeds[0] if isinstance(embeds, list) and embeds else embeds
        self.check_data_type(ctx, data)
        fields = await self.create_embed(ctx, data, content=content)
        embed = fields["embed"]
        if self.validate:
            await self.validate_embed(ctx, embed, content=fields.get("content"))
        return embed

    def check_data_type(self, ctx: commands.Context, data, *, data_type=dict) -> None:
        if not isinstance(data, data_type):
            raise commands.BadArgument(
                f"This doesn't seem to be properly formatted embed {self.conversion_type.upper()}. "
                f"See `{ctx.clean_prefix}help {ctx.command.qualified_name}`."
            )

    async def load_from_json(self, ctx: commands.Context, data: str, **kwargs) -> Any:
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as error:
            await self.embed_convert_error(ctx, "JSON Parse Error", error)
            raise commands.BadArgument()
        self.check_data_type(ctx, parsed, **kwargs)
        return parsed

    async def load_from_yaml(self, ctx: commands.Context, data: str, **kwargs) -> Any:
        try:
            parsed = yaml.safe_load(data)
        except Exception as error:
            await self.embed_convert_error(ctx, "YAML Parse Error", error)
            raise commands.BadArgument()
        self.check_data_type(ctx, parsed, **kwargs)
        return parsed

    def get_content(self, data: dict, *, content: str = None) -> Optional[str]:
        content = data.pop("content", content) if isinstance(data, dict) else content
        if content is not None and not self.allow_content:
            raise commands.BadArgument("The `content` field is not supported for this command.")
        return content

    async def create_embed(
        self, ctx: commands.Context, data: dict, *, content: str = None
    ) -> Dict[str, Union[discord.Embed, str, None]]:
        content = self.get_content(data, content=content) if isinstance(data, dict) else content
        if isinstance(data, dict):
            if data.get("color") is None:
                data.pop("color", None)
            timestamp = data.get("timestamp")
            if timestamp is not None:
                data["timestamp"] = (
                    timestamp.strip("Z") if isinstance(timestamp, str) else str(timestamp)
                )
            else:
                data.pop("timestamp", None)
        try:
            embed = discord.Embed.from_dict(data)
            length = len(embed)
        except Exception as error:
            await self.embed_convert_error(ctx, "Embed Parse Error", error)
            raise commands.BadArgument()
        if length > 6000:
            raise commands.BadArgument(
                f"Embed size exceeds Discord limit of 6000 characters ({length})."
            )
        return {"embed": embed, "content": content}

    async def validate_embed(
        self, ctx: commands.Context, embed: discord.Embed, *, content: str = None
    ) -> None:
        try:
            await ctx.channel.send(content=content, embed=embed)
        except discord.HTTPException as error:
            await self.embed_convert_error(ctx, "Embed Send Error", error)
            raise commands.BadArgument()

    @staticmethod
    async def embed_convert_error(ctx: commands.Context, error_type: str, error: Exception) -> None:
        embed = discord.Embed(
            title=f"{error_type}: `{type(error).__name__}`",
            description=box(str(error), lang="py"),
            color=await ctx.embed_color(),
        )
        command = getattr(ctx.command, "qualified_name", "embed")
        embed.set_footer(text=f"Use `{ctx.clean_prefix}help {command}` to see an example.")
        try:
            await ctx.send(embed=embed)
        except discord.HTTPException:
            await ctx.send(f"{error_type}: {error}")
        raise EmbedConversionError(error_type, error)


class ListStringToEmbed(StringToEmbed):
    def __init__(self, *, conversion_type: str = "json", limit: int = 10, content: bool = True):
        super().__init__(conversion_type=conversion_type, allow_content=content)
        self.limit = min(limit, 10)

    async def convert(self, ctx: commands.Context, argument: str) -> Dict[str, Any]:
        data = await self.converter(ctx, cleanup_code(argument), data_type=(dict, list))
        content = data.get("content") if isinstance(data, dict) else None
        if isinstance(data, list):
            raw = data
        elif isinstance(data, dict) and "embed" in data:
            raw = [data["embed"]]
        elif isinstance(data, dict) and "embeds" in data:
            raw = data["embeds"]
            if isinstance(raw, dict):
                raw = list(raw.values())
        elif isinstance(data, dict) and "content" in data and len(data) == 1:
            raw = []
        else:
            raw = [data]
        self.check_data_type(ctx, raw, data_type=list)
        embeds: List[discord.Embed] = []
        for i, embed_data in enumerate(raw, 1):
            fields = await self.create_embed(ctx, embed_data)
            embeds.append(fields["embed"])
            if i > self.limit:
                raise commands.BadArgument(f"Embed limit reached ({self.limit}).")
        if content or embeds:
            return {"content": content, "embeds": embeds}
        raise commands.BadArgument("Failed to convert input into embeds.")


class StoredEmbedConverter(commands.Converter):
    async def convert(self, ctx: commands.Context, name: str) -> dict:
        cog = ctx.cog
        data = await cog.config.guild(ctx.guild).embeds()
        embed = data.get(name)
        if not embed:
            raise commands.BadArgument(f'Embed "{name}" not found.')
        result = dict(embed)
        result.update(name=name)
        return result


class GlobalStoredEmbedConverter(commands.Converter):
    async def convert(self, ctx: commands.Context, name: str) -> dict:
        cog = ctx.cog
        data = await cog.config.embeds()
        embed = data.get(name)
        if not embed:
            raise commands.BadArgument(f'Global embed "{name}" not found.')
        can_view = await ctx.bot.is_owner(ctx.author) or not embed.get("locked")
        if not can_view:
            raise commands.BadArgument(f'Global embed "{name}" not found.')
        result = dict(embed)
        result.update(name=name)
        return result


class MyMessageConverter(commands.MessageConverter):
    async def convert(self, ctx: commands.Context, argument: str) -> discord.Message:
        message = await super().convert(ctx, argument)
        if message.author.id != ctx.me.id:
            raise commands.BadArgument("That is not a message sent by me.")
        channel = message.channel
        if not channel.permissions_for(ctx.me).send_messages:
            mention = getattr(channel, "mention", str(channel))
            raise commands.BadArgument(f"I do not have permissions to send/edit messages in {mention}.")
        return message


class MessageableChannel(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str):
        channel = None
        for converter in (
            commands.TextChannelConverter,
            commands.VoiceChannelConverter,
            commands.ThreadConverter,
        ):
            try:
                channel = await converter().convert(ctx, argument)
                break
            except commands.BadArgument:
                continue
        if channel is None:
            raise commands.BadArgument("That's not a valid text channel, voice channel, or thread.")
        bot_perms = channel.permissions_for(ctx.me)
        if not (bot_perms.send_messages and bot_perms.embed_links):
            raise commands.BadArgument(f"I do not have permissions to send embeds in {channel.mention}.")
        author_perms = channel.permissions_for(ctx.author)
        if not (author_perms.send_messages and author_perms.embed_links):
            raise commands.BadArgument(
                f"You do not have permissions to send embeds in {channel.mention}."
            )
        return channel


class MessageableOrMessageConverter(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str):
        try:
            return await MyMessageConverter().convert(ctx, argument)
        except commands.BadArgument:
            pass
        try:
            message = await commands.MessageConverter().convert(ctx, argument)
            if message.author.id == ctx.me.id:
                return message
        except commands.BadArgument:
            pass
        return await MessageableChannel().convert(ctx, argument)


class PastebinMixin:
    async def fetch_remote(self, ctx: commands.Context, argument: str) -> str:
        session = getattr(ctx.cog, "session", None)
        if session is None:
            raise commands.BadArgument("HTTP session is not available.")
        url = await self.resolve_url(argument)
        async with session.get(url) as resp:
            if resp.status != 200:
                raise commands.BadArgument(f"`{argument}` could not be fetched ({resp.status}).")
            return await resp.text()

    @staticmethod
    async def resolve_url(argument: str) -> str:
        argument = argument.strip()
        if match := PASTEBIN_RE.fullmatch(argument) or PASTEBIN_RE.search(argument):
            return f"https://pastebin.com/raw/{match.group(1)}"
        if match := GIST_RAW_RE.search(argument):
            return argument if argument.startswith("http") else f"https://{argument}"
        if match := GIST_RE.search(argument):
            user, gist_id = match.group(1), match.group(2)
            return f"https://gist.githubusercontent.com/{user}/{gist_id}/raw"
        if match := HASTE_RE.search(argument):
            host, paste_id = match.group(1), match.group(2)
            return f"https://{host}/raw/{paste_id}"
        if match := GITHUB_RE.search(argument):
            user, repo, branch, path = match.groups()
            return f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{path}"
        if argument.startswith("http://") or argument.startswith("https://"):
            return argument
        raise commands.BadArgument(f"`{argument}` is not a recognized Pastebin, Gist, Hastebin, or GitHub link.")


class PastebinConverter(PastebinMixin, StringToEmbed):
    async def convert(self, ctx: commands.Context, argument: str) -> discord.Embed:
        raw = await self.fetch_remote(ctx, argument)
        return await super().convert(ctx, raw)


class PastebinListConverter(PastebinMixin, ListStringToEmbed):
    async def convert(self, ctx: commands.Context, argument: str) -> Dict[str, Any]:
        raw = await self.fetch_remote(ctx, argument)
        return await super().convert(ctx, raw)


async def read_attachment_text(ctx: commands.Context, suffixes: tuple[str, ...]) -> str:
    if not ctx.message.attachments:
        raise commands.BadArgument("Attach a file when using this command.")
    attachment = ctx.message.attachments[0]
    name = attachment.filename.lower()
    if not any(name.endswith(f".{suffix}") for suffix in suffixes):
        pretty = ", ".join(f".{s}" for s in suffixes)
        raise commands.BadArgument(f"Invalid file type. Use one of: {pretty}")
    try:
        return (await attachment.read()).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise commands.BadArgument("Failed to read the file as UTF-8.") from exc
