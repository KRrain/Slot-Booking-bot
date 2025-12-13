import discord
from discord import app_commands
from datetime import datetime

# This function will be called from bot.py
def setup_decline_command(bot, is_staff_member):

    @bot.tree.command(name="decline", description="Staff only: Send invitation declined message.")
    @app_commands.describe(
        vtc_name="VTC Name",
        user="User to mention"
    )
    async def decline(
        interaction: discord.Interaction,
        vtc_name: str,
        user: discord.Member
    ):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message(
                "❌ You are not staff.", ephemeral=True
            )

        embed = discord.Embed(
            title="🔴 Invitation Declined",
            description=(
                f"<:truck:1397230402527297577> "
                f"Dear **{vtc_name}**, {user.mention} 🙏\n\n"
                f"**🔴 Apologies for Declining the Invitation**\n\n"
                f"Thank you for your kind invitation to your event. "
                f"We truly appreciate the opportunity to connect. "
                f"Unfortunately, we already have a VTC event scheduled on the same day "
                f"and won't be able to attend.\n\n"
                f"**`We look forward to finding another opportunity to collaborate in the future. "
                f"♥️ Thank you for your understanding, and we wish you a highly successful event!`**\n\n"
                f"Warm regards,\n"
                f"**NepPath**"
            ),
            color=discord.Color.from_rgb(255, 90, 32),  # #FF5A20
            timestamp=datetime.utcnow()
        )

        embed.set_footer(text="NepPath")

        await interaction.channel.send(embed=embed)
        await interaction.response.send_message(
            "✅ Decline embed sent.", ephemeral=True
      )

