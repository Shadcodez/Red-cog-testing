from .mtgcard import MTGCardCog

async def setup(bot):
    """Load the MTGCard cog."""
    cog = MTGCardCog(bot)
    await bot.add_cog(cog)
