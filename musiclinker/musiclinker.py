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
    """Detects Spotify and YouTube music links, then replies with
    cross-platform search links (YouTube, Spotify, Tidal, Amazon Music)
    and a Brave Search lyrics link.

    When Spotify API credentials are configured, retrieves full track metadata.
    Falls back to oEmbed when API is unavailable or credentials missing.
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
            return {"title": oembed.get("title", "Unknown Track"), "thumbnail": oembed.get("thumbnail_url")}
        return None

    @staticmethod
    def _clean_yt_title(title: str) -> str:
        title = MusicLinker.YT_TITLE_NOISE.sub("", title)
        title = MusicLinker.YT_TITLE_KEYWORDS.sub("", title)
        return title.strip() or "YouTube Video"

    @staticmethod
    def _parse_yt_artist_and_song(raw_title: str, channel_name: str) -> tuple[str, str]:
        match = MusicLinker.YT_ARTIST_TITLE_RE.match(raw_title)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        return channel_name.strip() or "Unknown", raw_title.strip()

    def _build_search_urls(self, artist: str, title: str) -> dict:
        q = quote(f"{artist} {title}".strip())
        return {
            "spotify": f"https://open.spotify.com/search/{q}",
            "youtube": f"https://www.youtube.com/results?search_query={q}",
            "tidal": f"https://listen.tidal.com/search?q={q}",
            "amazon": f"https://music.amazon.com/search/{q}",
            "lyrics": f"https://search.brave.com/search?q={quote(f'{artist} {title} lyrics')}",
        }

    def _build_spotify_embed(self, track_info: dict, show_thumb: bool) -> discord.Embed:
        e = discord.Embed(color=self.SPOTIFY_GREEN)
        e.title = track_info.get("title", "Spotify Track")
        e.description = f"**Artist:** {track_info.get('artist', 'Unknown')}\n**Album:** {track_info.get('album', 'Unknown')}"
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

    async def _build_embeds_for_links(
        self, spotify_ids: list[str], youtube_ids: list[str], show_thumb: bool, max_links: int
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
                        data.get("author_name", "Unknown Channel"),
                        data.get("thumbnail_url"),
                        show_thumb,
                    )
                )

        return embeds

    def _track_message(self, message_id: int, data: dict):
        self._message_links[message_id] = data
        if len(self._message_links) > self.MAX_TRACKED_MESSAGES:
            self._message_links.popitem(last=False)

    @commands.guild_only()
    @commands.group(
        name="musiclinker",
        aliases=["ml"],
        invoke_without_command=True,
    )
    @commands.admin_or_permissions(manage_guild=True)
    async def musiclinker(self, ctx: commands.Context):
        """
        MusicLinker settings & configuration.

        Subcommands:
          channel     Set channel restriction (or all channels if omitted)
          clearapi    Remove Spotify API credentials (owner only)
          maxlinks    Set maximum number of embeds per responded message (1–10)
          react       Toggle between reaction mode and auto-reply mode
          search      Search for a song and get cross-platform links
          setup       Quick setup guide with interactive buttons
          spotifyapi  Set Spotify API credentials (owner only)
          thumbnail   Toggle showing album/video thumbnails
          toggle      Toggle MusicLinker on/off for this server
        """
        if ctx.invoked_subcommand is None:
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

        embed = discord.Embed(title="MusicLinker Settings", color=discord.Color.blurple())
        embed.add_field(name="Enabled", value="✅ Yes" if enabled else "❌ No", inline=True)
        embed.add_field(name="Channel", value=channel_display, inline=True)
        embed.add_field(name="React Mode", value="✅ On" if use_reactions else "❌ Off", inline=True)
        embed.add_field(name="Thumbnails", value="✅ Yes" if thumb else "❌ No", inline=True)
        embed.add_field(name="Max links / message", value=str(limit), inline=True)
        embed.add_field(name="Spotify API", value="✅ Configured" if has_api else "❌ Not set", inline=True)

        await ctx.send(embed=embed)

    @musiclinker.command(name="toggle")
    async def ml_toggle(self, ctx: commands.Context):
        """Toggle MusicLinker on/off for this server."""
        enabled = await self.config.guild(ctx.guild).enabled()
        new = not enabled
        await self.config.guild(ctx.guild).enabled.set(new)
        status = "enabled" if new else "disabled"
        await ctx.send(f"MusicLinker is now **{status}** in this server.")

    @musiclinker.command(name="channel")
    async def ml_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Set channel restriction (or all channels if omitted)."""
        if channel is None:
            await self.config.guild(ctx.guild).channel_id.set(0)
            await ctx.send("MusicLinker will now work in **all channels**.")
        else:
            await self.config.guild(ctx.guild).channel_id.set(channel.id)
            await ctx.send(f"MusicLinker is now restricted to {channel.mention}.")

    @musiclinker.command(name="react", aliases=["reactions"])
    async def ml_react(self, ctx: commands.Context):
        """Toggle between reaction mode and auto-reply mode."""
        current = await self.config.guild(ctx.guild).use_reactions()
        new = not current
        await self.config.guild(ctx.guild).use_reactions.set(new)
        mode = "reaction buttons" if new else "auto-embed replies"
        await ctx.send(f"MusicLinker will now use **{mode}**.")

    @musiclinker.command(name="thumbnail", aliases=["thumb", "thumbs"])
    async def ml_thumbnail(self, ctx: commands.Context):
        """Toggle showing album/video thumbnails."""
        current = await self.config.guild(ctx.guild).show_thumbnail()
        new = not current
        await self.config.guild(ctx.guild).show_thumbnail.set(new)
        status = "shown" if new else "hidden"
        await ctx.send(f"Thumbnails will now be **{status}** in embeds.")

    @musiclinker.command(name="maxlinks", aliases=["limit", "max"])
    async def ml_maxlinks(self, ctx: commands.Context, limit: int):
        """Set maximum number of embeds per responded message (1–10)."""
        limit = max(1, min(10, limit))
        await self.config.guild(ctx.guild).max_links_per_message.set(limit)
        await ctx.send(f"Maximum links per message set to **{limit}**.")

    @commands.is_owner()
    @musiclinker.command(name="spotifyapi")
    async def ml_spotifyapi(self, ctx: commands.Context, client_id: str, client_secret: str):
        """Set Spotify API credentials (owner only)."""
        await self.config.spotify_client_id.set(client_id.strip())
        await self.config.spotify_client_secret.set(client_secret.strip())
        await ctx.send("Spotify API credentials have been **updated**.")

    @commands.is_owner()
    @musiclinker.command(name="clearapi")
    async def ml_clearapi(self, ctx: commands.Context):
        """Remove Spotify API credentials (owner only)."""
        await self.config.spotify_client_id.set("")
        await self.config.spotify_client_secret.set("")
        await ctx.send("Spotify API credentials have been **cleared**.")

    # ── Setup & Search ──────────────────────────────────────────────────────

    class SpotifyApiModal(Modal, title="Set Spotify API Credentials"):
        client_id = TextInput(
            label="Spotify Client ID",
            placeholder="Paste your Client ID here...",
            style=discord.TextStyle.short,
            required=True,
            max_length=255,
        )
        client_secret = TextInput(
            label="Spotify Client Secret",
            placeholder="Paste your Client Secret here...",
            style=discord.TextStyle.short,
            required=True,
            max_length=255,
        )

        def __init__(self, cog):
            super().__init__()
            self.cog = cog

        async def on_submit(self, interaction: discord.Interaction):
            if not await self.cog.bot.is_owner(interaction.user):
                await interaction.response.send_message("Only the bot owner can set API keys.", ephemeral=True)
                return

            cid = self.client_id.value.strip()
            secret = self.client_secret.value.strip()

            if not cid or not secret:
                await interaction.response.send_message("Both fields are required.", ephemeral=True)
                return

            await self.cog.config.spotify_client_id.set(cid)
            await self.cog.config.spotify_client_secret.set(secret)

            await interaction.response.send_message(
                "Spotify API credentials updated successfully! 🎵\n"
                "(Rich metadata for Spotify links should now work.)",
                ephemeral=True
            )

    class SetupView(View):
        def __init__(self, cog):
            super().__init__(timeout=300)
            self.cog = cog

        @button(label="Start Setup", style=discord.ButtonStyle.green)
        async def start_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(
                "Starting MusicLinker setup...\nFirst: Where should I work?",
                ephemeral=True
            )
            view = self.cog.ChannelSelectView(self.cog, interaction.user)
            await interaction.followup.send(
                "Choose channel scope:", view=view, ephemeral=True
            )

    class ChannelSelectView(View):
        def __init__(self, cog, user):
            super().__init__(timeout=300)
            self.cog = cog
            self.user = user

            options = [
                discord.SelectOption(label="Entire Server", value="0", description="Work in all channels"),
                discord.SelectOption(label="This Channel Only", value=str(interaction.channel_id), description="Only current channel")
            ]
            self.select = Select(placeholder="Select channel scope...", options=options)
            self.add_item(self.select)

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            return interaction.user == self.user

        @Select
        async def select_callback(self, interaction: discord.Interaction):
            channel_id = int(self.select.values[0])
            await self.cog.config.guild(interaction.guild).channel_id.set(channel_id)
            await interaction.response.edit_message(
                content=f"MusicLinker will now work in {'all channels' if channel_id == 0 else 'the selected channel'}.",
                view=None
            )
            view = self.cog.ResponseModeView(self.cog, interaction.user)
            await interaction.followup.send(
                "Next: How should I respond to music links?",
                view=view,
                ephemeral=True
            )

    class ResponseModeView(View):
        def __init__(self, cog, user):
            super().__init__(timeout=300)
            self.cog = cog
            self.user = user

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            return interaction.user == self.user

        @button(label="Auto-Reply (Embeds)", style=discord.ButtonStyle.primary)
        async def auto_reply(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self.cog.config.guild(interaction.guild).use_reactions.set(False)
            await interaction.response.edit_message(content="Set to **auto-reply embeds**.", view=None)
            view = self.cog.ToggleView(self.cog, interaction.user)
            await interaction.followup.send("Finally: Turn MusicLinker on now?", view=view, ephemeral=True)

        @button(label="Reaction Mode", style=discord.ButtonStyle.secondary)
        async def reaction_mode(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self.cog.config.guild(interaction.guild).use_reactions.set(True)
            await interaction.response.edit_message(content="Set to **reaction mode**.", view=None)
            view = self.cog.ToggleView(self.cog, interaction.user)
            await interaction.followup.send("Finally: Turn MusicLinker on now?", view=view, ephemeral=True)

    class ToggleView(View):
        def __init__(self, cog, user):
            super().__init__(timeout=300)
            self.cog = cog
            self.user = user

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            return interaction.user == self.user

        @button(label="Yes - Turn ON", style=discord.ButtonStyle.success)
        async def turn_on(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self.cog.config.guild(interaction.guild).enabled.set(True)
            await interaction.response.edit_message(content="MusicLinker is now **enabled**!", view=None)
            await interaction.followup.send("Setup complete! Use `[p]ml settings` to review.", ephemeral=True)

        @button(label="No - Leave OFF", style=discord.ButtonStyle.danger)
        async def turn_off(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.edit_message(content="MusicLinker remains **disabled** for now.", view=None)
            await interaction.followup.send("Setup complete! Use `[p]ml toggle` later if you want to enable.", ephemeral=True)

    @musiclinker.command(name="setup")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def ml_setup(self, ctx: commands.Context):
        """Start interactive MusicLinker setup wizard."""
        embed = discord.Embed(
            title="MusicLinker Setup Wizard",
            description="Let's configure MusicLinker step by step.\nClick below to begin.",
            color=discord.Color(0x1DB954)
        )
        view = self.SetupView(self)
        await ctx.send(embed=embed, view=view)

    @musiclinker.command(name="search")
    @commands.guild_only()
    async def ml_search(self, ctx: commands.Context, *, query: str):
        """Search for a song and get cross-platform links."""
        guild_conf = self.config.guild(ctx.guild)
        if not await guild_conf.enabled():
            await ctx.send("MusicLinker is disabled. Use [p]ml toggle.")
            return

        channel_id = await guild_conf.channel_id()
        if channel_id != 0 and ctx.channel.id != channel_id:
            await ctx.send("Restricted to configured channel.")
            return

        parts = query.split(" ", 1)
        artist = parts[0] if len(parts) > 1 else "Unknown"
        title = parts[1] if len(parts) > 1 else query

        urls = self._build_search_urls(artist.strip(), title.strip())

        embed = discord.Embed(title=f"Search: {title.strip()}", color=discord.Color.blurple())
        embed.add_field(
            name="Listen on",
            value="\n".join(f"[{k.replace('_',' ').title()}]({v})" for k,v in urls.items()),
            inline=False
        )

        await ctx.send(embed=embed)

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

        if not spotify_ids and not youtube_ids:
            return

        use_react = await guild_conf.use_reactions()
        show_thumb = await guild_conf.show_thumbnail()
        max_l = await guild_conf.max_links_per_message()

        try:
            async with message.channel.typing():
                embeds = await self._build_embeds_for_links(spotify_ids, youtube_ids, show_thumb, max_l)
        except Exception:
            embeds = []

        if not embeds:
            await message.reply(warning("Could not fetch rich metadata right now. Try again later or use `[p]ml search <song>`."), mention_author=False)
            return

        if use_react:
            try:
                msg = await message.reply("React ♻️ to see music links (expires in 5 min)", mention_author=False)
                await start_adding_reactions(msg, ["♻️"])
                self._track_message(msg.id, {
                    "embeds": embeds,
                    "author": message.author.id,
                    "expires": time.time() + 300,
                })
            except discord.HTTPException:
                pass
        else:
            for e in embeds:
                try:
                    await message.reply(embed=e, mention_author=False)
                except discord.HTTPException:
                    pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return

        if str(payload.emoji) != "♻️":
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
            await msg.clear_reactions()
            for embed in data["embeds"]:
                await channel.send(embed=embed)
        except discord.HTTPException:
            pass
        finally:
            self._message_links.pop(payload.message_id, None)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        pass
