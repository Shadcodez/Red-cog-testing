from .mtgc import MTGCCog

async def setup(bot):
    await bot.add_cog(MTGCCog(bot))
