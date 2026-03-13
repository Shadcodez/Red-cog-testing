import aiohttp
import urllib.parse
from typing import List, Dict, Optional

import discord
from discord.ext import commands
from redbot.core import commands as red_commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import bold, inline


class BraveSearch(red_commands.Cog):
    """Brave Search integration — search links + optional AI summaries with follow-ups."""

    __author__ = ["YourName"]
    __version__ = "1.2.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210)
        self.config.register_global(api_key: Optional[str] = None)
        self.config.register_guild(ai_enabled: bool = False)
        self.conversations: Dict[int, List[Dict[str, str]]] = {}  # bot_msg_id → conversation history

    async def red_delete_data_for_user(self, **kwargs):
        pass  # No personal data stored

    @red_commands.command(hidden=True)
    @red_commands.is_owner()
    async def setbravekey(self, ctx: red_commands.Context, *, key: str = None):
        """Set Brave Search API key (owner only).  
        Get started (with $5 free monthly credits) at https://api.search.brave.com"""
        if not key:
            await ctx.send("API key is hidden for security.\nUse `[p]setbravekey YOUR_KEY_HERE` to set/update.")
            return
        await self.config.api_key.set(key.strip())
        await ctx.send("✅ Brave API key saved securely.")

    @red_commands.guild_only()
    @red_commands.command()
    async def braveai(self, ctx: red_commands.Context):
        """Toggle Brave AI summaries (Leo-style) on/off for this server."""
        current = await self.config.guild(ctx.guild).ai_enabled()
        new_val = not current
        await self.config.guild(ctx.guild).ai_enabled.set(new_val)
        status = bold("enabled") if new_val else bold("disabled")
        await ctx.send(f"✅ Brave AI summaries are now {status} in this server.", delete_after=30)

    @red_commands.guild_only()
    @red_commands.command(name="bravesearchstatus")
    async def bravesearch_status(self, ctx: red_commands.Context):
        """Show current BraveSearch cog status for this server."""
        key_set = bool(await self.config.api_key())
        ai_on = await self.config.guild(ctx.guild).ai_enabled()
        lines = [
            f"API key: {'Set' if key_set else bold('Not set')}",
            f"AI summaries: {bold('Enabled') if ai_on else bold('Disabled')}",
            "\nUse `[p]setbravekey` (owner) and `[p]braveai` (here) to configure."
        ]
        await ctx.send("\n".join(lines))

    @red_commands.command(name="brave")
    @red_commands.cooldown(rate=1, per=30, type=red_commands.BucketType.user)  # 30s per user
    @red_commands.guild_only()
    async def brave_search(self, ctx: red_commands.Context, *, query: str):
        """Search Brave: `brave your question here`  
        Always gives search link; AI summary if enabled + key exists."""
        if not query.strip():
            await ctx.send_help()
            return

        search_url = f"https://search.brave.com/search?q={urllib.parse.quote_plus(query)}"
        await ctx.send(f"**Brave Search Link:** {search_url}")

        api_key = await self.config.api_key()
        if not api_key:
            if ctx.author.guild_permissions.administrator or await self.bot.is_owner(ctx.author):
                await ctx.send(
                    "⚠️ No Brave API key set → AI skipped.\n"
                    f"Owner: use `{ctx.prefix}setbravekey YOUR_KEY` "
                    "(free $5 credits/month available at https://api.search.brave.com)"
                )
            return

        ai_enabled = await self.config.guild(ctx.guild).ai_enabled()
        if not ai_enabled:
            return

        try:
            history = [{"role": "user", "content": query}]
            ai_text = await self._get_ai_answer(history, timeout=60)

            msg = await ctx.send(
                f">>> **Brave AI Answer**\n\n{ai_text}\n\n"
                f"*(React with ❓ or reply to me to ask follow-ups — context preserved)*"
            )
            await msg.add_reaction("❓")

            self.conversations[msg.id] = history + [{"role": "assistant", "content": ai_text}]

        except aiohttp.ClientResponseError as e:
            await ctx.send(f"⚠️ Brave API error ({e.status}): {str(e)}")
        except aiohttp.ClientError:
            await ctx.send("⚠️ Network issue reaching Brave AI — try again later.")
        except Exception as e:
            await ctx.send(f"⚠️ AI failed: {type(e).__name__} – {str(e)[:180]}")

    async def _handle_followup(self, message: discord.Message):
        if not message.reference or not message.reference.message_id:
            return

        ref_id = message.reference.message_id
        if ref_id not in self.conversations:
            return

        history = self.conversations[ref_id]
        history.append({"role": "user", "content": message.content})

        try:
            ai_text = await self._get_ai_answer(history, timeout=60)

            follow_msg = await message.reply(
                f">>> **Brave AI Follow-up**\n\n{ai_text}\n\n"
                f"*(React ❓ or reply again to continue — context kept)*"
            )
            await follow_msg.add_reaction("❓")

            history.append({"role": "assistant", "content": ai_text})
            self.conversations[ref_id] = history

        except Exception as e:
            await message.reply(f"⚠️ Follow-up failed: {str(e)[:140]}", delete_after=30)

    @red_commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        if message.content.lower().startswith("brave "):
            # Handled by the @command above — we just need to ignore it here
            return

        # Follow-up via reply to bot's AI message
        if message.reference and message.reference.message_id in self.conversations:
            ref_msg = message.reference.resolved
            if ref_msg and ref_msg.author == self.bot.user:
                await self._handle_followup(message)

    @red_commands.Cog.listener()
    async def on_command_error(self, ctx: red_commands.Context, error):
        if isinstance(error, red_commands.CommandOnCooldown):
            await ctx.send(
                f"⏳ Please wait {error.retry_after:.1f}s before using `{ctx.prefix}brave` again.",
                delete_after=10
            )

    @red_commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        if user.bot or str(reaction.emoji) != "❓":
            return
        msg = reaction.message
        if msg.id not in self.conversations or msg.author != self.bot.user:
            return

        try:
            await msg.reply(
                "**Follow-up ready!**\nReply directly to **this message** with your next question.\n"
                "Conversation context stays active. React ❓ on new replies to keep going.",
                delete_after=60,
            )
        except discord.HTTPException:
            pass

    async def _get_ai_answer(self, messages: List[Dict[str, str]], *, timeout: int = 60) -> str:
        api_key = await self.config.api_key()
        if not api_key:
            raise ValueError("No API key configured.")

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

        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=timeout_obj) as session:
            async with session.post(
                "https://api.search.brave.com/res/v1/chat/completions",
                json=payload,
                headers=headers,
            ) as resp:
                if resp.status != 200:
                    err_text = await resp.text()
                    raise aiohttp.ClientResponseError(
                        resp.request_info, resp.history, status=resp.status,
                        message=f"Brave API {resp.status}: {err_text[:200]}"
                    )
                data = await resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                if not content:
                    raise ValueError("Empty response from Brave AI.")
                return content


async def setup(bot: Red):
    await bot.add_cog(BraveSearch(bot))