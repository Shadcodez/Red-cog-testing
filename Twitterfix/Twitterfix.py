import discord
from discord.ext import commands
import re

class TwitterFixer(commands.Cog):
    """A cog that automatically replaces Twitter URLs with fxtwitter URLs for better embeds"""
    
    def __init__(self, bot):
        self.bot = bot
        
        # Regex patterns to match various Twitter URL formats
        self.twitter_patterns = [
            re.compile(r'https?://(?:www\.)?twitter\.com/([^/\s]+/status/\d+(?:\?\S*)?)', re.IGNORECASE),
            re.compile(r'https?://(?:www\.)?x\.com/([^/\s]+/status/\d+(?:\?\S*)?)', re.IGNORECASE),
            re.compile(r'https?://mobile\.twitter\.com/([^/\s]+/status/\d+(?:\?\S*)?)', re.IGNORECASE),
        ]
    
    @commands.Cog.listener()
    async def on_message(self, message):
        # Don't respond to bot messages or messages without content
        if message.author.bot or not message.content:
            return
            
        # Check if the message contains any Twitter URLs
        original_content = message.content
        modified_content = original_content
        found_twitter_url = False
        
        # Apply all patterns to replace Twitter URLs
        for pattern in self.twitter_patterns:
            if pattern.search(modified_content):
                found_twitter_url = True
                modified_content = pattern.sub(r'https://fxtwitter.com/\1', modified_content)
        
        # If we found and replaced Twitter URLs, send the modified message
        if found_twitter_url and modified_content != original_content:
            # Create embed with the fixed URLs
            embed = discord.Embed(
                description=modified_content,
                color=0x1DA1F2  # Twitter blue
            )
            embed.set_author(
                name=message.author.display_name,
                icon_url=message.author.display_avatar.url
            )
            embed.set_footer(text="Twitter URLs converted to fxtwitter for better previews")
            
            # Send the embed
            await message.channel.send(embed=embed)
            
            # Optionally suppress the original message embed (requires manage messages permission)
            try:
                await message.edit(suppress=True)
            except (discord.Forbidden, discord.HTTPException):
                # If we can't suppress embeds, that's okay
                pass

    @commands.command(name='fixtwitter', aliases=['fx'])
    async def fix_twitter_command(self, ctx, *, url: str = None):
        """Manually convert a Twitter URL to fxtwitter URL"""
        if not url:
            await ctx.send("Please provide a Twitter URL to convert!")
            return
            
        original_url = url
        modified_url = url
        
        # Apply patterns to the provided URL
        for pattern in self.twitter_patterns:
            if pattern.search(modified_url):
                modified_url = pattern.sub(r'https://fxtwitter.com/\1', modified_url)
                break
        
        if modified_url != original_url:
            embed = discord.Embed(
                title="Twitter URL Fixed!",
                description=f"**Original:** {original_url}\n**Fixed:** {modified_url}",
                color=0x1DA1F2
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send("No Twitter URLs found in the provided text!")

    @commands.command(name='toggletwitterfix')
    @commands.has_permissions(manage_guild=True)
    async def toggle_twitter_fix(self, ctx):
        """Toggle automatic Twitter URL fixing for this server (Admin only)"""
        # This is a placeholder for server-specific settings
        # You'd need to implement a database or config system for this
        await ctx.send("This feature would require a database to store server preferences!")

# Setup function to add the cog to the bot
async def setup(bot):
    await bot.add_cog(TwitterFixer(bot))

# Alternative setup for older discord.py versions
def setup(bot):
    bot.add_cog(TwitterFixer(bot))
