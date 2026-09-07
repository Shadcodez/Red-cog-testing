from redbot.core.bot import Red

from .aethergate import AetherGate

__red_end_user_data_statement__ = (
    "This cog stores the Discord user ID of whoever created or adopted a managed "
    "role, plus role IDs and the last permission template applied to channels. "
    "No message content is stored."
)


async def setup(bot: Red) -> None:
    await bot.add_cog(AetherGate(bot))
