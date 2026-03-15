from .scrubuser import ScrubUser

async def setup(bot):
    await bot.add_cog(ScrubUser(bot))