from redbot.core.bot import Red

from .retrosign import Retrosign

__red_end_user_data_statement__ = (
    "This cog does not persistently store data or metadata about users."
)


async def setup(bot: Red):
    await bot.add_cog(Retrosign(bot))
