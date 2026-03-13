import aiohttp
import urllib.parse
from typing import Dict, List, Optional
from datetime import datetime

import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box


class BraveSearch(commands.GroupCog, name="bravesearch"):
    """Premium Brave Search + AI Answers
    • Type `bravesearch` alone → native Red help menu
    • Type `bravesearch your question` or use aliases `brave` / `b` / `search`"""

    __author__ = "shadow using grok"
    __version__ = "2.3.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)
        self.config.register_global(api_key=None)
        self.config.register_guild(
            mode="web",          # "web" or "answers"
            error_channel=None,
        )
        self.conversations: Dict[int, List[Dict[str, str]]] = {}

    async def red_delete_data_for_user(self, **kwargs):
        pass

    # ====================== OWNER / ADMIN COMMANDS ======================
    @commands.is_owner()
    @commands.command(hidden=True)
    async def setbravekey(self, ctx: commands.Context, *, key: str = None):
        """Set Brave API key (owner only)."""
        if key is None:
            await ctx.send("Key is hidden.\nUse `[p]setbravekey YOUR_KEY` to set.")
            return
        await self.config.api_key.set(key.strip())
        await ctx.send("✅ Brave API key saved securely.")

    @commands.guild_only()
    @commands.guildowner_or_permissions(administrator=True)
    @commands.command()
    async def mode(self, ctx: commands.Context, mode: str):
        """Toggle mode: web or answers (admins + owner)."""
        mode = mode.lower().strip()
        if mode not in ("web", "answers"):
            await ctx.send("Please use `web` or `answers`.")
            return
        await self.config.guild(ctx.guild).mode.set(mode)
        await ctx.send(f"✅ BraveSearch mode is now **{mode.upper()}**.")

    @commands.guild_only()
    @commands.guildowner_or_permissions(administrator=True)
    @commands.command()
    async def errorchannel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Set error log channel (`none` to disable)."""
        if channel is None:
            await self.config.guild(ctx.guild).error_channel.set(None)
            await ctx.send("✅ Error logging disabled.")
            return
        await self.config.guild(ctx.guild).error_channel.set(channel.id)
        await ctx.send(f"✅ Errors will be logged to {channel.mention}.")

    @commands.guild_only()
    @commands.command()
    async def status(self, ctx: commands.Context):
        """Show current settings."""
        data = await self.config.guild(ctx.guild).all()
        mode = data["mode"].upper()
        ch = self.bot.get_channel(data["error_channel"]) if data["error_channel"] else None
        key_set = "✅ Set" if await self.config.api_key() else "❌ Not set"

        embed = discord.Embed(title="BraveSearch • Status", color=0x00AEEF)
        embed.add_field(name="Mode", value=mode, inline=True)
        embed.add_field(name="API Key", value=key_set, inline=True)
        embed.add_field(name="Error Channel", value=ch.mention if ch else "Disabled", inline=True)
        embed.set_footer(text="Powered by Brave")
        await ctx.send(embed=embed)

    # ====================== MAIN SEARCH (root command) ======================
    @commands.command(name="bravesearch", aliases=["brave", "b", "search"])
    @commands.cooldown(1, 30, commands.BucketType.user)
    @commands.guild_only()
    async def bravesearch(self, ctx: commands.Context, *, query: str = None):
        """bravesearch your question here
        • `bravesearch` alone shows this help menu
        • Aliases: brave, b, search"""
        if query is None:
            await ctx.send_help()          # Native Red help menu
            return

        query = query.strip()
        search_url = f"https://search.brave.com/search?q={urllib.parse.quote_plus(query)}"

        # ── Fancy Brave Search Embed (exactly as requested) ──
        embed = discord.Embed(
            title="🔍 Brave Search",
            description=query,
            color=0x00AEEF,                     # Official Brave cyan
            url=search_url,
            timestamp=datetime.utcnow(),
        )
        embed.set_thumbnail(url="https://brave.com/static-assets/images/brave-logo.png")
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        embed.set_footer(text="Real-time results • Independent index • Powered by Brave")
        await ctx.send(embed=embed)

        api_key = await self.config.api_key()
        if not api_key:
            return  # silent for regular users

        guild_data = await self.config.guild(ctx.guild).all()
        mode = guild_data.get("mode", "web")

        try:
            if mode == "web":
                await self._web_search(ctx, query, api_key)
            else:
                await self._answers_search(ctx, query, api_key)
        except Exception as e:
            await self._log_error(ctx.guild, f"Query: {query}\nError: {str(e)}")

    # ====================== WEB SEARCH MODE ======================
    async def _web_search(self, ctx: commands.Context, query: str, api_key: str):
        headers = {"X-Subscription-Token": api_key}
        params = {"q": query, "count": 9, "safesearch": "moderate"}

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as session:
            async with session.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers=headers, params=params
            ) as r:
                if r.status != 200:
                    raise Exception(f"Web API {r.status}")
                data = await r.json()

        embed = discord.Embed(title="Brave Web Results", color=0x00AEEF, url=f"https://search.brave.com/search?q={urllib.parse.quote_plus(query)}")
        embed.set_footer(text="Powered by Brave")
        for i, res in enumerate(data.get("results", [])[:8], 1):
            title = res.get("title", "Untitled")
            url = res.get("url", "#")
            desc = (res.get("description") or res.get("snippet") or "")[:280]
            embed.add_field(name=f"{i}. {title}", value=f"{desc}\n[Open]({url})", inline=False)

        await ctx.send(embed=embed)

    # ====================== ANSWERS MODE ======================
    async def _answers_search(self, ctx: commands.Context, query: str, api_key: str):
        thinking = await ctx.send("🤔 **Brave AI is thinking...**")
        history = [{"role": "user", "content": query}]

        try:
            answer = await self._get_ai_answer(history, api_key)
            await thinking.delete()

            msg = await ctx.send(
                f">>> **Brave AI Answer**\n\n{answer}\n\n"
                "*(Reply to continue • ❓ follow-up • 🗑️ clear)*"
            )
            await msg.add_reaction("❓")
            await msg.add_reaction("🗑️")
            self.conversations[msg.id] = history + [{"role": "assistant", "content": answer}]
        except Exception:
            await thinking.edit(content="⚠️ AI failed (logged privately).")
            raise

    async def _get_ai_answer(self, messages: List[Dict[str, str]], api_key: str) -> str:
        headers = {"X-Subscription-Token": api_key, "Content-Type": "application/json"}
        payload = {
            "model": "brave",
            "messages": messages,
            "stream": False,
            "max_tokens": 1500,
            "temperature": 0.7,
        }
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=70)) as session:
            async with session.post(
                "https://api.search.brave.com/res/v1/chat/completions",
                json=payload, headers=headers
            ) as r:
                if r.status != 200:
                    raise Exception(f"Answers API {r.status}")
                data = await r.json()
                return data["choices"][0]["message"]["content"].strip()

    # ====================== FOLLOW-UPS (NO MORE 404 ERRORS) ======================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if message.reference and message.reference.message_id in self.conversations:
            ref = message.reference.resolved
            if ref and ref.author.id == self.bot.user.id:
                await self._handle_followup(message)

    async def _handle_followup(self, message: discord.Message):
        mid = message.reference.message_id
        history = self.conversations.get(mid)
        if not history:
            return

        history.append({"role": "user", "content": message.content})
        try:
            api_key = await self.config.api_key()
            answer = await self._get_ai_answer(history, api_key)

            # ── Delete old AI message (per your request) ──
            try:
                old_msg = await message.channel.fetch_message(mid)
                await old_msg.delete()
            except (discord.NotFound, discord.HTTPException):
                pass  # already gone or can't delete

            # Post fresh new message (no reference = zero 404/10008)
            new_msg = await message.channel.send(
                f">>> **Brave AI Follow-up**\n\n{answer}\n\n"
                "*(Reply • ❓ follow-up • 🗑️ clear)*"
            )
            await new_msg.add_reaction("❓")
            await new_msg.add_reaction("🗑️")

            # Update conversation key to the new message
            self.conversations[new_msg.id] = history + [{"role": "assistant", "content": answer}]
            if mid in self.conversations:
                del self.conversations[mid]

        except Exception as e:
            await self._log_error(message.guild, f"Follow-up error: {str(e)}")

    # ====================== REACTIONS ======================
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        if user.bot or reaction.message.author != self.bot.user:
            return
        mid = reaction.message.id
        if mid not in self.conversations:
            return

        emoji = str(reaction.emoji)
        try:
            if emoji == "❓":
                await reaction.message.reply("Reply to this message to continue!", delete_after=30)
            elif emoji == "🗑️":
                if mid in self.conversations:
                    del self.conversations[mid]
                await reaction.message.reply("🗑️ Conversation cleared.", delete_after=12)
        except (discord.NotFound, discord.HTTPException):
            pass  # message already gone

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.id in self.conversations:
            del self.conversations[message.id]

    # ====================== ERROR LOGGING (10008 SUPPRESSED) ======================
    async def _log_error(self, guild: discord.Guild, text: str):
        """Only logs real issues — 404/10008 (deleted messages) are silently ignored."""
        if "10008" in text or "Unknown Message" in text:
            return  # ← No more spam from user deletions

        cid = await self.config.guild(guild).error_channel()
        if not cid:
            return
        channel = guild.get_channel(cid)
        if not channel:
            return

        embed = discord.Embed(title="BraveSearch • Issue", color=0xFF5555, timestamp=datetime.utcnow())
        embed.description = box(text[:1800], lang="text")
        embed.set_footer(text=f"Guild: {guild.name} ({guild.id})")
        try:
            await channel.send(embed=embed)
        except:
            pass

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏳ Wait {error.retry_after:.1f}s before using again.", delete_after=10)


async def setup(bot: Red):
    await bot.add_cog(BraveSearch(bot))
