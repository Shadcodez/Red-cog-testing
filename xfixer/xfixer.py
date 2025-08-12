import re
import discord

from redbot.core import commands
from redbot.core.bot import Red

class XFixer(commands.Cog):
    """
    A cog to automatically replace x.com links with fixvx.com for better video embeds.
    
    This cog listens for messages in the chat and when it detects a URL
    pointing to "x.com", it replaces it with "fixvx.com" and sends the
    corrected message to the channel. This is based on the service
    provided by BetterTwitFix (https://github.com/dylanpdx/BetterTwitFix).
    """

    # The __init__ method is where we set up the cog
    def __init__(self, bot: Red):
        self.bot = bot
        # We compile the regex pattern here for efficiency.
        # This pattern looks for 'http://x.com' or 'https://x.com', case-insensitively.
        self.x_url_pattern = re.compile(r"https?://x\.com", re.IGNORECASE)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        The core listener that gets called for every message sent in the server.
        """
        # 1. Ignore messages from bots to prevent loops and unwanted behavior.
        if message.author.bot:
            return

        # 2. Check if the message content is valid and contains 'x.com'.
        #    This is a quick check before we run the more expensive regex operation.
        if not message.content or "x.com" not in message.content.lower():
            return
            
        # 3. Use our compiled regex to find and replace URLs.
        #    The re.sub() function is perfect for this, as it handles multiple
        #    occurrences in a single pass.
        new_content, num_replacements = self.x_url_pattern.subn("https://fixvx.com", message.content)

        # 4. If at least one replacement was made, send the new message.
        if num_replacements > 0:
            # We ensure the bot has permissions to send messages in the channel.
            if not message.channel.permissions_for(message.guild.me).send_messages:
                # If the bot can't send a message, it shouldn't try.
                # You could add logging here if you wanted.
                return

            # Construct a user-friendly message that attributes the original link.
            response_message = f"Here is a fixed link from {message.author.mention}:\n{new_content}"
            
            # To prevent the bot from pinging everyone, we'll control mentions.
            # This allows mentions for the original author but not @everyone or @here.
            allowed_mentions = discord.AllowedMentions(
                everyone=False, users=True, roles=False, replied_user=False
            )

            await message.channel.send(response_message, allowed_mentions=allowed_mentions)
