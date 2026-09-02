from .void import Void


async def setup(bot):
    await bot.add_cog(Void(bot))
