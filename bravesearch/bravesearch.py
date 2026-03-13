import aiohttp
import urllib.parse
from typing import Dict, List, Optional
from datetime import datetime

import discord
from discord.ext import commands
from redbot.core import commands as red_commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import bold, box


class BraveSearch(red_commands.GroupCog, name="bravesearch"):
    """Premium Brave Search + AI Answers (type 'bravesearch' for help)"""

    __author__ = "YourName"
    __version__ = "2.2.0"

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

    # ── Owner-only key setup ──
    @red_commands.is_owner()
    @red_commands.command(hidden=True)
    async def setbravekey(self, ctx: red_commands.Context, *, key: str = None):
        if key is None:
            await ctx.send("Key hidden.\n`[p]setbravekey YOUR_KEY` to set.")
            return
        await self.config.api_key.set(key.strip())
        await ctx.send("✅ API key saved.")

    # ── Admin/Owner mode toggle ──
    @red_commands.guild_only()
    @red_commands.guildowner_or_permissions(administrator=True)
    @red_commands.command()
    async def mode(self, ctx: red_commands.Context, mode: str):
        mode = mode.lower().strip()
        if mode not in ("web", "answers"):
            await ctx.send("Use `web` or `answers`.")
            return
        await self.config.guild(ctx.guild).mode.set(mode)
        await ctx.send(f"✅ Mode set to **{mode.upper()}**.")

    # ── Admin/Owner error channel ──
    @red_commands.guild_only()
    @red_commands.guildowner_or_permissions(administrator=True)
    @red_commands.command()
    async def errorchannel(self, ctx: red_commands.Context, channel: discord.TextChannel = None):
        if channel is None:
            await self.config.guild(ctx.guild).error_channel.set(None)
            await ctx.send("Error logging disabled.")
            return
        await self.config.guild(ctx.guild).error_channel.set(channel.id)
        await ctx.send(f"Errors → {channel.mention}")

    # ── Status (public) ──
    @red_commands.guild_only()
    @red_commands.command()
    async def status(self, ctx: red_commands.Context):
        data = await self.config.guild(ctx.guild).all()
        mode = data["mode"].upper()
        ch = self.bot.get_channel(data["error_channel"]) if data["error_channel"] else None
        key = "✅ Set" if await self.config.api_key() else "❌ Not set"

        embed = discord.Embed(title="BraveSearch • Status", color=0x00AEEF)
        embed.add_field(name="Mode", value=mode, inline=True)
        embed.add_field(name="API Key", value=key, inline=True)
        embed.add_field(name="Error Logs", value=ch.mention if ch else "Off", inline=True)
        embed.set_footer(text="Powered by Brave")
        await ctx.send(embed=embed)

    # ── Main search trigger (when no subcommand) → show help ──
    @red_commands.command(name="brave", aliases=["b", "search"])
    @red_commands.cooldown(1, 30, red_commands.BucketType.user)
    @red_commands.guild_only()
    async def brave(self, ctx: red_commands.Context, *, query: str = None):
        if query is None:
            # User typed just "bravesearch" / "brave" → show native Red help
            await ctx.send_help()
            return

        # Normal search flow
        query = query.strip()
        search_url = f"https://search.brave.com/search?q={urllib.parse.quote_plus(query)}"
        await ctx.send(f"**Brave Search:** {search_url}")

        api_key = await self.config.api_key()
        if not api_key:
            return

        guild_data = await self.config.guild(ctx.guild).all()
        mode = guild_data.get("mode", "web")

        try:
            if mode == "web":
                await self._web_search(ctx, query, api_key)
            else:
                await self._answers_search(ctx, query, api_key)
        except Exception as e:
            await self._log_error(ctx.guild, f"Query: {query}\nError: {str(e)}")

    # ── Web search ──
    async def _web_search(self, ctx, query, api_key):
        headers = {"X-Subscription-Token": api_key}
        params = {"q": query, "count": 9}

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as s:
            async with s.get("https://api.search.brave.com/res/v1/web/search",
                             headers=headers, params=params) as r:
                if r.status != 200:
                    raise Exception(f"Web API {r.status}")
                data = await r.json()

        embed = discord.Embed(title="🔍 Brave Results", color=0x00AEEF, url=f"https://search.brave.com/search?q={urllib.parse.quote_plus(query)}")
        for i, res in enumerate(data.get("results", [])[:8], 1):
            title = res.get("title", "No title")
            url = res.get("url", "#")
            desc = (res.get("description") or res.get("snippet") or "")[:280]
            embed.add_field(name=f"{i}. {title}", value=f"{desc}\n[Link]({url})", inline=False)

        await ctx.send(embed=embed)

    # ── Answers search ──
    async def _answers_search(self, ctx, query, api_key):
        thinking = await ctx.send("🤔 **Thinking...**")
        history = [{"role": "user", "content": query}]

        try:
            answer = await self._get_ai_answer(history, api_key)
            await thinking.delete()

            msg = await ctx.send(
                f">>> **Brave AI**\n\n{answer}\n\n*(Reply or ❓ to continue • 🗑️ clear)*"
            )
            await msg.add_reaction("❓")
            await msg.add_reaction("🗑️")
            self.conversations[msg.id] = history + [{"role": "assistant", "content": answer}]
        except:
            await thinking.edit(content="⚠️ AI failed (logged).")
            raise

    async def _get_ai_answer(self, messages, api_key):
        headers = {"X-Subscription-Token": api_key, "Content-Type": "application/json"}
        payload = {"model": "brave", "messages": messages, "stream": False, "max_tokens": 1500}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=70)) as s:
            async with s.post("https://api.search.brave.com/res/v1/chat/completions",
                              json=payload, headers=headers) as r:
                if r.status != 200:
                    raise Exception(f"API {r.status}")
                data = await r.json()
                return data["choices"][0]["message"]["content"].strip()

    # ── Follow-up ──
    @red_commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if message.reference and message.reference.message_id in self.conversations:
            ref = message.reference.resolved
            if ref and ref.author.id == self.bot.user.id:
                await self._handle_followup(message)

    async def _handle_followup(self, message):
        mid = message.reference.message_id
        history = self.conversations.get(mid)
        if not history:
            return

        history.append({"role": "user", "content": message.content})
        try:
            api_key = await self.config.api_key()
            answer = await self._get_ai_answer(history, api_key)
            reply = await message.reply(f">>> **Follow-up**\n\n{answer}\n\n*(❓ / 🗑️)*")
            await reply.add_reaction("❓")
            await reply.add_reaction("🗑️")
            history.append({"role": "assistant", "content": answer})
            self.conversations[mid] = history
        except discord.NotFound:
            pass  # Message gone → ignore
        except Exception as e:
            await self._log_error(message.guild, f"Follow-up: {str(e)}")

    # ── Reactions ──
    @red_commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        if user.bot or reaction.message.author != self.bot.user:
            return
        mid = reaction.message.id
        if mid not in self.conversations:
            return

        emoji = str(reaction.emoji)
        try:
            if emoji == "❓":
                await reaction.message.reply("Reply to continue!", delete_after=30)
            elif emoji == "🗑️":
                if mid in self.conversations:
                    del self.conversations[mid]
                await reaction.message.reply("Cleared.", delete_after=10)
        except discord.NotFound:
            pass  # Message/reaction target gone

    # ── Cleanup deleted messages ──
    @red_commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.id in self.conversations:
            del self.conversations[message.id]

    # ── Error logging (ignore 10008) ──
    async def _log_error(self, guild, text):
        cid = await self.config.guild(guild).error_channel()
        if not cid:
            return
        channel = guild.get_channel(cid)
        if not channel:
            return

        embed = discord.Embed(title="BraveSearch Issue", color=0xFF5555, timestamp=datetime.utcnow())
        embed.description = box(text[:1800], lang="text")
        try:
            await channel.send(embed=embed)
        except:
            pass

    @red_commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, red_commands.CommandOnCooldown):
            await ctx.send(f"⏳ Wait {error.retry_after:.1f}s", delete_after=10)


async def setup(bot: Red):
    await bot.add_cog(BraveSearch(bot))
