"""
CleanupUI Cog for Red-DiscordBot

Provides a staff-only interactive panel using Discord Components V2 (Containers)
to perform message cleanup actions similar to the built-in Cleanup cog.
"""

import logging
import asyncio
import time
from typing import Optional, Callable

import discord
from discord import ui
from redbot.core import commands, Config
from redbot.core.bot import Red

log = logging.getLogger("red.cleanupui")


class CleanupModal(ui.Modal):
    """Generic modal for collecting cleanup parameters.
    When Slow Mode is active, also collects and verifies the tool password.
    """

    def __init__(
        self,
        title: str,
        view: "CleanupPanelView",
        action: str,
        fields: list[tuple[str, str, bool, int]],
        require_password: bool = False,
    ):
        super().__init__(title=title)
        self.view = view
        self.action = action
        self.require_password = require_password
        self.field_data = {}

        for label, placeholder, required, max_length in fields:
            text_input = ui.TextInput(
                label=label,
                placeholder=placeholder,
                required=required,
                max_length=max_length,
                style=discord.TextStyle.short,
            )
            self.add_item(text_input)
            setattr(self, f"input_{label.replace(' ', '_').lower()}", text_input)

        if require_password:
            password_input = ui.TextInput(
                label="Tool Password",
                placeholder="Unique CleanupUI password (not a personal password)",
                required=True,
                max_length=100,
                style=discord.TextStyle.short,
            )
            self.add_item(password_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        values = {}
        password_attempt = None
        for item in self.children:
            if isinstance(item, ui.TextInput):
                if item.label == "Tool Password":
                    password_attempt = item.value.strip() if item.value else None
                else:
                    key = item.label.replace(" ", "_").lower()
                    values[key] = item.value.strip() if item.value else None

        # Verify password if required
        if self.require_password:
            guild = interaction.guild
            if not guild:
                await interaction.response.send_message("Guild only.", ephemeral=True)
                return
            stored = await self.view.cog.config.guild(guild).password()
            if not stored:
                await interaction.response.send_message(
                    "No Slow Mode password has been set for this server.\n"
                    "An administrator must use `[p]setcleanuppassword` first.",
                    ephemeral=True,
                )
                return
            if password_attempt != stored:
                await interaction.response.send_message(
                    "Incorrect tool password. Slow Mode action cancelled.",
                    ephemeral=True,
                )
                return

        await interaction.response.defer(ephemeral=True)
        try:
            result = await self.view.perform_action(interaction, self.action, values)
            await interaction.followup.send(result, ephemeral=True)
        except Exception as e:
            log.exception("Cleanup action failed")
            await interaction.followup.send(
                f"An error occurred while performing the cleanup: {e}", ephemeral=True
            )


class CleanupPanelView(ui.LayoutView):
    """Main interactive panel using Containers."""

    def __init__(self, cog: "CleanupUI", ctx: commands.Context, timeout: float = 300.0):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.ctx = ctx
        self.bot = ctx.bot
        self.target_channel: Optional[discord.TextChannel] = None
        self.delete_pinned = False
        self.slow_mode = False
        self.message: Optional[discord.Message] = None

        # Build the UI
        self._build_ui()

    def _build_ui(self) -> None:
        # Header text
        header = ui.TextDisplay(
            "# 🧹 Staff Cleanup Panel\n"
            "Select a cleanup action below. Most actions will ask for a number of messages.\n"
            "**Normal mode:** Bulk delete (fast, only works on messages < 14 days old).\n"
            "**Slow mode:** Deletes one-by-one (works on any age). Requires tool password. Max 5 minutes."
        )

        # Channel selector section
        channel_row = ui.ActionRow()
        channel_select = ui.ChannelSelect(
            placeholder="Select target channel (optional - defaults to current)",
            channel_types=[discord.ChannelType.text, discord.ChannelType.news],
            min_values=0,
            max_values=1,
            custom_id="cleanup_channel_select",
        )
        channel_row.add_item(channel_select)

        # Action buttons - Row 1
        row1 = ui.ActionRow()
        row1.add_item(self._make_button("Messages", "messages", discord.ButtonStyle.primary))
        row1.add_item(self._make_button("Bot Msgs", "bot", discord.ButtonStyle.primary))
        row1.add_item(self._make_button("User", "user", discord.ButtonStyle.primary))
        row1.add_item(self._make_button("Text", "text", discord.ButtonStyle.primary))

        # Action buttons - Row 2
        row2 = ui.ActionRow()
        row2.add_item(self._make_button("Spam", "spam", discord.ButtonStyle.secondary))
        row2.add_item(self._make_button("Self", "self", discord.ButtonStyle.secondary))
        row2.add_item(self._make_button("After", "after", discord.ButtonStyle.secondary))
        row2.add_item(self._make_button("Before", "before", discord.ButtonStyle.secondary))

        # Action buttons - Row 3
        row3 = ui.ActionRow()
        row3.add_item(self._make_button("Between", "between", discord.ButtonStyle.secondary))
        toggle_btn = ui.Button(
            label="Delete Pinned: Off",
            style=discord.ButtonStyle.danger,
            custom_id="cleanup_toggle_pinned",
        )
        toggle_btn.callback = self.toggle_pinned
        row3.add_item(toggle_btn)

        slow_btn = ui.Button(
            label="Slow Mode: Off",
            style=discord.ButtonStyle.secondary,
            custom_id="cleanup_toggle_slow",
        )
        slow_btn.callback = self.toggle_slow
        row3.add_item(slow_btn)

        # After building rows, assign callbacks properly
        for row in (row1, row2, row3):
            for item in row.children:
                if isinstance(item, ui.Button) and item.custom_id and item.custom_id.startswith("cleanup_action_"):
                    action = item.custom_id.replace("cleanup_action_", "")
                    item.callback = self._create_action_callback(action)

        # Info text
        info = ui.TextDisplay(
            "-# Staff only • Components V2 Containers • "
            "Slow Mode: ~2.5s delay between deletes • Auto-stops after 5 minutes."
        )

        # Container
        container = ui.Container(
            header,
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            channel_row,
            ui.Separator(),
            row1,
            row2,
            row3,
            ui.Separator(spacing=discord.SeparatorSpacing.small),
            info,
            accent_color=discord.Color.red(),
        )
        self.add_item(container)

        # Store select for callback
        self.channel_select = channel_select
        channel_select.callback = self.on_channel_select

    def _make_button(self, label: str, action: str, style: discord.ButtonStyle) -> ui.Button:
        btn = ui.Button(label=label, style=style, custom_id=f"cleanup_action_{action}")
        # We'll handle all in a central way via interaction_check or by assigning properly
        return btn

    async def on_channel_select(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return
        values = interaction.data.get("values", [])
        if values:
            channel_id = int(values[0])
            self.target_channel = interaction.guild.get_channel(channel_id)
            await interaction.response.send_message(
                f"Target channel set to {self.target_channel.mention}.", ephemeral=True
            )
        else:
            self.target_channel = None
            await interaction.response.send_message(
                "Target channel cleared. Will use current channel.", ephemeral=True
            )

    async def toggle_pinned(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return
        self.delete_pinned = not self.delete_pinned
        button.label = f"Delete Pinned: {'On' if self.delete_pinned else 'Off'}"
        button.style = discord.ButtonStyle.success if self.delete_pinned else discord.ButtonStyle.danger
        await interaction.response.edit_message(view=self)

    async def toggle_slow(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return
        self.slow_mode = not self.slow_mode
        button.label = f"Slow Mode: {'On' if self.slow_mode else 'Off'}"
        button.style = discord.ButtonStyle.success if self.slow_mode else discord.ButtonStyle.secondary
        await interaction.response.edit_message(view=self)

    def _create_action_callback(self, action: str):
        async def callback(interaction: discord.Interaction):
            await self.on_action_button(interaction, None, action)
        return callback

    async def on_action_button(
        self, interaction: discord.Interaction, button: ui.Button, action: str
    ) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return

        # Determine modal fields based on action
        fields = []
        title = f"Cleanup: {action.title()}"

        if action in ("messages", "bot", "spam", "self"):
            fields = [
                ("Number", "How many messages to check/delete (1-1000)", True, 5),
            ]
            if action == "self":
                fields.append(("Pattern (optional)", "Text to match (leave blank for all)", False, 100))
        elif action == "user":
            fields = [
                ("User ID or Mention", "User ID, mention, or name", True, 100),
                ("Number", "How many messages (1-1000)", True, 5),
            ]
        elif action == "text":
            fields = [
                ("Text", "Text to search for in messages", True, 200),
                ("Number", "How many messages (1-1000)", True, 5),
            ]
        elif action == "after":
            fields = [("Message ID", "ID of the message to start after", True, 20)]
        elif action == "before":
            fields = [
                ("Message ID", "ID of the message to start before", True, 20),
                ("Number", "How many messages (1-1000)", True, 5),
            ]
        elif action == "between":
            fields = [
                ("Older Message ID", "ID of the older message", True, 20),
                ("Newer Message ID", "ID of the newer message", True, 20),
            ]
        else:
            await interaction.response.send_message("Unknown action.", ephemeral=True)
            return

        modal = CleanupModal(title, self, action, fields, require_password=self.slow_mode)
        await interaction.response.send_modal(modal)

    async def perform_action(
        self, interaction: discord.Interaction, action: str, values: dict
    ) -> str:
        channel = self.target_channel or interaction.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return "Invalid target channel."

        # Permission checks
        if not channel.permissions_for(interaction.guild.me).manage_messages:
            return "I don't have Manage Messages permission in the target channel."
        if not channel.permissions_for(interaction.user).manage_messages:
            return "You don't have Manage Messages permission in the target channel."

        delete_pinned = self.delete_pinned
        number = 100  # default

        try:
            if action == "messages":
                number = int(values.get("number", 100))
                check = lambda m: True
                deleted = await self._purge(channel, check, number, delete_pinned)
                return f"Deleted {deleted} message(s) in {channel.mention}."

            elif action == "bot":
                number = int(values.get("number", 100))
                check = lambda m: m.author.bot
                deleted = await self._purge(channel, check, number, delete_pinned)
                return f"Deleted {deleted} bot message(s) in {channel.mention}."

            elif action == "user":
                user_input = values.get("user_id_or_mention", "")
                number = int(values.get("number", 100))
                user = await self._resolve_user(interaction.guild, user_input)
                if not user:
                    return "Could not resolve the user. Try a user ID or mention."
                check = lambda m: m.author.id == user.id
                deleted = await self._purge(channel, check, number, delete_pinned)
                return f"Deleted {deleted} message(s) from {user} in {channel.mention}."

            elif action == "text":
                text = values.get("text", "")
                number = int(values.get("number", 100))
                if not text:
                    return "Text is required."
                check = lambda m: text.lower() in (m.content or "").lower()
                deleted = await self._purge(channel, check, number, delete_pinned)
                return f"Deleted {deleted} message(s) containing '{text}' in {channel.mention}."

            elif action == "spam":
                number = int(values.get("number", 50))
                deleted = await self._cleanup_spam(channel, number, delete_pinned)
                return f"Removed {deleted} duplicate/spam message(s) in {channel.mention}."

            elif action == "self":
                number = int(values.get("number", 100))
                pattern = values.get("pattern_(optional)", "") or ""
                check = lambda m: m.author.id == self.bot.user.id and (
                    not pattern or pattern.lower() in (m.content or "").lower()
                )
                deleted = await self._purge(channel, check, number, delete_pinned)
                return f"Deleted {deleted} of my message(s) in {channel.mention}."

            elif action == "after":
                msg_id = int(values.get("message_id", 0))
                after_msg = await channel.fetch_message(msg_id)
                check = lambda m: True
                deleted = await self._purge(
                    channel, check, limit=1000, delete_pinned=delete_pinned, after=after_msg
                )
                return f"Deleted {deleted} message(s) after the specified message in {channel.mention}."

            elif action == "before":
                msg_id = int(values.get("message_id", 0))
                number = int(values.get("number", 100))
                before_msg = await channel.fetch_message(msg_id)
                check = lambda m: True
                deleted = await self._purge(
                    channel, check, number, delete_pinned, before=before_msg
                )
                return f"Deleted {deleted} message(s) before the specified message in {channel.mention}."

            elif action == "between":
                older_id = int(values.get("older_message_id", 0))
                newer_id = int(values.get("newer_message_id", 0))
                older = await channel.fetch_message(older_id)
                newer = await channel.fetch_message(newer_id)
                check = lambda m: True
                deleted = await self._purge(
                    channel, check, limit=1000, delete_pinned=delete_pinned, after=older, before=newer
                )
                return f"Deleted {deleted} message(s) between the two messages in {channel.mention}."

            else:
                return "Unknown action."

        except ValueError:
            return "Invalid number or message ID. Please use integers."
        except discord.NotFound:
            return "Could not find one of the specified messages."
        except discord.Forbidden:
            return "Missing permissions to delete messages."
        except Exception as e:
            log.exception("Action error")
            return f"Error: {type(e).__name__}: {e}"

    async def _purge(
        self,
        channel: discord.abc.Messageable,
        check: Callable[[discord.Message], bool],
        limit: int = 100,
        delete_pinned: bool = False,
        after: Optional[discord.Message] = None,
        before: Optional[discord.Message] = None,
    ) -> int:
        def full_check(m: discord.Message) -> bool:
            if not delete_pinned and m.pinned:
                return False
            return check(m)

        # Use slow mode or normal purge
        if self.slow_mode:
            deleted = await self._slow_purge(channel, full_check, limit, after, before)
        else:
            deleted = await channel.purge(
                limit=min(limit, 1000),
                check=full_check,
                after=after,
                before=before,
                bulk=True,
                oldest_first=False,
            )
            deleted = len(deleted)
        return deleted

    async def _slow_purge(
        self,
        channel: discord.abc.Messageable,
        check: Callable[[discord.Message], bool],
        limit: int = 100,
        after: Optional[discord.Message] = None,
        before: Optional[discord.Message] = None,
    ) -> int:
        """Delete messages one-by-one with a moderate delay. Works on messages of any age.
        Automatically stops after 5 minutes to prevent endless runs.
        """
        deleted = 0
        delay = 2.5  # moderate delay to stay safely under rate limits
        max_duration = 300  # 5 minutes hard timeout
        start_time = time.monotonic()

        async for message in channel.history(limit=min(limit, 1000), after=after, before=before, oldest_first=False):
            # Smart timeout check
            if time.monotonic() - start_time >= max_duration:
                log.info("Slow purge stopped: 5-minute timeout reached.")
                break
            if deleted >= limit:
                break
            if check(message):
                try:
                    await message.delete()
                    deleted += 1
                    # Sleep, but also respect remaining time
                    remaining = max_duration - (time.monotonic() - start_time)
                    await asyncio.sleep(min(delay, max(0.5, remaining)))
                except discord.HTTPException as e:
                    if e.status == 429:
                        # Rate limited — wait longer and retry once
                        await asyncio.sleep(5)
                        try:
                            await message.delete()
                            deleted += 1
                            await asyncio.sleep(delay)
                        except discord.HTTPException:
                            log.warning(f"Failed to delete message {message.id} after rate limit retry")
                    else:
                        log.warning(f"Failed to delete message {message.id}: {e}")
                except discord.Forbidden:
                    log.warning(f"Forbidden deleting message {message.id}")
                    break

        return deleted

    async def _cleanup_spam(
        self, channel: discord.TextChannel, limit: int, delete_pinned: bool
    ) -> int:
        """Simple spam cleaner: remove exact duplicate messages, keep one."""
        messages = []
        async for msg in channel.history(limit=min(limit, 200)):
            if not delete_pinned and msg.pinned:
                continue
            messages.append(msg)

        seen = {}
        to_delete = []
        for msg in messages:
            key = (msg.author.id, msg.content)
            if key in seen:
                to_delete.append(msg)
            else:
                seen[key] = msg

        if not to_delete:
            return 0

        # Delete in chunks of 100, preferring bulk for recent ones
        deleted_count = 0
        for i in range(0, len(to_delete), 100):
            chunk = to_delete[i : i + 100]
            try:
                await channel.delete_messages(chunk)
                deleted_count += len(chunk)
            except discord.HTTPException:
                # Fall back to individual deletes for older messages
                for m in chunk:
                    try:
                        await m.delete()
                        deleted_count += 1
                    except discord.HTTPException:
                        pass
        return deleted_count

    async def _resolve_user(self, guild: discord.Guild, user_input: str) -> Optional[discord.Member]:
        # Try mention
        if user_input.startswith("<@") and user_input.endswith(">"):
            user_id = int(user_input[2:-1].replace("!", ""))
            return guild.get_member(user_id)
        # Try ID
        if user_input.isdigit():
            return guild.get_member(int(user_input))
        # Try name
        return discord.utils.find(
            lambda m: m.name.lower() == user_input.lower()
            or m.display_name.lower() == user_input.lower(),
            guild.members,
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Extra safety
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "Only the staff member who opened this panel can use it.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self) -> None:
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass


class CleanupUI(commands.Cog):
    """Staff Cleanup Panel using Discord Containers (Components V2)."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)
        self.config.register_guild(password=None)

    @commands.command(name="setcleanuppassword", aliases=["cleanupuipassword", "setslowpassword"])
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def set_cleanup_password(self, ctx: commands.Context):
        """Set or update the password required for Slow Mode (past 14-day cleans).

        Only server owners or administrators can use this.
        The bot will DM you to set a unique tool password (do not use a personal password).
        """
        if not (ctx.author.id == ctx.guild.owner_id or ctx.author.guild_permissions.administrator):
            await ctx.send("Only the server owner or administrators can set the CleanupUI password.")
            return

        try:
            dm_channel = await ctx.author.create_dm()
            await dm_channel.send(
                "**CleanupUI Slow Mode Password Setup**\n\n"
                "Please reply to this DM with a password **unique to this tool**.\n"
                "**Do not use a personal password.**\n\n"
                "This password will be required to use Slow Mode (cleaning messages older than 14 days).\n"
                "You have 90 seconds to reply."
            )

            def check(m: discord.Message) -> bool:
                return m.channel.id == dm_channel.id and m.author.id == ctx.author.id

            reply = await self.bot.wait_for("message", check=check, timeout=90)
            password = reply.content.strip()

            if len(password) < 4:
                await dm_channel.send("Password must be at least 4 characters. Please try the command again.")
                return
            if len(password) > 100:
                await dm_channel.send("Password too long. Please try the command again.")
                return

            await self.config.guild(ctx.guild).password.set(password)
            await dm_channel.send(
                "✅ Password set successfully for this server.\n"
                "Remember: this is only for the CleanupUI Slow Mode tool."
            )
            await ctx.send("CleanupUI Slow Mode password has been set via DM.")
        except asyncio.TimeoutError:
            await ctx.send("Timed out waiting for your reply in DMs. Please try again.")
        except discord.Forbidden:
            await ctx.send(
                "I couldn't send you a DM. Please enable DMs from server members and try again."
            )
        except Exception as e:
            log.exception("Error setting password")
            await ctx.send(f"An error occurred: {e}")

    @commands.command(name="cleanuppanel", aliases=["cleanui", "cleanupui"])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, send_messages=True, embed_links=True)
    async def cleanup_panel(self, ctx: commands.Context):
        """Open the staff cleanup control panel.

        This uses Discord's new Components V2 Containers for a clean interface.
        Only members with Manage Messages can use this.
        """
        view = CleanupPanelView(self, ctx)
        # Send as Components V2 message (LayoutView automatically sets the flag)
        msg = await ctx.send(
            view=view,
            # No content/embeds when using LayoutView
        )
        view.message = msg
        # Delete the command message to keep channel clean (optional)
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_ready(self):
        # Optional: log that cog is ready
        log.info("CleanupUI cog loaded and ready.")

