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

# booking memory
booking_messages = {}

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
    """Parse named, hex (with or without #), or RGB color."""
    if not input_color:
        return None

    input_color = input_color.lower().strip()

    # Named colors
    if input_color in COLOR_OPTIONS:
        return COLOR_OPTIONS[input_color]

    # Hex without # (add # back)
    if re.fullmatch(r"[0-9a-f]{6}", input_color):
        try:
            return discord.Color(int(input_color, 16))
        except:
            return None

    # Hex with #
    if input_color.startswith("#") and re.fullmatch(r"#[0-9a-f]{6}", input_color):
        try:
            return discord.Color(int(input_color[1:], 16))
        except:
            return None

    return None


async def parse_slot_range(text: str):
    """Convert '1-10' into ['1', '2', ...]"""
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
#                    SLOT BOOKING VIEW
# ============================================================
class BookSlotView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="📌 Book Slot",
        style=discord.ButtonStyle.green,
        custom_id="book_slot_button",
    )
    async def book_slot_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            msg_id = interaction.message.id
            data = booking_messages.get(msg_id)

            if not data:
                return await interaction.response.send_message(
                    "❌ This button is not attached to a valid booking message.\n"
                    "Create a new booking with `/create`.",
                    ephemeral=True,
                )

            slots_dict = data.get("slots", {})
            if not slots_dict:
                return await interaction.response.send_message(
                    "❌ Booking data missing.", ephemeral=True
                )

            if not any(v is None for v in slots_dict.values()):
                return await interaction.response.send_message(
                    "❌ No available slots.", ephemeral=True
                )

            # This modal must exist. You did not include its code, so placeholder:
            await interaction.response.send_message(
                "Modal not implemented yet.", ephemeral=True
            )

        except Exception:
            traceback.print_exc()
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Internal error.", ephemeral=True
                )


# ============================================================
#                    ANNOUNCEMENT MODAL
# ============================================================
class AnnouncementModal(discord.ui.Modal, title="Create Announcement"):
    title = discord.ui.TextInput(
        label="Announcement Title",
        placeholder="Enter the title",
        max_length=100,
    )
    message = discord.ui.TextInput(
        label="Announcement Message",
        placeholder="Enter content",
        style=discord.TextStyle.paragraph,
        max_length=2000,
    )
    color = discord.ui.TextInput(
        label="Announcement Color (optional)",
        placeholder="blue | red | #ff0000 ...",
        max_length=7,
        required=False,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            announcement_title = self.title.value.strip()
            announcement_message = self.message.value.strip()
            color_input = self.color.value.strip()

            embed_color = parse_color(color_input) or discord.Color.blue()

            announcement_channel = discord.utils.get(
                interaction.guild.text_channels, name="announcements"
            )

            if not announcement_channel:
                return await interaction.response.send_message(
                    "❌ `#announcements` channel not found.",
                    ephemeral=True,
                )

            embed = discord.Embed(
                title=announcement_title,
                description=announcement_message,
                color=embed_color,
            )

            await announcement_channel.send(embed=embed)

            await interaction.response.send_message(
                "✅ Announcement sent.", ephemeral=True
            )

        except Exception:
            traceback.print_exc()
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Error occurred.", ephemeral=True
                )


# ============================================================
#                      MARK COMMAND
# ============================================================
@bot.tree.command(
    name="mark",
    description="Create a Mark Attendance embed from a TruckersMP link."
)
@app_commands.describe(
    event_link="TruckersMP event link"
)
async def mark(interaction: discord.Interaction, event_link: str):
    await interaction.response.defer(thinking=True, ephemeral=True)

    match = re.search(r"/events/(\d+)", event_link)
    if not match:
        return await interaction.followup.send(
            "❌ Invalid TruckersMP link.",
            ephemeral=True,
        )

    event_id = match.group(1)
    api_url = f"https://api.truckersmp.com/v2/events/{event_id}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as resp:
                if resp.status != 200:
                    return await interaction.followup.send(
                        f"❌ API returned HTTP {resp.status}.",
                        ephemeral=True,
                    )
                data = await resp.json()
    except Exception as e:
        traceback.print_exc()
        return await interaction.followup.send(
            f"❌ API error: {e}",
            ephemeral=True,
        )

    if data.get("error"):
        return await interaction.followup.send(
            "❌ API reports invalid event ID.",
            ephemeral=True,
        )

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
        description="<@&1398294285597671606> \n\n **🙏 𝐏𝐋𝐄𝐀𝐒𝐄 𝐌𝐀𝐑𝐊 𝐘𝐎𝐔𝐑 𝐀𝐓𝐓𝐄𝐍𝐃𝐀𝐍𝐂𝐄 ❤️**",
        color=discord.Color(0xFF5A20),
    )
    embed.add_field(
        name="Event",
        value=f"[{name}]({event_link})",
        inline=False
    )
    embed.add_field(name="Date", value=date_str, inline=True)
    embed.add_field(name="Meetup Time", value=meetup_time, inline=True)
    embed.add_field(name="Departure Time", value=depart_time, inline=True)

    if banner:
        embed.set_image(url=banner)

    # missing view in your code, so placeholder
    await interaction.channel.send(embed=embed)

    await interaction.followup.send(
        "✅ Attendance embed created.",
        ephemeral=True
    )


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

    sent_msg = await channel.send(embed=embed, view=BookSlotView())

    booking_messages[sent_msg.id] = {
        "message": sent_msg,
        "slots": {slot: None for slot in slots_list},
    }

    await interaction.response.send_message(
        f"✅ Booking embed created with {len(slots_list)} slots.",
        ephemeral=True
    )


# ============================================================
#                         READY
# ============================================================
@bot.event
async def on_ready():
    bot.add_view(BookSlotView())
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

    try:
        synced = await bot.tree.sync()
        print(f"✅ Slash commands synced ({len(synced)} commands).")
    except Exception as e:
        print("❌ Slash sync error:", e)
        traceback.print_exc()

    for cmd in bot.tree.get_commands():
        print(f"Command: {cmd.name}")


# ============================================================
#                          RUN
# ============================================================
bot.run(BOT_TOKEN)
