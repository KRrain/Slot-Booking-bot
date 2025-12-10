# bot.py - ULTIMATE TRUCKERSMP VTC BOT (2025) - FULL EVENT FETCH + NEPAL TIME

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
import re
import traceback
import os
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ==================== CONFIG ====================
STAFF_ROLE_IDS = [1395579577555878012, 1395579347804487769, 1395580379565527110, 1395699038715642031, 1395578532406624266]
ANNOUNCEMENT_CHANNEL_ID = 1446383730242355200  # ← CHANGE TO YOUR ANNOUNCEMENT CHANNEL

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ==================== HELPERS ====================
def is_staff(member: discord.Member):
    return any(r.id in STAFF_ROLE_IDS for r in member.roles)

def format_time(iso_str: str):
    if not iso_str: return "Unknown"
    iso_str = iso_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso_str)
        utc = dt.strftime("%H:%M UTC")
        nepal = (dt + timedelta(hours=5, minutes=45)).strftime("%H:%M NPT")
        return f"{utc} | {nepal}"
    except:
        return "Unknown"

async def validate_image(url: str) -> bool:
    if not url or not url.startswith("http"): return False
    try:
        async with aiohttp.ClientSession() as s:
            async with s.head(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                return "image" in r.headers.get("content-type", "").lower()
    except:
        return False

# ==================== PERFECT /announcement ====================
class AnnouncementModal(discord.ui.Modal, title="Announce Upcoming Convoy"):
    event_link = discord.ui.TextInput(label="TruckersMP Event Link (Full URL)", placeholder="https://truckersmp.com/events/12345")
    distance = discord.ui.TextInput(label="Distance (e.g. 1,250 KM)", placeholder="1,250 KM")
    vtc_slot = discord.ui.TextInput(label="VTC Slot Number", placeholder="15")
    route_image = discord.ui.TextInput(label="Route Image URL", placeholder="https://i.imgur.com/abc123.jpg")
    slot_image = discord.ui.TextInput(label="Slot List Image URL (optional)", placeholder="https://i.imgur.com/slots.png", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Extract event ID
        match = re.search(r"/events/(\d+)", self.event_link.value)
        if not match:
            return await interaction.followup.send("Invalid event link!", ephemeral=True)
        event_id = match.group(1)

        # Fetch full event data
        event_data = {
            "name": "Unknown Convoy",
            "game": "ETS2",
            "server": "Simulation 1",
            "start_at": None,
            "meetup_at": None,
            "departure_city": "Unknown",
            "arrival_city": "Unknown",
            "dlc": "None",
            "banner": None
        }

        try:
            resp = requests.get(f"https://api.truckersmp.com/v2/events/{event_id}", timeout=10)
            if resp.status_code == 200:
                data = resp.json().get("response", {})
                event_data.update({
                    "name": data.get("name", "Unknown Convoy"),
                    "game": "ETS2" if "ets2" in data.get("game", "").lower() else "ATS",
                    "server": data.get("server", "Simulation 1"),
                    "start_at": data.get("start_at"),
                    "meetup_at": data.get("meetup_at") or data.get("start_at"),
                    "departure_city": data.get("departure", {}).get("city", "Unknown") if data.get("departure") else "Unknown",
                    "arrival_city": data.get("arrival", {}).get("city", "Unknown") if data.get("arrival") else "Unknown",
                    "dlc": ", ".join(data.get("dlc", [])) or "None",
                    "banner": data.get("banner")
                })
        except: pass

        # Validate images
        route_ok = await validate_image(self.route_image.value)
        slot_ok = await validate_image(self.slot_image.value) if self.slot_image.value else False
        banner_ok = await validate_image(event_data["banner"]) if event_data["banner"] else False

        # Build FINAL embed
        embed = discord.Embed(
            title=event_data["name"],
            color=0x00FFFF,
            url=self.event_link.value
        )
        embed.add_field(name="Game", value=event_data["game"], inline=True)
        embed.add_field(name="Date", value="See times below", inline=True)
        embed.add_field(name="Server", value=event_data["server"], inline=True)

        embed.add_field(name="Meetup Time", value=format_time(event_data["meetup_at"]), inline=True)
        embed.add_field(name="Departure Time", value=format_time(event_data["start_at"]), inline=True)
        embed.add_field(name="", value="", inline=False)  # spacer

        embed.add_field(name="Distance", value=self.distance.value, inline=True)
        embed.add_field(name="VTC Slot", value=self.vtc_slot.value, inline=True)
        embed.add_field(name="", value="", inline=False)

        embed.add_field(name="Departure Location", value=event_data["departure_city"], inline=True)
        embed.add_field(name="Destination Location", value=event_data["arrival_city"], inline=True)
        embed.add_field(name="Required DLCs", value=event_data["dlc"], inline=False)

        # Images
        if route_ok:
            embed.set_image(url=self.route_image.value)
        if slot_ok and self.slot_image.value:
            embed.set_thumbnail(url=self.slot_image.value)
        if banner_ok and event_data["banner"]:
            embed.set_footer(text="Official Event Banner", icon_url=event_data["banner"])
        embed.set_author(name=f"Announced by {interaction.user}", icon_url=interaction.user.display_avatar.url)

        await interaction.followup.send(
            "**Preview – Click Send when ready:**",
            embed=embed,
            view=ConfirmSendView(embed),
            ephemeral=True
        )

class ConfirmSendView(discord.ui.View):
    def __init__(self, embed):
        super().__init__(timeout=300)
        self.embed = embed

    @discord.ui.button(label="Send Announcement", style=discord.ButtonStyle.green)
    async def send(self, i: discord.Interaction, b):
        channel = i.guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
        if not channel:
            return await i.response.edit_message(content="Announcement channel not found!", view=None)
        await channel.send(embed=self.embed)
        await i.response.edit_message(content="Announcement sent successfully!", view=None, embed=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, i: discord.Interaction, b):
        await i.response.edit_message(content="Cancelled.", view=None, embed=None)

@bot.tree.command(name="announcement", description="Staff: Announce convoy with FULL details + Nepal time")
async def announcement(interaction: discord.Interaction):
    if not is_staff(interaction.user):
        return await interaction.response.send_message("Staff only!", ephemeral=True)
    await interaction.response.send_modal(AnnouncementModal())

# ==================== REST OF YOUR BOT (Slot booking, /create, /mark) ====================
# ← Paste your full working slot booking system + /create + /mark from previous version here
# (Everything else stays 100% the same)

@bot.event
async def on_ready():
    print(f"Bot online: {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(e)

bot.run(BOT_TOKEN)
