# main.py – NepPath VTC Bot | Fully Fixed (No More Errors)
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

# ===== ATTENDANCE =====
class AttendanceModal(discord.ui.Modal, title="Mark Attendance"):
    event_name = discord.ui.TextInput(label="Event Name", placeholder="e.g. INDIAN CARRIERS CONVOY", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Attendance Marked!", color=0xFF4500)
        embed.description = f"**{self.event_name.value}** (Heart)\nPlz Kindly Mark Your Attendance On This Event"
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_image(url="https://i.imgur.com/ScaniaDuo.jpg")
        embed.set_footer(text="NepPath Nepal • Doing what we do best!")
        await interaction.response.send_message(embed=embed, ephemeral=False)

class AttendanceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label='Go-To "I Will Be There"', style=discord.ButtonStyle.red, emoji="(Heart)")
    async def btn(self, i: discord.Interaction, b):
        await i.response.send_modal(AttendanceModal())

@bot.event
async def on_ready():
    print(f"NepPath Bot Ready → {bot.user}")
    await tree.sync()
    bot.add_view(AttendanceView())
    print("Bot fully online!")

# ===== COMMANDS =====
@tree.command(name="announcement", description="Latest announcement")
async def announcement(i: discord.Interaction):
    await i.response.defer()
    feed = feedparser.parse(RSS_URL)
    if not feed.entries:
        await i.followup.send("No announcements.")
        return
    e = feed.entries[0]
    embed = discord.Embed(title="Latest Announcement", description=e.summary[:1500], url=e.link, color=0xFF4500)
    embed.set_thumbnail(url="https://truckersmp.com/storage/vtc/81586/logo.png")
    await i.followup.send(embed=embed)

@tree.command(name="mark_attendance", description="Mark attendance like the app")
async def mark_attendance(i: discord.Interaction):
    embed = discord.Embed(title="Mark Your Attendance", description="Plz Kindly Mark Your Attendance On This Event : (Heart)", color=0x8B4513)
    embed.set_image(url="https://i.imgur.com/ScaniaDuo.jpg")
    await i.response.send_message(embed=embed, view=AttendanceView())

@tree.command(name="upcoming_events", description="Events we're attending")
async def upcoming_events(i: discord.Interaction):
    await i.response.defer()
    data = requests.get(f"{API_BASE}/vtc/{VTC_ID}/events/attending").json()
    if not data.get("response"):
        await i.followup.send("No upcoming events.")
        return
    embed = discord.Embed(title="Upcoming Events (Attending)", color=0x00FF00)
    for e in data["response"][:8]:
        start = datetime.fromisoformat(e["startDate"].replace("Z", "+00:00"))
        embed.add_field(name=e["name"], value=start.strftime("%d %B %Y - %H:%M UTC"), inline=False)
    await i.followup.send(embed=embed)

# ===== FIXED VTC_MEMBERS (Handles dict AND list) =====
@tree.command(name="vtc_members", description="Full member list with join dates")
async def vtc_members(interaction: discord.Interaction):
    await interaction.response.defer()

    try:
        # Get VTC info
        info = requests.get(f"{API_BASE}/vtc/{VTC_ID}").json()["response"]
        total = info.get("memberCount", "N/A")
        founded = info.get("creationDate", "N/A")[:10]

        # Get members (can be dict or list!)
        raw = requests.get(f"{API_BASE}/vtc/{VTC_ID}/members").json()
        members_data = raw.get("response", {})

        # Convert dict → list if needed
        if isinstance(members_data, dict):
            members = list(members_data.values()) if members_data else []
        else:
            members = members_data if isinstance(members_data, list) else []

        if not members:
            await interaction.followup.send("No members found.")
            return

        # Sort by join date (oldest first)
        members = sorted(members, key=lambda x: x.get("joinDate", "9999-99-99") or "9999-99-99")

        per_page = 8
        pages = [members[i:i + per_page] for i in range(0, len(members), per_page)]
        current = 0

        def make_embed(page):
            embed = discord.Embed(title="NepPath Nepal VTC Members", color=0xFF4500)
            embed.description = f"**Total:** {total} drivers | **Founded:** {founded}"
            embed.set_thumbnail(url="https://truckersmp.com/storage/vtc/81586/logo.png")
            for m in pages[page]:
                name = m["user"]["username"]
                join = (m.get("joinDate") or "")[:10]
                role = m["role"]["name"]
                emoji = "Crown" if "owner" in role.lower() else "Shield" if "manager" in role.lower() else "Party" if "event" in role.lower() else "Truck"
                embed.add_field(name=f"{emoji} {name}", value=f"**Joined:** {join}\n**Role:** {role}", inline=False)
            embed.set_footer(text=f"Page {page+1}/{len(pages)}")
            return embed

        msg = await interaction.followup.send(embed=make_embed(0))

        if len(pages) > 1:
            class View(discord.ui.View):
                @discord.ui.button(label="Previous", style=discord.ButtonStyle.grey)
                async def prev(self, i: discord.Interaction, b):
                    nonlocal current
                    if current > 0:
                        current -= 1
                        await i.response.edit_message(embed=make_embed(current))

                @discord.ui.button(label="Next", style=discord.ButtonStyle.grey)
                async def next(self, i: discord.Interaction, b):
                    nonlocal current
                    if current < len(pages)-1:
                        current += 1
                        await i.response.edit_message(embed=make_embed(current))

            await msg.edit(view=View(timeout=300))

    except Exception as e:
        await interaction.followup.send(f"Error: {str(e)}")

bot.run(BOT_TOKEN)
