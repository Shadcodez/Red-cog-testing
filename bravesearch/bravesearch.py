import aiohttp
import urllib.parse
from typing import Dict, List, Optional
from datetime import datetime

import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import bold, box


class BraveSearch(commands.Cog):
    """Premium Brave Search + AI Answers with dual API support."""

    __author__ = "YourName"
    __version__ = "2.1.0"

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

    # ====================== OWNER COMMANDS ======================
    @commands.is_owner()
    @commands.command(hidden=True)
    async def setbravekey(self, ctx: commands.Context, *, key: str = None):
        """Set your Brave API key."""
        if key is None:
            await ctx.send("Key hidden for security.\nUse `[p]setbravekey YOUR_KEY` to set.")
            return
        await self.config.api_key.set(key.strip())
        await ctx.send("✅ Brave API key saved securely.")

    @commands.guild_only()
    @commands.guildowner_or_permissions(administrator=True)
    @commands.command()
    async def bravemode(self, ctx: commands.Context, mode: str):
        """Toggle between **web** and **answers** mode (Admins + Owner)."""
        mode = mode.lower().strip()
        if mode not in ("web", "answers"):
            await ctx.send("Please use `web` or `answers`.")
            return
        await self.config.guild(ctx.guild).mode.set(mode)
        await ctx.send(f"✅ **BraveSearch** is now in **{mode.upper()}** mode.")

    @commands.guild_only()
    @commands.guildowner_or_permissions(administrator=True)
    @commands.command()
    async def braveerrorchannel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Set error log channel (`none` to disable)."""
        if channel is None:
            await self.config.guild(ctx.guild).error_channel.set(None)
            await ctx.send("✅ Error logging disabled.")
            return
        await self.config.guild(ctx.guild).error_channel.set(channel.id)
        await ctx.send(f"✅ Errors will be sent to {channel.mention}.")

    # ====================== STATUS ======================
    @commands.guild_only()
    @commands.command()
    async def bravestatus(self, ctx: commands.Context):
        """Show current BraveSearch settings."""
        data = await self.config.guild(ctx.guild).all()
        mode = data["mode"].upper()
        ch = self.bot.get_channel(data["error_channel"]) if data["error_channel"] else None
        key_set = "✅ Set" if await self.config.api_key() else "❌ Not set"

        embed = discord.Embed(title="BraveSearch Status", color=0x00AEEF)
        embed.add_field(name="Mode", value=mode, inline=True)
        embed.add_field(name="API Key", value=key_set, inline=True)
        embed.add_field(name="Error Log", value=ch.mention if ch else "Disabled", inline=True)
        embed.set_footer(text="Powered by Brave • Premium Experience")
        await ctx.send(embed=embed)

    # ====================== MAIN COMMAND ======================
    @commands.command(name="brave", aliases=["b", "search"])
    @commands.cooldown(1, 30, commands.BucketType.user)
    @commands.guild_only()
    async def brave_search(self, ctx: commands.Context, *, query: str):
        """brave your question here\nAliases: b, search"""
        query = query.strip()
        if not query:
            await ctx.send_help()
            return

        search_url = f"https://search.brave.com/search?q={urllib.parse.quote_plus(query)}"
        await ctx.send(f"**Brave Search:** {search_url}")

        api_key = await self.config.api_key()
        if not api_key:
            return  # silent

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
            async with session.get("https://api.search.brave.com/res/v1/web/search",
                                   headers=headers, params=params) as r:
                if r.status != 200:
                    raise Exception(f"Web API {r.status}")
                data = await r.json()

        embed = discord.Embed(
            title="🔍 Brave Web Results",
            description=f"**Query:** {query}",
            color=0x00AEEF,
            url=f"https://search.brave.com/search?q={urllib.parse.quote_plus(query)}",
        )
        embed.set_footer(text="Powered by Brave Search")

        for i, result in enumerate(data.get("results", [])[:8], 1):
            title = result.get("title", "Untitled")
            url = result.get("url", "#")
            desc = (result.get("description") or result.get("snippet") or "")[:280]
            age = f" • {result.get('age', '')}" if result.get("age") else ""
            embed.add_field(
                name=f"{i}. {title}",
                value=f"{desc}\n[Open Link]({url}){age}",
                inline=False,
            )

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
                "*(Reply to me or react ❓ to continue • 🗑️ to clear history)*"
            )
            await msg.add_reaction("❓")
            await msg.add_reaction("🗑️")
            self.conversations[msg.id] = history + [{"role": "assistant", "content": answer}]
        except Exception as e:
            await thinking.edit(content="⚠️ AI request failed (check error log channel).")
            raise e

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
                json=payload,
                headers=headers,
            ) as r:
                if r.status != 200:
                    err = await r.text()
                    raise Exception(f"Answers API {r.status}: {err[:300]}")
                data = await r.json()
                return data["choices"][0]["message"]["content"].strip()

    # ====================== FOLLOW-UPS & REACTIONS ======================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or message.content.lower().startswith("brave "):
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

            reply = await message.reply(
                f">>> **Brave AI Follow-up**\n\n{answer}\n\n"
                "*(Reply or react ❓ • 🗑️ to clear)*"
            )
            await reply.add_reaction("❓")
            await reply.add_reaction("🗑️")
            history.append({"role": "assistant", "content": answer})
            self.conversations[mid] = history
        except Exception as e:
            await self._log_error(message.guild, f"Follow-up error: {str(e)}")

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        if user.bot or reaction.message.author != self.bot.user:
            return

        msg_id = reaction.message.id
        if msg_id not in self.conversations:
            return

        emoji = str(reaction.emoji)
        if emoji == "❓":
            await reaction.message.reply(
                "**Follow-up mode active!** Just reply to this message.",
                delete_after=40,
            )
        elif emoji == "🗑️":
            if msg_id in self.conversations:
                del self.conversations[msg_id]
                await reaction.message.reply("🗑️ Conversation cleared.", delete_after=15)

    # ====================== ERROR LOGGING ======================
    async def _log_error(self, guild: discord.Guild, text: str):
        cid = await self.config.guild(guild).error_channel()
        if not cid:
            return
        channel = guild.get_channel(cid)
        if not channel:
            return

        embed = discord.Embed(title="BraveSearch Error", color=0xFF0000, timestamp=datetime.utcnow())
        embed.description = box(text[:1800], lang="python")
        embed.set_footer(text=f"Guild: {guild.name} ({guild.id})")
        try:
            await channel.send(embed=embed)
        except:
            pass

    # ====================== COOLDOWN HANDLING ======================
    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(
                f"⏳ **Cooldown** — try again in {error.retry_after:.1f} seconds.",
                delete_after=10,
            )


async def setup(bot: Red):
    await bot.add_cog(BraveSearch(bot))
