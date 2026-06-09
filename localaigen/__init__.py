from .localaigen import LocalAIImageGen

async def setup(bot):
    await bot.add_cog(LocalAIImageGen(bot))
