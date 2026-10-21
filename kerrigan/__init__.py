from .kerrigan import Kerrigan


async def setup(bot):
    await bot.add_cog(Kerrigan(bot))
