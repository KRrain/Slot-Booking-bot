# ac/vtc.py
import discord
from discord import app_commands
import aiohttp
from datetime import datetime
import re

def setup_vtc_command(bot):

    @bot.tree.command(name="vtc_info", description="Fetch TruckersMP VTC information")
    @app_commands.describe(
        vtc_link="TruckersMP VTC link or ID"
    )
    async def vtc_info(interaction: discord.Interaction, vtc_link: str):
        await interaction.response.defer(thinking=True, ephemeral=True)

        match = re.search(r"/vtc/(\d+)", vtc_link)
        if match:
            vtc_id = match.group(1)
        elif vtc_link.isdigit():
            vtc_id = vtc_link
        else:
            return await interaction.followup.send("❌ Invalid VTC link or ID.", ephemeral=True)

        api_url = f"https://api.truckersmp.com/v2/vtc/{vtc_id}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as resp:
                    if resp.status != 200:
                        return await interaction.followup.send(f"❌ API returned HTTP {resp.status}.", ephemeral=True)
                    data = await resp.json()
        except Exception as e:
            return await interaction.followup.send(f"❌ Failed to fetch data: {e}", ephemeral=True)

        vtc = data.get("response")
        if not vtc:
            return await interaction.followup.send("❌ VTC not found.", ephemeral=True)

        members_count = vtc.get("memberCount", 0)
        members_display = f"{members_count/1000:.1f}K" if members_count >= 1000 else str(members_count)

        embed = discord.Embed(
            title=f"{vtc.get('name')} (ID: {vtc_id})",
            description=vtc.get("description", "No description"),
            color=discord.Color.from_rgb(255, 90, 32),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Rules", value=vtc.get("rules", "No rules listed"), inline=False)
        embed.add_field(name="Recruitment State", value=vtc.get("recruitmentState", "Unknown"), inline=True)
        embed.add_field(name="Created On", value=vtc.get("foundingDate", "Unknown"), inline=True)
        embed.add_field(name="Members", value=members_display, inline=True)

        logo = vtc.get("logo")
        if logo:
            embed.set_thumbnail(url=logo)

        await interaction.followup.send(embed=embed)
