import discord
from discord import app_commands
from datetime import datetime

def setup_decline_time_command(bot, is_staff_member):

    @bot.tree.command(
        name="decline_time",
        description="Staff only: Decline invitation due to convoy timing."
    )
    @app_commands.describe(
        vtc_name="VTC Name",
        role="Role to mention"
    )
    async def decline_time(
        interaction: discord.Interaction,
        vtc_name: str,
        role: discord.Role
    ):
        # Staff-only check
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message(
                "❌ You are not staff.", ephemeral=True
            )

        # Create embed
        embed = discord.Embed(
            title="🔴 The invitation has been declined",
            description=(
                f"Dear **{vtc_name}**, {role.mention}. 🙏\n\n"
                f"---\n\n"
                f"Thank you so much **{vtc_name}**, for inviting us. "
                f"Unfortunately, we apologize for not being able to accept your invitation, "
                f"due to your convoy timing. Because we cannot accept convoys departure scheduled above 17:15 UTC.\n\n"
                f"> Thank you for your understanding, and I hope we can connect at another time.\n"
                f"I wish you all the best with your upcoming event and hope it is a great success.\n\n"
                f"Kind regards,\nNepPath"
            ),
            color=discord.Color.from_rgb(255, 90, 32),  # #FF5A20
            timestamp=datetime.utcnow()
        )

        # Footer
        embed.set_footer(text="<:NepPath:1395694322061410334> NepPath | Timestamp")

        # Send in the same channel
        await interaction.channel.send(embed=embed)
        await interaction.response.send_message(
            "✅ Decline due to timing embed sent.", ephemeral=True
      )
      
