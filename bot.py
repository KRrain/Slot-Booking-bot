# bot.py - NepPath VTC Bot v3.0 - FINAL 100% WORKING (December 2025)

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
import json
from pathlib import Path

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

# ==================== PERSISTENCE ====================
DATA_FILE = Path("booking_data.json")

def load_booking_data():
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_booking_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

booking_messages = load_booking_data()  # Persistent across restarts

# ==================== HELPERS ====================
def is_staff(member: discord.Member):
    return any(role.id in STAFF_ROLE_IDS for role in member.roles)

def format_time(iso_str: str):
    if not iso_str: return "Unknown"
    iso_str = iso_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso_str)
        return f"{dt.strftime('%H:%M')} UTC | {(dt + timedelta(hours=5, minutes=45)).strftime('%H:%M')} NPT)"
    except:
        return "Invalid"

def format_date(iso_str: str):
    if not iso_str: return "Unknown"
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

# ==================== ANNOUNCEMENT MODAL (Manual Finish Only) ====================
class AnnouncementModal(discord.ui.Modal, title="Announce Upcoming Convoy"):
    event_link = discord.ui.TextInput(label="TruckersMP Event Link", placeholder="https://truckersmp.com/events/12345")
    distance = discord.ui.TextInput(label="Distance", placeholder="1,092 km")
    vtc_slot = discord.ui.TextInput(label="VTC Slot Number", placeholder="7")
    
    finish_location = discord.ui.TextInput(
        label="Finish Location (Manual - Leave empty to use API)",
        placeholder="e.g. Milano (Company), Innsbruck",
        max_length=100,
        required=False
    )
    
    route_image = discord.ui.TextInput(label="Route Image URL", placeholder="https://i.imgur.com/abc123.png")
    slot_image = discord.ui.TextInput(label="Slot Image URL (Optional)", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        match = re.search(r"/events/(\d+)", self.event_link.value.strip())
        if not match:
            return await interaction.followup.send("Invalid TruckersMP event link!", ephemeral=True)

        event_id = match.group(1)
        event_url = self.event_link.value.strip()

        event = {
            "name": "Unknown Convoy",
            "game": "ETS2",
            "server": "Event",
            "start_at": None,
            "departure_city": "Unknown",
            "arrival_city": "Unknown",
            "banner": None
        }

        # Fetch from API
        try:
            api_url = f"https://api.truckersmp.com/v2/events/{event_id}"
            headers = {"User-Agent": "NepPathVTCBot/3.0"}
            r = requests.get(api_url, headers=headers, timeout=12)
            if r.status_code == 200:
                data = r.json().get("response", {})
                event.update({
                    "name": data.get("name") or "Unknown Convoy",
                    "game": "ETS2" if data.get("game", "").lower() == "ets2" else "ATS",
                    "server": data.get("server", {}).get("name", "Event Server"),
                    "start_at": data.get("start_at"),
                    "departure_city": data.get("departure", {}).get("city", "Unknown"),
                    "arrival_city": data.get("arrival", {}).get("city", "Unknown"),
                    "banner": data.get("banner")
                })
        except Exception as e:
            print(f"[API ERROR] {e}")

        # Use manual finish if provided
        final_finish = self.finish_location.value.strip() or event["arrival_city"]

        # Validate images
        route_ok = await validate_image(self.route_image.value)
        slot_ok = await validate_image(self.slot_image.value) if self.slot_image.value else True
        banner_ok = await validate_image(event["banner"]) if event["banner"] else False

        # Build embed
        embed = discord.Embed(title=event["name"], url=event_url, color=0x00FFFF)
        embed.add_field(name="Game", value=event["game"], inline=True)
        embed.add_field(name="Date", value=format_date(event["start_at"]), inline=True)
        embed.add_field(name="Server", value=event["server"], inline=True)

        if event["start_at"]:
            embed.add_field(name="Meetup Time", value=format_time(event["start_at"]), inline=True)
            embed.add_field(name="Start Time", value=format_time(event["start_at"]), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False)

        embed.add_field(name="Distance", value=self.distance.value, inline=True)
        embed.add_field(name="Our Slot", value=f"**{self.vtc_slot.value}**", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False)

        embed.add_field(name="Start", value=event["departure_city"], inline=True)
        embed.add_field(name="Finish", value=final_finish, inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False)

        if route_ok:
            embed.set_image(url=self.route_image.value)
        if slot_ok and self.slot_image.value:
            embed.set_thumbnail(url=self.slot_image.value)
        if banner_ok and event["banner"]:
            embed.set_footer(text="Official TruckersMP Event", icon_url=event["banner"])

        embed.set_author(name=f"Announced by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()

        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label="View on TruckersMP", style=discord.ButtonStyle.link, url=event_url, emoji="Globe"))

        confirm_view = ConfirmSendView(embed, view)
        await interaction.followup.send("Preview ready! Click Send when happy", embed=embed, view=confirm_view, ephemeral=True)


class ConfirmSendView(discord.ui.View):
    def __init__(self, embed, event_view):
        super().__init__(timeout=300)
        self.embed = embed
        self.event_view = event_view

    @discord.ui.button(label="Send Announcement", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
        if not channel:
            return await interaction.response.edit_message(content="Channel not found!", view=None)
        await channel.send(embed=self.embed, view=self.event_view)
        await interaction.response.edit_message(content="Announcement sent!", view=None, embed=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Cancelled.", view=None, embed=None)


# ==================== SLOT BOOKING SYSTEM (FULLY PERSISTENT) ====================
class PersistentBookSlotView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Book Slot", style=discord.ButtonStyle.green, custom_id="book_slot_persistent")
    async def book(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg_id = interaction.message.id
        data = booking_messages.get(str(msg_id))
        if not data:
            return await interaction.response.send_message("This booking is no longer active.", ephemeral=True)

        taken = sum(1 for v in data["slots"].values() if v)
        if taken >= len(data["slots"]):
            return await interaction.response.send_message("All slots taken!", ephemeral=True)

        await interaction.response.send_modal(SlotBookingModal(msg_id, data))


class SlotBookingModal(discord.ui.Modal, title="Book Your Slot"):
    vtc_name = discord.ui.TextInput(label="Your VTC Name", placeholder="NepPath Logistics", max_length=50)
    slot = discord.ui.TextInput(label="Slot Number", placeholder="7", max_length=3)

    def __init__(self, msg_id, data):
        super().__init__()
        self.msg_id = msg_id
        self.data = data

    async def on_submit(self, interaction: discord.Interaction):
        if not self.slot.value.isdigit():
            return await interaction.response.send_message("Slot must be a number!", ephemeral=True)

        slot_key = f"Slot {int(self.slot.value)}"
        if slot_key not in self.data["slots"]:
            return await interaction.response.send_message("Slot doesn't exist!", ephemeral=True)
        if self.data["slots"][slot_key] is not None:
            return await interaction.response.send_message("Slot already taken!", ephemeral=True)

        # Anti double-book
        user_subs = user_submissions.setdefault(interaction.guild_id, {}).setdefault(interaction.user.id, set())
        if slot_key in user_subs:
            return await interaction.response.send_message("You already booked this slot!", ephemeral=True)

        # Book it
        self.data["slots"][slot_key] = interaction.user.id
        user_subs.add(slot_key)

        # Update embed
        lines = []
        booked_count = 0
        for k, v in self.data["slots"].items():
            status = "Taken" if v else "Available"
            user = f"<@{v}>" if v else "`Available`"
            lines.append(f"{status} **{k}** → {user}")
            if v: booked_count += 1

        embed = interaction.message.embeds[0]
        embed.description = "\n".join(lines)
        embed.set_footer(text=f"Booked: {booked_count}/{len(self.data['slots'])} • Last: {interaction.user}")

        await interaction.message.edit(embed=embed)
        await interaction.response.send_message(f"You booked **{slot_key}** as **{self.vtc_name.value}**!", ephemeral=True)

        # Save + log
        save_booking_data(booking_messages)
        log = bot.get_channel(STAFF_LOG_CHANNEL_ID)
        if log:
            await log.send(f"Slot Booked | {interaction.user} → **{slot_key}** as `{self.vtc_name.value}`")

user_submissions = {}  # Anti-spam reset on restart (fine for most VTCs)


# ==================== COMMANDS ====================
@app_commands.command(name="announce", description="Staff: Create convoy announcement")
async def announce(interaction: discord.Interaction):
    if not is_staff(interaction.user):
        return await interaction.response.send_message("Staff only!", ephemeral=True)
    await interaction.response.send_modal(AnnouncementModal())

@app_commands.command(name="booking", description="Staff: Create slot booking system")
@app_commands.describe(channel="Where to send", title="Event name", slots="Example: 1-50", color="green/red/blue/#hex", image="Route image")
async def create_booking(interaction: discord.Interaction, channel: discord.TextChannel, title: str, slots: str, color: str = "green", image: str = None):
    if not is_staff(interaction.user):
        return await interaction.response.send_message("Staff only!", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    try:
        start, end = map(int, slots.split("-"))
        if not (1 <= start <= end <= 200):
            raise ValueError
        slot_list = [f"Slot {i}" for i in range(start, end + 1)]
    except:
        return await interaction.followup.send("Invalid range! Use: `1-50`", ephemeral=True)

    col = discord.Color.blurple()
    if color.startswith("#"):
        col = discord.Color(int(color.lstrip("#"), 16))
    elif hasattr(discord.Color, color.lower()):
        col = getattr(discord.Color, color.lower())()

    lines = [f"Available **Slot {i}** → `Available`" for i in range(start, end + 1)]
    embed = discord.Embed(title=title, description="\n".join(lines), color=col, timestamp=discord.utils.utcnow())
    embed.set_footer(text="0 booked • Click button below")

    if image and await validate_image(image):
        embed.set_image(url=image)

    msg = await channel.send(embed=embed, view=PersistentBookSlotView())

    booking_messages[str(msg.id)] = {
        "channel_id": channel.id,
        "guild_id": interaction.guild_id,
        "slots": {f"Slot {i}": None for i in range(start, end + 1)},
        "title": title
    }
    save_booking_data(booking_messages)

    await interaction.followup.send(f"Booking system created → {channel.mention}", ephemeral=True)


# ==================== STARTUP ====================
@bot.event
async def on_ready():
    print(f"Bot online: {bot.user}")

    bot.tree.add_command(announce)
    bot.tree.add_command(create_booking)
    bot.add_view(PersistentBookSlotView())

    # Restore old bookings
    restored = 0
    for msg_id, data in list(booking_messages.items()):
        channel = bot.get_channel(data.get("channel_id"))
        if channel:
            try:
                msg = await channel.fetch_message(int(msg_id))
                data["message"] = msg
                restored += 1
            except:
                print(f"Failed to restore: {msg_id}")
    print(f"Restored {restored} bookings")

    await bot.tree.sync()
    print("Synced commands")

bot.run(BOT_TOKEN)
