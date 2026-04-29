from .ollamaai import OllamaAI


async def setup(bot):
    cog = OllamaAI(bot)
    await bot.add_cog(cog)
