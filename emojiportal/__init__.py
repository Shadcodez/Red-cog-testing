from .emojiportal import EmojiPortal

async def setup(bot):
    await bot.add_cog(EmojiPortal(bot))
