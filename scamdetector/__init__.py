from redbot.core.bot import Red
from .scamdetector import ScamDetector

async def setup(bot: Red):
    await bot.add_cog(ScamDetector(bot))
