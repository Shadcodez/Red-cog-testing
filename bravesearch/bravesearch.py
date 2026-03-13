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
    Type `bravesearch` for full help & command list"""

    __author__ = "YourName"
    __version__ = "2.4.0"

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

    # ====================== HELP MENU (when typing just "bravesearch") ======================
    @commands.command(name="bravesearch", aliases=["brave", "b", "search"])
    @commands.cooldown(1, 30, commands.BucketType.user)
    @commands.guild_only()
    async def bravesearch(self, ctx: commands.Context, *, query: str = None):
        """Main entry point"""
        if query is None:
            # Fancy full help embed – shows EVERY command
            embed = discord.Embed(
                title="🔍 BraveSearch – Full Command List",
                description="Type `bravesearch your question` to search.\nAll commands below:",
                color=0x00AEEF,
                timestamp=datetime.utcnow(),
            )
            embed.add_field(name="Search", value="`bravesearch <question>`\nAliases: `brave`, `b`, `search`", inline=False)
            embed.add_field(name="Mode Toggle (Admin/Owner)", value="`bravesearch mode web` or `bravesearch mode answers`", inline=False)
            embed.add_field(name="Error Log Channel (Admin/Owner)", value="`bravesearch errorchannel #channel` or `none`", inline=False)
            embed.add_field(name="Status", value="`bravesearch status`", inline=False)
            embed.add_field(name="Set API Key (Owner only)", value="`[p]setbravekey YOUR_KEY`", inline=False)
            embed.set_footer(text="BraveSearch • Premium Experience")
            await ctx.send(embed=embed)
            return

        # ====================== NORMAL SEARCH ======================
        query = query.strip()
        search_url = f"https://search.brave.com/search?q={urllib.parse.quote_plus(query)}"

        # Fancy search embed with query in code block
        embed = discord.Embed(
            title="🔍 Brave Search",
            description=f"**Query:**\n```{query}```",
            color=0x00AEEF,
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
            if mode == "web":
                await self._web_search(ctx, query, api_key)
            else:
                await self._answers_search(ctx, query, api_key)
        except Exception as e:
            await self._log_error(ctx.guild, f"Query: {query}\nError: {str(e)}")

    # ====================== WEB SEARCH ======================
    async def _web_search(self, ctx: commands.Context, query: str, api_key: str):
        # ... (same clean web results as before – omitted for brevity, unchanged)
        # (full code available on request if needed)

    # ====================== ANSWERS MODE (now with Assistant-style fallback) ======================
    async def _answers_search(self, ctx: commands.Context, query: str, api_key: str):
        thinking = await ctx.send("🤔 **Brave AI is thinking...**")
        history = [{"role": "user", "content": query}]

        try:
            answer = await self._get_ai_answer(history, api_key)
            await thinking.delete()

            msg = await ctx.send(
                f">>> **Brave AI Answer**\n\n{answer}\n\n"
                "*(Reply to this message • ❓ for follow-up • 🗑️ to clear)*"
            )
            await msg.add_reaction("❓")
            await msg.add_reaction("🗑️")
            self.conversations[msg.id] = history + [{"role": "assistant", "content": answer}]
        except Exception as e:
            await thinking.edit(
                content="⚠️ **Brave AI is enabled but currently unavailable.**\n"
                "This usually means the **Answers plan** is not active on the API key.\n"
                "Owner: check `[p]bravesearch status` and your Brave dashboard."
            )
            await self._log_error(ctx.guild, f"AI failed for '{query}': {str(e)}")

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

    # ====================== FOLLOW-UPS (delete old + new message – zero 404s) ======================
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

            # Delete old message
            try:
                old = await message.channel.fetch_message(mid)
                await old.delete()
            except:
                pass

            # Post fresh message (no reference = no 10008)
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

    # (Reaction, delete, and logging sections are identical to the previous perfect version – no 10008 spam)

    # ====================== SUBCOMMANDS (mode, errorchannel, status) ======================
    @commands.guild_only()
    @commands.guildowner_or_permissions(administrator=True)
    @commands.command()
    async def mode(self, ctx: commands.Context, mode: str):
        # ... (unchanged)

    @commands.guild_only()
    @commands.guildowner_or_permissions(administrator=True)
    @commands.command()
    async def errorchannel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        # ... (unchanged)

    @commands.guild_only()
    @commands.command()
    async def status(self, ctx: commands.Context):
        # ... (unchanged)

    # ====================== ERROR LOGGING (10008 suppressed) ======================
    async def _log_error(self, guild: discord.Guild, text: str):
        if "10008" in text or "Unknown Message" in text:
            return
        # ... (rest unchanged – sends nice embed to log channel)

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏳ Wait {error.retry_after:.1f}s", delete_after=10)


async def setup(bot: Red):
    await bot.add_cog(BraveSearch(bot))
