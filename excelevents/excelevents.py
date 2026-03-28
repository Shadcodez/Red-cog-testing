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
            "event_mappings": {},   # {normalized_name: discord_event_id}
            "last_synced": None
        }
        self.config.register_guild(**defaults_guild)

    # ====================== CONFIRMATION VIEW ======================
    class ConfirmView(discord.ui.View):
        def __init__(self, ctx: commands.Context, action: str, callback):
            super().__init__(timeout=60)
            self.ctx = ctx
            self.action = action
            self.callback = callback

        @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.danger)
        async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.ctx.author.id:
                await interaction.response.send_message("Only the command author can confirm.", ephemeral=True)
                return
            await interaction.response.defer()
            await self.callback()
            self.stop()

        @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
        async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.ctx.author.id:
                await interaction.response.send_message("Only the command author can cancel.", ephemeral=True)
                return
            await interaction.response.send_message("Action cancelled.", ephemeral=True)
            self.stop()

    # ====================== HELPERS ======================
    async def _parse_datetime(self, value) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

        value_str = str(value).strip()
        formats = [
            "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S",
            "%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S",
            "%m/%d/%y %H:%M", "%m/%d/%y %H:%M:%S"
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(value_str, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None

    def _normalize_key(self, name: str) -> str:
        """Create a consistent key from event name for matching."""
        return str(name).strip().lower()

    async def _create_event(self, guild: discord.Guild, data: Dict, row_num: int) -> Optional[discord.ScheduledEvent]:
        name = str(data.get("Name", "")).strip()
        if not name:
            return None

        start_time = await self._parse_datetime(data.get("Start"))
        if not start_time:
            print(f"[ExcelEvents] Row {row_num}: Invalid Start time")
            return None

        end_time = await self._parse_datetime(data.get("End"))
        description = str(data.get("Description", "")).strip()[:1000] or None

        event_type = str(data.get("Type", "")).strip().lower()
        location = str(data.get("Location", "")).strip() or None
        channel_id_input = data.get("ChannelID")

        channel = None
        event_location = None
        entity_type = discord.EntityType.voice  # default

        if event_type == "external" and location:
            entity_type = discord.EntityType.external
            event_location = location
        elif event_type == "stage" and channel_id_input:
            entity_type = discord.EntityType.stage
            try:
                ch_id = int(str(channel_id_input).strip())
                channel = guild.get_channel(ch_id)
            except:
                pass
        else:  # voice or default
            entity_type = discord.EntityType.voice
            if channel_id_input:
                try:
                    ch_id = int(str(channel_id_input).strip())
                    channel = guild.get_channel(ch_id)
                except:
                    pass

        if entity_type in (discord.EntityType.voice, discord.EntityType.stage) and not channel:
            print(f"[ExcelEvents] Row {row_num}: Voice/Stage event needs valid ChannelID")
            return None
        if entity_type == discord.EntityType.external and not event_location:
            print(f"[ExcelEvents] Row {row_num}: External event needs Location")
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
        except Exception as exc:
            print(f"[ExcelEvents] Row {row_num}: Failed to create '{name}': {exc}")
            return None

    # ====================== COMMANDS ======================
    @commands.group(name="excelevents", invoke_without_command=True)
    @commands.guild_only()
    @commands.admin_or_permissions(manage_events=True)
    async def excelevents(self, ctx: commands.Context):
        """Manage Discord events from Excel or pasted CSV."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @excelevents.command(name="upload")
    async def upload(self, ctx: commands.Context):
        """Upload an events.xlsx file."""
        if not ctx.message.attachments:
            await ctx.send("Attach an `.xlsx` file.")
            return
        # ... (same as before - save file)
        attachment = ctx.message.attachments[0]
        if not attachment.filename.lower().endswith((".xlsx", ".xls")):
            await ctx.send("Only `.xlsx` or `.xls` files supported.")
            return

        data_path: Path = data_manager.cog_data_path(self)
        data_path.mkdir(parents=True, exist_ok=True)
        file_path = data_path / "events.xlsx"

        await attachment.save(str(file_path))
        await ctx.send(f"✅ File saved!\nUse `{ctx.prefix}excelevents sync` or paste CSV with `{ctx.prefix}excelevents paste`.")

    @excelevents.command(name="paste")
    async def paste(self, ctx: commands.Context):
        """Paste raw CSV text directly (multi-line message)."""
        if not ctx.message.content.strip():
            await ctx.send("Please paste your CSV data after the command.")
            return

        # Extract text after the command
        lines = ctx.message.content.splitlines()
        csv_text = "\n".join(lines[1:]) if len(lines) > 1 else ""

        if not csv_text.strip():
            await ctx.send("No CSV data found. Paste your data like this:\n```csv\nType,Name,...\nvoice,My Event,...\n```")
            return

        data_path: Path = data_manager.cog_data_path(self)
        data_path.mkdir(parents=True, exist_ok=True)
        file_path = data_path / "events.xlsx"

        try:
            # Convert pasted CSV to Excel file
            reader = csv.DictReader(io.StringIO(csv_text))
            rows = list(reader)

            wb = openpyxl.Workbook()
            ws = wb.active
            if rows:
                ws.append(list(rows[0].keys()))
                for row in rows:
                    ws.append(list(row.values()))

            wb.save(file_path)
            await ctx.send(f"✅ CSV pasted and saved as Excel!\nUse `{ctx.prefix}excelevents sync` to process.")
        except Exception as e:
            await ctx.send(f"❌ Failed to parse CSV: {e}")

    @excelevents.command(name="sync")
    async def sync(self, ctx: commands.Context):
        """Sync events from the uploaded Excel (or pasted CSV)."""
        data_path = data_manager.cog_data_path(self)
        file_path = data_path / "events.xlsx"

        if not file_path.exists():
            await ctx.send("No events file found. Use `upload` or `paste` first.")
            return

        await ctx.send("🔄 Syncing events...")

        try:
            wb = openpyxl.load_workbook(file_path, data_only=True)
            ws = wb.active
            headers = [str(cell.value).strip() if cell.value else "" for cell in next(ws.iter_rows(min_row=1, max_row=1))]
            mappings: Dict[str, int] = await self.config.guild(ctx.guild).event_mappings()
            new_mappings = {}
            active_keys = set()
            row_num = 1
            processed = 0

            for row in ws.iter_rows(min_row=2, values_only=True):
                row_num += 1
                if not row or all(v is None for v in row):
                    continue

                data = {headers[i]: row[i] for i in range(min(len(headers), len(row))) if i < len(headers) and headers[i]}

                name = str(data.get("Name", "")).strip()
                if not name:
                    continue

                key = self._normalize_key(name)
                active_keys.add(key)

                # Update or create
                if key in mappings:
                    try:
                        event = await ctx.guild.fetch_scheduled_event(mappings[key])
                        start_time = await self._parse_datetime(data.get("Start"))
                        end_time = await self._parse_datetime(data.get("End"))
                        await event.edit(
                            name=name,
                            description=str(data.get("Description", "") or "")[:1000] or None,
                            start_time=start_time,
                            end_time=end_time,
                        )
                        await asyncio.sleep(1.5)
                        new_mappings[key] = event.id
                        processed += 1
                        continue
                    except:
                        pass

                new_event = await self._create_event(ctx.guild, data, row_num)
                if new_event:
                    new_mappings[key] = new_event.id
                    processed += 1

            # Delete old events
            deleted = 0
            for old_key, old_id in list(mappings.items()):
                if old_key not in active_keys:
                    try:
                        event = await ctx.guild.fetch_scheduled_event(old_id)
                        await event.delete()
                        await asyncio.sleep(1.5)
                        deleted += 1
                    except:
                        pass

            await self.config.guild(ctx.guild).event_mappings.set(new_mappings)

            await ctx.send(f"✅ **Sync done!**\n• Processed: **{processed}**\n• Active now: **{len(new_mappings)}**\n• Deleted: **{deleted}**")

        except Exception as e:
            await ctx.send(f"❌ Sync failed: {type(e).__name__}: {e}")

    # list, delete, clear, clearfile commands remain the same as previous version
    # (copy them from the last working version if needed)

    @excelevents.command(name="list")
    async def list_events(self, ctx: commands.Context):
        """List managed events."""
        mappings = await self.config.guild(ctx.guild).event_mappings()
        if not mappings:
            await ctx.send("No managed events.")
            return
        lines = ["**Managed Events:**"]
        for key, eid in mappings.items():
            try:
                event = await ctx.guild.fetch_scheduled_event(eid)
                lines.append(f"• `{key}` → **{event.name}** — {event.status.name}")
            except:
                lines.append(f"• `{key}` → (missing)")
        await ctx.send("\n".join(lines[:20]))

    # ... (add clear, clearfile, delete if you want them - they are unchanged)

    def cog_unload(self):
        pass
