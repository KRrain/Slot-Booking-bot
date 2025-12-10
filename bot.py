# bot.py - Complete TruckersMP VTC Bot (Slot Booking + Attendance + Announcement)

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
STAFF_LOG_CHANNEL_ID = 1446383730242355200  # REPLACE THIS

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

# ---------- Global error handlers ----------

@bot.event
async def on_error(event_method, *args, **kwargs):
    print(f"Error in {event_method}:")
    traceback.print_exc()

@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
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

# ---------- SlotBookingModal ----------
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

        # Show available numbers (shortened if long)
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

            # Validate number input
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

            # Prevent duplicate request
            if (
                user_id in user_submissions[guild_id]
                and slot_name in user_submissions[guild_id][user_id]
            ):
                return await interaction.response.send_message(
                    f"❌ You already submitted slot `{raw}`.",
                    ephemeral=True,
                )

            # Save user request
            user_submissions[guild_id].setdefault(user_id, set()).add(slot_name)

            await interaction.response.send_message(
                f"✅ Request submitted for slot **{slot_id}**",
                ephemeral=True,
            )

            # Log to staff
            log_channel = bot.get_channel(STAFF_LOG_CHANNEL_ID)
            if log_channel:
                embed = discord.Embed(
                    title="📥 Slot Booking Request",
                    color=discord.Color.orange(),
                )
                embed.add_field(
                    name="User", value=interaction.user.mention, inline=False
                )
                embed.add_field(
                    name="VTC Name", value=self.vtc_name.value, inline=False
                )
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

# ---------- BookSlotView ----------
class BookSlotView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="📌 Book Slot",
        style=discord.ButtonStyle.green,
        custom_id="book_slot_button",
    )
    async def book_slot_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        try:
            msg_id = interaction.message.id
            data = booking_messages.get(msg_id)

            if not data:
                return await interaction.response.send_message(
                    "❌ This button is not attached to a valid booking message.",
                    ephemeral=True,
                )

            slots_dict = data.get("slots", {})
            if not any(v is None for v in slots_dict.values()):
                return await interaction.response.send_message(
                    "❌ No available slots.",
                    ephemeral=True,
                )

            modal = SlotBookingModal(message_id=msg_id)
            await interaction.response.send_modal(modal)

        except Exception:
            traceback.print_exc()

# ---------- ApproveDenyView ----------
class ApproveDenyView(discord.ui.View):
    def __init__(
        self,
        user_id: int,
        vtc_name: str,
        slot_number: str,
        message_id: int,
        guild_id: int,
    ):
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
                await user.send(f"✅ Your slot **{self.slot_number}** approved!")
            else:
                await user.send(f"❌ Your slot **{self.slot_number}** denied.")
        except:
            pass

    @discord.ui.button(label="✅ Approve", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ Staff only.", ephemeral=True)

        data = booking_messages.get(self.message_id)
        if not data:
            return await interaction.response.send_message("❌ Booking data not found.", ephemeral=True)

        slots_dict = data["slots"]

        if slots_dict.get(self.slot_number):
            return await interaction.response.send_message("❌ Already approved.", ephemeral=True)

        slots_dict[self.slot_number] = self.vtc_name
        if self.user_id in user_submissions.get(self.guild_id, {}):
            user_submissions[self.guild_id][self.user_id].discard(self.slot_number)

        original_msg = data["message"]
        new_embed = original_msg.embeds[0]
        updated_lines = [
            f"{s} - {v} ✅" if v else s for s, v in slots_dict.items()
        ]
        new_embed.description = "\n".join(updated_lines)
        await original_msg.edit(embed=new_embed)

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.set_footer(text=f"✅ Approved by {interaction.user}")
        self.disable_all_items()
        await interaction.message.edit(embed=embed, view=self)

        await self._notify_user(True)
        await interaction.response.send_message("✅ Approved.", ephemeral=True)

    @discord.ui.button(label="❌ Deny", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ Staff only.", ephemeral=True)

        if self.user_id in user_submissions.get(self.guild_id, {}):
            user_submissions[self.guild_id][self.user_id].discard(self.slot_number)

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.set_footer(text=f"❌ Denied by {interaction.user}")
        self.disable_all_items()
        await interaction.message.edit(embed=embed, view=self)

        await self._notify_user(False)
        await interaction.response.send_message("❌ Denied.", ephemeral=True)

# ---------- /create ----------
@bot.tree.command(name="create", description="Staff only: Create booking message.")
@app_commands.describe(
    channel="Channel to post",
    title="Embed title",
    slot_range="Example: 1-10",
    color="Color name or hex",
    image="Optional image URL",
)
async def create(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    title: str,
    slot_range: str,
    color: str,
    image: str = None,
):
    if not is_staff_member(interaction.user):
        return await interaction.response.send_message("❌ Staff only.", ephemeral=True)

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

    booking_messages[sent_msg.id] = {
        "message": sent_msg,
        "slots": {slot: None for slot in slots_list},
    }

    await interaction.response.send_message(
        f"✅ Booking embed created with {len(slots_list)} slots.",
        ephemeral=True,
    )

# ---------- MarkAttendanceView ----------
class MarkAttendanceView(discord.ui.View):
    def __init__(self, event_link: str):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label='Go To "I Will Be There"',
                style=discord.ButtonStyle.link,
                url=event_link,
            )
        )

# ---------- /mark ----------
@bot.tree.command(
    name="mark",
    description="Create attendance embed from TruckersMP event link.",
)
@app_commands.describe(
    event_link="TruckersMP event URL"
)
async def mark(interaction: discord.Interaction, event_link: str):
    await interaction.response.defer(ephemeral=True)

    match = re.search(r"/events/(\d+)", event_link)
    if not match:
        return await interaction.followup.send("❌ Invalid link.", ephemeral=True)

    event_id = match.group(1)
    api_url = f"https://api.truckersmp.com/v2/events/{event_id}"

    async with aiohttp.ClientSession() as session:
        async with session.get(api_url) as resp:
            if resp.status != 200:
                return await interaction.followup.send("❌ API error.", ephemeral=True)
            data = await resp.json()

    event = data.get("response", {})
    name = event.get("name", "Unknown Event")
    banner = event.get("banner", None)

    embed = discord.Embed(
        title="Mark Your Attendance",
        description="Please mark your attendance ❤️",
        color=0xFF5A20,
    )
    embed.add_field(
        name="Event",
        value=f"[{name}]({event_link})",
        inline=False,
    )
    if banner:
        embed.set_image(url=banner)

    await interaction.channel.send(embed=embed, view=MarkAttendanceView(event_link))
    await interaction.followup.send("✅ Created.", ephemeral=True)

# ---------- PERFECT /announcement (EXACTLY LIKE SCREENSHOT) ----------
class AnnouncementModal(discord.ui.Modal, title="Announce Upcoming Convoy"):
    event_id = discord.ui.TextInput(
        label="TruckersMP Event ID (last part of URL)",
        placeholder="e.g. 12345",
        max_length=20
    )
    distance = discord.ui.TextInput(
        label="Distance",
        placeholder="e.g. 850 km",
        max_length=50
    )
    slot_image = discord.ui.TextInput(
        label="Slot Image URL (optional)",
        placeholder="https://i.imgur.com/abc123.png",
        required=False,
        max_length=200
    )
    vtc_slot = discord.ui.TextInput(
        label="VTC Slot Number",
        placeholder="e.g. 15",
        max_length=10
    )
    route_image = discord.ui.TextInput(
        label="Route Image URL",
        placeholder="https://i.imgur.com/route.jpg",
        max_length=200
    )

    async def on_submit(self, interaction: discord.Interaction):
        eid = self.event_id.value.strip()
        dist = self.distance.value.strip()
        vtc_slot_num = self.vtc_slot.value.strip()

        # Fetch event name
        event_name = "Unknown Convoy"
        try:
            url = f"https://api.truckersmp.com/v2/events/{eid}"
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json().get("response", {})
                event_name = data.get("name", "Unknown Convoy")
        except:
            pass

        # Build embed
        embed = discord.Embed(
            title=event_name,
            description=f"**Distance:** {dist}\n**VTC Slot:** {vtc_slot_num}",
            color=0x00FFFF
        )
        embed.add_field(
            name="Event Link",
            value=f"[Click Here to Join](https://truckersmp.com/event/{eid})",
            inline=False
        )
        if self.route_image.value:
            embed.set_image(url=self.route_image.value)
        if self.slot_image.value:
            embed.set_thumbnail(url=self.slot_image.value)
        embed.set_footer(text=f"Announced by {interaction.user}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)

        # Preview + Send/Cancel
        await interaction.response.send_message(
            "**Preview:**",
            embed=embed,
            view=ConfirmSendView(embed),
            ephemeral=True
        )

class ConfirmSendView(discord.ui.View):
    def __init__(self, embed):
        super().__init__(timeout=300)
        self.embed = embed

    @discord.ui.button(label="Send Announcement", style=discord.ButtonStyle.green)
    async def send(self, interaction: discord.Interaction, button: discord.ui.Button):
        # CHANGE THIS TO YOUR ANNOUNCEMENT CHANNEL ID
        channel = interaction.guild.get_channel(1446383730242355200)  # ← Replace with your channel ID!
        if channel:
            await channel.send(embed=self.embed)
            await interaction.response.edit_message(content="Sent!", view=None, embed=None)
        else:
            await interaction.response.edit_message(content="Channel not found!", view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Cancelled.", view=None, embed=None)

@bot.tree.command(name="announcement", description="Staff: Announce upcoming convoy")
async def announcement(interaction: discord.Interaction):
    if not is_staff_member(interaction.user):
        return await interaction.response.send_message("❌ Staff only.", ephemeral=True)

    await interaction.response.send_modal(AnnouncementModal())

# ---------- Ready ----------
@bot.event
async def on_ready():
    bot.add_view(BookSlotView())
    print(f"Logged in as {bot.user}")
    synced = await bot.tree.sync()
    print(f"Synced {len(synced)} commands.")

bot.run(BOT_TOKEN)
