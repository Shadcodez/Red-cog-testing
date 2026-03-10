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

    When Spotify API credentials are configured, retrieves full track
    metadata (artist, album, track name). Otherwise falls back to oEmbed.
    """

    SPOTIFY_GREEN = 0x1DB954
    YOUTUBE_RED = 0xFF0000

    MAX_TRACKED_MESSAGES = 500

    SPOTIFY_RE = re.compile(
        r"https?://open\.spotify\.com/(?:intl-[a-z]{2}/)?track/([a-zA-Z0-9]{22})\S*"
    )

    YOUTUBE_RE = re.compile(
        r"https://(?:(?:www\.)?youtube\.com/watch\?[^\s]*v=|youtu\.be/"
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

    # ────────────────────────────────────────────────────────────────────────
    #                   Spotify API Token & Track Fetching
    # ────────────────────────────────────────────────────────────────────────

    async def _get_spotify_token(self) -> str | None:
        client_id = await self.config.spotify_client_id()
        client_secret = await self.config.spotify_client_secret()
        if not client_id or not client_secret:
            return None

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
                    self._spotify_token_expires = time.time() + data.get("expires_in", 3600)
                    return self._spotify_token
        except Exception:
            pass
        return None

    async def _fetch_spotify_track_api(self, track_id: str) -> dict | None:
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
                    artists = ", ".join(a["name"] for a in data.get("artists", []))
                    album = data.get("album", {}).get("name", "")
                    track_name = data.get("name", "Unknown Track")
                    thumbnail = data.get("album", {}).get("images", [{}])[0].get("url")
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
        url = f"https://open.spotify.com/track/{track_id}"
        session = await self._get_session()
        try:
            async with session.get(
                f"https://open.spotify.com/oembed?url={url}",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
        except Exception:
            pass
        return None

    async def _fetch_spotify_track(self, track_id: str) -> dict | None:
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

    # (rest of your fetch / clean / parse / link builder methods remain unchanged)

    # ────────────────────────────────────────────────────────────────────────
    #                         Commands ─ Modern layout
    # ────────────────────────────────────────────────────────────────────────

    @commands.guild_only()
    @commands.group(name="musiclinker", aliases=["ml"], invoke_without_command=True)
    @commands.admin_or_permissions(manage_guild=True)
    async def musiclinker(self, ctx: commands.Context):
        """MusicLinker settings overview

        Use one of these to see settings:
        • ml
        • musiclinker
        • ml settings
        • musiclinker settings

        Then use subcommands like:
        • ml toggle
        • ml channel #music
        • ml react
        """
        if ctx.invoked_subcommand is None:
            await self._send_settings_embed(ctx)

    @musiclinker.command(name="settings", hidden=True)
    async def musiclinker_settings(self, ctx: commands.Context):
        """Alias for showing the settings overview"""
        await self._send_settings_embed(ctx)

    async def _send_settings_embed(self, ctx: commands.Context):
        guild_conf = self.config.guild(ctx.guild)
        enabled = await guild_conf.enabled()
        thumb = await guild_conf.show_thumbnail()
        limit = await guild_conf.max_links_per_message()
        channel_id = await guild_conf.channel_id()
        use_reactions = await guild_conf.use_reactions()
        has_api = bool(await self.config.spotify_client_id())

        channel_display = "All Channels" if channel_id == 0 else \
            (ctx.guild.get_channel(channel_id).mention if ctx.guild.get_channel(channel_id)
             else f"Unknown ({channel_id})")

        embed = discord.Embed(title="MusicLinker Settings", color=discord.Color.blurple())
        embed.add_field(name="Enabled",      value="✅ Yes" if enabled else "❌ No",       inline=True)
        embed.add_field(name="Channel",      value=channel_display,                        inline=True)
        embed.add_field(name="React Mode",   value="✅ On" if use_reactions else "❌ Off", inline=True)
        embed.add_field(name="Thumbnails",   value="✅ Yes" if thumb else "❌ No",         inline=True)
        embed.add_field(name="Max links/msg", value=str(limit),                            inline=True)
        embed.add_field(name="Spotify API",  value="✅ Set" if has_api else "❌ Not set",   inline=True)

        embed.set_footer(text="Use ml toggle / channel / react / thumbnail / maxlinks / …")
        await ctx.send(embed=embed)

    @musiclinker.command(name="toggle")
    async def ml_toggle(self, ctx: commands.Context):
        """Toggle MusicLinker on/off for this server"""
        current = await self.config.guild(ctx.guild).enabled()
        new = not current
        await self.config.guild(ctx.guild).enabled.set(new)
        await ctx.send(f"MusicLinker is now **{'enabled' if new else 'disabled'}**.")

    @musiclinker.command(name="channel")
    async def ml_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Set channel restriction (or all channels if omitted)"""
        if channel is None:
            await self.config.guild(ctx.guild).channel_id.set(0)
            await ctx.send("MusicLinker will now work in **all channels**.")
        else:
            await self.config.guild(ctx.guild).channel_id.set(channel.id)
            await ctx.send(f"MusicLinker restricted to {channel.mention} only.")

    @musiclinker.command(name="react")
    async def ml_react(self, ctx: commands.Context):
        """Toggle between reaction mode and auto-reply mode"""
        current = await self.config.guild(ctx.guild).use_reactions()
        new = not current
        await self.config.guild(ctx.guild).use_reactions.set(new)
        mode = "reaction" if new else "auto-reply"
        await ctx.send(f"Mode changed to **{mode}**.")

    @musiclinker.command(name="thumbnail", aliases=["thumb"])
    async def ml_thumbnail(self, ctx: commands.Context):
        """Toggle showing album/video thumbnails"""
        current = await self.config.guild(ctx.guild).show_thumbnail()
        new = not current
        await self.config.guild(ctx.guild).show_thumbnail.set(new)
        await ctx.send(f"Thumbnails are now **{'shown' if new else 'hidden'}**.")

    @musiclinker.command(name="maxlinks", aliases=["limit"])
    async def ml_maxlinks(self, ctx: commands.Context, limit: commands.Range[int, 1, 10]):
        """Set maximum number of embeds per responded message (1–10)"""
        await self.config.guild(ctx.guild).max_links_per_message.set(limit)
        await ctx.send(f"Max links per message set to **{limit}**.")

    @commands.is_owner()
    @musiclinker.command(name="spotifyapi")
    async def ml_spotifyapi(self, ctx: commands.Context, client_id: str, client_secret: str):
        """Set Spotify API credentials (owner only)"""
        await self.config.spotify_client_id.set(client_id)
        await self.config.spotify_client_secret.set(client_secret)
        self._spotify_token = None
        self._spotify_token_expires = 0.0

        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        if await self._get_spotify_token():
            await ctx.send("✅ Spotify API credentials saved and **verified**.")
        else:
            await ctx.send("⚠️ Credentials saved, but authentication **failed**.")

    @commands.is_owner()
    @musiclinker.command(name="clearapi")
    async def ml_clearapi(self, ctx: commands.Context):
        """Remove Spotify API credentials (owner only)"""
        await self.config.spotify_client_id.set("")
        await self.config.spotify_client_secret.set("")
        self._spotify_token = None
        self._spotify_token_expires = 0.0
        await ctx.send("🗑️ Spotify API credentials cleared.")

    # ────────────────────────────────────────────────────────────────────────
    #                         Listeners (unchanged)
    # ────────────────────────────────────────────────────────────────────────

    # ... your on_message, on_raw_reaction_add, on_raw_reaction_remove ...
    # remain exactly as they were in your original code

    # (If you want me to paste the full listeners too just say so)
