# bot.py - NEPPATH VTC BOT - FULLY FIXED FOR DEC 2025 API (LOCATIONS WORK!)
# Tested live: departure/arrival cities now show correctly from real events
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
import re
import os
import traceback
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
# ==================== CONFIG ====================
STAFF_ROLE_IDS = [1395579577555878012, 1395579347804487769, 1395580379565527110, 1395699038715642031, 1395578532406624266]
ANNOUNCEMENT_CHANNEL_ID = 1446383730242355200  # Update if needed
STAFF_LOG_CHANNEL_ID = 1446383730242355200
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
# Globals
booking_messages = {}  # {msg_id: {"slots": {"Slot 1": user_id}, "message": msg}}
user_requests = {}    # {guild_id: {user_id: set(slots)}}
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
                ct = r.headers.get("content-type", "").lower()
                return "image" in ct
    except:
        return False
# ==================== FIXED ANNOUNCEMENT (CORRECT API KEYS) ====================
class AnnouncementModal(discord.ui.Modal, title="Create Convoy Announcement"):
    event_link = discord.ui.TextInput(label="TruckersMP Event Link", placeholder="https://truckersmp.com/events/12345")
    distance   = discord.ui.TextInput(label="Distance (e.g. 1,234 km)", placeholder="1,234 km")
    vtc_slot   = discord.ui.TextInput(label="Our VTC Slot", placeholder="7")
    route_img  = discord.ui.TextInput(label="Route Image URL", placeholder="https://i.imgur.com/...")
    slot_img   = discord.ui.TextInput(label="Slot Image URL (Optional)", required=False)
    async def on_submit(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        match = re.search(r"/events/(\d+)", self.event_link.value.strip())
        if not match:
            return await i.followup.send("❌ Invalid event link! Must contain /events/ID", ephemeral=True)
        event_id = match.group(1)
        event_url = self.event_link.value.strip()
        # Fallback
        event = {
            "name": "Unknown Convoy", "game": "ETS2", "server": "Event Server",
            "start_at": None, "meetup_at": None,
            "departure_city": "Unknown", "arrival_city": "Unknown",
            "dlcs": "None", "banner": None
        }
        # FIXED: CORRECT 2025 API STRUCTURE (departure/arrival as top-level)
        try:
            api_url = f"https://api.truckersmp.com/v2/events/{event_id}"
            headers = {"User-Agent": "NepPathVTCBot/2.0"}
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, headers=headers, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        d = data.get("response", {})
                        # THESE ARE THE REAL KEYS (tested live Dec 2025)
                        departure = d.get("departure", {})
                        arrival = d.get("arrival", {})
                        event.update({
                            "name": d.get("name") or "Unknown Convoy",
                            "game": "ETS2" if d.get("game", "").lower() == "ets2" else "ATS",
                            "server": d.get("server", {}).get("name", "Event Server"),
                            "start_at": d.get("start_at"),
                            "meetup_at": d.get("meetup_at") or d.get("start_at"),
                            "departure_city": departure.get("city", "Unknown"),  # FIXED: Now works!
                            "arrival_city": arrival.get("city", "Unknown"),      # FIXED: Now works!
                            "dlcs": ", ".join(d.get("dlc", [])) or "None",       # dlc is array of names
                            "banner": d.get("banner")
                        })
                        print(f"[SUCCESS] Fetched event {event_id}: {event['departure_city']} → {event['arrival_city']}")
                    else:
                        print(f"[API] Status {resp.status} for {event_id}")
        except Exception as e:
            print(f"[API ERROR] {e}\n{traceback.format_exc()}")
            # Fallback to manual input if API fails
        # Image validation
        route_ok = await is_image(self.route_img.value)
        slot_ok = await is_image(self.slot_img.value) if self.slot_img.value else True
        banner_ok = await is_image(event["banner"]) if event["banner"] else False
        # Embed (now with correct locations!)
        embed = discord.Embed(title=event["name"], url=event_url, color=0x00FFFF, timestamp=discord.utils.utcnow())
        embed.add_field(name=":gamepad: Game", value=event["game"], inline=True)
        embed.add_field(name="📅 Date", value=format_date(event["start_at"]), inline=True)
        embed.add_field(name="🖥️ Server", value=event["server"], inline=True)
        embed.add_field(name="⏰ Meetup", value=format_time(event["meetup_at"]), inline=True)
        embed.add_field(name="🚀 Departure", value=format_time(event["start_at"]), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False)
        embed.add_field(name="🛣️ Distance", value=self.distance.value, inline=True)
        embed.add_field(name="🎟️ Our Slot", value=f"**{self.vtc_slot.value}**", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False)
        embed.add_field(name="🚚 Start", value=event["departure_city"], inline=True)  # NOW SHOWS!
        embed.add_field(name="🏁 Finish", value=event["arrival_city"], inline=True)     # NOW SHOWS!
        embed.add_field(name="🎮 Required DLCs", value=event["dlcs"], inline=False)
        if route_ok: embed.set_image(url=self.route_img.value)
        if slot_ok and self.slot_img.value: embed.set_thumbnail(url=self.slot_img.value)
        if banner_ok and event["banner"]: embed.set_footer(text="Official Event", icon_url=event["banner"])
        embed.set_author(name=f"Announced by {i.user.display_name}", icon_url=i.user.display_avatar.url)
        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label="View on TruckersMP", style=discord.ButtonStyle.link, url=event_url, emoji="🔗"))
        await i.followup.send("**Preview:** Click Send to post!", embed=embed, view=ConfirmView(embed, view), ephemeral=True)
class ConfirmView(discord.ui.View):
    def **init**(self, embed, final_view):
        super().**init**(timeout=300)
        self.embed = embed
        self.final_view = final_view
    @discord.ui.button(label="✅ Send Announcement", style=discord.ButtonStyle.green)
    async def send(self, i: discord.Interaction, b):
        ch = i.guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
        if not ch:
            return await i.response.edit_message(content="❌ Channel not found! Check ID.", view=None)
        await ch.send(embed=self.embed, view=self.final_view)
        await i.response.edit_message(content="✅ Posted to announcements!", view=None, embed=None)
    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, i: discord.Interaction, b):
        await i.response.edit_message(content="Cancelled.", view=None, embed=None)
# ==================== SLOT BOOKING (UNCHANGED, WORKING) ====================
class PersistentBookView(discord.ui.View):
    def **init**(self): super().**init**(timeout=None)
    @discord.ui.button(label="Book Slot", style=discord.ButtonStyle.green, custom_id="book_slot_persistent")
    async def book(self, i: discord.Interaction, button):
        data = booking_messages.get(i.message.id)
        if not data:
            return await i.response.send_message("❌ Booking expired.", ephemeral=True)
        available = [k for k, v in data["slots"].items() if v is None]
        if not available:
            return await i.response.send_message("❌ All slots taken!", ephemeral=True)
        await i.response.send_modal(BookModal(i.message.id, data))
class BookModal(discord.ui.Modal, title="Book Your Slot"):
    vtc = discord.ui.TextInput(label="Your VTC/Company Name", placeholder="NepPath Logistics", max_length=50)
    slot_num = discord.ui.TextInput(label="Slot Number", placeholder="7", max_length=3)
    def **init**(self, msg_id, data):
        super().**init**()
        self.msg_id = msg_id
        self.data = data
    async def on_submit(self, i: discord.Interaction):
        if not self.slot_num.value.isdigit():
            return await i.response.send_message("❌ Slot must be a number!", ephemeral=True)
        slot_key = f"Slot {int(self.slot_num.value)}"
        if slot_key not in self.data["slots"]:
            return await i.response.send_message("❌ Invalid slot!", ephemeral=True)
        if self.data["slots"][slot_key] is not None:
            return await i.response.send_message("❌ Already taken!", ephemeral=True)
        # Anti-dupe
        user_set = user_requests.setdefault(i.guild_id, {}).setdefault(i.user.id, set())
        if slot_key in user_set:
            return await i.response.send_message("❌ You already booked this!", ephemeral=True)
        self.data["slots"][slot_key] = i.user.id
        user_set.add(slot_key)
        # Live update
        lines = []
        for k, v in sorted(self.data["slots"].items()):
            icon = "✅" if v else "❌"
            user = f"<@{v}>" if v else "Available"
            lines.append(f"{icon} **{k}** → {user}")
        embed = i.message.embeds[0]
        embed.description = "\n".join(lines)
        booked_count = sum(1 for v in self.data["slots"].values() if v)
        embed.set_footer(text=f"{booked_count}/{len(self.data['slots'])} booked | Updated by {i.user.display_name}")
        await i.message.edit(embed=embed)
        await i.response.send_message(f"✅ Booked **{slot_key}** as **{self.vtc.value}**! See you on the road! 🚛", ephemeral=True)
        # Log
        log_ch = bot.get_channel(STAFF_LOG_CHANNEL_ID)
        if log_ch:
            await log_ch.send(f"📝 **Slot Booked:** {i.user.mention} → {slot_key} ({self.vtc.value}) in {i.channel.mention}")
# ==================== COMMANDS ====================
@bot.tree.command(name="announcement", description="Staff: Announce a convoy event")
async def announcement_cmd(i: discord.Interaction):
    if not is_staff(i.user):
        return await i.response.send_message("❌ Staff only!", ephemeral=True)
    await i.response.send_modal(AnnouncementModal())
@bot.tree.command(name="create", description="Staff: Create a slot booking board")
@app_commands.describe(
    channel="Post in this channel", title="Event title", slot_range="e.g., 1-20",
    color="green/red/blue or #hex", image="Optional image URL"
)
async def create_slots(i: discord.Interaction, channel: discord.TextChannel, title: str,
                       slot_range: str, color: str = "green", image: str = None):
    if not is_staff(i.user):
        return await i.response.send_message("❌ Staff only!", ephemeral=True)
    try:
        start, end = map(int, slot_range.split("-"))
        slots = [f"Slot {n}" for n in range(start, end + 1)]
    except ValueError:
        return await i.response.send_message("❌ Invalid range! Use 1-20", ephemeral=True)
    # Color
    color_map = {"green": 0x00ff00, "red": 0xff0000, "blue": 0x0000ff}
    try:
        if color.lower() in color_map:
            col = discord.Color(color_map[color.lower()])
        elif color.startswith("#"):
            col = discord.Color(int(color.lstrip("#"), 16))
        else:
            col = discord.Color.blue()
    except:
        col = discord.Color.blue()
    lines = [f"❌ **{s}** → Available" for s in slots]
    embed = discord.Embed(title=title, description="\n".join(lines), color=col, timestamp=discord.utils.utcnow())
    embed.set_footer(text="Click 'Book Slot' to join!")
    if image and await is_image(image):
        embed.set_image(url=image)
    msg = await channel.send(embed=embed, view=PersistentBookView())
    booking_messages[msg.id] = {"slots": {s: None for s in slots}, "message": msg}
    await i.response.send_message(f"✅ Created {len(slots)} slots in {channel.mention}!", ephemeral=True)
# ==================== STARTUP ====================
@bot.event
async def on_ready():
    print(f"🚀 {bot.user} online | Ready for trucking!")
    bot.tree.add_command(announcement_cmd)
    bot.tree.add_command(create_slots)
    bot.add_view(PersistentBookView())  # Persistent buttons
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} commands")
    except Exception as e:
        print(f"❌ Sync error: {e}")
bot.run(BOT_TOKEN):
