# steal/__init__.py
from redbot.core.bot import Red
from .steal import Steal


async def setup(bot: Red) -> None:
    """Load the Steal cog."""
    cog = Steal(bot)
    await bot.add_cog(cog)
