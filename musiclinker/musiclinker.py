import re
from urllib.parse import quote, quote_plus

import aiohttp
import discord
from redbot.core import Config, commands
from redbot.core.bot import Red


class MusicLinker(commands.Cog):
    """Detects Spotify and YouTube music links, then replies with a
    cross-platform search link and a Brave Search lyrics link."""

    SPOTIFY_GREEN = 0x1DB954
    YOUTUBE_RED = 0xFF0000

    # Matches Spotify track links (with optional /intl-xx/ prefix)
    SPOTIFY_RE = re.compile(
        r"https?://open\.spotify\.com/(?:intl-[a-z]{2}/)?track/([a-zA-Z0-9]{22})\S*"
    )

    # Matches youtube.com, youtu.be, and music.youtube.com watch links
    YOUTUBE_RE = re.compile(
        r"https?://(?:(?:www\.)?youtube\.com/watch\?[^\s]*v=|youtu\.be/"
        r"|music\.youtube\.com/watch\?[^\s]*v=)([a-zA-Z0-9_-]{11})\S*"
    )

    # Junk commonly found in YouTube titles that we want to strip for search
    YT_TITLE_NOISE = re.compile(
        r"(?i)[\(\[\{].*?[\)\]\}]"  # anything in brackets / parens
    )
    YT_TITLE_KEYWORDS = re.compile(
        r"(?i)\b(?:official\s*(?:music\s*)?video|lyric\s*video|official\s*audio"
        r"|audio|visualizer|performance\s*video|clip\s*officiel|remaster(?:ed)?|"
        r"hd|hq|4k|mv)\b"
    )

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=620983015, force_registration=True)
        default_guild = {
            "enabled": True,
            "show_thumbnail": True,
            "max_links_per_message": 3,
        }
        self.config.register_guild(**default_guild)
        self._session: aiohttp.ClientSession | None = None

    # -- Session management --------------------------------------------------

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def cog_unload(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # -- oEmbed helpers ------------------------------------------------------

    async def _fetch_spotify_oembed(self, track_id: str) -> dict | None:
        """Fetch metadata from Spotify's free oEmbed endpoint."""
        url = f"https://open.spotify.com/track/{track_id}"
        oembed = f"https://open.spotify.com/oembed?url={url}"
        session = await self._get_session()
        try:
            async with session.get(oembed, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
        except Exception:
            pass
        return None

    async def _fetch_youtube_oembed(self, video_id: str) -> dict | None:
        """Fetch metadata from YouTube's free oEmbed endpoint."""
        url = f"https://www.youtube.com/watch?v={video_id}"
        oembed = f"https://www.youtube.com/oembed?url={url}&format=json"
        session = await self._get_session()
        try:
            async with session.get(oembed, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
        except Exception:
            pass
        return None

    # -- Title cleaning ------------------------------------------------------

    @staticmethod
    def _clean_yt_title(title: str) -> str:
        """Strip noise from a YouTube video title to get a cleaner search query."""
        cleaned = MusicLinker.YT_TITLE_NOISE.sub("", title)
        cleaned = MusicLinker.YT_TITLE_KEYWORDS.sub("", cleaned)
        # Collapse separators left dangling at edges
        cleaned = re.sub(r"\s*[-–—|/\\]+\s*$", "", cleaned)
        cleaned = re.sub(r"^\s*[-–—|/\\]+\s*", "", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        return cleaned or title.strip()

    # -- Link builders -------------------------------------------------------

    @staticmethod
    def _yt_music_search(query: str) -> str:
        return f"https://music.youtube.com/search?q={quote_plus(query)}"

    @staticmethod
    def _yt_search(query: str) -> str:
        return f"https://www.youtube.com/results?search_query={quote_plus(query)}"

    @staticmethod
    def _spotify_search(query: str) -> str:
        return f"https://open.spotify.com/search/{quote(query)}"

    @staticmethod
    def _brave_lyrics(query: str) -> str:
        return f"https://search.brave.com/search?q={quote_plus(query + ' lyrics')}"

    # -- Embed builders ------------------------------------------------------

    def _build_spotify_embed(
        self, title: str, thumbnail: str | None, show_thumb: bool
    ) -> discord.Embed:
        yt_music = self._yt_music_search(title)
        yt_regular = self._yt_search(title)
        brave = self._brave_lyrics(title)

        embed = discord.Embed(title=f"🎵  {title}", color=self.SPOTIFY_GREEN)
        embed.add_field(
            name="🔴  YouTube",
            value=f"[YouTube Music]({yt_music})\n[YouTube]({yt_regular})",
            inline=True,
        )
        embed.add_field(
            name="📝  Lyrics",
            value=f"[Brave Search]({brave})",
            inline=True,
        )
        if show_thumb and thumbnail:
            embed.set_thumbnail(url=thumbnail)
        embed.set_footer(text="MusicLinker  •  Spotify ➜ YouTube")
        return embed

    def _build_youtube_embed(
        self,
        raw_title: str,
        author: str,
        thumbnail: str | None,
        show_thumb: bool,
    ) -> discord.Embed:
        clean = self._clean_yt_title(raw_title)
        spotify = self._spotify_search(clean)
        brave = self._brave_lyrics(clean)

        embed = discord.Embed(title=f"🎵  {raw_title}", color=self.YOUTUBE_RED)
        if author:
            embed.description = f"by **{author}**"
        embed.add_field(
            name="🟢  Spotify",
            value=f"[Search on Spotify]({spotify})",
            inline=True,
        )
        embed.add_field(
            name="📝  Lyrics",
            value=f"[Brave Search]({brave})",
            inline=True,
        )
        if show_thumb and thumbnail:
            embed.set_thumbnail(url=thumbnail)
        embed.set_footer(text="MusicLinker  •  YouTube ➜ Spotify")
        return embed

    # -- Settings commands ---------------------------------------------------

    @commands.guild_only()
    @commands.group(name="musiclinker", aliases=["ml"], invoke_without_command=True)
    @commands.admin_or_permissions(manage_guild=True)
    async def musiclinker(self, ctx: commands.Context):
        """View or configure MusicLinker settings."""
        guild_conf = self.config.guild(ctx.guild)
        enabled = await guild_conf.enabled()
        thumb = await guild_conf.show_thumbnail()
        limit = await guild_conf.max_links_per_message()

        embed = discord.Embed(title="MusicLinker Settings", color=discord.Color.blurple())
        embed.add_field(name="Enabled", value="✅ Yes" if enabled else "❌ No", inline=True)
        embed.add_field(name="Thumbnails", value="✅ Yes" if thumb else "❌ No", inline=True)
        embed.add_field(name="Max links / message", value=str(limit), inline=True)
        await ctx.send(embed=embed)

    @musiclinker.command(name="toggle")
    async def ml_toggle(self, ctx: commands.Context):
        """Toggle MusicLinker on or off."""
        current = await self.config.guild(ctx.guild).enabled()
        await self.config.guild(ctx.guild).enabled.set(not current)
        state = "enabled" if not current else "disabled"
        await ctx.send(f"MusicLinker is now **{state}**.")

    @musiclinker.command(name="thumbnail", aliases=["thumb"])
    async def ml_thumbnail(self, ctx: commands.Context):
        """Toggle album / video thumbnail display."""
        current = await self.config.guild(ctx.guild).show_thumbnail()
        await self.config.guild(ctx.guild).show_thumbnail.set(not current)
        state = "shown" if not current else "hidden"
        await ctx.send(f"Thumbnails will now be **{state}**.")

    @musiclinker.command(name="maxlinks", aliases=["limit"])
    async def ml_maxlinks(self, ctx: commands.Context, limit: int):
        """Set the maximum number of links the bot will respond to per message (1-10)."""
        limit = max(1, min(10, limit))
        await self.config.guild(ctx.guild).max_links_per_message.set(limit)
        await ctx.send(f"Max links per message set to **{limit}**.")

    # -- Listener ------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bots, DMs, and commands
        if message.author.bot or not message.guild:
            return

        enabled = await self.config.guild(message.guild).enabled()
        if not enabled:
            return

        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        content = message.content
        guild_conf = self.config.guild(message.guild)
        show_thumb = await guild_conf.show_thumbnail()
        max_links = await guild_conf.max_links_per_message()

        embeds: list[discord.Embed] = []

        # --- Spotify tracks ---
        for match in self.SPOTIFY_RE.finditer(content):
            if len(embeds) >= max_links:
                break
            track_id = match.group(1)
            data = await self._fetch_spotify_oembed(track_id)
            if data:
                title = data.get("title", "Unknown Track")
                thumb = data.get("thumbnail_url")
                embeds.append(self._build_spotify_embed(title, thumb, show_thumb))

        # --- YouTube videos ---
        for match in self.YOUTUBE_RE.finditer(content):
            if len(embeds) >= max_links:
                break
            video_id = match.group(1)
            data = await self._fetch_youtube_oembed(video_id)
            if data:
                raw_title = data.get("title", "Unknown")
                author = data.get("author_name", "")
                thumb = data.get("thumbnail_url")
                embeds.append(
                    self._build_youtube_embed(raw_title, author, thumb, show_thumb)
                )

        # Send all embeds in a single reply
        if embeds:
            try:
                await message.reply(embeds=embeds, mention_author=False)
            except discord.HTTPException:
                # Fall back to sending embeds one at a time if the batch is too large
                for embed in embeds:
                    try:
                        await message.channel.send(embed=embed)
                    except discord.HTTPException:
                        pass
