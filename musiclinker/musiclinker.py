import re
import time
from collections import OrderedDict
from urllib.parse import quote, quote_plus

import aiohttp
import discord
from redbot.core import Config, commands
from redbot.core.bot import Red


class MusicLinker(commands.Cog):
    """Detects Spotify and YouTube music links, then replies with
    cross-platform search links (YouTube, Spotify, Tidal, Amazon Music)
    and a Brave Search lyrics link.

    When Spotify API credentials are configured, the bot retrieves full
    track metadata (artist, album, track name) from the Spotify Web API.
    Without credentials it falls back to the free oEmbed endpoint, which
    only provides the track name.

    Features:
    - Disabled by default per server (must be enabled with toggle)
    - Channel-specific mode (restrict to one channel or all channels)
    - Auto-reply mode (sends embeds directly)
    - Reaction mode (adds 🎵 reaction; any user clicks to reveal embeds)
    - Cross-platform links: YouTube, YouTube Music, Spotify, Tidal, Amazon Music
    """

    SPOTIFY_GREEN = 0x1DB954
    YOUTUBE_RED = 0xFF0000

    # Maximum tracked messages for reaction mode (FIFO eviction)
    MAX_TRACKED_MESSAGES = 500

    # Matches Spotify track links (with optional /intl-xx/ prefix)
    SPOTIFY_RE = re.compile(
        r"https?://open\.spotify\.com/(?:intl-[a-z]{2}/)?track/([a-zA-Z0-9]{22})\S*"
    )

    # Matches youtube.com, youtu.be, and music.youtube.com watch links
    YOUTUBE_RE = re.compile(
        r"https?://(?:(?:www\.)?youtube\.com/watch\?[^\s]*v=|youtu\.be/"
        r"|music\.youtube\.com/watch\?[^\s]*v=)([a-zA-Z0-9_-]{11})\S*"
    )

    # Junk commonly found in YouTube titles that we want to strip
    YT_TITLE_NOISE = re.compile(r"(?i)[\(\[\{].*?[\)\]\}]")
    YT_TITLE_KEYWORDS = re.compile(
        r"(?i)\b(?:official\s*(?:music\s*)?video|lyric\s*video|official\s*audio"
        r"|audio|visualizer|performance\s*video|clip\s*officiel|remaster(?:ed)?|"
        r"hd|hq|4k|mv)\b"
    )

    # Many YouTube music titles follow "Artist - Song Name"
    YT_ARTIST_TITLE_RE = re.compile(r"^(.+?)\s*[-–—]\s*(.+)$")

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=620983015, force_registration=True
        )
        default_guild = {
            "enabled": False,
            "channel_id": 0,
            "show_thumbnail": True,
            "max_links_per_message": 3,
            "use_reactions": False,
        }
        default_global = {
            "spotify_client_id": "",
            "spotify_client_secret": "",
        }
        self.config.register_guild(**default_guild)
        self.config.register_global(**default_global)
        self._session: aiohttp.ClientSession | None = None
        self._spotify_token: str | None = None
        self._spotify_token_expires: float = 0.0
        # OrderedDict for reaction-mode message tracking with FIFO eviction
        self._message_links: OrderedDict = OrderedDict()

    # -- Session management --------------------------------------------------

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def cog_unload(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # -- Spotify API token management ----------------------------------------

    async def _get_spotify_token(self) -> str | None:
        """Obtain a Spotify access token via the client-credentials flow."""
        client_id = await self.config.spotify_client_id()
        client_secret = await self.config.spotify_client_secret()
        if not client_id or not client_secret:
            return None

        # Return the cached token if it is still valid (with a 60-second buffer)
        if self._spotify_token and time.time() < self._spotify_token_expires - 60:
            return self._spotify_token

        session = await self._get_session()
        try:
            async with session.post(
                "https://accounts.spotify.com/api/token",
                data={"grant_type": "client_credentials"},
                auth=aiohttp.BasicAuth(client_id, client_secret),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._spotify_token = data["access_token"]
                    self._spotify_token_expires = time.time() + data.get(
                        "expires_in", 3600
                    )
                    return self._spotify_token
        except Exception:
            pass
        return None

    # -- Spotify data fetchers -----------------------------------------------

    async def _fetch_spotify_track_api(self, track_id: str) -> dict | None:
        """Fetch full track metadata from the Spotify Web API."""
        token = await self._get_spotify_token()
        if not token:
            return None

        session = await self._get_session()
        try:
            async with session.get(
                f"https://api.spotify.com/v1/tracks/{track_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    artists = ", ".join(
                        a["name"] for a in data.get("artists", [])
                    )
                    album = data.get("album", {}).get("name", "")
                    track_name = data.get("name", "Unknown Track")
                    thumbnail = None
                    images = data.get("album", {}).get("images", [])
                    if images:
                        thumbnail = images[0].get("url")
                    return {
                        "track_name": track_name,
                        "artists": artists,
                        "album": album,
                        "thumbnail_url": thumbnail,
                        "source": "api",
                    }
        except Exception:
            pass
        return None

    async def _fetch_spotify_oembed(self, track_id: str) -> dict | None:
        """Fetch basic metadata from Spotify's free oEmbed endpoint."""
        url = f"https://open.spotify.com/track/{track_id}"
        oembed = f"https://open.spotify.com/oembed?url={url}"
        session = await self._get_session()
        try:
            async with session.get(
                oembed, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
        except Exception:
            pass
        return None

    async def _fetch_spotify_track(self, track_id: str) -> dict | None:
        """Get Spotify track info.  Tries the Web API first, then oEmbed."""
        info = await self._fetch_spotify_track_api(track_id)
        if info:
            return info

        oembed = await self._fetch_spotify_oembed(track_id)
        if oembed:
            return {
                "track_name": oembed.get("title", "Unknown Track"),
                "artists": "",
                "album": "",
                "thumbnail_url": oembed.get("thumbnail_url"),
                "source": "oembed",
            }
        return None

    # -- YouTube data fetcher ------------------------------------------------

    async def _fetch_youtube_oembed(self, video_id: str) -> dict | None:
        """Fetch metadata from YouTube's free oEmbed endpoint."""
        url = f"https://www.youtube.com/watch?v={video_id}"
        oembed = f"https://www.youtube.com/oembed?url={url}&format=json"
        session = await self._get_session()
        try:
            async with session.get(
                oembed, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
        except Exception:
            pass
        return None

    # -- Title cleaning / parsing --------------------------------------------

    @staticmethod
    def _clean_yt_title(title: str) -> str:
        """Strip noise like (Official Video) from a YouTube title."""
        cleaned = MusicLinker.YT_TITLE_NOISE.sub("", title)
        cleaned = MusicLinker.YT_TITLE_KEYWORDS.sub("", cleaned)
        cleaned = re.sub(r"\s*[-–—|/\\]+\s*$", "", cleaned)
        cleaned = re.sub(r"^\s*[-–—|/\\]+\s*", "", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        return cleaned or title.strip()

    @staticmethod
    def _parse_yt_artist_and_song(
        raw_title: str, channel_name: str
    ) -> tuple[str, str]:
        """Extract (artist, song) from a YouTube title.

        Many music videos use the pattern ``Artist - Song Name``.  When that
        pattern is detected we use it directly.  Otherwise we fall back to
        the channel name as the artist and the cleaned title as the song.
        """
        cleaned = MusicLinker._clean_yt_title(raw_title)

        match = MusicLinker.YT_ARTIST_TITLE_RE.match(cleaned)
        if match:
            artist = match.group(1).strip()
            song = match.group(2).strip()
            song = MusicLinker.YT_TITLE_NOISE.sub("", song)
            song = MusicLinker.YT_TITLE_KEYWORDS.sub("", song)
            song = re.sub(r"\s{2,}", " ", song).strip()
            if artist and song:
                return artist, song

        return channel_name.strip(), cleaned

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
    def _tidal_search(query: str) -> str:
        return f"https://tidal.com/search?q={quote_plus(query)}"

    @staticmethod
    def _amazon_music_search(query: str) -> str:
        return f"https://music.amazon.com/search/{quote(query, safe='')}"

    @staticmethod
    def _brave_lyrics(query: str) -> str:
        return f"https://search.brave.com/search?q={quote_plus(query + ' lyrics')}"

    # -- Embed builders ------------------------------------------------------

    def _build_spotify_embed(
        self, track_info: dict, show_thumb: bool
    ) -> discord.Embed:
        """Build the reply embed for a detected Spotify link."""
        track_name = track_info["track_name"]
        artists = track_info["artists"]
        album = track_info["album"]
        thumbnail = track_info["thumbnail_url"]

        # Display title: "Artist(s) — Track" or just "Track"
        if artists:
            display_title = f"{artists} — {track_name}"
        else:
            display_title = track_name

        # Search queries include artist + song (+ album for YouTube to narrow results)
        search_parts = [p for p in (artists, track_name) if p]
        search_query = " ".join(search_parts)

        yt_query = " ".join([p for p in (artists, track_name, album) if p])
        platform_query = search_query
        lyrics_query = search_query

        yt_music = self._yt_music_search(yt_query)
        yt_regular = self._yt_search(yt_query)
        tidal = self._tidal_search(platform_query)
        amazon = self._amazon_music_search(platform_query)
        brave = self._brave_lyrics(lyrics_query)

        embed = discord.Embed(
            title=f"🎵  {display_title}", color=self.SPOTIFY_GREEN
        )
        if album:
            embed.description = f"💿 *{album}*"

        embed.add_field(
            name="🔴  YouTube",
            value=f"[YouTube Music]({yt_music})\n[YouTube]({yt_regular})",
            inline=True,
        )
        embed.add_field(
            name="🔗  More Platforms",
            value=f"[Tidal]({tidal})\n[Amazon Music]({amazon})",
            inline=True,
        )
        embed.add_field(
            name="📝  Lyrics",
            value=f"[Brave Search]({brave})",
            inline=True,
        )

        if show_thumb and thumbnail:
            embed.set_thumbnail(url=thumbnail)

        if track_info["source"] == "oembed":
            embed.set_footer(
                text="MusicLinker  •  Spotify ➜ YouTube / Tidal / Amazon  •  "
                "Tip: set Spotify API credentials for artist & album info"
            )
        else:
            embed.set_footer(
                text="MusicLinker  •  Spotify ➜ YouTube / Tidal / Amazon"
            )
        return embed

    def _build_youtube_embed(
        self,
        raw_title: str,
        author: str,
        thumbnail: str | None,
        show_thumb: bool,
    ) -> discord.Embed:
        """Build the reply embed for a detected YouTube link."""
        artist, song = self._parse_yt_artist_and_song(raw_title, author)

        platform_query = f"{artist} {song}" if artist else song
        spotify = self._spotify_search(platform_query)
        tidal = self._tidal_search(platform_query)
        amazon = self._amazon_music_search(platform_query)
        lyrics_query = f"{artist} {song}" if artist else song
        brave = self._brave_lyrics(lyrics_query)

        embed = discord.Embed(
            title=f"🎵  {raw_title}", color=self.YOUTUBE_RED
        )
        if artist:
            embed.description = f"by **{artist}**"

        embed.add_field(
            name="🟢  Spotify",
            value=f"[Search on Spotify]({spotify})",
            inline=True,
        )
        embed.add_field(
            name="🔗  More Platforms",
            value=f"[Tidal]({tidal})\n[Amazon Music]({amazon})",
            inline=True,
        )
        embed.add_field(
            name="📝  Lyrics",
            value=f"[Brave Search]({brave})",
            inline=True,
        )

        if show_thumb and thumbnail:
            embed.set_thumbnail(url=thumbnail)
        embed.set_footer(
            text="MusicLinker  •  YouTube ➜ Spotify / Tidal / Amazon"
        )
        return embed

    # -- Reaction mode helpers -----------------------------------------------

    def _track_message(self, message_id: int, data: dict):
        """Store message data for reaction mode with FIFO eviction."""
        while len(self._message_links) >= self.MAX_TRACKED_MESSAGES:
            self._message_links.popitem(last=False)
        self._message_links[message_id] = data

    # -- Shared embed building -----------------------------------------------

    async def _build_embeds_for_links(
        self,
        spotify_ids: list[str],
        youtube_ids: list[str],
        show_thumb: bool,
        max_links: int,
    ) -> list[discord.Embed]:
        """Build embed list for the given track/video IDs."""
        embeds: list[discord.Embed] = []

        for track_id in spotify_ids:
            if len(embeds) >= max_links:
                break
            track_info = await self._fetch_spotify_track(track_id)
            if track_info:
                embeds.append(
                    self._build_spotify_embed(track_info, show_thumb)
                )

        for video_id in youtube_ids:
            if len(embeds) >= max_links:
                break
            data = await self._fetch_youtube_oembed(video_id)
            if data:
                raw_title = data.get("title", "Unknown")
                author = data.get("author_name", "")
                thumb = data.get("thumbnail_url")
                embeds.append(
                    self._build_youtube_embed(
                        raw_title, author, thumb, show_thumb
                    )
                )

        return embeds

    # -- Settings commands ---------------------------------------------------

    @commands.guild_only()
    @commands.group(
        name="musiclinker", aliases=["ml"], invoke_without_command=True
    )
    @commands.admin_or_permissions(manage_guild=True)
    async def musiclinker(self, ctx: commands.Context):
        """View or configure MusicLinker settings.

        Subcommands:
        - toggle: Enable/disable MusicLinker for the server
        - channel: Set a specific channel or all channels
        - react: Toggle reaction mode vs auto-reply
        - thumbnail: Toggle thumbnail display
        - maxlinks: Set max links per message
        - spotifyapi: Configure Spotify API credentials (owner only)
        - clearapi: Remove Spotify API credentials (owner only)
        """
        guild_conf = self.config.guild(ctx.guild)
        enabled = await guild_conf.enabled()
        thumb = await guild_conf.show_thumbnail()
        limit = await guild_conf.max_links_per_message()
        channel_id = await guild_conf.channel_id()
        use_reactions = await guild_conf.use_reactions()

        has_api = bool(await self.config.spotify_client_id())

        if channel_id == 0:
            channel_display = "All Channels"
        else:
            channel = ctx.guild.get_channel(channel_id)
            channel_display = (
                channel.mention if channel else f"Unknown ({channel_id})"
            )

        embed = discord.Embed(
            title="MusicLinker Settings", color=discord.Color.blurple()
        )
        embed.add_field(
            name="Enabled",
            value="✅ Yes" if enabled else "❌ No",
            inline=True,
        )
        embed.add_field(
            name="Channel",
            value=channel_display,
            inline=True,
        )
        embed.add_field(
            name="React Mode",
            value="✅ On" if use_reactions else "❌ Off",
            inline=True,
        )
        embed.add_field(
            name="Thumbnails",
            value="✅ Yes" if thumb else "❌ No",
            inline=True,
        )
        embed.add_field(
            name="Max links / message", value=str(limit), inline=True
        )
        embed.add_field(
            name="Spotify API",
            value="✅ Configured" if has_api else "❌ Not set",
            inline=True,
        )
        await ctx.send(embed=embed)

    @musiclinker.command(name="toggle")
    async def ml_toggle(self, ctx: commands.Context):
        """Toggle MusicLinker on or off for this server."""
        current = await self.config.guild(ctx.guild).enabled()
        await self.config.guild(ctx.guild).enabled.set(not current)
        state = "enabled" if not current else "disabled"
        await ctx.send(f"MusicLinker is now **{state}**.")

    @musiclinker.command(name="channel")
    async def ml_channel(
        self, ctx: commands.Context, channel: discord.TextChannel = None
    ):
        """Set the channel where MusicLinker operates (or all channels).

        Usage:
            [p]musiclinker channel #general  - Enable in #general only
            [p]musiclinker channel           - Enable in all channels
        """
        if channel is None:
            await self.config.guild(ctx.guild).channel_id.set(0)
            await ctx.send(
                "MusicLinker will now operate in **all channels**."
            )
        else:
            await self.config.guild(ctx.guild).channel_id.set(channel.id)
            await ctx.send(
                f"MusicLinker will now operate in {channel.mention} only."
            )

    @musiclinker.command(name="react")
    async def ml_react(self, ctx: commands.Context):
        """Toggle reaction mode on or off.

        When reaction mode is ON:
            - Bot adds 🎵 reaction to messages with music links
            - Any user clicks the reaction to reveal cross-platform embeds

        When reaction mode is OFF:
            - Bot sends embeds directly (auto-reply mode)
        """
        current = await self.config.guild(ctx.guild).use_reactions()
        await self.config.guild(ctx.guild).use_reactions.set(not current)
        mode = "reaction" if not current else "auto-reply"
        await ctx.send(f"MusicLinker is now in **{mode}** mode.")

    @musiclinker.command(name="thumbnail", aliases=["thumb"])
    async def ml_thumbnail(self, ctx: commands.Context):
        """Toggle album / video thumbnail display."""
        current = await self.config.guild(ctx.guild).show_thumbnail()
        await self.config.guild(ctx.guild).show_thumbnail.set(not current)
        state = "shown" if not current else "hidden"
        await ctx.send(f"Thumbnails will now be **{state}**.")

    @musiclinker.command(name="maxlinks", aliases=["limit"])
    async def ml_maxlinks(self, ctx: commands.Context, limit: int):
        """Set the max number of links the bot responds to per message (1-10)."""
        limit = max(1, min(10, limit))
        await self.config.guild(ctx.guild).max_links_per_message.set(limit)
        await ctx.send(f"Max links per message set to **{limit}**.")

    @commands.is_owner()
    @musiclinker.command(name="spotifyapi")
    async def ml_spotifyapi(
        self, ctx: commands.Context, client_id: str, client_secret: str
    ):
        """Set Spotify API credentials (bot owner only).

        1. Go to https://developer.spotify.com/dashboard
        2. Create an app and copy the **Client ID** and **Client Secret**.
        3. Run this command (**preferably in DMs** to keep credentials private).

        **Usage:** `[p]musiclinker spotifyapi <client_id> <client_secret>`
        """
        await self.config.spotify_client_id.set(client_id)
        await self.config.spotify_client_secret.set(client_secret)

        self._spotify_token = None
        self._spotify_token_expires = 0.0

        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

        token = await self._get_spotify_token()
        if token:
            await ctx.send(
                "✅ Spotify API credentials saved and verified!\n"
                "Full track metadata (artist, album) is now available."
            )
        else:
            await ctx.send(
                "⚠️ Credentials saved but authentication failed. "
                "Double-check your Client ID and Client Secret."
            )

    @commands.is_owner()
    @musiclinker.command(name="clearapi")
    async def ml_clearapi(self, ctx: commands.Context):
        """Remove stored Spotify API credentials (bot owner only)."""
        await self.config.spotify_client_id.set("")
        await self.config.spotify_client_secret.set("")
        self._spotify_token = None
        self._spotify_token_expires = 0.0
        await ctx.send("🗑️ Spotify API credentials have been cleared.")

    # -- Listener: on_message ------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        enabled = await self.config.guild(message.guild).enabled()
        if not enabled:
            return

        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        guild_conf = self.config.guild(message.guild)
        channel_id = await guild_conf.channel_id()
        if channel_id != 0 and message.channel.id != channel_id:
            return

        content = message.content
        show_thumb = await guild_conf.show_thumbnail()
        max_links = await guild_conf.max_links_per_message()
        use_reactions = await guild_conf.use_reactions()

        spotify_matches = list(self.SPOTIFY_RE.finditer(content))
        youtube_matches = list(self.YOUTUBE_RE.finditer(content))

        if not spotify_matches and not youtube_matches:
            return

        # Extract IDs as plain strings (safe for later use)
        spotify_ids = [m.group(1) for m in spotify_matches]
        youtube_ids = [m.group(1) for m in youtube_matches]

        # -- Reaction mode: tag the message and store IDs --
        if use_reactions:
            try:
                await message.add_reaction("🎵")
                self._track_message(
                    message.id,
                    {
                        "spotify_ids": spotify_ids,
                        "youtube_ids": youtube_ids,
                        "channel_id": message.channel.id,
                        "guild_id": message.guild.id,
                        "sent": False,
                    },
                )
            except discord.Forbidden:
                pass
            return

        # -- Auto-reply mode: send embeds immediately --
        embeds = await self._build_embeds_for_links(
            spotify_ids, youtube_ids, show_thumb, max_links
        )

        if embeds:
            try:
                await message.reply(embeds=embeds, mention_author=False)
            except discord.HTTPException:
                for embed in embeds:
                    try:
                        await message.channel.send(embed=embed)
                    except discord.HTTPException:
                        pass

    # -- Listener: reaction add (reaction mode) ------------------------------

    @commands.Cog.listener()
    async def on_raw_reaction_add(
        self, payload: discord.RawReactionActionEvent
    ):
        """When any non-bot user clicks the 🎵 reaction, send the embeds."""
        if payload.emoji.name != "🎵":
            return

        if payload.message_id not in self._message_links:
            return

        # Ignore the bot's own reaction
        if self.bot.user and payload.user_id == self.bot.user.id:
            return

        # Ignore other bots (member may be None for uncached members)
        if payload.member and payload.member.bot:
            return

        msg_data = self._message_links[payload.message_id]

        # Prevent duplicate sends
        if msg_data["sent"]:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        # Re-validate that the cog is still enabled and in reaction mode
        guild_conf = self.config.guild(guild)
        enabled = await guild_conf.enabled()
        if not enabled:
            return
        use_reactions = await guild_conf.use_reactions()
        if not use_reactions:
            return

        channel = guild.get_channel(payload.channel_id)
        if not channel:
            return

        # Mark as sent immediately to prevent race conditions
        msg_data["sent"] = True

        show_thumb = await guild_conf.show_thumbnail()
        max_links = await guild_conf.max_links_per_message()

        embeds = await self._build_embeds_for_links(
            msg_data["spotify_ids"],
            msg_data["youtube_ids"],
            show_thumb,
            max_links,
        )

        if embeds:
            try:
                message = await channel.fetch_message(payload.message_id)
                await message.reply(embeds=embeds, mention_author=False)
            except discord.NotFound:
                # Message was deleted; clean up
                self._message_links.pop(payload.message_id, None)
                return
            except discord.Forbidden:
                # No permission to fetch or reply; try a plain send
                for embed in embeds:
                    try:
                        await channel.send(embed=embed)
                    except discord.HTTPException:
                        pass
            except discord.HTTPException:
                for embed in embeds:
                    try:
                        await channel.send(embed=embed)
                    except discord.HTTPException:
                        pass

    # -- Listener: reaction remove (cleanup) ---------------------------------

    @commands.Cog.listener()
    async def on_raw_reaction_remove(
        self, payload: discord.RawReactionActionEvent
    ):
        """If the bot's 🎵 reaction is removed, stop tracking the message."""
        if payload.emoji.name != "🎵":
            return
        if payload.message_id not in self._message_links:
            return
        # Clean up if the bot's own reaction was removed (e.g. by a moderator)
        if self.bot.user and payload.user_id == self.bot.user.id:
            self._message_links.pop(payload.message_id, None)
