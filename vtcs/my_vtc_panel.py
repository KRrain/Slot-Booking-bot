import discord
from discord.ext import commands
import aiohttp
import os
from datetime import datetime

VTC_ID = int(os.getenv("MY_VTC_ID", "81586"))  # Set your VTC ID in .env
NEPPATH_VTC_ID = int(os.getenv("NEPPATH_VTC_ID", "81586"))  # Optional if different

def setup_my_vtc(bot: commands.Bot):

    class MyVTCView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)

        @discord.ui.button(label="Members", style=discord.ButtonStyle.green)
        async def members_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://api.truckersmp.com/v2/vtc/{VTC_ID}/members") as resp:
                    if resp.status != 200:
                        return await interaction.response.send_message(f"❌ Failed to fetch members. HTTP {resp.status}", ephemeral=True)
                    data = await resp.json()
                    members = data.get("response", [])

            total_members = len(members)
            banned_members = sum(1 for m in members if isinstance(m, dict) and m.get("banned", False))

            embed = discord.Embed(
                title="My VTC Members",
                description=f"**Total Members:** {total_members}\n**Banned Members:** {banned_members}",
                color=discord.Color.from_rgb(255, 90, 32),
                timestamp=datetime.utcnow()
            )
            embed.set_footer(text="NepPath | Timestamp")
            await interaction.response.send_message(embed=embed, ephemeral=True)

        @discord.ui.button(label="NepPath Events", style=discord.ButtonStyle.blurple)
        async def neppath_events_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://api.truckersmp.com/v2/vtc/{NEPPATH_VTC_ID}/events/attending") as resp:
                    if resp.status != 200:
                        return await interaction.response.send_message(f"❌ Failed to fetch events. HTTP {resp.status}", ephemeral=True)
                    data = await resp.json()
                    events = data.get("response", [])

            if not events:
                await interaction.response.send_message("No upcoming NepPath events.", ephemeral=True)
                return

            first_event = events[0]
            description = (
                f"**Date:** {first_event.get('date')}\n"
                f"**Game:** {first_event.get('game')}\n"
                f"**Type:** {first_event.get('eventType')}\n"
                f"**Server:** {first_event.get('server')}\n"
                f"**Attending:** {first_event.get('attending')}\n"
                f"**Unsure:** {first_event.get('unsure')}\n"
                f"**VTCs Attending:** {first_event.get('vtcsAttending')}\n"
            )

            embed = discord.Embed(
                title="NepPath Upcoming Event",
                description=description + f"\n**Total Events:** {len(events)}",
                color=discord.Color.from_rgb(255, 90, 32),
                timestamp=datetime.utcnow()
            )
            embed.set_footer(text="NepPath | Timestamp")
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="my_vtc", description="Show My VTC Info with buttons")
    async def my_vtc_command(interaction: discord.Interaction):
        async with aiohttp.ClientSession() as session:
            # Fetch VTC info
            async with session.get(f"https://api.truckersmp.com/v2/vtc/{VTC_ID}") as resp:
                if resp.status != 200:
                    return await interaction.response.send_message(f"❌ Failed to fetch VTC info. HTTP {resp.status}", ephemeral=True)
                vtc_data = await resp.json()
                vtc_info = vtc_data.get("response", {})

        embed = discord.Embed(
            title=f"My VTC Info",
            description=(
                f"**Name:** {vtc_info.get('name')}\n"
                f"**Tag:** {vtc_info.get('tag')}\n"
                f"**Created:** {vtc_info.get('createDate')}\n"
                f"**Recruitment:** {vtc_info.get('recruitmentState')}"
            ),
            color=discord.Color.from_rgb(255, 90, 32),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="NepPath | Timestamp")

        view = MyVTCView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
