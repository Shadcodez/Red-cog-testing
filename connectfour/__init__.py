from .connectfour import ConnectFour


async def setup(bot):
    await bot.add_cog(ConnectFour(bot))
