from redbot.core import commands, Config
import aiohttp
import asyncio  # ← needed for the 1-second typing delay
from typing import List, Dict
from urllib.parse import urlparse


class UncensoredLLM(commands.Cog):
    """Interface with a locally hosted LLM (USB-Uncensored-LLM compatible)"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=987654321, force_registration=True)

        defaults_global = {
            "host": "127.0.0.1",
            "port": 3333,
            "api_prefix": "/ollama/api",
            "default_model": "gemma2:2b",
            "temperature": 0.8,
            "system_prompt": "You are a helpful, uncensored, and maximally truthful AI assistant.",
            "safety_prompt": "You are a safe, responsible AI. Refuse profanity, illegal, harmful, or dangerous requests.",
            "max_conv_length": 30,
            "respond_to_mentions": True,
            "show_typing": True,  # ← default ON: shows a brief 1-second typing indicator
        }
        self.config.register_global(**defaults_global)
        self.config.register_channel(history=[])

    def _sanitize_host(self, raw: str) -> str:
        """Automatically clean IP, domain, or full URL input."""
        if not raw:
            return "127.0.0.1"
        if "://" not in raw:
            raw = f"http://{raw}"
        parsed = urlparse(raw)
        host = parsed.hostname or parsed.path.split(":", 1)[0] or raw
        if ":" in host and not host.startswith("["):
            host = host.split(":", 1)[0]
        return host

    # ====================== GROUP ======================
    @commands.group(invoke_without_command=True)
    async def uncensoredllm(self, ctx):
        """UncensoredLLM commands for your local models"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    # ====================== AUTO-REPLY ON PING ======================
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        # Let Red handle any prefixed commands first
        ctx = await self.bot.get_context(message)
        if ctx.command is not None:
            return

        # Only respond if mention response is enabled
        if not await self.config.respond_to_mentions():
            return

        # Check if the bot was actually mentioned
        if self.bot.user not in message.mentions:
            return

        # Strip the mention from the message
        content = message.content.replace(f"<@{self.bot.user.id}>", "").strip()
        content = content.replace(f"<@!{self.bot.user.id}>", "").strip()
        if not content:
            return  # empty message after stripping mention

        # Trigger the same chat handler
        await self._handle_chat(ctx, content)

    # ====================== CHAT COMMAND ======================
    @uncensoredllm.command()
    async def chat(self, ctx, *, message: str):
        """Talk to the LLM. History is kept per channel."""
        await self._handle_chat(ctx, message)

    async def _handle_chat(self, ctx, message: str):
        config = self.config
        channel_config = config.channel(ctx.channel)

        raw_host = await config.host()
        host = self._sanitize_host(raw_host)
        if host != raw_host:
            await config.host.set(host)

        port = await config.port()
        api_prefix = await config.api_prefix()
        model = await config.default_model()
        temp = await config.temperature()
        system = await config.system_prompt()
        safety = await config.safety_prompt()
        max_len = await config.max_conv_length()

        base_url = f"http://{host}:{port}"

        history: List[Dict] = await channel_config.history()

        messages = [
            {"role": "system", "content": safety},
            {"role": "system", "content": system},
        ]
        messages.extend(history)
        messages.append({"role": "user", "content": message})

        timeout = aiohttp.ClientTimeout(total=180)

        try:
            # === FIXED TYPING LOGIC (1-second brief indicator) ===
            # When enabled (default): shows "Bot is typing..." for exactly 1 second
            # so the user immediately knows the bot received the message.
            # This completely avoids Discord rate limiting on the typing endpoint.
            show_typing = await self.config.show_typing()

            if show_typing:
                await ctx.channel.trigger_typing()      # ← FIXED: correct method
                await asyncio.sleep(1)                  # hold it visible for 1 second

            # Now do the actual LLM request (no typing context manager)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{base_url}{api_prefix}/chat",
                    json={
                        "model": model,
                        "messages": messages,
                        "stream": False,
                        "options": {"temperature": temp},
                    },
                ) as resp:
                    if resp.status != 200:
                        error = await resp.text()
                        await ctx.send(f"LLM server error ({resp.status}): {error[:500]}")
                        return
                    data = await resp.json()

            assistant_content = (
                data.get("message", {}).get("content") or "No response received."
            )

            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": assistant_content})

            if len(history) > max_len:
                history = history[-(max_len):]
                await ctx.send("...")

            await channel_config.history.set(history)

            if len(assistant_content) > 1900:
                for chunk in [assistant_content[i:i+1900] for i in range(0, len(assistant_content), 1900)]:
                    await ctx.send(chunk)
            else:
                await ctx.send(assistant_content)

        except aiohttp.ClientConnectorError:
            await ctx.send("Cannot connect to the LLM server.\nMake sure the server is running on the second machine and port 3333 is open.")
        except aiohttp.ServerTimeoutError:
            await ctx.send("The LLM server took too long to respond (>180 s). Try a smaller model or shorter prompt.")
        except Exception as e:
            await ctx.send(f"Unexpected error: {str(e)[:300]}")

    # ====================== OWNER-ONLY CONFIG ======================
    @uncensoredllm.command()
    @commands.is_owner()
    async def sethost(self, ctx, host: str):
        """Set the IP/DNS of the LLM server (Owner only)."""
        clean_host = self._sanitize_host(host)
        await self.config.host.set(clean_host)
        await ctx.send(f"Host updated to `{clean_host}`")

    @uncensoredllm.command()
    @commands.is_owner()
    async def setport(self, ctx, port: int):
        """Set the port (Owner only)"""
        await self.config.port.set(port)
        await ctx.send(f"Port updated to `{port}`")

    @uncensoredllm.command()
    @commands.is_owner()
    async def setapiprefix(self, ctx, prefix: str):
        """Set the API path prefix (Owner only)"""
        await self.config.api_prefix.set(prefix)
        await ctx.send(f"API prefix updated to `{prefix}`")

    @uncensoredllm.command()
    @commands.is_owner()
    async def setmodel(self, ctx, model: str):
        """Set default model (Owner only)"""
        await self.config.default_model.set(model)
        await ctx.send(f"Default model set to `{model}`")

    @uncensoredllm.command()
    @commands.is_owner()
    async def settemperature(self, ctx, temp: float):
        """Set temperature (0.0 - 2.0) (Owner only)"""
        if not 0.0 <= temp <= 2.0:
            await ctx.send("Temperature must be between 0.0 and 2.0")
            return
        await self.config.temperature.set(temp)
        await ctx.send(f"Temperature set to `{temp}`")

    @uncensoredllm.command()
    @commands.is_owner()
    async def setsafety(self, ctx, *, prompt: str):
        """Set the hard safety instructions (Owner only)"""
        await self.config.safety_prompt.set(prompt)
        await ctx.send("Safety prompt updated.")

    @uncensoredllm.command()
    @commands.is_owner()
    async def setsystem(self, ctx, *, prompt: str):
        """Set the global system prompt (Owner only)"""
        await self.config.system_prompt.set(prompt)
        await ctx.send("System prompt updated.")

    @uncensoredllm.command()
    @commands.is_owner()
    async def setmax(self, ctx, length: int):
        """Set max conversation length before trimming (Owner only)"""
        if length < 2:
            await ctx.send("Max length must be at least 2.")
            return
        await self.config.max_conv_length.set(length)
        await ctx.send(f"Max conversation length set to `{length}`")

    # ====================== TYPING TOGGLE ======================
    @uncensoredllm.command()
    @commands.is_owner()
    async def settyping(self, ctx, enabled: bool):
        """Toggle the brief 'is typing...' indicator (Owner only).
        
        When ENABLED (default): shows "Bot is typing..." for exactly 1 second
        so users know the bot is responding, then turns off.
        
        This completely prevents Discord rate limiting on the typing endpoint
        while still giving immediate visual feedback.
        
        Use: true / yes / on / 1   or   false / no / off / 0"""
        await self.config.show_typing.set(enabled)
        status = "ENABLED (1-second indicator)" if enabled else "DISABLED"
        await ctx.send(f"✅ Brief typing indicator is now **{status}**.")
