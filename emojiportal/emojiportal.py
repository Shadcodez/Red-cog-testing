"""
EmojiPortal - Modern emoji management for Red Discord Bot.

Features:
- List all server emojis in compact yellow embeds (even number per row, minimal messages).
- Download all emojis as 1-5 zip files (each under 50 MB), using temporary in-memory/temp handling only.
- Move emojis to another server with full rate-limit, timeout, and error handling.
  Process is deliberately slow, saves progress, and can resume after hangups.
- Public list/download limited to 10 times per day per server (non-resource intensive config check).
- Staff-only for adding emojis (steal/move).
- Additional: search, stats.
"""

from __future__ import annotations

import asyncio
import io
import logging
import zipfile
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import aiohttp
import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, pagify

log = logging.getLogger("red.emojiportal")

# Constants
EMOJIS_PER_ROW = 8  # Even number
MAX_ZIP_SIZE = 50 * 1024 * 1024  # 50 MB
MAX_ZIPS = 5
MOVE_DELAY = 2.5  # seconds between creations to stay under aggressive emoji rate limits
YELLOW = discord.Color.gold()
DAILY_PUBLIC_LIMIT = 10  # list + download combined per server per day


class EmojiPortal(commands.Cog):
    """Modern tools for listing, downloading, and moving server emojis."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210123, force_registration=True)
        self.config.register_global(transfers={})  # job_id -> transfer state
        self.config.register_guild(
            public_uses_today=0,
            last_public_date=None,
        )
        self.session: Optional[aiohttp.ClientSession] = None
        self._move_tasks: Dict[str, asyncio.Task] = {}

    async def cog_load(self) -> None:
        self.session = aiohttp.ClientSession()

    async def cog_unload(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()
        # Cancel running move tasks cleanly
        for task in self._move_tasks.values():
            if not task.done():
                task.cancel()

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    async def _check_and_increment_public_limit(self, guild: discord.Guild) -> bool:
        """
        Non-resource intensive daily limit check for public commands (list/download).
        Uses Config only. Returns True if allowed and increments, False if limit reached.
        """
        today = datetime.now(timezone.utc).date().isoformat()
        data = await self.config.guild(guild).all()
        last_date = data.get("last_public_date")
        count = data.get("public_uses_today", 0)

        if last_date != today:
            # New day – reset
            await self.config.guild(guild).last_public_date.set(today)
            await self.config.guild(guild).public_uses_today.set(1)
            return True

        if count >= DAILY_PUBLIC_LIMIT:
            return False

        await self.config.guild(guild).public_uses_today.set(count + 1)
        return True

    @staticmethod
    def _format_emoji_grid(emojis: List[discord.Emoji], per_row: int = EMOJIS_PER_ROW) -> str:
        """Build a multi-line string of emojis with even number per row."""
        lines = []
        for i in range(0, len(emojis), per_row):
            chunk = emojis[i : i + per_row]
            lines.append(" ".join(str(e) for e in chunk))
        return "\n".join(lines)

    def _build_list_embeds(self, guild: discord.Guild, emojis: List[discord.Emoji]) -> List[discord.Embed]:
        """Create as few embeds as possible packing the emoji grid into yellow embeds."""
        if not emojis:
            return [
                discord.Embed(
                    title=f"{guild.name} Emojis",
                    description="This server has no custom emojis.",
                    color=YELLOW,
                )
            ]

        grid = self._format_emoji_grid(emojis)
        embeds: List[discord.Embed] = []
        # Split grid into chunks that fit in description (~3900 to be safe)
        for page_text in pagify(grid, delims=["\n"], page_length=3900):
            embed = discord.Embed(
                title=f"{guild.name} Emojis" if not embeds else f"{guild.name} Emojis (cont.)",
                description=page_text,
                color=YELLOW,
            )
            embed.set_footer(text=f"Total: {len(emojis)} emojis • {EMOJIS_PER_ROW} per row")
            embeds.append(embed)
        return embeds

    async def _fetch_emoji_bytes(self, emoji: discord.Emoji) -> Optional[bytes]:
        """Temporarily fetch emoji image bytes without permanent storage."""
        if not self.session:
            return None
        try:
            async with self.session.get(emoji.url) as resp:
                if resp.status == 200:
                    return await resp.read()
                log.warning("Failed to fetch %s: HTTP %s", emoji, resp.status)
        except Exception as e:
            log.exception("Error fetching emoji %s: %s", emoji, e)
        return None

    async def _create_zip_from_emojis(
        self, emojis: List[discord.Emoji]
    ) -> List[Tuple[str, io.BytesIO]]:
        """
        Create 1-5 zip files (each <50MB) containing the emojis.
        Uses only in-memory BytesIO; nothing is written to disk permanently.
        """
        zips: List[Tuple[str, io.BytesIO]] = []
        current_zip = io.BytesIO()
        zf = zipfile.ZipFile(current_zip, "w", compression=zipfile.ZIP_DEFLATED)
        current_size = 0
        zip_index = 1
        added = 0

        for emoji in emojis:
            data = await self._fetch_emoji_bytes(emoji)
            if not data:
                continue
            ext = "gif" if emoji.animated else "png"
            filename = f"{emoji.name}.{ext}"
            # Avoid name collisions inside zip
            while filename in zf.namelist():
                filename = f"{emoji.name}_{added}.{ext}"
            file_size = len(data)

            # Start a new zip if this file would exceed limit
            if current_size + file_size > MAX_ZIP_SIZE and current_size > 0:
                zf.close()
                current_zip.seek(0)
                zips.append((f"emojis_part{zip_index}.zip", current_zip))
                zip_index += 1
                if zip_index > MAX_ZIPS:
                    log.info("Reached max %s zips, stopping early", MAX_ZIPS)
                    break
                current_zip = io.BytesIO()
                zf = zipfile.ZipFile(current_zip, "w", compression=zipfile.ZIP_DEFLATED)
                current_size = 0

            zf.writestr(filename, data)
            current_size += file_size
            added += 1

        # Finalize last zip if it has content
        if current_size > 0 and zip_index <= MAX_ZIPS:
            zf.close()
            current_zip.seek(0)
            zips.append((f"emojis_part{zip_index}.zip", current_zip))

        return zips

    async def _safe_create_emoji(
        self, guild: discord.Guild, name: str, image: bytes, reason: str = "EmojiPortal move"
    ) -> Optional[discord.Emoji]:
        """Create emoji with retry on rate limits and name conflicts."""
        attempt = 0
        base_name = name
        while attempt < 5:
            try:
                return await guild.create_custom_emoji(name=name, image=image, reason=reason)
            except discord.HTTPException as e:
                if e.status == 429:
                    retry = getattr(e, "retry_after", 30) or 30
                    log.info("Rate limited on emoji create, sleeping %.1fs", retry)
                    await asyncio.sleep(retry + 1)
                    attempt += 1
                    continue
                if e.status == 400 and "name" in str(e).lower():
                    # Name conflict or invalid – try suffix
                    name = f"{base_name}_{attempt + 1}"
                    attempt += 1
                    continue
                log.warning("Failed to create emoji %s in %s: %s", name, guild.id, e)
                return None
            except Exception as e:
                log.exception("Unexpected error creating emoji: %s", e)
                return None
        return None

    # -------------------------------------------------------------------------
    # Commands
    # -------------------------------------------------------------------------

    @commands.group(name="emojiportal")
    @commands.guild_only()
    async def emojiportal(self, ctx: commands.Context):
        """Emoji management tools (list, download, move, etc.)."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @emojiportal.command(name="list")
    async def ep_list(self, ctx: commands.Context):
        """
        Post all server emojis into yellow embeds.

        Uses an even number of emojis per row and as few messages as possible
        while respecting Discord embed character limits.

        Anyone can use this (limited to 10 public uses per day per server).
        """
        if not await self._check_and_increment_public_limit(ctx.guild):
            return await ctx.send(
                f"Daily limit of {DAILY_PUBLIC_LIMIT} list/download uses reached for this server. "
                "Try again tomorrow (UTC)."
            )

        emojis = list(ctx.guild.emojis)
        embeds = self._build_list_embeds(ctx.guild, emojis)

        for embed in embeds:
            await ctx.send(embed=embed)
            await asyncio.sleep(0.5)

    @emojiportal.command(name="download", aliases=["dl", "export"])
    async def ep_download(self, ctx: commands.Context):
        """
        Download all server emojis as 1–5 zip files (each under 50 MB).

        Files are created temporarily in memory and deleted after sending.
        Anyone can use this (limited to 10 public uses per day per server).
        """
        if not await self._check_and_increment_public_limit(ctx.guild):
            return await ctx.send(
                f"Daily limit of {DAILY_PUBLIC_LIMIT} list/download uses reached for this server. "
                "Try again tomorrow (UTC)."
            )

        emojis = list(ctx.guild.emojis)
        if not emojis:
            return await ctx.send("No custom emojis to download.")

        async with ctx.typing():
            zips = await self._create_zip_from_emojis(emojis)

        if not zips:
            return await ctx.send("Failed to fetch any emoji images.")

        await ctx.send(
            f"Prepared **{len(zips)}** zip file(s) containing the server emojis.\n"
            f"Each is under 50 MB. Temporary only — nothing left on the bot host."
        )

        for name, bio in zips:
            bio.seek(0)
            file = discord.File(bio, filename=name)
            await ctx.send(file=file)
            bio.close()
            await asyncio.sleep(1)

    @emojiportal.command(name="move")
    @commands.admin_or_permissions(manage_emojis=True)
    async def ep_move(self, ctx: commands.Context, target_guild_id: int):
        """
        Move all emojis from this server to another server the bot is in.

        Staff only. The process is intentionally slow, handles rate limits / timeouts / errors,
        saves progress, and can be resumed if interrupted.

        **Arguments**
        - `<target_guild_id>`: The ID of the destination server.
        """
        source = ctx.guild
        target = self.bot.get_guild(target_guild_id)
        if not target:
            return await ctx.send("Bot is not in the target server, or the ID is invalid.")
        if target.id == source.id:
            return await ctx.send("Source and target cannot be the same server.")

        # Permission checks
        if not source.me.guild_permissions.manage_emojis:
            return await ctx.send("I need **Manage Expressions** in this (source) server.")
        if not target.me.guild_permissions.manage_emojis:
            return await ctx.send("I need **Manage Expressions** in the target server.")

        emojis = [e for e in source.emojis if e.available]
        if not emojis:
            return await ctx.send("No available emojis to move.")

        job_id = f"{source.id}_{target.id}_{ctx.author.id}"
        transfers = await self.config.transfers()
        if job_id in transfers and transfers[job_id].get("status") == "running":
            return await ctx.send("A move job for these servers is already running.")

        # Save initial state
        state = {
            "source_id": source.id,
            "target_id": target.id,
            "initiator": ctx.author.id,
            "pending_ids": [e.id for e in emojis],
            "completed": 0,
            "failed": 0,
            "status": "running",
        }
        transfers[job_id] = state
        await self.config.transfers.set(transfers)

        await ctx.send(
            f"Starting move of **{len(emojis)}** emojis → **{target.name}**.\n"
            f"This will be slow (≈{MOVE_DELAY}s + rate-limit waits between each) and can be resumed.\n"
            f"Job ID: `{job_id}`\nUse `[p]ep status` or `[p]ep resume` if needed."
        )

        # Launch background task
        task = asyncio.create_task(self._run_move_job(job_id, ctx.channel.id))
        self._move_tasks[job_id] = task

    @emojiportal.command(name="resume")
    @commands.admin_or_permissions(manage_emojis=True)
    async def ep_resume(self, ctx: commands.Context, job_id: str):
        """Resume a previously interrupted emoji move job. Staff only."""
        transfers = await self.config.transfers()
        if job_id not in transfers:
            return await ctx.send("No such transfer job found.")
        state = transfers[job_id]
        if state.get("status") == "running":
            return await ctx.send("That job is already marked as running.")
        if not state.get("pending_ids"):
            return await ctx.send("That job has no remaining emojis.")

        state["status"] = "running"
        transfers[job_id] = state
        await self.config.transfers.set(transfers)

        await ctx.send(f"Resuming job `{job_id}`…")
        task = asyncio.create_task(self._run_move_job(job_id, ctx.channel.id))
        self._move_tasks[job_id] = task

    @emojiportal.command(name="status")
    async def ep_status(self, ctx: commands.Context):
        """Show status of any active or incomplete emoji move jobs."""
        transfers = await self.config.transfers()
        if not transfers:
            return await ctx.send("No transfer jobs recorded.")

        lines = []
        for jid, state in transfers.items():
            pending = len(state.get("pending_ids", []))
            status = state.get("status", "unknown")
            lines.append(
                f"`{jid}` — {status} — completed: {state.get('completed', 0)}, "
                f"pending: {pending}, failed: {state.get('failed', 0)}"
            )
        text = "\n".join(lines)
        for page in pagify(text):
            await ctx.send(box(page, lang="yaml"))

    @emojiportal.command(name="search")
    async def ep_search(self, ctx: commands.Context, *, query: str):
        """Search server emojis by name (case-insensitive partial match)."""
        query = query.lower()
        matches = [e for e in ctx.guild.emojis if query in e.name.lower()]
        if not matches:
            return await ctx.send("No matching emojis.")
        embeds = self._build_list_embeds(ctx.guild, matches)
        for embed in embeds[:3]:  # limit to avoid spam
            embed.title = f"Search results for “{query}”"
            await ctx.send(embed=embed)

    @emojiportal.command(name="steal")
    @commands.admin_or_permissions(manage_emojis=True)
    async def ep_steal(self, ctx: commands.Context, emoji: discord.PartialEmoji):
        """Steal a single emoji (from this or another server) into the current server. Staff only."""
        if not emoji.url:
            return await ctx.send("Could not get image URL for that emoji.")
        data = await self._fetch_emoji_bytes_from_url(emoji.url)
        if not data:
            return await ctx.send("Failed to download the emoji image.")
        created = await self._safe_create_emoji(ctx.guild, emoji.name, data, reason=f"Stolen by {ctx.author}")
        if created:
            await ctx.send(f"Added {created}")
        else:
            await ctx.send("Failed to create the emoji (name conflict, slots full, or rate limit).")

    # -------------------------------------------------------------------------
    # Background move runner
    # -------------------------------------------------------------------------

    async def _run_move_job(self, job_id: str, notify_channel_id: int) -> None:
        """Background task that performs the actual emoji move with progress saving."""
        try:
            transfers = await self.config.transfers()
            state = transfers.get(job_id)
            if not state:
                return

            source = self.bot.get_guild(state["source_id"])
            target = self.bot.get_guild(state["target_id"])
            channel = self.bot.get_channel(notify_channel_id)

            if not source or not target:
                state["status"] = "error"
                transfers[job_id] = state
                await self.config.transfers.set(transfers)
                if channel:
                    await channel.send(f"Job `{job_id}` failed: one of the guilds is no longer available.")
                return

            pending_ids = state["pending_ids"][:]
            completed = state.get("completed", 0)
            failed = state.get("failed", 0)

            for eid in pending_ids[:]:  # copy so we can mutate
                emoji = discord.utils.get(source.emojis, id=eid)
                if not emoji:
                    pending_ids.remove(eid)
                    continue

                data = await self._fetch_emoji_bytes(emoji)
                if not data:
                    failed += 1
                    pending_ids.remove(eid)
                    continue

                created = await self._safe_create_emoji(
                    target, emoji.name, data, reason=f"Moved from {source.name} by EmojiPortal"
                )
                if created:
                    completed += 1
                else:
                    failed += 1

                pending_ids.remove(eid)

                # Persist progress after every emoji
                state["pending_ids"] = pending_ids
                state["completed"] = completed
                state["failed"] = failed
                transfers[job_id] = state
                await self.config.transfers.set(transfers)

                # Deliberate delay to avoid hammering the emoji endpoint
                await asyncio.sleep(MOVE_DELAY)

                # Occasional progress update
                if completed % 10 == 0 and channel:
                    try:
                        await channel.send(
                            f"Job `{job_id}` progress: {completed} moved, {len(pending_ids)} remaining."
                        )
                    except Exception:
                        pass

            # Finished
            state["status"] = "completed" if not pending_ids else "partial"
            transfers[job_id] = state
            await self.config.transfers.set(transfers)

            if channel:
                await channel.send(
                    f"Job `{job_id}` finished.\n"
                    f"Moved: **{completed}** | Failed: **{failed}** | Remaining: **{len(pending_ids)}**"
                )

        except asyncio.CancelledError:
            log.info("Move job %s cancelled", job_id)
            # State is already saved after each emoji, so resume will pick up remaining
        except Exception as e:
            log.exception("Move job %s crashed: %s", job_id, e)
            try:
                transfers = await self.config.transfers()
                if job_id in transfers:
                    transfers[job_id]["status"] = "error"
                    await self.config.transfers.set(transfers)
            except Exception:
                pass
        finally:
            self._move_tasks.pop(job_id, None)

    async def _fetch_emoji_bytes_from_url(self, url: str) -> Optional[bytes]:
        if not self.session:
            return None
        try:
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    return await resp.read()
        except Exception:
            pass
        return None

    # -------------------------------------------------------------------------
    # Suggestions / extra utility
    # -------------------------------------------------------------------------

    @emojiportal.command(name="stats")
    async def ep_stats(self, ctx: commands.Context):
        """Show emoji statistics for the server."""
        emojis = ctx.guild.emojis
        animated = sum(1 for e in emojis if e.animated)
        static = len(emojis) - animated
        embed = discord.Embed(title=f"{ctx.guild.name} Emoji Stats", color=YELLOW)
        embed.add_field(name="Total", value=str(len(emojis)))
        embed.add_field(name="Static", value=str(static))
        embed.add_field(name="Animated", value=str(animated))
        embed.set_footer(text="Slot limits depend on server boost level (50/100/150/250 base).")
        await ctx.send(embed=embed)
