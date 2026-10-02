from .ytsanitizer import YTSanitizer

__red_end_user_data_statement__ = (
    "This cog stores per-server settings only (mode and whether to delete the "
    "original post). It does not store messages, user ids, or link history."
)


async def setup(bot):
    await bot.add_cog(YTSanitizer(bot))
