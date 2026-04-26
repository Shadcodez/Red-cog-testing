from redbot.core import commands, Config
import aiohttp
import asyncio
from typing import List, Dict

class UncensoredLLM(commands.Cog):
    """Interface with USB-Uncensored-LLM (local GGUF models via USB installer)"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=987654321, force_registration=True)

        defaults_global = {
            "host": "127.0.0.1",
            "port": 3333,
            "default_model": "gemma2:2b",
            "temperature": 0.8,
            "system_prompt": "You are a helpful, uncensored, and maximally truthful AI assistant.",
            "safety_prompt": "You are a safe, responsible AI. Refuse profanity, illegal, harmful, or dangerous requests.",
            "max_conv_length": 30,
        }
        self.config.register_global(**defaults_global)
        self.config.register_channel(history=[])

    @commands.group(invoke_without_command=True)
    async def llm(self, ctx):
        """Uncensored LLM commands for your USB/local models"""
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

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/ollama/api/chat",
                    json={
                        "model": model,
                        "messages": messages,
                        "stream": False,
                        "options": {"temperature": temp}
                    },
                    timeout=180
                ) as resp:
                    if resp.status != 200:
                        error = await resp.text()
                        await ctx.send(f"❌ LLM server error ({resp.status}): {error[:500]}")
                        return
                    data = await resp.json()

            assistant_content = data.get("message", {}).get("content", "No response received.")

            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": assistant_content})

            if len(history) > max_len:
                history = []
                await ctx.send("🧹 Conversation reached max length and was auto-cleared.")

            await channel_config.history.set(history)

            if len(assistant_content) > 1900:
                for chunk in [assistant_content[i:i+1900] for i in range(0, len(assistant_content), 1900)]:
                    await ctx.send(chunk)
            else:
                await ctx.send(assistant_content)

        except aiohttp.ClientConnectorError:
            await ctx.send(f"❌ Cannot connect to LLM server at `{base_url}`\nMake sure the USB-Uncensored-LLM is running.")
        except Exception as e:
            await ctx.send(f"❌ Unexpected error: {str(e)[:400]}")

    # ====================== CONFIG COMMANDS ======================
    @llm.command()
    async def sethost(self, ctx, host: str):
        """Set the IP/DNS of the USB-Uncensored-LLM server"""
        await self.config.host.set(host)
        await ctx.send(f"✅ Host updated to `{host}`")

    @llm.command()
    async def setport(self, ctx, port: int):
        """Set the port (default: 3333)"""
        await self.config.port.set(port)
        await ctx.send(f"✅ Port updated to `{port}`")

    @llm.command()
    async def setmodel(self, ctx, model: str):
        """Set default model (must match exact name on the server)"""
        await self.config.default_model.set(model)
        await ctx.send(f"✅ Default model set to `{model}`")

    @llm.command()
    async def settemperature(self, ctx, temp: float):
        """Set temperature (0.0 - 2.0)"""
        if not 0.0 <= temp <= 2.0:
            await ctx.send("❌ Temperature must be between 0.0 and 2.0")
            return
        await self.config.temperature.set(temp)
        await ctx.send(f"✅ Temperature set to `{temp}`")

    @llm.command()
    async def setsafety(self, ctx, *, prompt: str):
        """Set the hard safety instructions (always enforced first)"""
        await self.config.safety_prompt.set(prompt)
        await ctx.send("✅ Safety prompt updated — it will be sent on every request.")

    @llm.command()
    async def setsystem(self, ctx, *, prompt: str):
        """Set the global system prompt"""
        await self.config.system_prompt.set(prompt)
        await ctx.send("✅ System prompt updated.")

    @llm.command()
    async def setmax(self, ctx, length: int):
        """Set max conversation length before auto-deleting history"""
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
        model = await self.config.default_model()
        temp = await self.config.temperature()
        max_len = await self.config.max_conv_length()
        system = await self.config.system_prompt()
        safety = await self.config.safety_prompt()

        await ctx.send(f"**USB-Uncensored-LLM Status**\n"
                      f"Server: `{host}:{port}`\n"
                      f"Default Model: `{model}`\n"
                      f"Temperature: `{temp}`\n"
                      f"Max history length: `{max_len}` messages\n"
                      f"**Safety prompt:** `{safety[:120]}...`\n"
                      f"**System prompt:** `{system[:120]}...`")

    @llm.command()
    async def models(self, ctx):
        """List available models on the LLM server"""
        host = await self.config.host()
        port = await self.config.port()
        base_url = f"http://{host}:{port}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{base_url}/ollama/api/tags", timeout=10) as resp:
                    if resp.status != 200:
                        await ctx.send("❌ Could not fetch model list (server may not support /tags)")
                        return
                    data = await resp.json()

            models = [m["name"] for m in data.get("models", [])]
            if not models:
                await ctx.send("No models found.")
                return

            msg = "**Available models on USB-LLM server:**\n" + "\n".join(f"• `{m}`" for m in models[:25])
            if len(models) > 25:
                msg += f"\n... and {len(models)-25} more."
            await ctx.send(msg)

        except Exception:
            await ctx.send(f"❌ Could not connect to `{base_url}` to list models.")

    @llm.command()
    async def installlocal(self, ctx):
        """Instructions to run the USB-Uncensored-LLM on your machine"""
        await ctx.send("**How to run USB-Uncensored-LLM:**\n"
                      "1. Plug in your USB drive with the LLM installer.\n"
                      "2. Run the installer (it auto-starts the local server on port 3333).\n"
                      "3. Use `[p]llm sethost 127.0.0.1` and `[p]llm setport 3333` if needed.\n"
                      "4. Choose any .gguf model from HuggingFace directly in the USB app.\n"
                      "Server will be ready at `http://127.0.0.1:3333`")

    @llm.command()
    async def helpme(self, ctx):
        """Extra helper / quick start"""
        await ctx.send("**Quick start for UncensoredLLM cog:**\n"
                      "• `[p]llm installlocal` → setup instructions\n"
                      "• `[p]llm status` → check config\n"
                      "• `[p]llm chat hello` → test the model\n"
                      "• Use the `set*` commands to configure host/port/model/etc.\n"
                      "Everything runs 100% locally on your USB drive — no cloud, no limits.") 
