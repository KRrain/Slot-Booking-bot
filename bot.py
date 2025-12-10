# bot.py - Ultimate TruckersMP VTC Bot (2025 Ready)
import aiohttp, discord, re, traceback, os, requests
from discord import app_commands
from discord.ext import commands
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ==================== CONFIG ====================
STAFF_ROLE_IDS = [1395579577555878012, 1395579347804487769, 1395580379565527110, 1395699038715642031, 1395578532406624266]
STAFF_LOG_CHANNEL_ID = 1446383730242355200  # Change if needed

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ==================== STORAGE ====================
booking_messages = {}   # {msg_id: {"message": Message, "slots": {slot: vtc_name}}}
user_submissions = {}   # {guild_id: {user_id: set(slots)}}

def is_staff(member: discord.Member):
    return any(r.id in STAFF_ROLE_IDS for r in member.roles)

# ==================== SLOT BOOKING SYSTEM ====================
class SlotBookingModal(discord.ui.Modal, title="Book Slot"):
    vtc_name = discord.ui.TextInput(label="VTC Name", placeholder="Your VTC", max_length=100)
    slot_num = discord.ui.TextInput(label="Slot Number", placeholder="e.g. 12", max_length=4)

    def __init__(self, msg_id): super().__init__(); self.msg_id = msg_id
    async def on_submit(self, i: discord.Interaction):
        if not self.slot_num.value.isdigit():
            return await i.response.send_message("Slot must be a number!", ephemeral=True)
        slot = f"Slot {int(self.slot_num.value)}"
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

# ==================== PERFECT /announcement (ONE FORM) ====================
class AnnouncementModal(discord.ui.Modal, title="Create Event Announcement"):
    event_link = discord.ui.TextInput(label="TruckersMP Event Link", placeholder="https://truckersmp.com/event/12345")
    route_img = discord.ui.TextInput(label="Route Image URL (optional)", required=False)
    slot_img = discord.ui.TextInput(label="Slot Image URL (thumbnail, optional)", required=False)

    def __init__(self, channel): super().__init__(); self.channel = channel
    async def on_submit(self, i: discord.Interaction):
        link = self.event_link.value.strip()
        eid = link.rstrip("/").split("/")[-1]
        name = "Unknown Event"
        try:
            url = f"https://api.truckersmp.com/v2/vtc/event/{eid}" if "vtc" in link.lower() else f"https://api.truckersmp.com/v2/events/{eid}"
            r = requests.get(url, timeout=10)
            if r.ok: name = r.json().get("response", {}).get("name") or r.json().get("response", {}).get("event", {}).get("title", name)
        except: pass

        embed = discord.Embed(title=name, color=0x00FF00)
        embed.add_field(name="Event Link", value=f"[Click Here]({link})", inline=False)
        if self.route_img.value: embed.set_image(url=self.route_img.value)
        if self.slot_img.value: embed.set_thumbnail(url=self.slot_img.value)
        embed.set_footer(text=f"By {i.user}", icon_url=i.user.avatar.url if i.user.avatar else None)

        await i.response.send_message("Preview:", embed=embed, view=ConfirmSendView(self.channel, embed), ephemeral=True)

class ConfirmSendView(discord.ui.View):
    def __init__(self, ch, emb): super().__init__(timeout=300); self.ch, self.emb = ch, emb
    @discord.ui.button(label="Send", style=discord.ButtonStyle.green)
    async def send(self, i: discord.Interaction, b): await self.ch.send(embed=self.emb); await i.response.edit_message(content="Sent!", view=None, embed=None)
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, i: discord.Interaction, b): await i.response.edit_message(content="Cancelled", view=None, embed=None)

class ChannelSelectView(discord.ui.View):
    def __init__(self): super().__init__(timeout=300)
    @discord.ui.select(placeholder="Choose channel", channel_types=[discord.ChannelType.text])
    async def sel(self, select: discord.ui.Select, i: discord.Interaction):
        await i.response.send_modal(AnnouncementModal(select.values[0]))

@bot.tree.command(name="announcement", description="Staff: Create beautiful event announcement")
async def announcement(i: discord.Interaction):
    if not is_staff(i.user): return await i.response.send_message("Staff only!", ephemeral=True)
    await i.response.send_message("Select channel:", view=ChannelSelectView(), ephemeral=True)

# ==================== /create & /mark ====================
@bot.tree.command(name="create", description="Staff: Create slot booking")
@app_commands.describe(channel="Channel", title="Title", slot_range="1-50", color="green/#ff0000", image="Optional image URL")
async def create(i: discord.Interaction, channel: discord.TextChannel, title: str, slot_range: str, color: str, image: str = None):
    if not is_staff(i.user): return await i.response.send_message("Staff only", ephemeral=True)
    try:
        start, end = map(int, slot_range.split("-"))
        slots = [f"Slot {x}" for x in range(start, end+1)]
    except: return await i.response.send_message("Invalid range!", ephemeral=True)
    col = discord.Color.green() if color.lower() == "green" else discord.Color(int(color.lstrip("#"), 16)) if color.startswith("#") else discord.Color.red()
    embed = discord.Embed(title=title, description="\n".join(slots), color=col)
    if image: embed.set_image(url=image)
    msg = await channel.send(embed=embed, view=BookSlotView())
    booking_messages[msg.id] = {"message": msg, "slots": {s: None for s in slots}}
    await i.response.send_message(f"Created {len(slots)} slots!", ephemeral=True)

@bot.tree.command(name="mark", description="Create attendance embed")
@app_commands.describe(event_link="TruckersMP event link")
async def mark(i: discord.Interaction, event_link: str):
    await i.response.defer(ephemeral=True)
    eid = re.search(r"/(\d+)", event_link)
    if not eid: return await i.followup.send("Invalid link", ephemeral=True)
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://api.truckersmp.com/v2/events/{eid.group(1)}") as r:
            if r.status != 200: return await i.followup.send("API error", ephemeral=True)
            data = await r.json()
    e = data.get("response", {})
    emb = discord.Embed(title="Mark Attendance", description="<@&ROLE_ID> Please mark attendance!", color=0xFF5A20)
    emb.add_field(name="Event", value=f"[{e.get('name','?')}]({event_link})", inline=False)
    if e.get("banner"): emb.set_image(url=e["banner"])
    await i.channel.send(embed=emb, view=discord.ui.View().add_item(discord.ui.Button(label="I Will Attend", style=discord.ButtonStyle.link, url=event_link)))
    await i.followup.send("Done!", ephemeral=True)

# ==================== STARTUP ====================
@bot.event
async def on_ready():
    bot.add_view(BookSlotView())
    print(f"{bot.user} is online!")
    try: synced = await bot.tree.sync(); print(f"Synced {len(synced)} commands")
    except Exception as e: print(e)

bot.run(BOT_TOKEN)
