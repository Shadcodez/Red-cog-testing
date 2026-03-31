from redbot.core import commands
from .excelembeds import excelembed

async def setup(bot: commands.Bot):
    await bot.add_cog(excelembed(bot))
