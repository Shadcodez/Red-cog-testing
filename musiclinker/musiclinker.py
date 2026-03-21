import re
import time
from collections import OrderedDict
from urllib.parse import quote, quote_plus

import aiohttp
import discord
from discord.ui import Modal, TextInput, View, button, Select
from redbot.core import Config, commands
from redbot.core.bot import Red


class MusicLinker(commands.Cog):
    """Detects Spotify, YouTube (incl. Music), and Apple Music links.
    Replies with cross-platform search links + Brave lyrics search.

    Features:
    • [p]ml song <query> — manual song search
    • Configurable reaction timeout (default 600s)
    • Per-platform toggle for output links
    • Deezer, SoundCloud, Bandcamp included
    """

    SPOTIFY_GREEN = 0x1DB954
    YOUTUBE_RED = 0xFF0000
    APPLE_MUSIC_BLACK = 0x000000

    MAX_TRACKED_MESSAGES = 15

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

    # All toggleable platforms (lowercase keys)
    PLATFORMS = [
        "spotify", "youtube", "tidal", "amazon",
        "apple_music", "deezer", "soundcloud", "bandcamp"
    ]

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=620983015, force_registration=True)
        default_guild = {
            "enabled": False,
            "channel_id": 0,
            "show_thumbnail": True,
            "max_links_per_message": 3,
            "use_reactions": False,
            "reaction_timeout": 600,
            "platforms": {p: True for p in self.PLATFORMS},  # all enabled by default
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

    # ── Spotify / fetch methods unchanged ── (omitted for brevity)

    async def _get_spotify_token(self) -> str | None:
        # ... (unchanged)
        pass

    async def _fetch_spotify_track_api(self, track_id: str) -> dict | None:
        # ... (unchanged)
        pass

    async def _fetch_spotify_oembed(self, track_id: str) -> dict | None:
        # ... (unchanged)
        pass

    async def _fetch_youtube_oembed(self, video_id: str) -> dict | None:
        # ... (unchanged)
        pass

    async def _fetch_apple_music_oembed(self, song_id: str) -> dict | None:
        # ... (unchanged)
        pass

    async def _fetch_spotify_track(self, track_id: str) -> dict | None:
        # ... (unchanged)
        pass

    async def _fetch_apple_music_track(self, song_id: str) -> dict | None:
        # ... (unchanged)
        pass

    @staticmethod
    def _clean_yt_title(title: str) -> str:
        # ... (unchanged)
        pass

    @staticmethod
    def _parse_yt_artist_and_song(raw_title: str, channel_name: str) -> tuple[str, str]:
        # ... (unchanged)
        pass

    def _build_search_urls(self, artist: str = "", title: str = "") -> dict:
        query = " ".join([p for p in [artist, title] if p]).strip()
        q = quote(query or "song")
        return {
            "spotify": f"https://open.spotify.com/search/{q}",
            "youtube": f"https://www.youtube.com/results?search_query={q}",
            "tidal": f"https://listen.tidal.com/search?q={q}",
            "amazon": f"https://music.amazon.com/search/{q}",
            "apple_music": f"https://music.apple.com/us/search?term={q}",
            "deezer": f"https://www.deezer.com/search/{q}",
            "soundcloud": f"https://soundcloud.com/search/sounds?q={q}",
            "bandcamp": f"https://bandcamp.com/search?q={q}&item_type=t",
            "lyrics": f"https://search.brave.com/search?q={quote(f'{artist} {title} lyrics'.strip())}",
        }

    def _build_sources_embed(self, artist: str, title: str) -> discord.Embed:
        urls = self._build_search_urls(artist, title)
        embed = discord.Embed(
            title=title or "Song",
            description=f"by {artist}" if artist else "",
            color=discord.Color.blurple()
        )

        enabled_platforms = []
        guild_conf = self.config.guild_from_id(embed.guild_id) if hasattr(embed, "guild_id") else None
        if guild_conf:
            platforms = await guild_conf.platforms()
            enabled_platforms = [p for p in self.PLATFORMS if platforms.get(p, True)]

        listen_lines = []
        for p in enabled_platforms:
            if p in urls:
                nice_name = p.replace("_", " ").title()
                listen_lines.append(f"[{nice_name}]({urls[p]})")

        if listen_lines:
            embed.add_field(name="Listen on", value="\n".join(listen_lines), inline=False)

        embed.add_field(name="Lyrics", value=f"[Brave Search Lyrics]({urls['lyrics']})", inline=False)
        embed.set_footer(text="Click any link to open")
        return embed

    # ── Other embed builders unchanged ── (omitted for brevity)

    def _build_spotify_embed(self, track_info: dict, show_thumb: bool) -> discord.Embed:
        # ... (unchanged)
        pass

    def _build_youtube_embed(self, raw_title: str, author: str, thumbnail: str | None, show_thumb: bool) -> discord.Embed:
        # ... (unchanged)
        pass

    def _build_apple_music_embed(self, track_info: dict, show_thumb: bool) -> discord.Embed:
        # ... (unchanged)
        pass

    async def _build_embeds_for_links(self, spotify_ids, youtube_ids, apple_ids, show_thumb, max_links):
        # ... (unchanged)
        pass

    def _extract_info(self, embeds):
        # ... (unchanged)
        pass

    def _track_message(self, message_id: int, data: dict):
        # ... (unchanged)
        pass

    # ── Commands ────────────────────────────────────────────────────────────

    @commands.guild_only()
    @commands.group(name="musiclinker", aliases=["ml"], invoke_without_command=True)
    @commands.admin_or_permissions(manage_guild=True)
    async def musiclinker(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(self.musiclinker)

    @musiclinker.command(name="song", aliases=["search", "s"])
    async def ml_song(self, ctx: commands.Context, *, query: str):
        """Search any song and get instant cross-platform links + lyrics.
        Supports "Artist - Title" format."""
        query = query.strip()
        if not query:
            await ctx.send("Please provide a song name or query (e.g. `ml song Never Gonna Give You Up`).")
            return

        artist = ""
        title = query
        match = self.YT_ARTIST_TITLE_RE.match(query)
        if match:
            artist = match.group(1).strip()
            title = match.group(2).strip()

        sources_embed = self._build_sources_embed(artist, title)
        await ctx.send(embed=sources_embed)

    @musiclinker.command(name="platform")
    @commands.admin_or_permissions(manage_guild=True)
    async def ml_platform(self, ctx: commands.Context, platform: str.lower, state: str.lower = None):
        """Toggle individual platforms on/off in the Listen On embed.
        Example: [p]ml platform deezer off"""
        platform = platform.lower()
        if platform not in self.PLATFORMS:
            await ctx.send(f"Unknown platform. Available: {', '.join(self.PLATFORMS)}")
            return

        current = await self.config.guild(ctx.guild).platforms()
        if state is None:
            new_state = not current.get(platform, True)
        elif state in ("on", "enable", "true", "1", "yes"):
            new_state = True
        elif state in ("off", "disable", "false", "0", "no"):
            new_state = False
        else:
            await ctx.send("State must be `on`/`off` (or omitted to toggle).")
            return

        current[platform] = new_state
        await self.config.guild(ctx.guild).platforms.set(current)

        status = "enabled" if new_state else "disabled"
        await ctx.send(f"**{platform.title()}** is now **{status}** in search results.")

    @musiclinker.command(name="settings")
    @commands.admin_or_permissions(manage_guild=True)
    async def musiclinker_settings(self, ctx: commands.Context):
        guild_conf = self.config.guild(ctx.guild)
        enabled = await guild_conf.enabled()
        thumb = await guild_conf.show_thumbnail()
        limit = await guild_conf.max_links_per_message()
        channel_id = await guild_conf.channel_id()
        use_reactions = await guild_conf.use_reactions()
        react_timeout = await guild_conf.reaction_timeout()
        platforms = await guild_conf.platforms()

        has_api = bool(await self.config.spotify_client_id())

        if channel_id == 0:
            channel_display = "All Channels"
        else:
            channel = ctx.guild.get_channel(channel_id)
            channel_display = channel.mention if channel else f"Unknown ({channel_id})"

        embed = discord.Embed(title="MusicLinker Settings", color=discord.Color.blurple())
        embed.add_field(name="Enabled", value="✅ Yes" if enabled else "❌ No", inline=True)
        embed.add_field(name="Channel", value=channel_display, inline=True)
        embed.add_field(name="React Mode", value="✅ On" if use_reactions else "❌ Off", inline=True)
        embed.add_field(name="React Timeout", value=f"{react_timeout} seconds", inline=True)
        embed.add_field(name="Thumbnails", value="✅ Yes" if thumb else "❌ No", inline=True)
        embed.add_field(name="Max links / message", value=str(limit), inline=True)
        embed.add_field(name="Spotify API", value="✅ Configured" if has_api else "❌ Not set", inline=True)

        plat_status = "\n".join(
            f"• {p.replace('_', ' ').title()}: {'✅' if platforms.get(p, True) else '❌'}"
            for p in self.PLATFORMS
        )
        embed.add_field(name="Enabled Platforms", value=plat_status or "None", inline=False)

        await ctx.send(embed=embed)

    # Other commands (toggle, channel, react, thumbnail, maxlinks, spotifyapi, clearapi, config) remain unchanged

    @musiclinker.command(name="toggle")
    async def ml_toggle(self, ctx: commands.Context):
        # ... (unchanged)
        pass

    @musiclinker.command(name="channel")
    async def ml_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        # ... (unchanged)
        pass

    @musiclinker.command(name="react", aliases=["reactions"])
    async def ml_react(self, ctx: commands.Context):
        # ... (unchanged)
        pass

    @musiclinker.command(name="thumbnail", aliases=["thumb", "thumbs"])
    async def ml_thumbnail(self, ctx: commands.Context):
        # ... (unchanged)
        pass

    @musiclinker.command(name="maxlinks", aliases=["limit", "max"])
    async def ml_maxlinks(self, ctx: commands.Context, limit: int):
        # ... (unchanged)
        pass

    @commands.is_owner()
    @musiclinker.command(name="spotifyapi")
    async def ml_spotifyapi(self, ctx: commands.Context, client_id: str, client_secret: str):
        # ... (unchanged)
        pass

    @commands.is_owner()
    @musiclinker.command(name="clearapi")
    async def ml_clearapi(self, ctx: commands.Context):
        # ... (unchanged)
        pass

    @musiclinker.command(name="config")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def ml_config(self, ctx: commands.Context):
        embed = discord.Embed(
            title="MusicLinker Configuration Wizard",
            description="Configure MusicLinker step by step.\nClick below to start.\n(Cancel by ignoring messages.)",
            color=discord.Color(0x1DB954)
        )
        view = self.SetupView(self)
        await ctx.send(embed=embed, view=view)

    # ── Listener (on_message, on_raw_reaction_add/remove) unchanged ──

    # ── Setup Wizard ────────────────────────────────────────────────────────

    class SetupView(View):
        def __init__(self, cog):
            super().__init__(timeout=300)
            self.cog = cog

        @button(label="Start Config", style=discord.ButtonStyle.green)
        async def start_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(
                "**MusicLinker Configuration Wizard**\n\n"
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

    # ChannelSelectView, ResponseModeView unchanged...

    class ResponseModeView(View):
        # ... (unchanged, but calls _continue_to_timeout)
        async def _continue_to_timeout(self, interaction: discord.Interaction):
            view = self.cog.TimeoutView(self.cog, interaction.user)
            await interaction.followup.send(
                "**Next step: Reaction timeout (optional)**\n\n"
                "How long should users have to click the 🎵 reaction?\n\n"
                "Default is **600 seconds (10 minutes)**.\n"
                "You can change this later with `[p]ml timeout <seconds>`.\n\n"
                "Enter a number between 10 and 7200 seconds, or skip:",
                view=view,
                ephemeral=True
            )

    class TimeoutView(View):
        # ... (unchanged, now continues to platforms)

        async def _finish_setup(self, interaction: discord.Interaction):
            view = self.cog.PlatformsView(self.cog, interaction.user)
            await interaction.followup.send(
                "**Final step (optional): Select platforms to show**\n\n"
                "Choose which services to include in the 'Listen on' embed.\n"
                "You can change these later with `[p]ml platform <name> on/off`.\n\n"
                "Toggle any you want to disable:",
                view=view,
                ephemeral=True
            )

    class PlatformsView(View):
        def __init__(self, cog, user):
            super().__init__(timeout=600)
            self.cog = cog
            self.user = user
            self.selected = set()

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            return interaction.user == self.user

        @button(label="Finish Setup", style=discord.ButtonStyle.success)
        async def finish(self, interaction: discord.Interaction, button: discord.ui.Button):
            if self.selected:
                platforms = await self.cog.config.guild(interaction.guild).platforms()
                for p in self.selected:
                    platforms[p] = False
                await self.cog.config.guild(interaction.guild).platforms.set(platforms)

                disabled = ", ".join(self.selected).title().replace("_", " ")
                msg = f"Disabled: **{disabled}**"
            else:
                msg = "All platforms remain enabled."

            await interaction.response.edit_message(content=f"{msg}\n\nSetup complete! 🎉", view=None)
            await interaction.followup.send(
                "• Review settings: `[p]ml settings`\n"
                "• Toggle platforms: `[p]ml platform <name> on/off`\n"
                "• Re-run wizard: `[p]ml config`",
                ephemeral=True
            )

        # Simple toggle buttons for each platform (you can expand if needed)
        @button(label="Deezer", style=discord.ButtonStyle.secondary)
        async def toggle_deezer(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._toggle("deezer", interaction, button)

        @button(label="SoundCloud", style=discord.ButtonStyle.secondary)
        async def toggle_soundcloud(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._toggle("soundcloud", interaction, button)

        @button(label="Bandcamp", style=discord.ButtonStyle.secondary)
        async def toggle_bandcamp(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._toggle("bandcamp", interaction, button)

        async def _toggle(self, platform: str, interaction: discord.Interaction, button: discord.ui.Button):
            if platform in self.selected:
                self.selected.remove(platform)
                button.style = discord.ButtonStyle.secondary
                button.label = platform.title()
            else:
                self.selected.add(platform)
                button.style = discord.ButtonStyle.danger
                button.label = f"× {platform.title()}"
            await interaction.response.edit_message(view=self)

    # TimeoutModal unchanged...

# End of file
