import discord
from discord import app_commands
from discord.ui import View, Button
import aiohttp
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
NEPPATH_VTC_ID = int(os.getenv("NEPPATH_VTC_ID"))

def setup_my_vtc(bot):
    ..,

class MyVTCView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Button(label="NepPath Upcoming Event", style=discord.ButtonStyle.blurple, custom_id="neppath_event"))

async def fetch_neppath_events():
    async with aiohttp.ClientSession() as session:
        url = f"https://api.truckersmp.com/v2/vtc/{NEPPATH_VTC_ID}/events/attending"
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            return data.get("response", [])

async def neppath_event_callback(interaction: discord.Interaction):
    events = await fetch_neppath_events()
    if not events:
        return await interaction.response.send_message("❌ No upcoming NepPath events found.", ephemeral=True)
    
    first_event = events[0]
    total_events = len(events)
    
    # Format date nicely
    try:
        dt = datetime.fromisoformat(first_event["startDateTime"].rstrip("Z"))
        event_date = dt.strftime("%d %b %Y | %H:%M UTC")
    except Exception:
        event_date = "Unknown"

    embed = discord.Embed(
        title=f"🛠 NepPath Upcoming Event",
        description=(
            f"**Event Name:** {first_event.get('name','Unknown')}\n"
            f"**Date:** {event_date}\n"
            f"**Game:** {first_event.get('game','Unknown')}\n"
            f"**Event Type:** {first_event.get('eventType','Unknown')}\n"
            f"**Server:** {first_event.get('server','Unknown')}\n"
            f"**Attendees:** {first_event.get('attendees',0)}\n"
            f"**Unsure:** {first_event.get('unsure',0)}\n"
            f"**VTCs Attending:** {first_event.get('vtcs',0)}\n\n"
            f"**Total NepPath Events:** {total_events}"
        ),
        color=discord.Color.from_rgb(255, 90, 32)  # #FF5A20
    )
    embed.set_footer(text="NepPath | Upcoming Event")
    await interaction.response.send_message(embed=embed)

def setup_my_vtc(bot):
    view = MyVTCView()
    
    # Connect button callback
    bot.add_view(view)
    
    # Find the button and attach callback
    for item in view.children:
        if item.custom_id == "neppath_event":
            item.callback = neppath_event_callback
