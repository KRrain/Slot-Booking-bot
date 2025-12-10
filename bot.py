# main.py - NepPath VTC Discord Bot (Zeabur Ready)
import discord
from discord.ext import commands
from discord import app_commands
import os
from dotenv import load_dotenv
import requests
import feedparser
from datetime import datetime

# Load .env (for local testing) — Zeabur uses dashboard variables instead
load_dotenv()

# Bot Token (Zeabur injects this as environment variable)
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not found! Set it in .env or Zeabur variables.")

# NepPath VTC Info
VTC_ID = 81586
API_BASE = "https://api.truckersmp.com/v2"
RSS_URL = f"https://truckersmp.com/vtc/{VTC_ID}/news/rss"

# Intents
intents = discord.Intents.default()
intents.message_content = True

# Bot Setup
bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree

# ------------------- Attendance Modal -------------------
class AttendanceModal(discord.ui.Modal, title="Mark Attendance"):
    event_name = discord.ui.TextInput(
        label="Event Name",
        placeholder="e.g. INDIAN CARRIERS FEBRUARY PUBLIC CONVOY",
        required=True,
        max_length=100,
        style=discord.TextStyle.short
    )

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Attendance Marked!",
            description=f"Plz Kindly Mark Your Attendance On This Event :\n\n**{self.event_name.value}** ❤️",
            color=0xFF4500  # Scania Orange
        )
        embed.set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.display_avatar.url
        )
        embed.set_image(url="https://i.imgur.com/ScaniaDuo.jpg")  # Replace with your convoy image
        embed.set_footer(text="Doing what we do best! • NepPath Nepal")
        embed.timestamp = datetime.utcnow()

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="I Will Be There", style=discord.ButtonStyle.red, emoji="❤️", disabled=True))

        await interaction.response.send_message(embed=embed, ephemeral=False)

# ------------------- Persistent Button View -------------------
class AttendanceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # Persistent across restarts

    @discord.ui.button(label='Go-To Hit "I Will Be There"', style=discord.ButtonStyle.red, emoji="❤️")
    async def confirm_attendance(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AttendanceModal())

# ------------------- On Ready -------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} | {bot.user.id}")
    print("Syncing slash commands...")
    try:
        synced = await tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print("Sync failed:", e)
    
    # Register persistent view
    bot.add_view(AttendanceView())
    print("NepPath Bot is fully ready!")

# ------------------- /announcement -------------------
@tree.command(name="announcement", description="Latest announcement from NepPath VTC")
async def announcement(interaction: discord.Interaction):
    await interaction.response.defer()
    feed = feedparser.parse(RSS_URL)
    
    if not feed.entries:
        await interaction.followup.send("No announcements found.")
        return

    latest = feed.entries[0]
    embed = discord.Embed(
        title="Latest Announcement",
        description=latest.summary[:1500],
        url=latest.link,
        color=0xFF4500
    )
    embed.set_author(name="NepPath Management")
    embed.set_thumbnail(url="https://truckersmp.com/storage/vtc/81586/logo.png")
    embed.timestamp = datetime(*latest.published_parsed[:6])
    
    await interaction.followup.send(embed=embed)

# ------------------- /mark_attendance -------------------
@tree.command(name="mark_attendance", description="Mark attendance like the app!")
async def mark_attendance(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Mark Your Attendance",
        description="Plz Kindly Mark Your Attendance On This Event : ❤️\n\nClick the button below to confirm!",
        color=0x8B4513
    )
    embed.set_image(url="https://i.imgur.com/ScaniaDuo.jpg")  # Your convoy image
    embed.set_footer(text="NepPath Nepal • February Public Convoy")

    view = AttendanceView()
    await interaction.response.send_message(embed=embed, view=view)

# ------------------- /upcoming_events (Attending) -------------------
@tree.command(name="upcoming_events", description="Events NepPath is attending")
async def upcoming_events(interaction: discord.Interaction):
    await interaction.response.defer()
    url = f"{API_BASE}/vtc/{VTC_ID}/events/attending"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()

        if data.get("error") or not data.get("response"):
            await interaction.followup.send("No upcoming events found.")
            return

        embed = discord.Embed(title="Upcoming Events (Attending)", color=0x00FF00)
        for event in data["response"][:8]:
            start = datetime.fromisoformat(event["startDate"].replace("Z", "+00:00"))
            embed.add_field(
                name=event["name"],
                value=f"**Date:** {start.strftime('%d %B %Y - %H:%M UTC')}\n"
                      f"**Server:** {event.get('serverName', 'TBD')}\n"
                      f"**Attendees:** {event.get('attendingCount', 0)}",
                inline=False
            )
        embed.set_thumbnail(url="https://truckersmp.com/storage/vtc/81586/logo.png")
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"API Error: {e}")

# ------------------- /upcoming (All Events) -------------------
@tree.command(name="upcoming", description="All upcoming NepPath events")
async def upcoming(interaction: discord.Interaction):
    await interaction.response.defer()
    url = f"{API_BASE}/vtc/{VTC_ID}/events"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()

        if data.get("error") or not data.get("response"):
            await interaction.followup.send("No events found.")
            return

        embed = discord.Embed(title="All Upcoming NepPath Events", color=0xFF4500)
        for event in data["response"][:8]:
            start = datetime.fromisoformat(event["startDate"].replace("Z", "+00:00"))
            embed.add_field(
                name=event["name"],
                value=f"**Date:** {start.strftime('%d %B %Y - %H:%M')}\n**Type:** {event.get('eventType', 'Convoy')}",
                inline=False
            )
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"Error: {e}")

# ------------------- /vtc_members -------------------
@tree.command(name="vtc_members", description="Show NepPath member count")
async def vtc_members(interaction: discord.Interaction):
    url = f"{API_BASE}/vtc/{VTC_ID}"
    r = requests.get(url)
    data = r.json()

    if data.get("error"):
        await interaction.response.send_message("Failed to fetch VTC info.")
        return

    vtc = data["response"]
    embed = discord.Embed(title="NepPath Nepal VTC", color=0xFF4500)
    embed.add_field(name="Members", value=vtc.get("memberCount", "N/A"), inline=True)
    embed.add_field(name="Founded", value=vtc.get("creationDate", "N/A")[:10], inline=True)
    embed.add_field(name="View Full List", value=f"[TruckersMP](https://truckersmp.com/vtc/{VTC_ID}/members)", inline=False)
    embed.set_thumbnail(url=vtc.get("logo", ""))
    await interaction.response.send_message(embed=embed)

# ------------------- Start Bot -------------------
if __name__ == "__main__":
    bot.run(BOT_TOKEN)
