import os
import discord
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    print("ERROR: TOKEN is missing!")
    exit(1)

try:
    VTC_ROLE_ID = int(os.getenv("VTC_ROLE_ID", "0"))
except:
    print("ERROR: VTC_ROLE_ID must be a number")
    exit(1)

GUILD_ID = os.getenv("GUILD_ID")
if GUILD_ID:
    try:
        GUILD_ID = int(GUILD_ID)
    except:
        GUILD_ID = None

intents = discord.Intents.default()
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

@client.event
async def on_ready():
    print(f"Bot is alive → {client.user}")
    if GUILD_ID:
        await tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"Commands synced to guild {GUILD_ID}")
    else:
        await tree.sync()
        print("Commands synced globally")
    print("Bot ready – no more crashes!")

@tree.command(name="vtc", description="VTC commands")
async def vtc(interaction: discord.Interaction):
    pass

@vtc.command(name="members", description="Show all VTC members")
async def members(interaction: discord.Interaction):
    await interaction.response.defer()
    
    role = interaction.guild.get_role(VTC_ROLE_ID)
    if not role:
        await interaction.followup.send("VTC role not found – check VTC_ROLE_ID")
        return

    members = [m for m in interaction.guild.members if role in m.roles]
    if not members:
        await interaction.followup.send("No one has the VTC role yet")
        return

    members.sort(key=lambda m: m.display_name.lower())
    lines = []
    for m in members:
        emoji = "🟢" if m.status == discord.Status.online else "🟡" if m.status == discord.Status.idle else "🔴" if m.status == discord.Status.dnd else "⚫"
        lines.append(f"{emoji} **{discord.utils.escape_markdown(m.display_name)}** ({m})")

    embeds = []
    for i in range(0, len(lines), 25):
        embed = discord.Embed(
            title="VTC Members" if i == 0 else "VTC Members (continued)",
            description="\n".join(lines[i:i+25]),
            color=0x00ff00
        )
        embed.set_footer(text=f"Total: {len(members)} • Requested by {interaction.user}")
        embeds.append(embed)

    await interaction.followup.send(embeds=embeds)

client.run(TOKEN)
