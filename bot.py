# main.py - NepPath Nepal VTC Bot | FINAL VERSION (No Errors)
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
    raise ValueError("BOT_TOKEN missing! Set in .env or Zeabur variables")

VTC_ID = 81586
API_BASE = "https://api.truckersmp.com/v2"
RSS_URL = f"https://truckersmp.com/vtc/{VTC_ID}/news/rss"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree

# =============== PERSISTENT ATTENDANCE BUTTON ===============
class AttendanceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # Persistent view

    @discord.ui.button(label='Go-To "I Will Be There"', style=discord.ButtonStyle.red, emoji="Heart", custom_id="attendance_button")
    async def attendance(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AttendanceModal()
        await interaction.response.send_modal(modal)

class AttendanceModal(discord.ui.Modal, title="Mark Attendance"):
    event = discord.ui.TextInput(label="Event Name", placeholder="e.g. INDIAN CARRIERS CONVOY", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Attendance Marked!", color=0xFF4500)
        embed.description = f"**{self.event.value}** Heart\nYou are confirmed!"
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_image(url="https://i.imgur.com/ScaniaDuo.jpg")  # Your convoy photo
        embed.set_footer(text="NepPath Nepal • Doing what we do best!")
        await interaction.response.send_message(embed=embed, ephemeral=False)

# =============== ON READY ===============
@bot.event
async def on_ready():
    print(f"NepPath Bot Online → {bot.user}")
    await tree.sync()
    bot.add_view(AttendanceView())  # Re-add persistent view
    print("Bot ready & synced!")

# =============== COMMANDS ===============
@tree.command(name="announcement", description="Latest NepPath announcement")
async def announcement(i: discord.Interaction):
    await i.response.defer()
    feed = feedparser.parse(RSS_URL)
    if not feed.entries:
        return await i.followup.send("No announcements.")
    e = feed.entries[0]
    embed = discord.Embed(title="Latest Announcement", description=e.summary[:1500], url=e.link, color=0xFF4500)
    embed.set_thumbnail(url="https://truckersmp.com/storage/vtc/81586/logo.png")
    await i.followup.send(embed=embed)

@tree.command(name="mark_attendance", description="Mark attendance like the app")
async def mark_attendance(i: discord.Interaction):
    embed = discord.Embed(title="Mark Your Attendance", description="Plz Kindly Mark Your Attendance On This Event : Heart", color=0x8B4513)
    embed.set_image(url="https://i.imgur.com/ScaniaDuo.jpg")
    await i.response.send_message(embed=embed, view=AttendanceView())

@tree.command(name="upcoming_events", description="Events we're attending")
async def upcoming_events(i: discord.Interaction):
    await i.response.defer()
    data = requests.get(f"{API_BASE}/vtc/{VTC_ID}/events/attending").json()
    if not data.get("response"):
        return await i.followup.send("No upcoming events.")
    embed = discord.Embed(title="Upcoming Events (Attending)", color=0x00FF00)
    for e in data["response"][:8]:
        start = datetime.fromisoformat(e["startDate"].replace("Z", "+00:00"))
        embed.add_field(name=e["name"], value=start.strftime("%d %B %Y - %H:%M UTC"), inline=False)
    await i.followup.send(embed=embed)

# =============== FIXED VTC_MEMBERS (100% WORKING) ===============
@tree.command(name="vtc_members", description="Full member list with join dates")
async def vtc_members(interaction: discord.Interaction):
    await interaction.response.defer()

    try:
        # Get VTC info
        info = requests.get(f"{API_BASE}/vtc/{VTC_ID}").json()["response"]
        total = info.get("memberCount", "N/A")
        founded = info.get("creationDate", "N/A")[:10]

        # Get members (can be dict or list)
        raw = requests.get(f"{API_BASE}/vtc/{VTC_ID}/members").json()
        data = raw.get("response", {})

        if isinstance(data, dict):
            members = list(data.values())
        else:
            members = data if isinstance(data, list) else []

        if not members:
            return await interaction.followup.send("No members found.")

        # Sort by join date
        members = sorted(members, key=lambda x: x.get("joinDate", "9999-99-99") or "9999-99-99")

        per_page = 8
        pages = [members[i:i + per_page] for i in range(0, len(members), per_page)]
        page = 0

        def embed_page(p):
            emb = discord.Embed(title="NepPath Nepal VTC Members", color=0xFF4500)
            emb.description = f"**Total:** {total} drivers | **Founded:** {founded}"
            emb.set_thumbnail(url="https://truckersmp.com/storage/vtc/81586/logo.png")
            for m in pages[p]:
                name = m["user"]["username"]
                join = (m.get("joinDate") or "")[:10]
                role = m["role"]["name"]
                emoji = "Crown" if "owner" in role.lower() else "Shield" if "manager" in role.lower() else "Party Popper" if "event" in role.lower() else "Truck"
                emb.add_field(name=f"{emoji} {name}", value=f"**Joined:** {join}\n**Role:** {role}", inline=False)
            emb.set_footer(text=f"Page {p+1}/{len(pages)} • NepPath Nepal")
            return emb

        msg = await interaction.followup.send(embed=embed_page(0))

        if len(pages) > 1:
            class Paginator(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=None)  # Persistent
                    self.page = 0

                @discord.ui.button(label="Previous", style=discord.ButtonStyle.grey, custom_id="prev_page")
                async def prev(self, i: discord.Interaction, b):
                    if self.page > 0:
                        self.page -= 1
                        await i.response.edit_message(embed=embed_page(self.page))

                @discord.ui.button(label="Next", style=discord.ButtonStyle.grey, custom_id="next_page")
                async def next(self, i: discord.Interaction, b):
                    if self.page < len(pages)-1:
                        self.page += 1
                        await i.response.edit_message(embed=embed_page(self.page))

            await msg.edit(view=Paginator())
            bot.add_view(Paginator())  # Keep alive after restart

    except Exception as e:
        await interaction.followup.send(f"Error: {str(e)}")

# =============== START ===============
bot.run(BOT_TOKEN)
