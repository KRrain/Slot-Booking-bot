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
load_dotenv()  # Load .env file
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Your bot token here

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

# ---------- View for Slot Booking ----------
class BookSlotView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # persistent

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
                # Covers: message not registered, edited into weird state, or created before restart
                return await interaction.response.send_message(
                    "❌ This button is not attached to a valid booking message.\n"
                    "Create a new booking with `/create` for this block of slots.",
                    ephemeral=True,
                )

            slots_dict = data.get("slots", {})
            if not slots_dict:
                return await interaction.response.send_message(
                    "❌ Booking data is missing for this message.",
                    ephemeral=True,
                )

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


# ---------- Announcement Modal ----------
class AnnouncementModal(discord.ui.Modal, title="Create Announcement"):
    title = discord.ui.TextInput(
        label="Announcement Title",
        placeholder="Enter the title of your announcement",
        max_length=100,
    )
    message = discord.ui.TextInput(
        label="Announcement Message",
        placeholder="Enter the content of your announcement",
        style=discord.TextStyle.paragraph,
        max_length=2000,
    )
    color = discord.ui.TextInput(
        label="Announcement Color (optional)",
        placeholder="Enter a color name or hex code (e.g., 'blue' or '#ff5733')",
        max_length=7,
        required=False,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Get inputs
            announcement_title = self.title.value.strip()
            announcement_message = self.message.value.strip()
            color_input = self.color.value.strip()

            # Parse the color
            embed_color = parse_color(color_input) or discord.Color.blue()

            # Send the announcement
            announcement_channel = discord.utils.get(
                interaction.guild.text_channels, name="announcements"
            )

            if not announcement_channel:
                return await interaction.response.send_message(
                    "❌ The `announcements` channel was not found.", ephemeral=True
                )

            # Embed for the announcement
            embed = discord.Embed(
                title=announcement_title, description=announcement_message, color=embed_color
            )

            # Send the embed
            await announcement_channel.send(embed=embed)

            await interaction.response.send_message(
                "✅ Your announcement has been sent.", ephemeral=True
            )

        except Exception:
            traceback.print_exc()
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An internal error occurred while processing the announcement.",
                    ephemeral=True,
                )


# ---------- /mark Command ----------
@bot.tree.command(name="mark", description="Create a Mark Attendance embed from a TruckersMP event link.")
@app_commands.describe(
    event_link="TruckersMP event URL, e.g. https://truckersmp.com/events/12345"
)
async def mark(interaction: discord.Interaction, event_link: str):
    await interaction.response.defer(thinking=True, ephemeral=True)

    # Extract numeric event ID from the URL
    match = re.search(r"/events/(\d+)", event_link)
    if not match:
        return await interaction.followup.send(
            "❌ Could not find an event ID in that link. "
            "Make sure it looks like `https://truckersmp.com/events/12345`.",
            ephemeral=True,
        )

    event_id = match.group(1)

    # Fetch event info from TruckersMP API
    api_url = f"https://api.truckersmp.com/v2/events/{event_id}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as resp:
                if resp.status != 200:
                    return await interaction.followup.send(
                        f"❌ TruckersMP API returned HTTP {resp.status}.",
                        ephemeral=True,
                    )
                data = await resp.json()
    except Exception as e:
        traceback.print_exc()
        return await interaction.followup.send(
            f"❌ Failed to contact TruckersMP API: `{e}`", ephemeral=True
        )

    if data.get("error"):
        return await interaction.followup.send(
            "❌ TruckersMP API reported an error for that event ID.",
            ephemeral=True,
        )

    event = data.get("response") or {}
    name = event.get("name", "Unknown Event")

    # Times (ISO 8601 strings)
    start_raw = event.get("start_at") or event.get("start") or ""
    meetup_raw = event.get("meetup_at") or event.get("meetup") or start_raw

    def parse_iso(iso: str):
        if not iso:
            return None
        iso = iso.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(iso)
        except Exception:
            return None

    start_dt = parse_iso(start_raw)
    meetup_dt = parse_iso(meetup_raw)

    if start_dt:
        date_str = start_dt.strftime("%a, %d %B %Y")
        depart_time_str = start_dt.strftime("%H:%M UTC")
    else:
        date_str = "Unknown"
        depart_time_str = "Unknown"

    if meetup_dt:
        meetup_time_str = meetup_dt.strftime("%H:%M UTC")
    else:
        meetup_time_str = "Unknown"

    banner = event.get("banner") or event.get("cover") or None

    # Embed with color #FF5A20
    embed = discord.Embed(
        title="<:NepPathLogocircledim:1395694322061410334> Mark Your Attendance",
        description="<@&1398294285597671606> \n Plz Kindly Mark Your Attendance On This Event : ❤️",
        color=discord.Color(0xFF5A20),
    )
    embed.add_field(
        name="Event",
        value=f"[{name}]({event_link})",
        inline=False,
    )
    embed.add_field(name="Date", value=date_str, inline=True)
    embed.add_field(name="Meetup Time", value=meetup_time_str, inline=True)
    embed.add_field(name="Departure Time", value=depart_time_str, inline=True)

    if banner:
        embed.set_image(url=banner)

    # Send to the channel where the command was used
    await interaction.channel.send(embed=embed, view=MarkAttendanceView(event_link))

    await interaction.followup.send(
        "✅ Attendance embed created.", ephemeral=True
    )


# ---------- /create Command ----------
@bot.tree.command(name="create", description="Staff only: Create booking message.")
@app_commands.describe(
    channel="Channel to post booking embed",
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
        return await interaction.response.send_message(
            "❌ You are not staff.", ephemeral=True
        )

    slots_list = await parse_slot_range(slot_range)
    if not slots_list:
        return await interaction.response.send_message(
            "❌ Invalid slot range.", ephemeral=True
        )

    hex_color = parse_color(color)
    if not hex_color:
        return await interaction.response.send_message(
            "❌ Invalid color.", ephemeral=True
        )

    desc = "\n".join(slots_list)
    embed = discord.Embed(title=title, description=desc, color=hex_color)
    if image:
        embed.set_image(url=image)

    # Each /create makes a NEW message with its own booking list
    sent_msg = await channel.send(embed=embed, view=BookSlotView())

    booking_messages[sent_msg.id] = {
        "message": sent_msg,
        "slots": {slot: None for slot in slots_list},
    }

    await interaction.response.send_message(
        f"✅ Booking embed created with {len(slots_list)} slots.",
        ephemeral=True
    )


# ---------- Ready ----------
@bot.event
async def on_ready():
    bot.add_view(BookSlotView())  # persistent view for all "Book Slot" buttons
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    
    try:
        # Force full sync of all commands
        synced = await bot.tree.sync(guild=None)  # `guild=None` forces global sync
        print(f"✅ Slash commands synced globally ({len(synced)} commands).")
    except Exception as e:
        print("❌ Slash sync error:", e)
        traceback.print_exc()

    # Debugging: List all registered commands
    for command in bot.tree.get_commands():
        print(f"Command registered: {command.name}")


# ---------- Run ----------
bot.run(BOT_TOKEN)
