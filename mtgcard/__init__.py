from .mtgcard import MTGCard


async def setup(bot):
    await bot.add_cog(MTGCard(bot))
