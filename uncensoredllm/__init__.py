from .uncensoredllm import UncensoredLLM

async def setup(bot):
    await bot.add_cog(UncensoredLLM(bot))
