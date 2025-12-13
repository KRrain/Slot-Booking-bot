import os
import discord
import aiohttp
from datetime import datetime

VTC_ID = os.getenv("VTC_ID")  # Set your VTC ID in .env

def setup_my_vtc(bot):

class MyVTCView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🚚 Info", style=discord.ButtonStyle.primary)
    async def info_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.truckersmp.com/v2/vtc/{VTC_ID}") as r:
                data = await r.json()
                vtc = data["response"]

        embed = discord.Embed(
            title=f"🚚 {vtc['name']}",
            description=vtc["description"] or "No description",
            color=discord.Color.from_rgb(255, 90, 32),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Members", value=vtc["members_count"])
        embed.add_field(name="Recruitment", value="Open" if vtc["recruitment"] else "Closed")
        embed.set_thumbnail(url=vtc["logo"])
        embed.set_footer(text="NepPath")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="👥 Members", style=discord.ButtonStyle.secondary)
    async def members_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.truckersmp.com/v2/vtc/{VTC_ID}/members") as r:
                data = await r.json()
                members = data["response"]

        total = len(members)
        banned = sum(1 for m in members if m["banned"])

        embed = discord.Embed(
            title="👥 Members",
            description=f"**Total Members:** {total}\n**Banned:** {banned}",
            color=discord.Color.from_rgb(255, 90, 32),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="NepPath")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="📅 Events", style=discord.ButtonStyle.success)
    async def events_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.truckersmp.com/v2/vtc/{VTC_ID}/events/attending") as r:
                data = await r.json()
                events = data["response"]

        if not events:
            return await interaction.response.send_message("❌ No upcoming events.", ephemeral=True)

        first_event = events[0]["event"]
        embed = discord.Embed(
            title="📅 Upcoming Events",
            description=(
                f"**{first_event['name']}**\n"
                f"Date: {first_event['start_at']}\n"
                f"Game: {first_event['game']}\n"
                f"Server: {first_event['server']['name']}\n"
                f"Attendees: {first_event['attendees']}\n"
                f"Unsure: {first_event['unsure']}\n"
                f"VTCs attending: {len(first_event.get('vtcs_attending', []))}\n\n"
                f"Total Upcoming Events: {len(events)}"
            ),
            color=discord.Color.from_rgb(255, 90, 32),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="NepPath")

        await interaction.response.send_message(embed=embed, ephemeral=True)


def setup_my_vtc(bot):
    @bot.tree.command(name="my_vtc", description="View My VTC Info, Members, and Events")
    async def my_vtc_command(interaction: discord.Interaction):
        embed = discord.Embed(
            title="🚚 My VTC Panel",
            description="Click a button below to view info, members, or events.",
            color=discord.Color.from_rgb(255, 90, 32)
        )
        embed.set_footer(text="NepPath")
        await interaction.response.send_message(embed=embed, view=MyVTCView())
