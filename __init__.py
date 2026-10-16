from .cleanupui import CleanupUI

async def setup(bot):
    await bot.add_cog(CleanupUI(bot))
