import aiohttp
import urllib.parse
from typing import Dict, List, Optional

import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import bold


class BraveSearch(commands.Cog):
    """Brave Search — search link + optional AI summaries with follow-ups."""

    __author__ = "YourName"
    __version__ = "1.2.2"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)
        self.config.register_global(api_key=None)
        self.config.register_guild(ai_enabled=False)
        self.conversations: Dict[int, List[Dict[str, str]]] = {}

    @commands.command(hidden=True)
    @commands.is_owner()
    async def setbravekey(self, ctx: commands.Context, *, key: str = None):
        """Set Brave Search API key (owner only)."""
        if key is None:
            await ctx.send("API key is hidden.\nUse `[p]setbravekey YOUR_KEY` to set.")
            return
        await self.config.api_key.set(key.strip())
        await ctx.send("✅ Brave API key saved.")

    @commands.guild_only()
    @commands.command()
    async def braveai(self, ctx: commands.Context):
        """Toggle AI summaries on/off."""
        current = await self.config.guild(ctx.guild).ai_enabled()
        await self.config.guild(ctx.guild).ai_enabled.set(not current)
        status = bold("enabled") if not current else bold("disabled")
        await ctx.send(f"✅ Brave AI summaries are now {status}.", delete_after=30)

    @commands.command(name="brave")
    @commands.cooldown(1, 30, commands.BucketType.user)
    @commands.guild_only()
    async def brave_search(self, ctx: commands.Context, *, query: str):
        """brave your question here"""
        query = query.strip()
        if not query:
            await ctx.send_help()
            return

        url = f"https://search.brave.com/search?q={urllib.parse.quote_plus(query)}"
        await ctx.send(f"**Brave Search:** {url}")

        api_key = await self.config.api_key()
        if not api_key:
            await ctx.send("⚠️ No API key set — AI skipped.\nOwner: `[p]setbravekey YOUR_KEY`")
            return

        if not await self.config.guild(ctx.guild).ai_enabled():
            return

        try:
            history = [{"role": "user", "content": query}]
            answer = await self._get_ai_answer(history)

            msg = await ctx.send(
                f">>> **Brave AI Answer**\n\n{answer}\n\n"
                "*(React ❓ or reply to this message for follow-ups)*"
            )
            await msg.add_reaction("❓")
            self.conversations[msg.id] = history + [{"role": "assistant", "content": answer}]

        except Exception as e:
            await ctx.send(f"⚠️ {str(e)}")   # ← Now shows Brave's exact error

    async def _get_ai_answer(self, messages: List[Dict[str, str]], timeout: int = 60) -> str:
        api_key = await self.config.api_key()
        headers = {
            "x-subscription-token": api_key,      # ← Fixed to match official docs
            "Content-Type": "application/json",
        }
        payload = {
            "model": "brave",
            "messages": messages,
            "stream": False,                      # ← Explicitly added
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
                        error_msg = err.get("error", {}).get("message") or str(err)
                    except:
                        error_msg = await r.text()
                    raise Exception(f"Brave API error ({r.status}): {error_msg[:400]}")

                data = await r.json()
                content = data["choices"][0]["message"]["content"].strip()
                return content or "No answer received."

    # (The rest of the cog — on_message, _handle_followup, on_reaction_add, etc. — stays exactly the same as the previous version I gave you)

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
            answer = await self._get_ai_answer(history)
            reply = await message.reply(
                f">>> **Brave AI Follow-up**\n\n{answer}\n\n*(Reply or react ❓ to continue)*"
            )
            await reply.add_reaction("❓")
            history.append({"role": "assistant", "content": answer})
            self.conversations[mid] = history
        except Exception as e:
            await message.reply(f"⚠️ {str(e)}", delete_after=30)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        if user.bot or str(reaction.emoji) != "❓" or reaction.message.author != self.bot.user:
            return
        if reaction.message.id not in self.conversations:
            return
        await reaction.message.reply(
            "**Follow-up mode active!**\nReply to this message with your next question.",
            delete_after=45,
        )


async def setup(bot: Red):
    await bot.add_cog(BraveSearch(bot))
