import os
import discord
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
VTC_ROLE_ID = int(os.getenv("VTC_ROLE_ID"))
GUILD_ID = int(os.getenv("GUILD_ID")) if os.getenv("GUILD_ID") else None

intents = discord.Intents.default()
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

@client.event
async def on_ready():
    print(f"Logged in as {client.user} (ID: {client.user.id})")
    print("Syncing slash commands...")

    if GUILD_ID:
        guild = discord.Object(id=GUILD_ID)
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
        print(f"Commands synced to guild {GUILD_ID} (instant)")
    else:
        await tree.sync()
        print("Commands synced globally (may take up to 1 hour)")

    print("Bot is ready!")


@tree.command(name="vtc", description="VTC Commands")
@app_commands.subcommand(name="members", description="Show all VTC members")
async def vtc_members(interaction: discord.Interaction):
    await interaction.response.defer()

    if VTC_ROLE_ID not in [role.id for role in interaction.guild.roles]:
        await interaction.followup.send("Error: VTC role ID is invalid or role doesn't exist.")
        return

    # Fetch all members (important for large servers)
    await interaction.guild.chunk()

    vtc_members = [m for m in interaction.guild.members if VTC_ROLE_ID in [r.id for r in m.roles]]

    if m.roles]

    if not vtc_members:
        await interaction.followup.send("No members found with the VTC role.")
        return

    # Sort by display name
    vtc_members.sort(key=lambda m: m.display_name.lower())

    lines = []
    for member in vtc_members:
        status = member.status
        emoji = "🟢" if status == discord.Status.online else \
                "🟡" if status == discord.Status.idle else \
                "🔴" if status == discord.Status.dnd else "⚫"
        lines.append(f"{emoji} **{member.display_name}** (`{member}`)")

    description = "\n".join(lines)

    embeds = []
    title = f"🚛 VTC Members ({len(vtc_members)})"
    
    # Split if too long for one embed
    while description:
        chunk = description[:4000]  # leave room for ```
        # Find last newline to avoid cutting words
        if len(description) > 4000:
            cut = chunk.rfind("\n")
            chunk = chunk[:cut]
            description = description[cut+1:]
        else:
            description = ""

        embed = discord.Embed(
            title=title if not embeds else "Continued...",
            description=chunk or "*No more members*",
            color=0x00ff00
        )
        embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        embed.timestamp = discord.utils.utcnow()
        embeds.append(embed)

    await interaction.followup.send(embeds=embeds)


# Run the bot
client.run(TOKEN)
