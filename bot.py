# bot.py - All-in-one slot booking bot with safe

import discord
from discord.ext import commands
from discord import app_commands

import os
from dotenv import load_dotenv

load_dotenv()  # Load .env file
BOT_TOKEN = os.getenv("BOT_TOKEN")

intents = discord.Intents.default()
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------- CONFIG ----------------
STAFF_ROLE_IDS = [
    1395579577555878012,
    1395579347804487769,
    1395580379565527110,
    1395699038715642031,
    1395578532406624266,
]
STAFF_LOG_CHANNEL_ID = 1395811260351647934

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
# ----------------------------------------

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ---------- In-memory storage ----------
booking_messages: dict[int, dict] = {}  # {guild_id: {"message": Message, "slots": {slot_name: approved_vtc or None}}}
user_submissions: dict[int, dict[int, set[str]]] = {}  # {guild_id: {user_id: set(slots_submitted)}}

# ---------- Helpers ----------
def is_staff_member(member: discord.Member) -> bool:
    return any(role.id in STAFF_ROLE_IDS for role in member.roles)

async def parse_slot_range(slot_range: str):
    try:
        start_str, end_str = slot_range.split("-")
        start = int(start_str)
        end = int(end_str)
        if start < 1 or end < start:
            raise ValueError
        return [f"Slot {i}" for i in range(start, end + 1)]
    except Exception:
        return None

def parse_color(color_str: str):
    if color_str.lower() in COLOR_OPTIONS:
        return COLOR_OPTIONS[color_str.lower()]
    try:
        if color_str.startswith("#"):
            color_str = color_str[1:]
        return discord.Color(int(color_str, 16))
    except Exception:
        return None

# ---------- Modal ----------
class SlotBookingModal(discord.ui.Modal, title="Book Slot"):
    vtc_name = discord.ui.TextInput(label="VTC Name", placeholder="Enter your VTC name", max_length=100)
    slot_numbers = discord.ui.TextInput(
        label="Slot Number(s)",
        placeholder="Enter slot number(s), comma-separated (e.g., Slot 1, Slot 2)",
        max_length=200
    )

    def __init__(self, guild_id: int):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        if self.guild_id not in booking_messages:
            await interaction.response.send_message("❌ Booking data not found.", ephemeral=True)
            return

        slots_dict = booking_messages[self.guild_id]["slots"]
        requested_slots = [s.strip().capitalize() for s in self.slot_numbers.value.split(",") if s.strip()]

        # Prevent double submissions
        if self.guild_id not in user_submissions:
            user_submissions[self.guild_id] = {}
        user_slots = user_submissions[self.guild_id].get(interaction.user.id, set())
        for slot in requested_slots:
            if slot in user_slots:
                await interaction.response.send_message(f"❌ You already submitted slot `{slot}`.", ephemeral=True)
                return
            if slot not in slots_dict:
                await interaction.response.send_message(f"❌ Slot `{slot}` does not exist.", ephemeral=True)
                return
            if slots_dict[slot]:
                await interaction.response.send_message(f"❌ Slot `{slot}` is already approved.", ephemeral=True)
                return

        # Record submission
        if interaction.user.id not in user_submissions[self.guild_id]:
            user_submissions[self.guild_id][interaction.user.id] = set()
        user_submissions[self.guild_id][interaction.user.id].update(requested_slots)

        await interaction.response.send_message(
            f"✅ Your request(s) submitted: {', '.join(requested_slots)}", ephemeral=True
        )

        # Send each request to staff log
        log_channel = bot.get_channel(STAFF_LOG_CHANNEL_ID)
        if log_channel is None:
            return

        for slot in requested_slots:
            embed = discord.Embed(title="📥 Slot Booking Request", color=discord.Color.orange())
            embed.add_field(name="User", value=interaction.user.mention, inline=False)
            embed.add_field(name="VTC Name", value=self.vtc_name.value, inline=False)
            embed.add_field(name="Slot Number", value=slot, inline=False)
            embed.set_footer(text="Waiting for staff action")
            view = ApproveDenyView(
                user_id=interaction.user.id,
                vtc_name=self.vtc_name.value,
                slot_number=slot,
                guild_id=self.guild_id,
                approved=False,
                denied=False
            )
            await log_channel.send(embed=embed, view=view)

# ---------- Book Slot Button ----------
class BookSlotView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📌 Book Slot", style=discord.ButtonStyle.green, custom_id="book_slot_button")
    async def book_slot_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild_id not in booking_messages:
            await interaction.response.send_message(
                "❌ No booking message found. Ask staff to create slots first.",
                ephemeral=True
            )
            return

        slots_dict = booking_messages[interaction.guild_id]["slots"]
        available_slots = [s for s, v in slots_dict.items() if not v]
        if not available_slots:
            await interaction.response.send_message(
                "❌ No available slots at the moment.", ephemeral=True
            )
            return

        modal = SlotBookingModal(guild_id=interaction.guild_id)
        await interaction.response.send_modal(modal)

# ---------- Staff Approve/Deny/Remove ----------
class ApproveDenyView(discord.ui.View):
    def __init__(self, user_id: int, vtc_name: str, slot_number: str | list[str], guild_id: int, approved: bool = False, denied: bool = False):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.vtc_name = vtc_name
        self.slot_number = slot_number if isinstance(slot_number, list) else [slot_number]
        self.guild_id = guild_id

        if approved or denied:
            self.approve.disabled = True
            self.deny.disabled = True

    async def _notify_user(self, approved: bool):
        try:
            user = await bot.fetch_user(self.user_id)
            if approved:
                await user.send(f"✅ Your slot(s) {', '.join(self.slot_number)} have been approved! VTC: {self.vtc_name}")
            else:
                await user.send(f"❌ Your slot(s) {', '.join(self.slot_number)} have been denied or removed.")
        except Exception:
            pass

    @discord.ui.button(label="✅ Approve", style=discord.ButtonStyle.green, custom_id="approve_button")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if button.disabled:
            return await interaction.response.send_message("❌ Already processed.", ephemeral=True)
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ You are not staff.", ephemeral=True)

        data = booking_messages.get(self.guild_id)
        slots_dict = data["slots"] if data else {}

        for slot in self.slot_number:
            if slots_dict.get(slot):
                await interaction.response.send_message(f"❌ Slot `{slot}` is already approved.", ephemeral=True)
                return

        for slot in self.slot_number:
            slots_dict[slot] = self.vtc_name

        # Remove from user_submissions so they can book again if removed
        user_submissions[self.guild_id][self.user_id].difference_update(self.slot_number)

        original_msg = data["message"]
        updated_lines = [f"{s}: {v} ✅" if v else f"{s}" for s, v in slots_dict.items()]
        new_embed = original_msg.embeds[0]
        new_embed.description = "\n".join(updated_lines)
        await original_msg.edit(embed=new_embed)

        await self._notify_user(True)
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.set_footer(text=f"✅ Approved by {interaction.user}")
        self.approve.disabled = True
        self.deny.disabled = True
        await interaction.message.edit(embed=embed, view=self)
        await interaction.response.send_message("Slot approved and user notified.", ephemeral=True)

    @discord.ui.button(label="❌ Deny", style=discord.ButtonStyle.red, custom_id="deny_button")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if button.disabled:
            return await interaction.response.send_message("❌ Already processed.", ephemeral=True)
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ You are not staff.", ephemeral=True)

        # Remove from user_submissions so they can book again
        if self.user_id in user_submissions.get(self.guild_id, {}):
            user_submissions[self.guild_id][self.user_id].difference_update(self.slot_number)

        await self._notify_user(False)
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.set_footer(text=f"❌ Denied by {interaction.user}")
        self.approve.disabled = True
        self.deny.disabled = True
        await interaction.message.edit(embed=embed, view=self)
        await interaction.response.send_message("Slot denied and user notified.", ephemeral=True)

    @discord.ui.button(label="♻ Remove Approval", style=discord.ButtonStyle.gray, custom_id="remove_approval")
    async def remove_approval(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ You are not staff.", ephemeral=True)

        data = booking_messages.get(self.guild_id)
        if not data:
            return await interaction.response.send_message("❌ Booking data not found.", ephemeral=True)

        slots_dict = data["slots"]
        removed_slots = []

        for slot in self.slot_number:
            if slot in slots_dict and slots_dict[slot]:
                slots_dict[slot] = None
                removed_slots.append(slot)

        if not removed_slots:
            return await interaction.response.send_message("❌ No approved slots to remove.", ephemeral=True)

        # Remove from user_submissions
        if self.user_id in user_submissions.get(self.guild_id, {}):
            user_submissions[self.guild_id][self.user_id].difference_update(self.slot_number)

        original_msg = data["message"]
        updated_lines = [f"{s}: {v} ✅" if v else f"{s}" for s, v in slots_dict.items()]
        new_embed = original_msg.embeds[0]
        new_embed.description = "\n".join(updated_lines)
        await original_msg.edit(embed=new_embed)

        await self._notify_user(False)
        await interaction.response.send_message(
            f"♻ Removed approval for slot(s): {', '.join(removed_slots)}", ephemeral=True
        )

# ---------- Slash Commands ----------
@bot.tree.command(name="create", description="Staff only: Create booking message with custom slot range.")
@app_commands.describe(
    channel="Channel to post the booking message in",
    title="Embed title",
    slot_range="Slot range to generate (e.g. 1-10, 5-50)",
    color="Embed color name or hex (e.g., blue or #FF0000)",
    image="Optional image URL"
)
async def create(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    title: str,
    slot_range: str,
    color: str,
    image: str | None = None
):
    if not is_staff_member(interaction.user):
        return await interaction.response.send_message("❌ You are not staff.", ephemeral=True)

    slots_list = await parse_slot_range(slot_range)
    if not slots_list:
        return await interaction.response.send_message("❌ Invalid slot range.", ephemeral=True)

    hex_color = parse_color(color)
    if not hex_color:
        return await interaction.response.send_message("❌ Invalid color.", ephemeral=True)

    desc = "\n".join(slots_list)
    embed = discord.Embed(title=title, description=desc, color=hex_color)
    if image and image.startswith("http"):
        embed.set_image(url=image)

    sent_msg = await channel.send(embed=embed, view=BookSlotView())
    slots_dict = {slot: None for slot in slots_list}
    booking_messages[interaction.guild_id] = {"message": sent_msg, "slots": slots_dict}

    await interaction.response.send_message(f"✅ Booking message posted with {len(slots_list)} slots.", ephemeral=True)

@bot.tree.command(name="editcreate", description="Staff only: Edit booking message (keeps approved slots).")
@app_commands.describe(
    title="Embed title",
    slot_range="Slot range to generate (e.g. 1-10, 5-50)",
    color="Embed color name or hex",
    image="Optional image URL"
)
async def editcreate(
    interaction: discord.Interaction,
    title: str,
    slot_range: str,
    color: str,
    image: str | None = None
):
    if not is_staff_member(interaction.user):
        return await interaction.response.send_message("❌ You are not staff.", ephemeral=True)

    if interaction.guild_id not in booking_messages:
        return await interaction.response.send_message("❌ No booking message found.", ephemeral=True)

    slots_list = await parse_slot_range(slot_range)
    if not slots_list:
        return await interaction.response.send_message("❌ Invalid slot range.", ephemeral=True)

    hex_color = parse_color(color)
    if not hex_color:
        return await interaction.response.send_message("❌ Invalid color.", ephemeral=True)

    data = booking_messages[interaction.guild_id]
    original_msg: discord.Message = data["message"]
    slots_dict = data["slots"]

    updated_slots_dict = {}
    for slot in slots_list:
        if slot in slots_dict and slots_dict[slot]:
            updated_slots_dict[slot] = slots_dict[slot]
        else:
            updated_slots_dict[slot] = None

    lines = [f"{s}: {v} ✅" if v else s for s, v in updated_slots_dict.items()]
    embed = discord.Embed(title=title, description="\n".join(lines), color=hex_color)
    if image and image.startswith("http"):
        embed.set_image(url=image)

    await original_msg.edit(embed=embed, view=BookSlotView())
    booking_messages[interaction.guild_id]["slots"] = updated_slots_dict

    await interaction.response.send_message("✅ Booking message updated.", ephemeral=True)

# ---------- Ready ----------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    bot.add_view(BookSlotView())
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print("Slash command sync failed:", e)

# ---------- Run ----------
if __name__ == "__main__":
    bot.run(BOT_TOKEN)
