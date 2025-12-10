# bot.py - NEPPATH VTC BOT - FIXED MODAL LIMIT (DEC 2025)
# Sequential modals: 3 fields → Preview → Optional 2-field city edit

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
ANNOUNCEMENT_CHANNEL_ID = 1446383730242355200
STAFF_LOG_CHANNEL_ID = 1446383730242355200

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# Globals
booking_messages = {}   # {message_id: data}
user_requests = {}      # anti-dupe
temp_data = {}          # {user_id: {"event": data, "embed": embed, "view": view}}


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
    if not url or not url.startswith("http"):
        return False
    try:
        async with aiohttp.ClientSession() as s:
            async with s.head(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                return "image" in r.headers.get("content-type", "").lower()
    except:
        return False


# ==================== FIRST MODAL (3 FIELDS ONLY - EVENT BASICS) ====================
class AnnouncementModal1(discord.ui.Modal, title="Convoy Announcement - Step 1"):
    event_link = discord.ui.TextInput(label="TruckersMP Event Link", placeholder="https://truckersmp.com/events/12345")
    distance   = discord.ui.TextInput(label="Distance (e.g. 1,234 km)", placeholder="1,234 km")
    vtc_slot   = discord.ui.TextInput(label="Our VTC Slot", placeholder="7")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        match = re.search(r"/events/(\d+)", self.event_link.value.strip())
        if not match:
            return await interaction.followup.send("❌ Invalid event link! Must contain /events/ID", ephemeral=True)

        event_id = match.group(1)
        event_url = self.event_link.value.strip()

        # Default data
        event = {
            "name": "Unknown Convoy", "game": "ETS2", "server": "Event Server",
            "start_at": None, "meetup_at": None,
            "departure_city": "Unknown", "arrival_city": "Unknown",
            "dlcs": "None", "banner": None,
            "distance": self.distance.value.strip(),
            "vtc_slot": self.vtc_slot.value.strip()
        }

        # Fetch from TruckersMP API
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://api.truckersmp.com/v2/events/{event_id}",
                    headers={"User-Agent": "NepPathVTCBot/2.1"},
                    timeout=15
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        d = data.get("response", {})
                        dep = d.get("departure", {})
                        arr = d.get("arrival", {})

                        event.update({
                            "name": d.get("name") or "Unknown Convoy",
                            "game": "ETS2" if str(d.get("game", "")).lower() == "ets2" else "ATS",
                            "server": d.get("server", {}).get("name", "Event Server"),
                            "start_at": d.get("start_at"),
                            "meetup_at": d.get("meetup_at") or d.get("start_at"),
                            "departure_city": dep.get("city", "Unknown"),
                            "arrival_city": arr.get("city", "Unknown"),
                            "dlcs": ", ".join(d.get("dlc", [])) or "None",
                            "banner": d.get("banner")
                        })
        except Exception as e:
            print(f"[API ERROR] {e}")

        # Temp store (no cities yet)
        temp_data[interaction.user.id] = {
            "event": event,
            "event_url": event_url,
            "route_img": None,  # Will ask in next step if needed
            "slot_img": None
        }

        # Build PREVIEW embed (with API cities)
        embed = discord.Embed(title=event["name"], url=event_url, color=0x00FFFF, timestamp=discord.utils.utcnow())
        embed.add_field(name=":gamepad: Game", value=event["game"], inline=True)
        embed.add_field(name="📅 Date", value=format_date(event["start_at"]), inline=True)
        embed.add_field(name="🖥️ Server", value=event["server"], inline=True)

        embed.add_field(name="⏰ Meetup", value=format_time(event["meetup_at"]), inline=True)
        embed.add_field(name="🚀 Departure", value=format_time(event["start_at"]), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False)

        embed.add_field(name="🛣️ Distance", value=event["distance"], inline=True)
        embed.add_field(name="🎟️ Our Slot", value=f"**{event['vtc_slot']}**", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False)

        embed.add_field(name="🚚 Start", value=event["departure_city"], inline=True)
        embed.add_field(name="🏁 Finish", value=event["arrival_city"], inline=True)
        embed.add_field(name="🎮 Required DLCs", value=event["dlcs"], inline=False)

        embed.set_author(name=f"Preview by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)

        # Images will be added in step 2
        view = PreviewView1()
        await interaction.followup.send("**Step 1 Complete!** Preview below. Add images & edit cities in Step 2?", embed=embed, view=view, ephemeral=True)


# ==================== PREVIEW VIEW AFTER STEP 1 ====================
class PreviewView1(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=900)  # 15 min

    @discord.ui.button(label="➡️ Step 2: Add Images & Edit Cities", style=discord.ButtonStyle.primary)
    async def step2(self, interaction: discord.Interaction, button):
        await interaction.response.send_modal(AnnouncementModal2())

    @discord.ui.button(label="✅ Looks Good - Post Now", style=discord.ButtonStyle.green)
    async def post_now(self, interaction: discord.Interaction, button):
        data = temp_data.get(interaction.user.id)
        if not data:
            return await interaction.response.send_message("❌ Data expired. Start over.", ephemeral=True)

        # Use API cities, no images
        event = data["event"]
        embed = create_embed(event, data["event_url"], no_images=True)
        final_view = create_final_view(data["event_url"])

        ch = interaction.guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
        if not ch:
            return await interaction.response.send_message("❌ Channel not found!", ephemeral=True)

        await ch.send(embed=embed, view=final_view)
        await interaction.response.send_message("✅ Posted without images/city edits!", ephemeral=True)
        del temp_data[interaction.user.id]

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button):
        del temp_data[interaction.user.id]
        await interaction.response.send_message("❌ Cancelled.", ephemeral=True)


# ==================== SECOND MODAL (2 FIELDS ONLY - IMAGES + CITIES) ====================
class AnnouncementModal2(discord.ui.Modal, title="Convoy Announcement - Step 2"):
    route_img = discord.ui.TextInput(label="Route Image URL", placeholder="https://i.imgur.com/...", required=False)
    slot_img  = discord.ui.TextInput(label="Slot Image URL (Optional)", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        data = temp_data.get(interaction.user.id)
        if not data:
            return await interaction.followup.send("❌ Session expired. Start over.", ephemeral=True)

        # Update images
        data["route_img"] = self.route_img.value.strip() if self.route_img.value.strip() else None
        data["slot_img"] = self.slot_img.value.strip() if self.slot_img.value.strip() else None

        # Show city edit option
        embed = discord.Embed(title="Step 2 Complete!", description="Images added. Edit cities now?", color=0x00FFFF)
        view = PreviewView2(data)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class PreviewView2(discord.ui.View):
    def __init__(self, data):
        super().__init__(timeout=900)
        self.data = data

    @discord.ui.button(label="✏️ Edit Start & Finish Cities", style=discord.ButtonStyle.secondary)
    async def edit_cities(self, interaction: discord.Interaction, button):
        await interaction.response.send_modal(CityModal())

    @discord.ui.button(label="✅ Post Announcement", style=discord.ButtonStyle.green)
    async def post(self, interaction: discord.Interaction, button):
        event = self.data["event"]
        event_url = self.data["event_url"]
        embed = create_embed(event, event_url, self.data)
        final_view = create_final_view(event_url)

        ch = interaction.guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
        if not ch:
            return await interaction.response.send_message("❌ Channel not found!", ephemeral=True)

        await ch.send(embed=embed, view=final_view)
        await interaction.response.send_message("✅ Announcement posted!", ephemeral=True)
        del temp_data[interaction.user.id]

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button):
        del temp_data[interaction.user.id]
        await interaction.response.send_message("❌ Cancelled.", ephemeral=True)


# ==================== CITY EDIT MODAL (2 FIELDS ONLY) ====================
class CityModal(discord.ui.Modal, title="Edit Cities (Optional)"):
    manual_start = discord.ui.TextInput(
        label="Start City Override",
        placeholder="Leave empty = keep API value",
        required=False,
        max_length=100
    )
    manual_finish = discord.ui.TextInput(
        label="Finish City Override",
        placeholder="Leave empty = keep API value",
        required=False,
        max_length=100
    )

    async def on_submit(self, interaction: discord.Interaction):
        data = temp_data.get(interaction.user.id)
        if not data:
            return await interaction.response.send_message("❌ Session expired.", ephemeral=True)

        # Apply overrides
        if self.manual_start.value.strip():
            data["event"]["departure_city"] = self.manual_start.value.strip()
        if self.manual_finish.value.strip():
            data["event"]["arrival_city"] = self.manual_finish.value.strip()

        # Refresh preview
        event = data["event"]
        event_url = data["event_url"]
        embed = create_embed(event, event_url, data, preview=True)
        view = PreviewView2(data)
        await interaction.response.send_message("Cities updated! Preview:", embed=embed, view=view, ephemeral=True)


# ==================== HELPER FUNCTIONS ====================
def create_embed(event, event_url, data=None, preview=False, no_images=False):
    start_tag = " (manual)" if data and data.get("manual_start") else ""
    finish_tag = " (manual)" if data and data.get("manual_finish") else ""

    embed = discord.Embed(title=event["name"], url=event_url, color=0x00FFFF, timestamp=discord.utils.utcnow())
    embed.add_field(name=":gamepad: Game", value=event["game"], inline=True)
    embed.add_field(name="📅 Date", value=format_date(event["start_at"]), inline=True)
    embed.add_field(name="🖥️ Server", value=event["server"], inline=True)

    embed.add_field(name="⏰ Meetup", value=format_time(event["meetup_at"]), inline=True)
    embed.add_field(name="🚀 Departure", value=format_time(event["start_at"]), inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=False)

    embed.add_field(name="🛣️ Distance", value=event["distance"], inline=True)
    embed.add_field(name="🎟️ Our Slot", value=f"**{event['vtc_slot']}**", inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=False)

    embed.add_field(name="🚚 Start", value=f"{event['departure_city']}{start_tag}", inline=True)
    embed.add_field(name="🏁 Finish", value=f"{event['arrival_city']}{finish_tag}", inline=True)
    embed.add_field(name="🎮 Required DLCs", value=event["dlcs"], inline=False)

    # Images
    if not no_images and data:
        if data["route_img"] and await is_image(data["route_img"]):
            embed.set_image(url=data["route_img"])
        if data["slot_img"] and await is_image(data["slot_img"]):
            embed.set_thumbnail(url=data["slot_img"])
        if event["banner"] and await is_image(event["banner"]):
            embed.set_footer(text="Official Event", icon_url=event["banner"])

    if preview:
        embed.set_footer(text="Click Post to send!")

    embed.set_author(name=f"Announced by {bot.get_user(interaction.user.id).display_name if 'interaction' in locals() else 'Preview'}", icon_url=bot.get_user(interaction.user.id).avatar.url if 'interaction' in locals() else None)
    return embed

def create_final_view(event_url):
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="View on TruckersMP", style=discord.ButtonStyle.link, url=event_url, emoji="🔗"))
    return view


# ==================== SLOT BOOKING (UNCHANGED) ====================
class PersistentBookView(discord.ui.View):
    def __init__(self): 
        super().__init__(timeout=None)

    @discord.ui.button(label="Book Slot", style=discord.ButtonStyle.green, custom_id="book_slot")
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

    def __init__(self, msg_id, data):
        super().__init__()
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

        # Update embed
        lines = []
        for k, v in sorted(self.data["slots"].items()):
            status = "✅" if v else "❌"
            user = f"<@{v}>" if v else "Available"
            lines.append(f"{status} **{k}** → {user}")

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
async def announcement_cmd(interaction: discord.Interaction):
    if not is_staff(interaction.user):
        return await interaction.response.send_message("❌ Staff only!", ephemeral=True)
    await interaction.response.send_modal(AnnouncementModal1())


@bot.tree.command(name="create", description="Staff: Create a slot booking board")
@app_commands.describe(
    channel="Post in this channel", title="Event title", slot_range="e.g., 1-20",
    color="green/red/blue or #hex", image="Optional image URL"
)
async def create_slots(interaction: discord.Interaction, channel: discord.TextChannel, title: str,
                       slot_range: str, color: str = "cyan", image: str = None):
    if not is_staff(interaction.user):
        return await interaction.response.send_message("❌ Staff only!", ephemeral=True)

    try:
        start, end = map(int, slot_range.split("-"))
        slots = [f"Slot {n}" for n in range(start, end + 1)]
    except ValueError:
        return await interaction.response.send_message("❌ Invalid range! Use 1-20", ephemeral=True)

    # Color
    color_map = {"green": 0x00ff00, "red": 0xff0000, "blue": 0x0000ff, "cyan": 0x00ffff}
    try:
        if color.startswith("#"):
            col = discord.Color(int(color.lstrip("#"), 16))
        else:
            col = discord.Color(color_map.get(color.lower(), 0x00ffff))
    except:
        col = discord.Color.cyan()

    lines = [f"❌ **{s}** → Available" for s in slots]
    embed = discord.Embed(title=title, description="\n".join(lines), color=col, timestamp=discord.utils.utcnow())
    embed.set_footer(text="Click 'Book Slot' to join!")

    if image and await is_image(image):
        embed.set_image(url=image)

    msg = await channel.send(embed=embed, view=PersistentBookView())
    booking_messages[msg.id] = {"slots": {s: None for s in slots}, "message": msg}

    await interaction.response.send_message(f"✅ Created {len(slots)} slots in {channel.mention}!", ephemeral=True)


# ==================== STARTUP ====================
@bot.event
async def on_ready():
    print(f"🚀 {bot.user} online | Ready for trucking!")
    bot.add_view(PersistentBookView())
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} commands")
    except Exception as e:
        print(f"❌ Sync error: {e}")


bot.run(BOT_TOKEN)
