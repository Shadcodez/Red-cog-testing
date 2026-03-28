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
    """Easily create and manage Discord Scheduled Events from Excel or pasted CSV.

    Optimized CSV parsing + advanced file validation:
    • Fast csv.reader in paste command (lower memory & faster)
    • Detects CSV files mistakenly saved as .xlsx (fixes BadZipFile error)
    • Clear, actionable error messages
    • Real-time feedback during sync
    • Announcement & reminder systems with background task
    """

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
        return str(name).strip().lower()

    def _is_valid_xlsx(self, file_path: Path) -> bool:
        """Quick check if file is a real .xlsx (ZIP-based)."""
        try:
            with open(file_path, "rb") as f:
                header = f.read(4)
            return header[:2] == b'PK'
        except Exception:
            return False

    async def _create_event(self, guild: discord.Guild, data: Dict) -> Optional[discord.ScheduledEvent]:
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
            entity_type = discord.EntityType.stage_instance if event_type == "stage" else discord.EntityType.voice
            if channel_id_input:
                try:
                    ch_id = int(str(channel_id_input).strip())
                    channel = guild.get_channel(ch_id)
                except Exception:
                    pass

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
            await asyncio.sleep(1.5)
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
                raise zipfile.BadZipFile("Not a valid .xlsx file")

            wb = openpyxl.load_workbook(file_path, data_only=True)
            ws = wb.active
            if ws is None:
                errors.append("Could not read the active worksheet.")
                return errors, warnings

            header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
            headers = [str(cell).strip().lower() if cell is not None else "" for cell in header_row]

        except (zipfile.BadZipFile, openpyxl.utils.exceptions.InvalidFileException):
            errors.append("❌ This is **not** a valid .xlsx file.")
            errors.append("It looks like a CSV file that was renamed to .xlsx (or the file is corrupted).")
            errors.append("**Best solution**: Use the `,excelevents paste` command instead of upload.")
            return errors, warnings
        except Exception as e:
            errors.append(f"Failed to read file: {type(e).__name__} – {e}")
            return errors, warnings

        required = {"name", "start"}
        missing = [col for col in required if col not in headers]
        if missing:
            errors.append(f"Missing required column(s): {', '.join(missing)}")

        row_num = 1
        seen_names: set[str] = set()

        for row in ws.iter_rows(min_row=2, values_only=True):
            row_num += 1
            if not row or all(v is None for v in row):
                continue

            data = {headers[i]: row[i] for i in range(len(row)) if i < len(headers) and headers[i]}

            name = str(data.get("name", "")).strip()
            if not name:
                errors.append(f"Row {row_num}: Missing or empty **Name**")
                continue

            if len(name) > 100:
                errors.append(f"Row {row_num}: Name too long (max 100 characters)")

            key = self._normalize_key(name)
            if key in seen_names:
                warnings.append(f"Row {row_num}: Duplicate name '{name}' – only last row kept")
            seen_names.add(key)

            start_dt = await self._parse_datetime(data.get("start"))
            if not start_dt:
                errors.append(f"Row {row_num}: Invalid **Start** time")
            elif start_dt < datetime.now(timezone.utc):
                warnings.append(f"Row {row_num}: Start time is in the past")

            end_val = data.get("end")
            if end_val:
                end_dt = await self._parse_datetime(end_val)
                if not end_dt:
                    errors.append(f"Row {row_num}: Invalid **End** time")
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
        await ctx.send(
            "✅ **File uploaded and old file replaced!**\n"
            f"Use `{ctx.prefix}excelevents check` to validate it."
        )

    @excelevents.command(name="paste")
    async def paste(self, ctx: commands.Context):
        """Optimized paste command using csv.reader for speed and low memory."""
        lines = ctx.message.content.splitlines()
        csv_text = "\n".join(lines[1:]) if len(lines) > 1 else ""

        if not csv_text.strip():
            await ctx.send("❌ Please paste your CSV data after the command.")
            return

        data_path = data_manager.cog_data_path(self)
        data_path.mkdir(parents=True, exist_ok=True)
        file_path = data_path / "events.xlsx"

        try:
            input_io = io.StringIO(csv_text)
            reader = csv.reader(input_io)
            rows = list(reader)

            if not rows:
                await ctx.send("❌ No valid rows found in CSV.")
                return

            wb = openpyxl.Workbook()
            ws = wb.active
            for row in rows:
                ws.append(row)          # Direct append = faster
            wb.save(file_path)

            await ctx.send(
                f"✅ **CSV parsed successfully** ({len(rows)-1} data rows).\n"
                f"Use `{ctx.prefix}excelevents check` to validate."
            )
        except Exception as e:
            await ctx.send(f"❌ CSV parsing failed: {type(e).__name__} – {e}")

    @excelevents.command(name="check")
    async def check(self, ctx: commands.Context):
        data_path = data_manager.cog_data_path(self)
        file_path = data_path / "events.xlsx"

        await ctx.send("🔍 **Running advanced validation...**")

        errors, warnings = await self._validate_excel(file_path, ctx.guild)

        if errors:
            error_text = "\n".join([f"❌ {msg}" for msg in errors])
            await ctx.send(
                f"**Validation Failed:**\n{error_text}\n\n"
                f"After fixing, re-upload or use `paste` and run check again."
            )
        elif warnings:
            warn_text = "\n".join([f"⚠️ {msg}" for msg in warnings])
            await ctx.send(f"**✅ Valid with warnings:**\n{warn_text}\n\nYou can now run `sync`.")
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

        await ctx.send("🔄 **Syncing events…** (real-time feedback below)")

        try:
            wb = openpyxl.load_workbook(file_path, data_only=True)
            ws = wb.active
            headers = [str(cell.value).strip().lower() if cell.value is not None else "" 
                       for cell in next(ws.iter_rows(min_row=1, max_row=1))]

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

                data = {headers[i]: row[i] for i in range(len(row)) if i < len(headers) and headers[i]}

                name = str(data.get("name", "")).strip()
                await ctx.send(f"**Row {row_num}** → Name: `{name}` | Start: `{data.get('start')}`")

                if not name:
                    continue

                key = self._normalize_key(name)
                active_keys.add(key)

                start_time = await self._parse_datetime(data.get("start"))
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
                        await ctx.send(f"✅ **Updated:** [{name}]({event.url})")
                        continue
                    except Exception:
                        pass

                new_event = await self._create_event(ctx.guild, data)
                if new_event:
                    new_mappings[key] = new_event.id
                    new_events_created.append(new_event)
                    processed += 1
                    await ctx.send(f"✅ **Created:** [{new_event.name}]({new_event.url})")

            # Cleanup removed events
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

            # Announcement
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

            result = f"**✅ FINAL RESULT**\n• Processed: **{processed}**\n• Active: **{len(new_mappings)}**\n• Deleted: **{deleted}**"
            if announced:
                result += f"\n📢 Announced **{announced}** new events!"
            await ctx.send(result)

        except Exception as e:
            await ctx.send(f"❌ Sync failed: {type(e).__name__}: {e}")

    @excelevents.command(name="status")
    async def status(self, ctx: commands.Context):
        data_path = data_manager.cog_data_path(self)
        file_path = data_path / "events.xlsx"
        mappings = await self.config.guild(ctx.guild).event_mappings()
        ann_mode = await self.config.guild(ctx.guild).announcement_mode()
        rem_mode = await self.config.guild(ctx.guild).reminder_mode()

        await ctx.send(
            f"**ExcelEvents Status**\n"
            f"• File exists: **{file_path.exists()}**\n"
            f"• Tracked events: **{len(mappings)}**\n"
            f"• Announcement mode: **{'✅ Enabled' if ann_mode else '❌ Disabled'}**\n"
            f"• Reminder mode: **{'✅ Enabled' if rem_mode else '❌ Disabled'}**"
        )

    # Announcement and Reminder groups (simple toggle)
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
        await ctx.send(f"✅ Announcement mode enabled in {channel.mention}.")

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
        await ctx.send(f"✅ Reminder mode enabled in {channel.mention}.")

    @excelevents.command(name="clear")
    async def clear(self, ctx: commands.Context):
        data_path = data_manager.cog_data_path(self)
        file_path = data_path / "events.xlsx"
        if file_path.exists():
            file_path.unlink()
            await self.config.guild(ctx.guild).event_mappings.set({})
            await ctx.send("✅ File deleted and mappings reset.")
        else:
            await ctx.send("No file to clear.")

    def cog_unload(self):
        if self.reminder_task and not self.reminder_task.done():
            self.reminder_task.cancel()


# Note: You still need to implement reminder times command if desired.
# The core functionality is now optimized and robust.
