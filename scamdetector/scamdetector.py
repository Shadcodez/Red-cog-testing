import discord
import re
from datetime import timedelta
from urllib.parse import urlparse
from redbot.core import commands, Config, checks
from redbot.core.bot import Red
import aiohttp

class ScamAlertView(discord.ui.View):
    def __init__(self, cog, member: discord.Member, reason: str, punishment_enabled: bool = True):
        super().__init__(timeout=7200)  # 2 hours
        self.cog = cog
        self.member = member
        self.reason = reason
        self.punishment_enabled = punishment_enabled

        if self.punishment_enabled:
            self.add_item(discord.ui.Button(
                label="Apply Punishment",
                style=discord.ButtonStyle.danger,
                custom_id="apply_punishment"
            ))
        self.add_item(discord.ui.Button(
            label="Dismiss",
            style=discord.ButtonStyle.secondary,
            custom_id="dismiss_alert"
        ))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("You need Manage Messages permission.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Apply Punishment", style=discord.ButtonStyle.danger, custom_id="apply_punishment")
    async def apply(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.apply_punishment(interaction.guild, self.member, interaction.user, self.reason)
        await interaction.response.edit_message(
            content=f"✅ Punishment applied to {self.member} by {interaction.user}.", 
            view=None
        )

    @discord.ui.button(label="Dismiss", style=discord.ButtonStyle.secondary, custom_id="dismiss_alert")
    async def dismiss(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content=f"❌ Alert dismissed by {interaction.user} (no action taken).", 
            view=None
        )

class ScamDetector(commands.Cog):
    """Modern scam detection with staff review & configurable punishment."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)
        self.config.register_guild(
            enabled=False,
            alert_channel=None,
            punishment_type="timeout",
            duration_days=7,
            scam_role=None,
            punishment_enabled=True,      # Allows notification-only mode
            delete_message=True,
            keywords=["free nitro", "nitro gift", "claim nitro", "discord gift", "limited nitro", "you've been reported", "account suspension", "free gift", "claim now", "steam gift"],
            bad_domains=[],
            image_threshold=4,
            min_account_age_days=0,       # 0 = disabled (off by default)
            immune_roles=[]
        )

    @commands.group(invoke_without_command=True)
    @checks.admin_or_permissions(manage_guild=True)
    async def scam(self, ctx):
        """Main scam detection command group."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @scam.command()
    async def settings(self, ctx):
        """Show current ScamDetector configuration."""
        cfg = await self.config.guild(ctx.guild).all()
        embed = discord.Embed(title="ScamDetector Settings", color=discord.Color.blue())
        embed.add_field(name="Enabled", value=cfg["enabled"], inline=True)
        embed.add_field(name="Notification Only (No Punishment)", value=not cfg["punishment_enabled"], inline=True)
        embed.add_field(name="Delete Message", value=cfg["delete_message"], inline=True)
        embed.add_field(name="Punishment Type", value=cfg["punishment_type"], inline=True)
        embed.add_field(name="Duration", value=f"{cfg['duration_days']} days", inline=True)
        embed.add_field(name="Image Threshold", value=cfg["image_threshold"], inline=True)
        embed.add_field(name="Min Account Age", value=f"{cfg['min_account_age_days']} days (0 = off)", inline=True)
        embed.add_field(name="Alert Channel", value=f"<#{cfg['alert_channel']}>" if cfg["alert_channel"] else "Not set", inline=False)
        embed.add_field(name="Immune Roles", value=len(cfg["immune_roles"]), inline=True)
        await ctx.send(embed=embed)

    @scam.command()
    async def enable(self, ctx, state: bool = True):
        """Enable or disable scam detection."""
        await self.config.guild(ctx.guild).enabled.set(state)
        await ctx.send(f"Scam detection is now {'enabled' if state else 'disabled'}.")

    @scam.command()
    async def alertchannel(self, ctx, channel: discord.TextChannel = None):
        """Set the staff alert channel (or clear it)."""
        await self.config.guild(ctx.guild).alert_channel.set(channel.id if channel else None)
        await ctx.send(f"Alert channel {'set to ' + channel.mention if channel else 'cleared'}.")

    @scam.command()
    async def punishment(self, ctx, ptype: str = "timeout", days: int = 7):
        """Set punishment type: timeout or role + duration in days."""
        if ptype.lower() not in ["timeout", "role"]:
            return await ctx.send("Type must be `timeout` or `role`.")
        await self.config.guild(ctx.guild).punishment_type.set(ptype.lower())
        await self.config.guild(ctx.guild).duration_days.set(days)
        await ctx.send(f"Punishment set to **{ptype}** for **{days}** days.")

    @scam.command()
    async def punishmentenable(self, ctx, state: bool = True):
        """Enable or disable the punishment button (notification-only mode)."""
        await self.config.guild(ctx.guild).punishment_enabled.set(state)
        await ctx.send(f"Punishment button is now {'enabled' if state else 'disabled'} (notification-only mode).")

    @scam.command()
    async def scamrole(self, ctx, role: discord.Role = None):
        """Set the role to add when using role punishment."""
        await self.config.guild(ctx.guild).scam_role.set(role.id if role else None)
        await ctx.send(f"Scam role {'set to ' + role.name if role else 'cleared'}.")

    @scam.command()
    async def delete(self, ctx, state: bool = True):
        """Enable or disable automatic message deletion on detection."""
        await self.config.guild(ctx.guild).delete_message.set(state)
        await ctx.send(f"Message deletion on detection is now {'enabled' if state else 'disabled'}.")

    @scam.command()
    async def accountage(self, ctx, days: int):
        """Set minimum account age in days to flag as potential scam (0 to disable)."""
        if days < 0:
            days = 0
        await self.config.guild(ctx.guild).min_account_age_days.set(days)
        await ctx.send(f"Minimum account age set to **{days}** days (0 = disabled).")

    @scam.group(invoke_without_command=True)
    async def immunerole(self, ctx):
        """Manage immune roles (staff roles that will never trigger alerts)."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @immunerole.command(name="add")
    async def immunerole_add(self, ctx, role: discord.Role):
        """Add a role to the immune list."""
        async with self.config.guild(ctx.guild).immune_roles() as roles:
            if role.id not in roles:
                roles.append(role.id)
                await ctx.send(f"✅ {role.name} is now immune.")
            else:
                await ctx.send("Role is already immune.")

    @immunerole.command(name="remove")
    async def immunerole_remove(self, ctx, role: discord.Role):
        """Remove a role from the immune list."""
        async with self.config.guild(ctx.guild).immune_roles() as roles:
            if role.id in roles:
                roles.remove(role.id)
                await ctx.send(f"✅ {role.name} is no longer immune.")
            else:
                await ctx.send("Role was not in the immune list.")

    @immunerole.command(name="list")
    async def immunerole_list(self, ctx):
        """List all immune roles."""
        roles = await self.config.guild(ctx.guild).immune_roles()
        if not roles:
            return await ctx.send("No immune roles set.")
        role_mentions = [f"<@&{rid}>" for rid in roles if ctx.guild.get_role(rid)]
        await ctx.send(f"Immune roles: {', '.join(role_mentions) if role_mentions else 'None'}")

    @scam.command()
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
                await ctx.send(f"✅ Added: {word}")
            else:
                await ctx.send("Already in list.")
        elif cmd == "remove" and len(parts) > 1:
            word = parts[1].lower()
            if word in current:
                current.remove(word)
                await cfg.keywords.set(current)
                await ctx.send(f"✅ Removed: {word}")
            else:
                await ctx.send("Not found.")
        elif cmd == "list":
            await ctx.send(f"Current keywords: {', '.join(current) if current else 'None'}")
        elif cmd == "clear":
            await cfg.keywords.set([])
            await ctx.send("Keywords cleared.")
        else:
            await ctx.send_help(ctx.command)

    @scam.command()
    async def updatedomains(self, ctx):
        """Update bad domains from public scam list (highly recommended)."""
        async with aiohttp.ClientSession() as session:
            async with session.get("https://raw.githubusercontent.com/Discord-AntiScam/scam-links/main/list.txt") as resp:
                if resp.status != 200:
                    return await ctx.send("Failed to fetch domain list.")
                text = await resp.text()
                domains = [line.strip().lower() for line in text.splitlines() if line.strip() and not line.startswith("#")]
                await self.config.guild(ctx.guild).bad_domains.set(list(set(domains)))
                await ctx.send(f"✅ Updated with **{len(domains)}** bad domains.")

    @scam.command()
    async def imagethreshold(self, ctx, number: int):
        """Set image threshold (0 to disable)."""
        await self.config.guild(ctx.guild).image_threshold.set(number)
        await ctx.send(f"Image threshold set to **{number}**.")

    @scam.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def undo(self, ctx, member: discord.Member):
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

        # Automatic staff immunity (Manage Messages or higher)
        if message.author.guild_permissions.manage_messages:
            return

        # Configured immune roles
        if any(role.id in await guild_cfg.immune_roles() for role in message.author.roles):
            return

        is_scam, reason = await self.detect_scam(message, guild_cfg)
        if not is_scam:
            return

        # Delete message if enabled
        if await guild_cfg.delete_message():
            try:
                await message.delete()
            except:
                pass

        # Send staff alert
        alert_channel_id = await guild_cfg.alert_channel()
        if not alert_channel_id:
            return
        channel = message.guild.get_channel(alert_channel_id)
        if not channel:
            return

        punishment_enabled = await guild_cfg.punishment_enabled()

        embed = discord.Embed(title="🚨 Potential Scam Detected", color=discord.Color.red())
        embed.add_field(name="User", value=message.author.mention, inline=False)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Content", value=message.content[:500] or "No text", inline=False)
        embed.add_field(name="Jump Link", value=message.jump_url, inline=False)
        embed.timestamp = discord.utils.utcnow()

        if not punishment_enabled:
            embed.set_footer(text="Notification-only mode — punishment button disabled")

        view = ScamAlertView(self, message.author, reason, punishment_enabled=punishment_enabled)
        await channel.send(embed=embed, view=view)

    async def detect_scam(self, message: discord.Message, cfg):
        content = message.content.lower()
        reasons = []

        # Keywords
        if any(kw in content for kw in await cfg.keywords()):
            reasons.append("Keyword match")

        # Bad domains
        bad_domains = await cfg.bad_domains()
        urls = re.findall(r'(https?://[^\s]+)', message.content)
        for url in urls:
            domain = urlparse(url).netloc.lower()
            if domain and any(bad in domain for bad in bad_domains):
                reasons.append("Bad domain")

        # Image spam
        image_count = sum(1 for a in message.attachments if a.content_type and a.content_type.startswith("image/"))
        threshold = await cfg.image_threshold()
        if threshold > 0 and image_count >= threshold:
            reasons.append(f"{image_count} images")

        # Account age check
        min_age = await cfg.min_account_age_days()
        if min_age > 0:
            age_days = (discord.utils.utcnow() - message.author.created_at).days
            if age_days < min_age:
                reasons.append(f"New account (<{min_age} days)")

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
                await member.edit(timed_out_until=until, reason=f"Scam: {reason} (by {staff})")
            else:
                role_id = await cfg.scam_role()
                if role_id:
                    role = guild.get_role(role_id)
                    if role:
                        await member.add_roles(role, reason=f"Scam: {reason} (by {staff})")
        except Exception:
            pass
