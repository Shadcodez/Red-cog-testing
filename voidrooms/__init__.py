from .voidrooms import VoidRooms

async def setup(bot):
    await bot.add_cog(VoidRooms(bot))
