import asyncio
import discord
import csv
import io
from redbot.core import commands, Config, data_manager
from redbot.core.bot import Red
import openpyxl
from datetime import datetime, timezone
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

    # ====================== HELPERS ======================
    async def _parse_datetime(self, value) -> Optional[datetime]:
        if not value:
            return None
        value_str = str(value).strip()
        formats = ["%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S"]
        for fmt in formats:
            try:
                dt = datetime.strptime(value_str, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
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
                    channel = None

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

        **Copy-paste example for Excel**:
        ```csv
        Type,Name,Description,Start,End,Location,ChannelID
        voice,Finding knees toes,Just look down bruh,2026-05-28 08:00,2026-05-28 09:00,,26355909847822000
        voice,toy story warhammer edition,shits rough with Buzz,2026-05-28 11:00,2026-05-28 11:30,,26355909847822000
        ```
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
            await ctx.send("✅ CSV saved as Excel!\nRun `excelevents sync`")
        except Exception as e:
            await ctx.send(f"❌ CSV parse error: {e}")

    @excelevents.command(name="sync")
    async def sync(self, ctx: commands.Context):
        """Sync events from the uploaded/pasted file."""
        data_path = data_manager.cog_data_path(self)
        file_path = data_path / "events.xlsx"

        if not file_path.exists():
            await ctx.send("No file found. Use `upload` or `paste` first.")
            return

        await ctx.send("🔄 Starting sync — reporting every row...")

        try:
            wb = openpyxl.load_workbook(file_path, data_only=True)
            ws = wb.active
            headers = [str(cell.value).strip().lower() if cell.value else "" for cell in next(ws.iter_rows(min_row=1, max_row=1))]
            await ctx.send(f"**Headers detected:** {headers}")

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

                await ctx.send(f"**Row {row_num}** — Name: `{name}` | Start: `{data.get('start')}` | ChannelID: `{data.get('channelid')}`")

                if not name:
                    await ctx.send(f"❌ Row {row_num}: Skipped — No Name")
                    continue

                key = self._normalize_key(name)
                active_keys.add(key)

                # Try update first
                if key in mappings:
                    try:
                        event = await ctx.guild.fetch_scheduled_event(mappings[key])
                        start_time = await self._parse_datetime(data.get("start"))
                        end_time = await self._parse_datetime(data.get("end"))
                        await event.edit(name=name, description=str(data.get("description", ""))[:1000] or None, start_time=start_time, end_time=end_time)
                        new_mappings[key] = event.id
                        processed += 1
                        await ctx.send(f"✅ Row {row_num}: Updated existing event")
                        continue
                    except:
                        pass

                # Create new event
                new_event = await self._create_event(ctx.guild, data, row_num)
                if new_event:
                    new_mappings[key] = new_event.id
                    processed += 1

            # Delete events no longer in the sheet
            deleted = 0
            for old_key, old_id in list(mappings.items()):
                if old_key not in active_keys:
                    try:
                        await ctx.guild.fetch_scheduled_event(old_id).delete()
                        deleted += 1
                    except:
                        pass

            await self.config.guild(ctx.guild).event_mappings.set(new_mappings)

            await ctx.send(f"**FINAL RESULT**\n• Processed: **{processed}**\n• Active now: **{len(new_mappings)}**\n• Deleted: **{deleted}**")

        except Exception as e:
            await ctx.send(f"❌ Sync failed: {type(e).__name__}: {e}")

    @excelevents.command(name="status")
    async def status(self, ctx: commands.Context):
        """Check if the Excel file exists."""
        data_path = data_manager.cog_data_path(self)
        file_path = data_path / "events.xlsx"
        mappings = await self.config.guild(ctx.guild).event_mappings()
        await ctx.send(f"**Status**\n• File exists: **{file_path.exists()}**\n• Tracked events: **{len(mappings)}**")

    def cog_unload(self):
        pass
