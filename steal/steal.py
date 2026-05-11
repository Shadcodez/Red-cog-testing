# steal/steal.py
import asyncio
import re
from typing import List, Tuple

import discord
from redbot.core import commands
from redbot.core.bot import Red


class Steal(commands.Cog):
    """DM users pictures of any custom emojis, stickers, or reaction emojis from a replied-to message."""

    def __init__(self, bot: Red):
        self.bot = bot

    @commands.command(name="steal", aliases=["illtakethat", "mine", "yoink"])
    async def steal(self, ctx: commands.Context):
        """DM yourself pictures of all custom emojis, stickers, and reaction emojis from the message you're replying to.

        Reply to any message with this command and the bot will privately send you image embeds of every custom emoji
        (in the message content), every sticker attached to the message, and every custom emoji used in reactions.
        """
        if not ctx.message.reference or not ctx.message.reference.message_id:
            await ctx.send_help(ctx.command)
            await ctx.send("❌ You must **reply** to the target message when using this command.")
            return

        try:
            message: discord.Message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        except discord.NotFound:
            await ctx.send("❌ Could not find the message you replied to.")
            return
        except discord.HTTPException:
            await ctx.send("❌ Failed to fetch the message.")
            return

        assets: List[Tuple[str, str]] = []  # (name, image_url)

        # 1. Custom emojis in message content
        emoji_pattern = r"<(a?):(\w+):(\d+)>"
        for animated, name, emoji_id in re.findall(emoji_pattern, message.content):
            ext = "gif" if animated else "png"
            url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}?size=4096"
            assets.append((name, url))

        # 2. Custom reaction emojis
        for reaction in message.reactions:
            emoji = reaction.emoji
            if isinstance(emoji, (discord.Emoji, discord.PartialEmoji)) and emoji.id is not None:
                url = emoji.url
                assets.append((emoji.name, url))

        # 3. Stickers on the message
        for sticker_item in message.stickers:
            try:
                sticker = await self.bot.fetch_sticker(sticker_item.id)
                assets.append((sticker.name, sticker.url))
            except (discord.NotFound, discord.HTTPException):
                # Fallback CDN URL (works for most static stickers)
                fallback_url = f"https://cdn.discordapp.com/stickers/{sticker_item.id}.png?size=4096"
                assets.append((sticker_item.name, fallback_url))

        # Remove duplicates while preserving first-seen name
        unique_assets: dict[str, str] = {}
        for name, url in assets:
            if url not in unique_assets:
                unique_assets[url] = name

        if not unique_assets:
            await ctx.send("✅ No custom emojis, stickers, or custom reaction emojis found on that message.")
            return

        # Send to user's DMs
        try:
            dm_channel = await ctx.author.create_dm()
        except discord.HTTPException:
            await ctx.send("❌ I couldn't open a DM with you. Please enable DMs from this server.")
            return

        await dm_channel.send(
            f"🕵️ **Stolen assets from this message** (requested by {ctx.author}):\n"
            f"{message.jump_url}\n\n"
            f"Found **{len(unique_assets)}** unique image asset(s):"
        )

        # Send in smaller batches with delays to avoid rate limits
        asset_list = list(unique_assets.items())
        BATCH_SIZE = 5  # Reduced from 10 for better reliability
        for i in range(0, len(asset_list), BATCH_SIZE):
            embeds: List[discord.Embed] = []
            for name, url in asset_list[i : i + BATCH_SIZE]:
                embed = discord.Embed(title=name, color=discord.Color.blurple())
                embed.set_image(url=url)
                embeds.append(embed)

            try:
                await dm_channel.send(embeds=embeds)
                await asyncio.sleep(1.2)  # Small delay to respect Discord DM rate limits
            except discord.HTTPException as e:
                # If a batch fails (rate limit or size), try sending one by one with longer delay
                await dm_channel.send("⚠️ Batch failed — sending assets one at a time...")
                for name, url in asset_list[i : i + BATCH_SIZE]:
                    try:
                        single_embed = discord.Embed(title=name, color=discord.Color.blurple())
                        single_embed.set_image(url=url)
                        await dm_channel.send(embed=single_embed)
                        await asyncio.sleep(2.0)
                    except discord.HTTPException:
                        await dm_channel.send(f"⚠️ Could not send: **{name}** (rate limit or Discord issue)")

        await ctx.tick()  # Green checkmark reaction to confirm success
