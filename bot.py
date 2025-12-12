# bot.py

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
                "❌ An internal error occurred while running this command.",
                ephemeral=True,
            )
    except Exception:
        pass


# ---------- In-memory storage ----------
booking_messages = {}  # {message_id: {"message": Message, "slots": {slot: vtc_name}}}
user_submissions = {}  # {guild_id: {user_id: set(slots)}}


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


# ---------- Slot Booking Modal ----------
class SlotBookingModal(discord.ui.Modal, title="Book Slot"):
    vtc_name = discord.ui.TextInput(
        label="VTC Name",
        placeholder="Enter your VTC name",
        max_length=100,
    )
    slot_number = discord.ui.TextInput(
        label="Slot Number",
        placeholder="Enter slot number like: 1",
        max_length=3,
    )

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
                return await interaction.response.send_message(
                    "❌ Booking data not found.", ephemeral=True
                )

            slots_dict = data["slots"]
            raw = self.slot_number.value.strip()

            if not raw.isdigit():
                return await interaction.response.send_message(
                    "❌ Slot number must be a **number only**, like `1`.",
                    ephemeral=True,
                )

            slot_id = int(raw)
            slot_name = f"Slot {slot_id}"

            if slot_name not in slots_dict:
                return await interaction.response.send_message(
                    f"❌ Slot `{raw}` does not exist.",
                    ephemeral=True,
                )

            if slots_dict[slot_name]:
                return await interaction.response.send_message(
                    f"❌ Slot `{raw}` is already booked.",
                    ephemeral=True,
                )

            guild_id = interaction.guild_id
            user_id = interaction.user.id

            if guild_id not in user_submissions:
                user_submissions[guild_id] = {}

            if (
                user_id in user_submissions[guild_id]
                and slot_name in user_submissions[guild_id][user_id]
            ):
                return await interaction.response.send_message(
                    f"❌ You already submitted slot `{raw}`.",
                    ephemeral=True,
                )

            user_submissions[guild_id].setdefault(user_id, set()).add(slot_name)

            await interaction.response.send_message(
                f"✅ Request submitted for slot **{slot_id}**",
                ephemeral=True,
            )

            log_channel = bot.get_channel(STAFF_LOG_CHANNEL_ID)
            if log_channel:
                embed = discord.Embed(
                    title="📥 Slot Booking Request",
                    color=discord.Color.orange(),
                )
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
                await interaction.response.send_message(
                    "❌ Error while processing booking.",
                    ephemeral=True,
                )

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        traceback.print_exc()
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "❌ An internal error occurred while processing your booking.",
                ephemeral=True,
            )


# ---------- Book Slot Button ----------
class BookSlotView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📌 Book Slot", style=discord.ButtonStyle.green, custom_id="book_slot_button")
    async def book_slot_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            msg_id = interaction.message.id
            data = booking_messages.get(msg_id)

            if not data:
                return await interaction.response.send_message(
                    "❌ This button is not attached to a valid booking message.\n"
                    "Create a new booking with `/create` for this block of slots.",
                    ephemeral=True,
                )

            slots_dict = data.get("slots", {})
            if not any(v is None for v in slots_dict.values()):
                return await interaction.response.send_message(
                    "❌ No available slots in this booking message.",
                    ephemeral=True,
                )

            modal = SlotBookingModal(message_id=msg_id)
            await interaction.response.send_modal(modal)

        except Exception:
            traceback.print_exc()
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An internal error occurred when opening the booking modal.",
                    ephemeral=True,
                )


# ---------- Staff Approve/Deny/Remove ----------
class ApproveDenyView(discord.ui.View):
    def __init__(self, user_id: int, vtc_name: str, slot_number: str, message_id: int, guild_id: int):
        super().__init__()
        self.user_id = user_id
        self.vtc_name = vtc_name
        self.slot_number = slot_number
        self.message_id = message_id
        self.guild_id = guild_id

    async def _notify_user(self, approved: bool):
        try:
            user = await bot.fetch_user(self.user_id)
            if approved:
                await user.send(f"✅ Your slot **{self.slot_number}** has been approved! VTC: **{self.vtc_name}**")
            else:
                await user.send(f"❌ Your slot **{self.slot_number}** has been denied or removed.")
        except Exception:
            pass

    @discord.ui.button(label="✅ Approve", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not is_staff_member(interaction.user):
                return await interaction.response.send_message("❌ You are not staff.", ephemeral=True)

            data = booking_messages.get(self.message_id)
            if not data:
                return await interaction.response.send_message(
                    "❌ Booking data not found.", ephemeral=True
                )

            slots_dict = data["slots"]
            if slots_dict.get(self.slot_number):
                return await interaction.response.send_message("❌ Slot already approved.", ephemeral=True)

            slots_dict[self.slot_number] = self.vtc_name
            if self.user_id in user_submissions.get(self.guild_id, {}):
                user_submissions[self.guild_id][self.user_id].discard(self.slot_number)

            original_msg = data["message"]
            if original_msg.embeds:
                new_embed = original_msg.embeds[0]
                updated_lines = [f"{s} - {v} ✅" if v else s for s, v in slots_dict.items()]
                new_embed.description = "\n".join(updated_lines)
                await original_msg.edit(embed=new_embed)

            embed = interaction.message.embeds[0]
            embed.color = discord.Color.green()
            embed.set_footer(text=f"✅ Approved by {interaction.user}")
            button.disabled = True
            self.deny.disabled = True
            await interaction.message.edit(embed=embed, view=self)

            await self._notify_user(True)
            await interaction.response.send_message("✅ Approved.", ephemeral=True)

        except Exception:
            traceback.print_exc()
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An internal error occurred while approving.", ephemeral=True)

    @discord.ui.button(label="❌ Deny", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not is_staff_member(interaction.user):
                return await interaction.response.send_message("❌ You are not staff.", ephemeral=True)

            if self.user_id in user_submissions.get(self.guild_id, {}):
                user_submissions[self.guild_id][self.user_id].discard(self.slot_number)

            embed = interaction.message.embeds[0]
            embed.color = discord.Color.red()
            embed.set_footer(text=f"❌ Denied by {interaction.user}")
            button.disabled = True
            self.approve.disabled = True
            await interaction.message.edit(embed=embed, view=self)

            await self._notify_user(False)
            await interaction.response.send_message("❌ Denied.", ephemeral=True)

        except Exception:
            traceback.print_exc()
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An internal error occurred while denying.", ephemeral=True)

    @discord.ui.button(label="♻ Remove Approval", style=discord.ButtonStyle.gray)
    async def remove_approval(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not is_staff_member(interaction.user):
                return await interaction.response.send_message("❌ You are not staff.", ephemeral=True)

            data = booking_messages.get(self.message_id)
            if not data:
                return await interaction.response.send_message(
                    "❌ Booking data not found.", ephemeral=True
                )

            slots_dict = data["slots"]
            if not slots_dict.get(self.slot_number):
                return await interaction.response.send_message("❌ Slot is not approved.", ephemeral=True)

            slots_dict[self.slot_number] = None

            original_msg = data["message"]
            if original_msg.embeds:
                new_embed = original_msg.embeds[0]
                updated_lines = [f"{s} - {v} ✅" if v else s for s, v in slots_dict.items()]
                new_embed.description = "\n".join(updated_lines)
                await original_msg.edit(embed=new_embed)

            await self._notify_user(False)
            await interaction.response.send_message(f"♻ Removed approval for {self.slot_number}.", ephemeral=True)

        except Exception:
            traceback.print_exc()
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An internal error occurred while removing approval.", ephemeral=True)


# ---------- /create ----------
@bot.tree.command(name="create", description="Staff only: Create booking message.")
@app_commands.describe(
    channel="Channel to post booking embed",
    title="Embed title",
    slot_range="Example: 1-10",
    color="Color name or hex",
    image="Optional image URL",
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

    desc = "\n".join(slots_list)
    embed = discord.Embed(title=title, description=desc, color=hex_color)
    if image:
        embed.set_image(url=image)

    sent_msg = await channel.send(embed=embed, view=BookSlotView())
    booking_messages[sent_msg.id] = {"message": sent_msg, "slots": {slot: None for slot in slots_list}}

    await interaction.response.send_message(f"✅ Booking embed created with {len(slots_list)} slots.", ephemeral=True)


# ---------- Mark Attendance ----------
class MarkAttendanceView(discord.ui.View):
    def __init__(self, event_link: str):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label='I Will Be There',
                style=discord.ButtonStyle.link,
                url=event_link,
            )
        )


@bot.tree.command(name="mark", description="Create a Mark Attendance embed from a TruckersMP event link.")
@app_commands.describe(event_link="TruckersMP event URL, e.g. https://truckersmp.com/events/12345")
async def mark(interaction: discord.Interaction, event_link: str):
    await interaction.response.defer(thinking=True, ephemeral=True)

    match = re.search(r"/events/(\d+)", event_link)
    if not match:
        return await interaction.followup.send(
            "❌ Could not find an event ID in that link.", ephemeral=True
        )

    event_id = match.group(1)
    api_url = f"https://api.truckersmp.com/v2/events/{event_id}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as resp:
                if resp.status != 200:
                    return await interaction.followup.send(f"❌ TruckersMP API returned HTTP {resp.status}.", ephemeral=True)
                data = await resp.json()
    except Exception as e:
        traceback.print_exc()
        return await interaction.followup.send(f"❌ Failed to contact TruckersMP API: `{e}`", ephemeral=True)

    if not data.get("response"):
        error_msg = data.get("error", "Unknown error from TruckersMP API")
        return await interaction.followup.send(f"❌ Could not fetch event data: {error_msg}", ephemeral=True)

    event_info = data["response"]
    event_name = event_info.get("name", "TruckersMP Event")
    event_start = event_info.get("startDate") or "Unknown date"
    event_description = event_info.get("description", "")

    embed = discord.Embed(
        title=f"📌 {event_name}",
        description=f"{event_description}\n\n**Start:** {event_start}\n\nClick the button below if you will attend the event.",
        color=discord.Color.blue()
    )

    view = MarkAttendanceView(event_link=event_link)
    await interaction.followup.send(embed=embed, view=view)


# ---------- Bot Ready ----------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} ({bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} commands globally.")
    except Exception as e:
        print("❌ Failed to sync commands:", e)


# ---------- Run Bot ----------
bot.run(BOT_TOKEN)
