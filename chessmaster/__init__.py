from .chessmaster import Chessmaster


async def setup(bot):
    await bot.add_cog(Chessmaster(bot))
