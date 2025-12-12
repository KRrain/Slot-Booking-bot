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
BOT_TOKEN = os.getenv("BOT_TOKEN")

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

# In-memory booking storage
booking_messages = {}  # message_id: {"message": msg, "slots": {slot_number: {"name": str, "status": "pending"}}}

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
        a, b = int(a), int(b)
        if a > b:
            return None
        return [str(i) for i in range(a, b + 1)]
    except:
        return None

def is_staff_member(user):
    return any(r.id in STAFF_ROLE_IDS for r in user.roles)

# ============================================================
#                    BOOK SLOT MODAL (with slot number input)
# ============================================================
class BookSlotModal(discord.ui.Modal, title="Book a Slot"):
    vtc_name = discord.ui.TextInput(label="Your VTC Name", placeholder="Enter your VTC Name", max_length=50)
    slot_number = discord.ui.TextInput(label="Slot Number", placeholder="Enter available slot number", max_length=5)

    def __init__(self, message_id):
        super().__init__()
        self.message_id = message_id

    async def on_submit(self, interaction: discord.Interaction):
        data = booking_messages.get(self.message_id)
        if not data:
            return await interaction.response.send_message("❌ Booking message not found.", ephemeral=True)

        slot = self.slot_number.value.strip()
        vtc_name = self.vtc_name.value.strip()

        if slot not in data["slots"]:
            return await interaction.response.send_message("❌ Invalid slot number.", ephemeral=True)

        slot_data = data["slots"][slot]
        if slot_data and slot_data.get("status") == "approved":
            return await interaction.response.send_message("❌ Slot already approved.", ephemeral=True)

        # Save pending booking
        data["slots"][slot] = {"name": vtc_name, "status": "pending"}

        # Staff log
        staff_channel = bot.get_channel(STAFF_LOG_CHANNEL_ID)
        if staff_channel:
            staff_embed = discord.Embed(
                title="📌 New Slot Booking (Pending Approval)",
                description=f"User: {interaction.user.mention}\nVTC Name: {vtc_name}\nSlot: {slot}",
                color=discord.Color.orange(),
                timestamp=datetime.utcnow()
            )
            view = StaffActionView(interaction.user.id, slot, self.message_id)
            staff_channel.send(embed=staff_embed, view=view)
            bot.add_view(view)  # persistent view

        await interaction.response.send_message(
            f"✅ You requested slot `{slot}` as `{vtc_name}`. Waiting for staff approval.",
            ephemeral=True
        )

# ============================================================
#                     BOOK SLOT BUTTON VIEW
# ============================================================
class BookSlotView(discord.ui.View):
    def __init__(self, message_id):
        super().__init__(timeout=None)
        self.message_id = message_id

    @discord.ui.button(label="📌 Book Slot", style=discord.ButtonStyle.green)
    async def book_slot_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = booking_messages.get(self.message_id)
        if not data:
            return await interaction.response.send_message("❌ Booking message not found.", ephemeral=True)

        available_slots = [s for s, info in data["slots"].items() if not info or info.get("status") != "approved"]
        if not available_slots:
            return await interaction.response.send_message("❌ No available slots.", ephemeral=True)

        modal = BookSlotModal(self.message_id)
        await interaction.response.send_modal(modal)

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
            embed.description = "\n".join(
                f"Slot {s}: {slots[s]['name'] if slots[s]['status']=='approved' else 'Available'}" for s in slots
            )
            await data["message"].edit(embed=embed)
            try: await user.send(f"✅ Your slot `{self.view.slot}` has been approved!")
            except: pass
            await interaction.response.send_message(f"✅ Approved {user.mention}'s booking.", ephemeral=True)

        elif self.action == "deny":
            try: await user.send(f"❌ Your slot `{self.view.slot}` has been denied!")
            except: pass
            await interaction.response.send_message(f"❌ Deny DM sent to {user.mention}.", ephemeral=True)

        elif self.action == "remove":
            if slot_data.get("status") != "approved":
                return await interaction.response.send_message("❌ No approval to remove.", ephemeral=True)
            slot_data["status"] = "pending"
            embed.description = "\n".join(
                f"Slot {s}: {slots[s]['name'] if slots[s]['status']=='approved' else 'Available'}" for s in slots
            )
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

    embed = discord.Embed(title=title, description="\n".join(f"Slot {s}: Available" for s in slots_list), color=hex_color)
    if image:
        embed.set_image(url=image)

    sent_msg = await channel.send(embed=embed)
    booking_messages[sent_msg.id] = {"message": sent_msg, "slots": {slot: None for slot in slots_list}}
    view = BookSlotView(sent_msg.id)
    await sent_msg.edit(view=view)
    bot.add_view(view)  # persistent

    await interaction.response.send_message(f"✅ Booking embed created with {len(slots_list)} slots.", ephemeral=True)

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

bot.run(BOT_TOKEN)
