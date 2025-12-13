import discord
from discord import app_commands
from datetime import datetime

def setup_decline_command(bot, is_staff_member):
    # ---------- /decline ----------
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
            return await interaction.response.send_message("❌ You are not staff.", ephemeral=True)

        embed = discord.Embed(
            title="🔴 Invitation Declined",
            description=(
                f"<:truck:1397230402527297577> Dear **{vtc_name}**, {user.mention} 🙏\n\n"
                f"**🔴 Apologies for Declining the Invitation**\n\n"
                f"Thank you for your kind invitation to your event. "
                f"We truly appreciate the opportunity to connect. "
                f"Unfortunately, we already have a VTC event scheduled on the same day "
                f"and won't be able to attend.\n\n"
                f"**`We look forward to finding another opportunity to collaborate in the future. "
                f"♥️ Thank you for your understanding, and we wish you a highly successful event!`**\n\n"
                f"Warm regards,\nNepPath"
            ),
            color=discord.Color.from_rgb(255, 90, 32),  # #FF5A20
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="**NepPath**")

        await interaction.channel.send(embed=embed)
        await interaction.response.send_message("✅ Decline embed sent.", ephemeral=True)

    # ---------- /decline_time ----------
    @bot.tree.command(name="decline_time", description="Staff only: Decline due to convoy time.")
    @app_commands.describe(
        vtc_name="VTC Name",
        user="User to mention"
    )
    async def decline_time(
        interaction: discord.Interaction,
        vtc_name: str,
        user: discord.Member
    ):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ You are not staff.", ephemeral=True)

        embed = discord.Embed(
            title="🔴 The invitation has been declined",
            description=(
                f"Dear **{vtc_name}**, {user.mention}. 🙏\n\n"
                f"Thank you so much **`{vtc_name}`**, for inviting us. "
                f"Unfortunately, we apologize for not being able to accept your invitation "
                f"due to your convoy timing. We cannot accept convoys `departure` scheduled above 17:15 UTC.\n\n"
                f"> Thank you for your understanding, and I hope we can connect at another time.\n"
                f"> I wish you all the best with your upcoming event and hope it is a great success.\n\n"
                f"Kind regards,\nNepPath"
            ),
            color=discord.Color.from_rgb(255, 90, 32),  # #FF5A20
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="**NepPath**")

        await interaction.channel.send(embed=embed)
        await interaction.response.send_message("✅ Decline due to timing embed sent.", ephemeral=True)
