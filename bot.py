# bot.py - FINAL ULTIMATE TRUCKERSMP VTC BOT (2025) - WITH VISIT EVENT BUTTON

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
ANNOUNCEMENT_CHANNEL_ID = 1446383730242355200  # CHANGE TO YOUR ANNOUNCEMENT CHANNEL
STAFF_LOG_CHANNEL_ID = 1446383730242355200

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
        npt = (dt + timedelta(hours=5, minutes=45)).strftime("%H:%M NPT")
        return f"{utc} | {npt}"
    except:
        return "Unknown"

def format_date(iso_str: str):
    if not iso_str: return "Unknown"
    iso_str = iso_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%A, %d %B %Y")
    except:
        return "Unknown"

async def validate_image(url: str) -> bool:
    if not url or not url.startswith("http"): return False
    try:
        async with aiohttp.ClientSession() as s:
            async with s.head(url, timeout=aiohttp.ClientTimeout(total=6)) as r:
                return "image" in r.headers.get("content-type", "").lower()
    except:
        return False

# ==================== SLOT BOOKING SYSTEM (FULLY WORKING) ====================
booking_messages = {}
user_submissions = {}

class SlotBookingModal(discord.ui.Modal, title="Book Slot"):
    vtc_name = discord.ui.TextInput(label="VTC Name", placeholder="Your VTC", max_length=100)
    slot_number = discord.ui.TextInput(label="Slot Number", placeholder="e.g. 12", max_length=3)

    def __init__(self, msg_id): super().__init__(); self.msg_id = msg_id
    async def on_submit(self, i: discord.Interaction):
        if not self.slot_number.value.isdigit():
            return await i.response.send_message("Slot must be a number!", ephemeral=True)
        slot = f"Slot {int(self.slot_number.value)}"
        data = booking_messages.get(self.msg_id)
        if not data or slot not in data["slots"] or data["slots"][slot]:
            return await i.response.send_message("Invalid or taken slot!", ephemeral=True)
        user_submissions.setdefault(i.guild_id, {}).setdefault(i.user.id, set()).add(slot)
        await i.response.send_message(f"Request sent for **{slot}**!", ephemeral=True)

        log = bot.get_channel(STAFF_LOG_CHANNEL_ID)
        if log:
            embed = discord.Embed(title="Slot Request", color=0xFFAA00)
            embed.add_field(name="User", value=i.user.mention)
            embed.add_field(name="VTC", value=self.vtc_name.value)
            embed.add_field(name="Slot", value=slot)
            await log.send(embed=embed, view=ApproveDenyView(i.user.id, self.vtc_name.value, slot, self.msg_id, i.guild_id))

class BookSlotView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Book Slot", style=discord.ButtonStyle.green, custom_id="book_slot_btn")
    async def book(self, i: discord.Interaction, b):
        data = booking_messages.get(i.message.id)
        if not data or all(data["slots"].values()):
            return await i.response.send_message("No slots available!", ephemeral=True)
        await i.response.send_modal(SlotBookingModal(i.message.id))

class ApproveDenyView(discord.ui.View):
    def __init__(self, uid, vtc, slot, mid, gid):
        super().__init__(timeout=None)
        self.uid, self.vtc, self.slot, self.mid, self.gid = uid, vtc, slot, mid, gid
    async def update(self, msg: discord.Message):
        e = msg.embeds[0]
        e.description = "\n".join(f"{s} - {v} Approved" if v else s for s, v in booking_messages[msg.id]["slots"].items())
        await msg.edit(embed=e)
    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
    async def approve(self, i: discord.Interaction, b):
        if not is_staff(i.user): return await i.response.send_message("Staff only", ephemeral=True)
        data = booking_messages.get(self.mid)
        if data and not data["slots"].get(self.slot):
            data["slots"][self.slot] = self.vtc
            user_submissions[self.gid][self.uid].discard(self.slot)
            await self.update(data["message"])
            await i.message.edit(embed=i.message.embeds[0].set_footer(text=f"Approved by {i.user}"), view=None)
            await i.response.send_message("Approved!", ephemeral=True)
    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red)
    async def deny(self, i: discord.Interaction, b):
        if not is_staff(i.user): return await i.response.send_message("Staff only", ephemeral=True)
        user_submissions[self.gid][self.uid].discard(self.slot)
        await i.message.edit(embed=i.message.embeds[0].set_footer(text=f"Denied by {i.user}"), view=None)
        await i.response.send_message("Denied", ephemeral=True)

@bot.tree.command(name="create", description="Staff: Create slot booking")
@app_commands.describe(channel="Channel", title="Title", slot_range="1-50", color="green/#hex", image="Optional image")
async def create(i: discord.Interaction, channel: discord.TextChannel, title: str, slot_range: str, color: str = "green", image: str = None):
    if not is_staff(i.user): return await i.response.send_message("Staff only", ephemeral=True)
    try:
        start, end = map(int, slot_range.split("-"))
        slots = [f"Slot {x}" for x in range(start, end+1)]
    except: return await i.response.send_message("Invalid range!", ephemeral=True)
    col = discord.Color.green() if color.lower() == "green" else discord.Color(int(color.lstrip("#"), 16))
    embed = discord.Embed(title=title, description="\n".join(slots), color=col)
    if image: embed.set_image(url=image)
    msg = await channel.send(embed=embed, view=BookSlotView())
    booking_messages[msg.id] = {"message": msg, "slots": {s: None for s in slots}}
    await i.response.send_message(f"Created {len(slots)} slots!", ephemeral=True)

# ==================== FINAL /announcement WITH VISIT EVENT BUTTON ====================
class AnnouncementModal(discord.ui.Modal, title="Announce Upcoming Convoy"):
    event_link = discord.ui.TextInput(label="TruckersMP Event Link", placeholder="https://truckersmp.com/events/12345")
    distance = discord.ui.TextInput(label="Distance", placeholder="1,092 KM")
    vtc_slot = discord.ui.TextInput(label="VTC Slot Number", placeholder="7")
    route_image = discord.ui.TextInput(label="Route Image URL", placeholder="https://i.imgur.com/...")
    slot_image = discord.ui.TextInput(label="Slot Image URL (optional)", placeholder="https://i.imgur.com/...", required=False)

    async def on_submit(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)

        match = re.search(r"/events/(\d+)", self.event_link.value)
        if not match:
            return await i.followup.send("Invalid event link!", ephemeral=True)
        event_id = match.group(1)
        event_url = self.event_link.value.strip()

        # Fetch event data
        data = {
            "name": "Unknown Convoy", "game": "ETS2", "server": {"name": "Event Server"},
            "start_at": None, "meetup_at": None,
            "departure": {"city": "Unknown"}, "arrival": {"city": "Unknown"},
            "dlc": [], "banner": None
        }
        try:
            r = requests.get(f"https://api.truckersmp.com/v2/events/{event_id}", timeout=10)
            if r.status_code == 200:
                resp = r.json().get("response", {})
                data.update({
                    "name": resp.get("name", "Unknown"),
                    "game": "ETS2" if "ets2" in resp.get("game", "").lower() else "ATS",
                    "server": resp.get("server", {"name": "Event Server"}),
                    "start_at": resp.get("start_at"),
                    "meetup_at": resp.get("meetup_at") or resp.get("start_at"),
                    "departure": resp.get("departure", {"city": "Unknown"}),
                    "arrival": resp.get("arrival", {"city": "Unknown"}),
                    "dlc": resp.get("dlc", []),
                    "banner": resp.get("banner")
                })
        except: pass

        # Validate images
        route_ok = await validate_image(self.route_image.value)
        slot_ok = await validate_image(self.slot_image.value) if self.slot_image.value else False
        banner_ok = await validate_image(data["banner"]) if data["banner"] else False

        # FINAL EMBED
        embed = discord.Embed(title=data["name"], color=0x00FFFF, url=event_url)
        embed.add_field(name="Game", value=data["game"], inline=True)
        embed.add_field(name="Date", value=format_date(data["start_at"]), inline=True)
        embed.add_field(name="Server", value=data["server"]["name"], inline=True)

        embed.add_field(name="Meetup Time", value=format_time(data["meetup_at"]), inline=True)
        embed.add_field(name="Departure Time", value=format_time(data["start_at"]), inline=True)
        embed.add_field(name="", value="", inline=False)

        embed.add_field(name="Distance", value=self.distance.value, inline=True)
        embed.add_field(name="VTC Slot", value=self.vtc_slot.value, inline=True)
        embed.add_field(name="", value="", inline=False)

        embed.add_field(name="Departure Location", value=data["departure"]["city"], inline=True)
        embed.add_field(name="Destination Location", value=data["arrival"]["city"], inline=True)
        embed.add_field(name="Required DLCs", value=", ".join(data["dlc"]) or "None", inline=False)

        if route_ok: embed.set_image(url=self.route_image.value)
        if slot_ok and self.slot_image.value: embed.set_thumbnail(url=self.slot_image.value)
        if banner_ok and data["banner"]: embed.set_footer(text="Official Event Banner", icon_url=data["banner"])
        embed.set_author(name=f"Announced by {i.user}", icon_url=i.user.display_avatar.url)

        # VIEW WITH "VISIT OFFICIAL EVENT" BUTTON
        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label="Visit Official Event", style=discord.ButtonStyle.link, url=event_url, emoji="Link"))

        await i.followup.send("**Preview – Click Send:**", embed=embed, view=ConfirmSendView(embed, view), ephemeral=True)

class ConfirmSendView(discord.ui.View):
    def __init__(self, embed, event_view):
        super().__init__(timeout=300)
        self.embed = embed
        self.event_view = event_view
    @discord.ui.button(label="Send Announcement", style=discord.ButtonStyle.green)
    async def send(self, i: discord.Interaction, b):
        ch = i.guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
        if not ch: return await i.response.edit_message(content="Channel not found!", view=None)
        await ch.send(embed=self.embed, view=self.event_view)
        await i.response.edit_message(content="Announcement sent with Visit Event button!", view=None, embed=None)
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, i: discord.Interaction, b):
        await i.response.edit_message(content="Cancelled", view=None, embed=None)

@bot.tree.command(name="announcement", description="Staff: Announce convoy with Visit Event button")
async def announcement(i: discord.Interaction):
    if not is_staff(i.user):
        return await i.response.send_message("Staff only!", ephemeral=True)
    await i.response.send_modal(AnnouncementModal())

# ==================== STARTUP ====================
@bot.event
async def on_ready():
    bot.add_view(BookSlotView())
    print(f"NepPath Bot Online: {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(e)

bot.run(BOT_TOKEN)
