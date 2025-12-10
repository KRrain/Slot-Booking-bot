import os
import discord
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
VTC_ROLE_ID = int(os.getenv("VTC_ROLE_ID"))
GUILD_ID = os.getenv("GUILD_ID")
if GUILD_ID:
    GUILD_ID = int(GUILD_ID)

# Intents
intents = discord.Intents.default()
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

@client.event
async def on_ready():
    print(f"Bot connected as {client.user}")
    await tree.sync(guild=discord.Object(id=GUILD_ID) if GUILD_ID else None)
    print("Slash commands synced ✓")
    print("Bot is ready and stable!")


@tree.command(name="vtc", description="VTC Commands")
@app_commands.describe()
async def vtc(interaction: discord.Interaction):
    pass  # parent command


@vtc.command(name="members", description="Show full VTC member list")
async def members(interaction: discord.Interaction):
    await interaction.response.defer()

    # Safety check
    role = interaction.guild.get_role(VTC_ROLE_ID)
    if not role:
        await interaction.followup.send("❌ VTC role not found. Check VTC_ROLE_ID in Zeabur variables.")
        return

    # Fetch members safely
    members_with_role = [m for m in interaction.guild.members if role in m.roles]

    if not members_with_role:
        await interaction.followup.send("🚛 No VTC members found.")
        return

    # Sort alphabetically
    members_with_role.sort(key=lambda m: m.display_name.lower())

    # Build list with status
    lines = []
    for member in members_with_role:
        status = member.status
        emoji = "🟢" if status == discord.Status.online else \
                "🟡" if status == discord.Status.idle else \
                "🔴" if status == discord.Status.dnd else "⚫"
        lines.append(f"{emoji} **{discord.utils.escape_markdown(member.display_name)}** ({member})")

    # Split into multiple embeds if too long
    embeds = []
    chunk_size = 25  # ~25 members per embed looks clean
    for i in range(0, len(lines), chunk_size):
        chunk = "\n".join(lines[i:i + chunk_size])
        embed = discord.Embed(
            title="VTC Members" if i == 0 else "VTC Members (continued)",
            description=chunk,
            color=0x00ff00
        )
        embed.set_footer(text=f"Total: {len(members_with_role)} • Requested by {interaction.user}",
                         icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        embed.timestamp = discord.utils.utcnow()
        embeds.append(embed)

    await interaction.followup.send(embeds=embeds)


# Start bot
try:
    client.run(TOKEN)
except discord.LoginFailure:
    print("Invalid bot token! Check TOKEN in Zeabur variables.")
except Exception as e:
    print(f"Failed to start: {e}")
