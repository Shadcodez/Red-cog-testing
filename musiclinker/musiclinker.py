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
    """

    SPOTIFY_GREEN = 0x1DB954
    YOUTUBE_RED = 0xFF0000

    MAX_TRACKED_MESSAGES = 500

    SPOTIFY_RE = re.compile(
        r"https?://open\.spotify\.com/(?:intl-[a-z]{2}/)?track/([a-zA-Z0-9]{22})\S*"
    )

    YOUTUBE_RE = re.compile(
        r"https?://(?:(?:www\.)?youtube\.com/watch\?[^\s]*v=|youtu\.be/"
        r"|music\.youtube\.com/watch\?[^\s]*v=)([a-zA-Z0-9_-]{11})\S*"
    )

    YT_TITLE_NOISE = re.compile(r"(?i)[\(\[\{].*?[\)\]\}]")
    YT_TITLE_KEYWORDS = re.compile(
        r"(?i)\b(?:official\s*(?:music\s*)?video|lyric\s*video|official\s*audio"
        r"|audio|visualizer|performance\s*video|clip\s*officiel|remaster(?:ed)?|"
        r"hd|hq|4k|mv)\b"
    )

    YT_ARTIST_TITLE_RE = re.compile(r"^(.+?)\s*[-–—]\s*(.+)$")

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=620983015, force_registration=True)
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
        self._message_links: OrderedDict = OrderedDict()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def cog_unload(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Spotify token & data fetching ───────────────────────────────────────
    # (unchanged methods – omitted for brevity)

    async def _get_spotify_token(self) -> str | None:
        # ... (same as original)
        pass

    async def _fetch_spotify_track_api(self, track_id: str) -> dict | None:
        # ... (same)
        pass

    async def _fetch_spotify_oembed(self, track_id: str) -> dict | None:
        # ... (same)
        pass

    async def _fetch_spotify_track(self, track_id: str) -> dict | None:
        # ... (same)
        pass

    async def _fetch_youtube_oembed(self, video_id: str) -> dict | None:
        # ... (same)
        pass

    @staticmethod
    def _clean_yt_title(title: str) -> str:
        # ... (same)
        pass

    @staticmethod
    def _parse_yt_artist_and_song(raw_title: str, channel_name: str) -> tuple[str, str]:
        # ... (same)
        pass

    # ── Search URL builders ─────────────────────────────────────────────────
    # (unchanged – omitted)

    # ── Embed builders ──────────────────────────────────────────────────────
    # (unchanged – omitted for brevity)

    def _build_spotify_embed(self, track_info: dict, show_thumb: bool) -> discord.Embed:
        # ... (same)
        pass

    def _build_youtube_embed(
        self, raw_title: str, author: str, thumbnail: str | None, show_thumb: bool
    ) -> discord.Embed:
        # ... (same)
        pass

    async def _build_embeds_for_links(
        self, spotify_ids: list[str], youtube_ids: list[str], show_thumb: bool, max_links: int
    ) -> list[discord.Embed]:
        # ... (same)
        pass

    def _track_message(self, message_id: int, data: dict):
        # ... (same)
        pass

    # ── New: Settings display ───────────────────────────────────────────────

    @commands.guild_only()
    @commands.group(
        name="musiclinker",
        aliases=["ml"],
        invoke_without_command=True,
        brief="MusicLinker settings & configuration",
    )
    @commands.admin_or_permissions(manage_guild=True)
    async def musiclinker(self, ctx: commands.Context):
        """
        MusicLinker main command.

        • Just typing `[p]ml` or `[p]musiclinker` shows this help message
        • Use `[p]ml settings` to view current server settings
        • Other subcommands: toggle, channel, react, thumbnail, maxlinks, ...
        """
        if ctx.invoked_subcommand is None:
            # Show native Red help for this cog/command group
            await ctx.send_help(self.musiclinker)

    @musiclinker.command(name="settings")
    @commands.admin_or_permissions(manage_guild=True)
    async def musiclinker_settings(self, ctx: commands.Context):
        """View current MusicLinker settings for this server."""
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
            channel_display = channel.mention if channel else f"Unknown ({channel_id})"

        embed = discord.Embed(
            title="MusicLinker Settings", color=discord.Color.blurple()
        )
        embed.add_field(name="Enabled", value="✅ Yes" if enabled else "❌ No", inline=True)
        embed.add_field(name="Channel", value=channel_display, inline=True)
        embed.add_field(
            name="React Mode", value="✅ On" if use_reactions else "❌ Off", inline=True
        )
        embed.add_field(name="Thumbnails", value="✅ Yes" if thumb else "❌ No", inline=True)
        embed.add_field(name="Max links / message", value=str(limit), inline=True)
        embed.add_field(
            name="Spotify API", value="✅ Configured" if has_api else "❌ Not set", inline=True
        )

        await ctx.send(embed=embed)

    # The rest of the subcommands remain unchanged
    # Just make sure they are properly attached under the group

    @musiclinker.command(name="toggle")
    async def ml_toggle(self, ctx: commands.Context):
        # ... (same as original)
        pass

    @musiclinker.command(name="channel")
    async def ml_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        # ... (same)
        pass

    @musiclinker.command(name="react")
    async def ml_react(self, ctx: commands.Context):
        # ... (same)
        pass

    @musiclinker.command(name="thumbnail", aliases=["thumb"])
    async def ml_thumbnail(self, ctx: commands.Context):
        # ... (same)
        pass

    @musiclinker.command(name="maxlinks", aliases=["limit"])
    async def ml_maxlinks(self, ctx: commands.Context, limit: int):
        # ... (same)
        pass

    @commands.is_owner()
    @musiclinker.command(name="spotifyapi")
    async def ml_spotifyapi(self, ctx: commands.Context, client_id: str, client_secret: str):
        # ... (same)
        pass

    @commands.is_owner()
    @musiclinker.command(name="clearapi")
    async def ml_clearapi(self, ctx: commands.Context):
        # ... (same)
        pass

    # ── Listeners (on_message, on_raw_reaction_add, on_raw_reaction_remove) ──
    # (unchanged – omitted for brevity)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ... (same as original)
        pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        # ... (same)
        pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        # ... (same)
        pass
