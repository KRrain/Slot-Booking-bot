import os
import discord
from discord.ext import commands
import aiohttp
from datetime import datetime

VTC_ID = os.getenv("VTC_ID")


class MyVTCView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🚚 My VTC", style=discord.ButtonStyle.primary)
    async def myvtc(self, interaction: discord.Interaction, button: discord.ui.Button):
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
    async def members(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.truckersmp.com/v2/vtc/{VTC_ID}/members") as r:
                data = await r.json()
                members = data["response"]

        total = len(members)
        banned = sum(1 for m in members if m["banned"])

        embed = discord.Embed(
            title="👥 Members",
            description=f"**Total:** {total}\n**Banned:** {banned}",
            color=discord.Color.from_rgb(255, 90, 32),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="NepPath")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="📅 Events", style=discord.ButtonStyle.success)
    async def events(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.truckersmp.com/v2/vtc/{VTC_ID}/events/attending") as r:
                data = await r.json()
                events = data["response"]

        if not events:
            return await interaction.response.send_message("❌ No upcoming events.", ephemeral=True)

        first = events[0]["event"]

        embed = discord.Embed(
            title="📅 Upcoming Events",
            description=(
                f"**{first['name']}**\n"
                f"Date: {first['start_at']}\n"
                f"Server: {first['server']['name']}\n"
                f"Game: {first['game']}\n\n"
                f"Total Events: {len(events)}"
            ),
            color=discord.Color.from_rgb(255, 90, 32),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="NepPath")

        await interaction.response.send_message(embed=embed, ephemeral=True)


def setup_vtc_commands(bot):

    @bot.tree.command(name="myvtc", description="My VTC control panel")
    async def myvtc(interaction: discord.Interaction):
        embed = discord.Embed(
            title="🚚 My VTC Panel",
            description="Click a button below to view information.",
            color=discord.Color.from_rgb(255, 90, 32)
        )
        embed.set_footer(text="NepPath")

        await interaction.response.send_message(embed=embed, view=MyVTCView())
