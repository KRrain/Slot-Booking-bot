import discord
from discord import app_commands
import aiohttp
import re

def setup_vtcinfo_command(bot, is_staff_member):
    @app_commands.command(name="vtcinfo", description="Fetch TruckersMP VTC info by link or ID")
    @app_commands.describe(link="VTC link or ID")
    async def vtcinfo(interaction: discord.Interaction, link: str):
        # Optional: only staff can use
        if not is_staff_member(interaction.user):
            await interaction.response.send_message("❌ You are not allowed to use this command.", ephemeral=True)
            return

        await interaction.response.defer()

        match = re.search(r"(\d+)", link)
        if not match:
            await interaction.followup.send("❌ Invalid VTC link or ID.", ephemeral=True)
            return
        vtc_id = match.group(1)

        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.truckersmp.com/v2/vtc/{vtc_id}") as resp:
                if resp.status != 200:
                    await interaction.followup.send("❌ VTC not found.", ephemeral=True)
                    return
                vtc_data = await resp.json()

        vtc = vtc_data.get("response", {})
        if not vtc:
            await interaction.followup.send("❌ VTC not found.", ephemeral=True)
            return

        member_count = vtc.get("members", 0)
        member_count_str = f"{member_count//1000}K members" if member_count >= 1000 else f"{member_count} members"
        recruitment = "Open" if vtc.get("recruitmentOpen") else "Closed"
        creation_date = vtc.get("creationDate", "Unknown")

        embed = discord.Embed(
            title=f"{vtc.get('name', 'Unknown')} [{vtc.get('tag', '')}]",
            url=f"https://truckersmp.com/vtc/{vtc_id}",
            color=0xFF5A20
        )
        embed.add_field(name="📌 VTC ID", value=vtc_id, inline=True)
        embed.add_field(name="📅 Created", value=creation_date, inline=True)
        embed.add_field(name="📈 Recruitment", value=recruitment, inline=True)
        embed.add_field(name="👥 Members", value=member_count_str, inline=True)
        embed.add_field(name="📜 Description / Rules", value=vtc.get("description", "No description provided"), inline=False)
        embed.set_footer(text="Powered by NepPath | TruckersMP API")

        await interaction.followup.send(embed=embed)

    # Add the command to the bot
    bot.tree.add_command(vtcinfo)
