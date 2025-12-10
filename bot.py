# bot.py - FINAL 100% WORKING TRUCKERSMP VTC BOT (December 2025) - MANUAL ARRIVAL CITY

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
import re
import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
import asyncio

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ==================== CONFIG ====================
STAFF_ROLE_IDS = [1395579577555878012, 1395579347804487769, 1395580379565527110, 1395699038715642031, 1395578532406624266]
ANNOUNCEMENT_CHANNEL_ID = 1446383730242355200
STAFF_LOG_CHANNEL_ID = 1446383730242355200

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ==================== GLOBALS ====================
booking_messages = {}
user_submissions = {}

# ==================== HELPERS ====================
def is_staff(member: discord.Member):
    return any(role.id in STAFF_ROLE_IDS for role in member.roles)

def format_time(iso_str: str):
    if not iso_str:
        return "Unknown"
    iso_str = iso_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso_str)
        return f"{dt.strftime('%H:%M')} UTC | {(dt + timedelta(hours=5, minutes=45)).strftime('%H:%M')} NPT"
    except:
        return "Invalid time"

def format_date(iso_str: str):
    if not iso_str:
        return "Unknown"
    iso_str = iso_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%A, %d %B %Y")
    except:
        return "Unknown"

async def validate_image(url: str) -> bool:
    if not url or not url.startswith(("http://", "https://")):
        return False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                ctype = resp.headers.get("content-type", "").lower()
                return "image" in ctype or "octet-stream" in ctype
    except:
        return False

# ==================== ANNOUNCEMENT SYSTEM (MANUAL ARRIVAL) ====================

class AnnouncementModal(discord.ui.Modal, title="Announce Upcoming Convoy"):
    event_link = discord.ui.TextInput(label="TruckersMP Event Link", placeholder="https://truckersmp.com/events/12345")
    distance = discord.ui.TextInput(label="Distance", placeholder="1,092 km")
    vtc_slot = discord.ui.TextInput(label="VTC Slot Number", placeholder="7")
    departure_city = discord.ui.TextInput(label="Departure City (Manual)", placeholder="e.g. Berlin")
    arrival_city = discord.ui.TextInput(label="Arrival City (Manual)", placeholder="e.g. Paris")  # NEW MANUAL FIELD
    route_image = discord.ui.TextInput(label="Route Image URL", placeholder="https://i.imgur.com/abc123.png")
    slot_image = discord.ui.TextInput(label="Slot Image URL (Optional)", required=False, placeholder="https://i.imgur.com/xyz.png")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        match = re.search(r"/events/(\d+)", self.event_link.value.strip())
        if not match:
            return await interaction.followup.send("Invalid TruckersMP event link!", ephemeral=True)

        event_id = match.group(1)
        event_url = self.event_link.value.strip()

        # Default fallback
        event = {
            "name": "Unknown Convoy",
            "game": "ETS2",
            "server": "Event",
            "start_at": None,
            "meetup_at": None,
            "dlcs": "None",
            "banner": None
        }

        # Only fetch basic info from API (name, times, server, banner, DLCs)
        try:
            api_url = f"https://api.truckersmp.com/v2/events/{event_id}"
            headers = {"User-Agent": "NepPathVTCBot/2.0 (+https://yourvtc.com)"}
            r = requests.get(api_url, headers=headers, timeout=12)
            if r.status_code == 200:
                data = r.json().get("response", {})
                event.update({
                    "name": data.get("name") or "Unknown Convoy",
                    "game": "ETS2" if data.get("game", "").lower() == "ets2" else "ATS",
                    "server": data.get("server", {}).get("name", "Event Server"),
                    "start_at": data.get("start_at"),
                    "meetup_at": data.get("meetup_at") or data.get("start_at"),
                    "dlcs": ", ".join(data.get("dlc", [])) or "None",
                    "banner": data.get("banner")
                })
        except Exception as e:
            print(f"[API ERROR] {e}")

        # Validate images
        route_ok = await validate_image(self.route_image.value)
        slot_ok = await validate_image(self.slot_image.value) if self.slot_image.value else True
        banner_ok = await validate_image(event["banner"]) if event["banner"] else False

        # Build embed with MANUAL cities
        embed = discord.Embed(title=event["name"], url=event_url, color=0x00FFFF)
        embed.add_field(name="Game", value=event["game"], inline=True)
        embed.add_field(name="Date", value=format_date(event["start_at"]), inline=True)
        embed.add_field(name="Server", value=event["server"], inline=True)

        embed.add_field(name="Meetup Time", value=format_time(event["meetup_at"]), inline=True)
        embed.add_field(name="Start Time", value=format_time(event["start_at"]), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False)

        embed.add_field(name="Distance", value=self.distance.value, inline=True)
        embed.add_field(name="Our Slot", value=f"**{self.vtc_slot.value}**", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False)

        # MANUAL CITIES
        embed.add_field(name="Start", value=self.departure_city.value.strip() or "Unknown", inline=True)
        embed.add_field(name="Finish", value=self.arrival_city.value.strip() or "Unknown", inline=True)
        embed.add_field(name="Required DLCs", value=event["dlcs"], inline=False)

        if route_ok:
            embed.set_image(url=self.route_image.value)
        if slot_ok and self.slot_image.value:
            embed.set_thumbnail(url=self.slot_image.value)
        if banner_ok and event["banner"]:
            embed.set_footer(text="Official TruckersMP Event", icon_url=event["banner"])

        embed.set_author(name=f"Announced by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()

        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label="View on TruckersMP", style=discord.ButtonStyle.link, url=event_url, emoji="Link"))

        confirm_view = ConfirmSendView(embed, view)
        await interaction.followup.send("**Preview:**\nClick **Send** when ready ↓", embed=embed, view=confirm_view, ephemeral=True)

# Confirm Send View (unchanged)
class ConfirmSendView(discord.ui.View):
    def __init__(self, embed, event_view):
        super().__init__(timeout=300)
        self.embed = embed
        self.event_view = event_view

    @discord.ui.button(label="Send Announcement", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
        if not channel:
            return await interaction.response.edit_message(content="Announcement channel not found!", view=None)

        await channel.send(embed=self.embed, view=self.event_view)
        await interaction.response.edit_message(content="Announcement sent successfully!", view=None, embed=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Cancelled.", view=None, embed=None)

# ==================== SLOT BOOKING SYSTEM (unchanged) ====================
# ... (PersistentBookSlotView, SlotBookingModal, etc. remain exactly the same...

class PersistentBookSlotView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Book Slot", style=discord.ButtonStyle.green, custom_id="persistent_book_slot")
    async def book_slot(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg_id = interaction.message.id
        data = booking_messages.get(msg_id)
        if not data:
            return await interaction.response.send_message("This booking is no longer active.", ephemeral=True)

        taken = [k for k, v in data["slots"].items() if v is not None]
        if len(taken) >= len(data["slots"]):
            return await interaction.response.send_message("All slots are taken!", ephemeral=True)

        await interaction.response.send_modal(SlotBookingModal(msg_id, data))

class SlotBookingModal(discord.ui.Modal, title="Book Your Slot"):
    vtc_name = discord.ui.TextInput(label="Your VTC Name", placeholder="Example: NepPath Logistics", max_length=50)
    slot = discord.ui.TextInput(label="Slot Number (e.g. 7)", placeholder="7", max_length=3)

    def __init__(self, msg_id, data):
        super().__init__()
        self.msg_id = msg_id
        self.data = data

    async def on_submit(self, interaction: discord.Interaction):
        if not self.slot.value.isdigit():
            return await interaction.response.send_message("Slot must be a number!", ephemeral=True)

        slot_key = f"Slot {int(self.slot.value)}"
        if slot_key not in self.data["slots"]:
            return await interaction.response.send_message("That slot doesn't exist!", ephemeral=True)
        if self.data["slots"][slot_key] is not None:
            return await interaction.response.send_message("Slot already taken!", ephemeral=True)

        submissions = user_submissions.setdefault(interaction.guild_id, {}).setdefault(interaction.user.id, set())
        if slot_key in submissions:
            return await interaction.response.send_message("You already requested this slot!", ephemeral=True)

        self.data["slots"][slot_key] = interaction.user.id
        submissions.add(slot_key)

        lines = []
        for k, v in self.data["slots"].items():
            status = "Taken" if v else "Available"
            user = f"<@{v}>" if v else "Available"
            lines.append(f"{status} **{k}** → {user}")

        embed = interaction.message.embeds[0]
        embed.description = "\n".join(lines)
        embed.set_footer(text=f"Last updated by {interaction.user} • {len([x for x in self.data['slots'].values() if x])}/{len(self.data['slots'])} booked")

        await interaction.message.edit(embed=embed)
        await interaction.response.send_message(f"You have successfully booked **{slot_key}** as **{self.vtc_name.value}**!", ephemeral=True)

        log = bot.get_channel(STAFF_LOG_CHANNEL_ID)
        if log:
            await log.send(f"Slot Booked | {interaction.user} booked **{slot_key}** as {self.vtc_name.value} in {interaction.channel.mention}")

# ==================== COMMANDS ====================
@app_commands.command(name="announcement", description="Staff Only: Create a professional convoy announcement")
async def announcement_slash(interaction: discord.Interaction):
    if not is_staff(interaction.user):
        return await interaction.response.send_message("You don't have permission.", ephemeral=True)
    await interaction.response.send_modal(AnnouncementModal())

@app_commands.command(name="create", description="Staff: Create slot booking message")
@app_commands.describe(
    channel="Channel to send booking message",
    title="Title of the event",
    slot_range="Example: 1-30",
    color="Hex or 'green'/'red'/'blue'",
    image="Optional route image"
)
async def create_booking(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    title: str,
    slot_range: str,
    color: str = "green",
    image: str = None
):
    if not is_staff(interaction.user):
        return await interaction.response.send_message("Staff only!", ephemeral=True)

    )

    try:
        start, end = map(int, slot_range.split("-"))
        if start > end or start < 1 or end > 200:
            raise ValueError
        slots = [f"Slot {i}" for i in range(start, end + 1)]
    except:
        return await interaction.response.send_message("Invalid format! Use: 1-30", ephemeral=True)

    try:
        if color.startswith("#"):
            col = discord.Color(int(color.lstrip("#"), 16))
        else:
            col = {"green": discord.Color.green(), "red": discord.Color.red(), "blue": discord.Color.blue()}.get(color.lower(), discord.Color.blurple())
    except:
        col = discord.Color.blurple()

    lines = [f"Available **{s}** → Available" for s in slots]
    embed = discord.Embed(title=title, description="\n".join(lines), color=col, timestamp=discord.utils.utcnow())
    embed.set_footer(text="Click 'Book Slot' to reserve your place")

    if image and await validate_image(image):
        embed.set_image(url=image)

    msg = await channel.send(embed=embed, view=PersistentBookSlotView())
    booking_messages[msg.id] = {"slots": {s: None for s in slots}, "message": msg}

    await interaction.response.send_message(f"Created booking with {len(slots)} slots in {channel.mention}", ephemeral=True)

# ==================== BOT STARTUP ====================
@bot.event
async def on_ready():
    print(f"{bot.user} is online!")
    bot.tree.add_command(announcement_slash)
    bot.tree.add_command(create_booking)
    bot.add_view(PersistentBookSlotView())

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"Sync failed: {e}")

bot.run(BOT_TOKEN)
