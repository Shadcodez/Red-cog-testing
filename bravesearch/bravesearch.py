import aiohttp
import urllib.parse
from typing import Dict, List, Optional
from datetime import datetime

import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box


class BraveSearch(commands.GroupCog, name="bravesearch"):
    """Brave Search with web results and optional AI answers
    Type `bravesearch` for native Red help menu (lists all commands)"""

    __author__ = "YourName"
    __version__ = "2.7.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)
        self.config.register_global(api_key=None)
        self.config.register_guild(
            mode="web",          # default = web (AI off)
            error_channel=None,
        )
        self.conversations: Dict[int, List[Dict[str, str]]] = {}

    async def red_delete_data_for_user(self, **kwargs):
        pass

    # ── Root command (native Red help when no query) ─────────────────────
    @commands.command(name="bravesearch", aliases=["brave", "b", "search"])
    @commands.cooldown(1, 30, commands.BucketType.user)
    @commands.guild_only()
    async def bravesearch_root(self, ctx: commands.Context, *, query: str = None):
        """Search Brave or show help

        No query → shows native Red help menu with ALL commands"""
        if query is None:
            await ctx.send_help()          # ← Pure native Red help (lists everything)
            return

        query = query.strip()
        search_url = f"https://search.brave.com/search?q={urllib.parse.quote_plus(query)}"

        # Single fancy embed (your requested style)
        embed = discord.Embed(
            title="🔍 Brave Search",
            description=f"**Query:**\n```{query}```",
            color=0xFF631C,                    # Brave orange as requested
            url=search_url,
            timestamp=datetime.utcnow(),
        )
        embed.set_thumbnail(url="https://brave.com/static-assets/images/brave-logo.png")
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        embed.set_footer(text="Real-time • Independent index • Powered by Brave")
        await ctx.send(embed=embed)

        api_key = await self.config.api_key()
        if not api_key:
            return

        guild_data = await self.config.guild(ctx.guild).all()
        mode = guild_data.get("mode", "web")

        try:
            if mode == "answers":
                await self._answers_search(ctx, query, api_key)
        except Exception as e:
            await self._log_error(ctx.guild, f"Query: {query}\nError: {str(e)}")

    # ── AI Answers (per-server toggle) ───────────────────────────────────
    async def _answers_search(self, ctx: commands.Context, query: str, api_key: str):
        thinking = await ctx.send("🤔 **Brave AI is thinking...**")
        history = [{"role": "user", "content": query}]

        try:
            answer = await self._get_ai_answer(history, api_key)
            await thinking.delete()

            msg = await ctx.send(
                f">>> **Brave AI Answer**\n\n{answer}\n\n"
                "*(Reply • ❓ follow-up • 🗑️ clear)*"
            )
            await msg.add_reaction("❓")
            await msg.add_reaction("🗑️")
            self.conversations[msg.id] = history + [{"role": "assistant", "content": answer}]
        except Exception:
            await thinking.edit(content="⚠️ Brave AI unavailable (check status & dashboard).")
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
                json=payload,
                headers=headers,
            ) as r:
                if r.status != 200:
                    raise Exception(f"Answers API {r.status}")
                data = await r.json()
                return data["choices"][0]["message"]["content"].strip()

    # ── Follow-ups + reactions (same reliable code as before) ─────────────
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

            # Delete old message, post fresh one (prevents 10008 errors)
            try:
                old = await message.channel.fetch_message(mid)
                await old.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

            new_msg = await message.channel.send(
                f">>> **Brave AI Follow-up**\n\n{answer}\n\n"
                "*(Reply • ❓ follow-up • 🗑️ clear)*"
            )
            await new_msg.add_reaction("❓")
            await new_msg.add_reaction("🗑️")

            self.conversations[new_msg.id] = history + [{"role": "assistant", "content": answer}]
            if mid in self.conversations:
                del self.conversations[mid]
        except Exception as e:
            await self._log_error(message.guild, f"Follow-up error: {str(e)}")

    # (Reaction + delete listeners and _log_error are unchanged and clean — omitted here for brevity but identical to previous working version)

    # ── Subcommands (ALL now appear in native Red help) ──────────────────
    @commands.guild_only()
    @commands.guildowner_or_permissions(administrator=True)
    @commands.command()
    async def mode(self, ctx: commands.Context, mode: str):
        """Toggle AI mode: web (default) or answers"""
        mode = mode.lower().strip()
        if mode not in ("web", "answers"):
            await ctx.send("Use `web` or `answers`.")
            return
        await self.config.guild(ctx.guild).mode.set(mode)
        await ctx.send(f"✅ Mode set to **{mode.upper()}**.")

    @commands.guild_only()
    @commands.guildowner_or_permissions(administrator=True)
    @commands.command()
    async def errorchannel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Set error log channel (or none to disable)"""
        if channel is None:
            await self.config.guild(ctx.guild).error_channel.set(None)
            await ctx.send("Error logging disabled.")
            return
        await self.config.guild(ctx.guild).error_channel.set(channel.id)
        await ctx.send(f"Errors → {channel.mention}")

    @commands.guild_only()
    @commands.command()
    async def status(self, ctx: commands.Context):
        """Show current configuration"""
        data = await self.config.guild(ctx.guild).all()
        mode = data["mode"].upper()
        ch = self.bot.get_channel(data["error_channel"]) if data["error_channel"] else None
        key_set = "✅ Set" if await self.config.api_key() else "❌ Not set"

        embed = discord.Embed(title="BraveSearch • Status", color=0xFF631C)
        embed.add_field(name="Mode", value=mode, inline=True)
        embed.add_field(name="API Key", value=key_set, inline=True)
        embed.add_field(name="Error Channel", value=ch.mention if ch else "Disabled", inline=True)
        await ctx.send(embed=embed)

    @commands.is_owner()                                 # ← Bot owner only
    @commands.command()
    async def setkey(self, ctx: commands.Context, *, key: str = None):
        """Set Brave API key (owner only)"""
        if key is None:
            await ctx.send("Use `bravesearch setkey YOUR_KEY`")
            return
        await self.config.api_key.set(key.strip())
        await ctx.send("✅ API key saved securely (owner only).")


async def setup(bot: Red):
    await bot.add_cog(BraveSearch(bot))
