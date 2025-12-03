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

# -------- CONFIG --------
STAFF_ROLE_IDS = [
    1395579577555878012,  # Example staff role IDs
    1395579347804487769
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

booking_messages: dict[int, dict] = {}  # guild_id: {message: Message, slots: {slot: vtc_name or None}}

def is_staff(member: discord.Member) -> bool:
    return any(role.id in STAFF_ROLE_IDS for role in member.roles)

# -------- Views and Modals --------
class BookSlotModal(discord.ui.Modal, title="Book Slot"):
    vtc_name = discord.ui.TextInput(label="VTC Name", placeholder="Enter your VTC name", max_length=100)
    slot_number = discord.ui.TextInput(label="Slot Number", placeholder="Enter slot number(s) e.g. 1,2,3", max_length=50)

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        selected_slots = [s.strip().capitalize() for s in self.slot_number.value.split(",") if s.strip()]
        if not selected_slots:
            return await interaction.response.send_message("❌ Invalid slot numbers.", ephemeral=True)

        # Save requests in staff log
        log_channel = bot.get_channel(STAFF_LOG_CHANNEL_ID)
        if not log_channel:
            return await interaction.response.send_message("❌ Staff log channel not found.", ephemeral=True)

        for slot in selected_slots:
            embed = discord.Embed(title="📥 Slot Booking Request", color=discord.Color.orange())
            embed.add_field(name="User", value=interaction.user.mention)
            embed.add_field(name="VTC Name", value=self.vtc_name.value)
            embed.add_field(name="Slot Number", value=slot)
            embed.set_footer(text="Waiting for staff action")

            view = ApproveDenyView(user_id=interaction.user.id, vtc_name=self.vtc_name.value, slot_number=slot, guild_id=guild_id)
            await log_channel.send(embed=embed, view=view)

        await interaction.response.send_message(f"✅ Your request(s) submitted: {', '.join(selected_slots)}", ephemeral=True)


class BookSlotView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📌 Book Slot", style=discord.ButtonStyle.green)
    async def book_slot_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        try:
            await interaction.response.send_modal(BookSlotModal())
        except Exception:
            await interaction.followup.send("❌ Something went wrong.", ephemeral=True)


class ApproveDenyView(discord.ui.View):
    def __init__(self, user_id: int, vtc_name: str, slot_number: str, guild_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.vtc_name = vtc_name
        self.slot_number = slot_number
        self.guild_id = guild_id
        self.approved = False

    async def notify_user(self, approved: bool):
        try:
            user = await bot.fetch_user(self.user_id)
            if approved:
                await user.send(f"✅ Your slot {self.slot_number} has been **approved**! VTC: {self.vtc_name}")
            else:
                await user.send(f"❌ Your slot {self.slot_number} has been **denied**.")
        except Exception:
            pass

    @discord.ui.button(label="✅ Approve", style=discord.ButtonStyle.green)
    async def approve(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.approved:
            return await interaction.response.send_message("❌ Already approved.", ephemeral=True)
        if not is_staff(interaction.user):
            return await interaction.response.send_message("❌ You are not staff.", ephemeral=True)

        await self.notify_user(True)
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.set_footer(text=f"✅ Approved by {interaction.user}")
        await interaction.message.edit(embed=embed, view=None)
        self.approved = True
        await interaction.response.send_message("✅ Slot approved.", ephemeral=True)

    @discord.ui.button(label="❌ Deny", style=discord.ButtonStyle.red)
    async def deny(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.approved:
            return await interaction.response.send_message("❌ Already approved.", ephemeral=True)
        if not is_staff(interaction.user):
            return await interaction.response.send_message("❌ You are not staff.", ephemeral=True)

        await self.notify_user(False)
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.set_footer(text=f"❌ Denied by {interaction.user}")
        await interaction.message.edit(embed=embed, view=None)
        await interaction.response.send_message("❌ Slot denied.", ephemeral=True)

# -------- Slash Commands --------
@bot.tree.command(name="create", description="Staff only: Create booking message")
async def create(interaction: discord.Interaction, title: str, slots: str):
    if not is_staff(interaction.user):
        return await interaction.response.send_message("❌ You are not staff.", ephemeral=True)

    slot_list = [f"Slot {i}" for i in range(1, int(slots)+1)]
    desc = "\n".join(slot_list)
    embed = discord.Embed(title=title, description=desc, color=discord.Color.blue())
    msg = await interaction.channel.send(embed=embed, view=BookSlotView())
    booking_messages[interaction.guild_id] = {"message": msg, "slots": {slot: None for slot in slot_list}}
    await interaction.response.send_message(f"✅ Booking message created with {slots} slots.", ephemeral=True)

# -------- Bot Ready --------
@bot.event
async def on_ready():
    print(f"Bot online as {bot.user}")
    bot.add_view(BookSlotView())
    try:
        await bot.tree.sync()
        print("Slash commands synced.")
    except Exception as e:
        print("Sync failed:", e)

# -------- Run Bot --------
bot.run(BOT_TOKEN)
