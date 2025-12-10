# main.py - NepPath Nepal VTC Bot | Fixed Imports & Custom Pagination
import discord
from discord.ext import commands
from discord import app_commands
import os
from dotenv import load_dotenv
import requests
import feedparser
from datetime import datetime

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN missing!")

VTC_ID = 81586
API_BASE = "https://api.truckersmp.com/v2"
RSS_URL = f"https://truckersmp.com/vtc/{VTC_ID}/news/rss"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree

# ===== ATTENDANCE SYSTEM =====
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
        embed.set_image(url="https://i.imgur.com/ScaniaDuo.jpg")  # Replace with your convoy image
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

# ===== ON READY =====
@bot.event
async def on_ready():
    print(f"NepPath Bot Online → {bot.user} ({bot.user.id})")
    await tree.sync()
    bot.add_view(AttendanceView())
    print("Slash commands synced. Bot is fully ready!")

# ===== /ANNOUNCEMENT =====
@tree.command(name="announcement", description="Latest NepPath announcement")
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

# ===== /MARK_ATTENDANCE =====
@tree.command(name="mark_attendance", description="Mark attendance like the app!")
async def mark_attendance(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Mark Your Attendance",
        description="Plz Kindly Mark Your Attendance On This Event : ❤️",
        color=0x8B4513
    )
    embed.set_image(url="https://i.imgur.com/ScaniaDuo.jpg")  # Your convoy image
    embed.set_footer(text="NepPath Nepal • Public Convoy Series")
    await interaction.response.send_message(embed=embed, view=AttendanceView())

# ===== /UPCOMING_EVENTS =====
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
                value=f"**{start.strftime('%d %B %Y - %H:%M UTC')}**\nServer: {e.get('serverName', 'TBD')}",
                inline=False
            )
        embed.set_thumbnail(url="https://truckersmp.com/storage/vtc/81586/logo.png")
        await interaction.followup.send(embed=embed)
    except Exception as ex:
        await interaction.followup.send(f"Error fetching events: {ex}")

# ===== /UPCOMING =====
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
            embed.add_field(
                name=e["name"],
                value=start.strftime('%d %B %Y - %H:%M UTC'),
                inline=False
            )
        await interaction.followup.send(embed=embed)
    except Exception as ex:
        await interaction.followup.send(f"Error: {ex}")

# ===== /VTC_MEMBERS WITH CUSTOM PAGINATION =====
@tree.command(name="vtc_members", description="Full member list with join dates")
async def vtc_members(interaction: discord.Interaction):
    await interaction.response.defer()

    try:
        # Fetch data
        info_r = requests.get(f"{API_BASE}/vtc/{VTC_ID}", timeout=10)
        info = info_r.json()["response"]
        total = info.get("memberCount", "N/A")
        founded = info.get("creationDate", "N/A")[:10]

        members_r = requests.get(f"{API_BASE}/vtc/{VTC_ID}/members", timeout=10)
        members_data = members_r.json()
        if not members_data.get("response"):
            await interaction.followup.send("Failed to load members.")
            return

        members = members_data["response"]
        members.sort(key=lambda x: x.get("joinDate", "9999-99-99"))  # Oldest first

        # Pagination setup (8 per page)
        per_page = 8
        pages = [members[i:i + per_page] for i in range(0, len(members), per_page)]
        current_page = 0

        def create_embed(page_num):
            embed = discord.Embed(
                title="NepPath Nepal VTC Members",
                description=f"**Total Drivers:** {total}\n**Founded:** {founded}\n\n**Member List:**",
                color=0xFF4500
            )
            embed.set_thumbnail(url="https://truckersmp.com/storage/vtc/81586/logo.png")
            embed.set_footer(text=f"Page {page_num + 1}/{len(pages)} • NepPath Nepal")

            page_members = pages[page_num]
            for m in page_members:
                user = m.get("user", {})
                name = user.get("username", "Unknown")
                join = m.get("joinDate", "Unknown")[:10]
                role = m.get("role", {}).get("name", "Driver")

                # Simple role emoji
                role_emoji = "👑" if "owner" in role.lower() else "🛡️" if "manager" in role.lower() else "🎉" if "event" in role.lower() else "🚛"
                
                embed.add_field(
                    name=f"{role_emoji} {name}",
                    value=f"**Joined:** {join}\n**Role:** {role}",
                    inline=False
                )
            return embed

        # Initial message
        msg = await interaction.followup.send(embed=create_embed(current_page))

        # Custom pagination view
        class MemberPaginator(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=300)  # 5 min timeout
                self.current_page = 0

            @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.grey)
            async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
                if self.current_page > 0:
                    self.current_page -= 1
                    await interaction.response.edit_message(embed=create_embed(self.current_page))

            @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.grey)
            async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
                if self.current_page < len(pages) - 1:
                    self.current_page += 1
                    await interaction.response.edit_message(embed=create_embed(self.current_page))

            @discord.ui.button(label="Stop", style=discord.ButtonStyle.red)
            async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
                self.stop()
                await interaction.response.edit_message(view=None)

        if len(pages) > 1:
            await msg.edit(view=MemberPaginator())
        # For single page, no view needed

    except Exception as e:
        await interaction.followup.send(f"Error loading members: {e}")

# ===== START BOT =====
bot.run(BOT_TOKEN)
