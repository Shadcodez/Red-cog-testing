import re
import time
from collections import OrderedDict
from urllib.parse import quote, quote_plus

import aiohttp
import discord
from discord.ui import Modal, TextInput, View, button, Select
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.chat_formatting import warning


class MusicLinker(commands.Cog):
    """Detects Spotify, YouTube (incl. Music), and Apple Music links.
    Replies with cross-platform search links + Brave lyrics search.

    Rich metadata via oEmbed/API fallback. Reaction mode uses 🎵 on original message.
    """

    SPOTIFY_GREEN = 0x1DB954
    YOUTUBE_RED = 0xFF0000
    APPLE_MUSIC_BLACK = 0x000000

    MAX_TRACKED_MESSAGES = 15   # last 15 messages keep reaction functional
    REACTION_TIMEOUT = 300.0    # 5 minutes

    SPOTIFY_RE = re.compile(
        r"https?://open\.spotify\.com/(?:intl-[a-z]{2}/)?track/([a-zA-Z0-9]{22})\S*"
    )

    YOUTUBE_RE = re.compile(
        r"https?://(?:(?:www\.)?youtube\.com/watch\?[^\s]*v=|youtu\.be/"
        r"|music\.youtube\.com/watch\?[^\s]*v=)([a-zA-Z0-9_-]{11})\S*"
    )

    APPLE_MUSIC_RE = re.compile(
        r"https?://music\.apple\.com/(?:[^/]+/)?(?:album|song)/[^/]+/(\d+)(?:\?i=\d+)?"
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
        self._message_links: OrderedDict = OrderedDict()  # message_id -> data

    async def cog_load(self):
        try:
            self.bot.add_view(self.SetupView(self))
        except Exception as e:
            print(f"Warning: Failed to register persistent SetupView: {e}")

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def cog_unload(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _get_spotify_token(self) -> str | None:
        client_id = await self.config.spotify_client_id()
        client_secret = await self.config.spotify_client_secret()
        if not client_id or not client_secret:
            return None

        now = time.time()
        if self._spotify_token and now < self._spotify_token_expires:
            return self._spotify_token

        url = "https://accounts.spotify.com/api/token"
        data = {"grant_type": "client_credentials"}
        auth = aiohttp.BasicAuth(client_id, client_secret)

        try:
            async with (await self._get_session()).post(url, data=data, auth=auth, timeout=10) as r:
                if r.status != 200:
                    return None
                js = await r.json()
                self._spotify_token = js.get("access_token")
                self._spotify_token_expires = now + js.get("expires_in", 3600) - 60
                return self._spotify_token
        except Exception:
            return None

    async def _fetch_spotify_track_api(self, track_id: str) -> dict | None:
        token = await self._get_spotify_token()
        if not token:
            return None

        url = f"https://api.spotify.com/v1/tracks/{track_id}"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            async with (await self._get_session()).get(url, headers=headers, timeout=8) as r:
                if r.status == 200:
                    return await r.json()
                if r.status == 401:
                    self._spotify_token = None
                return None
        except Exception:
            return None

    async def _fetch_spotify_oembed(self, track_id: str) -> dict | None:
        url = f"https://open.spotify.com/oembed?url=spotify:track:{track_id}"
        try:
            async with (await self._get_session()).get(url, timeout=6) as r:
                if r.status == 200:
                    return await r.json()
                return None
        except Exception:
            return None

    async def _fetch_youtube_oembed(self, video_id: str) -> dict | None:
        url = f"https://www.youtube.com/oembed?url=https://youtu.be/{video_id}&format=json"
        try:
            async with (await self._get_session()).get(url, timeout=6) as r:
                if r.status == 200:
                    data = await r.json()
                    if data.get("title"):
                        return data
        except Exception as e:
            print(f"YouTube oEmbed failed for {video_id}: {e}")
        return {
            "title": "YouTube Video",
            "author_name": "YouTube",
            "thumbnail_url": None
        }

    async def _fetch_apple_music_oembed(self, song_id: str) -> dict | None:
        url = f"https://music.apple.com/us/song/{song_id}"
        try:
            async with (await self._get_session()).get(
                "https://embed.music.apple.com/oembed",
                params={"url": url},
                timeout=6
            ) as r:
                if r.status == 200:
                    return await r.json()
                return None
        except Exception:
            return None

    async def _fetch_spotify_track(self, track_id: str) -> dict | None:
        data = await self._fetch_spotify_track_api(track_id)
        if data:
            images = data.get("album", {}).get("images", [])
            thumb = images[0]["url"] if images else None
            return {
                "title": data["name"],
                "artist": ", ".join(a["name"] for a in data["artists"]),
                "album": data["album"]["name"],
                "thumbnail": thumb,
            }

        oembed = await self._fetch_spotify_oembed(track_id)
        if oembed:
            return {"title": oembed.get("title", "Unknown Track"), "artist": "Unknown", "album": "Unknown", "thumbnail": oembed.get("thumbnail_url")}
        return None

    async def _fetch_apple_music_track(self, song_id: str) -> dict | None:
        oembed = await self._fetch_apple_music_oembed(song_id)
        if oembed:
            return {"title": oembed.get("title", "Apple Music Track"), "artist": "Unknown", "album": "Unknown", "thumbnail": oembed.get("thumbnail_url")}
        return None

    @staticmethod
    def _clean_yt_title(title: str) -> str:
        title = MusicLinker.YT_TITLE_NOISE.sub("", title)
        title = MusicLinker.YT_TITLE_KEYWORDS.sub("", title)
        title = re.sub(r" - YouTube$", "", title, flags=re.I)
        return title.strip() or "YouTube Video"

    @staticmethod
    def _parse_yt_artist_and_song(raw_title: str, channel_name: str) -> tuple[str, str]:
        match = MusicLinker.YT_ARTIST_TITLE_RE.match(raw_title)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        return channel_name.strip() or "", raw_title.strip()

    def _build_search_urls(self, artist: str = "", title: str = "") -> dict:
        query = " ".join([p for p in [artist, title] if p]).strip()
        q = quote(query or "song")
        return {
            "spotify": f"https://open.spotify.com/search/{q}",
            "youtube": f"https://www.youtube.com/results?search_query={q}",
            "tidal": f"https://listen.tidal.com/search?q={q}",
            "amazon": f"https://music.amazon.com/search/{q}",
            "apple_music": f"https://music.apple.com/us/search?term={q}",
            "lyrics": f"https://search.brave.com/search?q={quote(f'{artist} {title} lyrics'.strip())}",
        }

    def _build_spotify_embed(self, track_info: dict, show_thumb: bool) -> discord.Embed:
        e = discord.Embed(color=self.SPOTIFY_GREEN)
        e.title = track_info.get("title", "Spotify Track")
        e.description = f"**Artist:** {track_info.get('artist', '')}\n**Album:** {track_info.get('album', '')}"
        if show_thumb and (thumb := track_info.get("thumbnail")):
            e.set_thumbnail(url=thumb)
        return e

    def _build_youtube_embed(
        self, raw_title: str, author: str, thumbnail: str | None, show_thumb: bool
    ) -> discord.Embed:
        e = discord.Embed(color=self.YOUTUBE_RED)
        e.title = self._clean_yt_title(raw_title)
        e.description = f"**Channel:** {author}"
        if show_thumb and thumbnail:
            e.set_thumbnail(url=thumbnail)
        return e

    def _build_apple_music_embed(self, track_info: dict, show_thumb: bool) -> discord.Embed:
        e = discord.Embed(color=self.APPLE_MUSIC_BLACK)
        e.title = track_info.get("title", "Apple Music Track")
        if show_thumb and (thumb := track_info.get("thumbnail")):
            e.set_thumbnail(url=thumb)
        return e

    async def _build_embeds_for_links(
        self, spotify_ids: list[str], youtube_ids: list[str], apple_ids: list[str], show_thumb: bool, max_links: int
    ) -> list[discord.Embed]:
        embeds = []

        for sid in spotify_ids[:max_links]:
            info = await self._fetch_spotify_track(sid)
            if info:
                embeds.append(self._build_spotify_embed(info, show_thumb))

        remaining = max_links - len(embeds)
        for yid in youtube_ids[:remaining]:
            data = await self._fetch_youtube_oembed(yid)
            if data:
                embeds.append(
                    self._build_youtube_embed(
                        data.get("title", "YouTube Video"),
                        data.get("author_name", "YouTube"),
                        data.get("thumbnail_url"),
                        show_thumb,
                    )
                )

        remaining = max_links - len(embeds)
        for aid in apple_ids[:remaining]:
            info = await self._fetch_apple_music_track(aid)
            if info:
                embeds.append(self._build_apple_music_embed(info, show_thumb))

        return embeds

    def _extract_info(self, embeds: list[discord.Embed]) -> tuple[str, str]:
        artist = ""
        title = ""
        if embeds:
            first = embeds[0]
            title = first.title or ""
            if first.description:
                for line in first.description.split("\n"):
                    if "**Artist:**" in line:
                        artist = line.split("**Artist:**", 1)[1].strip()
                        break
                    if "**Channel:**" in line:
                        artist = line.split("**Channel:**", 1)[1].strip()
                        break
            if not artist and "YouTube" in first.title:
                artist, title_part = self._parse_yt_artist_and_song(first.title, "")
                title = self._clean_yt_title(title_part)
        return artist.strip(), title.strip()

    def _build_sources_embed(self, artist: str, title: str) -> discord.Embed:
        urls = self._build_search_urls(artist, title)
        embed = discord.Embed(
            title=title or "Song",
            description=f"by {artist}" if artist else "",
            color=discord.Color.blurple()
        )
        listen_value = "\n".join(f"[{k.replace('_', ' ').title()}]({v})" for k, v in urls.items() if k != "lyrics")
        if listen_value:
            embed.add_field(name="Listen on", value=listen_value, inline=False)
        embed.add_field(name="Lyrics", value=f"[Brave Search Lyrics]({urls['lyrics']})", inline=False)
        embed.set_footer(text="Click any link to open")
        return embed

    def _track_message(self, message_id: int, data: dict):
        self._message_links[message_id] = data
        if len(self._message_links) > self.MAX_TRACKED_MESSAGES:
            self._message_links.popitem(last=False)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or message.webhook_id:
            return

        guild_conf = self.config.guild(message.guild)
        if not await guild_conf.enabled():
            return

        channel_id = await guild_conf.channel_id()
        if channel_id != 0 and message.channel.id != channel_id:
            return

        spotify_ids = self.SPOTIFY_RE.findall(message.content)
        youtube_ids = self.YOUTUBE_RE.findall(message.content)
        apple_ids = self.APPLE_MUSIC_RE.findall(message.content)

        if not (spotify_ids or youtube_ids or apple_ids):
            return

        use_react = await guild_conf.use_reactions()
        show_thumb = await guild_conf.show_thumbnail()
        max_l = await guild_conf.max_links_per_message()

        embeds = []
        try:
            async with message.channel.typing():
                embeds = await self._build_embeds_for_links(spotify_ids, youtube_ids, apple_ids, show_thumb, max_l)
        except Exception as exc:
            print(f"Metadata fetch failed in {message.guild.name}/{message.channel.name}: {exc}")

        artist, title = self._extract_info(embeds)
        sources_embed = self._build_sources_embed(artist, title)

        if use_react:
            try:
                await message.add_reaction("🎵")
                self._track_message(message.id, {
                    "rich_embeds": embeds,
                    "sources_embed": sources_embed,
                    "author": message.author.id,
                    "expires": time.time() + self.REACTION_TIMEOUT,
                })
            except discord.HTTPException as e:
                print(f"Failed to add 🎵 reaction: {e}")
        else:
            # Auto-reply mode
            for e in embeds:
                try:
                    await message.reply(embed=e, mention_author=False)
                except discord.HTTPException:
                    pass
            try:
                await message.reply(embed=sources_embed, mention_author=False)
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return

        if str(payload.emoji) != "🎵":
            return

        data = self._message_links.get(payload.message_id)
        if not data:
            return

        if payload.user_id != data.get("author"):
            return

        if time.time() > data.get("expires", 0):
            self._message_links.pop(payload.message_id, None)
            return

        channel = self.bot.get_channel(payload.channel_id)
        if not channel:
            return

        try:
            msg = await channel.fetch_message(payload.message_id)
            await msg.remove_reaction("🎵", self.bot.user)

            # Send rich embeds if any
            for embed in data["rich_embeds"]:
                await channel.send(embed=embed)

            # Send sources embed
            await channel.send(embed=data["sources_embed"])
        except discord.HTTPException as e:
            print(f"Reaction response failed: {e}")
        finally:
            self._message_links.pop(payload.message_id, None)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        pass

    # ------------------------------------------------------------------------------
    # Setup wizard classes (add your working versions here if needed)
    # ------------------------------------------------------------------------------

    class SetupView(View):
        def __init__(self, cog):
            super().__init__(timeout=300)
            self.cog = cog

        @button(label="Start Setup", style=discord.ButtonStyle.green)
        async def start_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(
                "**MusicLinker Setup Wizard**\n\n"
                "This wizard will help you configure MusicLinker in a few steps.\n"
                "You can cancel at any time by ignoring the messages.\n\n"
                "Step 1: Choose where MusicLinker should listen for music links.\n"
                "Use the dropdown below.",
                ephemeral=True
            )
            view = self.cog.ChannelSelectView(self.cog, interaction.user, interaction.channel.id)
            await interaction.followup.send(
                "Where should MusicLinker work?",
                view=view,
                ephemeral=True
            )

    # ... (add ChannelSelectView, ResponseModeView, ToggleView as in your previous working version)

    @musiclinker.command(name="setup")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def ml_setup(self, ctx: commands.Context):
        embed = discord.Embed(
            title="MusicLinker Setup Wizard",
            description="Configure MusicLinker step by step.\nClick below to start.\n(Cancel by ignoring messages.)",
            color=discord.Color(0x1DB954)
        )
        view = self.SetupView(self)
        await ctx.send(embed=embed, view=view)
