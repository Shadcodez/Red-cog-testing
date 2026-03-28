import asyncio
import discord
from redbot.core import commands, Config, data_manager
from redbot.core.bot import Red
import openpyxl
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict

class ExcelEvents(commands.Cog):
    """Manage Discord Scheduled Events from an Excel sheet."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=9876543210987654321, force_registration=True
        )
        defaults_guild = {
            "event_mappings": {},   # {unique_key: discord_event_id}
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
        """Create a new scheduled event (compatible with current Red/discord.py)."""
        name = str(data.get("Name", "Unnamed Event")).strip()
        if not name:
            return None

        start_time = await self._parse_datetime(data.get("Start"))
        if not start_time:
            return None

        end_time = await self._parse_datetime(data.get("End"))
        description = str(data.get("Description", "")).strip()[:1000] or None
        location = str(data.get("Location", "")).strip() or None

        channel_input = data.get("Channel")

        # External event (Somewhere Else)
        if location and not channel_input:
            entity_type = discord.EntityType.external
            channel = None
            # location is passed directly (no entity_metadata)
        else:
            # Voice or Stage event
            entity_type = discord.EntityType.voice
            channel = None
            if channel_input:
                try:
                    ch_id = int(str(channel_input).strip())
                    channel = guild.get_channel(ch_id)
                except ValueError:
                    for ch in guild.channels:
                        if ch.name and ch.name.lower() == str(channel_input).lower().strip():
                            channel = ch
                            break

        try:
            event = await guild.create_scheduled_event(
                name=name,
                description=description,
                start_time=start_time,
                end_time=end_time,
                entity_type=entity_type,
                channel=channel,
                location=location if entity_type == discord.EntityType.external else None,
                privacy_level=discord.PrivacyLevel.guild_only,
            )
            await asyncio.sleep(1.5)  # Rate-limit protection
            return event
        except discord.HTTPException as exc:
            print(f"[ExcelEvents] Failed to create event '{name}': {exc}")
            return None

    # ====================== MAIN GROUP ======================
    @commands.group(name="excelevents", invoke_without_command=True)
    @commands.guild_only()
    @commands.admin_or_permissions(manage_events=True)
    async def excelevents(self, ctx: commands.Context):
        """Manage Discord events from an Excel sheet."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @excelevents.command(name="upload")
    async def upload(self, ctx: commands.Context):
        """
        Upload a new events.xlsx file (replaces any existing file).

        **Copy & paste this directly into Excel** (first row = headers):
        ```csv
        Key,Name,Description,Start,End,Location,Channel
        weekly-meeting,Team Sync,Weekly team catch-up,2026-04-05 14:00,2026-04-05 15:00,,General Voice
        conference,Big Conference,Annual company event,2026-05-10 09:00,2026-05-10 17:00,New York Convention Center,
        ```
        - `Key` = unique identifier (required)
        - `Start` = required
        - Use `Location` for external events ("Somewhere Else")
        - `Channel` = voice/stage name or ID
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
        await ctx.send(f"✅ Events sheet uploaded!\nUse `{ctx.prefix}excelevents sync` to process it.")

    @excelevents.command(name="sync")
    async def sync(self, ctx: commands.Context):
        """Sync Discord events with the uploaded Excel sheet (create/update/delete)."""
        data_path = data_manager.cog_data_path(self)
        file_path = data_path / "events.xlsx"

        if not file_path.exists():
            await ctx.send("No `events.xlsx` found. Use `[p]excelevents upload` first.")
            return

        await ctx.send("🔄 Syncing events (with rate-limit protection)...")

        try:
            wb = openpyxl.load_workbook(file_path, data_only=True)
            ws = wb.active
            if not ws:
                await ctx.send("❌ Could not read the worksheet.")
                return

            headers = [str(cell.value).strip() if cell.value is not None else "" for cell in next(ws.iter_rows(min_row=1, max_row=1))]
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

                data = {headers[i]: row[i] for i in range(min(len(headers), len(row))) if i < len(headers) and headers[i]}

                key = str(data.get("Key", "")).strip()
                if not key:
                    continue
                active_keys.add(key)

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
                        await asyncio.sleep(1.5)
                        new_mappings[key] = event.id
                        continue
                    except (discord.NotFound, discord.HTTPException):
                        pass

                new_event = await self._create_event(ctx.guild, data)
                if new_event:
                    new_mappings[key] = new_event.id

            # Delete events no longer in sheet
            deleted = 0
            for old_key, old_id in list(mappings.items()):
                if old_key not in active_keys:
                    try:
                        event = await ctx.guild.fetch_scheduled_event(old_id)
                        await event.delete()
                        await asyncio.sleep(1.5)
                        deleted += 1
                    except (discord.NotFound, discord.HTTPException):
                        pass

            await self.config.guild(ctx.guild).event_mappings.set(new_mappings)
            await self.config.guild(ctx.guild).last_synced.set(datetime.utcnow().isoformat())

            await ctx.send(f"✅ **Sync completed!**\n• Active events: **{len(new_mappings)}**\n• Deleted: **{deleted}**")

        except Exception as e:
            await ctx.send(f"❌ Sync failed: `{type(e).__name__}: {e}`")
            print(f"[ExcelEvents] Error in guild {ctx.guild.id}: {e}")

    @excelevents.command(name="list")
    async def list_events(self, ctx: commands.Context):
        """List all events managed by this cog."""
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

        await ctx.send("\n".join(lines[:25]))

    @excelevents.command(name="delete")
    async def delete(self, ctx: commands.Context, key: str):
        """Delete a specific event by its Key."""
        key = key.strip()
        mappings: Dict[str, int] = await self.config.guild(ctx.guild).event_mappings()

        if key not in mappings:
            await ctx.send(f"No managed event found with key `{key}`.")
            return

        async def do_delete():
            event_id = mappings[key]
            try:
                event = await ctx.guild.fetch_scheduled_event(event_id)
                await event.delete()
                await asyncio.sleep(1.5)
                await ctx.send(f"✅ Deleted event: **{event.name}** (Key: `{key}`)")
            except discord.NotFound:
                await ctx.send(f"Event with key `{key}` no longer exists on Discord.")
            except discord.HTTPException as e:
                await ctx.send(f"Failed to delete: {e}")
                return

            if key in mappings:
                del mappings[key]
                await self.config.guild(ctx.guild).event_mappings.set(mappings)

        view = self.ConfirmView(ctx, f"delete key `{key}`", do_delete)
        await ctx.send(f"⚠️ Are you sure you want to delete the event with key `{key}`?", view=view)

    @excelevents.command(name="clear")
    async def clear(self, ctx: commands.Context):
        """Clear ALL managed event mappings (does NOT delete the Excel file)."""
        async def do_clear():
            await self.config.guild(ctx.guild).event_mappings.set({})
            await ctx.send("✅ All event mappings have been cleared.")

        view = self.ConfirmView(ctx, "clear all mappings", do_clear)
        await ctx.send("⚠️ **This will clear ALL event mappings.** Continue?", view=view)

    @excelevents.command(name="clearfile")
    async def clearfile(self, ctx: commands.Context):
        """Delete the uploaded events.xlsx file (mappings are untouched)."""
        data_path = data_manager.cog_data_path(self)
        file_path = data_path / "events.xlsx"

        if not file_path.exists():
            await ctx.send("No Excel file to delete.")
            return

        async def do_clearfile():
            if file_path.exists():
                file_path.unlink()
            await ctx.send("✅ Excel file has been deleted. You can upload a new one with `excelevents upload`.")

        view = self.ConfirmView(ctx, "delete the Excel file", do_clearfile)
        await ctx.send("⚠️ **This will delete the events.xlsx file.** Continue?", view=view)

    def cog_unload(self):
        pass
