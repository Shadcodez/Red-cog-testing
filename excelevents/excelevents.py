import asyncio
import csv
import io
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Tuple

import discord
import openpyxl
from redbot.core import commands, Config, data_manager
from redbot.core.bot import Red


class ExcelEvents(commands.Cog):
    """Easily create and manage Discord Scheduled Events from Excel or CSV.

    Features (2026 Red Bot ready):
    • Bulk upload .xlsx or paste CSV → create/update/delete scheduled events
    • Robust parsing (handles messy CSV, missing columns, Excel serial dates)
    • Writes Discord Event ID + clickable URL back into your spreadsheet after sync
    • Announcement embeds in a channel for new events
    • Optional reminder pings
    • Full validation + safety limits
    """

    MAX_ROWS = 500  # Hard safety limit

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=9876543210987654321, force_registration=True
        )
        defaults_guild = {
            "event_mappings": {},
            "last_synced": None,
            "announcement_mode": False,
            "announcement_channel": None,
            "reminder_mode": False,
            "reminder_channel": None,
            "reminder_minutes": [60, 15, 5],
            "reminder_sent": {},
        }
        self.config.register_guild(**defaults_guild)
        self.reminder_task = None

    async def cog_load(self):
        if self.reminder_task is None or self.reminder_task.done():
            self.reminder_task = asyncio.create_task(self._reminder_task())

    # ====================== HELPERS ======================
    async def _parse_datetime(self, value) -> Optional[datetime]:
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
        if not value_str:
            return None
        formats = [
            "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S",
            "%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S",
            "%m/%d/%y %H:%M", "%m/%d/%y %H:%M:%S",
            "%m/%d/%Y %I:%M %p", "%m/%d/%Y %I:%M:%S %p",
            "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %I:%M %p",
            "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(value_str, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None

    def _normalize_key(self, name: str) -> str:
        return str(name).strip().lower()

    def _is_valid_xlsx(self, file_path: Path) -> bool:
        try:
            with open(file_path, "rb") as f:
                header = f.read(4)
            return header[:2] == b'PK'
        except Exception:
            return False

    # ====================== ROBUST COLUMN MAPPING (with aliases) ======================
    def _get_column_indices(self, headers: List[str]) -> Dict[str, int]:
        col_map = {}
        aliases = {
            "name": ["name", "event name", "title", "event"],
            "start": ["start", "start time", "start date", "date", "when"],
            "end": ["end", "end time", "end date"],
            "description": ["description", "desc", "details"],
            "type": ["type", "event type", "format", "kind"],
            "location": ["location", "place", "venue", "address", "link"],
            "channelid": ["channelid", "channel id", "channel", "voice channel", "stage channel"],
        }
        for i, h in enumerate(headers):
            if not h:
                continue
            norm = self._normalize_key(h)
            for canonical, alias_list in aliases.items():
                if any(norm == self._normalize_key(a) for a in alias_list):
                    col_map[canonical] = i
                    break
            else:
                col_map[norm] = i
        return col_map

    def _get_cell(self, row: tuple, col_map: Dict[str, int], key: str, default=None):
        idx = col_map.get(key)
        if idx is not None and idx < len(row):
            val = row[idx]
            return val if val is not None else default
        return default

    # ====================== FIXED CREATE EVENT (critical fix for external events) ======================
    async def _create_event(self, guild: discord.Guild, data: Dict) -> Optional[discord.ScheduledEvent]:
        name = str(data.get("name", "")).strip()
        if not name or len(name) > 100:
            return None

        start_time = await self._parse_datetime(data.get("start"))
        if not start_time:
            return None

        end_time = await self._parse_datetime(data.get("end"))
        description = str(data.get("description", "")).strip()[:1000] or None
        event_type_str = str(data.get("type", "")).strip().lower() or "voice"
        location = str(data.get("location", "")).strip() or None
        channel_id_input = data.get("channelid")

        # Determine entity type
        if event_type_str in ("external", "url", "link"):
            entity_type = discord.EntityType.external
        elif event_type_str == "stage":
            entity_type = discord.EntityType.stage_instance
        else:
            entity_type = discord.EntityType.voice

        channel = None
        if entity_type in (discord.EntityType.voice, discord.EntityType.stage_instance) and channel_id_input:
            try:
                ch_id = int(str(channel_id_input).strip())
                temp_ch = guild.get_channel(ch_id)
                if temp_ch:
                    if (entity_type == discord.EntityType.voice and isinstance(temp_ch, discord.VoiceChannel)) or \
                       (entity_type == discord.EntityType.stage_instance and isinstance(temp_ch, discord.StageChannel)):
                        channel = temp_ch
            except Exception:
                pass

        try:
            if entity_type == discord.EntityType.external:
                if not location:
                    return None
                event = await guild.create_scheduled_event(
                    name=name,
                    description=description,
                    start_time=start_time,
                    end_time=end_time,
                    entity_type=entity_type,
                    location=location,
                    privacy_level=discord.PrivacyLevel.guild_only,
                )
            else:
                if not channel:
                    return None
                event = await guild.create_scheduled_event(
                    name=name,
                    description=description,
                    start_time=start_time,
                    end_time=end_time,
                    entity_type=entity_type,
                    channel=channel,
                    privacy_level=discord.PrivacyLevel.guild_only,
                )
            await asyncio.sleep(1.5)  # Rate-limit safety
            return event
        except Exception:
            return None

    def _create_event_embed(self, event: discord.ScheduledEvent) -> discord.Embed:
        embed = discord.Embed(
            title=event.name[:256],
            description=(event.description or "No description provided.")[:4096],
            color=discord.Color.blurple(),
            url=event.url,
        )
        if event.start_time:
            ts = int(event.start_time.timestamp())
            embed.add_field(name="🕒 Start", value=f"<t:{ts}:F> (<t:{ts}:R>)", inline=True)
        if event.end_time:
            ts = int(event.end_time.timestamp())
            embed.add_field(name="🕒 End", value=f"<t:{ts}:F>", inline=True)

        loc = event.location or (event.channel.mention if event.channel else "Voice/Stage")
        embed.add_field(name="📍 Location", value=loc, inline=False)
        embed.add_field(name="Type", value=event.entity_type.name.replace("_", " ").title(), inline=True)
        embed.set_footer(text="New Event • Synced via ExcelEvents • RedBot 2026")
        return embed

    def _create_reminder_embed(self, event: discord.ScheduledEvent, minutes: int) -> discord.Embed:
        embed = discord.Embed(
            title=f"⏰ {event.name} starts in {minutes} minutes!",
            description=(event.description or "")[:4096],
            color=discord.Color.orange(),
            url=event.url,
        )
        if event.start_time:
            ts = int(event.start_time.timestamp())
            embed.add_field(name="Exact Time", value=f"<t:{ts}:F>", inline=False)
        loc = event.location or (event.channel.mention if event.channel else "Voice/Stage")
        embed.add_field(name="📍 Location", value=loc, inline=False)
        embed.set_footer(text=f"Reminder • ExcelEvents")
        return embed

    # ====================== ADVANCED VALIDATION ======================
    async def _validate_excel(self, file_path: Path, guild: discord.Guild) -> Tuple[List[str], List[str]]:
        errors: List[str] = []
        warnings: List[str] = []

        if not file_path.exists():
            errors.append("No events.xlsx file found. Use `upload` or `paste` first.")
            return errors, warnings

        if file_path.stat().st_size == 0:
            errors.append("The uploaded file is empty.")
            return errors, warnings

        is_real_xlsx = self._is_valid_xlsx(file_path)

        try:
            if not is_real_xlsx:
                raise zipfile.BadZipFile("Not a valid .xlsx")

            wb = openpyxl.load_workbook(file_path, data_only=True)
            ws = wb.active
            if ws is None or ws.max_row < 1:
                errors.append("Worksheet is empty or unreadable.")
                return errors, warnings

            header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
            headers = [str(cell).strip().lower() if cell is not None else "" for cell in header_row]
            col_map = self._get_column_indices(headers)

        except (zipfile.BadZipFile, openpyxl.utils.exceptions.InvalidFileException):
            errors.append("❌ This is **not** a valid .xlsx file.")
            errors.append("It looks like a CSV file renamed to .xlsx.")
            errors.append("**Use `,excelevents paste` instead.**")
            return errors, warnings
        except Exception as e:
            errors.append(f"Failed to read file: {type(e).__name__} – {e}")
            return errors, warnings

        required = {"name", "start"}
        missing = [col for col in required if col not in col_map]
        if missing:
            errors.append(f"Missing required column(s): {', '.join(missing)}")

        row_num = 1
        seen_names: set[str] = set()

        for row in ws.iter_rows(min_row=2, values_only=True):
            row_num += 1
            if not row or all(v is None for v in row):
                continue

            name = str(self._get_cell(row, col_map, "name", "")).strip()
            start_val = self._get_cell(row, col_map, "start")

            if not name:
                errors.append(f"Row {row_num}: Missing or empty **Name**")
                continue

            if len(name) > 100:
                errors.append(f"Row {row_num}: Name too long (max 100 characters)")

            key = self._normalize_key(name)
            if key in seen_names:
                warnings.append(f"Row {row_num}: Duplicate name '{name}' – only last row kept")
            seen_names.add(key)

            start_dt = await self._parse_datetime(start_val)
            if not start_dt:
                errors.append(f"Row {row_num}: Invalid **Start** time format")
            elif start_dt < datetime.now(timezone.utc):
                warnings.append(f"Row {row_num}: Start time is in the past")

            end_val = self._get_cell(row, col_map, "end")
            if end_val:
                end_dt = await self._parse_datetime(end_val)
                if not end_dt:
                    errors.append(f"Row {row_num}: Invalid **End** time format")
                elif start_dt and end_dt <= start_dt:
                    errors.append(f"Row {row_num}: End time must be after Start time")

        if not seen_names:
            errors.append("No valid event rows found in the file.")

        return errors, warnings

    # ====================== BACKGROUND REMINDER TASK ======================
    async def _reminder_task(self):
        await self.bot.wait_until_ready()
        while True:
            try:
                for guild in self.bot.guilds:
                    config = self.config.guild(guild)
                    if not await config.reminder_mode():
                        continue
                    ch_id = await config.reminder_channel()
                    channel = guild.get_channel(ch_id) if ch_id else None
                    if not (channel and channel.permissions_for(guild.me).send_messages):
                        continue

                    mappings = await config.event_mappings()
                    reminder_sent = await config.reminder_sent() or {}

                    for event_id in list(mappings.values()):
                        try:
                            event = await guild.fetch_scheduled_event(event_id)
                            if event.status not in (discord.ScheduledEventStatus.scheduled, discord.ScheduledEventStatus.active):
                                continue
                            if not event.start_time:
                                continue

                            minutes_until = (event.start_time - datetime.now(timezone.utc)).total_seconds() / 60
                            for min_before in await config.reminder_minutes():
                                if min_before > 0 and abs(minutes_until - min_before) <= 7:
                                    sent_list = reminder_sent.get(str(event_id), [])
                                    if min_before not in sent_list:
                                        embed = self._create_reminder_embed(event, min_before)
                                        await channel.send(embed=embed)
                                        reminder_sent.setdefault(str(event_id), []).append(min_before)
                                        await asyncio.sleep(1.5)
                        except Exception:
                            continue

                    await config.reminder_sent.set(reminder_sent)
            except Exception:
                pass
            await asyncio.sleep(300)

    # ====================== COMMANDS ======================
    @commands.group(name="excelevents", invoke_without_command=True)
    @commands.guild_only()
    @commands.admin_or_permissions(manage_events=True)
    async def excelevents(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @excelevents.command(name="template")
    async def template(self, ctx: commands.Context):
        """Send a ready-to-use CSV template."""
        example = (
            "name,start,end,description,type,location,channelid\n"
            'Game Night,2026-04-05 20:00,2026-04-05 22:00,Weekly game night,voice,,"123456789012345678"\n'
            'Community Meeting,2026-04-10 19:00,,Monthly meeting,stage,,"987654321098765432"\n'
            'External Webinar,2026-04-15 18:00,2026-04-15 19:00,Live on YouTube,external,https://youtube.com/live/abc123,'
        )
        await ctx.send(f"**Example CSV template** (copy & paste after the command):\n```csv\n{example}\n```")

    @excelevents.command(name="upload")
    async def upload(self, ctx: commands.Context):
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
        await ctx.send("✅ **File uploaded!** Use `check` to validate.")

    @excelevents.command(name="paste")
    async def paste(self, ctx: commands.Context):
        """Hardened paste command – very tolerant of trailing commas/spaces."""
        lines = ctx.message.content.splitlines()
        csv_text = "\n".join(lines[1:]) if len(lines) > 1 else ""

        if not csv_text.strip():
            await ctx.send("❌ Please paste your CSV data after the command.")
            return

        data_path = data_manager.cog_data_path(self)
        data_path.mkdir(parents=True, exist_ok=True)
        file_path = data_path / "events.xlsx"

        try:
            input_io = io.StringIO(csv_text.strip())
            reader = csv.reader(input_io, delimiter=',', quotechar='"',
                                quoting=csv.QUOTE_MINIMAL, skipinitialspace=True)

            rows = []
            for row in reader:
                if row and any(cell.strip() for cell in row):
                    cleaned_row = [cell.strip() for cell in row]
                    rows.append(cleaned_row)

            if len(rows) < 1:
                await ctx.send("❌ No valid rows found in the pasted CSV.")
                return

            if len(rows) - 1 > self.MAX_ROWS:
                rows = rows[:self.MAX_ROWS + 1]
                await ctx.send(f"⚠️ **Row limit reached!** Only the first **{self.MAX_ROWS}** events were saved.")

            if rows:
                header_len = len(rows[0])
                for i in range(1, len(rows)):
                    if len(rows[i]) > header_len:
                        rows[i] = rows[i][:header_len]
                    elif len(rows[i]) < header_len:
                        rows[i] += [''] * (header_len - len(rows[i]))

            wb = openpyxl.Workbook()
            ws = wb.active
            for row in rows:
                ws.append(row)
            wb.save(file_path)

            data_rows = len(rows) - 1
            await ctx.send(
                f"✅ **CSV parsed and saved successfully!**\n"
                f"• **{data_rows}** event rows processed\n"
                f"Use `{ctx.prefix}excelevents check` to validate."
            )

        except Exception as e:
            await ctx.send(f"❌ Failed to parse CSV: {type(e).__name__} – {e}")

    @excelevents.command(name="check")
    async def check(self, ctx: commands.Context):
        data_path = data_manager.cog_data_path(self)
        file_path = data_path / "events.xlsx"

        await ctx.send("🔍 **Running advanced validation...**")

        errors, warnings = await self._validate_excel(file_path, ctx.guild)

        if errors:
            error_text = "\n".join([f"❌ {msg}" for msg in errors])
            await ctx.send(f"**Validation Failed:**\n{error_text}\n\nFix the issues and try again.")
        elif warnings:
            warn_text = "\n".join([f"⚠️ {msg}" for msg in warnings])
            await ctx.send(f"**✅ Valid with warnings:**\n{warn_text}\n\nYou may now run `sync`.")
        else:
            await ctx.send("✅ **Perfect! No errors or warnings.** Ready to sync.")

    @excelevents.command(name="sync")
    async def sync(self, ctx: commands.Context):
        if not ctx.guild.me.guild_permissions.manage_events:
            await ctx.send("❌ I need the **Manage Events** permission.")
            return

        data_path = data_manager.cog_data_path(self)
        file_path = data_path / "events.xlsx"
        if not file_path.exists():
            await ctx.send("❌ No file found. Use `upload` or `paste` first.")
            return

        errors, warnings = await self._validate_excel(file_path, ctx.guild)
        if errors:
            await ctx.send("⚠️ Validation failed. Run `check` first.")
            return

        await ctx.send("🔄 **Syncing events…** (this may take a moment for many rows)")

        try:
            wb = openpyxl.load_workbook(file_path, data_only=True)
            ws = wb.active
            header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
            headers = [str(cell).strip().lower() if cell is not None else "" for cell in header_row]
            col_map = self._get_column_indices(headers)

            mappings = await self.config.guild(ctx.guild).event_mappings()
            new_mappings: Dict[str, int] = {}
            active_keys = set()
            processed = 0
            new_events_created = []

            row_num = 1
            for row in ws.iter_rows(min_row=2, values_only=True):
                row_num += 1
                if not row or all(v is None for v in row):
                    continue

                name = str(self._get_cell(row, col_map, "name", "")).strip()
                if not name:
                    continue

                key = self._normalize_key(name)
                active_keys.add(key)

                data = {
                    "name": name,
                    "start": self._get_cell(row, col_map, "start"),
                    "end": self._get_cell(row, col_map, "end"),
                    "description": self._get_cell(row, col_map, "description"),
                    "type": self._get_cell(row, col_map, "type"),
                    "location": self._get_cell(row, col_map, "location"),
                    "channelid": self._get_cell(row, col_map, "channelid"),
                }

                start_time = await self._parse_datetime(data["start"])
                if not start_time:
                    continue

                if key in mappings:
                    try:
                        event = await ctx.guild.fetch_scheduled_event(mappings[key])
                        await event.edit(
                            name=name,
                            description=str(data.get("description", "")).strip()[:1000] or None,
                            start_time=start_time,
                            end_time=await self._parse_datetime(data.get("end")),
                        )
                        new_mappings[key] = event.id
                        processed += 1
                        continue
                    except Exception:
                        pass  # Fall through to create new

                new_event = await self._create_event(ctx.guild, data)
                if new_event:
                    new_mappings[key] = new_event.id
                    new_events_created.append(new_event)
                    processed += 1
                else:
                    await ctx.send(f"⚠️ **Failed** to create/update event: {name}")

            # Cleanup old events
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
            await self.config.guild(ctx.guild).last_synced.set(datetime.now(timezone.utc).isoformat())

            # === NEW: Write Discord Event ID + URL back into the spreadsheet ===
            try:
                wb = openpyxl.load_workbook(file_path, data_only=True)
                ws = wb.active
                header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
                headers = [str(cell).strip().lower() if cell is not None else "" for cell in header_row]

                id_col = None
                url_col = None
                for c_idx, h in enumerate(headers, start=1):
                    if h == "discord event id":
                        id_col = c_idx
                    if h == "discord event url":
                        url_col = c_idx

                if id_col is None:
                    id_col = ws.max_column + 1
                    ws.cell(row=1, column=id_col, value="Discord Event ID")
                if url_col is None:
                    url_col = ws.max_column + 1
                    ws.cell(row=1, column=url_col, value="Discord Event URL")

                for r_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                    name = str(self._get_cell(row, col_map, "name", "")).strip()
                    if not name:
                        continue
                    key = self._normalize_key(name)
                    if key in new_mappings:
                        event_id = new_mappings[key]
                        try:
                            event = await ctx.guild.fetch_scheduled_event(event_id)
                            ws.cell(row=r_idx, column=id_col, value=event_id)
                            ws.cell(row=r_idx, column=url_col, value=event.url)
                        except Exception:
                            pass

                wb.save(file_path)
            except Exception:
                pass  # Non-critical – sync still succeeded

            # Announcement for new events
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

            result = f"**✅ FINAL RESULT**\n• Processed: **{processed}**\n• Active now: **{len(new_mappings)}**\n• Deleted: **{deleted}**"
            if announced:
                result += f"\n📢 Announced **{announced}** new events!"
            result += "\n📊 **Spreadsheet updated with live Discord Event IDs & URLs!**"
            await ctx.send(result)

        except Exception as e:
            await ctx.send(f"❌ Sync failed: {type(e).__name__}: {e}")

    @excelevents.command(name="status")
    async def status(self, ctx: commands.Context):
        data_path = data_manager.cog_data_path(self)
        file_path = data_path / "events.xlsx"
        mappings = await self.config.guild(ctx.guild).event_mappings()
        await ctx.send(
            f"**ExcelEvents Status**\n"
            f"• File exists: **{file_path.exists()}**\n"
            f"• Tracked events: **{len(mappings)}**"
        )

    @excelevents.group(name="announcement", invoke_without_command=True)
    async def announcement_group(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @announcement_group.command(name="toggle")
    async def toggle_announcement(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        config = self.config.guild(ctx.guild)
        if channel is None:
            new_mode = not await config.announcement_mode()
            await config.announcement_mode.set(new_mode)
            await ctx.send(f"✅ Announcement mode **{'enabled' if new_mode else 'disabled'}**.")
            return
        await config.announcement_channel.set(channel.id)
        await config.announcement_mode.set(True)
        await ctx.send(f"✅ Announcement mode enabled → {channel.mention}")

    @excelevents.group(name="reminder", invoke_without_command=True)
    async def reminder_group(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @reminder_group.command(name="toggle")
    async def toggle_reminder(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        config = self.config.guild(ctx.guild)
        if channel is None:
            new_mode = not await config.reminder_mode()
            await config.reminder_mode.set(new_mode)
            await ctx.send(f"✅ Reminder mode **{'enabled' if new_mode else 'disabled'}**.")
            return
        await config.reminder_channel.set(channel.id)
        await config.reminder_mode.set(True)
        await ctx.send(f"✅ Reminder mode enabled → {channel.mention}")

    @reminder_group.command(name="times")
    async def reminder_times(self, ctx: commands.Context, *minutes: int):
        valid = [m for m in minutes if m > 0]
        if not valid:
            await ctx.send("❌ Please provide positive numbers.")
            return
        await self.config.guild(ctx.guild).reminder_minutes.set(valid)
        await ctx.send(f"✅ Reminder times updated to: **{valid}** minutes before start.")

    @excelevents.command(name="clear")
    async def clear(self, ctx: commands.Context):
        data_path = data_manager.cog_data_path(self)
        file_path = data_path / "events.xlsx"
        if file_path.exists():
            file_path.unlink()
            await self.config.guild(ctx.guild).event_mappings.set({})
            await ctx.send("✅ Events file deleted and mappings reset.")
        else:
            await ctx.send("No file to clear.")

    def cog_unload(self):
        if self.reminder_task and not self.reminder_task.done():
            self.reminder_task.cancel()
