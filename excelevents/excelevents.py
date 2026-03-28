import discord
from redbot.core import commands, Config, data_manager
from redbot.core.bot import Red
import openpyxl
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict

class ExcelEvents(commands.Cog):
    """Create, update, and delete Discord Scheduled Events from an Excel sheet."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=9876543210987654321, force_registration=True
        )
        defaults_guild = {
            "event_mappings": {},   # {unique_key: discord_event_id (int)}
            "last_synced": None
        }
        self.config.register_guild(**defaults_guild)

    # ====================== HELPERS ======================
    async def _parse_datetime(self, value) -> Optional[datetime]:
        """Convert Excel value or ISO string to timezone-aware UTC datetime."""
        if isinstance(value, datetime):
            return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        if isinstance(value, str):
            try:
                cleaned = value.replace("Z", "+00:00")
                dt = datetime.fromisoformat(cleaned)
                return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
            except ValueError:
                pass
        return None

    async def _create_event(self, guild: discord.Guild, data: Dict) -> Optional[discord.ScheduledEvent]:
        """Create a new scheduled event from row data."""
        name = str(data.get("Name", "Unnamed Event")).strip()
        if not name:
            return None

        start_time = await self._parse_datetime(data.get("Start"))
        if not start_time:
            return None

        end_time = await self._parse_datetime(data.get("End"))
        description = str(data.get("Description", "")).strip()[:1000] or None
        location = str(data.get("Location", "")).strip() or None

        # Decide event type
        channel_input = data.get("Channel")
        if location and not channel_input:
            entity_type = discord.EntityType.external
            entity_metadata = discord.ScheduledEventEntityMetadata(location=location)
            channel = None
        else:
            entity_type = discord.EntityType.voice
            entity_metadata = None
            channel = None
            if channel_input:
                try:
                    ch_id = int(str(channel_input).strip())
                    channel = guild.get_channel(ch_id)
                except ValueError:
                    for ch in guild.channels:
                        if ch.name.lower() == str(channel_input).lower().strip():
                            channel = ch
                            break

        try:
            event = await guild.create_scheduled_event(
                name=name,
                description=description,
                start_time=start_time,
                end_time=end_time,
                entity_type=entity_type,
                entity_metadata=entity_metadata,
                channel=channel,
                privacy_level=discord.PrivacyLevel.guild_only,
            )
            return event
        except discord.HTTPException as exc:
            print(f"[ExcelEvents] Failed to create event '{name}': {exc}")
            return None

    # ====================== COMMANDS ======================
    @commands.command()
    @commands.guild_only()
    @commands.admin_or_permissions(manage_events=True)
    async def upload_events(self, ctx: commands.Context):
        """
        Upload a new events.xlsx file (replaces any previous file).

        **Example Excel format** (first row = headers):

        | Key            | Name                  | Description                     | Start                | End                  | Location             | Channel            |
        |----------------|-----------------------|---------------------------------|----------------------|----------------------|----------------------|--------------------|
        | weekly-meeting | Team Sync             | Weekly team catch-up            | 2026-04-05 14:00    | 2026-04-05 15:00    |                      | General Voice      |
        | conference     | Big Conference        | Annual company event            | 2026-05-10 09:00    | 2026-05-10 17:00    | New York Convention Center |                    |

        - **Key**: Unique identifier (required for updates)
        - **Start/End**: Datetime or ISO string
        - **Location**: Use for external events
        - **Channel**: Voice/Stage channel name or ID
        """
        if not ctx.message.attachments:
            await ctx.send("Please attach an `.xlsx` file.")
            return

        attachment = ctx.message.attachments[0]
        if not attachment.filename.lower().endswith((".xlsx", ".xls")):
            await ctx.send("Only `.xlsx` or `.xls` files are supported.")
            return

        data_path: Path = data_manager.cog_data_path(self)
        data_path.mkdir(parents=True, exist_ok=True)
        file_path = data_path / "events.xlsx"

        await attachment.save(str(file_path))
        await ctx.send(
            f"✅ Events sheet saved successfully.\n"
            f"Use `{ctx.prefix}sync_events` to create/update/delete Discord events."
        )

    @commands.command()
    @commands.guild_only()
    @commands.admin_or_permissions(manage_events=True)
    async def sync_events(self, ctx: commands.Context):
        """
        Sync Discord Scheduled Events with the uploaded Excel sheet.

        This will:
        - Create new events
        - Update existing events (matched by Key)
        - Delete events that are no longer in the sheet
        """
        data_path = data_manager.cog_data_path(self)
        file_path = data_path / "events.xlsx"

        if not file_path.exists():
            await ctx.send("No `events.xlsx` found. Use `[p]upload_events` first.")
            return

        await ctx.send("🔄 Reading Excel and syncing events...")

        try:
            wb = openpyxl.load_workbook(file_path, data_only=True)
            ws = wb.active
            if not ws:
                await ctx.send("❌ Could not read the active worksheet.")
                return

            headers = [str(cell.value).strip() if cell.value else "" for cell in next(ws.iter_rows(min_row=1, max_row=1))]
            header_map = {h.lower(): i for i, h in enumerate(headers) if h}

            required = ["key", "name", "start"]
            missing = [col for col in required if col not in header_map]
            if missing:
                await ctx.send(f"❌ Missing required columns: {', '.join(missing)}")
                return

            mappings: Dict[str, int] = await self.config.guild(ctx.guild).event_mappings()
            new_mappings: Dict[str, int] = {}
            active_keys = set()

            for row in ws.iter_rows(min_row=2, values_only=True):
                if not row or all(v is None for v in row):
                    continue

                data = {}
                for i, value in enumerate(row):
                    if i < len(headers) and headers[i]:
                        data[headers[i]] = value

                key = str(data.get("Key", "")).strip()
                if not key:
                    continue

                active_keys.add(key)

                # Try to update existing event
                if key in mappings:
                    try:
                        event = await ctx.guild.fetch_scheduled_event(mappings[key])
                        start_time = await self._parse_datetime(data.get("Start"))
                        end_time = await self._parse_datetime(data.get("End"))

                        await event.edit(
                            name=str(data.get("Name", event.name)).strip(),
                            description=str(data.get("Description", "") or event.description or "")[:1000] or None,
                            start_time=start_time,
                            end_time=end_time,
                        )
                        new_mappings[key] = event.id
                        continue
                    except (discord.NotFound, discord.HTTPException):
                        pass  # recreate below

                # Create new event
                new_event = await self._create_event(ctx.guild, data)
                if new_event:
                    new_mappings[key] = new_event.id

            # Delete removed events
            deleted = 0
            for old_key, old_id in list(mappings.items()):
                if old_key not in active_keys:
                    try:
                        event = await ctx.guild.fetch_scheduled_event(old_id)
                        await event.delete()
                        deleted += 1
                    except (discord.NotFound, discord.HTTPException):
                        pass

            await self.config.guild(ctx.guild).event_mappings.set(new_mappings)
            await self.config.guild(ctx.guild).last_synced.set(datetime.utcnow().isoformat())

            await ctx.send(
                f"✅ **Sync completed!**\n"
                f"• Active events: **{len(new_mappings)}**\n"
                f"• Deleted events: **{deleted}**"
            )

        except Exception as e:
            await ctx.send(f"❌ Sync failed: `{type(e).__name__}: {e}`")
            print(f"[ExcelEvents] Sync error in guild {ctx.guild.id}: {e}")

    @commands.command()
    @commands.guild_only()
    @commands.admin_or_permissions(manage_events=True)
    async def list_events(self, ctx: commands.Context):
        """List all events currently managed by this cog."""
        mappings: Dict[str, int] = await self.config.guild(ctx.guild).event_mappings()
        if not mappings:
            await ctx.send("No events are currently managed.")
            return

        lines = ["**Managed Events:**"]
        for key, eid in mappings.items():
            try:
                event = await ctx.guild.fetch_scheduled_event(eid)
                lines.append(f"• `{key}` → **{event.name}** (ID: {eid}) — {event.status.name}")
            except:
                lines.append(f"• `{key}` → (Event not found — ID: {eid})")

        await ctx.send("\n".join(lines[:25]))  # safety limit

    @commands.command(hidden=True)
    @commands.is_owner()
    async def clear_event_data(self, ctx: commands.Context):
        """Owner only: Clear all mappings and delete the Excel file."""
        data_path = data_manager.cog_data_path(self)
        file_path = data_path / "events.xlsx"
        if file_path.exists():
            file_path.unlink()

        await self.config.guild(ctx.guild).event_mappings.set({})
        await ctx.send("✅ All ExcelEvents data cleared for this server.")

    def cog_unload(self):
        pass