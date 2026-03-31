from redbot.core import commands
from .excelembed import Excelembed

async def setup(bot: commands.Bot):
    await bot.add_cog(Excelembed(bot))
