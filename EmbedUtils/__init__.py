from redbot.core.bot import Red

from .embedutils import EmbedUtils

__red_end_user_data_statement__ = (
    "This cog stores the Discord user ID of anyone who saves an embed, "
    "along with the embed payload and usage count. If a user requests data "
    "deletion, every embed they authored is removed."
)


async def setup(bot: Red) -> None:
    await bot.add_cog(EmbedUtils(bot))
