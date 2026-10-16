"""Extra maker actions that do not consume the editor's five component rows."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord

WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}
MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}
# Abbreviations and city names mapped to IANA zones so daylight saving is handled.
ZONE_ALIASES = {
    "utc": "UTC", "gmt": "UTC",
    "est": "America/New_York", "edt": "America/New_York",
    "cst": "America/Chicago", "cdt": "America/Chicago",
    "mst": "America/Denver", "mdt": "America/Denver",
    "pst": "America/Los_Angeles", "pdt": "America/Los_Angeles",
    "bst": "Europe/London", "cet": "Europe/Paris", "cest": "Europe/Paris",
    "jst": "Asia/Tokyo", "kst": "Asia/Seoul", "ist": "Asia/Kolkata",
    "aest": "Australia/Sydney", "aedt": "Australia/Sydney",
    "nzst": "Pacific/Auckland", "nzdt": "Pacific/Auckland",
    "new york": "America/New_York", "nyc": "America/New_York",
    "chicago": "America/Chicago", "denver": "America/Denver",
    "los angeles": "America/Los_Angeles", "la": "America/Los_Angeles",
    "toronto": "America/Toronto", "vancouver": "America/Vancouver",
    "mexico city": "America/Mexico_City", "sao paulo": "America/Sao_Paulo",
    "buenos aires": "America/Argentina/Buenos_Aires",
    "london": "Europe/London", "paris": "Europe/Paris", "berlin": "Europe/Berlin",
    "madrid": "Europe/Madrid", "rome": "Europe/Rome", "amsterdam": "Europe/Amsterdam",
    "moscow": "Europe/Moscow", "dublin": "Europe/Dublin",
    "tokyo": "Asia/Tokyo", "seoul": "Asia/Seoul", "shanghai": "Asia/Shanghai",
    "beijing": "Asia/Shanghai", "hong kong": "Asia/Hong_Kong",
    "singapore": "Asia/Singapore", "dubai": "Asia/Dubai",
    "mumbai": "Asia/Kolkata", "india": "Asia/Kolkata",
    "sydney": "Australia/Sydney", "melbourne": "Australia/Melbourne",
    "auckland": "Pacific/Auckland",
    "johannesburg": "Africa/Johannesburg", "cairo": "Africa/Cairo", "lagos": "Africa/Lagos",
}


def is_placeholder(embed: discord.Embed) -> bool:
    title = (embed.title or "").strip()
    description = (embed.description or "").strip()
    return title in {"", "Untitled embed", "Welcome to the embed builder"} and (
        not description or description.startswith("Use the buttons below") or description.startswith("- Use the grey buttons")
    )
    """Accept IANA names, city names, common abbreviations, or a numeric offset."""
    text = (raw or "").strip()
    if not text or text.lower() in {"skip", "utc"}:
        return timezone.utc
    key = text.lower().replace("_", " ")
    if key in ZONE_ALIASES:
        return ZoneInfo(ZONE_ALIASES[key])
    candidate = text.replace(" ", "_")
    try:
        return ZoneInfo(candidate)
    except ZoneInfoNotFoundError:
        pass
    offset = text.lower().replace("utc", "").replace("gmt", "").strip()
    match = re.fullmatch(r"([+-])(\d{1,2})(?::?(\d{2}))?", offset)
    if match:
        sign = 1 if match.group(1) == "+" else -1
        hours = int(match.group(2))
        minutes = int(match.group(3) or 0)
        return timezone(timedelta(hours=sign * hours, minutes=sign * minutes))
    raise ValueError(
        "Use an IANA zone like `Europe/Paris` or `Asia/Tokyo`, a city like `London`, "
        "or an offset like `+5:30`."
    )


def _clock(text: str) -> Optional[tuple[int, int]]:
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text.strip().lower())
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    ampm = match.group(3)
    if ampm == "pm" and hour < 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def _at(day: datetime, clock: tuple[int, int], zone: timezone) -> datetime:
    local = day.astimezone(zone).replace(hour=clock[0], minute=clock[1], second=0, microsecond=0)
    return local.astimezone(timezone.utc)


def parse_friendly(raw: str, *, now: Optional[datetime] = None, base: Optional[datetime] = None, zone: timezone = timezone.utc) -> datetime:
    """Read a normal reply like 'tomorrow 7pm', 'friday 8:30pm', or 'in 2 hours'."""
    now = now or datetime.now(timezone.utc)
    text = re.sub(r"\s+", " ", (raw or "").strip().lower()).replace(" at ", " ")
    if text in {"now", "asap"}:
        return now + timedelta(minutes=5)
    match = re.fullmatch(r"(?:in\s+|\+)?(\d+)\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)", text)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        anchor = base or now
        if unit.startswith("m"):
            return anchor + timedelta(minutes=amount)
        if unit.startswith("h"):
            return anchor + timedelta(hours=amount)
        return anchor + timedelta(days=amount)
    if text == "tomorrow":
        return _at(now + timedelta(days=1), (19, 0), zone)
    if text.startswith("tomorrow "):
        clock = _clock(text[9:])
        if clock:
            return _at(now + timedelta(days=1), clock, zone)
    if text.startswith("today "):
        clock = _clock(text[6:])
        if clock:
            return _at(now, clock, zone)
    for name, index in WEEKDAYS.items():
        if text == name or text.startswith(name + " "):
            days = (index - now.weekday()) % 7 or 7
            day = now + timedelta(days=days)
            rest = text[len(name):].strip()
            return _at(day, _clock(rest) or (19, 0), zone)
    clock = _clock(text)
    if clock:
        moment = _at(now, clock, zone)
        if moment <= now:
            moment = _at(now + timedelta(days=1), clock, zone)
        return moment
    match = re.fullmatch(r"([a-z]+)\s+(\d{1,2})(?:\s+(.+))?", text)
    if match and match.group(1) in MONTHS:
        month = MONTHS[match.group(1)]
        day = int(match.group(2))
        year = now.year
        try:
            candidate = datetime(year, month, day, tzinfo=zone)
        except ValueError as exc:
            raise ValueError("That date is not valid.") from exc
        if candidate.date() < now.astimezone(zone).date():
            candidate = candidate.replace(year=year + 1)
        return _at(candidate, _clock(match.group(3) or "") or (19, 0), zone)
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?(?:\s+(.+))?", text)
    if match:
        month, day = int(match.group(1)), int(match.group(2))
        year = int(match.group(3) or now.year)
        if year < 100:
            year += 2000
        try:
            candidate = datetime(year, month, day, tzinfo=zone)
        except ValueError as exc:
            raise ValueError("That date is not valid.") from exc
        return _at(candidate, _clock(match.group(4) or "") or (19, 0), zone)
    try:
        moment = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            "Try `tomorrow 7pm`, `friday 8:30pm`, `in 2 hours`, or `10/20 7pm`."
        ) from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=zone)
    return moment.astimezone(timezone.utc)


class StoreNameModal(discord.ui.Modal, title="Save embed"):
    name = discord.ui.TextInput(label="Stored name", max_length=50, required=True)
    scope = discord.ui.TextInput(label="Global? yes/no", max_length=5, default="no", required=False)

    def __init__(self, cog, editor, *, update: bool):
        super().__init__(title="Update stored embed" if update else "Store embed")
        self.cog = cog
        self.editor = editor
        self.update = update

    async def on_submit(self, interaction: discord.Interaction) -> None:
        name = str(self.name.value).strip()
        global_level = str(self.scope.value or "").strip().lower() in {"1", "yes", "y", "true", "on"}
        if global_level and not await self.cog.bot.is_owner(interaction.user):
            await interaction.response.send_message("Only the bot owner can save global embeds.", ephemeral=True)
            return
        if self.update and not await self.cog.store.get(interaction.guild, name, global_level):
            await interaction.response.send_message(f"`{name}` is not stored yet. Use Store instead.", ephemeral=True)
            return
        embed = getattr(self.editor, "embed", None)
        if embed is None:
            await interaction.response.send_message("This builder has no embed to save.", ephemeral=True)
            return
        try:
            await self.cog.store.save(
                guild=interaction.guild,
                name=name,
                embed=embed,
                author_id=interaction.user.id,
                global_level=global_level,
                content=getattr(self.editor, "content", None),
            )
        except Exception as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        verb = "Updated" if self.update else "Stored"
        await interaction.response.send_message(f"{verb} `{name}`.", ephemeral=True)


class EventSetup:
    """Ask for an event one reply at a time. No ISO required."""

    def __init__(self, cog, interaction: discord.Interaction, embed: discord.Embed, channel, content: Optional[str] = None):
        self.cog = cog
        self.interaction = interaction
        self.embed = embed
        self.channel = channel or interaction.channel
        self.content = content
        self.user = interaction.user
        self.guild = interaction.guild

    async def ask(self, prompt: str) -> Optional[discord.Message]:
        await self.channel.send(prompt)
        try:
            return await self.cog.bot.wait_for("message", check=self._check, timeout=180)
        except asyncio.TimeoutError:
            await self.channel.send("Timed out. Event setup cancelled.")
            return None

    def _check(self, message: discord.Message) -> bool:
        return message.author.id == self.user.id and message.channel.id == getattr(self.channel, "id", None)

    async def run(self) -> None:
        await self.interaction.response.send_message(
            "Starting server event setup. Reply in this channel. Say `cancel` at any question to stop.",
            ephemeral=True,
        )
        name_msg = await self.ask(
            f"**1/6 Name.** Reply with the event name, or `title` to use `{self.embed.title or 'the embed title'}`."
        )
        if name_msg is None or name_msg.content.lower() == "cancel":
            return
        name = (self.embed.title or "Event") if name_msg.content.lower() == "title" else name_msg.content.strip()
        if not name:
            await self.channel.send("A name is required. Setup cancelled.")
            return

        zone_msg = await self.ask(
            "**2/6 Timezone.** Reply with an IANA zone (`Europe/Paris`, `Asia/Tokyo`), "
            "a city (`London`, `Sydney`), or an offset (`+5:30`). `skip` uses UTC."
        )
        if zone_msg is None or zone_msg.content.lower() == "cancel":
            return
        try:
            zone = parse_zone(zone_msg.content)
        except ValueError as error:
            await self.channel.send(str(error))
            return

        start_msg = await self.ask(
            "**3/6 Start.** Reply like `tomorrow 7pm`, `friday 8:30pm`, `in 2 hours`, or `10/20 7pm`."
        )
        if start_msg is None or start_msg.content.lower() == "cancel":
            return
        try:
            start = parse_friendly(start_msg.content, zone=zone)
        except ValueError as error:
            await self.channel.send(str(error))
            return

        end_msg = await self.ask("**4/6 End.** Reply with a time, `in 2 hours`, or `skip` for one hour after the start.")
        if end_msg is None or end_msg.content.lower() == "cancel":
            return
        if end_msg.content.lower() in {"skip", "1 hour", "1h"}:
            end = start + timedelta(hours=1)
        else:
            try:
                end = parse_friendly(end_msg.content, base=start, zone=zone)
            except ValueError as error:
                await self.channel.send(str(error))
                return
        if end <= start:
            end = start + timedelta(hours=1)

        loc_msg = await self.ask("**5/6 Location.** Reply with a place, or `skip` for Discord.")
        if loc_msg is None or loc_msg.content.lower() == "cancel":
            return
        location = "Discord" if loc_msg.content.lower() == "skip" else loc_msg.content.strip()[:100]

        image_msg = await self.ask("**6/6 Cover image.** Upload an image, or reply `skip`.")
        if image_msg is None or image_msg.content.lower() == "cancel":
            return
        image = None
        if image_msg.content.lower() != "skip":
            image = await self._image_bytes(image_msg)
            if image is None:
                await self.channel.send("No image found on that message. Continuing without a cover.")

        post_msg = await self.ask("Post the embed too? Reply with a channel mention, `here`, or `skip`.")
        if post_msg is None or post_msg.content.lower() == "cancel":
            return
        destination = self._channel(post_msg.content)

        confirm = await self.ask(
            "Are you sure you want to create this event? Have you finished editing the embed above first? Reply `yes` to create it, or `no` to cancel."
        )
        if confirm is None or confirm.content.lower() not in {"yes", "y"}:
            await self.channel.send("Event setup cancelled. Edit the embed, then click Server event again.")
            return

        try:
            event = await self.cog.create_server_event(
                self.guild,
                name=name[:100],
                description=(self.embed.description or "")[:1000] or None,
                start=start,
                end=end,
                location=location or "Discord",
                image=image,
            )
        except discord.Forbidden:
            await self.channel.send("I need Manage Events to create a server event.")
            return
        except discord.HTTPException as error:
            await self.channel.send(f"Discord rejected the event: {error}")
            return

        if destination is not None:
            try:
                await destination.send(embed=self.embed, content=self.content or None)
            except discord.HTTPException as error:
                await self.channel.send(f"Event created, but the embed could not be posted: {error}")
        await self.channel.send(f"Server event created: {event.url}")

    async def _image_bytes(self, message: discord.Message) -> Optional[bytes]:
        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith("image/"):
                return await attachment.read()
        if message.attachments:
            return await message.attachments[0].read()
        return None

    def _channel(self, text: str):
        raw = text.strip()
        if raw.lower() in {"skip", "no", "none"}:
            return None
        if raw.lower() in {"here", "this"}:
            return self.channel
        match = re.search(r"<#(\d+)>", raw)
        if match:
            return self.guild.get_channel(int(match.group(1)))
        return discord.utils.get(self.guild.text_channels, name=raw.lstrip("#"))


class EventUpdate:
    """Apply the current embed to an existing server event, then optionally change the time."""

    def __init__(self, cog, interaction: discord.Interaction, embed: discord.Embed, channel):
        self.cog = cog
        self.interaction = interaction
        self.embed = embed
        self.channel = channel or interaction.channel
        self.user = interaction.user
        self.guild = interaction.guild

    def _check(self, message: discord.Message) -> bool:
        return message.author.id == self.user.id and message.channel.id == getattr(self.channel, "id", None)

    async def ask(self, prompt: str) -> Optional[discord.Message]:
        await self.channel.send(prompt)
        try:
            return await self.cog.bot.wait_for("message", check=self._check, timeout=180)
        except asyncio.TimeoutError:
            await self.channel.send("Timed out. Event update cancelled.")
            return None

    async def _event(self, raw: str) -> Optional[discord.ScheduledEvent]:
        text = raw.strip()
        if text.lower().startswith("event:"):
            text = text.split(":", 1)[1].strip()
        match = re.search(r"discord(?:app)?\.com/events/\d+/(\d+)", text)
        event_id = int(match.group(1)) if match else int(text) if text.isdigit() else None
        if event_id is not None:
            return await self.guild.fetch_scheduled_event(event_id)
        events = await self.guild.fetch_scheduled_events()
        found = [event for event in events if event.name.lower() == text.lower()]
        return found[0] if len(found) == 1 else None

    async def run(self) -> None:
        await self.interaction.response.send_message(
            "Updating a server event. Reply in this channel. Say `cancel` to stop.",
            ephemeral=True,
        )
        target = await self.ask("Which event? Reply with its link, ID, or exact name.")
        if target is None or target.content.lower() == "cancel":
            return
        try:
            event = await self._event(target.content)
        except discord.NotFound:
            await self.channel.send("That server event was not found.")
            return
        if event is None:
            await self.channel.send("No single event matched that. Use the event link.")
            return
        kwargs = {}
        if self.embed.title:
            kwargs["name"] = self.embed.title[:100]
        if self.embed.description:
            kwargs["description"] = self.embed.description[:1000]
        image_url = getattr(getattr(self.embed, "image", None), "url", None)
        if image_url and getattr(self.cog, "session", None) is not None:
            try:
                async with self.cog.session.get(image_url) as response:
                    if response.status == 200:
                        kwargs["image"] = await response.read()
            except Exception:
                pass
        change = await self.ask("Change the time or location too? Reply `yes` or `no`.")
        if change is None or change.content.lower() == "cancel":
            return
        if change.content.lower() in {"yes", "y"}:
            zone_msg = await self.ask("Timezone? IANA name, city, or offset. `skip` uses UTC.")
            if zone_msg is None or zone_msg.content.lower() == "cancel":
                return
            try:
                zone = parse_zone(zone_msg.content)
            except ValueError as error:
                await self.channel.send(str(error))
                return
            start_msg = await self.ask("New start? `tomorrow 7pm`, `friday 8pm`, `in 2 hours`, or `skip` to keep it.")
            if start_msg is None or start_msg.content.lower() == "cancel":
                return
            if start_msg.content.lower() != "skip":
                try:
                    kwargs["start_time"] = parse_friendly(start_msg.content, zone=zone)
                except ValueError as error:
                    await self.channel.send(str(error))
                    return
            end_msg = await self.ask("New end? A time, `in 2 hours`, or `skip` to keep it.")
            if end_msg is None or end_msg.content.lower() == "cancel":
                return
            if end_msg.content.lower() != "skip":
                try:
                    anchor = kwargs.get("start_time") or event.start_time
                    kwargs["end_time"] = parse_friendly(end_msg.content, base=anchor, zone=zone)
                except ValueError as error:
                    await self.channel.send(str(error))
                    return
            loc_msg = await self.ask("New location? Reply with a place, or `skip` to keep it.")
            if loc_msg is None or loc_msg.content.lower() == "cancel":
                return
            if loc_msg.content.lower() != "skip":
                kwargs["location"] = loc_msg.content.strip()[:100]
        if not kwargs:
            await self.channel.send("Nothing to update.")
            return
        confirm = await self.ask(
            "Are you sure you want to update this event? Have you finished editing the embed above first? Reply `yes` to update it, or `no` to cancel."
        )
        if confirm is None or confirm.content.lower() not in {"yes", "y"}:
            await self.channel.send("Event update cancelled.")
            return
        try:
            updated = await event.edit(**kwargs)
        except discord.Forbidden:
            await self.channel.send("I need Manage Events to update that server event.")
            return
        except discord.HTTPException as error:
            await self.channel.send(f"Discord rejected the event update: {error}")
            return
        await self.channel.send(f"Updated server event: {updated.url}")


class MakerActions(discord.ui.View):
    def __init__(self, cog, editor, channel: Optional[discord.abc.Messageable]):
        super().__init__(timeout=600)
        self.cog = cog
        self.editor = editor
        self.channel = channel

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        author = getattr(self.editor, "context", None)
        expected = getattr(author, "author", None)
        if expected and interaction.user.id != expected.id:
            await interaction.response.send_message("This builder is not yours.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Store", style=discord.ButtonStyle.success)
    async def store(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(StoreNameModal(self.cog, self.editor, update=False))

    @discord.ui.button(label="Update stored", style=discord.ButtonStyle.primary)
    async def update(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(StoreNameModal(self.cog, self.editor, update=True))

    @discord.ui.button(label="Event embed", style=discord.ButtonStyle.secondary)
    async def event_embed(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = getattr(self.editor, "embed", None)
        if embed is None:
            await interaction.response.send_message("No embed to post.", ephemeral=True)
            return
        dest = self.channel or interaction.channel
        try:
            await dest.send(embed=embed, content=getattr(self.editor, "content", None))
        except discord.HTTPException as error:
            await interaction.response.send_message(f"Could not post the event embed: {error}", ephemeral=True)
            return
        await interaction.response.send_message("Event embed posted.", ephemeral=True)

    @discord.ui.button(label="Update event", style=discord.ButtonStyle.secondary)
    async def update_event(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = getattr(self.editor, "embed", None)
        if embed is None or interaction.guild is None:
            await interaction.response.send_message("Server events can only be updated in a guild.", ephemeral=True)
            return
        await EventUpdate(self.cog, interaction, embed, self.channel or interaction.channel).run()

    @discord.ui.button(label="Server event", style=discord.ButtonStyle.secondary)
    async def server_event(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = getattr(self.editor, "embed", None)
        if embed is None or interaction.guild is None:
            await interaction.response.send_message("Server events can only be created in a guild.", ephemeral=True)
            return
        await EventSetup(
            self.cog,
            interaction,
            embed,
            self.channel or interaction.channel,
            getattr(self.editor, "content", None),
        ).run()
