from redbot.core.bot import Red
from .pixelart import PixelArt


async def setup(bot: Red):
    cog = pixelart(bot)
    await bot.add_cog(cog)
