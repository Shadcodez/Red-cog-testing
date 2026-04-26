from .usbuncensoredllm import USBUncensoredLLM

async def setup(bot):
    await bot.add_cog(USBUncensoredLLM(bot))
