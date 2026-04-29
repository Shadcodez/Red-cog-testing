# ============================================
# OllamaAI - A Red-DiscordBot Cog
# Full-featured local AI chat using Ollama
# ============================================

import discord
import requests
import asyncio
from collections import defaultdict, deque
from redbot.core import commands, Config, checks
from redbot.core.bot import Red


class OllamaAI(commands.Cog):
    """Chat with a locally-hosted AI through Ollama."""

    __version__ = "1.0.0"
    __author__ = "YourName"

    # ============================================
    # INIT
    # ============================================
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=4572049816, force_registration=True)

        # Default per-guild settings
        default_guild = {
            "ollama_url": "http://localhost:11434/api/generate",
            "ollama_model": "llama3.1",
            "temperature": 0.9,
            "max_tokens": 200,
            "system_prompt": (
                "You are a friendly and helpful AI assistant in a Discord server. "
                "Keep your responses concise, engaging, and appropriate for a chat environment. "
                "Use a casual but informative tone."
            ),
            "mention_respond": True,
            "dm_respond": True,
            "trigger_words": [],
            "context_enabled": True,
            "context_length": 10,
            "enabled": True,
        }

        # Default global settings (fallback for DMs)
        default_global = {
            "ollama_url": "http://localhost:11434/api/generate",
            "ollama_model": "llama3.1",
            "temperature": 0.9,
            "max_tokens": 200,
            "system_prompt": (
                "You are a friendly and helpful AI assistant. "
                "Keep your responses concise and engaging."
            ),
        }

        self.config.register_guild(**default_guild)
        self.config.register_global(**default_global)

        # In-memory conversation history: {channel_id: deque of (role, content)}
        self.conversations = defaultdict(lambda: deque(maxlen=20))

    def cog_unload(self):
        """Clean up on cog unload."""
        self.conversations.clear()

    def format_help_for_context(self, ctx: commands.Context) -> str:
        return f"OllamaAI v{self.__version__} by {self.__author__}"

    # ============================================
    # HELPER: Build prompt with context
    # ============================================
    async def _build_prompt(self, guild, channel_id: int, user_name: str, user_message: str) -> str:
        """Build a prompt string including system prompt and conversation context."""
        if guild is not None:
            system_prompt = await self.config.guild(guild).system_prompt()
            context_enabled = await self.config.guild(guild).context_enabled()
            context_length = await self.config.guild(guild).context_length()
        else:
            system_prompt = await self.config.system_prompt()
            context_enabled = True
            context_length = 10

        parts = []
        parts.append(f"System: {system_prompt}")

        if context_enabled and channel_id in self.conversations:
            history = list(self.conversations[channel_id])[-context_length:]
            for role, content in history:
                parts.append(f"{role}: {content}")

        parts.append(f"User ({user_name}): {user_message}")
        parts.append("Assistant:")

        return "\n".join(parts)

    # ============================================
    # HELPER: Talk to Ollama AI
    # ============================================
    async def ask_ai(self, guild, channel_id: int, user_name: str, prompt: str) -> str:
        """
        Send a prompt to Ollama and get AI response.
        Runs the blocking HTTP request in an executor to avoid blocking the bot.
        """
        if guild is not None:
            ollama_url = await self.config.guild(guild).ollama_url()
            ollama_model = await self.config.guild(guild).ollama_model()
            temperature = await self.config.guild(guild).temperature()
            max_tokens = await self.config.guild(guild).max_tokens()
        else:
            ollama_url = await self.config.ollama_url()
            ollama_model = await self.config.ollama_model()
            temperature = await self.config.temperature()
            max_tokens = await self.config.max_tokens()

        full_prompt = await self._build_prompt(guild, channel_id, user_name, prompt)

        payload = {
            "model": ollama_model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        def _do_request():
            try:
                response = requests.post(ollama_url, json=payload, timeout=60)
                if response.status_code == 200:
                    data = response.json()
                    return data.get("response", "").strip()
                else:
                    return (
                        f"⚠️ Ollama returned status code `{response.status_code}`. "
                        "Make sure Ollama is running and the model is pulled."
                    )
            except requests.exceptions.ConnectionError:
                return (
                    "❌ **Connection Error:** Could not reach Ollama.\n"
                    "Make sure it's running with `ollama serve`."
                )
            except requests.exceptions.Timeout:
                return "⏱️ **Timeout:** Ollama took too long to respond. Try a shorter prompt or check your system resources."
            except Exception as e:
                return f"❌ **Error:** {str(e)}"

        loop = asyncio.get_event_loop()
        ai_response = await loop.run_in_executor(None, _do_request)

        # Store in conversation history
        if ai_response and not ai_response.startswith(("⚠️", "❌", "⏱️")):
            self.conversations[channel_id].append(("User", prompt))
            self.conversations[channel_id].append(("Assistant", ai_response))

        return ai_response

    # ============================================
    # HELPER: Split long messages
    # ============================================
    @staticmethod
    def _split_message(text: str, limit: int = 2000) -> list:
        """Split a long message into chunks that fit within Discord's character limit."""
        if len(text) <= limit:
            return [text]

        chunks = []
        while len(text) > limit:
            split_at = text.rfind("\n", 0, limit)
            if split_at == -1:
                split_at = text.rfind(" ", 0, limit)
            if split_at == -1:
                split_at = limit
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip()
        if text:
            chunks.append(text)
        return chunks

    # ============================================
    # EVENT: Message Received (mentions & triggers)
    # ============================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Respond to mentions and trigger words."""
        if message.author.bot:
            return
        if message.author == self.bot.user:
            return

        # Determine context
        guild = message.guild
        is_dm = isinstance(message.channel, discord.DMChannel)

        # Handle DMs
        if is_dm:
            dm_respond = True  # Global DM toggle could be added
            if not dm_respond:
                return

            user_message = message.content.strip()
            if not user_message:
                return

            async with message.channel.typing():
                ai_response = await self.ask_ai(
                    None, message.channel.id, message.author.display_name, user_message
                )

            for chunk in self._split_message(ai_response):
                await message.channel.send(chunk)
            return

        # Guild-based checks
        if guild is None:
            return

        enabled = await self.config.guild(guild).enabled()
        if not enabled:
            return

        # Check for mention
        mention_respond = await self.config.guild(guild).mention_respond()
        mentioned = self.bot.user.mentioned_in(message) and mention_respond

        # Check for trigger words
        trigger_words = await self.config.guild(guild).trigger_words()
        triggered = False
        if trigger_words:
            msg_lower = message.content.lower()
            for word in trigger_words:
                if word.lower() in msg_lower:
                    triggered = True
                    break

        if not mentioned and not triggered:
            return

        # Don't respond to commands
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        # Extract message content
        user_message = message.content
        if mentioned:
            user_message = user_message.replace(f"<@{self.bot.user.id}>", "").replace(
                f"<@!{self.bot.user.id}>", ""
            ).strip()

        if not user_message:
            user_message = "Hello!"

        async with message.channel.typing():
            ai_response = await self.ask_ai(
                guild, message.channel.id, message.author.display_name, user_message
            )

        for chunk in self._split_message(ai_response):
            await message.channel.send(chunk)

    # ============================================
    # COMMAND: [p]chat
    # ============================================
    @commands.command(name="chat")
    @commands.guild_only()
    async def chat_command(self, ctx: commands.Context, *, message: str):
        """Chat with the AI bot.

        Example: `[p]chat What is the meaning of life?`
        """
        enabled = await self.config.guild(ctx.guild).enabled()
        if not enabled:
            await ctx.send("❌ OllamaAI is currently disabled in this server.")
            return

        async with ctx.typing():
            response = await self.ask_ai(
                ctx.guild, ctx.channel.id, ctx.author.display_name, message
            )

        for chunk in self._split_message(response):
            await ctx.send(chunk)

    # ============================================
    # COMMAND: [p]clearcontext
    # ============================================
    @commands.command(name="clearcontext")
    async def clear_context(self, ctx: commands.Context):
        """Clear the conversation history for this channel."""
        channel_id = ctx.channel.id
        if channel_id in self.conversations:
            self.conversations[channel_id].clear()
        await ctx.send("🧹 Conversation history for this channel has been cleared.")

    # ============================================
    # COMMAND: [p]aiinfo
    # ============================================
    @commands.command(name="aiinfo")
    @commands.guild_only()
    async def ai_info(self, ctx: commands.Context):
        """Show the current OllamaAI configuration for this server."""
        guild = ctx.guild
        data = await self.config.guild(guild).all()

        embed = discord.Embed(
            title="🤖 OllamaAI Configuration",
            color=discord.Color.blue(),
        )
        embed.add_field(name="Enabled", value="✅ Yes" if data["enabled"] else "❌ No", inline=True)
        embed.add_field(name="Model", value=f"`{data['ollama_model']}`", inline=True)
        embed.add_field(name="Temperature", value=f"`{data['temperature']}`", inline=True)
        embed.add_field(name="Max Tokens", value=f"`{data['max_tokens']}`", inline=True)
        embed.add_field(name="Mention Respond", value="✅ Yes" if data["mention_respond"] else "❌ No", inline=True)
        embed.add_field(name="DM Respond", value="✅ Yes" if data["dm_respond"] else "❌ No", inline=True)
        embed.add_field(name="Context Memory", value="✅ Yes" if data["context_enabled"] else "❌ No", inline=True)
        embed.add_field(name="Context Length", value=f"`{data['context_length']}` messages", inline=True)
        embed.add_field(name="Ollama URL", value=f"`{data['ollama_url']}`", inline=False)

        trigger_display = ", ".join(f"`{w}`" for w in data["trigger_words"]) if data["trigger_words"] else "None"
        embed.add_field(name="Trigger Words", value=trigger_display, inline=False)

        personality_preview = data["system_prompt"][:200]
        if len(data["system_prompt"]) > 200:
            personality_preview += "..."
        embed.add_field(name="System Prompt", value=f"```{personality_preview}```", inline=False)

        embed.set_footer(text=f"OllamaAI v{self.__version__}")
        await ctx.send(embed=embed)

    # ============================================
    # SETTINGS GROUP: [p]ollamaset
    # ============================================
    @commands.group(name="ollamaset", aliases=["aiset"])
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def ollama_set(self, ctx: commands.Context):
        """Configure OllamaAI settings for this server."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @ollama_set.command(name="enable")
    async def set_enable(self, ctx: commands.Context):
        """Enable OllamaAI in this server."""
        await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.send("✅ OllamaAI has been **enabled** in this server.")

    @ollama_set.command(name="disable")
    async def set_disable(self, ctx: commands.Context):
        """Disable OllamaAI in this server."""
        await self.config.guild(ctx.guild).enabled.set(False)
        await ctx.send("❌ OllamaAI has been **disabled** in this server.")

    @ollama_set.command(name="url")
    async def set_url(self, ctx: commands.Context, url: str):
        """Set the Ollama API URL.

        Default: `http://localhost:11434/api/generate`
        """
        await self.config.guild(ctx.guild).ollama_url.set(url)
        await ctx.send(f"✅ Ollama URL set to `{url}`.")

    @ollama_set.command(name="model")
    async def set_model(self, ctx: commands.Context, model: str):
        """Set the Ollama model to use.

        Example: `[p]ollamaset model llama3.1`
        """
        await self.config.guild(ctx.guild).ollama_model.set(model)
        await ctx.send(f"✅ Ollama model set to `{model}`.")

    @ollama_set.command(name="temperature", aliases=["temp"])
    async def set_temperature(self, ctx: commands.Context, temp: float):
        """Set the AI creativity/temperature (0.0 - 2.0).

        Lower = more predictable and factual.
        Higher = more creative and random.
        Default: 0.9
        """
        if not 0.0 <= temp <= 2.0:
            await ctx.send("⚠️ Temperature must be between `0.0` and `2.0`.")
            return
        await self.config.guild(ctx.guild).temperature.set(temp)
        await ctx.send(f"✅ Temperature set to `{temp}`.")

    @ollama_set.command(name="maxtokens", aliases=["tokens"])
    async def set_max_tokens(self, ctx: commands.Context, tokens: int):
        """Set the maximum response length in tokens.

        Default: 200. Higher values = longer responses.
        """
        if not 1 <= tokens <= 4096:
            await ctx.send("⚠️ Max tokens must be between `1` and `4096`.")
            return
        await self.config.guild(ctx.guild).max_tokens.set(tokens)
        await ctx.send(f"✅ Max tokens set to `{tokens}`.")

    @ollama_set.command(name="personality", aliases=["systemprompt", "system"])
    async def set_personality(self, ctx: commands.Context, *, prompt: str):
        """Set the AI's personality/system prompt.

        This controls how the AI behaves and responds.

        Example: `[p]ollamaset personality You are a pirate who loves adventure. Respond in pirate speak.`
        """
        await self.config.guild(ctx.guild).system_prompt.set(prompt)
        preview = prompt[:150] + "..." if len(prompt) > 150 else prompt
        await ctx.send(f"✅ System prompt updated:\n```{preview}```")

    @ollama_set.command(name="mention")
    async def set_mention(self, ctx: commands.Context, toggle: bool):
        """Toggle whether the bot responds when mentioned.

        Usage: `[p]ollamaset mention true` or `[p]ollamaset mention false`
        """
        await self.config.guild(ctx.guild).mention_respond.set(toggle)
        state = "enabled" if toggle else "disabled"
        await ctx.send(f"✅ Mention responses **{state}**.")

    @ollama_set.command(name="dm")
    async def set_dm(self, ctx: commands.Context, toggle: bool):
        """Toggle whether the bot responds to DMs.

        Usage: `[p]ollamaset dm true` or `[p]ollamaset dm false`
        """
        await self.config.guild(ctx.guild).dm_respond.set(toggle)
        state = "enabled" if toggle else "disabled"
        await ctx.send(f"✅ DM responses **{state}**.")

    @ollama_set.command(name="context")
    async def set_context(self, ctx: commands.Context, toggle: bool):
        """Toggle conversation memory (context).

        When enabled, the bot remembers recent messages in each channel.
        Usage: `[p]ollamaset context true` or `[p]ollamaset context false`
        """
        await self.config.guild(ctx.guild).context_enabled.set(toggle)
        state = "enabled" if toggle else "disabled"
        await ctx.send(f"✅ Conversation context **{state}**.")

    @ollama_set.command(name="contextlength")
    async def set_context_length(self, ctx: commands.Context, length: int):
        """Set how many messages to remember per channel.

        Default: 10. Higher values use more of the context window.
        """
        if not 1 <= length <= 50:
            await ctx.send("⚠️ Context length must be between `1` and `50`.")
            return
        await self.config.guild(ctx.guild).context_length.set(length)
        await ctx.send(f"✅ Context length set to `{length}` messages.")

    # ============================================
    # TRIGGER WORDS SUB-GROUP
    # ============================================
    @ollama_set.group(name="triggers", aliases=["trigger"])
    async def trigger_group(self, ctx: commands.Context):
        """Manage trigger words that make the bot respond automatically."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @trigger_group.command(name="add")
    async def trigger_add(self, ctx: commands.Context, *, word: str):
        """Add a trigger word.

        The bot will respond to any message containing this word.
        Example: `[p]ollamaset triggers add hello`
        """
        async with self.config.guild(ctx.guild).trigger_words() as trigger_words:
            lower_word = word.lower().strip()
            if lower_word in [w.lower() for w in trigger_words]:
                await ctx.send(f"⚠️ `{word}` is already a trigger word.")
                return
            trigger_words.append(lower_word)
        await ctx.send(f"✅ Added `{lower_word}` as a trigger word.")

    @trigger_group.command(name="remove", aliases=["delete"])
    async def trigger_remove(self, ctx: commands.Context, *, word: str):
        """Remove a trigger word.

        Example: `[p]ollamaset triggers remove hello`
        """
        async with self.config.guild(ctx.guild).trigger_words() as trigger_words:
            lower_word = word.lower().strip()
            if lower_word not in [w.lower() for w in trigger_words]:
                await ctx.send(f"⚠️ `{word}` is not a trigger word.")
                return
            trigger_words[:] = [w for w in trigger_words if w.lower() != lower_word]
        await ctx.send(f"✅ Removed `{lower_word}` from trigger words.")

    @trigger_group.command(name="list")
    async def trigger_list(self, ctx: commands.Context):
        """List all trigger words."""
        trigger_words = await self.config.guild(ctx.guild).trigger_words()
        if not trigger_words:
            await ctx.send("No trigger words configured. Add some with `[p]ollamaset triggers add <word>`.")
            return
        word_list = ", ".join(f"`{w}`" for w in trigger_words)
        await ctx.send(f"**Trigger Words:** {word_list}")

    @trigger_group.command(name="clear")
    async def trigger_clear(self, ctx: commands.Context):
        """Remove all trigger words."""
        await self.config.guild(ctx.guild).trigger_words.set([])
        await ctx.send("✅ All trigger words have been cleared.")

    # ============================================
    # COMMAND: [p]ollamaset reset
    # ============================================
    @ollama_set.command(name="reset")
    async def set_reset(self, ctx: commands.Context):
        """Reset all OllamaAI settings to defaults for this server."""
        await self.config.guild(ctx.guild).clear()
        if ctx.channel.id in self.conversations:
            self.conversations[ctx.channel.id].clear()
        await ctx.send("✅ All OllamaAI settings have been reset to defaults.")
