# beandip/__init__.py
from .beandip import Beandip


async def setup(bot):
    """Red Discord Bot cog loader (2026 standard)."""
    await bot.add_cog(Beandip(bot))
