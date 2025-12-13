# ---------------- bot.py — Part 1 ----------------

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
import re
import traceback
from datetime import datetime, timedelta, timezone
import os
from dotenv import load_dotenv
from ac.decline import setup_decline_command
from ac.decline_time import setup_decline_time_command

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
                "❌ An internal error occurred while running this command.", ephemeral=True
            )
    except Exception:
        pass

# ---------- In-memory storage ----------

# Note: in-memory only — consider persisting for production
booking_messages = {}  # {message_id: {"message": Message, "slots": {slot: vtc_name}}}
user_submissions = {}  # {guild_id: {user_id: set(slots)}}

# ---------- Helpers ----------

def is_staff_member(member: discord.Member) -> bool:
    """Return True if the member has any of the STAFF_ROLE_IDS."""
    try:
        return any(role.id in STAFF_ROLE_IDS for role in member.roles)
    except Exception:
        return False

async def parse_slot_range(slot_range: str):
    """Parse a simple range like "1-10" into ["Slot 1", ..., "Slot 10"]."""
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
    """Accept named colors (from COLOR_OPTIONS) or hex like "#ff0000" or "ff0000"."""
    if not color_str:
        return None
    try:
        if color_str.lower() in COLOR_OPTIONS:
            return COLOR_OPTIONS[color_str.lower()]
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

            # Prevent duplicate request by same user for same slot
            if user_id in user_submissions[guild_id] and slot_name in user_submissions[guild_id][user_id]:
                return await interaction.response.send_message(f"❌ You already submitted slot `{raw}`.", ephemeral=True)

            # Save user request
            user_submissions[guild_id].setdefault(user_id, set()).add(slot_name)

            await interaction.response.send_message(f"✅ Request submitted for slot **{slot_id}**", ephemeral=True)

            # Log to staff channel (if available)
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

# ---------------- End of Part 1 ----------------
# ---------------- bot.py — Part 2 ----------------

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
                    "❌ This button is not attached to a valid booking message.\nCreate a new booking with `/create` for this block of slots.",
                    ephemeral=True,
                )

            slots_dict = data.get("slots", {})
            if not any(v is None for v in slots_dict.values()):
                return await interaction.response.send_message("❌ No available slots in this booking message.", ephemeral=True)

            modal = SlotBookingModal(message_id=msg_id)
            await interaction.response.send_modal(modal)

        except Exception:
            traceback.print_exc()
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An internal error occurred when opening the booking modal.", ephemeral=True)

# ---------- Approve/Deny/Remove Approval ----------

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
                return await interaction.response.send_message("❌ Booking data not found.", ephemeral=True)

            slots_dict = data["slots"]
            if slots_dict.get(self.slot_number):
                return await interaction.response.send_message("❌ Slot already approved.", ephemeral=True)

            # Approve
            slots_dict[self.slot_number] = self.vtc_name
            if self.user_id in user_submissions.get(self.guild_id, {}):
                user_submissions[self.guild_id][self.user_id].discard(self.slot_number)

            # Update main embed if exists
            original_msg = data["message"]
            if original_msg and original_msg.embeds:
                new_embed = original_msg.embeds[0]
                updated_lines = [f"{s} - {v} ✅" if v else s for s, v in slots_dict.items()]
                new_embed.description = "\n".join(updated_lines)
                try:
                    await original_msg.edit(embed=new_embed)
                except Exception:
                    pass

            # Update staff log message embed
            try:
                embed = interaction.message.embeds[0]
                embed.color = discord.Color.green()
                embed.set_footer(text=f"✅ Approved by {interaction.user}")
                button.disabled = True
                self.deny.disabled = True
                await interaction.message.edit(embed=embed, view=self)
            except Exception:
                pass

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

            try:
                embed = interaction.message.embeds[0]
                embed.color = discord.Color.red()
                embed.set_footer(text=f"❌ Denied by {interaction.user}")
                button.disabled = True
                self.approve.disabled = True
                await interaction.message.edit(embed=embed, view=self)
            except Exception:
                pass

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
                return await interaction.response.send_message("❌ Booking data not found.", ephemeral=True)

            slots_dict = data["slots"]
            if not slots_dict.get(self.slot_number):
                return await interaction.response.send_message("❌ Slot is not approved.", ephemeral=True)

            # Remove approval
            slots_dict[self.slot_number] = None

            # Update main embed if exists
            original_msg = data["message"]
            if original_msg and original_msg.embeds:
                new_embed = original_msg.embeds[0]
                updated_lines = [f"{s} - {v} ✅" if v else s for s, v in slots_dict.items()]
                new_embed.description = "\n".join(updated_lines)
                try:
                    await original_msg.edit(embed=new_embed)
                except Exception:
                    pass

            await self._notify_user(False)
            await interaction.response.send_message(f"♻ Removed approval for {self.slot_number}.", ephemeral=True)

        except Exception:
            traceback.print_exc()
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An internal error occurred while removing approval.", ephemeral=True)

# ---------------- End of Part 2 ----------------
# ---------------- bot.py — Part 3 ----------------

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


# ---------- /mark with optional role mention ----------

class MarkAttendanceView(discord.ui.View):
    def __init__(self, event_link: str):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label='I Will Be There', style=discord.ButtonStyle.link, url=event_link))

@bot.tree.command(name="mark", description="Staff only: Create a Mark Attendance embed from a TruckersMP event link.")
@app_commands.describe(
    event_link="TruckersMP event URL, e.g. https://truckersmp.com/events/12345",
    channel="Channel to post the embed",
    color="Embed color name or hex (optional)",
    mention_role="Optional role to mention"
)
async def mark(interaction: discord.Interaction, event_link: str, channel: discord.TextChannel, color: str = "blue", mention_role: discord.Role = None):
    if not is_staff_member(interaction.user):
        return await interaction.response.send_message("❌ You are not staff.", ephemeral=True)

    await interaction.response.defer(thinking=True, ephemeral=True)

    # Extract numeric event id
    match = re.search(r"/events/(\d+)", event_link)
    if not match:
        return await interaction.followup.send("❌ Could not find an event ID in that link.", ephemeral=True)

    event_id = match.group(1)
    api_url = f"https://api.truckersmp.com/v2/events/{event_id}"

    # Fetch from TruckersMP API
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
        return await interaction.followup.send("❌ Could not fetch event data.", ephemeral=True)

    event_info = data["response"]
    event_name = event_info.get("name", "TruckersMP Event")

    # Fetch meetupDateTime
    event_start = event_info.get("meetupDateTime")
    event_banner = event_info.get("banner")
    event_vtc = event_info.get("creator")
    vtc_avatar = None
    if isinstance(event_vtc, dict):
        vtc_avatar = event_vtc.get("avatar") or event_vtc.get("logo")

    embed_color = parse_color(color) or discord.Color.blue()

    # Format footer timestamp
    footer_text = "Powered by NepPath"
    if event_start:
        evt = event_start.rstrip("Z")
        try:
            dt = datetime.fromisoformat(evt).replace(tzinfo=timezone.utc)
            utc_str = dt.strftime("%H:%M UTC")
            npt_dt = dt + timedelta(hours=5, minutes=45)
            npt_str = npt_dt.strftime("%H:%M NPT")
            footer_text = f"Powered by NepPath | {utc_str} | {npt_str}"
        except Exception:
            pass

    embed = discord.Embed(
        title=event_name,
        description="**🙏 𝐏𝐥𝐳 𝐊𝐢𝐧𝐝𝐥𝐲 𝐌𝐚𝐫𝐤 𝐘𝐨𝐔𝐑 𝐀𝐭𝐭𝐞𝐧𝐝𝐚𝐧𝐜𝐞 𝐎𝐧 𝐓𝐡𝐢𝐬 𝐄𝐯𝐞𝐧𝐭 : ❤️**",
        color=embed_color
    )

    if event_banner:
        embed.set_image(url=event_banner)
    if vtc_avatar:
        embed.set_thumbnail(url=vtc_avatar)

    embed.set_footer(text=footer_text)

    view = MarkAttendanceView(event_link=event_link)

    # Mention role if selected
    content = mention_role.mention if mention_role else None

    await channel.send(content=content, embed=embed, view=view)
    await interaction.followup.send(f"✅ Attendance embed sent to {channel.mention}", ephemeral=True)

# ---------- /accepted ----------

@bot.tree.command(name="accepted", description="Staff only: Send invitation accepted embed.")
@app_commands.describe(
    vtc_name="VTC Name",
    user="User to mention",
    slot_number="Approved slot number",
    color="Embed color name or hex (optional)"
)
async def accepted(
    interaction: discord.Interaction,
    vtc_name: str,
    user: discord.Member,
    slot_number: str,
    color: str = "green"
):
    if not is_staff_member(interaction.user):
        return await interaction.response.send_message("❌ You are not staff.", ephemeral=True)

    embed_color = parse_color(color) or discord.Color.green()

    embed = discord.Embed(
        title="🟢 Invitation Accepted",
        description=(
            f"Dear **{vtc_name}**, {user.mention} 🙏\n\n"
            f"🟢 𝙄𝙣𝙫𝙞𝙩𝙖𝙩𝙞𝙤𝙣 𝙝𝙖𝙨 𝙗𝙚𝙚𝙣 𝘼𝙘𝙘𝙚𝙥𝙩𝙚𝙙. ♥️\n\n"
            f"We sincerely thank you for inviting **NepPath** to participate in your event. "
            f"We are pleased to confirm our attendance and look forward to being part of this valuable opportunity.\n\n"
            f"**🛷 Slot Requested: {slot_number} Kindly confirm our slot.**\n\n"
            f"<:calendar1:1398462389623586847>  **Your Event Marked Down Here: ⤵️ **\n"
            f"https://discord.com/channels/1395555672946643005/1396109795370471424\n\n"
            f"Should you require any further information or assistance, please feel free to contact us.\n\n"
            f"**<a:red_arrow:1396694832121905295> "
            f"If done: Plz Kindly send a ticket close confirmation. 🔒**\n\n"
            f"---\n\n"
            f"Best regards,\n"
            f"**NepPath**"
        ),
        color=embed_color,
        timestamp=datetime.utcnow()
    )

    embed.set_footer(text="NepPath")

    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("✅ Acceptance embed sent.", ephemeral=True)

# ---------------- End of Part 3 ----------------
# ---------------- bot.py — Part 4 ----------------

# ---------- Bot Ready ----------

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} ({bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} commands globally.")
    except Exception as e:
        print("❌ Failed to sync commands:", e)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} ({bot.user.id})")

    # Register external commands
    setup_decline_command(bot, is_staff_member)

    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} commands globally.")
    except Exception as e:
        print("❌ Failed to sync commands:", e)

@bot.event
async def on_ready():
    setup_decline_time_command(bot, is_staff_member)
    # then sync commands

# ---------- Run Bot ----------

if not BOT_TOKEN:
    print("❌ BOT_TOKEN not set in environment. Please set BOT_TOKEN in your .env file.")
else:
    bot.run(BOT_TOKEN)

# ---------------- End of Part 4 ----------------
