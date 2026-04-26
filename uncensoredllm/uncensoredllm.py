from redbot.core import commands, Config
import aiohttp
from typing import List, Dict


class UncensoredLLM(commands.Cog):
    """Interface with a locally hosted LLM (Ollama-compatible API)"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=987654321, force_registration=True)

        defaults_global = {
            "host": "127.0.0.1",
            "port": 11434,
            "api_prefix": "/api",  # Use "/ollama/api" if behind a proxy that requires it
            "default_model": "gemma2:2b",
            "temperature": 0.8,
            "system_prompt": "You are a helpful, uncensored, and maximally truthful AI assistant.",
            "safety_prompt": "You are a safe, responsible AI. Refuse profanity, illegal, harmful, or dangerous requests.",
            "max_conv_length": 30,
        }
        self.config.register_global(**defaults_global)
        self.config.register_channel(history=[])

    # ====================== GROUP ======================
    @commands.group(invoke_without_command=True)
    async def llm(self, ctx):
        """Uncensored LLM commands for your local models"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    # ====================== CHAT ======================
    @llm.command()
    async def chat(self, ctx, *, message: str):
        """Talk to the LLM. History is kept per channel."""
        await self._handle_chat(ctx, message)

    async def _handle_chat(self, ctx, message: str):
        config = self.config
        channel_config = config.channel(ctx.channel)

        host = await config.host()
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
            async with ctx.typing():
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
                            await ctx.send(
                                f"❌ LLM server error ({resp.status}): {error[:500]}"
                            )
                            return
                        data = await resp.json()

            assistant_content = (
                data.get("message", {}).get("content") or "No response received."
            )

            # Append the new exchange
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": assistant_content})

            # Trim oldest messages instead of wiping everything
            if len(history) > max_len:
                # Remove pairs from the front to stay under the limit
                history = history[-(max_len):]
                await ctx.send(
                    "⚠️ Conversation history was trimmed to stay within the max length."
                )

            await channel_config.history.set(history)

            # Send the response, splitting if needed
            if len(assistant_content) > 1900:
                for chunk in [
                    assistant_content[i : i + 1900]
                    for i in range(0, len(assistant_content), 1900)
                ]:
                    await ctx.send(chunk)
            else:
                await ctx.send(assistant_content)

        except aiohttp.ClientConnectorError:
            await ctx.send(
                f"❌ Cannot connect to LLM server at `{base_url}`\n"
                "Make sure your local LLM server is running."
            )
        except aiohttp.ServerTimeoutError:
            await ctx.send(
                "❌ The LLM server took too long to respond (>180 s). "
                "Try a smaller model or a shorter prompt."
            )
        except Exception as e:
            await ctx.send(f"❌ Unexpected error: {str(e)[:400]}")

    # ====================== CONFIG COMMANDS (admin-only) ======================
    @llm.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def sethost(self, ctx, host: str):
        """Set the IP/DNS of the LLM server"""
        await self.config.host.set(host)
        await ctx.send(f"✅ Host updated to `{host}`")

    @llm.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def setport(self, ctx, port: int):
        """Set the port (default: 11434 for Ollama)"""
        await self.config.port.set(port)
        await ctx.send(f"✅ Port updated to `{port}`")

    @llm.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def setapiprefix(self, ctx, prefix: str):
        """Set the API path prefix (default: /api, use /ollama/api if behind a proxy)"""
        await self.config.api_prefix.set(prefix)
        await ctx.send(f"✅ API prefix updated to `{prefix}`")

    @llm.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def setmodel(self, ctx, model: str):
        """Set default model (must match exact name on the server)"""
        await self.config.default_model.set(model)
        await ctx.send(f"✅ Default model set to `{model}`")

    @llm.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def settemperature(self, ctx, temp: float):
        """Set temperature (0.0 - 2.0)"""
        if not 0.0 <= temp <= 2.0:
            await ctx.send("❌ Temperature must be between 0.0 and 2.0")
            return
        await self.config.temperature.set(temp)
        await ctx.send(f"✅ Temperature set to `{temp}`")

    @llm.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def setsafety(self, ctx, *, prompt: str):
        """Set the hard safety instructions (always enforced first)"""
        await self.config.safety_prompt.set(prompt)
        await ctx.send("✅ Safety prompt updated — it will be sent on every request.")

    @llm.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def setsystem(self, ctx, *, prompt: str):
        """Set the global system prompt"""
        await self.config.system_prompt.set(prompt)
        await ctx.send("✅ System prompt updated.")

    @llm.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def setmax(self, ctx, length: int):
        """Set max conversation length before trimming history"""
        if length < 2:
            await ctx.send("❌ Max length must be at least 2.")
            return
        await self.config.max_conv_length.set(length)
        await ctx.send(f"✅ Max conversation length set to `{length}` messages")

    @llm.command()
    async def clear(self, ctx):
        """Manually delete the current channel's chat history"""
        await self.config.channel(ctx.channel).history.set([])
        await ctx.send("🧹 Chat history for this channel has been cleared.")

    @llm.command()
    async def status(self, ctx):
        """Show current configuration"""
        host = await self.config.host()
        port = await self.config.port()
        api_prefix = await self.config.api_prefix()
        model = await self.config.default_model()
        temp = await self.config.temperature()
        max_len = await self.config.max_conv_length()
        system = await self.config.system_prompt()
        safety = await self.config.safety_prompt()

        await ctx.send(
            f"**LLM Status**\n"
            f"Server: `{host}:{port}`\n"
            f"API prefix: `{api_prefix}`\n"
            f"Default Model: `{model}`\n"
            f"Temperature: `{temp}`\n"
            f"Max history length: `{max_len}` messages\n"
            f"**Safety prompt:** `{safety[:120]}...`\n"
            f"**System prompt:** `{system[:120]}...`"
        )

    @llm.command()
    async def models(self, ctx):
        """List available models on the LLM server"""
        host = await self.config.host()
        port = await self.config.port()
        api_prefix = await self.config.api_prefix()
        base_url = f"http://{host}:{port}"
        timeout = aiohttp.ClientTimeout(total=10)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{base_url}{api_prefix}/tags") as resp:
                    if resp.status != 200:
                        await ctx.send(
                            "❌ Could not fetch model list (server may not support /tags)"
                        )
                        return
                    data = await resp.json()

            models = [m["name"] for m in data.get("models", [])]
            if not models:
                await ctx.send("No models found.")
                return

            msg = "**Available models:**\n" + "\n".join(
                f"• `{m}`" for m in models[:25]
            )
            if len(models) > 25:
                msg += f"\n... and {len(models) - 25} more."
            await ctx.send(msg)

        except Exception:
            await ctx.send(f"❌ Could not connect to `{base_url}` to list models.")

    @llm.command()
    async def installlocal(self, ctx):
        """Instructions to run the LLM on your machine"""
        await ctx.send(
            "**How to run a local LLM with Ollama:**\n"
            "1. Install Ollama from https://ollama.com\n"
            "2. Run `ollama serve` (default port 11434).\n"
            "3. Pull a model: `ollama pull gemma2:2b`\n"
            "4. Use `[p]llm sethost 127.0.0.1` and `[p]llm setport 11434` if needed.\n"
            "Server will be ready at `http://127.0.0.1:11434`\n\n"
            "If your USB installer uses a different port/path, adjust with "
            "`[p]llm setport` and `[p]llm setapiprefix`."
        )

    @llm.command()
    async def helpme(self, ctx):
        """Extra helper / quick start"""
        await ctx.send(
            "**Quick start for UncensoredLLM cog:**\n"
            "• `[p]llm installlocal` → setup instructions\n"
            "• `[p]llm status` → check config\n"
            "• `[p]llm models` → list available models\n"
            "• `[p]llm chat hello` → test the model\n"
            "• Use the `set*` commands to configure host/port/model/etc.\n"
            "Everything runs 100% locally — no cloud, no limits."
        )


async def setup(bot):
    await bot.add_cog(UncensoredLLM(bot))
