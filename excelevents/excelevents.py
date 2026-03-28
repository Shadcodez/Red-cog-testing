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
        self.config = Config.get_conf(self, identifier=9876543210987654321, force_registration=True)
        self.config.register_guild(event_mappings={}, last_synced=None)

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
            await guild.system_channel.send(f"❌ Row {row_num}: Skipped — No Name") if guild.system_channel else None
            return None

        start_time = await self._parse_datetime(data.get("start"))
        if not start_time:
            print(f"[ExcelEvents] Row {row_num}: ❌ Invalid Start → '{data.get('start')}'")
            return None

        end_time = await self._parse_datetime(data.get("end"))
        description = str(data.get("description", "")).strip()[:1000] or None

        event_type = str(data.get("type", "")).strip().lower() or "voice"
        location = str(data.get("location", "")).strip() or None
        channel_id_input = data.get("channelid")

        channel = None
        event_location = None
        entity_type = discord.EntityType.voice

        if event_type == "external" and location:
            entity_type = discord.EntityType.external
            event_location = location
        elif event_type == "stage" and channel_id_input:
            entity_type = discord.EntityType.stage
            try:
                channel = guild.get_channel(int(str(channel_id_input).strip()))
            except:
                pass
        else:  # voice
            entity_type = discord.EntityType.voice
            if channel_id_input:
                try:
                    channel = guild.get_channel(int(str(channel_id_input).strip()))
                except:
                    pass

        if entity_type in (discord.EntityType.voice, discord.EntityType.stage) and not channel:
            print(f"[ExcelEvents] Row {row_num}: ❌ Voice/Stage needs valid ChannelID")
            return None
        if entity_type == discord.EntityType.external and not event_location:
            print(f"[ExcelEvents] Row {row_num}: ❌ External needs Location")
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
            print(f"[ExcelEvents] Row {row_num}: ✅ Created '{name}'")
            return event
        except Exception as exc:
            print(f"[ExcelEvents] Row {row_num}: ❌ Failed '{name}': {exc}")
            return None

    # ====================== COMMANDS ======================
    @commands.group(name="excelevents", invoke_without_command=True)
    @commands.guild_only()
    @commands.admin_or_permissions(manage_events=True)
    async def excelevents(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @excelevents.command(name="paste")
    async def paste(self, ctx: commands.Context):
        """Paste raw CSV text directly into chat."""
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
            await ctx.send("✅ CSV saved as Excel! Now run `excelevents sync`")
        except Exception as e:
            await ctx.send(f"❌ Failed to parse CSV: {e}")

    @excelevents.command(name="sync")
    async def sync(self, ctx: commands.Context):
        """Sync events from the uploaded/pasted file."""
        data_path = data_manager.cog_data_path(self)
        file_path = data_path / "events.xlsx"

        if not file_path.exists():
            await ctx.send("No file found. Use `excelevents paste` or `upload` first.")
            return

        await ctx.send("🔄 Syncing with full diagnostics...")

        try:
            wb = openpyxl.load_workbook(file_path, data_only=True)
            ws = wb.active
            headers = [str(cell.value).strip().lower() if cell.value else "" for cell in next(ws.iter_rows(min_row=1, max_row=1))]
            print(f"[ExcelEvents] Headers found: {headers}")

            mappings: Dict[str, int] = await self.config.guild(ctx.guild).event_mappings()
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
                    await ctx.send(f"❌ Row {row_num}: Skipped — No Name")
                    continue

                key = self._normalize_key(name)
                active_keys.add(key)

                print(f"[ExcelEvents] Processing row {row_num}: '{name}'")

                # Update existing
                if key in mappings:
                    try:
                        event = await ctx.guild.fetch_scheduled_event(mappings[key])
                        start_time = await self._parse_datetime(data.get("start"))
                        end_time = await self._parse_datetime(data.get("end"))
                        await event.edit(name=name, description=str(data.get("description", ""))[:1000] or None, start_time=start_time, end_time=end_time)
                        new_mappings[key] = event.id
                        processed += 1
                        await ctx.send(f"✅ Row {row_num}: Updated '{name}'")
                        continue
                    except:
                        pass

                # Create new
                new_event = await self._create_event(ctx.guild, data, row_num)
                if new_event:
                    new_mappings[key] = new_event.id
                    processed += 1
                    await ctx.send(f"✅ Row {row_num}: Created '{name}'")

            # Delete old events
            deleted = 0
            for old_key, old_id in list(mappings.items()):
                if old_key not in active_keys:
                    try:
                        event = await ctx.guild.fetch_scheduled_event(old_id)
                        await event.delete()
                        deleted += 1
                    except:
                        pass

            await self.config.guild(ctx.guild).event_mappings.set(new_mappings)

            await ctx.send(f"**Final Result**\n• Processed: **{processed}**\n• Active now: **{len(new_mappings)}**\n• Deleted: **{deleted}**")

        except Exception as e:
            await ctx.send(f"❌ Sync failed: {type(e).__name__}: {e}")

    @excelevents.command(name="status")
    async def status(self, ctx: commands.Context):
        """Check if the Excel file exists and how many events are tracked."""
        data_path = data_manager.cog_data_path(self)
        file_path = data_path / "events.xlsx"
        mappings = await self.config.guild(ctx.guild).event_mappings()
        exists = file_path.exists()
        await ctx.send(f"**ExcelEvents Status**\n• File exists: **{exists}**\n• Tracked events: **{len(mappings)}**")

    def cog_unload(self):
        pass
