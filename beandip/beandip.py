# beandip/beandip.py
import discord
import random
from redbot.core import commands


class GenderSelection(discord.ui.View):
    """Interactive view with Male/Female buttons for the beandip cog."""

    def __init__(self, cog: "Beandip", author: discord.Member):
        super().__init__(timeout=180.0)  # 3 minute timeout
        self.cog = cog
        self.author = author

    @discord.ui.button(label="Male", emoji="♂️", style=discord.ButtonStyle.primary, row=0)
    async def male_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Male button → runs the original penis cog style output."""
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "❌ This beandip session belongs to someone else!", ephemeral=True
            )
            return

        art = random.choice(self.cog.male_arts)
        await interaction.response.edit_message(
            content=(
                "**♂️ Male measurement detected!**\n"
                f"{art}\n\n"
                "*Your peen's measurment is 100% accurate*"
            ),
            view=None,  # disable buttons after selection
        )

    @discord.ui.button(label="Female", emoji="♀️", style=discord.ButtonStyle.primary, row=0)
    async def female_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Female button → runs kawaii ASCII table (15 responses)."""
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "❌ This beandip session belongs to someone else!", ephemeral=True
            )
            return

        art = random.choice(self.cog.female_arts)
        await interaction.response.edit_message(
            content=(
                "**♀️ Female measurement detected!**\n"
                f"{art}\n\n"
                "*Your Bean's measurment is 100% accurate*"
            ),
            view=None,
        )


class Beandip(commands.Cog):
    """Beandip — gender-choice ASCII (update of CogsByAdrian penis framework)."""

    def __init__(self, bot):
        self.bot = bot

        # Male arts — exact same style/method as the original penis cog (random ASCII penis output)
        self.male_arts = [
            "8D",
            "8=D",
            "8==D",
            "8===D",
            "8====D",
            "8=====D",
            "8======D",
            "8=======D",
            "8========D",
            "8=========D",
            "8==========D",
            "8D~",
            "8==D~~",
            "8===D~~~",
            "8====D~~~~",
        ]

        # Female arts — 15 Kawaii ASCII reactions (pulled from https://www.psd-dude.com/kaomojis/)
        self.female_arts = [
            "(｡•ᴗ•｡)",
            "(´｡• ᵕ •｡`)",
            "(´｡• ω •｡`)",
            "(￣▽￣)",
            "(o^▽^o)",
            "ヽ(・∀・)ﾉ",
            "(⌒▽⌒)☆",
            "(≧◡≦)",
            "(๑ > ᴗ < ๑)",
            "(* ^ ω ^)",
            "٩(◕‿◕｡)۶",
            "(☆▽☆)",
            "(⌒‿⌒)",
            "╰(*´︶`*)╯",
            "ヽ(>∀<☆)ノ",
        ]

    @commands.command(name="beandip")
    async def beandip_cmd(self, ctx: commands.Context):
        """Invoke the beandip command — shows Male/Female buttons as requested."""
        view = GenderSelection(self, ctx.author)

        embed = discord.Embed(
            title="🫘 Bean / dip Detector 3000",
            description=(
                "**Choose your mode!**\n\n"
                "♂️ **Male**\n"
                "♀️ **Female**\n\n"
                "Maximum accuracy guaranteed. 100% scientifically accurate. 😂"
            ),
            color=discord.Color.purple(),
        )
        embed.set_footer(text="Click a button below • Only the command author can choose")

        await ctx.send(embed=embed, view=view)


# This file contains only the cog and view. Setup is in __init__.py (Red V3/V4 standard).
