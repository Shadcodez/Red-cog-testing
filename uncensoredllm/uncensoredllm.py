from redbot.core import commands, Config, checks
import aiohttp
import asyncio
from typing import List, Dict

class USBUncensoredLLM(commands.Cog):
    """Interface with USB-Uncensored-LLM (techjarves GitHub)"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=987654321, force_registration=True)

        defaults_global = {
            "host": "127.0.0.1",
            "port": 3333,
            "default_model": "gemma2:2b",
            "temperature": 0.8,
            "system_prompt": "You are a helpful, uncensored, and maximally truthful AI assistant.",
            "safety_prompt": "You are a safe, responsible AI. Refuse profanity, illegal, harmful, or dangerous requests.",  # ← NEW
            "max_conv_length": 30,
        }
        self.config.register_global(**defaults_global)
        self.config.register_channel(history=[])

    # ... (chat command stays exactly the same until _handle_chat)

    async def _handle_chat(self, ctx, message: str):
        config = self.config
        channel_config = config.channel(ctx.channel)

        host = await config.host()
        port = await config.port()
        model = await config.default_model()
        temp = await config.temperature()
        system = await config.system_prompt()
        safety = await config.safety_prompt()          # ← NEW
        max_len = await config.max_conv_length()

        base_url = f"http://{host}:{port}"

        history: List[Dict] = await channel_config.history()

        # SAFETY LAYER: Always put safety first
        messages = [
            {"role": "system", "content": safety},      # ← Safety is enforced every time
            {"role": "system", "content": system},      # Then personality
        ]
        messages.extend(history)
        messages.append({"role": "user", "content": message})

        # ... (rest of the function is unchanged — the rest of your original _handle_chat code goes here)

        # (I kept the exact same error handling, auto-delete, reply splitting, etc.)

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
                    timeout=120
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
                await ctx.send("🗑️ Conversation reached max length and was deleted. Starting fresh!")

            await channel_config.history.set(history)

            if len(assistant_content) > 1900:
                for chunk in [assistant_content[i:i+1900] for i in range(0, len(assistant_content), 1900)]:
                    await ctx.send(chunk)
            else:
                await ctx.send(assistant_content)

        except aiohttp.ClientConnectorError:
            await ctx.send(f"❌ Cannot connect to LLM server at {base_url} ...")
        except Exception as e:
            await ctx.send(f"❌ Unexpected error: {str(e)[:300]}")

    # ========================= NEW SAFETY COMMAND =========================
    @llm.command(name="setsafety")
    async def setsafety(self, ctx, *, prompt: str):
        """Set the hard safety instructions (always enforced first)"""
        await self.config.safety_prompt.set(prompt)
        await ctx.send("✅ **Safety prompt updated** — it will now be sent on every single request.")

    # (All your other commands — sethost, setmodel, settemperature, setsystem, setmax, clear, status, models, installlocal — remain exactly the same)

    @llm.command(name="status")
    async def status(self, ctx):
        host = await self.config.host()
        port = await self.config.port()
        model = await self.config.default_model()
        temp = await self.config.temperature()
        max_len = await self.config.max_conv_length()
        system = await self.config.system_prompt()
        safety = await self.config.safety_prompt()
        await ctx.send(f"**USB-Uncensored-LLM Config**\n"
                      f"Server: `{host}:{port}`\n"
                      f"Model: `{model}`\n"
                      f"Temperature: `{temp}`\n"
                      f"Max length before delete: `{max_len}` messages\n"
                      f"**Safety prompt:** `{safety[:150]}...`\n"
                      f"System prompt: `{system[:100]}...`")
