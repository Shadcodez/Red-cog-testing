from redbot.core import commands, Config

from .witcher import Witcher

__red_end_user_data_statement__ = (
    "This cog stores your Discord user id, campaign progress, inventory, "
    "romance opt-in, and resume codes in Red's config so a game can follow you "
    "between channels and servers."
)


async def setup(bot):
    # A failed load can leave the slash command on Red's tree. Clear it or the next load dies.
    bot.tree.remove_command("witcher_scene", type=None)
    await bot.add_cog(Witcher(bot))
