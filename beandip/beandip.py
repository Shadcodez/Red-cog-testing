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
                "**♂️ Male mode activated!**\n"
                "Penis size detected with **maximum accuracy** (original CogsByAdrian framework style).\n\n"
                f"{art}\n\n"
                "*Beandip cog — 2026 update*"
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
                "**♀️ Female mode activated!**\n"
                "Kawaii beandip reactions loaded (15 ASCII options from psd-dude kaomojis).\n\n"
                f"{art}\n\n"
                "*Beandip cog — 2026 update*"
            ),
            view=None,
        )


class Beandip(commands.Cog):
    """Beandip — gender-choice ASCII generator (2026 update of CogsByAdrian penis framework)."""

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
            title="🫘 Beandip Detector 3000",
            description=(
                "**Choose your mode!**\n\n"
                "♂️ **Male** → Classic penis ASCII output (identical logic to original CogsByAdrian penis cog)\n"
                "♀️ **Female** → Kawaii ASCII reaction table (15 options, same random selection method)\n\n"
                "Maximum accuracy guaranteed. 100% scientifically accurate. 😂"
            ),
            color=discord.Color.purple(),
        )
        embed.set_footer(text="Click a button below • Only the command author can choose")

        await ctx.send(embed=embed, view=view)


# This file contains only the cog and view. Setup is in __init__.py (Red V3/V4 standard).
