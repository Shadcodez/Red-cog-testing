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
    """Easily create and manage Discord Scheduled Events from Excel or pasted CSV."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=9876543210987654321, force_registration=True
        )
        defaults_guild = {
            "event_mappings": {},
            "last_synced": None,
            "use_announcements": False,
            "announce_channel": None,
            "ping_role": None
        }
        self.config.register_guild(**defaults_guild)

    # ====================== FORGIVING DATE PARSER ======================
    async def _parse_datetime(self, value) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, (int, float)):
            try:
                base = datetime(1899, 12, 30)
                dt = base + timedelta(days=value)
                return dt.replace(tzinfo=timezone.utc)
            except:
                pass
        value_str = str(value).strip()
        formats = [
            "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S",
            "%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S",
            "%m/%d/%y %H:%M", "%m/%d/%y %H:%M:%S",
            "%m/%d/%Y %I:%M %p", "%m/%d/%Y %I:%M:%S %p",
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
                except:
                    pass

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
        except:
            return None

    # ====================== ANNOUNCEMENT FALLBACK ======================
    async def _post_announcement(self, guild: discord.Guild, data: Dict):
        if not await self.config.guild(guild).use_announcements():
            return
        channel_id = await self.config.guild(guild).announce_channel()
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if not channel:
            return

        name = str(data.get("name", "")).strip()
        start = await self._parse_datetime(data.get("start"))
        desc = str(data.get("description", "")).strip()

        embed = discord.Embed(title=name, description=desc or "No description provided.", color=0x00ff00, timestamp=start)
        embed.add_field(name="Starts", value=f"<t:{int(start.timestamp())}:F>", inline=True)

        ping_role_id = await self.config.guild(guild).ping_role()
        content = f"<@&{ping_role_id}>" if ping_role_id else None

        await channel.send(content=content, embed=embed)

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
        Upload an events.xlsx file.

        **Easy copy & paste example** (paste into row 1 of Excel):
        ```csv
        Type,Name,Description,Start,End,Location,ChannelID
        voice,Finding knees toes,Just look down bruh,2026-05-29 08:00,2026-05-29 09:00,,166220559225585664
        voice,toy story warhammer edition,shits rough with Buzz,2026-05-29 11:00,2026-05-29 11:30,,166220559225585664
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
        await ctx.send(f"✅ File uploaded!\nUse `{ctx.prefix}excelevents sync` to process it.")

    @excelevents.command(name="paste")
    async def paste(self, ctx: commands.Context):
        """
        Paste raw CSV text directly.

        **Easy copy & paste example**:
        ```csv
        Type,Name,Description,Start,End,Location,ChannelID
        voice,Finding knees toes,Just look down bruh,2026-05-29 08:00,2026-05-29 09:00,,166220559225585664
        voice,toy story warhammer edition,shits rough with Buzz,2026-05-29 11:00,2026-05-29 11:30,,166220559225585664
        ```
        """
        lines = ctx.message.content.splitlines()
        csv_text = "\n".join(lines[1:]) if len(lines) > 1 else ""
        if not csv_text.strip():
            await ctx.send("Please paste your CSV data after the command.")
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
            await ctx.send("✅ CSV saved!\nUse `excelevents sync` to process it.")
        except Exception as e:
            await ctx.send(f"❌ Failed to parse CSV: {e}")

    @excelevents.command(name="sync")
    async def sync(self, ctx: commands.Context):
        """Process the uploaded Excel or pasted CSV and sync Discord events."""
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

                await ctx.send(f"**Row {row_num}** → Name: `{name}` | Start: `{data.get('start')}` | ChannelID: `{data.get('channelid')}`")

                if not name:
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
                        continue
                    except:
                        pass

                new_event = await self._create_event(ctx.guild, data)
                if new_event:
                    new_mappings[key] = new_event.id
                    processed += 1
                    await self._post_announcement(ctx.guild, data)

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

    @excelevents.command(name="list")
    async def list_events(self, ctx: commands.Context):
        """List all currently managed events."""
        mappings = await self.config.guild(ctx.guild).event_mappings()
        if not mappings:
            await ctx.send("No events are currently managed.")
            return
        lines = ["**Managed Events:**"]
        for key, eid in mappings.items():
            try:
                event = await ctx.guild.fetch_scheduled_event(eid)
                lines.append(f"• `{key}` → **{event.name}** — {event.status.name}")
            except:
                lines.append(f"• `{key}` → (Event not found)")
        await ctx.send("\n".join(lines[:25]))

    @excelevents.command(name="status")
    async def status(self, ctx: commands.Context):
        """Show status of the events file and tracked mappings."""
        data_path = data_manager.cog_data_path(self)
        file_path = data_path / "events.xlsx"
        mappings = await self.config.guild(ctx.guild).event_mappings()
        await ctx.send(f"**Status**\n• File exists: **{file_path.exists()}**\n• Tracked events: **{len(mappings)}**")

    @excelevents.command(name="clearfile")
    async def clearfile(self, ctx: commands.Context):
        """Delete the uploaded events.xlsx file."""
        data_path = data_manager.cog_data_path(self)
        file_path = data_path / "events.xlsx"
        if file_path.exists():
            file_path.unlink()
            await ctx.send("✅ Excel file deleted.")
        else:
            await ctx.send("No file to delete.")

    def cog_unload(self):
        pass
