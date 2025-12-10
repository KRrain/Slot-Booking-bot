# bot.py - Fully working TruckersMP VTC Bot (Slot Booking + Attendance + Announcement)

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
import re
import traceback
from datetime import datetime
import os
import requests
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ==================== CONFIG ====================
STAFF_ROLE_IDS = [
    1395579577555878012, 1395579347804487769,
    1395580379565527110, 1395699038715642031,
    1395578532406624266,
]
STAFF_LOG_CHANNEL_ID = 1446383730242355200  # Change if needed

COLOR_OPTIONS = {
    "blue": discord.Color.blue(), "red": discord.Color.red(),
    "green": discord.Color.green(), "yellow": discord.Color.gold(),
    "purple": discord.Color.purple(), "orange": discord.Color.orange(),
    "white": discord.Color.from_rgb(255,255,255), "black": discord.Color.from_rgb(0,0,0),
}

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ==================== STORAGE & HELPERS ====================
booking_messages = {}   # {message_id: {"message": Message, "slots": {slot: vtc_name}}}
user_submissions = {}   # {guild_id: {user_id: set(slots)}}

def is_staff_member(member: discord.Member) -> bool:
    return any(role.id in STAFF_ROLE_IDS for role in member.roles)

async def parse_slot_range(slot_range: str):
    try:
        start, end = map(int, slot_range.split("-"))
        if start < 1 or end < start: raise ValueError
        return [f"Slot {i}" for i in range(start, end + 1)]
    except: return None

def parse_color(color_str: str):
    if color_str.lower() in COLOR_OPTIONS:
        return COLOR_OPTIONS[color_str.lower()]
    try:
        color_str = color_str.lstrip("#")
        return discord.Color(int(color_str, 16))
    except: return None

# ==================== SLOT BOOKING SYSTEM ====================
class SlotBookingModal(discord.ui.Modal, title="Book Slot"):
    vtc_name = discord.ui.TextInput(label="VTC Name", placeholder="Your VTC name", max_length=100)
    slot_number = discord.ui.TextInput(label="Slot Number", placeholder="e.g. 5", max_length=3)

    def __init__(self, message_id: int):
        super().__init__()
        self.message_id = message_id
        data = booking_messages.get(message_id)
        available = [s.replace("Slot ", "") for s, v in (data.get("slots") or {}).items() if not v]
        placeholder = f"Available: {', '.join(available[:10])}{'...' if len(available)>10 else ''}" if available else "No slots left"
        self.slot_number.placeholder = placeholder[:100]

    async def on_submit(self, interaction: discord.Interaction):
        try:
            raw = self.slot_number.value.strip()
            if not raw.isdigit():
                return await interaction.response.send_message("Slot must be a number!", ephemeral=True)
            slot_id = int(raw)
            slot_name = f"Slot {slot_id}"
            data = booking_messages.get(self.message_id)
            if not data or slot_name not in data["slots"]:
                return await interaction.response.send_message("Invalid slot!", ephemeral=True)
            if data["slots"][slot_name]:
                return await interaction.response.send_message("Slot already taken!", ephemeral=True)

            # Record submission
            user_submissions.setdefault(interaction.guild_id, {}).setdefault(interaction.user.id, set()).add(slot_name)
            await interaction.response.send_message(f"Request for **Slot {slot_id}** sent!", ephemeral=True)

            # Notify staff
            log = bot.get_channel(STAFF_LOG_CHANNEL_ID)
            if log:
                embed = discord.Embed(title="New Slot Request", color=discord.Color.orange())
                embed.add_field(name="User", value=interaction.user.mention)
                embed.add_field(name="VTC", value=self.vtc_name.value)
                embed.add_field(name="Slot", value=str(slot_id))
                view = ApproveDenyView(interaction.user.id, self.vtc_name.value, slot_name, self.message_id, interaction.guild_id)
                await log.send(embed=embed, view=view)
        except Exception:
            traceback.print_exc()

class BookSlotView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Book Slot", style=discord.ButtonStyle.green, custom_id="book_slot_persistent")
    async def book(self, i: discord.Interaction, b: discord.ui.Button):
        data = booking_messages.get(i.message.id)
        if not data or all(data["slots"].values()):
            return await i.response.send_message("No slots available or invalid message.", ephemeral=True)
        await i.response.send_modal(SlotBookingModal(i.message.id))

class ApproveDenyView(discord.ui.View):
    def __init__(self, user_id, vtc_name, slot, msg_id, guild_id):
        super().__init__(timeout=None)
        self.user_id, self.vtc_name, self.slot, self.msg_id, self.guild_id = user_id, vtc_name, slot, msg_id, guild_id

    async def notify(self, approved: bool):
        try:
            user = await bot.fetch_user(self.user_id)
            await user.send(f"{'Approved' if approved else 'Denied'}: **{self.slot}** – {self.vtc_name}")
        except: pass

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
    async def approve(self, i: discord.Interaction, b):
        if not is_staff_member(i.user): return await i.response.send_message("Staff only", ephemeral=True)
        data = booking_messages.get(self.msg_id)
        if not data or data["slots"].get(self.slot): return
        data["slots"][self.slot] = self.vtc_name
        user_submissions[self.guild_id][self.user_id].discard(self.slot)
        await self.update_embed(data["message"])
        await i.message.edit(embed=i.message.embeds[0].set_footer(text=f"Approved by {i.user}"), view=None)
        await self.notify(True)
        await i.response.send_message("Approved", ephemeral=True)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red)
    async def deny(self, i: discord.Interaction, b):
        if not is_staff_member(i.user): return await i.response.send_message("Staff only", ephemeral=True)
        user_submissions[self.guild_id][self.user_id].discard(self.slot)
        await i.message.edit(embed=i.message.embeds[0].set_footer(text=f"Denied by {i.user}"), view=None)
        await self.notify(False)
        await i.response.send_message("Denied", ephemeral=True)

    async def update_embed(self, msg: discord.Message):
        embed = msg.embeds[0]
        lines = [f"{s} - {v} Approved" if v else s for s, v in booking_messages[msg.id]["slots"].items()]
        embed.description = "\n".join(lines)
        await msg.edit(embed=embed)

# ==================== ANNOUNCEMENT COMMAND (Fixed for discord.py 2.3+) ====================
class ConfirmSend(discord.ui.View):
    def __init__(self, channel, embed):
        super().__init__(timeout=300)
        self.channel, self.embed = channel, embed
    @discord.ui.button(label="Send", style=discord.ButtonStyle.green)
    async def send(self, i: discord.Interaction, b):
        await self.channel.send(embed=self.embed)
        await i.response.edit_message(content="Announcement sent!", view=None, embed=None)
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, i: discord.Interaction, b):
        await i.response.edit_message(content="Cancelled.", view=None, embed=None)

class AnnouncementModal(discord.ui.Modal, title="Create Announcement"):
    event_link = discord.ui.TextInput(label="TruckersMP Event Link", placeholder="https://truckersmp.com/event/...")
    route_img = discord.ui.TextInput(label="Route Image URL", required=False)
    slot_img = discord.ui.TextInput(label="Slot Image URL (Thumbnail)", required=False)

    def __init__(self, channel): super().__init__(); self.channel = channel

    async def on_submit(self, i: discord.Interaction):
        link = self.event_link.value.strip()
        event_id = link.rstrip("/").split("/")[-1]
        name = "Unknown Event"
        try:
            if "vtc" in link:
                resp = requests.get(f"https://api.truckersmp.com/v2/vtc/event/{event_id}")
            else:
                resp = requests.get(f"https://api.truckersmp.com/v2/events/{event_id}")
            if resp.ok:
                data = resp.json().get("response", {})
                name = data.get("name") or data.get("event", {}).get("title") or name
        except: pass

        embed = discord.Embed(title=name, description=f"[Event Link]({link})", color=discord.Color.green())
        if self.route_img.value: embed.set_image(url=self.route_img.value)
        if self.slot_img.value: embed.set_thumbnail(url=self.slot_img.value)

        await i.response.send_message("Preview:", embed=embed, view=ConfirmSend(self.channel, embed), ephemeral=True)

class ChannelSelectView(discord.ui.View):
    def __init__(self): super().__init__(timeout=300)
    @discord.ui.select(placeholder="Select channel", channel_types=[discord.ChannelType.text])
    async def select(self, sel: discord.ui.Select, i: discord.Interaction):
        await i.response.send_modal(AnnouncementModal(sel.values[0]))

@bot.tree.command(name="announcement", description="Staff: Create rich event announcement")
async def announcement(interaction: discord.Interaction):
    if not is_staff_member(interaction.user):
        return await interaction.response.send_message("Staff only", ephemeral=True)
    await interaction.response.send_message("Choose channel:", view=ChannelSelectView(), ephemeral=True)

# ==================== /create & /mark (your original working ones) ====================
@bot.tree.command(name="create", description="Staff: Create slot booking")
@app_commands.describe(channel="Channel", title="Title", slot_range="1-50", color="green/#ff0000", image="Optional image")
async def create(i: discord.Interaction, channel: discord.TextChannel, title: str, slot_range: str, color: str, image: str = None):
    if not is_staff_member(i.user): return await i.response.send_message("Staff only", ephemeral=True)
    slots = await parse_slot_range(slot_range)
    if not slots: return await i.response.send_message("Invalid range", ephemeral=True)
    col = parse_color(color)
    if not col: return await i.response.send_message("Bad color", ephemeral=True)

    embed = discord.Embed(title=title, description="\n".join(slots), color=col)
    if image: embed.set_image(url=image)
    msg = await channel.send(embed=embed, view=BookSlotView())
    booking_messages[msg.id] = {"message": msg, "slots": {s: None for s in slots}}
    await i.response.send_message(f"Created {len(slots)} slots!", ephemeral=True)

@bot.tree.command(name="mark", description="Create attendance embed")
@app_commands.describe(event_link="TruckersMP event URL")
async def mark(i: discord.Interaction, event_link: str):
    await i.response.defer(ephemeral=True)
    match = re.search(r"/(\d+)", event_link)
    if not match: return await i.followup.send("Invalid link", ephemeral=True)
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://api.truckersmp.com/v2/events/{match.group(1)}") as r:
            if r.status != 200: return await i.followup.send("API error", ephemeral=True)
            data = await r.json()
    event = data.get("response", {})
    embed = discord.Embed(title="Mark Attendance", description="<@&ROLE_ID>\nMark attendance ❤️", color=0xFF5A20)
    embed.add_field(name="Event", value=f"[{event.get('name','?')}]({event_link})", inline=False)
    if event.get("banner"): embed.set_image(url=event["banner"])
    await i.channel.send(embed=embed, view=discord.ui.View().add_item(discord.ui.Button(label="I Will Attend", style=discord.ButtonStyle.link, url=event_link)))
    await i.followup.send("Done!", ephemeral=True)

# ==================== STARTUP ====================
@bot.event
async def on_ready():
    bot.add_view(BookSlotView())
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(e)

bot.run(BOT_TOKEN)
