# cogs/inactivepurge/inactivepurge.py

from datetime import datetime, timezone
import asyncio

import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.commands import Context


class InactivePurge(commands.Cog):
    """List and kick members who never sent a message (tracked after load)."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)
        self.config.register_member(messages=0)
        self.config.register_guild(tracking_enabled=False)  # off by default

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return
        if not await self.config.guild(message.guild).tracking_enabled():
            return
        try:
            count = await self.config.member(message.author).messages()
            await self.config.member(message.author).messages.set(count + 1)
        except Exception:
            pass

    @commands.hybrid_command(name="inactive", description="List inactive members + option to purge")
    @commands.guild_only()
    @commands.admin_or_permissions(kick_members=True)
    async def inactive(self, ctx: Context):
        guild = ctx.guild

        try:
            data = await self.config.all_members(guild)
        except Exception as exc:
            await ctx.send("Could not load member data. Try again later.")
            return

        inactive = [
            m for m in guild.members
            if not m.bot and (data.get(m.id) or {}).get("messages", 0) == 0
        ]

        if not inactive:
            await ctx.send("No members with zero tracked messages found.")
            return

        inactive.sort(key=lambda m: m.joined_at or datetime(1900, 1, 1, tzinfo=timezone.utc))

        # Create paginated view using reactions
        view = ReactionPaginator(ctx, inactive, self)
        try:
            msg = await ctx.send(embed=view.embed(0))
            await view.start(msg)
        except discord.HTTPException as exc:
            await ctx.send("Failed to send panel. Check permissions.")
            return

    @commands.hybrid_command(name="inactivetracking", description="Toggle message counting on/off")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def inactivetracking(self, ctx: Context, enable: bool):
        await self.config.guild(ctx.guild).tracking_enabled.set(enable)
        await ctx.send(f"Tracking is now **{'ON' if enable else 'OFF'}**.")


class ReactionPaginator:

    def __init__(self, ctx: Context, members: list[discord.Member], cog: InactivePurge):
        self.ctx = ctx
        self.members = members
        self.cog = cog
        self.page = 0
        self.per_page = 12
        self.total_pages = (len(members) + self.per_page - 1) // self.per_page
        self.msg: discord.Message = None
        self.owner_id = ctx.author.id

    def embed(self, page: int) -> discord.Embed:
        start = page * self.per_page
        end = start + self.per_page
        chunk = self.members[start:end]

        lines = []
        for i, m in enumerate(chunk, start + 1):
            joined = m.joined_at.strftime("%Y-%m-%d") if m.joined_at else "?"
            lines.append(f"{i:2d}. {m.mention}  •  joined {joined}")

        embed = discord.Embed(
            title=f"Inactive members (0 messages) — {len(self.members)} total",
            description="\n".join(lines) or "No members on this page.",
            color=discord.Color.dark_red(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(
            text=f"Page {page+1}/{self.total_pages}  •  {self.ctx.author} • Purge kicks everyone shown"
        )
        if self.ctx.guild.icon:
            embed.set_thumbnail(url=self.ctx.guild.icon.url)

        return embed

    async def start(self, message: discord.Message):
        self.msg = message

        try:
            await message.add_reaction("◀️")
            await message.add_reaction("▶️")
            await asyncio.sleep(0.4)
            await message.add_reaction("📋")
            await asyncio.sleep(0.4)
            await message.add_reaction("❌")
        except discord.HTTPException:
            await message.channel.send("Could not add reactions (missing permission?).", delete_after=20)
            return

        while True:
            try:
                reaction, user = await self.ctx.bot.wait_for(
                    "reaction_add",
                    check=self._check_reaction,
                    timeout=1800
                )
            except asyncio.TimeoutError:
                try:
                    await message.clear_reactions()
                except:
                    pass
                try:
                    await message.edit(content="Panel closed (timeout).", embed=None, view=None)
                except:
                    pass
                break

            emoji = str(reaction.emoji)

            if emoji == "◀️" and self.page > 0:
                self.page -= 1
                await self._edit_embed()

            elif emoji == "▶️" and self.page < self.total_pages - 1:
                self.page += 1
                await self._edit_embed()

            elif emoji == "📋":
                await self._purge_all()

            elif emoji == "❌":
                try:
                    await message.clear_reactions()
                    await message.edit(content="Panel closed.", embed=None)
                except:
                    pass
                break

    def _check_reaction(self, reaction: discord.Reaction, user: discord.User):
        if user.bot:
            return False
        if reaction.message.id != self.msg.id:
            return False
        if user.id != self.owner_id:
            return False
        return str(reaction.emoji) in ("◀️", "▶️", "📋", "❌")

    async def _edit_embed(self):
        if not self.msg:
            return
        try:
            await self.msg.edit(embed=self.embed(self.page))
        except discord.NotFound:
            pass
        except Exception as exc:
            print(f"Embed edit failed: {exc}")

    async def _purge_all(self):
        if not self.msg:
            return

        confirm_msg = await self.ctx.send(
            embed=discord.Embed(
                description="**Are you sure?**\nThis will kick **all** listed members.\nReply with `yes` within 30 seconds.",
                color=discord.Color.orange()
            )
        )

        def check(m):
            return m.author.id == self.owner_id and m.channel.id == confirm_msg.channel.id and m.content.lower() == "yes"

        try:
            await self.ctx.bot.wait_for("message", check=check, timeout=30)
        except asyncio.TimeoutError:
            await confirm_msg.edit(content="Cancelled (timeout).", embed=None)
            return

        await confirm_msg.edit(content="Starting purge...", embed=None)

        kicked = 0
        failed = 0
        total = len(self.members)

        for i, member in enumerate(self.members, 1):
            try:
                await member.kick(reason="Purge inactive (0 messages)")
                await self.cog.config.member(member).clear()
                kicked += 1
            except Exception:
                failed += 1

            await asyncio.sleep(0.7)  # generous delay to avoid rate limits

            if i % 5 == 0:
                await confirm_msg.edit(content=f"Purging… {i}/{total} • kicked {kicked} • failed {failed}")

        await confirm_msg.edit(
            content=f"**Purge finished**\nKicked: **{kicked}**\nFailed: **{failed}**",
            embed=None
        )

        # Update list after purge
        self.members = []
        self.total_pages = 1
        self.page = 0
        await self._edit_embed()


async def setup(bot: Red):
    await bot.add_cog(InactivePurge(bot))
