from .pixelart import PixelArt

async def setup(bot):
    await bot.add_cog(PixelArt(bot))