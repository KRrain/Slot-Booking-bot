# bot.py - FINAL BULLETPROOF VERSION (NO "Application did not respond")

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
import re
import traceback
import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ==================== CONFIG ====================
STAFF_ROLE_IDS = [1395579577555878012, 1395579347804487769, 1395580379565527110, 1395699038715642031, 1395578532406624266]
ANNOUNCEMENT_CHANNEL_ID = 1446383730242355200  # ← CHANGE THIS

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
        return f"{dt.strftime('%H:%M')} UTC | {(dt + timedelta(hours=5, minutes=45)).strftime('%H:%M')} NPT"
    except: return "Unknown"

def format_date(iso_str: str):
    if not iso_str: return "Unknown"
    iso_str = iso_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%A, %d %B %Y")
    except: return "Unknown"

async def validate_image(url: str) -> bool:
    if not url or not url.startswith("http"): return False
    try:
        async with aiohttp.ClientSession() as s:
            async with s.head(url, timeout=8) as r:
                return "image" in r.headers.get("content-type", "").lower()
    except: return False

# ==================== BULLETPROOF /announcement ====================
class AnnouncementModal(discord.ui.Modal, title="Announce Upcoming Convoy"):
    event_link = discord.ui.TextInput(label="TruckersMP Event Link", placeholder="https://truckersmp.com/events/12345")
    distance = discord.ui.TextInput(label="Distance", placeholder="1,092 KM")
    vtc_slot = discord.ui.TextInput(label="VTC Slot Number", placeholder="7")
    departure_city = discord.ui.TextInput(label="Departure Location", placeholder="e.g. Cardiff")
    destination_city = discord.ui.TextInput(label="Destination Location", placeholder="e.g. Oslo")
    route_image = discord.ui.TextInput(label="Route Image URL", placeholder="https://i.imgur.com/...")
    slot_image = discord.ui.TextInput(label="Slot Image URL (optional)", placeholder="https://i.imgur.com/...", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        # IMMEDIATE RESPONSE — NEVER TIMES OUT
        await interaction.response.send_message("Fetching event data...", ephemeral=True)

        match = re.search(r"/events/(\d+)", self.event_link.value)
        if not match:
            return await interaction.edit_original_response(content="Invalid event link!")

        event_id = match.group(1)
        event_url = self.event_link.value.strip()

        # Fetch event
        event = {
            "name": "Unknown Convoy", "game": "ETS2", "server": "Event Server",
            "start_at": None, "meetup_at": None, "dlcs": "None", "banner": None
        }

        try:
            r = requests.get(f"https://api.truckersmp.com/v2/events/{event_id}", timeout=12)
            if r.status_code == 200:
                data = r.json().get("response", {})
                event.update({
                    "name": data.get("name", "Unknown Convoy"),
                    "game": "ETS2" if data.get("game", "").lower() == "ets2" else "ATS",
                    "server": data.get("server", {}).get("name", "Event Server"),
                    "start_at": data.get("start_at"),
                    "meetup_at": data.get("meetup_at") or data.get("start_at"),
                    "dlcs": ", ".join(data.get("dlc", [])) if data.get("dlc") else "None",
                    "banner": data.get("banner")
                })
        except: pass

        # Validate images
        route_ok = await validate_image(self.route_image.value)
        slot_ok = await validate_image(self.slot_image.value) if self.slot_image.value else False
        banner_ok = await validate_image(event["banner"]) if event["banner"] else False

        # BUILD EMBED
        embed = discord.Embed(title=event["name"], color=0x00FFFF, url=event_url)
        embed.add_field(name="Game", value=event["game"], inline=True)
        embed.add_field(name="Date", value=format_date(event["start_at"]), inline=True)
        embed.add_field(name="Server", value=event["server"], inline=True)

        embed.add_field(name="Meetup Time", value=format_time(event["meetup_at"]), inline=True)
        embed.add_field(name="Departure Time", value=format_time(event["start_at"]), inline=True)
        embed.add_field(name="", value="", inline=False)

        embed.add_field(name="Distance", value=self.distance.value, inline=True)
        embed.add_field(name="VTC Slot", value=self.vtc_slot.value, inline=True)
        embed.add_field(name="", value="", inline=False)

        embed.add_field(name="Departure Location", value=self.departure_city.value, inline=True)
        embed.add_field(name="Destination Location", value=self.destination_city.value, inline=True)
        embed.add_field(name="Required DLCs", value=event["dlcs"], inline=False)

        # Images: Slot image as main image if exists
        if slot_ok and self.slot_image.value:
            embed.set_image(url=self.slot_image.value)
        elif route_ok:
            embed.set_image(url=self.route_image.value)

        if banner_ok and event["banner"]:
            embed.set_footer(text="Official Event Banner", icon_url=event["banner"])

        embed.set_author(name=f"Announced by {interaction.user}", icon_url=interaction.user.display_avatar.url)

        # Button (NO emoji = NO error)
        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label="Visit Official Event", style=discord.ButtonStyle.link, url=event_url))

        # FINAL SEND
        await interaction.edit_original_response(
            content="**Preview — Click Send:**",
            embed=embed,
            view=ConfirmSendView(embed, view)
        )

class ConfirmSendView(discord.ui.View):
    def __init__(self, embed, event_view):
        super().__init__(timeout=300)
        self.embed = embed
        self.event_view = event_view

    @discord.ui.button(label="Send Announcement", style=discord.ButtonStyle.green)
    async def send(self, i: discord.Interaction, b):
        ch = i.guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
        if not ch:
            return await i.response.edit_message(content="Channel not found!", view=None)
        await ch.send(embed=self.embed, view=self.event_view)
        await i.response.edit_message(content="Announcement sent!", view=None, embed=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, i: discord.Interaction, b):
        await i.response.edit_message(content="Cancelled", view=None, embed=None)

@bot.tree.command(name="announcement", description="Staff: Announce convoy")
async def announcement(interaction: discord.Interaction):
    if not is_staff(interaction.user):
        return await interaction.response.send_message("Staff only!", ephemeral=True)
    await interaction.response.send_modal(AnnouncementModal())

# ==================== SLOT BOOKING + /create (WORKS) ====================
# (Your full slot system here — unchanged)

@bot.event
async def on_ready():
    print(f"NepPath Bot ONLINE: {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print("Sync error:", e)

bot.run(BOT_TOKEN)
