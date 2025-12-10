# main.py - NepPath Nepal VTC Bot | Full Version with Join Dates
import discord
from discord.ext import commands
from discord import app_commands
from discord.ext import pages  # For pagination
import os
from dotenv import load_dotenv
import requests
import feedparser
from datetime import datetime

# Load .env (local) — Zeabur uses dashboard variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not found! Set in .env or Zeabur variables.")

# NepPath VTC Details
VTC_ID = 81586
API_BASE = "https://api.truckersmp.com/v2"
RSS_URL = f"https://truckersmp.com/vtc/{VTC_ID}/news/rss"

# Intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree

# =================== MARK ATTENDANCE MODAL ===================
class AttendanceModal(discord.ui.Modal, title="Mark Attendance"):
    event_name = discord.ui.TextInput(
        label="Event Name",
        placeholder="e.g. INDIAN CARRIERS FEBRUARY CONVOY",
        required=True,
        max_length=100
    )

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Attendance Marked!",
            description=f"Plz Kindly Mark Your Attendance On This Event :\n\n**{self.event_name.value}** ❤️",
            color=0xFF4500
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_image(url="https://i.imgur.com/ScaniaDuo.jpg")  # ← Change to your convoy photo
        embed.set_footer(text="Doing what we do best! • NepPath Nepal")
        embed.timestamp = datetime.utcnow()

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="I Will Be There", style=discord.ButtonStyle.red, emoji="❤️", disabled=True))
        await interaction.response.send_message(embed=embed, ephemeral=False)

class AttendanceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='Go-To Hit "I Will Be There"', style=discord.ButtonStyle.red, emoji="❤️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AttendanceModal())

# =================== ON READY ===================
@bot.event
async def on_ready():
    print(f"NepPath Bot Online → {bot.user} ({bot.user.id})")
    await tree.sync()
    bot.add_view(AttendanceView())
    print("Slash commands synced. Bot is fully ready!")

# =================== COMMANDS ===================

@tree.command(name="announcement", description="Latest NepPath announcement")
async def announcement(interaction: discord.Interaction):
    await interaction.response.defer()
    feed = feedparser.parse(RSS_URL)
    if not feed.entries:
        await interaction.followup.send("No announcements found.")
        return
    latest = feed.entries[0]
    embed = discord.Embed(title="Latest Announcement", description=latest.summary[:1500], url=latest.link, color=0xFF4500)
    embed.set_author(name="NepPath Management")
    embed.set_thumbnail(url="https://truckersmp.com/storage/vtc/81586/logo.png")
    embed.timestamp = datetime(*latest.published_parsed[:6])
    await interaction.followup.send(embed=embed)

@tree.command(name="mark_attendance", description="Mark attendance like the app!")
async def mark_attendance(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Mark Your Attendance",
        description="Plz Kindly Mark Your Attendance On This Event : ❤️",
        color=0x8B4513
    )
    embed.set_image(url="https://i.imgur.com/ScaniaDuo.jpg")
    embed.set_footer(text="NepPath Nepal • Public Convoy Series")
    await interaction.response.send_message(embed=embed, view=AttendanceView())

@tree.command(name="upcoming_events", description="Events NepPath is attending")
async def upcoming_events(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        r = requests.get(f"{API_BASE}/vtc/{VTC_ID}/events/attending", timeout=10)
        data = r.json()
        if not data.get("response"):
            await interaction.followup.send("No upcoming events.")
            return
        embed = discord.Embed(title="Upcoming Events (Attending)", color=0x00FF00)
        for e in data["response"][:8]:
            start = datetime.fromisoformat(e["startDate"].replace("Z", "+00:00"))
            embed.add_field(
                name=e["name"],
                value=f"**{start.strftime('%d %B %Y - %H:%M UTC')}**\nServer: {e.get('serverName','TBD')}",
                inline=False
            )
        embed.set_thumbnail(url="https://truckersmp.com/storage/vtc/81586/logo.png")
        await interaction.followup.send(embed=embed)
    except:
        await interaction.followup.send("Error fetching events.")

@tree.command(name="upcoming", description="All upcoming NepPath events")
async def upcoming(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        r = requests.get(f"{API_BASE}/vtc/{VTC_ID}/events", timeout=10)
        data = r.json()
        if not data.get("response"):
            await interaction.followup.send("No events.")
            return
        embed = discord.Embed(title="All Upcoming NepPath Events", color=0xFF4500)
        for e in data["response"][:8]:
            start = datetime.fromisoformat(e["startDate"].replace("Z", "+00:00"))
            embed.add_field(name=e["name"], value=start.strftime('%d %B %Y - %H:%M UTC'), inline=False)
        await interaction.followup.send(embed=embed)
    except:
        await interaction.followup.send("Error.")

# =================== FULL VTC MEMBERS WITH JOIN DATES ===================
@tree.command(name="vtc_members", description="Full member list with join dates")
async def vtc_members(interaction: discord.Interaction):
    await interaction.response.defer()

    try:
        # Get VTC info
        info = requests.get(f"{API_BASE}/vtc/{VTC_ID}").json()["response"]
        total = info.get("memberCount", "N/A")
        founded = info.get("creationDate", "N/A")[:10]

        # Get full member list
        members_data = requests.get(f"{API_BASE}/vtc/{VTC_ID}/members").json()
        if not members_data.get("response"):
            await interaction.followup.send("Failed to load members.")
            return

        members = members_data["response"]
        members.sort(key=lambda x: x.get("joinDate", "9999-99-99"))  # Oldest first

        embeds = []
        for i in range(0, len(members), 10):
            embed = discord.Embed(
                title="NepPath Nepal VTC Members",
                description=f"**Total Drivers:** {total}\n**Founded:** {founded}\n\n**Member List:**",
                color=0xFF4500
            )
            embed.set_thumbnail(url="https://truckersmp.com/storage/vtc/81586/logo.png")
            embed.set_footer(text=f"Page {(i//10)+1}/{((len(members)-1)//10)+1} • NepPath Nepal")

            for m in members[i:i+10]:
                user = m.get("user", {})
                name = user.get("username", "Unknown")
                join = m.get("joinDate", "Unknown")[:10]
                role = m.get("role", {}).get("name", "Driver")

                # Role emojis
                emoji = "Founder" if "owner" in role.lower() else "CEO" if "manager" in role.lower() else "Event" if "event" in role.lower() else "Driver"

                embed.add_field(
                    name=f"{emoji} {name}",
                    value=f"**Joined:** {join}\n**Role:** {role}",
                    inline=False
                )
            embeds.append(embed)

        if len(embeds) == 1:
            await interaction.followup.send(embed=embeds[0])
        else:
            paginator = pages.Paginator(pages=embeds)
            await paginator.respond(interaction)

    except Exception as e:
        await interaction.followup.send(f"Error: {e}")

# =================== START BOT ===================
bot.run(BOT_TOKEN)
