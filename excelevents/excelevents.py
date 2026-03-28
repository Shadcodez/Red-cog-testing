import asyncio
import csv
import io
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict

import discord
import openpyxl
from redbot.core import commands, Config, data_manager
from redbot.core.bot import Red


class ExcelEvents(commands.Cog):
    """Easily create and manage Discord Scheduled Events from Excel or pasted CSV.

    Features:
    • Bulk upload/sync events from .xlsx (or .xls) or raw CSV
    • Forgiving date parser (Excel serial dates + many common formats)
    • Updates existing events or creates new ones
    • Announcement mode: posts rich embeds with Discord <t:timestamp> formatting,
      hyperlinks to the event, location, type, and relative times
    • Only ONE Excel file is ever kept in the cog data folder (auto-overwrite)
    • Interactive help with copy-paste examples
    • Safe fallback: if editing fails, it deletes & recreates cleanly

    **Quick Start:**
    1. `[p]excelevents upload` → attach your events.xlsx
    2. `[p]excelevents sync`
    3. (Optional) `[p]excelevents announcement toggle #announcements`
    """

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=9876543210987654321, force_registration=True
        )
        defaults_guild = {
            "event_mappings": {},       # normalized_name → event_id
            "last_synced": None,
            "announcement_mode": False,
            "announcement_channel": None,  # channel ID
        }
        self.config.register_guild(**defaults_guild)

    # ====================== FORGIVING DATE PARSER ======================
    async def _parse_datetime(self, value) -> Optional[datetime]:
        """Parse Excel serial dates, common strings, or return None."""
        if not value:
            return None
        if isinstance(value, (int, float)):
            try:
                base = datetime(1899, 12, 30)
                dt = base + timedelta(days=value)
                return dt.replace(tzinfo=timezone.utc)
            except Exception:
                pass

        value_str = str(value).strip()
        formats = [
            "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S",
            "%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S",
            "%m/%d/%y %H:%M", "%m/%d/%y %H:%M:%S",
            "%m/%d/%Y %I:%M %p", "%m/%d/%Y %I:%M:%S %p",
            "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %I:%M %p",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(value_str, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None

    def _normalize_key(self, name: str) -> str:
        """Case-insensitive key for event tracking."""
        return str(name).strip().lower()

    async def _create_event(self, guild: discord.Guild, data: Dict) -> Optional[discord.ScheduledEvent]:
        """Create a scheduled event. Returns None on failure."""
        name = str(data.get("name", "")).strip()
        if not name:
            return None

        start_time = await self._parse_datetime(data.get("start"))
        if not start_time:
            return None

        end_time = await self._parse_datetime(data.get("end"))
        description = str(data.get("description", "")).strip()[:1000] or None
        event_type = str(data.get("type", "")).strip().lower() or "voice"
        location = str(data.get("location", "")).strip() or None
        channel_id_input = data.get("channelid")

        channel = None
        event_location = None

        if event_type == "external" and location:
            entity_type = discord.EntityType.external
            event_location = location
        else:
            entity_type = (
                discord.EntityType.stage_instance
                if event_type == "stage"
                else discord.EntityType.voice
            )
            if channel_id_input:
                try:
                    ch_id = int(str(channel_id_input).strip())
                    channel = guild.get_channel(ch_id)
                except Exception:
                    pass

        # Voice/Stage events require a channel
        if entity_type in (discord.EntityType.voice, discord.EntityType.stage_instance) and not channel:
            return None

        try:
            event = await guild.create_scheduled_event(
                name=name,
                description=description,
                start_time=start_time,
                end_time=end_time,
                entity_type=entity_type,
                channel=channel,
                location=event_location,
                privacy_level=discord.PrivacyLevel.guild_only,
            )
            await asyncio.sleep(1.5)  # Rate limit friendly
            return event
        except Exception:
            return None

    def _create_event_embed(self, event: discord.ScheduledEvent) -> discord.Embed:
        """Rich announcement embed with Discord timestamps and hyperlink."""
        embed = discord.Embed(
            title=event.name[:256],
            description=(event.description or "No description provided.")[:4096],
            color=discord.Color.blurple(),
            url=event.url,  # Clickable title link to the event
        )

        if event.start_time:
            start_ts = int(event.start_time.timestamp())
            embed.add_field(
                name="🕒 Start",
                value=f"<t:{start_ts}:F> (<t:{start_ts}:R>)",
                inline=True,
            )
        if event.end_time:
            end_ts = int(event.end_time.timestamp())
            embed.add_field(
                name="🕒 End",
                value=f"<t:{end_ts}:F>",
                inline=True,
            )

        # Location
        if event.entity_type == discord.EntityType.external:
            loc_text = event.location or "External link"
        else:
            loc_text = event.channel.mention if event.channel else "Voice/Stage channel"
        embed.add_field(name="📍 Location", value=loc_text, inline=False)

        embed.add_field(
            name="Type",
            value=event.entity_type.name.replace("_", " ").title(),
            inline=True,
        )

        embed.set_footer(text="Synced via ExcelEvents • RedBot 2026")
        return embed

    # ====================== COMMANDS ======================
    @commands.group(name="excelevents", invoke_without_command=True)
    @commands.guild_only()
    @commands.admin_or_permissions(manage_events=True)
    async def excelevents(self, ctx: commands.Context):
        """Easily manage Discord Scheduled Events from Excel or pasted CSV."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @excelevents.command(name="upload")
    async def upload(self, ctx: commands.Context):
        """
        Upload an events.xlsx file (auto-overwrites previous file).

        **Easy copy & paste example** (paste into row 1 of Excel):
        ```csv
        Type,Name,Description,Start,End,Location,ChannelID
        voice,Finding knees toes,Just look down bruh,2026-05-29 08:00,2026-05-29 09:00,,166220559225585664
        external,Toy Story Warhammer,Shits rough with Buzz,2026-05-29 11:00,2026-05-29 11:30,https://twitch.tv/example,
        ```
        """
        if not ctx.message.attachments:
            await ctx.send("❌ Please attach an `.xlsx` (or `.xls`) file.")
            return

        attachment = ctx.message.attachments[0]
        if not attachment.filename.lower().endswith((".xlsx", ".xls")):
            await ctx.send("❌ Only `.xlsx` or `.xls` files are supported.")
            return

        data_path: Path = data_manager.cog_data_path(self)
        data_path.mkdir(parents=True, exist_ok=True)
        file_path = data_path / "events.xlsx"

        await attachment.save(str(file_path))
        await ctx.send(
            "✅ **File uploaded and old file replaced!**\n"
            f"Use `{ctx.prefix}excelevents sync` to process it."
        )

    @excelevents.command(name="paste")
    async def paste(self, ctx: commands.Context):
        """
        Paste raw CSV text directly.

        **Easy copy & paste example**:
        ```csv
        Type,Name,Description,Start,End,Location,ChannelID
        voice,Finding knees toes,Just look down bruh,2026-05-29 08:00,2026-05-29 09:00,,166220559225585664
        external,Toy Story Warhammer,Shits rough with Buzz,2026-05-29 11:00,2026-05-29 11:30,https://twitch.tv/example,
        ```
        """
        lines = ctx.message.content.splitlines()
        csv_text = "\n".join(lines[1:]) if len(lines) > 1 else ""

        if not csv_text.strip():
            await ctx.send("❌ Please paste your CSV data after the command.")
            return

        data_path = data_manager.cog_data_path(self)
        data_path.mkdir(parents=True, exist_ok=True)
        file_path = data_path / "events.xlsx"

        try:
            reader = csv.DictReader(io.StringIO(csv_text))
            rows = list(reader)
            if not rows:
                await ctx.send("❌ No valid rows found in CSV.")
                return

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.append(list(rows[0].keys()))
            for row in rows:
                ws.append(list(row.values()))
            wb.save(file_path)

            await ctx.send(
                "✅ **CSV converted and saved!**\n"
                f"Use `{ctx.prefix}excelevents sync` to process it."
            )
        except Exception as e:
            await ctx.send(f"❌ Failed to parse CSV: {type(e).__name__} – {e}")

    @excelevents.command(name="sync")
    async def sync(self, ctx: commands.Context):
        """Process the uploaded Excel/CSV and sync Discord events + optional announcements."""
        if not ctx.guild.me.guild_permissions.manage_events:
            await ctx.send("❌ I need the **Manage Events** permission.")
            return

        data_path = data_manager.cog_data_path(self)
        file_path = data_path / "events.xlsx"
        if not file_path.exists():
            await ctx.send("❌ No file found. Use `upload` or `paste` first.")
            return

        await ctx.send("🔄 **Syncing events…** (real-time feedback below)")

        try:
            wb = openpyxl.load_workbook(file_path, data_only=True)
            ws = wb.active
            headers = [
                str(cell.value).strip().lower() if cell.value is not None else ""
                for cell in next(ws.iter_rows(min_row=1, max_row=1))
            ]

            mappings = await self.config.guild(ctx.guild).event_mappings()
            new_mappings: Dict[str, int] = {}
            active_keys = set()
            processed = 0
            new_events_created: list[discord.ScheduledEvent] = []

            row_num = 1
            for row in ws.iter_rows(min_row=2, values_only=True):
                row_num += 1
                if not row or all(v is None for v in row):
                    continue

                data = {
                    headers[i]: row[i]
                    for i in range(len(row))
                    if i < len(headers) and headers[i]
                }

                name = str(data.get("name", "")).strip()
                await ctx.send(
                    f"**Row {row_num}** → Name: `{name}` | "
                    f"Start: `{data.get('start')}` | ChannelID: `{data.get('channelid')}`"
                )

                if not name:
                    continue

                key = self._normalize_key(name)
                active_keys.add(key)

                start_time = await self._parse_datetime(data.get("start"))
                end_time = await self._parse_datetime(data.get("end"))

                if not start_time:
                    continue

                # Try update existing
                if key in mappings:
                    try:
                        event = await ctx.guild.fetch_scheduled_event(mappings[key])
                        await event.edit(
                            name=name,
                            description=str(data.get("description", "")).strip()[:1000] or None,
                            start_time=start_time,
                            end_time=end_time,
                        )
                        new_mappings[key] = event.id
                        processed += 1
                        continue
                    except Exception:
                        # Fallback: delete old event
                        try:
                            old_event = await ctx.guild.fetch_scheduled_event(mappings[key])
                            await old_event.delete()
                        except Exception:
                            pass

                # Create new event
                new_event = await self._create_event(ctx.guild, data)
                if new_event:
                    new_mappings[key] = new_event.id
                    new_events_created.append(new_event)
                    processed += 1

            # Clean up removed events
            deleted = 0
            for old_key, old_id in list(mappings.items()):
                if old_key not in active_keys:
                    try:
                        event = await ctx.guild.fetch_scheduled_event(old_id)
                        await event.delete()
                        deleted += 1
                    except Exception:
                        pass

            await self.config.guild(ctx.guild).event_mappings.set(new_mappings)
            await self.config.guild(ctx.guild).last_synced.set(
                datetime.now(timezone.utc).isoformat()
            )

            # Announcement Mode
            announcement_mode = await self.config.guild(ctx.guild).announcement_mode()
            announced = 0
            if announcement_mode and new_events_created:
                ann_ch_id = await self.config.guild(ctx.guild).announcement_channel()
                if ann_ch_id:
                    ann_channel = ctx.guild.get_channel(ann_ch_id)
                    if ann_channel and ann_channel.permissions_for(ctx.guild.me).send_messages:
                        for event in new_events_created:
                            try:
                                embed = self._create_event_embed(event)
                                await ann_channel.send(embed=embed)
                                announced += 1
                                await asyncio.sleep(0.8)
                            except Exception:
                                pass

            result = (
                f"**✅ FINAL RESULT**\n"
                f"• Processed: **{processed}**\n"
                f"• Active now: **{len(new_mappings)}**\n"
                f"• Deleted: **{deleted}**"
            )
            if announced:
                result += f"\n📢 **Announced {announced} new events**!"
            await ctx.send(result)

        except Exception as e:
            await ctx.send(f"❌ Sync failed: {type(e).__name__}: {e}")

    @excelevents.command(name="status")
    async def status(self, ctx: commands.Context):
        """Show file status, tracked events, and announcement settings."""
        data_path = data_manager.cog_data_path(self)
        file_path = data_path / "events.xlsx"
        mappings = await self.config.guild(ctx.guild).event_mappings()
        ann_mode = await self.config.guild(ctx.guild).announcement_mode()
        ann_ch_id = await self.config.guild(ctx.guild).announcement_channel()
        ann_ch = ctx.guild.get_channel(ann_ch_id) if ann_ch_id else None

        status_msg = (
            f"**ExcelEvents Status**\n"
            f"• File exists: **{file_path.exists()}**\n"
            f"• Tracked events: **{len(mappings)}**\n"
            f"• Announcement mode: **{'✅ Enabled' if ann_mode else '❌ Disabled'}**"
        )
        if ann_ch:
            status_msg += f"\n• Announcement channel: {ann_ch.mention}"
        await ctx.send(status_msg)

    @excelevents.group(name="announcement", invoke_without_command=True)
    @commands.guild_only()
    @commands.admin_or_permissions(manage_events=True)
    async def announcement_group(self, ctx: commands.Context):
        """Toggle announcement mode and set the channel for rich embeds."""
        await ctx.send_help(ctx.command)

    @announcement_group.command(name="toggle")
    async def toggle_announcement(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Toggle announcement mode.
        Provide a #channel to enable and set the announcement channel.
        Run without a channel to toggle the mode off/on."""
        config = self.config.guild(ctx.guild)

        if channel is None:
            current = await config.announcement_mode()
            new_mode = not current
            await config.announcement_mode.set(new_mode)
            await ctx.send(f"✅ Announcement mode **{'enabled' if new_mode else 'disabled'}**.")
            return

        # Enable + set channel
        await config.announcement_channel.set(channel.id)
        await config.announcement_mode.set(True)
        await ctx.send(
            f"✅ **Announcement mode enabled!**\n"
            f"Rich embeds with Discord timestamps will be posted in {channel.mention} "
            f"when new events are created via `sync`."
        )

    @excelevents.command(name="clear")
    async def clear(self, ctx: commands.Context):
        """Delete the events.xlsx file and reset all tracked mappings."""
        data_path = data_manager.cog_data_path(self)
        file_path = data_path / "events.xlsx"

        if file_path.exists():
            file_path.unlink()
            await self.config.guild(ctx.guild).event_mappings.set({})
            await ctx.send("✅ **Events file deleted** and mappings reset.")
        else:
            await ctx.send("No file to clear.")

    def cog_unload(self):
        """Clean shutdown."""
        pass
