import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
import re
import traceback
from datetime import datetime
import os
from dotenv import load_dotenv

# ---------------- CONFIG ----------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Your bot token here

STAFF_ROLE_IDS = [
    1395579577555878012,
    1395579347804487769,
    1395580379565527110,
    1395699038715642031,
    1395578532406624266,
]

STAFF_LOG_CHANNEL_ID = 1446383730242355200

COLOR_OPTIONS = {
    "blue": discord.Color.blue(),
    "red": discord.Color.red(),
    "green": discord.Color.green(),
    "yellow": discord.Color.gold(),
    "purple": discord.Color.purple(),
    "orange": discord.Color.orange(),
    "white": discord.Color.from_rgb(255, 255, 255),
    "black": discord.Color.from_rgb(0, 0, 0),
}

booking_messages = {}  # In-memory booking storage

# ----------------- INTENTS -----------------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ============================================================
#                      HELPER FUNCTIONS
# ============================================================

def parse_color(input_color: str):
    if not input_color:
        return None
    input_color = input_color.lower().strip()
    if input_color in COLOR_OPTIONS:
        return COLOR_OPTIONS[input_color]
    if re.fullmatch(r"[0-9a-f]{6}", input_color):
        return discord.Color(int(input_color, 16))
    if re.fullmatch(r"#[0-9a-f]{6}", input_color):
        return discord.Color(int(input_color[1:], 16))
    return None


async def parse_slot_range(text: str):
    try:
        if "-" not in text:
            return None
        a, b = text.split("-")
        a = int(a)
        b = int(b)
        if a > b:
            return None
        return [str(i) for i in range(a, b + 1)]
    except:
        return None


def is_staff_member(user):
    return any(r.id in STAFF_ROLE_IDS for r in user.roles)


# ============================================================
#                     BOOK SLOT MODAL
# ============================================================
class BookSlotModal(discord.ui.Modal, title="Book a Slot"):
    vtc_name = discord.ui.TextInput(label="Enter your VTC Name", placeholder="Your VTC name", max_length=50)

    def __init__(self, message_id, selected_slot):
        super().__init__()
        self.message_id = message_id
        self.selected_slot = selected_slot

    async def on_submit(self, interaction: discord.Interaction):
        data = booking_messages.get(self.message_id)
        if not data:
            return await interaction.response.send_message("❌ Booking message not found.", ephemeral=True)

        slots = data["slots"]
        slot = self.selected_slot
        vtc_name = self.vtc_name.value.strip()

        if slots[slot] is not None:
            return await interaction.response.send_message(f"❌ Slot `{slot}` already booked.", ephemeral=True)

        slots[slot] = {"name": vtc_name, "status": "pending"}

        # Update embed
        embed = data["message"].embeds[0]
        embed.description = "\n".join(
            f"{s}: {slots[s]['name'] if slots[s] else 'Available'}" for s in slots
        )
        await data["message"].edit(embed=embed, view=SlotDropdownView(self.message_id))

        # Staff log
        staff_channel = bot.get_channel(STAFF_LOG_CHANNEL_ID)
        if staff_channel:
            staff_embed = discord.Embed(
                title="📌 New Slot Booking",
                description=f"User: {interaction.user.mention}\nVTC Name: {vtc_name}\nSlot: {slot}",
                color=discord.Color.orange(),
                timestamp=datetime.utcnow()
            )
            view = StaffActionView(interaction.user.id, slot, self.message_id)
            await staff_channel.send(embed=staff_embed, view=view)

        await interaction.response.send_message(f"✅ You booked slot `{slot}` as `{vtc_name}`.", ephemeral=True)


# ============================================================
#                    SLOT DROPDOWN VIEW
# ============================================================
class SlotSelect(discord.ui.Select):
    def __init__(self, options, message_id):
        super().__init__(placeholder="Select a slot...", options=options)
        self.message_id = message_id

    async def callback(self, interaction: discord.Interaction):
        selected_slot = self.values[0]
        modal = BookSlotModal(self.message_id, selected_slot)
        await interaction.response.send_modal(modal)


class SlotDropdownView(discord.ui.View):
    def __init__(self, message_id):
        super().__init__(timeout=None)
        self.message_id = message_id
        data = booking_messages.get(message_id)
        self.slots = data["slots"] if data else {}

        options = [
            discord.SelectOption(label=slot, description="Available", default=False)
            for slot, user in self.slots.items() if user is None
        ]
        if options:
            self.add_item(SlotSelect(options, self.message_id))


# ============================================================
#                     BOOK SLOT BUTTON VIEW
# ============================================================
class BookSlotView(discord.ui.View):
    def __init__(self, message_id):
        super().__init__(timeout=None)
        self.message_id = message_id

    @discord.ui.button(label="📌 Book Slot", style=discord.ButtonStyle.green, custom_id="book_slot_button")
    async def book_slot_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(view=SlotDropdownView(self.message_id), ephemeral=True)


# ============================================================
#                 STAFF ACTION BUTTONS
# ============================================================
class StaffButton(discord.ui.Button):
    def __init__(self, action, label, style, emoji):
        super().__init__(label=label, style=style, emoji=emoji)
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        data = booking_messages.get(self.view.message_id)
        if not data:
            return await interaction.response.send_message("❌ Booking not found.", ephemeral=True)

        slots = data["slots"]
        slot_data = slots.get(self.view.slot)
        user = interaction.guild.get_member(self.view.user_id)

        if not slot_data:
            return await interaction.response.send_message("❌ Slot data missing.", ephemeral=True)

        embed = data["message"].embeds[0]

        if self.action == "approve":
            slot_data["status"] = "approved"
            embed.color = discord.Color.green()
            embed.title = f"✅ Approved: Slot {self.view.slot}"
            await data["message"].edit(embed=embed)
            try: await user.send(f"✅ Your slot `{self.view.slot}` has been approved!")
            except: pass
            await interaction.response.send_message(f"✅ Approved {user.mention}'s booking.", ephemeral=True)

        elif self.action == "deny":
            try: await user.send(f"❌ Your slot `{self.view.slot}` has been denied!")
            except: pass
            await interaction.response.send_message(f"❌ Deny DM sent to {user.mention}.", ephemeral=True)

        elif self.action == "remove":
            if slot_data["status"] != "approved":
                return await interaction.response.send_message("❌ No approval to remove.", ephemeral=True)
            slot_data["status"] = "pending"
            embed.color = discord.Color.orange()
            embed.title = f"🗑 Approval removed: Slot {self.view.slot}"
            await data["message"].edit(embed=embed)
            try: await user.send(f"🗑 Your approval for slot `{self.view.slot}` has been removed!")
            except: pass
            await interaction.response.send_message(f"🗑 Removed approval for {user.mention}.", ephemeral=True)


class StaffActionView(discord.ui.View):
    def __init__(self, user_id, slot, message_id):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.slot = slot
        self.message_id = message_id
        self.add_item(StaffButton("approve", "✅ Approve", discord.ButtonStyle.green, "✅"))
        self.add_item(StaffButton("deny", "❌ Deny", discord.ButtonStyle.red, "❌"))
        self.add_item(StaffButton("remove", "🗑 Remove Approval", discord.ButtonStyle.grey, "🗑"))


# ============================================================
#                  CREATE BOOKING COMMAND
# ============================================================
@bot.tree.command(name="create", description="Staff only: Create booking message.")
@app_commands.describe(
    channel="Channel to send booking embed",
    title="Embed title",
    slot_range="Example: 1-10",
    color="Color name or hex",
    image="Image URL (optional)",
)
async def create(interaction: discord.Interaction, channel: discord.TextChannel, title: str, slot_range: str, color: str, image: str = None):
    if not is_staff_member(interaction.user):
        return await interaction.response.send_message("❌ You are not staff.", ephemeral=True)

    slots_list = await parse_slot_range(slot_range)
    if not slots_list:
        return await interaction.response.send_message("❌ Invalid slot range.", ephemeral=True)

    hex_color = parse_color(color)
    if not hex_color:
        return await interaction.response.send_message("❌ Invalid color.", ephemeral=True)

    embed = discord.Embed(title=title, description="\n".join(slots_list), color=hex_color)
    if image:
        embed.set_image(url=image)

    sent_msg = await channel.send(embed=embed)
    booking_messages[sent_msg.id] = {"message": sent_msg, "slots": {slot: None for slot in slots_list}}
    await sent_msg.edit(view=BookSlotView(sent_msg.id))  # Corrected: pass real message_id

    await interaction.response.send_message(f"✅ Booking embed created with {len(slots_list)} slots.", ephemeral=True)


# ============================================================
#                      MARK COMMAND
# ============================================================
@bot.tree.command(name="mark", description="Create Mark Attendance embed from TruckersMP link.")
@app_commands.describe(event_link="TruckersMP event link")
async def mark(interaction: discord.Interaction, event_link: str):
    await interaction.response.defer(thinking=True, ephemeral=True)
    match = re.search(r"/events/(\d+)", event_link)
    if not match:
        return await interaction.followup.send("❌ Invalid TruckersMP link.", ephemeral=True)

    event_id = match.group(1)
    api_url = f"https://api.truckersmp.com/v2/events/{event_id}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as resp:
                if resp.status != 200:
                    return await interaction.followup.send(f"❌ API returned HTTP {resp.status}.", ephemeral=True)
                data = await resp.json()
    except Exception as e:
        traceback.print_exc()
        return await interaction.followup.send(f"❌ API error: {e}", ephemeral=True)

    if data.get("error"):
        return await interaction.followup.send("❌ API reports invalid event ID.", ephemeral=True)

    event = data.get("response") or {}
    name = event.get("name", "Unknown Event")

    def parse_iso(iso: str):
        if not iso:
            return None
        iso = iso.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(iso)
        except:
            return None

    start_dt = parse_iso(event.get("start_at"))
    meetup_dt = parse_iso(event.get("meetup_at", event.get("start_at")))
    date_str = start_dt.strftime("%a, %d %B %Y") if start_dt else "Unknown"
    meetup_time = meetup_dt.strftime("%H:%M UTC") if meetup_dt else "Unknown"
    depart_time = start_dt.strftime("%H:%M UTC") if start_dt else "Unknown"
    banner = event.get("banner") or event.get("cover")

    embed = discord.Embed(
        title="<:NepPathLogocircledim:1395694322061410334> Mark Your Attendance",
        description="<@&1398294285597671606>\n\n**🙏 PLEASE MARK YOUR ATTENDANCE ❤️**",
        color=discord.Color(0xFF5A20),
    )
    embed.add_field(name="Event", value=f"[{name}]({event_link})", inline=False)
    embed.add_field(name="Date", value=date_str, inline=True)
    embed.add_field(name="Meetup Time", value=meetup_time, inline=True)
    embed.add_field(name="Departure Time", value=depart_time, inline=True)
    if banner:
        embed.set_image(url=banner)

    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="➡️ Go to Event", url=event_link, style=discord.ButtonStyle.link))

    await interaction.channel.send(embed=embed, view=view)
    await interaction.followup.send("✅ Attendance embed created.", ephemeral=True)


# ============================================================
#                  ANNOUNCEMENT MODAL
# ============================================================
class AnnouncementModal(discord.ui.Modal, title="Create Announcement"):
    title = discord.ui.TextInput(label="Announcement Title", placeholder="Enter the title", max_length=100)
    message = discord.ui.TextInput(label="Announcement Message", placeholder="Enter content", style=discord.TextStyle.paragraph, max_length=2000)
    color = discord.ui.TextInput(label="Announcement Color (optional)", placeholder="blue | red | #ff0000", max_length=7, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            announcement_title = self.title.value.strip()
            announcement_message = self.message.value.strip()
            color_input = self.color.value.strip()
            embed_color = parse_color(color_input) or discord.Color.blue()

            announcement_channel = discord.utils.get(interaction.guild.text_channels, name="announcements")
            if not announcement_channel:
                return await interaction.response.send_message("❌ `#announcements` channel not found.", ephemeral=True)

            embed = discord.Embed(title=announcement_title, description=announcement_message, color=embed_color)
            await announcement_channel.send(embed=embed)
            await interaction.response.send_message("✅ Announcement sent.", ephemeral=True)
        except Exception:
            traceback.print_exc()
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error occurred.", ephemeral=True)


# ============================================================
#                         READY
# ============================================================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"✅ Slash commands synced ({len(synced)} commands).")
    except Exception as e:
        print("❌ Slash sync error:", e)
        traceback.print_exc()


# ============================================================
#                          RUN
# ============================================================
bot.run(BOT_TOKEN)
