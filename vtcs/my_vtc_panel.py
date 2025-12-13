# vtcs/my_vtc_panel.py
import discord
from discord.ui import View, Button
from discord import app_commands
from datetime import datetime
import aiohttp
import os

NEPPATH_VTC_ID = int(os.getenv("NEPPATH_VTC_ID", 81586))  # Set your VTC ID in .env

# ---------- Button Callback ----------
async def neppath_event_callback(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    # Fetch upcoming events
    api_url = f"https://api.truckersmp.com/v2/vtc/{NEPPATH_VTC_ID}/events/attending"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as resp:
                if resp.status != 200:
                    return await interaction.followup.send(f"❌ Failed to fetch events. HTTP {resp.status}", ephemeral=True)
                data = await resp.json()
    except Exception as e:
        return await interaction.followup.send(f"❌ Error fetching events: {e}", ephemeral=True)

    events = data.get("response", [])
    if not events:
        return await interaction.followup.send("ℹ️ No upcoming NepPath events found.", ephemeral=True)

    # Show first event
    event = events[0]
    embed = discord.Embed(
        title=f"NepPath Upcoming Event",
        description=f"**Date:** {event.get('date')}\n"
                    f"**Game:** {event.get('game')}\n"
                    f"**Event Type:** {event.get('eventType')}\n"
                    f"**Server:** {event.get('server')}\n"
                    f"**Attending:** {event.get('attending')}\n"
                    f"**Unsure:** {event.get('unsure')}\n"
                    f"**VTCs Attending:** {event.get('vtcsAttending')}",
        color=discord.Color.from_rgb(255, 90, 32),  # #FF5A20
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text=f"Total Upcoming Events: {len(events)} | NepPath")

    await interaction.followup.send(embed=embed, ephemeral=True)


# ---------- Button View ----------
class MyVTCView(View):
    def __init__(self):
        super().__init__(timeout=None)
        button = Button(label="NepPath Upcoming Event", style=discord.ButtonStyle.orange, custom_id="neppath_event")
        button.callback = neppath_event_callback
        self.add_item(button)


# ---------- Setup Function ----------
def setup_my_vtc(bot):
    view = MyVTCView()
    bot.add_view(view)
