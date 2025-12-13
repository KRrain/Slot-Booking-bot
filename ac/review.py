import discord
from discord import app_commands
from datetime import datetime

def setup_review_command(bot, is_staff_member):
    # ---------- /review ----------
    @bot.tree.command(name="review", description="Staff only: Review an invitation.")
    @app_commands.describe(
        vtc_name="VTC Name",
        user="User to mention"
    )
    async def review(
        interaction: discord.Interaction,
        vtc_name: str,
        user: discord.Member
    ):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ You are not staff.", ephemeral=True)

        embed = discord.Embed(
            title="🟠 Reviewing Your Invitation 👁️",
            description=(
                f"Dear **{vtc_name}**, {user.mention}. 🙏\n\n"
                f"Thank you for your invitation to NepPath. "
                f"We are currently reviewing the details and will get back to you shortly.\n\n"
                f"**``We appreciate the opportunity and look forward to connecting soon!``**\n\n"
                f"Best regards,\nNepPath"
            ),
            color=discord.Color.from_rgb(255, 90, 32),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="NepPath")

        await interaction.channel.send(embed=embed)
        await interaction.response.send_message("✅ Review embed sent.", ephemeral=True)
