# bot.py — FULL

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
import re
import traceback
from datetime import datetime, timedelta, timezone
import os
from dotenv import load_dotenv

# ---------------- CONFIG ----------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")  # set in .env

# Staff roles and log channel
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

# ---------------- INTENTS ----------------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ---------- Global error handlers ----------
@bot.event
async def on_error(event_method, *args, **kwargs):
    print(f"Error in {event_method}:")
    traceback.print_exc()

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    print("App command error:", repr(error))
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "❌ An internal error occurred while running this command.", ephemeral=True
            )
    except Exception:
        pass

# ---------- In-memory storage ----------
booking_messages = {}  # {message_id: {"message": Message, "slots": {slot: vtc_name}}}
user_submissions = {}  # {guild_id: {user_id: set(slots)}}

# ---------- Helpers ----------
def is_staff_member(member: discord.Member) -> bool:
    try:
        return any(role.id in STAFF_ROLE_IDS for role in member.roles)
    except Exception:
        return False

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
    if not color_str:
        return None
    try:
        lower = color_str.lower()
        if lower in COLOR_OPTIONS:
            return COLOR_OPTIONS[lower]
        if color_str.startswith("#"):
            color_str = color_str[1:]
        return discord.Color(int(color_str, 16))
    except Exception:
        return None

# ---------- Slot Booking Modal ----------
class SlotBookingModal(discord.ui.Modal, title="Book Slot"):
    vtc_name = discord.ui.TextInput(label="VTC Name", placeholder="Enter your VTC name", max_length=100)
    slot_number = discord.ui.TextInput(label="Slot Number", placeholder="Enter slot number like: 1", max_length=3)

    def __init__(self, message_id: int):
        super().__init__()
        self.message_id = message_id
        data = booking_messages.get(message_id)
        slots_dict = (data or {}).get("slots", {})
        available = [s.replace("Slot ", "") for s, v in slots_dict.items() if not v]
        if available:
            preview = ", ".join(available[:10])
            if len(available) > 10:
                preview += ", ..."
            placeholder = f"Available: {preview}"
            if len(placeholder) > 100:
                placeholder = placeholder[:97] + "..."
            self.slot_number.placeholder = placeholder
        else:
            self.slot_number.placeholder = "No slots available."

    async def on_submit(self, interaction: discord.Interaction):
        try:
            msg_id = self.message_id
            data = booking_messages.get(msg_id)
            if not data:
                return await interaction.response.send_message("❌ Booking data not found.", ephemeral=True)

            slots_dict = data["slots"]
            raw = self.slot_number.value.strip()
            if not raw.isdigit():
                return await interaction.response.send_message(
                    "❌ Slot number must be a **number only**, like `1`.", ephemeral=True
                )

            slot_id = int(raw)
            slot_name = f"Slot {slot_id}"
            if slot_name not in slots_dict:
                return await interaction.response.send_message(f"❌ Slot `{raw}` does not exist.", ephemeral=True)
            if slots_dict[slot_name]:
                return await interaction.response.send_message(f"❌ Slot `{raw}` is already booked.", ephemeral=True)

            guild_id = interaction.guild_id
            user_id = interaction.user.id
            if guild_id not in user_submissions:
                user_submissions[guild_id] = {}
            if user_id in user_submissions[guild_id] and slot_name in user_submissions[guild_id][user_id]:
                return await interaction.response.send_message(f"❌ You already submitted slot `{raw}`.", ephemeral=True)

            user_submissions[guild_id].setdefault(user_id, set()).add(slot_name)
            await interaction.response.send_message(f"✅ Request submitted for slot **{slot_id}**", ephemeral=True)

            # Log to staff channel
            log_channel = bot.get_channel(STAFF_LOG_CHANNEL_ID)
            if log_channel:
                embed = discord.Embed(title="📥 Slot Booking Request", color=discord.Color.orange())
                embed.add_field(name="User", value=interaction.user.mention, inline=False)
                embed.add_field(name="VTC Name", value=self.vtc_name.value, inline=False)
                embed.add_field(name="Slot Number", value=str(slot_id), inline=False)
                embed.set_footer(text="Waiting for staff action")
                view = ApproveDenyView(
                    user_id=user_id,
                    vtc_name=self.vtc_name.value,
                    slot_number=slot_name,
                    message_id=msg_id,
                    guild_id=guild_id,
                )
                await log_channel.send(embed=embed, view=view)
        except Exception:
            traceback.print_exc()
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error while processing booking.", ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        traceback.print_exc()
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "❌ An internal error occurred while processing your booking.", ephemeral=True
            )

# ---------- Slot Booking Button ----------
class BookSlotView(discord.ui.View):
    def __init__(self, message_id: int):
        super().__init__(timeout=None)
        self.add_item(BookSlotButton(message_id))

class BookSlotButton(discord.ui.Button):
    def __init__(self, message_id: int):
        super().__init__(label="📌 Book Slot", style=discord.ButtonStyle.green)
        self.message_id = message_id

    async def callback(self, interaction: discord.Interaction):
        data = booking_messages.get(self.message_id)
        if not data:
            return await interaction.response.send_message("❌ Booking message not found.", ephemeral=True)
        slots_dict = data["slots"]
        if all(slots_dict[s] for s in slots_dict):
            return await interaction.response.send_message("❌ All slots are already booked.", ephemeral=True)
        modal = SlotBookingModal(message_id=self.message_id)
        await interaction.response.send_modal(modal)

# ---------- Approve / Deny View ----------
class ApproveDenyView(discord.ui.View):
    def __init__(self, user_id: int, vtc_name: str, slot_number: str, message_id: int, guild_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.vtc_name = vtc_name
        self.slot_number = slot_number
        self.message_id = message_id
        self.guild_id = guild_id

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ You are not allowed.", ephemeral=True)
        data = booking_messages.get(self.message_id)
        if not data:
            return await interaction.response.send_message("❌ Booking data missing.", ephemeral=True)
        slots_dict = data["slots"]
        if slots_dict[self.slot_number]:
            return await interaction.response.send_message("❌ Slot already approved.", ephemeral=True)
        slots_dict[self.slot_number] = self.vtc_name
        message = data["message"]
        embed = message.embeds[0]
        slot_list = "\n".join([f"**{s}:** {slots_dict[s] if slots_dict[s] else '*Available*'}" for s in slots_dict])
        embed.set_field_at(0, name="Slots", value=slot_list)
        await message.edit(embed=embed)
        await interaction.response.send_message("✅ Approved", ephemeral=True)
        user = interaction.guild.get_member(self.user_id)
        if user:
            try:
                await user.send(f"✅ Your slot **{self.slot_number}** was approved. VTC: **{self.vtc_name}**")
            except: pass

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ You are not allowed.", ephemeral=True)
        await interaction.response.send_message("❌ Denied", ephemeral=True)
        user = interaction.guild.get_member(self.user_id)
        if user:
            try:
                await user.send(f"❌ Your slot **{self.slot_number}** booking was denied.")
            except: pass

    @discord.ui.button(label="Remove Approval", style=discord.ButtonStyle.grey)
    async def remove_approval(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ You are not allowed.", ephemeral=True)
        data = booking_messages.get(self.message_id)
        if not data:
            return await interaction.response.send_message("❌ No data.", ephemeral=True)
        slots_dict = data["slots"]
        if not slots_dict[self.slot_number]:
            return await interaction.response.send_message("❌ Slot is not approved.", ephemeral=True)
        slots_dict[self.slot_number] = None
        message = data["message"]
        embed = message.embeds[0]
        slot_list = "\n".join([f"**{s}:** {slots_dict[s] if slots_dict[s] else '*Available*'}" for s in slots_dict])
        embed.set_field_at(0, name="Slots", value=slot_list)
        await message.edit(embed=embed)
        await interaction.response.send_message("🗑 Approval removed.", ephemeral=True)

# ---------- /create COMMAND ----------
@bot.tree.command(name="create", description="Create a slot booking message (staff only)")
@app_commands.describe(title="Title of the booking", slot_range="Example: 1-10", color="Optional embed color", banner="Optional image URL")
async def create(interaction: discord.Interaction, title: str, slot_range: str, color: str = None, banner: str = None):
    if not is_staff_member(interaction.user):
        return await interaction.response.send_message("❌ You're not allowed.", ephemeral=True)
    slots = await parse_slot_range(slot_range)
    if not slots:
        return await interaction.response.send_message("❌ Invalid slot range.", ephemeral=True)
    color_parsed = parse_color(color)
    embed = discord.Embed(title=title, color=color_parsed or discord.Color.blue())
    embed.add_field(name="Slots", value="\n".join([f"**{s}:** *Available*" for s in slots]), inline=False)
    if banner:
        embed.set_image(url=banner)
    await interaction.response.send_message("✅ Slot booking created!", ephemeral=True)
    msg = await interaction.channel.send(embed=embed, view=BookSlotView(0))
    booking_messages[msg.id] = {"message": msg, "slots": {s: None for s in slots}}
    msg.view.children[0].message_id = msg.id
    await msg.edit(view=msg.view)

# ---------- Mark Attendance Button ----------
class MarkAttendanceButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ I Will Be There", style=discord.ButtonStyle.green, custom_id="attendance_mark")
    async def mark_attendance(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🎉 Thank you! Your attendance has been marked.", ephemeral=True)

# ---------- /mark COMMAND ----------
@bot.tree.command(name="mark", description="Create attendance embed from TruckersMP")
@app_commands.describe(event_link="TruckersMP event link", channel="Where to send the embed", color="Optional embed color", mention_role="Optional role to ping")
async def mark(interaction: discord.Interaction, event_link: str, channel: discord.TextChannel, color: str = None, mention_role: discord.Role = None):
    if not is_staff_member(interaction.user):
        return await interaction.response.send_message("❌ You're not allowed.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    match = re.search(r"/events/(\d+)", event_link)
    if not match:
        return await interaction.followup.send("❌ Invalid event link.", ephemeral=True)
    event_id = match.group(1)
    api_url = f"https://api.truckersmp.com/v2/events/{event_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(api_url) as r:
            data = await r.json()
    if not data.get("response"):
        return await interaction.followup.send("❌ Could not fetch event.", ephemeral=True)
    event_info = data["response"]
    title = event_info.get("name", "Event")
    banner = event_info.get("banner")
    vtc_info = event_info.get("vtc", {})
    avatar = vtc_info.get("logo")
    meetup_dt_raw = event_info.get("meetupDateTime")
    if meetup_dt_raw and meetup_dt_raw.endswith("Z"):
        meetup_dt_raw = meetup_dt_raw[:-1]
    try:
        meetup_dt = datetime.fromisoformat(meetup_dt_raw).replace(tzinfo=timezone.utc)
    except:
        meetup_dt = datetime.utcnow().replace(tzinfo=timezone.utc)
    color_parsed = parse_color(color) or discord.Color.blue()
    embed = discord.Embed(title=title, description="**🙏 𝐏𝐥𝐳 𝐊𝐢𝐧𝐝𝐥𝐲 𝐌𝐚𝐫𝐤 𝐘𝐨𝐮𝐑 𝐀𝐭𝐭𝐞𝐧𝐝𝐚𝐧𝐜𝐞 𝐎𝐧 𝐓𝐡𝐢𝐒 𝐄𝐯𝐞𝐧𝐭 : ❤️**", color=color_parsed, timestamp=meetup_dt)
    if banner:
        embed.set_image(url=banner)
    if avatar:
        embed.set_thumbnail(url=avatar)
    embed.set_footer(text="Powered by NepPath")
    mention_text = mention_role.mention if mention_role else ""
    await channel.send(content=mention_text, embed=embed, view=MarkAttendanceButton())
    await interaction.followup.send("✅ Attendance embed sent!", ephemeral=True)

# ---------- ON READY ----------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Slash commands synced: {len(synced)}")
    except Exception:
        traceback.print_exc()

# ---------- RUN BOT ----------
bot.run(BOT_TOKEN)
