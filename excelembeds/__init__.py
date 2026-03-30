from redbot.core import commands
from .excelembeds import Excelembeds

async def setup(bot: commands.Bot):
    await bot.add_cog(Excelembeds(bot))
