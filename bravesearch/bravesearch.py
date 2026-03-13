import aiohttp
import urllib.parse
from typing import Dict, List, Optional

import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import bold


class BraveSearch(commands.Cog):
    """Brave Search + AI Answers — owner toggles between Web Search and Answers modes."""

    __author__ = "Shadow using Grok"
    __version__ = "2.0.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)
        self.config.register_global(api_key=None)
        self.config.register_guild(
            mode="web",                    # "web" or "answers"
            error_channel=None,            # channel ID for error logs
        )
        self.conversations: Dict[int, List[Dict[str, str]]] = {}

    @commands.is_owner()
    @commands.command(hidden=True)
    async def setbravekey(self, ctx: commands.Context, *, key: str = None):
        """Set Brave API key (owner only)."""
        if key is None:
            await ctx.send("Key is hidden.\nUse `[p]setbravekey YOUR_KEY` to set.")
            return
        await self.config.api_key.set(key.strip())
        await ctx.send("✅ API key saved securely.")

    @commands.is_owner()
    @commands.guild_only()
    @commands.command()
    async def bravemode(self, ctx: commands.Context, mode: str):
        """Toggle API mode: web or answers (owner only)."""
        mode = mode.lower()
        if mode not in ("web", "answers"):
            await ctx.send("Invalid mode. Use `web` or `answers`.")
            return
        await self.config.guild(ctx.guild).mode.set(mode)
        await ctx.send(f"✅ BraveSearch mode set to **{mode}** for this server.")

    @commands.is_owner()
    @commands.guild_only()
    @commands.command()
    async def braveerrorchannel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Set error logging channel (or `none` to disable)."""
        if channel is None:
            await self.config.guild(ctx.guild).error_channel.set(None)
            await ctx.send("✅ Error logging disabled.")
            return
        await self.config.guild(ctx.guild).error_channel.set(channel.id)
        await ctx.send(f"✅ Errors will now be logged to {channel.mention}.")

    @commands.guild_only()
    @commands.command()
    async def bravestatus(self, ctx: commands.Context):
        """Show current mode and settings."""
        gconf = await self.config.guild(ctx.guild)
        mode = gconf.mode
        ch = self.bot.get_channel(gconf.error_channel) if gconf.error_channel else None
        await ctx.send(
            f"**BraveSearch Status**\n"
            f"• Mode: **{mode.upper()}**\n"
            f"• Error channel: {ch.mention if ch else 'None'}\n"
            f"• API key: {'Set' if await self.config.api_key() else 'Not set'}"
        )

    @commands.command(name="brave")
    @commands.cooldown(1, 30, commands.BucketType.user)
    @commands.guild_only()
    async def brave_search(self, ctx: commands.Context, *, query: str):
        """brave your question here"""
        query = query.strip()
        if not query:
            await ctx.send_help()
            return

        search_url = f"https://search.brave.com/search?q={urllib.parse.quote_plus(query)}"
        await ctx.send(f"**Brave Search:** {search_url}")

        api_key = await self.config.api_key()
        if not api_key:
            return  # silent for users

        guild_conf = await self.config.guild(ctx.guild)
        mode = guild_conf.mode

        try:
            if mode == "web":
                await self._do_web_search(ctx, query, api_key)
            else:
                await self._do_answers(ctx, query, api_key)
        except Exception as e:
            await self._log_error(ctx.guild, f"Error in {mode} mode for query '{query}': {str(e)}")
            # No message to user

    async def _do_web_search(self, ctx: commands.Context, query: str, api_key: str):
        """Web Search mode — rich results embed."""
        headers = {"X-Subscription-Token": api_key}
        params = {
            "q": query,
            "count": 8,
            "extra_snippets": "true",
            "safesearch": "moderate",
        }

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers=headers,
                params=params,
            ) as r:
                if r.status != 200:
                    text = await r.text()
                    raise Exception(f"Web Search API {r.status}: {text[:300]}")

                data = await r.json()

        embed = discord.Embed(
            title="Brave Web Search Results",
            description=f"**Query:** {query}",
            color=0x00AEEF,
            url=f"https://search.brave.com/search?q={urllib.parse.quote_plus(query)}",
        )

        results = data.get("results", [])[:8]
        for i, res in enumerate(results, 1):
            title = res.get("title", "No title")
            url = res.get("url", "#")
            desc = res.get("description", res.get("snippet", "No description"))[:300]
            age = res.get("age", "")
            embed.add_field(
                name=f"{i}. {title}",
                value=f"{desc}\n[Visit]({url}) {age}",
                inline=False,
            )

        await ctx.send(embed=embed)

    async def _do_answers(self, ctx: commands.Context, query: str, api_key: str):
        """Answers mode — AI summary + follow-ups."""
        history = [{"role": "user", "content": query}]
        answer = await self._get_ai_answer(history, api_key)

        msg = await ctx.send(
            f">>> **Brave AI Answer**\n\n{answer}\n\n"
            "*(React ❓ or reply to this message for follow-ups)*"
        )
        await msg.add_reaction("❓")
        self.conversations[msg.id] = history + [{"role": "assistant", "content": answer}]

    async def _get_ai_answer(self, messages: List[Dict[str, str]], api_key: str, timeout: int = 60) -> str:
        headers = {"X-Subscription-Token": api_key, "Content-Type": "application/json"}
        payload = {
            "model": "brave",
            "messages": messages,
            "stream": False,
            "max_tokens": 1400,
            "temperature": 0.7,
        }

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.post(
                "https://api.search.brave.com/res/v1/chat/completions",
                json=payload,
                headers=headers,
            ) as r:
                if r.status != 200:
                    try:
                        err = await r.json()
                        msg = err.get("error", {}).get("detail") or str(err)
                    except:
                        msg = await r.text()
                    raise Exception(f"Answers API {r.status}: {msg[:400]}")
                data = await r.json()
                return data["choices"][0]["message"]["content"].strip()

    # Follow-up handling (only in answers mode)
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if (message.author.bot or not message.guild or
                message.content.lower().startswith("brave ")):
            return

        if (message.reference and message.reference.message_id in self.conversations):
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
                f">>> **Brave AI Follow-up**\n\n{answer}\n\n*(Reply or react ❓ to continue)*"
            )
            await reply.add_reaction("❓")
            history.append({"role": "assistant", "content": answer})
            self.conversations[mid] = history
        except Exception as e:
            await self._log_error(message.guild, f"Follow-up error: {str(e)}")

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        if (user.bot or str(reaction.emoji) != "❓" or
                reaction.message.author != self.bot.user or
                reaction.message.id not in self.conversations):
            return
        await reaction.message.reply(
            "**Follow-up mode active!** Reply to this message with your next question.",
            delete_after=45,
        )

    async def _log_error(self, guild: discord.Guild, error_text: str):
        """Send error to the configured channel (if set)."""
        channel_id = await self.config.guild(guild).error_channel()
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if channel and channel.permissions_for(guild.me).send_messages:
            try:
                await channel.send(f"**BraveSearch Error**\nGuild: {guild.name} ({guild.id})\n{error_text}")
            except:
                pass


async def setup(bot: Red):
    await bot.add_cog(BraveSearch(bot))
