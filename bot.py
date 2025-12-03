# bot.py
import discord
from discord import app_commands
from discord.ext import commands
import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ===== CONFIG =====
STAFF_ROLE_IDS = [
    1395579577555878012,
    1395579347804487769,
    1395580379565527110,
    1395699038715642031,
    1395578532406624266,
]
STAFF_LOG_CHANNEL_ID = 1395811260351647934
# ==================

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

# In-memory storage: guild_id -> list of booking messages
# Each message: {"message": MessageObject, "slots": {slot_name: approved_vtc_name or None}}
booking_messages: dict[int, list[dict]] = {}


def is_staff_member(member: discord.Member) -> bool:
    return any(role.id in STAFF_ROLE_IDS for role in member.roles)


# ----------------- Views & Modals -----------------

class BookSlotModal(discord.ui.Modal, title="Book Slot"):
    vtc_name = discord.ui.TextInput(label="VTC Name", placeholder="Enter your VTC name", max_length=100)
    slot_number = discord.ui.TextInput(label="Slot Number", placeholder="Enter slot number(s) separated by commas", max_length=200)

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        selected_slots = [s.strip() for s in self.slot_number.value.split(",") if s.strip()]

        # Find which booking message contains the selected slots
        matched_messages = []
        for data in booking_messages.get(guild_id, []):
            message_slots = data["slots"]
            for slot in selected_slots:
                if slot in message_slots:
                    matched_messages.append((data, slot))

        if not matched_messages:
            return await interaction.response.send_message("❌ Slot(s) do not exist.", ephemeral=True)

        log_channel = bot.get_channel(STAFF_LOG_CHANNEL_ID)
        if not log_channel:
            return await interaction.response.send_message("❌ Staff log channel not found.", ephemeral=True)

        for data, slot in matched_messages:
            embed = discord.Embed(title="📥 Slot Booking Request", color=discord.Color.orange())
            embed.add_field(name="User", value=interaction.user.mention, inline=False)
            embed.add_field(name="VTC Name", value=self.vtc_name.value, inline=False)
            embed.add_field(name="Slot Number", value=slot, inline=False)
            embed.set_footer(text="Waiting for staff action")
            view = ApproveDenyView(user_id=interaction.user.id, vtc_name=self.vtc_name.value, slot_number=slot, data=data)
            await log_channel.send(embed=embed, view=view)

        await interaction.response.send_message(f"✅ Your request(s) submitted: {', '.join(selected_slots)}", ephemeral=True)


class BookSlotView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📌 Book Slot", style=discord.ButtonStyle.green, custom_id="book_slot_button")
    async def book_slot_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        try:
            await interaction.response.send_modal(BookSlotModal())
        except Exception:
            await interaction.followup.send("❌ Something went wrong.", ephemeral=True)


class ApproveDenyView(discord.ui.View):
    def __init__(self, user_id: int, vtc_name: str, slot_number: str, data: dict):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.vtc_name = vtc_name
        self.slot_number = slot_number
        self.data = data
        self.disabled = False

        # Disable buttons if already approved/denied
        if self.data["slots"].get(self.slot_number):
            self.disabled = True

    async def _notify_user(self, approved: bool):
        try:
            user = await bot.fetch_user(self.user_id)
            if approved:
                await user.send(f"✅ Your slot {self.slot_number} has been **approved**! VTC: {self.vtc_name}")
            else:
                await user.send(f"❌ Your slot {self.slot_number} has been **denied**.")
        except Exception:
            pass

    @discord.ui.button(label="✅ Approve", style=discord.ButtonStyle.green, custom_id="approve_button")
    async def approve(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.disabled:
            return await interaction.response.send_message("❌ Already processed.", ephemeral=True)
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ You are not staff.", ephemeral=True)

        await self._notify_user(approved=True)
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.set_footer(text=f"✅ Approved by {interaction.user}")
        await interaction.message.edit(embed=embed, view=None)
        interaction.response.send_message("Slot approved.", ephemeral=True)

        # Update booking message
        self.data["slots"][self.slot_number] = self.vtc_name
        original_msg: discord.Message = self.data["message"]
        updated_lines = [f"{s}: {v} ✅" if v else s for s, v in self.data["slots"].items()]
        new_embed = original_msg.embeds[0]
        new_embed.description = "\n".join(updated_lines)
        await original_msg.edit(embed=new_embed)

        self.disabled = True

    @discord.ui.button(label="❌ Deny", style=discord.ButtonStyle.red, custom_id="deny_button")
    async def deny(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.disabled:
            return await interaction.response.send_message("❌ Already processed.", ephemeral=True)
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ You are not staff.", ephemeral=True)

        await self._notify_user(approved=False)
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.set_footer(text=f"❌ Denied by {interaction.user}")
        await interaction.message.edit(embed=embed, view=None)
        interaction.response.send_message("Slot denied.", ephemeral=True)

        self.disabled = True


# ----------------- Slash Commands -----------------

@bot.tree.command(name="create", description="Staff only: Create booking message with slots.")
@app_commands.describe(channel="Channel to post booking message", title="Embed title",
                       slots="Comma-separated slots or range (e.g., 1-10)", color="Embed color (name or hex)", image="Optional image URL")
async def create(interaction: discord.Interaction, channel: discord.TextChannel, title: str, slots: str, color: str = "blue", image: str | None = None):
    if not isinstance(interaction.user, discord.Member) or not is_staff_member(interaction.user):
        return await interaction.response.send_message("❌ You are not staff.", ephemeral=True)

    # Parse slots
    slot_list = []
    for part in slots.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-")
            slot_list.extend([f"Slot {i}" for i in range(int(start), int(end) + 1)])
        else:
            slot_list.append(part)

    slot_dict = {s: None for s in slot_list}
    embed = discord.Embed(title=title, description="\n".join(slot_list), color=discord.Color.blue())
    if color.startswith("#"):
        try:
            embed.color = discord.Color(int(color.replace("#", ""), 16))
        except:
            pass
    elif color.lower() in COLOR_OPTIONS:
        embed.color = COLOR_OPTIONS[color.lower()]

    if image and image.startswith("http"):
        embed.set_image(url=image)

    sent_msg = await channel.send(embed=embed, view=BookSlotView())

    if interaction.guild_id not in booking_messages:
        booking_messages[interaction.guild_id] = []
    booking_messages[interaction.guild_id].append({"message": sent_msg, "slots": slot_dict})

    await interaction.response.send_message(f"✅ Booking message posted to {channel.mention}", ephemeral=True)


# ----------------- Start / Ready -----------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    bot.add_view(BookSlotView())
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print("Command sync failed:", e)


if __name__ == "__main__":
    bot.run(BOT_TOKEN)
