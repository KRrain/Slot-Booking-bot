# bot.py - NEPPATH VTC BOT - FINAL PERFECT VERSION (DEC 2025)
# Manual Start & Finish + Instant /announcement + Persistent Booking

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


# ==================== ANNOUNCEMENT MODAL (WITH MANUAL START & FINISH) ====================
class AnnouncementModal(discord.ui.Modal, title="Create Convoy Announcement"):
    event_link = discord.ui.TextInput(label="TruckersMP Event Link", placeholder="https://truckersmp.com/events/12345")
    distance   = discord.ui.TextInput(label="Distance (e.g. 1,234 km)", placeholder="1,234 km")
    vtc_slot   = discord.ui.TextInput(label="Our VTC Slot", placeholder="7")

    manual_start = discord.ui.TextInput(
        label="Start City — Manual (Optional)",
        placeholder="Leave empty = use API",
        required=False,
        max_length=100
    )
    manual_finish = discord.ui.TextInput(
        label="Finish City — Manual (Optional)",
        placeholder="Leave empty = use API",
        required=False,
        max_length=100
    )

    route_img = discord.ui.TextInput(label="Route Image URL", placeholder="https://i.imgur.com/...")
    slot_img  = discord.ui.TextInput(label="Slot Image URL (Optional)", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        match = re.search(r"/events/(\d+)", self.event_link.value.strip())
        if not match:
            return await interaction.followup.send("Invalid event link!", ephemeral=True)

        event_id = match.group(1)
        event_url = self.event_link.value.strip()

        # Default data
        event = {
            "name": "Unknown Convoy", "game": "ETS2", "server": "Event Server",
            "start_at": None, "meetup_at": None,
            "departure_city": "Unknown", "arrival_city": "Unknown",
            "dlcs": "None", "banner": None
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

        # Apply manual overrides
        final_start  = self.manual_start.value.strip()  or event["departure_city"]
        final_finish = self.manual_finish.value.strip() or event["arrival_city"]
        start_tag  = " (manual)" if self.manual_start.value.strip() else ""
        finish_tag = " (manual)" if self.manual_finish.value.strip() else ""

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

        embed.add_field(name="Start", value=f"{final_start}{start_tag}", inline=True)
        embed.add_field(name="Finish", value=f"{final_finish}{finish_tag}", inline=True)
        embed.add_field(name="Required DLCs", value=event["dlcs"], inline=False)

        if await is_image(self.route_img.value):
            embed.set_image(url=self.route_img.value)
        if self.slot_img.value and await is_image(self.slot_img.value):
            embed.set_thumbnail(url=self.slot_img.value)
        if event["banner"] and await is_image(event["banner"]):
            embed.set_footer(text="Official Event", icon_url=event["banner"])

        embed.set_author(name=f"Announced by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)

        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label="View on TruckersMP", style=discord.ButtonStyle.link, url=event_url, emoji="Link"))

        await interaction.followup.send("Preview ready — click Send to post!", embed=embed, view=ConfirmView(embed, view), ephemeral=True)


class ConfirmView(discord.ui.View):
    def __init__(self, embed, final_view):
        super().__init__(timeout=300)
        self.embed = embed
        self.final_view = final_view

    @discord.ui.button(label="Send Announcement", style=discord.ButtonStyle.green)
    async def send(self, i: discord.Interaction, button):
        ch = i.guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
        if not ch:
            return await i.response.edit_message(content="Channel not found! Check ID.", view=None)
        await ch.send(embed=self.embed, view=self.final_view)
        await i.response.edit_message(content="Announcement posted!", view=None, embed=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, i: discord.Interaction, button):
        await i.response.edit_message(content="Cancelled.", view=None, embed=None)


# ==================== SLOT BOOKING SYSTEM ====================
class PersistentBookView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Book Slot", style=discord.ButtonStyle.green, custom_id="book_slot")
    async def book(self, i: discord.Interaction, button):
        data = booking_messages.get(i.message.id)
        if not data or not any(v is None for v in data["slots"].values()):
            return await i.response.send_message("No slots available or expired!", ephemeral=True)
        await i.response.send_modal(BookModal(i.message.id, data))


class BookModal(discord.ui.Modal, title="Book Your Slot"):
    vtc = discord.ui.TextInput(label="Your VTC Name", placeholder="NepPath Logistics", max_length=50)
    slot_num = discord.ui.TextInput(label="Slot Number", placeholder="7", max_length=3)

    def __init__(self, msg_id, data):
        super().__init__()
        self.msg_id = msg_id
        self.data = data

    async def on_submit(self, i: discord.Interaction):
        if not self.slot_num.value.isdigit():
            return await i.response.send_message("Slot must be a number!", ephemeral=True)

        slot = f"Slot {int(self.slot_num.value)}"
        if slot not in self.data["slots"]:
            return await i.response.send_message("Invalid slot!", ephemeral=True)
        if self.data["slots"][slot] is not None:
            return await i.response.send_message("Slot already taken!", ephemeral=True)

        # Anti-dupe
        user_set = user_requests.setdefault(i.guild_id, {}).setdefault(i.user.id, set())
        if slot in user_set:
            return await i.response.send_message("You already booked a slot!", ephemeral=True)

        self.data["slots"][slot] = i.user.id
        user_set.add(slot)

        # Update embed live
        lines = []
        for k, v in sorted(self.data["slots"].items()):
            status = "Booked" if v else "Available"
            user = f"<@{v}>" if v else "Available"
            lines.append(f"{status} **{k}** → {user}")

        embed = i.message.embeds[0]
        embed.description = "\n".join(lines)
        booked = sum(1 for v in self.data["slots"].values() if v)
        embed.set_footer(text=f"{booked}/{len(self.data['slots'])} booked • Updated by {i.user.display_name}")

        await i.message.edit(embed=embed)
        await i.response.send_message(f"Booked **{slot}** as **{self.vtc.value}**! See you there!", ephemeral=True)

        log = bot.get_channel(STAFF_LOG_CHANNEL_ID)
        if log:
            await log.send(f"Slot Booked: {i.user.mention} → {slot} ({self.vtc.value})")


# ==================== COMMANDS (FIXED - NO MORE "DID NOT RESPOND") ====================
@bot.tree.command(name="announcement", description="Staff: Create convoy announcement")
async def announcement(interaction: discord.Interaction):
    if not is_staff(interaction.user):
        return await interaction.response.send_message("Staff only!", ephemeral=True)
    await interaction.response.send_modal(AnnouncementModal())


@bot.tree.command(name="create", description="Staff: Create slot booking board")
@app_commands.describe(channel="Where to post", title="Event name", slot_range="1-20", color="green/red/blue/#hex", image="Optional image")
async def create(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    title: str,
    slot_range: str,
    color: str = "cyan",
    image: str = None
):
    if not is_staff(interaction.user):
        return await interaction.response.send_message("Staff only!", ephemeral=True)

    try:
        start, end = map(int, slot_range.split("-"))
        slots = [f"Slot {n}" for n in range(start, end + 1)]
    except:
        return await interaction.response.send_message("Use format: 1-20", ephemeral=True)

    color_map = {"green": 0x00ff00, "red": 0xff0000, "blue": 0x0099ff, "cyan": 0x00ffff}
    col = discord.Color(int(color.lstrip("#"), 16)) if color.startswith("#") else discord.Color(color_map.get(color.lower(), 0x00ffff))

    lines = [f"Available **{s}** → Available" for s in slots]
    embed = discord.Embed(title=title, description="\n".join(lines), color=col, timestamp=discord.utils.utcnow())
    embed.set_footer(text="Click Book Slot to join!")

    if image and await is_image(image):
        embed.set_image(url=image)

    msg = await channel.send(embed=embed, view=PersistentBookView())
    booking_messages[msg.id] = {"slots": {s: None for s in slots}}

    await interaction.response.send_message(f"Created {len(slots)} slots in {channel.mention}!", ephemeral=True)


# ==================== STARTUP ====================
@bot.event
async def on_ready():
    print(f"NepPath VTC Bot Online → {bot.user}")
    bot.add_view(PersistentBookView())  # Keep booking buttons alive
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(f"Sync error: {e}")
    print("Bot fully ready — happy trucking!")


bot.run(BOT_TOKEN)
