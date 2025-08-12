from .xfixer import XFixer
from redbot.core.bot import Red

async def setup(bot: Red):
    cog = XFixer(bot)
    await bot.add_cog(cog)
