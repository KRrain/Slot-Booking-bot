# bot.py - NEPPATH VTC BOT - FINAL DEC 2025 VERSION
# → Auto + Manual arrival/departure city (so Newcastle upon Tyne (Port) will ALWAYS show)

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
import re
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ==================== CONFIG ====================
STAFF_ROLE_IDS = [1395579577555878012, 1395579347804487769, 1395580379565527110, 1395699038715642031, 1395578532406624266]
ANNOUNCEMENT_CHANNEL_ID = 1446383730242355200

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

booking_messages = {}
user_requests = {}

# ==================== HELPERS ====================
def is_staff(member: discord.Member):
    return any(role.id in STAFF_ROLE_IDS for role in member.roles)

def format_time(iso: str):
    if not iso: return "Unknown"
    iso = iso.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso)
        return f"{dt.strftime('%H:%M')} UTC | {(dt + timedelta(hours=5, minutes=45)).strftime('%H:%M')} NPT"
    except:
        return "Unknown"

def format_date(iso: str):
    if not iso: return "Unknown"
    iso = iso.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%A, %d %B %Y")
    except:
        return "Unknown"

async def is_image(url: str) -> bool:
    if not url or not url.startswith("http"): return False
    try:
        async with aiohttp.ClientSession() as s:
            async with s.head(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                return "image"image"" in r.headers.get("content-type", "").lower()
    except:
        return False

# ==================== ANNOUNCEMENT MODAL (NOW WITH MANUAL FIELDS) ====================
class AnnouncementModal(discord.ui.Modal, title="Create Convoy Announcement"):
    event_link = discord.ui.TextInput(label="TruckersMP Event Link", placeholder="https://truckersmp.com/events/29157")
    distance   = discord.ui.TextInput(label="Distance", placeholder="911 km")
    vtc_slot   = discord.ui.TextInput(label="Our VTC Slot", placeholder="7")
    departure_city = discord.ui.TextInput(label="Departure City (Manual Override)", placeholder="Cardiff (Slots)", required=False)
    arrival_city   = discord.ui.TextInput(label="Arrival City (Manual Override)", placeholder="Newcastle upon Tyne (Port)", required=False)
    route_img  = discord.ui.TextInput(label="Route Image URL", placeholder="https://i.imgur.com/...")
    slot_img   = discord.ui.TextInput(label="Slot Image URL (Optional)", required=False)

    async def on_submit(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)

        match = re.search(r"/events/(\d+)", self.event_link.value.strip())
        if not match:
            return await i.followup.send("Invalid event link!", ephemeral=True)

        event_id = match.group(1)
        event_url = self.event_link.value.strip()

        # Default values
        event = {
            "name": "Unknown Convoy",
            "game": "ETS2",
            "server": "Event Server",
            "start_at": None,
            "meetup_at": None,
            "departure_city": "Unknown",
            "arrival_city": "Unknown",
            "dlcs": "None",
            "banner": None
        }

        # Try to auto-fetch from API
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://api.truckersmp.com/v2/events/{event_id}") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        d = data.get("response", {})

                        dep = d.get("departure", {}) or {}
                        arr = d.get("arrive", {}) or d.get("arrival", {}) or {}

                        event.update({
                            "name": d.get("name") or "Unknown Convoy",
                            "game": "ETS2" if d.get("game", "").lower() == "ets2" else "ATS",
                            "server": d.get("server", {}).get("name", "Event Server"),
                            "start_at": d.get("start_at"),
                            "meetup_at": d.get("meetup_at") or d.get("start_at"),
                            "departure_city": dep.get("city") or dep.get("location") or "Unknown",
                            "arrival_city": arr.get("city") or arr.get("location") or "Unknown",
                            "dlcs": ", ".join(d.get("dlc", [])) or "None",
                            "banner": d.get("banner")
                        })
        except Exception as e:
            print(f"API fetch failed: {e}")

        # MANUAL OVERRIDE WINS — so Newcastle upon Tyne (Port) will always show!
        if self.departure_city.value.strip():
            event["departure_city"] = self.departure_city.value.strip()
        if self.arrival_city.value.strip():
            event["arrival_city"] = self.arrival_city.value.strip()

        # Image validation
        route_ok = await is_image(self.route_img.value)
        slot_ok = await is_image(self.slot_img.value) if self.slot_img.value else True
        banner_ok = await is_image(event["banner"]) if event["banner"] else False

        # Build embed
        embed = discord.Embed(title=event["name"], url=event_url, color=0x00FFFF, timestamp=discord.utils.utcnow())
        embed.add_field(name="Game", value=event["game"], inline=True)
        embed.add_field(name="Date", value=format_date(event["start_at"]), inline=True)
        embed.add_field(name="Server", value=event["server"], inline=True)

        embed.add_field(name="Meetup", value=format_time(event["meetup_at"]), inline=True)
        embed.add_field(name="Departure", value=format_time(event["start_at"]), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False)

        embed.add_field(name="Distance", value=self.distance.value, inline=True)
        embed.add_field(name="Our Slot", value=f"**{self.vtc_slot.value}**", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False)

        embed.add_field(name="Start", value=event["departure_city"], inline=True)
        embed.add_field(name="Finish", value=event["arrival_city"], inline=True)  # ← ALWAYS SHOWS NOW
        embed.add_field(name="Required DLCs", value=event["dlcs"], inline=False)

        if route_ok: embed.set_image(url=self.route_img.value)
        if slot_ok and self.slot_img.value: embed.set_thumbnail(url=self.slot_img.value)
        if banner_ok and event["banner"]: embed.set_footer(text="Official Event", icon_url=event["banner"])

        embed.set_author(name=f"Announced by {i.user.display_name}", icon_url=i.user.display_avatar.url)

        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label="View Event", style=discord.ButtonStyle.link, url=event_url, emoji="Link"))

        await i.followup.send("Preview – Click Send when ready", embed=embed, view=ConfirmView(embed, view), ephemeral=True)


class ConfirmView(discord.ui.View):
    def __init__(self, embed, final_view):
        super().__init__(timeout=300)
        self.embed = embed
        self.final_view = final_view

    @discord.ui.button(label="Send Announcement", style=discord.ButtonStyle.green)
    async def send(self, i: discord.Interaction, b):
        ch = i.guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
        if not ch: return await i.response.edit_message(content="Channel not found!", view=None)
        await ch.send(embed=self.embed, view=self.final_view)
        await i.response.edit_message(content="Announcement sent!", view=None, embed=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, i: discord.Interaction, b):
        await i.response.edit_message(content="Cancelled", view=None, embed=None)


# ==================== (Slot booking system unchanged — already perfect) ====================
# ... (same PersistentBookView, BookModal, /create command as in previous version)

@bot.tree.command(name="announcement")
async def announcement_cmd(i: discord.Interaction):
    if not is_staff(i.user):
        return await i.response.send_message("Staff only!", ephemeral=True)
    await i.response.send_modal(AnnouncementModal())

# (keep your /create command and on_ready from previous working version)

@bot.event
async def on_ready():
    print(f"{bot.user} is ready!")
    bot.tree.add_command(announcement_cmd)
    bot.add_view(PersistentBookView())
    await bot.tree.sync()
    print("Bot synced & online")

bot.run(BOT_TOKEN)
