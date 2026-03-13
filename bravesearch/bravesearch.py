import aiohttp
import urllib.parse
from typing import Dict, List, Optional

import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import bold


class BraveSearch(commands.Cog):
    """Brave Search — gives search link + optional AI summaries with follow-up support."""

    __author__ = "YourName"
    __version__ = "1.2.1"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)
        self.config.register_global(api_key=None)
        self.config.register_guild(ai_enabled=False)
        self.conversations: Dict[int, List[Dict[str, str]]] = {}  # bot message ID → history

    @commands.command(hidden=True)
    @commands.is_owner()
    async def setbravekey(self, ctx: commands.Context, *, key: str = None):
        """Set Brave Search API key (owner only).  
        Get free $5 monthly credits at https://api.search.brave.com"""
        if key is None:
            await ctx.send("API key is hidden.\nUse `[p]setbravekey YOUR_KEY` to set or update.")
            return
        await self.config.api_key.set(key.strip())
        await ctx.send("✅ Brave API key saved (stored securely).")

    @commands.guild_only()
    @commands.command()
    async def braveai(self, ctx: commands.Context):
        """Toggle Brave AI summaries on/off in this server."""
        current = await self.config.guild(ctx.guild).ai_enabled()
        new = not current
        await self.config.guild(ctx.guild).ai_enabled.set(new)
        status = bold("enabled") if new else bold("disabled")
        await ctx.send(f"✅ Brave AI summaries are now {status}.", delete_after=30)

    @commands.guild_only()
    @commands.command(name="bravesearchstatus")
    async def bravesearch_status(self, ctx: commands.Context):
        """Show BraveSearch configuration status."""
        key_set = "Set" if await self.config.api_key() else bold("Not set")
        ai_status = bold("Enabled") if await self.config.guild(ctx.guild).ai_enabled() else bold("Disabled")
        await ctx.send(
            f"**BraveSearch Status**\n"
            f"• API key: {key_set}\n"
            f"• AI summaries: {ai_status}\n\n"
            f"Use `[p]setbravekey` (owner) and `[p]braveai` to change settings."
        )

    @commands.command(name="brave")
    @commands.cooldown(1, 30, commands.BucketType.user)
    @commands.guild_only()
    async def brave_search(self, ctx: commands.Context, *, query: str):
        """Search Brave: `brave your question`  
        Always returns link; shows AI answer if enabled + API key set."""
        query = query.strip()
        if not query:
            await ctx.send_help()
            return

        url = f"https://search.brave.com/search?q={urllib.parse.quote_plus(query)}"
        await ctx.send(f"**Brave Search:** {url}")

        api_key = await self.config.api_key()
        if not api_key:
            if await self.bot.is_owner(ctx.author) or ctx.channel.permissions_for(ctx.author).administrator:
                await ctx.send(
                    "⚠️ No API key set — AI summary skipped.\n"
                    f"Owner: run `{ctx.prefix}setbravekey YOUR_KEY`\n"
                    "(Free $5 credits/month at https://api.search.brave.com)"
                )
            return

        if not await self.config.guild(ctx.guild).ai_enabled():
            return

        try:
            history = [{"role": "user", "content": query}]
            answer = await self._get_ai_answer(history)

            msg = await ctx.send(
                f">>> **Brave AI Answer**\n\n{answer}\n\n"
                "*(React ❓ or reply to this message to continue the conversation)*"
            )
            await msg.add_reaction("❓")
            self.conversations[msg.id] = history + [{"role": "assistant", "content": answer}]

        except aiohttp.ClientResponseError as e:
            await ctx.send(f"⚠️ Brave API error ({e.status})")
        except Exception as e:
            await ctx.send(f"⚠️ AI request failed: {str(e)[:180]}")

    async def _get_ai_answer(self, messages: List[Dict[str, str]], timeout: int = 60) -> str:
        api_key = await self.config.api_key()
        headers = {
            "X-Subscription-Token": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "model": "brave",
            "messages": messages,
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
                    text = await r.text()
                    raise aiohttp.ClientResponseError(
                        r.request_info, r.history, status=r.status,
                        message=f"Status {r.status}: {text[:200]}"
                    )
                data = await r.json()
                content = data["choices"][0]["message"]["content"].strip()
                if not content:
                    raise ValueError("Empty AI response")
                return content

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
        if mid not in self.conversations:
            return

        history = self.conversations[mid]
        history.append({"role": "user", "content": message.content})

        try:
            answer = await self._get_ai_answer(history)
            reply = await message.reply(
                f">>> **Brave AI Follow-up**\n\n{answer}\n\n"
                "*(Reply or react ❓ to ask more)*"
            )
            await reply.add_reaction("❓")
            history.append({"role": "assistant", "content": answer})
            self.conversations[mid] = history
        except Exception as e:
            await message.reply(f"⚠️ Follow-up failed: {str(e)[:140]}", delete_after=25)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        if user.bot or reaction.emoji != "❓" or reaction.message.author != self.bot.user:
            return
        if reaction.message.id not in self.conversations:
            return

        await reaction.message.reply(
            "**Follow-up mode active!**\nReply to **this message** with your next question.\n"
            "Context is preserved. React ❓ on new answers to keep going.",
            delete_after=45,
        )

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(
                f"⏳ Wait {error.retry_after:.1f} seconds before using `{ctx.prefix}brave` again.",
                delete_after=12,
            )


async def setup(bot: Red):
    await bot.add_cog(BraveSearch(bot))
