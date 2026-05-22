import discord
import re
from datetime import timedelta, datetime
from urllib.parse import urlparse
from redbot.core import commands, Config, checks
from redbot.core.bot import Red
from redbot.core.utils.chat import wait_for_reaction  # fallback if needed
import aiohttp  # Red usually has this

class ScamAlertView(discord.ui.View):
    def __init__(self, cog, member: discord.Member, reason: str, alert_msg_id: int = None):
        super().__init__(timeout=7200)  # 2 hours
        self.cog = cog
        self.member = member
        self.reason = reason
        self.alert_msg_id = alert_msg_id

    @discord.ui.button(label="Apply Punishment", style=discord.ButtonStyle.danger)
    async def apply(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("You need Manage Messages permission.", ephemeral=True)
            return

        await self.cog.apply_punishment(interaction.guild, self.member, interaction.user, self.reason)
        await interaction.response.edit_message(content=f"✅ Punishment applied to {self.member} by {interaction.user}.", view=None)

    @discord.ui.button(label="Dismiss", style=discord.ButtonStyle.secondary)
    async def dismiss(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("You need Manage Messages permission.", ephemeral=True)
            return
        await interaction.response.edit_message(content=f"❌ Alert dismissed by {interaction.user} (no action taken).", view=None)

class ScamDetector(commands.Cog):
    """Modern scam detection with staff review & punishment."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)
        self.config.register_guild(
            enabled=False,
            alert_channel=None,
            punishment_type="timeout",   # "timeout" or "role"
            duration_days=7,
            scam_role=None,
            delete_message=True,
            keywords=["free nitro", "nitro gift", "claim nitro", "discord gift", "limited nitro", "you've been reported", "account suspension", "free gift", "claim now", "steam gift"],
            bad_domains=[],
            image_threshold=4,
            min_account_age_days=0,      # 0 = disabled
            immune_roles=[]
        )

    @commands.group()
    @checks.admin_or_permissions(manage_guild=True)
    async def scamset(self, ctx):
        """Configure ScamDetector."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @scamset.command()
    async def enable(self, ctx, state: bool = True):
        """Enable/disable the cog."""
        await self.config.guild(ctx.guild).enabled.set(state)
        await ctx.send(f"Scam detection is now {'enabled' if state else 'disabled'}.")

    @scamset.command()
    async def alertchannel(self, ctx, channel: discord.TextChannel = None):
        """Set the staff alert channel."""
        if channel:
            await self.config.guild(ctx.guild).alert_channel.set(channel.id)
            await ctx.send(f"Alert channel set to {channel.mention}.")
        else:
            await self.config.guild(ctx.guild).alert_channel.set(None)
            await ctx.send("Alert channel cleared.")

    @scamset.command()
    async def punishment(self, ctx, ptype: str = "timeout", days: int = 7):
        """Set punishment type: timeout or role + duration in days."""
        if ptype.lower() not in ["timeout", "role"]:
            return await ctx.send("Type must be `timeout` or `role`.")
        await self.config.guild(ctx.guild).punishment_type.set(ptype.lower())
        await self.config.guild(ctx.guild).duration_days.set(days)
        await ctx.send(f"Punishment set to {ptype} for {days} days.")

    @scamset.command()
    async def scamrole(self, ctx, role: discord.Role = None):
        """Set the role to add when using role punishment (optional)."""
        await self.config.guild(ctx.guild).scam_role.set(role.id if role else None)
        await ctx.send(f"Scam role {'set to ' + role.name if role else 'cleared'}.")

    @scamset.command()
    async def keywords(self, ctx, *, action: str):
        """Manage keywords: add <word>, remove <word>, list, clear"""
        cfg = self.config.guild(ctx.guild)
        current = await cfg.keywords()
        parts = action.split(maxsplit=1)
        cmd = parts[0].lower()

        if cmd == "add" and len(parts) > 1:
            word = parts[1].lower()
            if word not in current:
                current.append(word)
                await cfg.keywords.set(current)
                await ctx.send(f"Added keyword: {word}")
            else:
                await ctx.send("Already exists.")
        elif cmd == "remove" and len(parts) > 1:
            word = parts[1].lower()
            if word in current:
                current.remove(word)
                await cfg.keywords.set(current)
                await ctx.send(f"Removed keyword: {word}")
            else:
                await ctx.send("Not found.")
        elif cmd == "list":
            await ctx.send(f"Current keywords: {', '.join(current) if current else 'None'}")
        elif cmd == "clear":
            await cfg.keywords.set([])
            await ctx.send("Keywords cleared.")
        else:
            await ctx.send("Usage: keywords add/remove <word> | list | clear")

    @scamset.command()
    async def updatedomains(self, ctx):
        """Update bad domains from public scam list (recommended)."""
        async with aiohttp.ClientSession() as session:
            async with session.get("https://raw.githubusercontent.com/Discord-AntiScam/scam-links/main/list.txt") as resp:
                if resp.status != 200:
                    return await ctx.send("Failed to fetch domain list.")
                text = await resp.text()
                domains = [line.strip().lower() for line in text.splitlines() if line.strip() and not line.startswith("#")]
                await self.config.guild(ctx.guild).bad_domains.set(list(set(domains)))  # dedupe
                await ctx.send(f"✅ Updated with \~{len(domains)} bad domains.")

    @scamset.command()
    async def imagethreshold(self, ctx, number: int):
        """Set minimum images in one message to flag (0 to disable)."""
        await self.config.guild(ctx.guild).image_threshold.set(number)
        await ctx.send(f"Image threshold set to {number}.")

    # Add more settings as needed (min_account_age_days, immune_roles, etc.)

    @commands.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def scamundo(self, ctx, member: discord.Member):
        """Undo the last scam punishment for a user."""
        cfg = self.config.guild(ctx.guild)
        ptype = await cfg.punishment_type()
        if ptype == "timeout":
            try:
                await member.edit(timed_out_until=None)
                await ctx.send(f"✅ Timeout removed from {member}.")
            except Exception as e:
                await ctx.send(f"Failed: {e}")
        else:
            role_id = await cfg.scam_role()
            if role_id:
                role = ctx.guild.get_role(role_id)
                if role and role in member.roles:
                    await member.remove_roles(role)
                    await ctx.send(f"✅ Scam role removed from {member}.")
                else:
                    await ctx.send("User does not have the scam role.")
            else:
                await ctx.send("No scam role configured.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        guild_cfg = self.config.guild(message.guild)
        if not await guild_cfg.enabled():
            return

        # Immunity
        immune_roles = await guild_cfg.immune_roles()
        if any(role.id in immune_roles for role in message.author.roles):
            return

        # Detection
        is_scam, reason = await self.detect_scam(message, guild_cfg)
        if not is_scam:
            return

        # Delete message?
        if await guild_cfg.delete_message():
            try:
                await message.delete()
            except:
                pass

        # Send alert
        alert_channel_id = await guild_cfg.alert_channel()
        if not alert_channel_id:
            return
        channel = message.guild.get_channel(alert_channel_id)
        if not channel:
            return

        embed = discord.Embed(title="🚨 Potential Scam Detected", color=discord.Color.red())
        embed.add_field(name="User", value=message.author.mention, inline=False)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Content", value=message.content[:500] or "No text", inline=False)
        embed.add_field(name="Jump Link", value=message.jump_url, inline=False)
        embed.timestamp = datetime.utcnow()

        view = ScamAlertView(self, message.author, reason)
        await channel.send(embed=embed, view=view)

    async def detect_scam(self, message: discord.Message, cfg):
        content = message.content.lower()
        reasons = []

        # Keywords
        keywords = await cfg.keywords()
        if any(kw in content for kw in keywords):
            reasons.append("Keyword match")

        # Bad domains / links
        bad_domains = await cfg.bad_domains()
        urls = re.findall(r'(https?://[^\s]+)', message.content)
        for url in urls:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain and any(bad in domain for bad in bad_domains):
                reasons.append("Bad domain")

        # Image spam (common in crypto scams)
        image_count = sum(1 for a in message.attachments if a.content_type and a.content_type.startswith("image/"))
        threshold = await cfg.image_threshold()
        if threshold > 0 and image_count >= threshold:
            reasons.append(f"{image_count} images")

        # New account check
        min_age = await cfg.min_account_age_days()
        if min_age > 0:
            age_days = (discord.utils.utcnow() - message.author.created_at).days
            if age_days < min_age:
                reasons.append("New account")

        if reasons:
            return True, " + ".join(reasons)
        return False, None

    async def apply_punishment(self, guild: discord.Guild, member: discord.Member, staff: discord.Member, reason: str):
        cfg = self.config.guild(guild)
        ptype = await cfg.punishment_type()
        days = await cfg.duration_days()

        try:
            if ptype == "timeout":
                until = discord.utils.utcnow() + timedelta(days=days)
                await member.edit(timed_out_until=until, reason=f"Scam detected: {reason} (staff: {staff})")
            else:
                role_id = await cfg.scam_role()
                if role_id:
                    role = guild.get_role(role_id)
                    if role:
                        await member.add_roles(role, reason=f"Scam detected: {reason} (staff: {staff})")
        except Exception as e:
            # Could log error here
            pass

    # Optional: add more config commands for immune_roles, min_account_age_days, etc.
