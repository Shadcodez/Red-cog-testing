import asyncio
import discord
import csv
import io
from redbot.core import commands, Config, data_manager
from redbot.core.bot import Red
import openpyxl
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict

class ExcelEvents(commands.Cog):
    """Manage Discord Scheduled Events from Excel or pasted CSV."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=9876543210987654321, force_registration=True
        )
        defaults_guild = {
            "event_mappings": {},
            "last_synced": None
        }
        self.config.register_guild(**defaults_guild)

    # ====================== IMPROVED DATE PARSER ======================
    async def _parse_datetime(self, value) -> Optional[datetime]:
        if not value:
            return None

        # Handle Excel serial date numbers (e.g. 46170.3333)
        if isinstance(value, (int, float)):
            try:
                # Excel base date is 1899-12-30 (accounting for Lotus 1-2-3 bug)
                base = datetime(1899, 12, 30)
                delta = timedelta(days=value)
                dt = base + delta
                return dt.replace(tzinfo=timezone.utc)
            except:
                pass

        value_str = str(value).strip()

        # Expanded list of formats (very forgiving)
        formats = [
            "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S",          # 2026-05-29 08:00
            "%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S",          # 05/29/2026 08:00
            "%m/%d/%y %H:%M", "%m/%d/%y %H:%M:%S",          # 05/29/26 08:00
            "%m/%d/%Y %I:%M %p", "%m/%d/%Y %I:%M:%S %p",    # 05/29/2026 8:00 AM
            "%m/%d/%Y %-H:%M", "%m/%d/%Y %-H:%M:%S",        # 05/29/2026 8:00 (some systems)
            "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S",          # European style
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(value_str, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

        # Last resort: try to parse with dateutil if available, but we avoid extra deps
        print(f"[ExcelEvents] Could not parse date: '{value_str}'")
        return None

    def _normalize_key(self, name: str) -> str:
        return str(name).strip().lower()

    async def _create_event(self, guild: discord.Guild, data: Dict, row_num: int) -> Optional[discord.ScheduledEvent]:
        name = str(data.get("name", "")).strip()
        if not name:
            print(f"[ExcelEvents] Row {row_num}: Skipped - No Name")
            return None

        start_time = await self._parse_datetime(data.get("start"))
        if not start_time:
            print(f"[ExcelEvents] Row {row_num}: Invalid Start time → {data.get('start')}")
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
            entity_type = discord.EntityType.stage if event_type == "stage" else discord.EntityType.voice
            if channel_id_input:
                try:
                    ch_id = int(str(channel_id_input).strip())
                    channel = guild.get_channel(ch_id)
                except:
                    print(f"[ExcelEvents] Row {row_num}: Invalid ChannelID format")

        if entity_type in (discord.EntityType.voice, discord.EntityType.stage) and not channel:
            print(f"[ExcelEvents] Row {row_num}: Voice/Stage - missing or invalid ChannelID")
            return None
        if entity_type == discord.EntityType.external and not event_location:
            print(f"[ExcelEvents] Row {row_num}: External - missing Location")
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
            print(f"[ExcelEvents] Row {row_num}: SUCCESS - Created '{name}'")
            return event
        except Exception as exc:
            print(f"[ExcelEvents] Row {row_num}: Failed to create '{name}': {exc}")
            return None

    # ====================== COMMANDS ======================
    @commands.group(name="excelevents", invoke_without_command=True)
    @commands.guild_only()
    @commands.admin_or_permissions(manage_events=True)
    async def excelevents(self, ctx: commands.Context):
        """Manage Discord Scheduled Events from Excel or CSV."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @excelevents.command(name="upload")
    async def upload(self, ctx: commands.Context):
        """
        Upload an events.xlsx file.
        """
        if not ctx.message.attachments:
            await ctx.send("Please attach an `.xlsx` file.")
            return

        attachment = ctx.message.attachments[0]
        if not attachment.filename.lower().endswith((".xlsx", ".xls")):
            await ctx.send("Only `.xlsx` or `.xls` files supported.")
            return

        data_path: Path = data_manager.cog_data_path(self)
        data_path.mkdir(parents=True, exist_ok=True)
        file_path = data_path / "events.xlsx"

        await attachment.save(str(file_path))
        await ctx.send(f"✅ File uploaded!\nRun `{ctx.prefix}excelevents sync`")

    @excelevents.command(name="paste")
    async def paste(self, ctx: commands.Context):
        """Paste raw CSV text directly."""
        lines = ctx.message.content.splitlines()
        csv_text = "\n".join(lines[1:]) if len(lines) > 1 else ""
        if not csv_text.strip():
            await ctx.send("Paste your CSV after the command.")
            return

        data_path = data_manager.cog_data_path(self)
        data_path.mkdir(parents=True, exist_ok=True)
        file_path = data_path / "events.xlsx"

        try:
            reader = csv.DictReader(io.StringIO(csv_text))
            rows = list(reader)
            wb = openpyxl.Workbook()
            ws = wb.active
            if rows:
                ws.append(list(rows[0].keys()))
                for row in rows:
                    ws.append(list(row.values()))
            wb.save(file_path)
            await ctx.send("✅ CSV saved!\nRun `excelevents sync`")
        except Exception as e:
            await ctx.send(f"❌ CSV parse error: {e}")

    @excelevents.command(name="sync")
    async def sync(self, ctx: commands.Context):
        """Sync events from the file."""
        data_path = data_manager.cog_data_path(self)
        file_path = data_path / "events.xlsx"

        if not file_path.exists():
            await ctx.send("No file found. Use `upload` or `paste` first.")
            return

        await ctx.send("🔄 Syncing events...")

        try:
            wb = openpyxl.load_workbook(file_path, data_only=True)
            ws = wb.active
            headers = [str(cell.value).strip().lower() if cell.value else "" for cell in next(ws.iter_rows(min_row=1, max_row=1))]

            mappings = await self.config.guild(ctx.guild).event_mappings()
            new_mappings = {}
            active_keys = set()
            processed = 0
            row_num = 1

            for row in ws.iter_rows(min_row=2, values_only=True):
                row_num += 1
                if not row or all(v is None for v in row):
                    continue

                data = {headers[i]: row[i] for i in range(len(row)) if i < len(headers) and headers[i]}
                name = str(data.get("name", "")).strip()

                if not name:
                    print(f"[ExcelEvents] Row {row_num}: Skipped - No Name")
                    continue

                key = self._normalize_key(name)
                active_keys.add(key)

                if key in mappings:
                    try:
                        event = await ctx.guild.fetch_scheduled_event(mappings[key])
                        start_time = await self._parse_datetime(data.get("start"))
                        end_time = await self._parse_datetime(data.get("end"))
                        await event.edit(name=name, description=str(data.get("description", ""))[:1000] or None, start_time=start_time, end_time=end_time)
                        new_mappings[key] = event.id
                        processed += 1
                        print(f"[ExcelEvents] Row {row_num}: Updated '{name}'")
                        continue
                    except:
                        pass

                new_event = await self._create_event(ctx.guild, data, row_num)
                if new_event:
                    new_mappings[key] = new_event.id
                    processed += 1

            deleted = 0
            for old_key, old_id in list(mappings.items()):
                if old_key not in active_keys:
                    try:
                        await ctx.guild.fetch_scheduled_event(old_id).delete()
                        deleted += 1
                    except:
                        pass

            await self.config.guild(ctx.guild).event_mappings.set(new_mappings)

            await ctx.send(f"✅ **Sync completed!**\n• Processed: **{processed}**\n• Active now: **{len(new_mappings)}**\n• Deleted: **{deleted}**")

        except Exception as e:
            await ctx.send(f"❌ Sync failed: {type(e).__name__}: {e}")

    @excelevents.command(name="status")
    async def status(self, ctx: commands.Context):
        data_path = data_manager.cog_data_path(self)
        file_path = data_path / "events.xlsx"
        mappings = await self.config.guild(ctx.guild).event_mappings()
        await ctx.send(f"**Status**\n• File exists: **{file_path.exists()}**\n• Tracked events: **{len(mappings)}**")

    def cog_unload(self):
        pass
