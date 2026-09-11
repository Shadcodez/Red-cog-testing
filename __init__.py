from .giveaways import Giveaways

__red_end_user_data_statement__ = (
    "This cog stores Discord user IDs of giveaway hosts and entrants, "
    "along with ticket counts, until the giveaway is cleaned up. "
    "No other personal data is stored."
)


async def setup(bot):
    await bot.add_cog(Giveaways(bot))
