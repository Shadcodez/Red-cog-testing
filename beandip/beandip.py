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
        """Male button → consistent measurement (seeded by user ID) + auto-delete embed."""
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "❌ This beandip session belongs to someone else!", ephemeral=True
            )
            return

        # Make measurement consistent across runs (exact same method as CogsByAdrian/penis.py)
        state = random.getstate()
        random.seed(str(interaction.user.id))
        art = random.choice(self.cog.male_arts)
        random.setstate(state)

        content = (
                "**♂️ Male measurement detected!**\n"
                f"{art}\n\n"
                "*Your peen's measurment is 100% accurate*"
        )

        # Send new result message + auto-delete the original embed
        await interaction.response.send_message(content=content)
        await interaction.message.delete()

    @discord.ui.button(label="Female", emoji="♀️", style=discord.ButtonStyle.primary, row=0)
    async def female_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Female button → consistent kawaii measurement (seeded by user ID) + auto-delete embed."""
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "❌ This beandip session belongs to someone else!", ephemeral=True
            )
            return

        # Make measurement consistent across runs (exact same method as CogsByAdrian/penis.py)
        state = random.getstate()
        random.seed(str(interaction.user.id))
        art = random.choice(self.cog.female_arts)
        random.setstate(state)

        content = (
                "**♀️ Female measurement detected!**\n"
                f"{art}\n\n"
                "*Your Bean's measurment is 100% accurate*"
        )

        # Send new result message + auto-delete the original embed
        await interaction.response.send_message(content=content)
        await interaction.message.delete()


class Beandip(commands.Cog):
    """Beandip — gender-choice ASCII (update of CogsByAdrian penis framework)."""

    def __init__(self, bot):
        self.bot = bot

        # Male arts — exact same style/method as the original penis cog
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

        # Female arts — 15 Kawaii ASCII kaomojis (pulled from https://www.psd-dude.com/kaomojis/)
        # Exactly the same count as male arts and fully consistent per user ID
        self.female_arts = [
            "(｡•ᴗ•｡)",
            "(´｡• ᵕ •｡`)",
            "(๑ > ᴗ < ๑)",
            "(´｡• ω •｡`)",
            "(´・ω・`)",
            "(´ ∀ ` *)",
            "(´• ω •`)",
            "(＾▽＾)",
            "(⌒ω⌒)",
            "(＠＾◡＾)",
            "(o´▽`o)",
            "(*´▽`*)",
            "(´ ꒳ ` )",
            "(≧◡≦)",
            "ヽ(>∀<☆)ノ",
        ]

    @commands.command(name="beandip")
    async def beandip_cmd(self, ctx: commands.Context):
        """Invoke the beandip command — shows Male/Female buttons as requested."""
        view = GenderSelection(self, ctx.author)

        embed = discord.Embed(
            title="🫘 Bean / Dip Detector 3001",
            description=(
                "**Before I measure, what are you?**\n\n"
                "♂️ **Male**\n"
                "♀️ **Female**\n"
                "Maximum accuracy guaranteed. 100% scientifically accurate."
            ),
            color=discord.Color.purple(),
        )
        embed.set_footer(text="Click a button below • Only the command author can choose")

        await ctx.send(embed=embed, view=view)
